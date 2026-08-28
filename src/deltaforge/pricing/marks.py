"""Mark ladder — the best available price for a contract at a timestamp.

The spike measured minute-bar coverage of 4-28% on these chains, so a
single-source mark is impossible; every mark records which rung priced it
and runs report the source mix (a "real-data" result dominated by
``bs_model`` marks must be visible as such).

Ladder, first hit wins:
  1. ``minute``      — a 1-minute bar within ``tolerance`` of the timestamp.
  2. ``daily``       — end-of-day contexts only (5-DTE close): that day's
                       daily bar close.
  3. ``bs_anchored`` — Black-Scholes at the current spot, with the IV backed
                       out from the most recent real bar (same day, or the
                       prior daily close). Re-uses the market's own vol,
                       just moves the underlying.
  4. ``bs_model``    — Black-Scholes with the RV-calibrated IVModel. The
                       fully synthetic rung; also the only rung available
                       pre-Feb-2024.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Callable

import pandas as pd

from deltaforge.data.occ import parse_occ_symbol
from deltaforge.data.options_client import DeltaForgeOptionsClient
from deltaforge.pricing.black_scholes import bs_price, implied_vol
from deltaforge.pricing.iv import IVModel, risk_free

_EXPIRY_CLOSE_UTC = time(20, 0)  # 16:00 ET standard close (ignores DST hour)


@dataclass(frozen=True, slots=True)
class Mark:
    price: float
    source: str  # minute | daily | bs_anchored | bs_model
    iv: float | None = None


def _t_years(ts: datetime, expiry: date) -> float:
    expiry_dt = datetime.combine(expiry, _EXPIRY_CLOSE_UTC, UTC)
    return max((expiry_dt - ts).total_seconds() / (365.0 * 86400.0), 0.0)


class MarkEngine:
    def __init__(
        self,
        client: DeltaForgeOptionsClient | None,
        iv_model: IVModel,
        tolerance: timedelta = timedelta(minutes=15),
        synthetic_only: bool = False,
    ) -> None:
        """``synthetic_only=True`` skips rungs 1-3 — the pre-2024 mode."""
        self._client = client
        self._iv_model = iv_model
        self._tolerance = tolerance
        self._synthetic_only = synthetic_only
        self._minute_cache: dict[str, pd.DataFrame] = {}
        self._daily_cache: dict[str, pd.DataFrame] = {}

    # -- bar access (one fetch per contract life, then in-memory) -----------

    def _bars(self, occ: str, tf_label: str, life_start: date) -> pd.DataFrame:
        cache = self._minute_cache if tf_label == "1m" else self._daily_cache
        if occ not in cache:
            expiry = parse_occ_symbol(occ)[1]
            assert self._client is not None
            cache[occ] = self._client.fetch_bars(
                occ,
                datetime.combine(life_start, time.min, UTC),
                datetime.combine(expiry, time.max, UTC),
                tf_label=tf_label,
            )
        return cache[occ]

    # -- the ladder ---------------------------------------------------------

    def mark(
        self,
        occ: str,
        ts: datetime,
        spot: float,
        rv: float,
        life_start: date,
        spot_at: Callable[[datetime], float] | None = None,
        eod: bool = False,
    ) -> Mark:
        _, expiry, cp, strike = parse_occ_symbol(occ)
        t = _t_years(ts, expiry)
        r = risk_free(ts.year)

        if not self._synthetic_only:
            minute = self._bars(occ, "1m", life_start)
            if not minute.empty:
                window = minute.loc[
                    (minute.index >= ts - self._tolerance) & (minute.index <= ts + self._tolerance)
                ]
                if not window.empty:
                    nearest = window.iloc[
                        (window.index - ts).to_series().abs().argmin()
                    ]
                    return Mark(price=float(nearest["close"]), source="minute")

            daily = self._bars(occ, "1d", life_start)
            if eod and not daily.empty:
                day_rows = daily.loc[daily.index.date == ts.date()]
                if not day_rows.empty:
                    return Mark(price=float(day_rows["close"].iloc[-1]), source="daily")

            anchored = self._anchored_iv(minute, daily, ts, expiry, cp, strike, spot_at)
            if anchored is not None:
                return Mark(
                    price=bs_price(spot, strike, t, r, anchored, cp),
                    source="bs_anchored",
                    iv=anchored,
                )

        iv = self._iv_model.predict(rv)
        return Mark(price=bs_price(spot, strike, t, r, iv, cp), source="bs_model", iv=iv)

    def _anchored_iv(
        self,
        minute: pd.DataFrame,
        daily: pd.DataFrame,
        ts: datetime,
        expiry: date,
        cp: str,
        strike: float,
        spot_at: Callable[[datetime], float] | None,
    ) -> float | None:
        """IV backed out from the most recent real print (<= 3 days old)."""
        if spot_at is None:
            return None
        for frame in (minute, daily):
            if frame.empty:
                continue
            prior = frame.loc[
                (frame.index < ts) & (frame.index >= ts - timedelta(days=3))
            ]
            if prior.empty:
                continue
            anchor_ts = prior.index[-1].to_pydatetime()
            anchor_px = float(prior["close"].iloc[-1])
            try:
                anchor_spot = spot_at(anchor_ts)
            except (KeyError, IndexError, ValueError):
                continue
            iv = implied_vol(
                anchor_px,
                anchor_spot,
                strike,
                _t_years(anchor_ts, expiry),
                risk_free(anchor_ts.year),
                cp,
            )
            if iv is not None:
                return iv
        return None
