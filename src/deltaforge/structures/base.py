"""Structure protocol — how a signal event becomes an options position.

A structure's ``select`` either returns a ``Position`` (legs chosen, entry
fills computed, contract count sized to budget) or a ``Skip`` naming why the
event was untradeable for that structure. Skips are first-class results: the
skip rate per reason is itself a backtest output (ANALYSIS.md's viability
question includes "how often is there no usable strike at all?").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Callable, Protocol

from deltaforge.data.chains import DiscoveredContract
from deltaforge.pricing.fees import FeeSchedule
from deltaforge.pricing.fills import FillModel
from deltaforge.pricing.marks import Mark
from deltaforge.signals.events import SignalEvent

CONTRACT_MULTIPLIER = 100


@dataclass(frozen=True, slots=True)
class Leg:
    occ: str
    expiry: date
    strike: float
    side: int  # +1 long, -1 short
    entry_fill: float  # per share


@dataclass(frozen=True, slots=True)
class Position:
    structure: str
    legs: tuple[Leg, ...]
    contracts: int
    entry_ts: datetime
    debit_per_share: float  # net premium paid per share (fills, no fees)
    open_fees: float

    @property
    def debit_dollars(self) -> float:
        return self.debit_per_share * CONTRACT_MULTIPLIER * self.contracts

    @property
    def expiry(self) -> date:
        return min(leg.expiry for leg in self.legs)


@dataclass(frozen=True, slots=True)
class Skip:
    reason: str  # no_expiry_in_window | no_contracts | no_long_strike | no_width | debit_exceeds_budget | negative_debit
    detail: str = ""


@dataclass(slots=True)
class EntryContext:
    """Everything a structure may consult at entry time."""

    event: SignalEvent
    spot: float
    rv: float
    contracts: list[DiscoveredContract]
    mark: Callable[[str], Mark]  # entry-time mark for one OCC symbol
    entry_delta: Callable[[DiscoveredContract], float | None]
    fills: FillModel
    fees: FeeSchedule
    max_debit: float
    params: dict[str, float] = field(default_factory=dict)


class Structure(Protocol):
    name: str

    def select(self, ctx: EntryContext) -> Position | Skip: ...


def size_contracts(debit_per_share: float, max_debit: float) -> int:
    if debit_per_share <= 0:
        return 0
    return int(max_debit // (debit_per_share * CONTRACT_MULTIPLIER))
