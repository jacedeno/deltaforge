"""Options transaction costs.

Alpaca charges no commission on options; the $0.65/contract/leg figure in
docs/ANALYSIS.md is the conservative planning number (covers regulatory
fees plus a broker-agnostic margin so the playbook survives a move to a
commissioned broker). Both rates are explicit so runs can sweep them.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FeeSchedule:
    commission_per_contract: float = 0.60
    regulatory_per_contract: float = 0.05  # ORF + OCC clearing, rounded up

    @property
    def per_contract(self) -> float:
        return self.commission_per_contract + self.regulatory_per_contract

    def one_way(self, n_legs: int, n_contracts: int = 1) -> float:
        """Cost of opening (or closing) every leg once."""
        if n_legs < 1 or n_contracts < 1:
            raise ValueError(f"n_legs and n_contracts must be >= 1, got {n_legs}, {n_contracts}")
        return self.per_contract * n_legs * n_contracts

    def round_trip(self, n_legs: int, n_contracts: int = 1) -> float:
        """Open + close. A 1-contract 2-leg spread: 4 x $0.65 = $2.60."""
        return 2 * self.one_way(n_legs, n_contracts)


DEFAULT_FEES = FeeSchedule()
