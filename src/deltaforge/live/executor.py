"""The paper bot's main loop.

Mirrors the backtest's mechanics exactly, because any divergence makes the
paper phase measure something other than what was tested:

- The **underlying's** 30-minute bars drive every exit. A stop is the frozen
  8-bar pivot low being touched; a target is entry + 3R being touched; on the
  same bar the stop wins. The option is only the instrument the P&L is
  expressed in.
- Entries are evaluated at 30-minute bar closes on the ML30 fresh-cross rule,
  imported from the validated repo rather than reimplemented.
- Position size is a fixed dollar amount and the *slot count* grows with the
  account — the sizing the study settled on, because compounding the bet
  compounds the drawdown with it.

What the backtest could not model and this must: orders are limit orders
placed at mid and chased no further than the haircut the backtest assumed.
An entry that will not fill inside that band is abandoned, not chased — the
whole point is to find out how often that happens.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import pandas as pd
from alpaca.data.enums import DataFeed
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from structlog import get_logger

from deltaforge.live import events as ev
from deltaforge.live.broker import Broker
from deltaforge.live.events import EventLog
from deltaforge.live.journal import Journal, TradeRecord
from deltaforge.live.selector import Rejection, Selection, select_call
from deltaforge.ml30_bridge import (
    AlpacaClientError,
    AlpacaHistoricalClient,
    EntryLogic,
    add_indicators,
    calculate_initial_stop,
    settings_with_credentials,
)
from deltaforge.pricing.fees import DEFAULT_FEES
from deltaforge.settings import CACHE_DIR

LIVE_CACHE_DIR = CACHE_DIR / "iex_30m"

log = get_logger(__name__)

TF_30M = TimeFrame(30, TimeFrameUnit.Minute)


@dataclass(slots=True)
class BotConfig:
    position_size: float = 300.0     # dollars per position, fixed
    max_slots: int = 15              # signals cannot fill more than this
    target_delta: float = 0.55
    dte_min: int = 7
    dte_max: int = 14
    dte_exit: int = 5                # close when this many days remain
    r_target: float = 3.0
    stop_lookback: int = 8
    sma_fast: int = 21
    sma_slow: int = 55
    haircut_cap: float = 0.5         # how far past mid an entry may be chased
    reprice_after_s: int = 45
    reprice_steps: int = 3
    lookback_days: int = 90          # underlying history for indicators
    dry_run: bool = False            # scan and journal intent, submit nothing
    # A signal whose 3R target is a short walk cannot pay for the option's
    # bid-ask and theta, whatever happens to the underlying. In the backtest
    # the 860 signals under 5% returned $1,844 of $42,000 — 4% of the profit
    # for 54% of the trades — and cutting them halved the drawdown while
    # slightly raising the return. ANALYSIS.md predicted this when it ruled
    # out the 5-minute variant for the same reason.
    min_target_distance_pct: float = 5.0


class Executor:
    def __init__(
        self,
        broker: Broker,
        journal: Journal,
        eventlog: EventLog,
        universe: list[str],
        config: BotConfig | None = None,
        cache_dir=None,
        credentials: tuple[str, str] | None = None,
    ) -> None:
        self.broker = broker
        self.journal = journal
        self.events = eventlog
        self.universe = universe
        self.cfg = config or BotConfig()
        # Market data uses the credentials we were handed, never whatever the
        # ml30 repo's .env happens to hold — those are revoked on both hosts,
        # and inheriting keys silently is how a bot trades the wrong account.
        settings = settings_with_credentials(*credentials) if credentials else None
        # IEX, matching the production ml30 bot on this host. The account's
        # entitlement covers historical SIP but not its last 15 minutes
        # ("subscription does not permit querying recent SIP data"), which is
        # exactly the window a bar-close strategy needs. IEX is a thinner tape
        # than the consolidated one the backtest used, so live signals can
        # differ at the margin — the same trade-off the real-money bot already
        # runs on.
        self.bars = AlpacaHistoricalClient(
            settings=settings,
            feed=DataFeed.IEX,
            cache_dir=cache_dir or LIVE_CACHE_DIR,
        )
        self._entry = EntryLogic(
            sma_fast_period=self.cfg.sma_fast, sma_slow_period=self.cfg.sma_slow
        )

    # -- sizing -------------------------------------------------------------

    def slots(self, equity: float) -> int:
        """One slot per position_size of equity, capped where signals run out."""
        return max(1, min(self.cfg.max_slots, int(equity // self.cfg.position_size)))

    def budget(self, equity: float) -> float:
        """Cash actually available for one more position."""
        free = equity - self.journal.deployed_debit()
        return min(self.cfg.position_size, max(0.0, free))

    # -- data ---------------------------------------------------------------

    def fetch(self, symbol: str) -> pd.DataFrame | None:
        end = datetime.now(UTC)
        start = end - timedelta(days=self.cfg.lookback_days)
        try:
            b = self.bars.fetch_bars(symbol, start, end, timeframe=TF_30M, use_cache=False)
        except AlpacaClientError as exc:
            log.warning("bot.fetch_failed", symbol=symbol, error=str(exc)[:150])
            return None
        if len(b) <= self.cfg.sma_slow:
            return None
        return add_indicators(b, fast=self.cfg.sma_fast, slow=self.cfg.sma_slow)

    # -- the pass -----------------------------------------------------------

    def run_once(self) -> None:
        """One full pass: manage what is open, then look for what to open."""
        # A dry run scans regardless of the clock: it submits nothing, and
        # validating the signal path before the open is the whole reason it
        # exists. Quotes will be stale, so selection may legitimately refuse.
        if not self.broker.is_open() and not self.cfg.dry_run:
            self.events.beat(ok=True, note="market closed")
            return

        equity = self.broker.equity()
        bars_by_symbol: dict[str, pd.DataFrame] = {}

        held = self.journal.open_symbols()
        for symbol in set(self.universe) | held:
            b = self.fetch(symbol)
            if b is not None:
                bars_by_symbol[symbol] = b

        self.events.emit(
            ev.SCAN, symbols=len(bars_by_symbol), equity=round(equity, 2),
            open_positions=len(self.journal.open_trades()), slots=self.slots(equity),
        )

        self._manage_open(bars_by_symbol)
        self._look_for_entries(bars_by_symbol, equity)

        self.events.beat(
            ok=True, last_scan=datetime.now(UTC).isoformat(timespec="seconds")
        )

    # -- exits --------------------------------------------------------------

    def _manage_open(self, bars_by_symbol: dict[str, pd.DataFrame]) -> None:
        for row in self.journal.open_trades():
            if row["status"] == "pending":
                self._resolve_pending(row)
                continue

            bars = bars_by_symbol.get(row["symbol"])
            if bars is None or bars.empty:
                continue
            entry_ts = datetime.fromisoformat(row["signal_ts"])
            since = bars.loc[bars.index > entry_ts]
            if since.empty:
                continue

            reason = None
            last = since.iloc[-1]
            # Same-bar precedence as the backtest: the stop wins.
            if float(since["low"].min()) <= row["stop_price"]:
                reason = "stop"
            elif float(since["high"].max()) >= row["target_price"]:
                reason = "target"
            elif (date.fromisoformat(row["expiry"]) - datetime.now(UTC).date()).days <= self.cfg.dte_exit:
                reason = "dte"

            if reason:
                self.events.emit(
                    ev.EXIT_SIGNAL, symbol=row["symbol"], occ=row["occ"], reason=reason,
                    stop=row["stop_price"], target=row["target_price"],
                    underlying=round(float(last["close"]), 2),
                )
                self._close(row, reason, float(last["close"]))

    def _close(self, row, reason: str, underlying: float) -> None:
        q = self.broker.quote(row["occ"])
        if q is None:
            self.events.emit(ev.ERROR, occ=row["occ"], detail="no quote to close against")
            return
        limit = q.mid - self.cfg.haircut_cap * (q.spread / 2)
        self.journal.set_exit_limit(row["id"], limit)
        if self.cfg.dry_run:
            log.info(
                "bot.dry_run.would_sell", occ=row["occ"], qty=int(row["contracts"]),
                limit=round(limit, 2), reason=reason,
            )
            return
        order_id = self.broker.sell_to_close(row["occ"], int(row["contracts"]), limit)
        self.events.emit(
            ev.ORDER_CLOSE, symbol=row["symbol"], occ=row["occ"], qty=int(row["contracts"]),
            limit=round(limit, 2), bid=q.bid, ask=q.ask, reason=reason,
        )

        filled = self._await_fill(order_id, limit, q.bid, side="sell")
        if filled is None:
            self.events.emit(ev.ORDER_CANCELLED, occ=row["occ"], leg="exit")
            return

        price, order_id, filled_at = filled
        fees = DEFAULT_FEES.round_trip(n_legs=1, n_contracts=int(row["contracts"]))
        self.journal.add_fill(
            row["id"], order_id, "sell", int(row["contracts"]), price, filled_at, "exit"
        )
        self.journal.mark_closed(
            row["id"], price, order_id, reason, fees, underlying, filled_at
        )
        pnl = (price - float(row["entry_fill"])) * 100 * int(row["contracts"]) - fees
        self.events.emit(
            ev.POSITION_CLOSED, symbol=row["symbol"], occ=row["occ"], reason=reason,
            entry=row["entry_fill"], exit=price, pnl=round(pnl, 2),
        )

    # -- entries ------------------------------------------------------------

    def _holds_foreign_equity(self) -> bool:
        """True while the account still carries stock this bot did not open.

        The account was handed over from another strategy whose positions
        liquidate at the next open. Until they clear, `equity` counts money
        that is not actually available, so sizing would open positions the
        buying power cannot cover. Managing our own trades stays safe; opening
        new ones does not.
        """
        try:
            positions = self.broker.trading.get_all_positions()
        except Exception as exc:  # noqa: BLE001 — a failed check must not open trades
            log.warning("bot.position_check_failed", error=str(exc)[:150])
            return True
        return any("option" not in str(getattr(p, "asset_class", "")).lower() for p in positions)

    def _look_for_entries(self, bars_by_symbol: dict[str, pd.DataFrame], equity: float) -> None:
        if self._holds_foreign_equity():
            self.events.emit(
                ev.SKIP, symbol="*", reason="foreign_positions",
                detail="account still holds stock from the previous strategy",
            )
            return

        open_rows = self.journal.open_trades()
        held = {r["symbol"] for r in open_rows}
        free_slots = self.slots(equity) - len(open_rows)
        if free_slots <= 0:
            return

        for symbol, bars in bars_by_symbol.items():
            if free_slots <= 0:
                return
            if symbol in held:
                continue
            if not self._entry.check_entry(bars, len(bars) - 1):
                continue

            i = len(bars) - 1
            entry_price = float(bars["close"].iloc[i])
            try:
                stop = calculate_initial_stop(bars, i, self.cfg.stop_lookback)
            except ValueError as exc:  # not enough history for the pivot window
                self.events.emit(ev.SKIP, symbol=symbol, reason="no_stop", detail=str(exc)[:120])
                continue
            if stop >= entry_price:
                self.events.emit(ev.SKIP, symbol=symbol, reason="stop_above_entry")
                continue
            risk = entry_price - stop
            target = entry_price + self.cfg.r_target * risk
            signal_ts = bars.index[i].to_pydatetime()

            target_pct = 100 * (target - entry_price) / entry_price
            self.events.emit(
                ev.SIGNAL, symbol=symbol, entry=round(entry_price, 2),
                stop=round(stop, 2), target=round(target, 2),
                target_pct=round(target_pct, 2),
            )
            if target_pct < self.cfg.min_target_distance_pct:
                self.events.emit(
                    ev.SKIP, symbol=symbol, reason="target_too_close",
                    detail=f"{target_pct:.2f}% < {self.cfg.min_target_distance_pct:.1f}%",
                )
                continue

            budget = self.budget(equity)
            picked = select_call(
                self.broker, symbol, entry_price, budget, datetime.now(UTC).date(),
                target_delta=self.cfg.target_delta, dte_min=self.cfg.dte_min,
                dte_max=self.cfg.dte_max, haircut_cap=self.cfg.haircut_cap,
            )
            if isinstance(picked, Rejection):
                self.events.emit(
                    ev.SKIP, symbol=symbol, reason=picked.reason, detail=picked.detail
                )
                continue

            if self._open(symbol, signal_ts, entry_price, stop, target, risk, picked):
                free_slots -= 1
                held.add(symbol)

    def _open(
        self, symbol: str, signal_ts: datetime, entry_price: float, stop: float,
        target: float, risk: float, sel: Selection,
    ) -> bool:
        q = sel.quote
        if self.cfg.dry_run:
            self.events.emit(
                ev.ORDER_OPEN, symbol=symbol, occ=q.occ, qty=sel.contracts,
                limit=round(sel.limit, 2), bid=q.bid, ask=q.ask,
                delta=round(q.delta, 3) if q.delta else None,
                debit=round(sel.debit, 2), dry_run=True,
            )
            log.info(
                "bot.dry_run.would_buy", symbol=symbol, occ=q.occ, qty=sel.contracts,
                limit=round(sel.limit, 2), debit=round(sel.debit, 2),
            )
            return True  # occupies a slot for this pass, so the scan stays realistic

        trade_id = self.journal.open_pending(
            TradeRecord(
                symbol=symbol, occ=q.occ, strike=q.strike, expiry=q.expiry.isoformat(),
                dte_at_entry=(q.expiry - datetime.now(UTC).date()).days,
                delta_at_entry=q.delta, signal_ts=signal_ts.isoformat(),
                entry_price=entry_price, stop_price=stop, target_price=target,
                risk_per_share=risk, contracts=sel.contracts, limit_price=sel.limit,
            )
        )
        order_id = self.broker.buy_to_open(q.occ, sel.contracts, sel.limit)
        self.events.emit(
            ev.ORDER_OPEN, symbol=symbol, occ=q.occ, qty=sel.contracts,
            limit=round(sel.limit, 2), bid=q.bid, ask=q.ask,
            delta=round(q.delta, 3) if q.delta else None, debit=round(sel.debit, 2),
        )

        filled = self._await_fill(order_id, sel.limit, sel.max_limit, side="buy")
        if filled is None:
            self.journal.abort(trade_id, "unfilled")
            self.events.emit(ev.ORDER_CANCELLED, symbol=symbol, occ=q.occ, leg="entry")
            return False

        price, order_id, filled_at = filled
        fees = DEFAULT_FEES.one_way(n_legs=1, n_contracts=sel.contracts)
        self.journal.add_fill(trade_id, order_id, "buy", sel.contracts, price, filled_at, "entry")
        self.journal.mark_filled(trade_id, price, order_id, fees, filled_at)
        self.events.emit(
            ev.ORDER_FILLED, symbol=symbol, occ=q.occ, asked=round(sel.limit, 2),
            got=round(price, 2), qty=sel.contracts,
        )
        return True

    # -- order management ---------------------------------------------------

    def _await_fill(
        self, order_id: str, start_limit: float, bound: float, side: str
    ) -> tuple[float, str, str] | None:
        """Wait, repricing toward `bound`; give up rather than cross past it."""
        limit = start_limit
        for step in range(self.cfg.reprice_steps + 1):
            time.sleep(self.cfg.reprice_after_s)
            order = self.broker.get_order(order_id)
            if self.broker.is_filled(order):
                return (
                    self.broker.fill_price(order),
                    order_id,
                    self.broker.filled_at(order),
                )
            if step == self.cfg.reprice_steps:
                break
            span = bound - start_limit
            limit = start_limit + span * (step + 1) / self.cfg.reprice_steps
            self.broker.cancel(order_id)
            self.events.emit(ev.ORDER_REPRICE, side=side, to=round(limit, 2), step=step + 1)
            occ = order.symbol
            qty = int(order.qty)
            order_id = (
                self.broker.buy_to_open(occ, qty, limit)
                if side == "buy"
                else self.broker.sell_to_close(occ, qty, limit)
            )
        self.broker.cancel(order_id)
        return None

    def _resolve_pending(self, row) -> None:
        """A pending row means the process died mid-order; reconcile against the broker."""
        positions = self.broker.option_positions()
        if row["occ"] in positions:
            p = positions[row["occ"]]
            self.journal.mark_filled(
                row["id"], float(p.avg_entry_price), "recovered",
                DEFAULT_FEES.one_way(1, int(row["contracts"])),
                datetime.now(UTC).isoformat(timespec="seconds"),
            )
            self.events.emit(ev.ORDER_FILLED, occ=row["occ"], note="recovered on restart")
        else:
            self.journal.abort(row["id"], "unresolved_on_restart")
