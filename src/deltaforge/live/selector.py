"""Contract selection from a live chain.

Same rule the backtest settled on — the call nearest 0.55 delta in the 7-14
DTE window — but decided on real greeks and a real two-sided market instead
of modelled ones, with two guards the backtest could not apply:

- **Plausibility**: the same time-value floor that stopped the backtest from
  believing stale marks. Live it should almost never fire; if it does, the
  quote is broken.
- **Liquidity**: a contract whose bid-ask is a large fraction of its own
  premium cannot be traded at anything near mid, and mid-ish fills are the
  assumption the whole result rests on. Rejecting these is not an
  optimisation, it is refusing to trade where the backtest's premise fails.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from deltaforge.live.broker import Broker, Quote


@dataclass(frozen=True, slots=True)
class Selection:
    quote: Quote
    contracts: int
    limit: float          # premium to ask for, per share
    max_limit: float      # the furthest we will chase it
    debit: float          # total dollars at the initial limit


@dataclass(frozen=True, slots=True)
class Rejection:
    reason: str
    detail: str = ""


DEFAULT_DELTA = 0.55
DTE_MIN, DTE_MAX = 7, 14
STRIKE_BAND = 0.12          # search +-12% of spot
MIN_TIME_VALUE_PCT = 0.003  # of spot
MAX_SPREAD_PCT = 0.25       # of mid
CONTRACT_MULTIPLIER = 100


def select_call(
    broker: Broker,
    symbol: str,
    spot: float,
    budget: float,
    today: date,
    target_delta: float = DEFAULT_DELTA,
    dte_min: int = DTE_MIN,
    dte_max: int = DTE_MAX,
    haircut_cap: float = 0.5,
) -> Selection | Rejection:
    lo, hi = today + timedelta(days=dte_min), today + timedelta(days=dte_max)
    quotes = broker.call_quotes(
        symbol, lo, hi, spot * (1 - STRIKE_BAND), spot * (1 + STRIKE_BAND)
    )
    if not quotes:
        return Rejection("no_chain", f"no two-sided calls {lo}..{hi}")

    expiry = max(q.expiry for q in quotes)
    chain = [q for q in quotes if q.expiry == expiry and q.delta is not None]
    if not chain:
        return Rejection("no_greeks", f"expiry {expiry} has no deltas")

    q = min(chain, key=lambda x: abs(x.delta - target_delta))

    intrinsic = max(spot - q.strike, 0.0)
    if q.mid - intrinsic < MIN_TIME_VALUE_PCT * spot:
        return Rejection(
            "premium_implausible",
            f"time value {q.mid - intrinsic:.3f} on spot {spot:.2f}",
        )
    if q.spread_pct > MAX_SPREAD_PCT:
        return Rejection(
            "illiquid", f"spread {q.spread:.2f} = {q.spread_pct:.0%} of mid {q.mid:.2f}"
        )

    per_contract = q.mid * CONTRACT_MULTIPLIER
    contracts = int(budget // per_contract)
    if contracts < 1:
        return Rejection(
            "over_budget", f"one contract costs ${per_contract:.0f}, budget ${budget:.0f}"
        )

    # Start at mid and allow chasing up to the haircut the backtest assumed.
    return Selection(
        quote=q,
        contracts=contracts,
        limit=q.mid,
        max_limit=q.mid + haircut_cap * (q.spread / 2),
        debit=q.mid * CONTRACT_MULTIPLIER * contracts,
    )
