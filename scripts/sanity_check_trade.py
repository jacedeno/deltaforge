"""Hand-verifiable walkthrough of one overlay trade.

Prints, for one event from a Phase 1 events file: the discovered chain, the
chosen strikes with their deltas, entry/exit marks (with their ladder
source) against the raw Alpaca bars, fees, and the final P&L — everything a
human needs to recompute the trade on paper.

Usage:
    python scripts/sanity_check_trade.py \\
        --events-file reports/phase1/events30m_trades.json \\
        --index -1            # which event (default: last post-Feb-2024 one)
"""

from __future__ import annotations

import argparse
from datetime import UTC, timedelta
from pathlib import Path

from alpaca.data.enums import DataFeed
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

from deltaforge.compare.harness import EventPipeline
from deltaforge.ml30_bridge import AlpacaHistoricalClient
from deltaforge.settings import SIP_30M_CACHE_DIR
from deltaforge.signals.events import load_events_from_trades_json
from deltaforge.structures.debit_spread import DebitSpread

TF_30M = TimeFrame(30, TimeFrameUnit.Minute)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events-file", type=Path, required=True)
    parser.add_argument("--index", type=int, default=-1)
    args = parser.parse_args()

    events = [
        e
        for e in load_events_from_trades_json(args.events_file)
        if e.signal_ts.astimezone(UTC).date().isoformat() >= "2024-02-12"
    ]
    event = events[args.index]
    print(f"Event: {event.symbol} @ {event.signal_ts}")
    print(f"  entry {event.entry_price:.2f}  stop {event.stop:.2f}  "
          f"target {event.target:.2f}  (dist {event.target_distance_pct*100:.2f}%)")
    print(f"  underlying exit: {event.underlying_exit_reason} @ {event.underlying_exit_price}")

    client = AlpacaHistoricalClient(feed=DataFeed.SIP, cache_dir=SIP_30M_CACHE_DIR)
    bars = client.fetch_bars(
        event.symbol,
        event.signal_ts.astimezone(UTC) - timedelta(days=60),
        (event.underlying_exit_ts or event.signal_ts).astimezone(UTC),
        timeframe=TF_30M,
    )

    pipeline = EventPipeline(structure=DebitSpread(), pricing="real")
    result = pipeline.run_event(event, bars)

    if result.skip:
        print(f"SKIPPED: {result.skip.reason} {result.skip.detail}")
        return
    t = result.trade
    print("\nPosition:")
    for leg in t.position.legs:
        side = "LONG " if leg.side > 0 else "SHORT"
        print(f"  {side} {leg.occ}  strike {leg.strike}  entry fill {leg.entry_fill:.4f}")
    print(f"  contracts {t.position.contracts}  debit/share {t.position.debit_per_share:.4f}"
          f"  debit ${t.debit_dollars:.2f}  open fees ${t.position.open_fees:.2f}")
    print(f"  entry mark sources: {t.entry_mark_sources}")
    print("\nExit:")
    print(f"  {t.exit_reason} @ {t.exit_ts}")
    print(f"  exit value/share {t.exit_value_per_share:.4f}  close fees ${t.close_fees:.2f}")
    print(f"  exit mark sources: {t.exit_mark_sources}")
    print(f"\nP&L: ${t.pnl_dollars:.2f}  ({t.pnl_pct_of_debit:+.1f}% of debit)")


if __name__ == "__main__":
    main()
