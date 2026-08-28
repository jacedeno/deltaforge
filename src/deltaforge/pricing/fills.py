"""Fill model — where inside the modeled bid-ask a manual order executes.

``haircut`` is the fraction of the modeled half-spread paid per leg:
0 = fills at mid (fantasy), 1.0 = crosses the whole half-spread (market
order into the quote). Default 0.5 — a patient limit order that still gets
filled — and the sweep treats haircut as a robustness axis, never an
optimization axis.
"""

from __future__ import annotations

from dataclasses import dataclass

from deltaforge.pricing.spreads import SpreadWidthModel


@dataclass(frozen=True, slots=True)
class FillModel:
    spread_model: SpreadWidthModel
    haircut: float = 0.5

    def __post_init__(self) -> None:
        if not (0.0 <= self.haircut <= 1.0):
            raise ValueError(f"haircut must be in [0, 1], got {self.haircut}")

    def buy(self, mark: float) -> float:
        return mark + self.haircut * self.spread_model.half_spread(mark)

    def sell(self, mark: float) -> float:
        return max(0.0, mark - self.haircut * self.spread_model.half_spread(mark))
