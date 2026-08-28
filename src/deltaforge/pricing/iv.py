"""Volatility inputs for synthetic pricing.

``realized_vol`` measures the underlying; ``IVModel`` maps that to an
implied vol for Black-Scholes marks when no market observation is usable.
The default coefficients are an uncalibrated prior (IV runs ~10% above RV
plus a floor); ``scripts/calibrate_iv.py`` refits them on the 2024-2026
overlap (backed-out IVs from real option bars vs RV) and persists them to
``config/iv_calibration.json``. Runs report whether they priced with the
prior or a calibration file.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd

TRADING_DAYS = 252


def realized_vol(daily_closes: pd.Series, window: int = 20) -> float:
    """Annualized close-to-close vol over the trailing ``window`` days."""
    rets = daily_closes.dropna().pct_change().dropna().tail(window)
    if len(rets) < window // 2:
        raise ValueError(f"need >= {window // 2} daily returns, got {len(rets)}")
    return float(rets.std(ddof=1) * math.sqrt(TRADING_DAYS))


# Approximate 3M T-bill by year — at 14-21 DTE the rate term is noise next
# to the bid-ask haircut, so a constant per year is deliberate.
RISK_FREE_BY_YEAR: dict[int, float] = {
    2020: 0.005,
    2021: 0.0005,
    2022: 0.02,
    2023: 0.05,
    2024: 0.052,
    2025: 0.045,
    2026: 0.04,
}


def risk_free(year: int) -> float:
    return RISK_FREE_BY_YEAR.get(year, 0.04)


@dataclass(frozen=True, slots=True)
class IVModel:
    a: float = 0.04
    b: float = 1.10
    calibrated: bool = False
    lo: float = 0.10
    hi: float = 2.00

    def predict(self, rv: float) -> float:
        return min(max(self.a + self.b * rv, self.lo), self.hi)

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(asdict(self), indent=1))

    @classmethod
    def load(cls, path: Path) -> IVModel:
        return cls(**json.loads(path.read_text()))
