"""Build the sub-$150 universe for the options overlay.

Reads ml30's ``config/broad_liquid_universe.json`` (80 liquid names) and keeps
the symbols whose price was under $150 **at the start of the backtest window**
— filtering on today's price would be a look-ahead bias on a 2020-start
backtest. Both the start-date and end-date prices are recorded so the
sensitivity of the cut can be reported.

Side effect (deliberate): fetching the 30-minute SIP bars used to read those
prices populates ``data/cache/sip_30m/`` — the exact cache Phase 1 runs on.

Usage:
    python scripts/build_universe.py --start 2020-01-01 --end 2026-08-01
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime

from alpaca.data.enums import DataFeed
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from structlog import get_logger

from deltaforge.ml30_bridge import AlpacaClientError, AlpacaHistoricalClient, ml30_commit
from deltaforge.settings import (
    ML30_REPO_PATH,
    SIP_30M_CACHE_DIR,
    UNIVERSE_FILE,
    UNIVERSE_PRICE_CAP,
)

log = get_logger(__name__)

TF_30M = TimeFrame(30, TimeFrameUnit.Minute)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", required=True, help="YYYY-MM-DD inclusive")
    parser.add_argument("--end", required=True, help="YYYY-MM-DD exclusive")
    parser.add_argument("--price-cap", type=float, default=UNIVERSE_PRICE_CAP)
    args = parser.parse_args()

    start = datetime.strptime(args.start, "%Y-%m-%d").replace(tzinfo=UTC)
    end = datetime.strptime(args.end, "%Y-%m-%d").replace(tzinfo=UTC)

    source_file = ML30_REPO_PATH / "config" / "broad_liquid_universe.json"
    payload = json.loads(source_file.read_text())
    symbols = [str(s).upper() for s in (payload["symbols"] if isinstance(payload, dict) else payload)]
    log.info("universe.source", file=str(source_file), symbols=len(symbols))

    client = AlpacaHistoricalClient(feed=DataFeed.SIP, cache_dir=SIP_30M_CACHE_DIR)

    rows = []
    for symbol in symbols:
        try:
            bars = client.fetch_bars(symbol, start, end, timeframe=TF_30M, use_cache=True)
        except AlpacaClientError as exc:
            log.warning("universe.fetch_failed", symbol=symbol, error=str(exc)[:200])
            continue
        if bars.empty:
            log.warning("universe.no_data", symbol=symbol)
            continue
        rows.append(
            {
                "symbol": symbol,
                "start_price": round(float(bars["close"].iloc[0]), 2),
                "end_price": round(float(bars["close"].iloc[-1]), 2),
                "first_bar": bars.index[0].isoformat(),
                "last_bar": bars.index[-1].isoformat(),
                "bars": int(len(bars)),
            }
        )
        log.info(
            "universe.symbol",
            symbol=symbol,
            start_price=rows[-1]["start_price"],
            end_price=rows[-1]["end_price"],
            bars=rows[-1]["bars"],
        )

    selected = [r for r in rows if r["start_price"] < args.price_cap]
    # Symbols whose verdict flips if filtered on end-date price instead —
    # the look-ahead sensitivity the report must mention.
    flips = [
        r["symbol"]
        for r in rows
        if (r["start_price"] < args.price_cap) != (r["end_price"] < args.price_cap)
    ]

    out = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "source": str(source_file),
        "ml30_commit": ml30_commit(),
        "filter": {
            "price_cap": args.price_cap,
            "as_of": args.start,
            "basis": "first 30m close on/after start date (start-of-backtest price, not today's)",
        },
        "window": {"start": args.start, "end": args.end},
        "symbols": [r["symbol"] for r in selected],
        "detail": selected,
        "excluded": [r for r in rows if r["start_price"] >= args.price_cap],
        "cap_flips_on_end_price": flips,
    }
    UNIVERSE_FILE.parent.mkdir(parents=True, exist_ok=True)
    UNIVERSE_FILE.write_text(json.dumps(out, indent=1))
    log.info(
        "universe.written",
        file=str(UNIVERSE_FILE),
        selected=len(selected),
        excluded=len(rows) - len(selected),
        flips=flips,
    )


if __name__ == "__main__":
    main()
