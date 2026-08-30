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

# Two ways to deploy the same capital: bigger positions, or more of them.
# Concentration (few large) and diversification (many small) reach 100%
# deployment by opposite routes and do not behave alike, so the grid crosses
# both axes rather than walking one.
DEBITS = [150.0, 300.0, 500.0]
SLOTS = [3, 5, 8, 10, 15, 20]


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
    print(f"{'per position':>13}{'slots':>7}{'deployed':>10}{'final':>12}"
          f"{'return':>9}{'maxDD':>8}{'taken':>8}{'capped':>8}")
    print("-" * 75)

    for debit in DEBITS:
        for slots in SLOTS:
            res = run_portfolio(
                trades,
                FEES,
                initial_equity=INITIAL,
                max_concurrent=slots,
                max_debit_cap=debit,
                max_debit_equity_pct=1.0,
            )
            s = portfolio_stats(res)
            deployed = debit * slots / INITIAL * 100
            print(
                f"${debit:>12,.0f}{slots:>7}{deployed:>9.0f}%"
                f"${s['final_equity']:>11,.0f}{s['total_return_pct']:>8.0f}%"
                f"{s['max_drawdown_pct']:>7.0f}%{s['trades_taken']:>8}"
                f"{res.skipped_by_cap:>8}"
            )
        print()

    print(
        "\nCaveats: replayed trades all passed the original $150 filter, so"
        "\nbigger budgets cannot admit the 1,656 events skipped as too"
        "\nexpensive — these returns are a floor. Long options are not"
        "\nmarginable (Reg T, 100% under 9 months), so every row is cash."
    )


if __name__ == "__main__":
    main()
