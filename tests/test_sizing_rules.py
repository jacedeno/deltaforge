"""The sizing rule the study settled on: fixed position size, growing slot count."""

from __future__ import annotations

import pytest

from deltaforge.live.executor import BotConfig, Executor


class _StubJournal:
    def __init__(self, deployed: float = 0.0) -> None:
        self._deployed = deployed

    def deployed_debit(self) -> float:
        return self._deployed


def make_executor(deployed: float = 0.0, **cfg) -> Executor:
    ex = Executor.__new__(Executor)  # no broker/network needed for the arithmetic
    ex.cfg = BotConfig(**cfg)
    ex.journal = _StubJournal(deployed)
    return ex


def test_one_slot_per_position_size():
    ex = make_executor()
    assert ex.slots(3000.0) == 10
    assert ex.slots(3300.0) == 11
    assert ex.slots(3600.0) == 12


def test_slots_shrink_with_the_account():
    ex = make_executor()
    assert ex.slots(2000.0) == 6
    assert ex.slots(900.0) == 3


def test_slot_count_is_capped_where_signals_run_out():
    ex = make_executor(max_slots=15)
    assert ex.slots(30_000.0) == 15


def test_at_least_one_slot():
    assert make_executor().slots(50.0) == 1


def test_budget_is_bounded_by_free_cash():
    # $3,000 account with $2,850 already deployed leaves $150, not a full $300.
    ex = make_executor(deployed=2850.0)
    assert ex.budget(3000.0) == pytest.approx(150.0)


def test_budget_never_negative_when_fully_deployed():
    ex = make_executor(deployed=3200.0)
    assert ex.budget(3000.0) == 0.0


def test_budget_capped_at_position_size_when_cash_is_ample():
    ex = make_executor(deployed=0.0)
    assert ex.budget(50_000.0) == pytest.approx(300.0)


def test_dry_run_defaults_to_off():
    """A safety flag that defaults on would make live trading the accident."""
    assert BotConfig().dry_run is False


def test_min_target_distance_defaults_to_the_backtested_floor():
    """Below 5% the backtest's signals returned 4% of the profit for 54% of trades."""
    assert BotConfig().min_target_distance_pct == 5.0
