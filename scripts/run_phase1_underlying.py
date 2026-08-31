"""Phase 1 — validate the 30-minute ML30 signal on the underlying.

Replays the ML30 mechanics (fresh-cross entry, 8-bar pivot stop, 3R bracket)
on 30-minute SIP bars over the sub-$150 universe, through ml30's own
``Coordinator`` — the same wiring as ``scripts/backtest_topn_portfolio.py``
in the ml30 repo, which only knows 5min/15min. Two canonical runs:

  Benchmark (the "shares" leg of the three-way comparison):
    python scripts/run_phase1_underlying.py --label bench30m \\
        --start 2020-01-01 --end 2026-08-01 \\
        --initial-equity 3000 --max-concurrent 3 --max-position-pct 0.33

  Signal events (uncapped stream, the Phase 2 feed — equity/pct chosen so
  the no-margin exposure cap never binds and every signal is taken):
    python scripts/run_phase1_underlying.py --label events30m \\
        --start 2020-01-01 --end 2026-08-01 \\
        --initial-equity 1000000 --max-concurrent 999 --max-position-pct 0.001

Outputs ml30's artifact triple (``<label>_trades.json``, ``_equity_curve.json``,
``_stats.json``) plus ``<label>_phase1_report.json`` with the go/no-go
metrics defined in the plan (target-touch rate, durations, −1.3R stop-fill
sensitivity, entry→target distance, per-year/per-symbol breadth).
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from alpaca.data.enums import DataFeed
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from structlog import get_logger

from deltaforge.ml30_bridge import (
    AlpacaClientError,
    AlpacaHistoricalClient,
    Coordinator,
    CoordinatorResult,
    Direction,
    add_indicators,
    deltaforge_commit,
    ml30_commit,
)
from deltaforge.settings import REPORTS_DIR, SIP_30M_CACHE_DIR, UNIVERSE_FILE

log = get_logger(__name__)

TF_30M = TimeFrame(30, TimeFrameUnit.Minute)
BARS_PER_DAY_30M = 13  # 09:30-16:00 RTH

# Live stop fills on the 5m book averaged -1.315R vs the modelled -1.00R
# (ml30 CLAUDE.md). The go/no-go expectancy must survive this repricing.
STOP_FILL_SENSITIVITY_R = -1.3


def load_universe_bars(
    symbols: list[str],
    start: datetime,
    end: datetime,
    cache_dir: Path,
    sma_fast: int,
    sma_slow: int,
) -> dict[str, object]:
    client = AlpacaHistoricalClient(feed=DataFeed.SIP, cache_dir=cache_dir)
    bars_by_symbol = {}
    for symbol in symbols:
        try:
            bars = client.fetch_bars(symbol, start, end, timeframe=TF_30M, use_cache=True)
        except AlpacaClientError as exc:
            log.warning("phase1.fetch_failed", symbol=symbol, error=str(exc)[:200])
            continue
        if len(bars) <= sma_slow:
            log.warning("phase1.insufficient_bars", symbol=symbol, rows=len(bars))
            continue
        bars_by_symbol[symbol] = add_indicators(bars, fast=sma_fast, slow=sma_slow)
    return bars_by_symbol


def phase1_report(result: CoordinatorResult) -> dict[str, object]:
    """Go/no-go metrics beyond ml30's standard stats."""
    closed = [t for t in result.trades if t.exit_time is not None]
    if not closed:
        return {"closed_trades": 0}

    r_values = np.array([t.pnl_r for t in closed])
    reasons = [str(t.exit_reason).lower() if t.exit_reason else "open" for t in closed]
    is_stop = np.array([r.endswith("stop") for r in reasons])
    is_target = np.array([r.endswith("target") for r in reasons])

    # Sensitivity: reprice every stop exit at -1.3R instead of its modelled fill.
    r_pessimistic = np.where(is_stop, STOP_FILL_SENSITIVITY_R, r_values)

    def profit_factor(r: np.ndarray) -> float:
        wins, losses = r[r > 0].sum(), -r[r < 0].sum()
        return float(wins / losses) if losses > 0 else float("inf")

    durations_td = [
        int(np.busday_count(t.entry_time.date(), t.exit_time.date())) for t in closed
    ]
    target_dist_pct = np.array(
        [(t.target_price - t.entry_price) / t.entry_price * 100 for t in closed]
    )

    per_year: dict[int, dict[str, float]] = {}
    for year in sorted({t.entry_time.year for t in closed}):
        idx = np.array([t.entry_time.year == year for t in closed])
        per_year[year] = {
            "trades": int(idx.sum()),
            "expectancy_r": round(float(r_values[idx].mean()), 3),
            "profit_factor": round(profit_factor(r_values[idx]), 3),
        }

    per_symbol: dict[str, dict[str, float]] = {}
    for sym in sorted({t.symbol for t in closed}):
        idx = np.array([t.symbol == sym for t in closed])
        per_symbol[sym] = {
            "trades": int(idx.sum()),
            "total_r": round(float(r_values[idx].sum()), 2),
        }

    pct = lambda a, q: round(float(np.percentile(a, q)), 2)  # noqa: E731
    return {
        "closed_trades": len(closed),
        "expectancy_r": round(float(r_values.mean()), 4),
        "expectancy_r_stop_fill_minus_1_3": round(float(r_pessimistic.mean()), 4),
        "profit_factor": round(profit_factor(r_values), 3),
        "profit_factor_stop_fill_minus_1_3": round(profit_factor(r_pessimistic), 3),
        "target_touch_rate_pct": round(float(is_target.mean() * 100), 2),
        "stop_rate_pct": round(float(is_stop.mean() * 100), 2),
        "duration_trading_days": {
            "median": float(np.median(durations_td)),
            "p75": pct(np.array(durations_td), 75),
            "p90": pct(np.array(durations_td), 90),
            "max": int(max(durations_td)),
        },
        "entry_to_target_pct": {
            "p10": pct(target_dist_pct, 10),
            "median": pct(target_dist_pct, 50),
            "p90": pct(target_dist_pct, 90),
        },
        "per_year": per_year,
        "per_symbol": per_symbol,
    }


def persist(
    result: CoordinatorResult,
    out_dir: Path,
    label: str,
    config: dict[str, object],
    elapsed_seconds: float,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    trades = [
        {
            **{
                k: (v.isoformat() if isinstance(v, datetime) else v)
                for k, v in asdict(t).items()
                if k not in ("exit_reason", "direction")
            },
            "direction": str(t.direction),
            "exit_reason": str(t.exit_reason) if t.exit_reason is not None else None,
            "pnl_dollars": t.pnl_dollars,
            "pnl_r": t.pnl_r,
        }
        for t in result.trades
    ]
    (out_dir / f"{label}_trades.json").write_text(json.dumps(trades, indent=1))

    curve = [
        {"timestamp": ts.isoformat(), "equity": float(eq)} for ts, eq in result.equity_curve.items()
    ]
    (out_dir / f"{label}_equity_curve.json").write_text(json.dumps(curve, indent=1))

    overall = result.overall
    stats = {
        "label": label,
        "config": config,
        "elapsed_seconds": round(elapsed_seconds, 1),
        "initial_equity": result.initial_equity,
        "final_equity": round(result.final_equity, 2),
        "total_return_pct": round(result.total_return_pct * 100, 3),
        "num_trades": overall.num_trades,
        "win_rate_pct": round(overall.win_rate * 100, 2),
        "expectancy_r": round(overall.expectancy_r, 4),
        "profit_factor": round(overall.profit_factor, 3),
        "max_drawdown_pct": round(overall.max_drawdown_pct * 100, 2),
        "sharpe_ratio": round(overall.sharpe_ratio, 3),
        "exit_reason_counts": overall.exit_reason_counts,
        "skipped_entries_due_to_cap": result.skipped_entries_due_to_cap,
        "symbols_traded": len(result.trades_by_symbol),
    }
    (out_dir / f"{label}_stats.json").write_text(json.dumps(stats, indent=1))

    report = phase1_report(result)
    (out_dir / f"{label}_phase1_report.json").write_text(json.dumps(report, indent=1))

    log.info(
        "phase1.persisted",
        label=label,
        out_dir=str(out_dir),
        final_equity=stats["final_equity"],
        num_trades=stats["num_trades"],
        expectancy_r=stats["expectancy_r"],
        target_touch_rate_pct=report.get("target_touch_rate_pct"),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe-file", type=Path, default=UNIVERSE_FILE)
    parser.add_argument("--start", required=True, help="YYYY-MM-DD inclusive")
    parser.add_argument("--end", required=True, help="YYYY-MM-DD exclusive")
    parser.add_argument("--initial-equity", type=float, required=True)
    parser.add_argument("--max-concurrent", type=int, required=True)
    parser.add_argument("--max-position-pct", type=float, required=True)
    parser.add_argument("--r-target", type=float, default=3.0)
    parser.add_argument("--stop-lookback", type=int, default=8)
    parser.add_argument("--sma-fast", type=int, default=21)
    parser.add_argument("--sma-slow", type=int, default=55)
    parser.add_argument("--cooldown-bars", type=int, default=BARS_PER_DAY_30M)
    parser.add_argument("--min-dollar-risk", type=float, default=0.01)
    parser.add_argument("--cache-dir", type=Path, default=SIP_30M_CACHE_DIR)
    parser.add_argument(
        "--direction",
        default="long",
        choices=["long", "short"],
        help="ml30 runs a book one way or the other, never mixed.",
    )
    parser.add_argument("--entry-ranking", default="file", choices=["file", "random"])
    parser.add_argument("--ranking-seed", type=int, default=42)
    parser.add_argument("--label", required=True)
    parser.add_argument("--out-dir", type=Path, default=REPORTS_DIR / "phase1")
    args = parser.parse_args()

    payload = json.loads(args.universe_file.read_text())
    symbols = [str(s).upper() for s in payload["symbols"]]
    start = datetime.strptime(args.start, "%Y-%m-%d").replace(tzinfo=UTC)
    end = datetime.strptime(args.end, "%Y-%m-%d").replace(tzinfo=UTC)

    log.info(
        "phase1.run.start",
        label=args.label,
        direction=args.direction,
        symbols=len(symbols),
        start=args.start,
        end=args.end,
        max_concurrent=args.max_concurrent,
        max_position_pct=args.max_position_pct,
    )

    t0 = time.monotonic()
    bars_by_symbol = load_universe_bars(
        symbols, start, end, args.cache_dir, args.sma_fast, args.sma_slow
    )
    log.info("phase1.data.loaded", symbols_with_data=len(bars_by_symbol))

    coordinator = Coordinator(
        initial_equity=args.initial_equity,
        r_target=args.r_target,
        exit_sma_period=None,
        max_concurrent_positions=args.max_concurrent,
        max_position_pct=args.max_position_pct,
        stop_lookback=args.stop_lookback,
        min_dollar_risk=args.min_dollar_risk,
        sma_fast_period=args.sma_fast,
        sma_slow_period=args.sma_slow,
        cooldown_bars=args.cooldown_bars,
        direction=Direction.SHORT if args.direction == "short" else Direction.LONG,
        entry_ranking=args.entry_ranking,
        ranking_seed=args.ranking_seed,
    )
    result = coordinator.run(bars_by_symbol)
    elapsed = time.monotonic() - t0

    config = {
        "universe_file": str(args.universe_file),
        "symbols_requested": len(symbols),
        "start": args.start,
        "end": args.end,
        "timeframe": "30min",
        "feed": "sip",
        "max_concurrent": args.max_concurrent,
        "max_position_pct": args.max_position_pct,
        "r_target": args.r_target,
        "stop_lookback": args.stop_lookback,
        "sma_fast": args.sma_fast,
        "sma_slow": args.sma_slow,
        "cooldown_bars": args.cooldown_bars,
        "direction": args.direction,
        "min_dollar_risk": args.min_dollar_risk,
        "entry_ranking": args.entry_ranking,
        "ranking_seed": args.ranking_seed,
        "ml30_commit": ml30_commit(),
        "deltaforge_commit": deltaforge_commit(),
    }
    persist(result, args.out_dir, args.label, config, elapsed)


if __name__ == "__main__":
    main()
