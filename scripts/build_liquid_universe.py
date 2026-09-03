"""Build the live universe: the N most liquid S&P 500 names, sector-capped.

This replaces the sub-$150 screen for **live trading only**. That screen cut
the 80-name list on each symbol's price at the *start of the 2020 backtest* —
correct then, since filtering on today's price would have been look-ahead on
a 2020-start run, but six years stale as a description of what a $300
position can buy. Sixteen of its 45 survivors now trade above $150, LLY at
$1,148, and a signal on one of them can only ever end in ``over_budget``.

Live there is no look-ahead to avoid: the budget check prices the actual
contract at the actual moment, which is a better filter than any price cap.
So the only screen worth keeping is the one ml30 arrived at independently —
**liquidity, plus sector diversification, and no feature selection**, per its
walk-forward study finding that no stock feature predicts forward P&L.

The method mirrors ml30's ``build_broad_liquid_universe.py`` so the two
universes stay comparable: rank by mean per-bar dollar volume over a recent
window, then walk down that ranking adding names while their sector is under
cap. Only the timeframe differs (30m, DeltaForge's own), which is immaterial
— a ranking by dollar volume is timeframe-agnostic.

The backtest universe (``config/universe_sub150.json``) is deliberately left
alone: every artefact under ``reports/`` was produced on it, and repointing
it would quietly invalidate the numbers in ``docs/BACKTEST.md``.

Usage:
    export ALPACA_API_KEY=... ALPACA_SECRET_KEY=...   # SIP-entitled keys
    python scripts/build_liquid_universe.py --top-n 160
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from alpaca.data.enums import DataFeed
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from structlog import get_logger

from deltaforge.ml30_bridge import AlpacaClientError, AlpacaHistoricalClient, ml30_commit
from deltaforge.settings import (
    LIQUIDITY_CACHE_DIR,
    LIVE_UNIVERSE_FILE,
    ML30_REPO_PATH,
)

log = get_logger(__name__)

TF_30M = TimeFrame(30, TimeFrameUnit.Minute)

# ml30's own defaults, kept so the two universes remain comparable.
DEFAULT_START, DEFAULT_END = "2026-01-01", "2026-06-01"
SECTOR_CAP_MULT = 1.6
MIN_BARS = 200


def select(ranked: list[str], sector_of: dict[str, str], top_n: int) -> tuple[list[str], int]:
    """Walk the liquidity ranking, adding names while their sector is under cap."""
    n_sectors = len({sector_of[t] for t in ranked})
    cap = max(4, math.ceil(top_n / n_sectors * SECTOR_CAP_MULT))
    selected: list[str] = []
    per_sector: Counter = Counter()
    for ticker in ranked:
        sector = sector_of[ticker]
        if per_sector[sector] >= cap:
            continue
        selected.append(ticker)
        per_sector[sector] += 1
        if len(selected) >= top_n:
            break
    return selected, cap


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top-n", type=int, default=160)
    parser.add_argument("--start", default=DEFAULT_START, help="liquidity window start")
    parser.add_argument("--end", default=DEFAULT_END, help="liquidity window end")
    parser.add_argument("--out", default=str(LIVE_UNIVERSE_FILE))
    args = parser.parse_args()

    start = datetime.strptime(args.start, "%Y-%m-%d").replace(tzinfo=UTC)
    end = datetime.strptime(args.end, "%Y-%m-%d").replace(tzinfo=UTC)

    source_file = ML30_REPO_PATH / "config" / "sp500_constituents.json"
    constituents = json.loads(source_file.read_text())["constituents"]
    sector_of = {c["ticker"]: c["sector"] for c in constituents}
    log.info("universe.source", file=str(source_file), constituents=len(constituents))

    client = AlpacaHistoricalClient(feed=DataFeed.SIP, cache_dir=LIQUIDITY_CACHE_DIR)

    liquidity: dict[str, float] = {}
    no_data: list[str] = []
    for ticker in sector_of:
        try:
            bars = client.fetch_bars(ticker, start, end, timeframe=TF_30M, use_cache=True)
        except AlpacaClientError as exc:
            log.warning("universe.fetch_failed", symbol=ticker, error=str(exc)[:120])
            no_data.append(ticker)
            continue
        if bars.empty or len(bars) < MIN_BARS:
            no_data.append(ticker)
            continue
        liquidity[ticker] = float((bars["close"] * bars["volume"]).mean())

    ranked = sorted(liquidity, key=liquidity.get, reverse=True)
    log.info("universe.ranked", ranked=len(ranked), no_data=len(no_data))

    selected, cap = select(ranked, sector_of, args.top_n)
    sector_breakdown = Counter(sector_of[t] for t in selected)

    out = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "source": str(source_file),
        "ml30_commit": ml30_commit(),
        "method": (
            f"top {args.top_n} by mean per-bar dollar volume (30m SIP bars, "
            f"{args.start}..{args.end}), per-sector cap={cap}; no price cap — "
            "the live budget check prices the real contract instead"
        ),
        "window": {"start": args.start, "end": args.end},
        "size": len(selected),
        "sector_breakdown": dict(sorted(sector_breakdown.items())),
        "symbols": selected,
        "detail": [
            {
                "symbol": t,
                "rank": i + 1,
                "sector": sector_of[t],
                "mean_bar_dollar_volume": round(liquidity[t]),
            }
            for i, t in enumerate(selected)
        ],
        "ranked_but_not_selected": [t for t in ranked if t not in set(selected)],
        "no_data": sorted(no_data),
    }

    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=1))
    log.info("universe.written", file=str(path), selected=len(selected), cap=cap)


if __name__ == "__main__":
    main()
