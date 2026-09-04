# Vendored from ml30-sp500-strategy @ c7ad990 (2026-09-02) — see deltaforge/ml30/__init__.py.
# Only the import paths and PROJECT_ROOT were changed.
"""Position sizing and initial-stop calculation.

Sizing is **equity-weighted** with fractional shares: every trade deploys
exactly `max_position_pct` of current account equity, regardless of the
stop distance. With max_position_pct=0.05 and equity=$60k, every trade
holds ~$3,000 of stock. The initial stop and take-profit are then
calculated normally (lookback pivot for stop, R-multiple for target),
which means the *dollar risk* per trade varies by stock — tight stops
risk less, wide stops risk more — but the deployed capital is constant.

The risk_pct parameter exists only for backward compatibility and is no
longer used by the sizing math; ``actual_risk = shares * (entry - stop)``
is reported per-trade by the engine. A future cleanup pass may remove it.

The initial stop is the lowest low of the prior `lookback` bars (highest
high, for a short) and is FROZEN once the trade opens (per TSD §6.3).

**Whole shares.** Fractional shares are the default and the live long bots
depend on them, but shorts cannot be fractional at any broker we use — so
`whole_shares=True` floors the count. Flooring can legitimately produce
**zero**: a $150 slot cannot hold one share of a $210 stock. That is not an
error, it is the affordability filter, and it must be applied at signal
time against the historical price. Pre-filtering a universe to today's
cheap names instead would be look-ahead — those are the names that fell to
that price, which is exactly the thing a short study must not assume.
Callers must therefore treat a 0.0 return as "skip this entry".

Reference: TSD-MomentumLong-v1.3 §6 (sizing and risk management).
"""

from __future__ import annotations

import math

import pandas as pd

from deltaforge.ml30.direction import Direction

DEFAULT_RISK_PCT: float = 0.01
DEFAULT_MAX_POSITION_PCT: float = 0.05
DEFAULT_STOP_LOOKBACK: int = 10


def calculate_shares(
    equity: float,
    entry: float,
    stop: float,
    risk_pct: float = DEFAULT_RISK_PCT,
    max_position_pct: float = DEFAULT_MAX_POSITION_PCT,
    fixed_position_dollars: float | None = None,
    direction: Direction = Direction.LONG,
    whole_shares: bool = False,
) -> float:
    """Return fractional share count for the configured sizing model.

    Two sizing modes:

    1. **Equity-weighted (default)** — position value is ``equity * max_position_pct``::

           shares = (equity * max_position_pct) / entry

    2. **Fixed-dollar** — when ``fixed_position_dollars`` is provided, every
       position deploys exactly that dollar amount regardless of equity::

           shares = fixed_position_dollars / entry

       This is useful for individual-stock backtests where equity drift
       between trades would otherwise distort the comparison.

    Stop is validated for the direction (strictly below entry for a long,
    strictly above for a short) but does NOT affect the share count.
    ``risk_pct`` is kept in the signature for backward compatibility but is
    unused.

    Alpaca natively supports fractional shares, so the result is not floored
    unless ``whole_shares=True`` — mandatory for shorts, which no broker we
    use will fill fractionally.

    Returns:
        Share count. **0.0 when `whole_shares=True` and the budget cannot
        cover a single share** — callers must treat that as "skip", not as
        an error (see module docstring).

    Raises:
        ValueError: if any input is non-positive, max_position_pct is out
            of (0, 1], or the stop is on the wrong side of entry.
    """
    if equity <= 0:
        raise ValueError(f"equity must be > 0, got {equity}")
    if entry <= 0:
        raise ValueError(f"entry must be > 0, got {entry}")
    if direction.is_long and entry <= stop:
        raise ValueError(f"entry ({entry}) must be greater than stop ({stop}) for a long")
    if direction.is_short and entry >= stop:
        raise ValueError(f"entry ({entry}) must be less than stop ({stop}) for a short")
    if not (0.0 < max_position_pct <= 1.0):
        raise ValueError(f"max_position_pct must be in (0, 1], got {max_position_pct}")
    if not (0.0 < risk_pct <= 1.0):
        raise ValueError(f"risk_pct must be in (0, 1], got {risk_pct}")
    if fixed_position_dollars is not None:
        if fixed_position_dollars <= 0:
            raise ValueError(f"fixed_position_dollars must be > 0, got {fixed_position_dollars}")
        raw = fixed_position_dollars / entry
    else:
        raw = (equity * max_position_pct) / entry
    return float(math.floor(raw)) if whole_shares else raw


def calculate_initial_stop(
    bars: pd.DataFrame,
    entry_idx: int,
    lookback: int = DEFAULT_STOP_LOOKBACK,
    direction: Direction = Direction.LONG,
) -> float:
    """Frozen pivot stop from the `lookback` bars immediately preceding `entry_idx`.

    LONG  -> lowest low of the window (stop sits below entry).
    SHORT -> highest high of the window (stop sits above entry).

    The window is `bars.iloc[entry_idx - lookback : entry_idx]` — that is, the
    `lookback` bars before the entry bar, exclusive of the entry bar itself.

    Raises:
        ValueError: if there are not enough bars before `entry_idx`, or the
            column the direction needs (`low` / `high`) is absent.
    """
    if lookback < 1:
        raise ValueError(f"lookback must be >= 1, got {lookback}")
    if entry_idx < lookback:
        raise ValueError(
            f"need {lookback} bars before entry_idx={entry_idx}, only {entry_idx} available"
        )
    column = "low" if direction.is_long else "high"
    if column not in bars.columns:
        raise ValueError(f"bars DataFrame must contain a '{column}' column")
    window = bars[column].iloc[entry_idx - lookback : entry_idx]
    return float(window.min() if direction.is_long else window.max())


class PositionSizer:
    """Stateful wrapper around `calculate_shares` carrying configured risk + cap."""

    def __init__(
        self,
        risk_pct: float = DEFAULT_RISK_PCT,
        max_position_pct: float = DEFAULT_MAX_POSITION_PCT,
        fixed_position_dollars: float | None = None,
        direction: Direction = Direction.LONG,
        whole_shares: bool = False,
    ) -> None:
        if not (0.0 < risk_pct <= 1.0):
            raise ValueError(f"risk_pct must be in (0, 1], got {risk_pct}")
        if not (0.0 < max_position_pct <= 1.0):
            raise ValueError(f"max_position_pct must be in (0, 1], got {max_position_pct}")
        if fixed_position_dollars is not None and fixed_position_dollars <= 0:
            raise ValueError(f"fixed_position_dollars must be > 0, got {fixed_position_dollars}")
        self.risk_pct = risk_pct
        self.max_position_pct = max_position_pct
        self.fixed_position_dollars = fixed_position_dollars
        self.direction = direction
        self.whole_shares = whole_shares

    def calculate_shares(self, equity: float, entry: float, stop: float) -> float:
        """Share count for one entry; 0.0 means unaffordable (see module docs)."""
        return calculate_shares(
            equity,
            entry,
            stop,
            self.risk_pct,
            self.max_position_pct,
            self.fixed_position_dollars,
            self.direction,
            self.whole_shares,
        )

    def dollar_risk(self, equity: float) -> float:
        """Risk budget for a single trade given current equity (uncapped)."""
        return equity * self.risk_pct

    def max_position_value(self, equity: float) -> float:
        """Hard cap on a single position's notional value at given equity."""
        return equity * self.max_position_pct
