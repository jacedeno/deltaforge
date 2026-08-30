"""Portfolio replay — the $3,000 account constraint applied to a trade stream.

Takes the *uncapped* per-event results (every signal traded in isolation
with the standard budget) and replays them chronologically under the account
rules from ANALYSIS.md: 3 slots, one position per underlying, max debit
min($150, 5% of current equity). Contract counts are rescaled to the budget
at open time (P&L scales linearly per contract; fees are recomputed).

Trades the cap rejects are recorded, like ml30's
``skipped_entries_due_to_cap`` — slot pressure is a result, not noise.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime

from deltaforge.engine.trade import OptionTrade
from deltaforge.pricing.fees import FeeSchedule
from deltaforge.structures.base import CONTRACT_MULTIPLIER


@dataclass(slots=True)
class PortfolioResult:
    initial_equity: float
    final_equity: float
    trades: list[OptionTrade]
    equity_curve: list[tuple[datetime, float]]
    skipped_by_cap: int
    skipped_by_budget: int
    open_at_end: int
    config: dict[str, float] = field(default_factory=dict)


def _rescale(trade: OptionTrade, contracts: int, fees: FeeSchedule) -> OptionTrade:
    n_legs = len(trade.position.legs)
    pos = replace(trade.position, contracts=contracts, open_fees=fees.one_way(n_legs, contracts))
    out = OptionTrade(symbol=trade.symbol, signal_ts=trade.signal_ts, position=pos)
    out.exit_ts = trade.exit_ts
    out.exit_reason = trade.exit_reason
    out.exit_value_per_share = trade.exit_value_per_share
    out.close_fees = fees.one_way(n_legs, contracts)
    out.entry_mark_sources = trade.entry_mark_sources
    out.exit_mark_sources = trade.exit_mark_sources
    out.underlying_exit_reason = trade.underlying_exit_reason
    return out


def run_portfolio(
    event_trades: list[OptionTrade],
    fees: FeeSchedule,
    initial_equity: float = 3000.0,
    max_concurrent: int = 3,
    max_debit_cap: float = 150.0,
    max_debit_equity_pct: float = 0.05,
    one_per_underlying: bool = True,
) -> PortfolioResult:
    """``event_trades``: closed uncapped trades, any order; opens are replayed in ts order."""
    pending = sorted(
        (t for t in event_trades if t.exit_ts is not None), key=lambda t: t.signal_ts
    )

    equity = initial_equity
    open_trades: list[OptionTrade] = []
    taken: list[OptionTrade] = []
    curve: list[tuple[datetime, float]] = []
    skipped_cap = 0
    skipped_budget = 0

    def settle_through(ts: datetime) -> None:
        nonlocal equity
        due = sorted((t for t in open_trades if t.exit_ts <= ts), key=lambda t: t.exit_ts)
        for t in due:
            equity += t.pnl_dollars
            open_trades.remove(t)
            curve.append((t.exit_ts, equity))

    for trade in pending:
        settle_through(trade.signal_ts)

        if len(open_trades) >= max_concurrent or (
            one_per_underlying and any(t.symbol == trade.symbol for t in open_trades)
        ):
            skipped_cap += 1
            continue

        # Long options are paid for in full (Reg T, under nine months), so the
        # debits of everything already open are cash that is gone until those
        # positions close. Without this the replay happily runs ten $300
        # positions on a $2,000 account during a drawdown — deploying money
        # that does not exist, exactly when the account can least afford it.
        cash_available = equity - sum(t.debit_dollars for t in open_trades)
        budget = min(max_debit_cap, equity * max_debit_equity_pct, cash_available)
        per_contract_debit = trade.position.debit_per_share * CONTRACT_MULTIPLIER
        contracts = int(budget // per_contract_debit) if per_contract_debit > 0 else 0
        if contracts < 1:
            skipped_budget += 1
            continue

        scaled = _rescale(trade, contracts, fees)
        open_trades.append(scaled)
        taken.append(scaled)

    # Settle whatever remains open at the end of the stream.
    still_open = list(open_trades)
    for t in sorted(still_open, key=lambda t: t.exit_ts):
        equity += t.pnl_dollars
        open_trades.remove(t)
        curve.append((t.exit_ts, equity))

    return PortfolioResult(
        initial_equity=initial_equity,
        final_equity=equity,
        trades=taken,
        equity_curve=curve,
        skipped_by_cap=skipped_cap,
        skipped_by_budget=skipped_budget,
        open_at_end=0,
        config={
            "max_concurrent": max_concurrent,
            "max_debit_cap": max_debit_cap,
            "max_debit_equity_pct": max_debit_equity_pct,
        },
    )
