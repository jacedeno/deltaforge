"""Overlay metrics — ml30's stats plus the numbers ANALYSIS.md left open.

Headliners beyond the usual: measured loss-at-stop as % of debit (the
"−40 to −60%, needs measuring, not assuming" number), fee drag, % of
theoretical max captured on target exits, skip rates by reason, and the
mark-source mix (how much of the result rests on synthetic pricing).
"""

from __future__ import annotations

from collections import Counter

import numpy as np

from deltaforge.engine.coordinator import PortfolioResult
from deltaforge.engine.trade import EXIT_STOP, EXIT_TARGET, OptionTrade
from deltaforge.structures.base import CONTRACT_MULTIPLIER, Skip


def _pct(values: list[float], q: float) -> float:
    return round(float(np.percentile(values, q)), 2)


def trade_stats(trades: list[OptionTrade], skips: list[Skip]) -> dict[str, object]:
    closed = [t for t in trades if not t.is_open]
    out: dict[str, object] = {
        "events_traded": len(closed),
        "events_skipped": len(skips),
        "skip_reasons": dict(Counter(s.reason for s in skips)),
    }
    if not closed:
        return out

    pnl_pct = [t.pnl_pct_of_debit for t in closed]
    pnl_usd = [t.pnl_dollars for t in closed]
    wins = [p for p in pnl_usd if p > 0]
    losses = [-p for p in pnl_usd if p < 0]
    gross_gains = sum(wins)

    stops = [t for t in closed if t.exit_reason == EXIT_STOP]
    targets = [t for t in closed if t.exit_reason == EXIT_TARGET]

    out.update(
        {
            "win_rate_pct": round(100 * len(wins) / len(closed), 2),
            "total_pnl_dollars": round(sum(pnl_usd), 2),
            "avg_pnl_pct_of_debit": round(float(np.mean(pnl_pct)), 2),
            "median_pnl_pct_of_debit": _pct(pnl_pct, 50),
            "profit_factor": round(sum(wins) / sum(losses), 3) if losses else float("inf"),
            "avg_debit_dollars": round(float(np.mean([t.debit_dollars for t in closed])), 2),
            "total_fees_dollars": round(sum(t.total_fees for t in closed), 2),
            "fee_drag_pct_of_gross_gains": (
                round(100 * sum(t.total_fees for t in closed) / gross_gains, 2)
                if gross_gains
                else None
            ),
            "exit_reason_counts": dict(Counter(t.exit_reason for t in closed)),
        }
    )

    if stops:
        stop_pct = [t.pnl_pct_of_debit for t in stops]
        out["loss_at_stop_pct_of_debit"] = {
            "mean": round(float(np.mean(stop_pct)), 2),
            "median": _pct(stop_pct, 50),
            "p10": _pct(stop_pct, 10),
            "p90": _pct(stop_pct, 90),
        }

    if targets:
        out["avg_pnl_pct_of_debit_at_target"] = round(
            float(np.mean([t.pnl_pct_of_debit for t in targets])), 2
        )
        # % of theoretical max captured — only defined for width-capped spreads.
        captures = []
        for t in targets:
            if len(t.position.legs) == 2:
                width = abs(t.position.legs[1].strike - t.position.legs[0].strike)
                max_gain = (width - t.position.debit_per_share) * CONTRACT_MULTIPLIER
                if max_gain > 0:
                    captures.append(
                        t.pnl_dollars / (max_gain * t.position.contracts) * 100
                    )
        if captures:
            out["pct_of_max_captured_at_target"] = round(float(np.mean(captures)), 2)

    sources = Counter(s for t in closed for s in (*t.entry_mark_sources, *t.exit_mark_sources))
    total_marks = sum(sources.values())
    out["mark_source_mix_pct"] = {
        k: round(100 * v / total_marks, 1) for k, v in sources.most_common()
    }
    return out


def portfolio_stats(result: PortfolioResult) -> dict[str, object]:
    eq = [e for _, e in result.equity_curve] or [result.initial_equity]
    peak = np.maximum.accumulate([result.initial_equity, *eq])
    dd = (np.array([result.initial_equity, *eq]) - peak) / peak
    return {
        "initial_equity": result.initial_equity,
        "final_equity": round(result.final_equity, 2),
        "total_return_pct": round(
            100 * (result.final_equity / result.initial_equity - 1), 2
        ),
        "max_drawdown_pct": round(float(dd.min() * 100), 2),
        "trades_taken": len(result.trades),
        "skipped_by_cap": result.skipped_by_cap,
        "skipped_by_budget": result.skipped_by_budget,
    }
