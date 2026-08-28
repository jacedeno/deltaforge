"""Phase 3 — variation sweep over the overlay's knobs.

Grid: DTE window x long-leg delta x short-strike placement (3R / 2R / none =
long call) x fill haircut. Haircut is a robustness axis, not an optimization
axis: a configuration that only wins at haircut 0 is a fantasy. Option data
is cached per contract, so re-runs are cheap; the first run fetches.

Judge robustness across the grid, not the single best cell (ml30 rule).

Usage:
    python scripts/sweep_overlay.py \\
        --events-file reports/phase1/events30m_trades.json \\
        --pricing real --start 2024-02-12 --label sweep_v1
"""

from __future__ import annotations

import argparse
import itertools
import json
import time as _time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from alpaca.data.enums import DataFeed
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from structlog import get_logger

from deltaforge.compare.harness import EventPipeline
from deltaforge.engine.coordinator import run_portfolio
from deltaforge.engine.metrics import portfolio_stats, trade_stats
from deltaforge.ml30_bridge import AlpacaHistoricalClient, deltaforge_commit, ml30_commit
from deltaforge.pricing.fees import FeeSchedule
from deltaforge.pricing.fills import FillModel
from deltaforge.pricing.iv import IVModel
from deltaforge.pricing.spreads import SpreadWidthModel
from deltaforge.settings import CONFIG_DIR, REPORTS_DIR, SIP_30M_CACHE_DIR
from deltaforge.signals.events import load_events_from_trades_json
from deltaforge.structures.debit_spread import DebitSpread
from deltaforge.structures.long_call import LongCall

log = get_logger(__name__)

TF_30M = TimeFrame(30, TimeFrameUnit.Minute)

DTE_WINDOWS = [(7, 14), (14, 21), (21, 35)]
LONG_DELTAS = [0.55, 0.60, 0.65, 0.70]
SHORT_MODES = [3.0, 2.0, None]  # short strike at r-multiple; None = plain long call
HAIRCUTS = [0.0, 0.25, 0.5, 1.0]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events-file", type=Path, required=True)
    parser.add_argument("--pricing", default="real", choices=["real", "synthetic"])
    parser.add_argument("--start", default=None)
    parser.add_argument("--end", default=None)
    parser.add_argument("--max-debit", type=float, default=150.0)
    parser.add_argument("--label", required=True)
    parser.add_argument("--out-dir", type=Path, default=REPORTS_DIR / "sweep")
    args = parser.parse_args()

    events = load_events_from_trades_json(args.events_file)
    if args.start:
        lo = datetime.strptime(args.start, "%Y-%m-%d").replace(tzinfo=UTC)
        events = [e for e in events if e.signal_ts.astimezone(UTC) >= lo]
    if args.end:
        hi = datetime.strptime(args.end, "%Y-%m-%d").replace(tzinfo=UTC)
        events = [e for e in events if e.signal_ts.astimezone(UTC) < hi]

    spread_path = CONFIG_DIR / "spread_calibration.json"
    iv_path = CONFIG_DIR / "iv_calibration.json"
    spread_model = SpreadWidthModel.load(spread_path) if spread_path.exists() else SpreadWidthModel()
    iv_model = IVModel.load(iv_path) if iv_path.exists() else IVModel()
    fees = FeeSchedule()

    symbols = sorted({e.symbol for e in events})
    client = AlpacaHistoricalClient(feed=DataFeed.SIP, cache_dir=SIP_30M_CACHE_DIR)
    span_start = min(e.signal_ts for e in events).astimezone(UTC) - timedelta(days=60)
    span_end = max((e.underlying_exit_ts or e.signal_ts) for e in events).astimezone(UTC)
    bars_by_symbol = {
        s: client.fetch_bars(s, span_start, span_end, timeframe=TF_30M) for s in symbols
    }

    t0 = _time.monotonic()
    rows = []
    grid = list(itertools.product(DTE_WINDOWS, LONG_DELTAS, SHORT_MODES, HAIRCUTS))
    for (dte_lo, dte_hi), delta, short_r, haircut in grid:
        if short_r is None:
            structure = LongCall(delta=delta, dte_min=dte_lo, dte_max=dte_hi)
        else:
            structure = DebitSpread(
                long_delta=delta, dte_min=dte_lo, dte_max=dte_hi, short_at_r=short_r
            )
        pipeline = EventPipeline(
            structure=structure,
            pricing=args.pricing,
            fills=FillModel(spread_model=spread_model, haircut=haircut),
            fees=fees,
            iv_model=iv_model,
            max_debit=args.max_debit,
            dte_envelope=(dte_lo, dte_hi),
        )
        results = pipeline.run(events, bars_by_symbol)
        trades = [r.trade for r in results if r.trade is not None]
        skips = [r.skip for r in results if r.skip is not None]
        stats = trade_stats(trades, skips)
        stats["portfolio"] = portfolio_stats(run_portfolio(trades, fees, max_debit_cap=args.max_debit))
        rows.append(
            {
                "dte": [dte_lo, dte_hi],
                "long_delta": delta,
                "short_at_r": short_r,
                "haircut": haircut,
                **{k: stats.get(k) for k in (
                    "events_traded", "events_skipped", "win_rate_pct",
                    "avg_pnl_pct_of_debit", "profit_factor", "total_pnl_dollars",
                )},
                "final_equity": stats["portfolio"]["final_equity"],
                "max_drawdown_pct": stats["portfolio"]["max_drawdown_pct"],
            }
        )
        log.info("sweep.cell", dte=f"{dte_lo}-{dte_hi}", delta=delta, short_r=short_r,
                 haircut=haircut, traded=stats.get("events_traded"),
                 final_equity=stats["portfolio"]["final_equity"])

    args.out_dir.mkdir(parents=True, exist_ok=True)
    out = {
        "label": args.label,
        "events": len(events),
        "pricing": args.pricing,
        "grid_cells": len(rows),
        "ml30_commit": ml30_commit(),
        "deltaforge_commit": deltaforge_commit(),
        "elapsed_seconds": round(_time.monotonic() - t0, 1),
        "cells": rows,
    }
    (args.out_dir / f"{args.label}_matrix.json").write_text(json.dumps(out, indent=1))
    log.info("sweep.done", cells=len(rows), out=str(args.out_dir / f"{args.label}_matrix.json"))


if __name__ == "__main__":
    main()
