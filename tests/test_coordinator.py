from datetime import UTC, date, datetime, timedelta

from deltaforge.engine.coordinator import run_portfolio
from deltaforge.engine.trade import EXIT_TARGET, OptionTrade
from deltaforge.pricing.fees import FeeSchedule
from deltaforge.structures.base import Leg, Position

FEES = FeeSchedule()


def make_trade(
    symbol: str,
    open_day: int,
    close_day: int,
    debit: float = 1.50,
    exit_value: float = 3.00,
) -> OptionTrade:
    ts = datetime(2026, 1, 5, 15, 0, tzinfo=UTC) + timedelta(days=open_day)
    expiry = date(2026, 3, 20)
    pos = Position(
        structure="debit_spread",
        legs=(
            Leg("X260320C00100000", expiry, 100.0, +1, debit + 0.8),
            Leg("X260320C00105000", expiry, 105.0, -1, 0.8),
        ),
        contracts=1,
        entry_ts=ts,
        debit_per_share=debit,
        open_fees=FEES.one_way(2, 1),
    )
    t = OptionTrade(symbol=symbol, signal_ts=ts, position=pos)
    t.exit_ts = datetime(2026, 1, 5, 20, 30, tzinfo=UTC) + timedelta(days=close_day)
    t.exit_reason = EXIT_TARGET
    t.exit_value_per_share = exit_value
    t.close_fees = FEES.one_way(2, 1)
    return t


def test_slot_cap_skips_fourth_concurrent():
    trades = [make_trade(s, open_day=0, close_day=10) for s in ("A", "B", "C", "D")]
    res = run_portfolio(trades, FEES, max_concurrent=3)
    assert len(res.trades) == 3
    assert res.skipped_by_cap == 1


def test_one_per_underlying():
    trades = [make_trade("A", 0, 10), make_trade("A", 2, 12)]
    res = run_portfolio(trades, FEES)
    assert len(res.trades) == 1
    assert res.skipped_by_cap == 1


def test_slot_frees_after_exit():
    trades = [make_trade("A", 0, 3), make_trade("A", 5, 9)]
    res = run_portfolio(trades, FEES)
    assert len(res.trades) == 2


def test_budget_sizes_contracts():
    # debit $150/contract with $150 budget -> exactly 1 contract.
    trades = [make_trade("A", 0, 3, debit=1.50)]
    res = run_portfolio(trades, FEES, max_debit_cap=150.0)
    assert res.trades[0].position.contracts == 1


def test_equity_compounds():
    trades = [make_trade("A", 0, 3), make_trade("B", 5, 9)]
    res = run_portfolio(trades, FEES)
    expected = 3000.0 + sum(t.pnl_dollars for t in res.trades)
    assert res.final_equity == expected
    assert res.final_equity > 3000.0


def test_never_deploys_more_cash_than_the_account_holds():
    """Long options are paid in full, so open debits are cash that is gone."""
    # Five overlapping $1,000 positions against a $3,000 account: only three
    # can be funded, however many slots the cap allows.
    trades = [make_trade(s, open_day=0, close_day=20, debit=10.0) for s in "ABCDE"]
    res = run_portfolio(trades, FEES, initial_equity=3000.0, max_concurrent=5,
                        max_debit_cap=1000.0, max_debit_equity_pct=1.0)
    assert len(res.trades) == 3
    assert res.skipped_by_budget == 2
    peak = max(
        sum(t.debit_dollars for t in res.trades[:n]) for n in range(1, len(res.trades) + 1)
    )
    assert peak <= 3000.0
