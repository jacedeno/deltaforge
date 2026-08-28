"""Options-overlay backtest over a Phase 1 signal-event feed.

Runs the selected structure(s) on the identical event stream, joins them per
event with the shares benchmark, and replays each through the $3,000
portfolio constraints. Artifacts per structure: ``<label>_<structure>_trades.json``
and stats; plus ``<label>_comparison.json`` (side-by-side + per-event join)
and ``<label>_config.json`` (full provenance).

Usage (after sourcing the Alpaca env):
    python scripts/backtest_overlay.py \\
        --events-file reports/phase1/events30m_trades.json \\
        --structure all --pricing real --start 2024-02-12 --end 2026-08-01 \\
        --label real_window
"""

from __future__ import annotations

import argparse
import json
import time as _time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from alpaca.data.enums import DataFeed
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from structlog import get_logger

from deltaforge.compare.harness import EventPipeline, per_event_join
from deltaforge.engine.coordinator import run_portfolio
from deltaforge.engine.metrics import portfolio_stats, trade_stats
from deltaforge.ml30_bridge import (
    AlpacaClientError,
    AlpacaHistoricalClient,
    deltaforge_commit,
    ml30_commit,
)
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
ALPACA_OPTIONS_DATA_START = "2024-02-12"  # first Monday with option bars

STRUCTURES = {
    "debit_spread": DebitSpread,
    "long_call": LongCall,
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events-file", type=Path, required=True)
    parser.add_argument("--structure", default="all", choices=[*STRUCTURES, "all"])
    parser.add_argument("--pricing", default="real", choices=["real", "synthetic"])
    parser.add_argument("--start", default=None, help="YYYY-MM-DD filter on signal ts")
    parser.add_argument("--end", default=None)
    parser.add_argument("--fill-haircut", type=float, default=0.5)
    parser.add_argument("--max-debit", type=float, default=150.0)
    parser.add_argument("--dte-exit-days", type=int, default=5)
    parser.add_argument("--next-bar-exit", action="store_true")
    parser.add_argument("--initial-equity", type=float, default=3000.0)
    parser.add_argument("--max-concurrent", type=int, default=3)
    parser.add_argument("--spread-calibration", type=Path,
                        default=CONFIG_DIR / "spread_calibration.json")
    parser.add_argument("--iv-calibration", type=Path,
                        default=CONFIG_DIR / "iv_calibration.json")
    parser.add_argument("--label", required=True)
    parser.add_argument("--out-dir", type=Path, default=REPORTS_DIR / "overlay")
    args = parser.parse_args()

    events = load_events_from_trades_json(args.events_file)
    if args.start:
        lo = datetime.strptime(args.start, "%Y-%m-%d").replace(tzinfo=UTC)
        events = [e for e in events if e.signal_ts.astimezone(UTC) >= lo]
    if args.end:
        hi = datetime.strptime(args.end, "%Y-%m-%d").replace(tzinfo=UTC)
        events = [e for e in events if e.signal_ts.astimezone(UTC) < hi]
    if args.pricing == "real":
        pre = [e for e in events if e.signal_ts.astimezone(UTC).date().isoformat() < ALPACA_OPTIONS_DATA_START]
        if pre:
            log.warning("overlay.events_before_options_data", dropped=len(pre))
            events = [e for e in events if e not in pre]
    if not events:
        raise SystemExit("no events in the selected window")

    spread_model = (
        SpreadWidthModel.load(args.spread_calibration)
        if args.spread_calibration.exists()
        else SpreadWidthModel()
    )
    iv_model = (
        IVModel.load(args.iv_calibration) if args.iv_calibration.exists() else IVModel()
    )
    fills = FillModel(spread_model=spread_model, haircut=args.fill_haircut)
    fees = FeeSchedule()

    symbols = sorted({e.symbol for e in events})
    stock_client = AlpacaHistoricalClient(feed=DataFeed.SIP, cache_dir=SIP_30M_CACHE_DIR)
    # 60 days of pre-signal history so the first events still get a 20d RV.
    span_start = min(e.signal_ts for e in events) - timedelta(days=60)
    span_end = max(
        e.underlying_exit_ts or e.signal_ts for e in events
    )
    bars_by_symbol = {}
    for sym in symbols:
        try:
            bars_by_symbol[sym] = stock_client.fetch_bars(
                sym, span_start.astimezone(UTC), span_end.astimezone(UTC), timeframe=TF_30M
            )
        except AlpacaClientError as exc:
            log.warning("overlay.underlying_fetch_failed", symbol=sym, error=str(exc)[:200])

    wanted = list(STRUCTURES) if args.structure == "all" else [args.structure]
    args.out_dir.mkdir(parents=True, exist_ok=True)
    t0 = _time.monotonic()

    results_by_structure = {}
    stats_by_structure = {}
    for name in wanted:
        pipeline = EventPipeline(
            structure=STRUCTURES[name](),
            pricing=args.pricing,
            fills=fills,
            fees=fees,
            iv_model=iv_model,
            max_debit=args.max_debit,
            dte_exit_days=args.dte_exit_days,
            next_bar_exit=args.next_bar_exit,
        )
        results = pipeline.run(events, bars_by_symbol)
        results_by_structure[name] = results

        trades = [r.trade for r in results if r.trade is not None]
        skips = [r.skip for r in results if r.skip is not None]
        stats = trade_stats(trades, skips)
        portfolio = run_portfolio(
            trades,
            fees,
            initial_equity=args.initial_equity,
            max_concurrent=args.max_concurrent,
            max_debit_cap=args.max_debit,
        )
        stats["portfolio"] = portfolio_stats(portfolio)
        stats_by_structure[name] = stats

        (args.out_dir / f"{args.label}_{name}_trades.json").write_text(
            json.dumps(
                [
                    {
                        "symbol": t.symbol,
                        "signal_ts": t.signal_ts.isoformat(),
                        "legs": [
                            {"occ": leg.occ, "side": leg.side, "strike": leg.strike,
                             "entry_fill": round(leg.entry_fill, 4)}
                            for leg in t.position.legs
                        ],
                        "contracts": t.position.contracts,
                        "debit_per_share": round(t.position.debit_per_share, 4),
                        "debit_dollars": round(t.debit_dollars, 2),
                        "exit_ts": t.exit_ts.isoformat(),
                        "exit_reason": t.exit_reason,
                        "exit_value_per_share": round(t.exit_value_per_share, 4),
                        "pnl_dollars": round(t.pnl_dollars, 2),
                        "pnl_pct_of_debit": round(t.pnl_pct_of_debit, 2),
                        "total_fees": round(t.total_fees, 2),
                        "entry_mark_sources": list(t.entry_mark_sources),
                        "exit_mark_sources": list(t.exit_mark_sources),
                        "underlying_exit_reason": t.underlying_exit_reason,
                    }
                    for t in trades
                ],
                indent=1,
            )
        )
        log.info("overlay.structure_done", structure=name,
                 traded=stats.get("events_traded"), skipped=stats.get("events_skipped"))

    shares_budget = args.initial_equity / args.max_concurrent
    join = per_event_join(events, results_by_structure, shares_budget)

    comparison = {
        "label": args.label,
        "events": len(events),
        "structures": stats_by_structure,
        "shares_budget_per_event": shares_budget,
        "per_event": join,
    }
    (args.out_dir / f"{args.label}_comparison.json").write_text(json.dumps(comparison, indent=1))

    config = {
        "label": args.label,
        "events_file": str(args.events_file),
        "events": len(events),
        "structures": wanted,
        "pricing": args.pricing,
        "start": args.start,
        "end": args.end,
        "fill_haircut": args.fill_haircut,
        "max_debit": args.max_debit,
        "dte_exit_days": args.dte_exit_days,
        "next_bar_exit": args.next_bar_exit,
        "initial_equity": args.initial_equity,
        "max_concurrent": args.max_concurrent,
        "fees": {"per_contract": fees.per_contract},
        "spread_model": {"a": spread_model.a, "b": spread_model.b,
                         "calibrated": spread_model.calibrated},
        "iv_model": {"a": iv_model.a, "b": iv_model.b, "calibrated": iv_model.calibrated},
        "ml30_commit": ml30_commit(),
        "deltaforge_commit": deltaforge_commit(),
        "elapsed_seconds": round(_time.monotonic() - t0, 1),
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    (args.out_dir / f"{args.label}_config.json").write_text(json.dumps(config, indent=1))
    log.info("overlay.done", label=args.label, out_dir=str(args.out_dir))


if __name__ == "__main__":
    main()
