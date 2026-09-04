# Vendored from ml30-sp500-strategy @ c7ad990 (2026-09-02) — see deltaforge/ml30/__init__.py.
# Only the import paths and PROJECT_ROOT were changed.
"""Technical indicators for the momentum-long strategy.

The strategy uses two-or-three simple moving averages:
- SMA_slow (entry breakout, e.g. 55 canonical)
- SMA_fast (entry confirmation, e.g. 21 canonical)
- SMA_exit (optional, for close-below exit; e.g. 8 / 13 / 21)

Optional entry filters (BB+RSI sweep):
- RSI(14)     — `rsi14`      column; entry blocked when RSI >= threshold
- BB upper(20) — `bb_upper20` column; entry blocked when close >= upper band

All indicators are evaluated off the candle close. Indicators are derived
in-memory at backtest time — never persisted — per TSD §9.2.

Reference: TSD-MomentumLong-v2.1 §4 (indicators).
"""

from __future__ import annotations

import pandas as pd

SMA_FAST_PERIOD: int = 21
SMA_SLOW_PERIOD: int = 55
RSI_PERIOD: int = 14
BB_PERIOD: int = 20
BB_STD_DEV: float = 2.0


def sma(close: pd.Series, period: int) -> pd.Series:
    """Simple moving average over `period` bars, evaluated at each bar's close.

    Returns NaN for the first `period - 1` bars where the window is incomplete.
    """
    if period < 1:
        raise ValueError(f"period must be >= 1, got {period}")
    return close.rolling(window=period, min_periods=period).mean()


def rsi(close: pd.Series, period: int = RSI_PERIOD) -> pd.Series:
    """Relative Strength Index via Wilder smoothing (EWM alpha=1/period).

    Returns NaN for the first `period` bars during the warm-up window.
    Values range 0–100; above 70 is conventionally overbought.
    """
    if period < 1:
        raise ValueError(f"period must be >= 1, got {period}")
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    # Avoid division by zero when avg_loss is 0 (pure uptrend window).
    rs = avg_gain / avg_loss.replace(0.0, float("nan"))
    return 100.0 - (100.0 / (1.0 + rs))


def bollinger_upper(
    close: pd.Series,
    period: int = BB_PERIOD,
    std_dev: float = BB_STD_DEV,
) -> pd.Series:
    """Upper Bollinger Band: SMA(period) + std_dev × rolling population std.

    Returns NaN for the first `period - 1` bars where the window is incomplete.
    """
    if period < 1:
        raise ValueError(f"period must be >= 1, got {period}")
    mid = close.rolling(window=period, min_periods=period).mean()
    std = close.rolling(window=period, min_periods=period).std(ddof=1)
    return mid + std_dev * std


def add_indicators(
    bars: pd.DataFrame,
    fast: int = SMA_FAST_PERIOD,
    slow: int = SMA_SLOW_PERIOD,
    exit_period: int | None = None,
    rsi_period: int | None = None,
    bb_period: int | None = None,
    bb_std_dev: float = BB_STD_DEV,
) -> pd.DataFrame:
    """Return a copy of `bars` with indicator columns appended.

    Always adds: `sma{fast}`, `sma{slow}`.
    Optional:
      `sma{exit_period}` — when exit_period is set and differs from fast/slow.
      `rsi{rsi_period}`  — when rsi_period is set (e.g. 14 → `rsi14`).
      `bb_upper{bb_period}` — when bb_period is set (e.g. 20 → `bb_upper20`).

    The input must contain a `close` column. Original DataFrame is not mutated;
    `df.attrs` (notably the `symbol` tag) is propagated to the output.
    """
    if "close" not in bars.columns:
        raise ValueError("bars DataFrame must contain a 'close' column")
    out = bars.copy()
    out[f"sma{fast}"] = sma(out["close"], fast)
    out[f"sma{slow}"] = sma(out["close"], slow)
    if exit_period is not None and exit_period not in (fast, slow):
        out[f"sma{exit_period}"] = sma(out["close"], exit_period)
    if rsi_period is not None:
        out[f"rsi{rsi_period}"] = rsi(out["close"], rsi_period)
    if bb_period is not None:
        out[f"bb_upper{bb_period}"] = bollinger_upper(out["close"], bb_period, bb_std_dev)
    out.attrs.update(bars.attrs)
    return out
