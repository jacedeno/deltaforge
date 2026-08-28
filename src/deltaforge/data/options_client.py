"""Historical option bars from Alpaca, with a per-contract parquet cache.

Mirrors the design of ml30's ``AlpacaHistoricalClient`` (parquet + coverage
sidecar, atomic writes) but per OCC contract instead of per stock symbol:

    data/cache/options/{UNDERLYING}/{OCC}_{tf}.parquet  (+ .meta.json)

A contract's life is short (weeks), so unlike the stock client there is no
delta-download logic: the first fetch takes the contract's whole requested
window and the sidecar marks it covered; later calls slice the cache.

Alpaca serves option bars from Feb 2024. Bars are trade-derived — sparse on
illiquid strikes (the spike measured 4-28%% minute coverage, 67-100%% daily)
— so absence of bars is data, not an error: an empty frame is cached too,
and the sidecar prevents re-fetching it.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
from alpaca.data.historical.option import OptionHistoricalDataClient
from alpaca.data.requests import OptionBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from structlog import get_logger

from deltaforge.data.occ import parse_occ_symbol
from deltaforge.settings import OPTIONS_CACHE_DIR, alpaca_keys

log = get_logger(__name__)

TIMEFRAMES: dict[str, TimeFrame] = {
    "1m": TimeFrame(1, TimeFrameUnit.Minute),
    "1d": TimeFrame.Day,
}

BAR_COLUMNS = ("open", "high", "low", "close", "volume", "trade_count", "vwap")


class DeltaForgeOptionsClient:
    def __init__(self, cache_dir: Path | None = None) -> None:
        key, secret = alpaca_keys()
        self._client = OptionHistoricalDataClient(api_key=key, secret_key=secret)
        self._cache_dir = cache_dir or OPTIONS_CACHE_DIR

    # -- cache layout -------------------------------------------------------

    def _paths(self, occ: str, tf_label: str) -> tuple[Path, Path]:
        underlying = parse_occ_symbol(occ)[0]
        base = self._cache_dir / underlying
        return base / f"{occ}_{tf_label}.parquet", base / f"{occ}_{tf_label}.meta.json"

    @staticmethod
    def _covers(meta_path: Path, start: datetime, end: datetime) -> bool:
        if not meta_path.exists():
            return False
        meta = json.loads(meta_path.read_text())
        return (
            datetime.fromisoformat(meta["covered_start"]) <= start
            and datetime.fromisoformat(meta["covered_end"]) >= end
        )

    @staticmethod
    def _atomic_write(df: pd.DataFrame, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f".tmp.{os.getpid()}")
        df.to_parquet(tmp, engine="pyarrow", compression="snappy")
        os.replace(tmp, path)

    # -- fetching -----------------------------------------------------------

    def fetch_bars(
        self,
        occ: str,
        start: datetime,
        end: datetime,
        tf_label: str = "1d",
        use_cache: bool = True,
    ) -> pd.DataFrame:
        """Bars for one contract in [start, end]; empty frame = no trades printed."""
        return self.fetch_bars_multi([occ], start, end, tf_label, use_cache)[occ]

    def fetch_bars_multi(
        self,
        occ_symbols: list[str],
        start: datetime,
        end: datetime,
        tf_label: str = "1d",
        use_cache: bool = True,
    ) -> dict[str, pd.DataFrame]:
        """Batch fetch — one API request for every contract missing cache."""
        if tf_label not in TIMEFRAMES:
            raise ValueError(f"tf_label must be one of {sorted(TIMEFRAMES)}, got {tf_label!r}")
        start, end = _as_utc(start), _as_utc(end)

        out: dict[str, pd.DataFrame] = {}
        missing: list[str] = []
        for occ in occ_symbols:
            pq, meta = self._paths(occ, tf_label)
            if use_cache and self._covers(meta, start, end):
                df = pd.read_parquet(pq) if pq.exists() else _empty_frame()
                out[occ] = df.loc[(df.index >= start) & (df.index <= end)]
            else:
                missing.append(occ)

        if missing:
            log.info("options.fetch", contracts=len(missing), tf=tf_label,
                     start=start.date().isoformat(), end=end.date().isoformat())
            req = OptionBarsRequest(
                symbol_or_symbols=missing,
                timeframe=TIMEFRAMES[tf_label],
                start=start,
                end=end,
            )
            data = self._get_bars_with_retry(req)
            for occ in missing:
                rows = data.get(occ, [])
                df = _to_frame(rows)
                pq, meta = self._paths(occ, tf_label)
                self._atomic_write(df, pq)
                meta.write_text(
                    json.dumps(
                        {
                            "covered_start": start.isoformat(),
                            "covered_end": end.isoformat(),
                            "rows": len(df),
                            "updated_at": datetime.now(UTC).isoformat(timespec="seconds"),
                        }
                    )
                )
                out[occ] = df
        return out


    def _get_bars_with_retry(self, req: OptionBarsRequest, attempts: int = 4):
        """Rate-limit resilience for multi-hour replay runs."""
        import time

        for attempt in range(attempts):
            try:
                return self._client.get_option_bars(req).data
            except Exception as exc:  # noqa: BLE001 — SDK raises generic APIError on 429
                if attempt == attempts - 1:
                    raise
                wait = 30 * (attempt + 1)
                log.warning("options.fetch.retry", error=str(exc)[:150], wait_s=wait)
                time.sleep(wait)
        raise RuntimeError("unreachable")


def _as_utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def _empty_frame() -> pd.DataFrame:
    idx = pd.DatetimeIndex([], tz="UTC", name="timestamp")
    return pd.DataFrame({c: pd.Series(dtype="float64") for c in BAR_COLUMNS}, index=idx)


def _to_frame(rows: list) -> pd.DataFrame:
    if not rows:
        return _empty_frame()
    df = pd.DataFrame(
        {
            "timestamp": [r.timestamp for r in rows],
            "open": [r.open for r in rows],
            "high": [r.high for r in rows],
            "low": [r.low for r in rows],
            "close": [r.close for r in rows],
            "volume": [r.volume for r in rows],
            "trade_count": [r.trade_count for r in rows],
            "vwap": [r.vwap for r in rows],
        }
    ).set_index("timestamp")
    df.index = pd.DatetimeIndex(df.index).tz_convert("UTC")
    df.index.name = "timestamp"
    return df.sort_index()
