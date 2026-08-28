"""M2 spike — is Alpaca's historical options data adequate for the overlay?

For a handful of post-Feb-2024 (symbol, date) probes it answers, with data:
  1. Does the trading-API contract listing still return contracts whose
     expiry is long past (the expired-contract lookback question)?
  2. Does OCC-symbol synthesis (Fridays in the DTE window x strike grid)
     find contracts that actually have bars — the fallback discovery path?
  3. How gappy are the bars? Daily-bar coverage per contract, and 1-minute
     bar presence around a specific entry timestamp, ATM vs the wings.

Decision this feeds: keep Alpaca as the data source, or budget for a paid
source with historical NBBO (Polygon / ThetaData).

Usage (after sourcing the Alpaca env):
    python scripts/spike_options_data.py
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, time, timedelta

from alpaca.data.historical.option import OptionHistoricalDataClient
from alpaca.data.historical.stock import StockHistoricalDataClient
from alpaca.data.requests import OptionBarsRequest, StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetOptionContractsRequest
from structlog import get_logger

from deltaforge.data.occ import candidate_strikes, fridays_between
from deltaforge.settings import REPORTS_DIR, alpaca_keys

log = get_logger(__name__)

# Probes: liquid sub-$150 names, dates spread across the real-data window.
PROBES: list[tuple[str, date]] = [
    ("INTC", date(2024, 5, 6)),
    ("BAC", date(2025, 2, 3)),
    ("UBER", date(2026, 3, 2)),
]
DTE_MIN, DTE_MAX = 14, 21
STRIKE_BAND_PCT = 0.10  # +-10% around spot covers 60-65 delta and a 3-6% target


def spot_close(stock: StockHistoricalDataClient, symbol: str, day: date) -> float:
    req = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=TimeFrame.Day,
        start=datetime.combine(day, time.min, UTC),
        end=datetime.combine(day + timedelta(days=4), time.min, UTC),
    )
    bars = stock.get_stock_bars(req).df
    return float(bars["close"].iloc[0])


def probe(
    options: OptionHistoricalDataClient,
    trading: TradingClient,
    stock: StockHistoricalDataClient,
    symbol: str,
    entry_day: date,
) -> dict[str, object]:
    spot = spot_close(stock, symbol, entry_day)
    expiries = fridays_between(entry_day + timedelta(days=DTE_MIN), entry_day + timedelta(days=DTE_MAX))
    strikes = candidate_strikes(spot, spot * (1 - STRIKE_BAND_PCT), spot * (1 + STRIKE_BAND_PCT))
    log.info("spike.probe", symbol=symbol, day=str(entry_day), spot=spot,
             expiries=[str(e) for e in expiries], candidate_strikes=len(strikes))

    # Path 1: trading-API listing for those (long-expired) contracts.
    listed: list[str] = []
    listing_error = None
    try:
        page = trading.get_option_contracts(
            GetOptionContractsRequest(
                underlying_symbols=[symbol],
                expiration_date_gte=expiries[0],
                expiration_date_lte=expiries[-1],
                type="call",
                limit=500,
            )
        )
        listed = [c.symbol for c in (page.option_contracts or [])]
    except Exception as exc:  # noqa: BLE001 — spike records the failure mode itself
        listing_error = f"{type(exc).__name__}: {exc}"[:300]

    # Path 2: OCC synthesis confirmed by daily bars, one bars request per expiry
    # (multi-symbol request covers the whole strike grid at once).
    from deltaforge.data.occ import build_occ_symbol

    synth_results = {}
    for expiry in expiries:
        candidates = [build_occ_symbol(symbol, expiry, "C", k) for k in strikes]
        req = OptionBarsRequest(
            symbol_or_symbols=candidates,
            timeframe=TimeFrame.Day,
            start=datetime.combine(entry_day - timedelta(days=1), time.min, UTC),
            end=datetime.combine(expiry, time.max, UTC),
        )
        data = options.get_option_bars(req).data
        trading_days = max(1, len({d for d in _weekdays(entry_day, expiry)}))
        per_contract = {
            occ: {
                "daily_bars": len(bars),
                "daily_coverage_pct": round(100 * len(bars) / trading_days, 1),
            }
            for occ, bars in data.items()
        }
        synth_results[str(expiry)] = {
            "candidates": len(candidates),
            "with_data": len(per_contract),
            "contracts": per_contract,
        }

    # 1-minute presence around 10:00 ET on entry day for the nearest expiry's
    # ATM strike and the +5% wing (the 3R-target neighbourhood).
    minute_check = {}
    if expiries and synth_results[str(expiries[0])]["with_data"]:
        atm = min(strikes, key=lambda k: abs(k - spot))
        wing = min(strikes, key=lambda k: abs(k - spot * 1.05))
        for label, k in (("atm", atm), ("target_wing", wing)):
            occ = build_occ_symbol(symbol, expiries[0], "C", k)
            req = OptionBarsRequest(
                symbol_or_symbols=occ,
                timeframe=TimeFrame(1, TimeFrameUnit.Minute),
                start=datetime.combine(entry_day, time(13, 30), UTC),  # 09:30 ET
                end=datetime.combine(entry_day, time(21, 0), UTC),
            )
            bars = options.get_option_bars(req).data.get(occ, [])
            minute_check[label] = {"strike": k, "occ": occ, "minute_bars_entry_day": len(bars)}

    return {
        "symbol": symbol,
        "entry_day": str(entry_day),
        "spot": round(spot, 2),
        "listing_api": {
            "returned": len(listed),
            "error": listing_error,
            "sample": listed[:5],
        },
        "occ_synthesis": synth_results,
        "minute_bars": minute_check,
    }


def _weekdays(start: date, end: date):
    d = start
    while d <= end:
        if d.weekday() < 5:
            yield d
        d += timedelta(days=1)


def main() -> None:
    key, secret = alpaca_keys()
    options = OptionHistoricalDataClient(api_key=key, secret_key=secret)
    trading = TradingClient(api_key=key, secret_key=secret, paper=True)
    stock = StockHistoricalDataClient(api_key=key, secret_key=secret)

    results = [probe(options, trading, stock, sym, day) for sym, day in PROBES]

    out_dir = REPORTS_DIR / "spike"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "options_data_spike.json"
    out_file.write_text(json.dumps(results, indent=1))

    for r in results:
        synth_found = sum(e["with_data"] for e in r["occ_synthesis"].values())
        log.info(
            "spike.summary",
            symbol=r["symbol"],
            listing_returned=r["listing_api"]["returned"],
            listing_error=bool(r["listing_api"]["error"]),
            synth_contracts_with_data=synth_found,
            minute_bars=r["minute_bars"],
        )
    log.info("spike.written", file=str(out_file))


if __name__ == "__main__":
    main()
