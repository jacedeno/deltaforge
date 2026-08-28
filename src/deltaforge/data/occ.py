"""OCC option symbology — build, parse, and candidate-strike grids.

Pure functions, no I/O. The OCC symbol format (as used by Alpaca) is:

    {UNDERLYING}{YYMMDD}{C|P}{strike * 1000, zero-padded to 8 digits}

e.g. ``INTC260918C00025000`` = INTC 2026-09-18 call, strike $25.00.

``candidate_strikes`` exists for the expired-contract fallback: Alpaca's
trading-API contract listing has a limited lookback for expired contracts,
so historical replay synthesizes plausible OCC symbols (Fridays in the DTE
window x a strike grid around spot) and confirms existence by whether
``get_option_bars`` returns data.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

_OCC_RE = re.compile(r"^([A-Z]{1,6})(\d{6})([CP])(\d{8})$")


def build_occ_symbol(underlying: str, expiry: date, call_put: str, strike: float) -> str:
    cp = call_put.upper()
    if cp not in ("C", "P"):
        raise ValueError(f"call_put must be 'C' or 'P', got {call_put!r}")
    strike_int = round(strike * 1000)
    if not (0 < strike_int < 10**8):
        raise ValueError(f"strike out of range: {strike}")
    return f"{underlying.upper()}{expiry.strftime('%y%m%d')}{cp}{strike_int:08d}"


def parse_occ_symbol(symbol: str) -> tuple[str, date, str, float]:
    """Return (underlying, expiry, 'C'|'P', strike)."""
    m = _OCC_RE.match(symbol)
    if m is None:
        raise ValueError(f"not an OCC symbol: {symbol!r}")
    underlying, yymmdd, cp, strike_raw = m.groups()
    expiry = date(2000 + int(yymmdd[:2]), int(yymmdd[2:4]), int(yymmdd[4:6]))
    return underlying, expiry, cp, int(strike_raw) / 1000


def strike_spacing(spot: float) -> float:
    """Typical minimum listed strike spacing for a US equity at this price.

    Deliberately the *finest* plausible grid — candidates that don't exist
    cost one bars request each and are discarded, while a too-coarse grid
    silently misses the strike nearest the 3R target.
    """
    if spot < 25:
        return 0.5
    if spot < 100:
        return 1.0
    if spot < 200:
        return 2.5
    return 5.0


def candidate_strikes(spot: float, lo: float, hi: float) -> list[float]:
    """All grid strikes in the [lo, hi] price band for this underlying."""
    if lo > hi:
        raise ValueError(f"lo {lo} > hi {hi}")
    step = strike_spacing(spot)
    first = int(lo / step) * step
    strikes = []
    k = first
    while k <= hi + 1e-9:
        if k >= lo - 1e-9 and k > 0:
            strikes.append(round(k, 2))
        k += step
    return strikes


def fridays_between(start: date, end: date) -> list[date]:
    """Candidate expiries: every Friday in [start, end] (weeklies + monthlies)."""
    d = start + timedelta(days=(4 - start.weekday()) % 7)
    out = []
    while d <= end:
        out.append(d)
        d += timedelta(days=7)
    return out
