from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest

from deltaforge.signals.events import SignalEvent


def make_bars(
    start: str,
    days: int,
    open_price: float = 100.0,
    drift_per_bar: float = 0.0,
    bar_range: float = 0.5,
) -> pd.DataFrame:
    """Flat-ish 30m RTH bars: 13 bars/day, deterministic."""
    stamps = []
    for d in pd.bdate_range(start, periods=days):
        day_bars = pd.date_range(
            d + pd.Timedelta(hours=14, minutes=30), periods=13, freq="30min", tz=UTC
        )
        stamps.extend(day_bars)
    idx = pd.DatetimeIndex(stamps, name="timestamp")
    closes = open_price + drift_per_bar * np.arange(len(idx))
    return pd.DataFrame(
        {
            "open": closes,
            "high": closes + bar_range,
            "low": closes - bar_range,
            "close": closes,
            "volume": 1000.0,
            "trade_count": 10.0,
            "vwap": closes,
        },
        index=idx,
    )


@pytest.fixture
def event() -> SignalEvent:
    return SignalEvent(
        symbol="TEST",
        signal_ts=datetime(2026, 3, 2, 15, 0, tzinfo=UTC),
        entry_price=100.0,
        stop=97.0,
        target=109.0,
        risk_per_share=3.0,
        underlying_exit_ts=None,
        underlying_exit_price=None,
        underlying_exit_reason=None,
    )
