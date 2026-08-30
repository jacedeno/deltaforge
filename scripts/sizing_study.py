"""What happens if the $3,000 account sizes up?

Replays the already-computed real-window trades through the portfolio
constraints at several budgets and slot counts. Pure re-simulation of the
sizing rules — no new pricing, no API calls.

Two caveats this study cannot escape, both printed with the results:

  1. It only replays trades that *passed* the original $150 debit filter.
     A bigger budget in a real run would also admit the events skipped for
     being too expensive, which this cannot conjure. So the trade-count
     column is constant and the returns here are a floor, not the full
     effect of sizing up.
  2. Long options are not marginable under Reg T (100% requirement under 9
     months to expiry), so "equity" here is always cash. Any row deploying
     more than 100% of equity is arithmetic, not a tradeable plan.

Usage:
    python scripts/sizing_study.py \\
        --trades reports/overlay/real_window_debit_spread_trades.json
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from deltaforge.engine.coordinator import run_portfolio
from deltaforge.engine.metrics import portfolio_stats
from deltaforge.engine.trade import OptionTrade
from deltaforge.pricing.fees import FeeSchedule
from deltaforge.structures.base import Leg, Position

FEES = FeeSchedule()
INITIAL = 3000.0

# (label, max_debit_per_position, slots, pct_of_equity_deployed_at_start)
SCENARIOS = [
    ("conservative (as backtested)", 150.0, 3, None),
    ("double the debit", 300.0, 3, None),
    ("$500 per position", 500.0, 3, None),
    ("all-in, 3 slots", 1000.0, 3, None),
    ("all-in, 2 slots", 1500.0, 2, None),
    ("all-in, 1 slot", 3000.0, 1, None),
    ("equity-scaled 5% (compounding)", 150.0, 3, 0.05),
    ("equity-scaled 33% (compounding)", 150.0, 3, 0.333),
]


def load_trades(path: Path) -> list[OptionTrade]:
    out = []
    for r in json.loads(path.read_text()):
        legs = tuple(
            Leg(
                occ=lg["occ"],
                expiry=datetime.fromisoformat(r["exit_ts"]).date(),
                strike=lg["strike"],
                side=lg["side"],
                entry_fill=lg["entry_fill"],
            )
            for lg in r["legs"]
        )
        pos = Position(
            structure="replay",
            legs=legs,
            contracts=r["contracts"],
            entry_ts=datetime.fromisoformat(r["signal_ts"]),
            debit_per_share=r["debit_per_share"],
            open_fees=FEES.one_way(len(legs), r["contracts"]),
        )
        t = OptionTrade(
            symbol=r["symbol"],
            signal_ts=datetime.fromisoformat(r["signal_ts"]),
            position=pos,
        )
        t.exit_ts = datetime.fromisoformat(r["exit_ts"])
        t.exit_reason = r["exit_reason"]
        t.exit_value_per_share = r["exit_value_per_share"]
        t.close_fees = FEES.one_way(len(legs), r["contracts"])
        out.append(t)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trades", type=Path, required=True)
    args = parser.parse_args()

    trades = load_trades(args.trades)
    print(f"replaying {len(trades)} trades from {args.trades.name}\n")
    print(f"{'scenario':<34}{'final':>12}{'return':>10}{'maxDD':>9}"
          f"{'taken':>8}{'capped':>8}{'deployed':>10}")
    print("-" * 91)

    for label, debit, slots, pct in SCENARIOS:
        res = run_portfolio(
            trades,
            FEES,
            initial_equity=INITIAL,
            max_concurrent=slots,
            max_debit_cap=debit,
            max_debit_equity_pct=pct if pct is not None else 1.0,
        )
        s = portfolio_stats(res)
        deployed = min(debit * slots, INITIAL * (pct or 1.0) * slots)
        print(
            f"{label:<34}${s['final_equity']:>11,.0f}"
            f"{s['total_return_pct']:>9.0f}%{s['max_drawdown_pct']:>8.0f}%"
            f"{s['trades_taken']:>8}{res.skipped_by_cap:>8}"
            f"{deployed / INITIAL * 100:>9.0f}%"
        )

    print(
        "\nCaveats: replayed trades all passed the original $150 filter, so"
        "\nbigger budgets cannot admit the 1,656 events skipped as too"
        "\nexpensive — these returns are a floor. Long options are not"
        "\nmarginable (Reg T, 100% under 9 months), so every row is cash."
    )


if __name__ == "__main__":
    main()
