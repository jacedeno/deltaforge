"""OptionTrade — one options position opened on a signal event and closed.

Modeled on ml30's ``backtest.trade.Trade`` but contract-aware: legs, debit,
fees on both sides, and the mark sources that priced entry and exit (so a
run can report what fraction of its P&L rests on synthetic marks).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from deltaforge.structures.base import CONTRACT_MULTIPLIER, Position

EXIT_STOP = "stop"
EXIT_TARGET = "target"
EXIT_DTE = "dte_exit"
EXIT_WINDOW_END = "window_end"


@dataclass(slots=True)
class OptionTrade:
    symbol: str
    signal_ts: datetime
    position: Position

    exit_ts: datetime | None = None
    exit_reason: str | None = None
    exit_value_per_share: float | None = None  # net closing proceeds per share
    close_fees: float = 0.0
    entry_mark_sources: tuple[str, ...] = ()
    exit_mark_sources: tuple[str, ...] = ()
    # Underlying-side context for joins/diagnostics.
    underlying_exit_reason: str | None = None
    notes: dict[str, float] = field(default_factory=dict)

    @property
    def is_open(self) -> bool:
        return self.exit_ts is None

    @property
    def debit_dollars(self) -> float:
        return self.position.debit_dollars

    @property
    def total_fees(self) -> float:
        return self.position.open_fees + self.close_fees

    @property
    def pnl_dollars(self) -> float:
        """Realized P&L including all fees; 0 while open."""
        if self.exit_value_per_share is None:
            return 0.0
        gross = (
            (self.exit_value_per_share - self.position.debit_per_share)
            * CONTRACT_MULTIPLIER
            * self.position.contracts
        )
        return gross - self.total_fees

    @property
    def pnl_pct_of_debit(self) -> float:
        return self.pnl_dollars / self.debit_dollars * 100 if self.debit_dollars else 0.0
