# Vendored from ml30-sp500-strategy @ c7ad990 (2026-09-02) — see deltaforge/ml30/__init__.py.
# Only the import paths and PROJECT_ROOT were changed.
"""Triple-confirmation entry logic.

A long entry fires only when, on a single candle close, all four conditions
are simultaneously true (canonical / FC+ mode):

    c1: close > SMA_slow            (above primary moving average)
    c2: prev_close <= SMA_slow      (FC+ — fresh-cross filter)
    c3: close > SMA_fast            (short-term momentum confirmation)
    c4: close > open                (bullish candle)

A **short** entry (``direction=Direction.SHORT``) is the exact mirror — the
same four confirmations with every comparison flipped:

    c1: close < SMA_slow            (below primary moving average)
    c2: prev_close >= SMA_slow      (FC+ — fresh cross DOWN)
    c3: close < SMA_fast            (short-term downside confirmation)
    c4: close < open                (bearish candle)

The c2 condition is the **Fresh-Cross filter (FC)**:

    FC+ (require_crossup=True, default)  → only fires on the bar where price
                                           crosses above SMA_slow from below.
                                           Rejects continuation entries where
                                           the cross already happened on an
                                           earlier bar.
    FC- (require_crossup=False)          → drops c2; allows entries on any
                                           bullish bar above both SMAs.
                                           Catches continuation moves but is
                                           more exposed to chop after stops.

Optional entry filters (BB+RSI sweep — never applied by default):

    rsi_threshold  — skip entry when RSI(14) >= threshold at the trigger bar.
                     Prevents entering after an overextended move. NaN RSI
                     (warm-up) is treated as a block (conservative).
    bb_filter      — skip entry when close >= BB_upper(20,2σ) at the trigger
                     bar. Prevents chasing price at the top of the band.
                     NaN BB (warm-up) is treated as a block.

Both filters are **long-only**: "don't chase an overextended move up" has
no automatic short reading, and guessing a mirror would be worse than
refusing one. Requesting either with ``direction=SHORT`` raises.

The deployed variants (CanonicalV2 15min, V1-5m 5min) run **FC+** with
rsi_threshold=None and bb_filter=False (filters disabled).
FC- is the variant that the pending sweep `future_sweep_no_crossup.md`
exists to evaluate — never change the default without an explicit Jose
decision based on that sweep.

Reference: TSD-MomentumLong-v2.1 §5.2 (entry trigger).
"""

from __future__ import annotations

import pandas as pd

from deltaforge.ml30.direction import Direction


def check_entry(
    *,
    curr_open: float,
    curr_close: float,
    curr_sma21: float,
    curr_sma65: float,
    prev_close: float,
    prev_sma65: float,
    require_crossup: bool = True,
    curr_rsi: float | None = None,
    rsi_threshold: float | None = None,
    curr_bb_upper: float | None = None,
    bb_filter: bool = False,
    direction: Direction = Direction.LONG,
) -> bool:
    """Pure scalar evaluation of the entry conditions.

    `require_crossup` toggles the Fresh-Cross filter (c2):
      - True  (FC+): require ``prev_close <= prev_sma_slow`` (canonical)
      - False (FC-): drop c2; allow trend-continuation entries

    `direction` mirrors every comparison: LONG needs a bullish bar closing
    above both SMAs having crossed up; SHORT needs a bearish bar closing
    below both SMAs having crossed down.

    `rsi_threshold` (optional, LONG only): block entry when RSI >= threshold.
    `bb_filter` (optional, LONG only): block entry when close >= BB upper band.
    NaN in either blocks the entry (conservative).

    Any NaN in the base SMA inputs returns False. When `require_crossup=False`,
    `prev_close` and `prev_sma65` are still required for NaN-validity but are
    not compared against each other.

    Raises:
        ValueError: if an entry filter is requested with `direction=SHORT`.
    """
    if direction.is_short and (rsi_threshold is not None or bb_filter):
        raise ValueError("rsi_threshold and bb_filter are long-only; no short mirror is defined")
    values = (curr_open, curr_close, curr_sma21, curr_sma65, prev_close, prev_sma65)
    if any(pd.isna(v) for v in values):
        return False
    if direction.is_long:
        base = curr_close > curr_sma65 and curr_close > curr_sma21 and curr_close > curr_open
        fresh_cross = prev_close <= prev_sma65
    else:
        base = curr_close < curr_sma65 and curr_close < curr_sma21 and curr_close < curr_open
        fresh_cross = prev_close >= prev_sma65
    if not base:
        return False
    if require_crossup and not fresh_cross:
        return False
    if rsi_threshold is not None and (
        curr_rsi is None or pd.isna(curr_rsi) or curr_rsi >= rsi_threshold
    ):
        return False
    return not (
        bb_filter
        and (curr_bb_upper is None or pd.isna(curr_bb_upper) or curr_close >= curr_bb_upper)
    )


class EntryLogic:
    """Stateless wrapper that evaluates the entry trigger against a DataFrame.

    The DataFrame is expected to carry the columns produced by
    `strategy.indicators.add_indicators`: at minimum `open`, `close`, and the
    SMA columns named by the configured periods.

    When rsi_threshold or bb_filter are set the DataFrame must also carry
    `rsi{rsi_period}` and/or `bb_upper{bb_period}` columns — produced by
    `add_indicators(..., rsi_period=14, bb_period=20)`.

    Parameters
    ----------
    sma_fast_period, sma_slow_period:
        Periods of the two SMAs used for confirmation / breakout.
    require_crossup:
        Fresh-Cross filter toggle. ``True`` (default, FC+) requires the
        previous bar's close to be at or below SMA_slow — the canonical
        cross-up trigger. ``False`` (FC-) drops the requirement and accepts
        any bullish bar above both SMAs (trend-continuation mode).
    rsi_threshold:
        When set, blocks entries where RSI(rsi_period) >= this value.
        None (default) disables the filter.
    rsi_period:
        RSI look-back period. Column expected: ``rsi{rsi_period}``.
    bb_filter:
        When True, blocks entries where close >= BB_upper(bb_period).
    bb_period:
        Bollinger Band look-back period. Column expected: ``bb_upper{bb_period}``.
    direction:
        ``Direction.LONG`` (default) or ``Direction.SHORT``. SHORT mirrors
        every comparison in the trigger. The entry filters are long-only and
        raise if combined with SHORT.
    """

    def __init__(
        self,
        sma_fast_period: int = 21,
        sma_slow_period: int = 55,
        require_crossup: bool = True,
        rsi_threshold: float | None = None,
        rsi_period: int = 14,
        bb_filter: bool = False,
        bb_period: int = 20,
        direction: Direction = Direction.LONG,
    ) -> None:
        if direction.is_short and (rsi_threshold is not None or bb_filter):
            raise ValueError(
                "rsi_threshold and bb_filter are long-only; no short mirror is defined"
            )
        self.direction = direction
        self.sma_fast_period = sma_fast_period
        self.sma_slow_period = sma_slow_period
        self.require_crossup = require_crossup
        self.rsi_threshold = rsi_threshold
        self.rsi_period = rsi_period
        self.bb_filter = bb_filter
        self.bb_period = bb_period
        self._fast_col = f"sma{sma_fast_period}"
        self._slow_col = f"sma{sma_slow_period}"
        self._rsi_col = f"rsi{rsi_period}"
        self._bb_upper_col = f"bb_upper{bb_period}"

    def required_columns(self) -> tuple[str, ...]:
        cols: list[str] = ["open", "close", self._fast_col, self._slow_col]
        if self.rsi_threshold is not None:
            cols.append(self._rsi_col)
        if self.bb_filter:
            cols.append(self._bb_upper_col)
        return tuple(cols)

    def check_entry(self, bars: pd.DataFrame, idx: int) -> bool:
        """Return True if the bar at integer position `idx` triggers entry."""
        if idx < 1 or idx >= len(bars):
            return False
        missing = [c for c in self.required_columns() if c not in bars.columns]
        if missing:
            raise ValueError(f"bars missing required columns: {missing}")
        curr = bars.iloc[idx]
        prev = bars.iloc[idx - 1]
        return check_entry(
            curr_open=float(curr["open"]),
            curr_close=float(curr["close"]),
            curr_sma21=float(curr[self._fast_col]),
            curr_sma65=float(curr[self._slow_col]),
            prev_close=float(prev["close"]),
            prev_sma65=float(prev[self._slow_col]),
            require_crossup=self.require_crossup,
            curr_rsi=float(curr[self._rsi_col]) if self.rsi_threshold is not None else None,
            rsi_threshold=self.rsi_threshold,
            curr_bb_upper=float(curr[self._bb_upper_col]) if self.bb_filter else None,
            bb_filter=self.bb_filter,
            direction=self.direction,
        )

    def find_entry_signals(self, bars: pd.DataFrame) -> pd.Series:
        """Boolean Series aligned to `bars.index`: True where entry fires."""
        missing = [c for c in self.required_columns() if c not in bars.columns]
        if missing:
            raise ValueError(f"bars missing required columns: {missing}")
        prev_close = bars["close"].shift(1)
        prev_slow = bars[self._slow_col].shift(1)
        if self.direction.is_long:
            base = (
                (bars["close"] > bars[self._slow_col])
                & (bars["close"] > bars[self._fast_col])
                & (bars["close"] > bars["open"])
            )
            fresh_cross = prev_close <= prev_slow
        else:
            base = (
                (bars["close"] < bars[self._slow_col])
                & (bars["close"] < bars[self._fast_col])
                & (bars["close"] < bars["open"])
            )
            fresh_cross = prev_close >= prev_slow
        if self.require_crossup:
            signal = base & fresh_cross
        else:
            # FC- still requires a defined prior bar so SMA warm-up NaNs
            # naturally drop the first row.
            signal = base & prev_close.notna() & prev_slow.notna()
        if self.rsi_threshold is not None:
            rsi_ok = bars[self._rsi_col].notna() & (bars[self._rsi_col] < self.rsi_threshold)
            signal = signal & rsi_ok
        if self.bb_filter:
            bb_ok = bars[self._bb_upper_col].notna() & (bars["close"] < bars[self._bb_upper_col])
            signal = signal & bb_ok
        return signal.fillna(False).astype(bool)
