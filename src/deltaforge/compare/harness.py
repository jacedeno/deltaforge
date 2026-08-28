"""Comparison harness — every structure over the identical signal events.

``EventPipeline`` runs one structure across the event stream: contract
discovery, entry marks and delta selection, budget sizing, then the
lifecycle replay. ``run_comparison`` runs several structures plus the shares
benchmark and joins them per event, so each signal shows its outcome under
every structure side by side.

Pricing modes:
  real       — mark ladder over Alpaca option bars (Feb 2024+), BS fallback.
  synthetic  — BS-only marks (the pre-2024 mode), contracts synthesized
               from the strike grid without a data-existence check.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta

import pandas as pd
from structlog import get_logger

from deltaforge.data.chains import DiscoveredContract, discover_calls
from deltaforge.data.occ import build_occ_symbol, candidate_strikes, fridays_between
from deltaforge.data.options_client import DeltaForgeOptionsClient
from deltaforge.engine.lifecycle import replay_trade
from deltaforge.engine.trade import OptionTrade
from deltaforge.pricing.black_scholes import bs_greeks, implied_vol
from deltaforge.pricing.fees import FeeSchedule
from deltaforge.pricing.fills import FillModel
from deltaforge.pricing.iv import IVModel, realized_vol, risk_free
from deltaforge.pricing.marks import MarkEngine, _t_years
from deltaforge.pricing.spreads import SpreadWidthModel
from deltaforge.signals.events import SignalEvent
from deltaforge.structures.base import EntryContext, Position, Skip, Structure
from deltaforge.structures.shares import shares_pnl

log = get_logger(__name__)

MIN_DAILY_HISTORY = 12  # daily returns needed for a usable RV estimate


@dataclass(slots=True)
class EventResult:
    event: SignalEvent
    trade: OptionTrade | None
    skip: Skip | None


class EventPipeline:
    def __init__(
        self,
        structure: Structure,
        pricing: str = "real",
        fills: FillModel | None = None,
        fees: FeeSchedule | None = None,
        iv_model: IVModel | None = None,
        max_debit: float = 150.0,
        dte_envelope: tuple[int, int] = (14, 28),
        strike_band: tuple[float, float] = (0.85, 1.12),
        dte_exit_days: int = 5,
        next_bar_exit: bool = False,
        options_client: DeltaForgeOptionsClient | None = None,
    ) -> None:
        if pricing not in ("real", "synthetic"):
            raise ValueError(f"pricing must be real|synthetic, got {pricing!r}")
        self.structure = structure
        self.pricing = pricing
        self.fills = fills or FillModel(spread_model=SpreadWidthModel())
        self.fees = fees or FeeSchedule()
        self.iv_model = iv_model or IVModel()
        self.max_debit = max_debit
        self.dte_envelope = dte_envelope
        self.strike_band = strike_band
        self.dte_exit_days = dte_exit_days
        self.next_bar_exit = next_bar_exit
        self._client = (
            options_client or (DeltaForgeOptionsClient() if pricing == "real" else None)
        )
        self._marks = MarkEngine(
            self._client, self.iv_model, synthetic_only=(pricing == "synthetic")
        )

    # -- per-event ----------------------------------------------------------

    def run_event(self, event: SignalEvent, bars_30m: pd.DataFrame) -> EventResult:
        spot = event.entry_price
        signal_day = event.signal_ts.date()

        history = bars_30m.loc[bars_30m.index <= event.signal_ts]
        daily_closes = history["close"].resample("1D").last().dropna()
        if len(daily_closes) < MIN_DAILY_HISTORY + 1:
            return EventResult(event, None, Skip("insufficient_history"))
        rv = realized_vol(daily_closes, window=min(20, len(daily_closes) - 1))

        contracts = self._discover(event.symbol, spot, signal_day, event.target)
        if not contracts:
            return EventResult(event, None, Skip("no_contracts"))

        def spot_at(ts: datetime) -> float:
            prior = bars_30m.loc[bars_30m.index <= ts]
            if prior.empty:
                raise KeyError(ts)
            return float(prior["close"].iloc[-1])

        def entry_mark(occ: str):
            return self._marks.mark(
                occ, event.signal_ts, spot, rv, life_start=signal_day, spot_at=spot_at
            )

        def entry_delta(c: DiscoveredContract) -> float | None:
            # Candidate ranking only — priced from the signal-day daily close
            # already fetched by discovery, so scanning a chain costs zero
            # extra requests. The chosen legs get the full mark ladder.
            t = _t_years(event.signal_ts, c.expiry)
            r = risk_free(event.signal_ts.year)
            iv = None
            if not c.daily_bars.empty:
                prior = c.daily_bars.loc[c.daily_bars.index.date <= signal_day]
                if not prior.empty:
                    iv = implied_vol(float(prior["close"].iloc[-1]), spot, c.strike, t, r, "C")
            if iv is None:
                iv = self.iv_model.predict(rv)
            return bs_greeks(spot, c.strike, t, r, iv, "C").delta

        ctx = EntryContext(
            event=event,
            spot=spot,
            rv=rv,
            contracts=contracts,
            mark=entry_mark,
            entry_delta=entry_delta,
            fills=self.fills,
            fees=self.fees,
            max_debit=self.max_debit,
        )
        selected = self.structure.select(ctx)
        if isinstance(selected, Skip):
            return EventResult(event, None, selected)

        trade = replay_trade(
            event,
            selected,
            bars_30m,
            self._marks,
            self.fills,
            self.fees,
            rv,
            spot_at=spot_at,
            dte_exit_days=self.dte_exit_days,
            next_bar_exit=self.next_bar_exit,
        )
        trade.entry_mark_sources = tuple(entry_mark(leg.occ).source for leg in selected.legs)
        if trade.is_open:
            return EventResult(event, None, Skip("no_bars_after_entry"))
        return EventResult(event, trade, None)

    def run(
        self, events: list[SignalEvent], bars_by_symbol: dict[str, pd.DataFrame]
    ) -> list[EventResult]:
        results = []
        for i, event in enumerate(events):
            bars = bars_by_symbol.get(event.symbol)
            if bars is None:
                results.append(EventResult(event, None, Skip("no_underlying_bars")))
                continue
            results.append(self.run_event(event, bars))
            if (i + 1) % 25 == 0:
                log.info(
                    "pipeline.progress",
                    structure=self.structure.name,
                    done=i + 1,
                    total=len(events),
                )
        return results

    # -- discovery ----------------------------------------------------------

    def _discover(self, symbol: str, spot: float, signal_day, target: float):
        lo = spot * self.strike_band[0]
        hi = max(spot * self.strike_band[1], target * 1.02)
        if self.pricing == "real":
            return discover_calls(
                self._client, symbol, spot, signal_day,
                self.dte_envelope[0], self.dte_envelope[1], lo, hi,
            )
        expiries = fridays_between(
            signal_day + timedelta(days=self.dte_envelope[0]),
            signal_day + timedelta(days=self.dte_envelope[1]),
        )
        empty = pd.DataFrame()
        return [
            DiscoveredContract(
                occ=build_occ_symbol(symbol, e, "C", k), expiry=e, strike=k, daily_bars=empty
            )
            for e in expiries
            for k in candidate_strikes(spot, lo, hi)
        ]


# -- three-way join ---------------------------------------------------------


def per_event_join(
    events: list[SignalEvent],
    results_by_structure: dict[str, list[EventResult]],
    shares_budget: float,
) -> list[dict[str, object]]:
    """One row per event: outcome under every structure plus the shares leg."""
    rows = []
    for i, event in enumerate(events):
        row: dict[str, object] = {
            "symbol": event.symbol,
            "signal_ts": event.signal_ts.isoformat(),
            "entry": event.entry_price,
            "target_distance_pct": round(event.target_distance_pct * 100, 2),
            "underlying_exit_reason": event.underlying_exit_reason,
        }
        sh = shares_pnl(event, shares_budget)
        row["shares"] = (
            {"pnl_dollars": round(sh["pnl_dollars"], 2),
             "pnl_pct": round(sh["pnl_pct_of_invested"], 2)}
            if sh
            else None
        )
        for name, results in results_by_structure.items():
            r = results[i]
            if r.trade is not None:
                row[name] = {
                    "pnl_dollars": round(r.trade.pnl_dollars, 2),
                    "pnl_pct_of_debit": round(r.trade.pnl_pct_of_debit, 2),
                    "debit": round(r.trade.debit_dollars, 2),
                    "exit_reason": r.trade.exit_reason,
                    "legs": [leg.occ for leg in r.trade.position.legs],
                    "mark_sources": list(
                        {*r.trade.entry_mark_sources, *r.trade.exit_mark_sources}
                    ),
                }
            else:
                row[name] = {"skip": r.skip.reason if r.skip else "unknown"}
        rows.append(row)
    return rows
