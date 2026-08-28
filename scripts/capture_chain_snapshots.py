"""Capture live option-chain snapshots for the universe — bid/ask + greeks.

Alpaca keeps no quote history, so this is how DeltaForge builds its own:
each run appends today's chain snapshots (real bid/ask, IV, delta) to
``data/snapshots/YYYY-MM-DD.parquet``. Two consumers:
  - ``scripts/calibrate_spread_model.py`` fits the bid-ask width model, and
  - the paper-trading phase validates modeled fills against reality.

Run daily during market hours (herdr job or cron). Idempotent per day —
re-running overwrites today's file.

Usage (after sourcing the Alpaca env):
    python scripts/capture_chain_snapshots.py
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pandas as pd
from alpaca.data.historical.option import OptionHistoricalDataClient
from alpaca.data.requests import OptionChainRequest
from structlog import get_logger

from deltaforge.settings import PROJECT_ROOT, UNIVERSE_FILE, alpaca_keys

log = get_logger(__name__)

SNAPSHOT_DIR = PROJECT_ROOT / "data" / "snapshots"
MAX_DTE = 45
STRIKE_BAND = 0.15


def main() -> None:
    key, secret = alpaca_keys()
    client = OptionHistoricalDataClient(api_key=key, secret_key=secret)
    symbols = json.loads(UNIVERSE_FILE.read_text())["symbols"]
    now = datetime.now(UTC)

    rows = []
    for symbol in symbols:
        try:
            chain = client.get_option_chain(
                OptionChainRequest(
                    underlying_symbol=symbol,
                    type="call",
                    expiration_date_lte=(now + timedelta(days=MAX_DTE)).date(),
                )
            )
        except Exception as exc:  # noqa: BLE001 — one symbol must not kill the capture
            log.warning("snapshot.fetch_failed", symbol=symbol, error=str(exc)[:200])
            continue
        for occ, snap in chain.items():
            q = snap.latest_quote
            if q is None or q.bid_price is None or q.ask_price is None:
                continue
            g = snap.greeks
            rows.append(
                {
                    "captured_at": now,
                    "underlying": symbol,
                    "occ": occ,
                    "bid": float(q.bid_price),
                    "ask": float(q.ask_price),
                    "iv": float(snap.implied_volatility) if snap.implied_volatility else None,
                    "delta": float(g.delta) if g and g.delta is not None else None,
                }
            )
        log.info("snapshot.symbol", symbol=symbol, contracts=len(rows))

    if not rows:
        raise SystemExit("no snapshots captured — market closed or auth problem?")

    df = pd.DataFrame(rows)
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    out = SNAPSHOT_DIR / f"{now.date().isoformat()}.parquet"
    df.to_parquet(out, engine="pyarrow", compression="snappy")
    log.info("snapshot.written", file=str(out), rows=len(df))


if __name__ == "__main__":
    main()
