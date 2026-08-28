"""Historical contract discovery per signal event.

The trading-API contract listing returns nothing for long-expired contracts
(the M2 spike measured 0/3 probes), so discovery synthesizes OCC candidates
— every Friday in the DTE window x the strike grid around spot — and keeps
the ones whose daily bars exist. The daily-bars probe doubles as the cache
warm-up: every kept contract already has its daily frame on disk afterward.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from datetime import UTC

import pandas as pd

from deltaforge.data.occ import build_occ_symbol, candidate_strikes, fridays_between
from deltaforge.data.options_client import DeltaForgeOptionsClient


@dataclass(frozen=True, slots=True)
class DiscoveredContract:
    occ: str
    expiry: date
    strike: float
    daily_bars: pd.DataFrame  # contract's daily bars from signal day to expiry


def discover_calls(
    client: DeltaForgeOptionsClient,
    underlying: str,
    spot: float,
    signal_day: date,
    dte_min: int,
    dte_max: int,
    strike_lo: float,
    strike_hi: float,
) -> list[DiscoveredContract]:
    """Call contracts with real daily bars for the event's DTE/strike box."""
    expiries = fridays_between(
        signal_day + timedelta(days=dte_min), signal_day + timedelta(days=dte_max)
    )
    strikes = candidate_strikes(spot, strike_lo, strike_hi)
    if not expiries or not strikes:
        return []

    found: list[DiscoveredContract] = []
    for expiry in expiries:
        candidates = {build_occ_symbol(underlying, expiry, "C", k): k for k in strikes}
        bars_by_occ = client.fetch_bars_multi(
            list(candidates),
            start=datetime.combine(signal_day, time.min, UTC),
            end=datetime.combine(expiry, time.max, UTC),
            tf_label="1d",
        )
        for occ, bars in bars_by_occ.items():
            if not bars.empty:
                found.append(
                    DiscoveredContract(
                        occ=occ, expiry=expiry, strike=candidates[occ], daily_bars=bars
                    )
                )
    found.sort(key=lambda c: (c.expiry, c.strike))
    return found
