"""Bid-ask width model.

Alpaca keeps no historical option quotes, so the half-spread at a historical
timestamp is modeled, not observed: ``half = max(floor, a + b * premium)``.
Defaults are a deliberately pessimistic prior for sub-$150 liquid names
(~12% total spread on a $1.00 mark); ``scripts/calibrate_spread_model.py``
refits from live chain snapshots (which do carry real bid/ask) and persists
to ``config/spread_calibration.json``.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class SpreadWidthModel:
    a: float = 0.02
    b: float = 0.04
    floor: float = 0.01
    calibrated: bool = False

    def half_spread(self, premium: float) -> float:
        return max(self.floor, self.a + self.b * max(premium, 0.0))

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(asdict(self), indent=1))

    @classmethod
    def load(cls, path: Path) -> SpreadWidthModel:
        return cls(**json.loads(path.read_text()))
