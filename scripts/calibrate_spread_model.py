"""Fit the bid-ask width model from captured chain snapshots.

Least-squares fit of ``half_spread = a + b * mid`` over every snapshot row
with a sane quote (bid > 0, ask > bid), then persists the coefficients to
``config/spread_calibration.json`` — which ``backtest_overlay.py`` picks up
automatically on its next run.

Usage:
    python scripts/calibrate_spread_model.py
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from structlog import get_logger

from deltaforge.pricing.spreads import SpreadWidthModel
from deltaforge.settings import CONFIG_DIR, PROJECT_ROOT

log = get_logger(__name__)

SNAPSHOT_DIR = PROJECT_ROOT / "data" / "snapshots"
OUT_FILE = CONFIG_DIR / "spread_calibration.json"


def main() -> None:
    files = sorted(SNAPSHOT_DIR.glob("*.parquet"))
    if not files:
        raise SystemExit(f"no snapshots in {SNAPSHOT_DIR} — run capture_chain_snapshots.py first")
    df = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    df = df[(df["bid"] > 0) & (df["ask"] > df["bid"])]
    if len(df) < 100:
        raise SystemExit(f"only {len(df)} usable quotes — capture more days first")

    mid = (df["bid"] + df["ask"]) / 2
    half = (df["ask"] - df["bid"]) / 2

    b, a = np.polyfit(mid, half, deg=1)
    floor = float(max(0.005, np.percentile(half, 5)))
    model = SpreadWidthModel(a=round(float(a), 4), b=round(float(b), 4),
                             floor=round(floor, 4), calibrated=True)
    model.save(OUT_FILE)

    resid = half - (a + b * mid)
    log.info(
        "spread.calibrated",
        rows=len(df),
        days=len(files),
        a=model.a,
        b=model.b,
        floor=model.floor,
        rmse=round(float(np.sqrt((resid**2).mean())), 4),
        out=str(OUT_FILE),
    )


if __name__ == "__main__":
    main()
