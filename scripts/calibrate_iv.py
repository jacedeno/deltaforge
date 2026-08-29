"""Fit the IV model on the 2024-2026 overlap — the M4 gate.

For every trade the real-window run took, backs out the long leg's implied
vol from its signal-day daily close (cached during the run; this script
makes no new API calls) and pairs it with the underlying's 20d realized
vol. Least-squares fit of ``IV = a + b * RV`` is persisted to
``config/iv_calibration.json``, which synthetic-mode runs pick up.

Usage:
    python scripts/calibrate_iv.py \\
        --trades-file reports/overlay/real_window_debit_spread_trades.json
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, time, timedelta
from pathlib import Path

import numpy as np
from alpaca.data.enums import DataFeed
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from structlog import get_logger

from deltaforge.data.occ import parse_occ_symbol
from deltaforge.data.options_client import DeltaForgeOptionsClient
from deltaforge.ml30_bridge import AlpacaHistoricalClient
from deltaforge.pricing.black_scholes import implied_vol
from deltaforge.pricing.iv import IVModel, realized_vol, risk_free
from deltaforge.pricing.marks import _t_years
from deltaforge.settings import CONFIG_DIR, SIP_30M_CACHE_DIR

log = get_logger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trades-file", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=CONFIG_DIR / "iv_calibration.json")
    args = parser.parse_args()

    trades = json.loads(args.trades_file.read_text())
    options = DeltaForgeOptionsClient()
    stocks = AlpacaHistoricalClient(feed=DataFeed.SIP, cache_dir=SIP_30M_CACHE_DIR)
    tf = TimeFrame(30, TimeFrameUnit.Minute)

    daily_by_symbol: dict[str, object] = {}
    pairs: list[tuple[float, float]] = []
    for t in trades:
        signal_ts = datetime.fromisoformat(t["signal_ts"])
        signal_day = signal_ts.date()
        long_leg = next(leg for leg in t["legs"] if leg["side"] == 1)
        occ = long_leg["occ"]
        _, expiry, cp, strike = parse_occ_symbol(occ)

        sym = t["symbol"]
        if sym not in daily_by_symbol:
            bars = stocks.fetch_bars(
                sym,
                datetime(2023, 12, 1, tzinfo=UTC),
                datetime(2026, 8, 1, tzinfo=UTC),
                timeframe=tf,
            )
            daily_by_symbol[sym] = bars["close"].resample("1D").last().dropna()
        daily = daily_by_symbol[sym]

        hist = daily.loc[daily.index.date <= signal_day]
        if len(hist) < 21:
            continue
        rv = realized_vol(hist, window=20)
        spot = float(hist.iloc[-1])

        opt_daily = options.fetch_bars(
            occ,
            datetime.combine(signal_day, time.min, UTC),
            datetime.combine(expiry, time.max, UTC),
            tf_label="1d",
        )
        day_rows = opt_daily.loc[opt_daily.index.date == signal_day]
        if day_rows.empty:
            continue
        close_px = float(day_rows["close"].iloc[-1])
        eod_ts = datetime.combine(signal_day, time(20, 0), UTC)
        iv = implied_vol(close_px, spot, strike, _t_years(eod_ts, expiry),
                         risk_free(signal_day.year), cp)
        if iv is not None and 0.05 < iv < 3.0:
            pairs.append((rv, iv))

    if len(pairs) < 50:
        raise SystemExit(f"only {len(pairs)} usable (rv, iv) pairs — not enough to fit")

    rv_arr = np.array([p[0] for p in pairs])
    iv_arr = np.array([p[1] for p in pairs])
    b, a = np.polyfit(rv_arr, iv_arr, deg=1)
    model = IVModel(a=round(float(a), 4), b=round(float(b), 4), calibrated=True)
    model.save(args.out)

    pred = a + b * rv_arr
    log.info(
        "iv.calibrated",
        pairs=len(pairs),
        a=model.a,
        b=model.b,
        rv_median=round(float(np.median(rv_arr)), 3),
        iv_median=round(float(np.median(iv_arr)), 3),
        rmse=round(float(np.sqrt(((iv_arr - pred) ** 2).mean())), 4),
        corr=round(float(np.corrcoef(rv_arr, iv_arr)[0, 1]), 3),
        out=str(args.out),
    )


if __name__ == "__main__":
    main()
