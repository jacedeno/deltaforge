# Vendored from ml30-sp500-strategy @ c7ad990 (2026-09-02) — see deltaforge/ml30/__init__.py.
# Only the import paths and PROJECT_ROOT were changed.
"""Alpaca Markets data and trading clients.

`AlpacaHistoricalClient` is the only external-I/O surface used by the
Phase 1 backtest engine: it fetches 30-minute bars, caches them to Parquet
under `data/cache/`, applies the regular-trading-hours filter required by
TSD §9.3, and returns DataFrames with the schema fixed in TSD §9.2.

`AlpacaLiveClient` is a stub. It pins down the method shape that the
Phase 2 paper-trading executor will consume so we can write the engine
against a stable interface today; every call body raises NotImplementedError
until Phase 2.

Reference: TSD-MomentumLong-v1.3 §9 (data source), §10 (live execution).
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd
import pandas_market_calendars as mcal
import structlog
from alpaca.data.enums import Adjustment, DataFeed
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

from deltaforge.ml30.settings import Settings
from deltaforge.ml30.settings import settings as default_settings

if TYPE_CHECKING:
    from collections.abc import Iterable

log = structlog.get_logger(__name__)

MARKET_TZ: str = "America/New_York"
NYSE_CALENDAR: str = "NYSE"
RTH_OPEN: tuple[int, int] = (9, 30)
RTH_CLOSE: tuple[int, int] = (16, 0)

BARS_SCHEMA: tuple[str, ...] = (
    "open",
    "high",
    "low",
    "close",
    "volume",
    "trade_count",
    "vwap",
)

META_SUFFIX: str = ".meta.json"
"""Sidecar recording which range was DOWNLOADED, next to each cache parquet.

Coverage cannot be inferred from the data itself. A request starting
2020-01-01 can never be satisfied by inferred bounds, because the first bar
the market ever produced that week is 2020-01-02 — so `min(index) <= start`
is false forever and the same 6.5 years re-download on every single run.
That silently cost hours per study (see docs/DATA-CACHE.md).

The sidecar stores the *requested* window instead, which is the only thing
that answers "have we already asked Alpaca for this?". Caches without a
sidecar fall back to the old inferred-bounds check, so nothing breaks — they
just keep re-downloading until `scripts/audit_cache.py --fix` backfills them.
"""


class AlpacaClientError(RuntimeError):
    """Raised when Alpaca returns an error or the response is malformed."""


class AlpacaHistoricalClient:
    """Fetch and cache historical equity bars from Alpaca.

    The cache is keyed by `{symbol}_{timeframe}.parquet` under
    `settings.paths.data_cache_dir`. Calls to `fetch_bars` are idempotent:
    repeated calls covering an already-cached range hit the cache; partial
    overlaps trigger a delta download that is merged back into the cache.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        feed: DataFeed = DataFeed.IEX,
        cache_dir: Path | None = None,
        adjustment: Adjustment = Adjustment.SPLIT,
    ) -> None:
        self.settings: Settings = settings or default_settings
        if not self.settings.alpaca.has_credentials:
            raise AlpacaClientError(
                "Alpaca credentials missing — set ALPACA_API_KEY and ALPACA_SECRET_KEY in .env"
            )
        self.settings.paths.ensure()
        # IEX is the default for live/recent data (free plan blocks SIP inside the
        # last 15 minutes). SIP *historical* data is served on the free plan and is
        # required before ~2021, where the IEX archive is empty (verified 2026-07-27).
        # A non-default feed must use its own cache_dir — bars from different feeds
        # must never be merged into one parquet series.
        self._feed: DataFeed = feed
        if feed is not DataFeed.IEX and cache_dir is None:
            raise AlpacaClientError(f"feed={feed.value} requires an explicit cache_dir")
        # Alpaca serves RAW (unadjusted) bars by default: a 10:1 split shows up
        # as a -90% overnight "return" and SMA55/21 read it as a crash for the
        # next ~55 bars. SPLIT adjustment is mandatory (see docs/SPLIT-BUG.md).
        # Dividends are deliberately NOT back-adjusted — prices stay the ones
        # that were actually tradeable.
        self._adjustment: Adjustment = adjustment
        self._cache_dir: Path | None = cache_dir
        self._client: StockHistoricalDataClient = StockHistoricalDataClient(
            api_key=self.settings.alpaca.api_key.get_secret_value(),
            secret_key=self.settings.alpaca.secret_key.get_secret_value(),
        )
        self._calendar = mcal.get_calendar(NYSE_CALENDAR)

    def fetch_bars(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        timeframe: TimeFrame | None = None,
        use_cache: bool = True,
        include_extended_hours: bool = False,
    ) -> pd.DataFrame:
        """Return bars for `symbol` between `start` and `end`.

        Both `start` and `end` are interpreted as timezone-aware datetimes;
        naive inputs are assumed UTC.

        ``include_extended_hours`` controls the RTH filter applied before
        return:

          - False (default): keep only bars stamped during NYSE regular
            trading hours (09:30-16:00 ET) — production / canonical
            backtest behaviour
          - True: keep all bars present in the cache, including pre-market
            (04:00-09:30 ET) and after-hours (16:00-20:00 ET). Use only
            for the FC/ETH research sweep — see [[future_sweep_no_crossup]]

        The returned DataFrame has columns matching `BARS_SCHEMA`, a tz-aware
        DatetimeIndex in `America/New_York`, and `df.attrs["symbol"] == symbol`.
        """
        tf = timeframe or TimeFrame(30, TimeFrameUnit.Minute)
        tf_label = self._timeframe_label(tf)
        start_utc = self._to_utc(start)
        end_utc = self._to_utc(end)
        ticker = symbol.strip().upper()

        cache_path = self._cache_path(ticker, tf_label)
        cached = self._load_cache(cache_path) if use_cache else None
        meta = self._load_meta(cache_path) if use_cache else None

        if meta is not None and meta.get("adjustment") != self._adjustment.value:
            # A cache built under a different adjustment is not merely stale,
            # it is a different price series. Refuse it rather than blending.
            log.warning(
                "client.cache.adjustment_mismatch",
                symbol=ticker,
                cached=meta.get("adjustment"),
                wanted=self._adjustment.value,
            )
            cached, meta = None, None

        if cached is not None and self._covers_range(cached, start_utc, end_utc, meta):
            log.info(
                "client.cache.hit",
                symbol=ticker,
                start=start_utc.isoformat(),
                end=end_utc.isoformat(),
                rows=len(cached),
                source="metadata" if meta else "inferred_bounds",
            )
            return self._slice_and_finalize(
                cached, ticker, start_utc, end_utc, include_extended_hours
            )

        log.info(
            "client.cache.miss",
            symbol=ticker,
            start=start_utc.isoformat(),
            end=end_utc.isoformat(),
            had_cache=cached is not None,
            had_meta=meta is not None,
        )
        fetched = self._download(ticker, start_utc, end_utc, tf)

        merged = self._merge(cached, fetched)
        self._save_cache(merged, cache_path)
        self._save_meta(cache_path, ticker, tf_label, start_utc, end_utc, merged, meta)
        log.info(
            "client.download.complete",
            symbol=ticker,
            fetched_rows=len(fetched),
            cache_rows=len(merged),
        )
        return self._slice_and_finalize(merged, ticker, start_utc, end_utc, include_extended_hours)

    def download_history(self, symbol: str, years: int = 3) -> pd.DataFrame:
        """Backfill `years` of 30-minute history for `symbol`."""
        end = datetime.now(UTC)
        start = end - timedelta(days=int(years * 365.25))
        return self.fetch_bars(symbol, start, end, use_cache=True)

    def _cache_path(self, symbol: str, timeframe: str) -> Path:
        root = self._cache_dir or self.settings.paths.data_cache_dir
        return root / f"{symbol}_{timeframe}.parquet"

    def _load_cache(self, path: Path) -> pd.DataFrame | None:
        if not path.exists():
            return None
        try:
            df = pd.read_parquet(path)
        except (OSError, ValueError) as exc:
            log.warning("client.cache.read_failed", path=str(path), error=str(exc))
            return None
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC").tz_convert(MARKET_TZ)
        elif str(df.index.tz) != MARKET_TZ:
            df.index = df.index.tz_convert(MARKET_TZ)
        return df

    def _save_cache(self, df: pd.DataFrame, path: Path) -> None:
        """Write the cache parquet atomically.

        Two processes backtesting the same universe both re-download and both
        rewrite this file. A plain `to_parquet` leaves it truncated for the
        duration of the write, and a concurrent reader gets a 4-byte stub
        instead of a parquet (observed 2026-07-28). Writing to a
        pid-suffixed temp and `os.replace`-ing it makes readers see either the
        old file or the new one, never a partial one.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        try:
            df.to_parquet(tmp, engine="pyarrow", compression="snappy")
            os.replace(tmp, path)
        finally:
            tmp.unlink(missing_ok=True)

    @staticmethod
    def _meta_path(cache_path: Path) -> Path:
        return cache_path.with_name(f"{cache_path.stem}{META_SUFFIX}")

    def _load_meta(self, cache_path: Path) -> dict[str, Any] | None:
        """Read the coverage sidecar, or None when absent/unreadable."""
        path = self._meta_path(cache_path)
        if not path.exists():
            return None
        try:
            meta = json.loads(path.read_text())
        except (OSError, ValueError) as exc:
            log.warning("client.meta.read_failed", path=str(path), error=str(exc))
            return None
        return meta if isinstance(meta, dict) else None

    def _save_meta(
        self,
        cache_path: Path,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
        df: pd.DataFrame,
        previous: dict[str, Any] | None,
    ) -> None:
        """Record the downloaded window, unioned with whatever was covered before.

        The union is only taken when the two windows overlap or touch. Disjoint
        windows are NOT merged: claiming to cover the hole between them would
        silently hand a backtest a range with missing bars, whereas keeping the
        old range merely re-downloads. Redundant work is a safe failure; a
        silent gap in a 6.5-year study is not.
        """
        covered_start, covered_end = start, end
        if previous:
            prev_start = self._parse_ts(previous.get("covered_start"))
            prev_end = self._parse_ts(previous.get("covered_end"))
            if prev_start and prev_end:
                if start <= prev_end and end >= prev_start:
                    covered_start = min(start, prev_start)
                    covered_end = max(end, prev_end)
                else:
                    log.warning(
                        "client.meta.disjoint_range",
                        symbol=symbol,
                        kept=f"{prev_start.isoformat()}..{prev_end.isoformat()}",
                        requested=f"{start.isoformat()}..{end.isoformat()}",
                    )
                    covered_start, covered_end = prev_start, prev_end

        payload = {
            "symbol": symbol,
            "timeframe": timeframe,
            "feed": self._feed.value,
            "adjustment": self._adjustment.value,
            "covered_start": covered_start.isoformat(),
            "covered_end": covered_end.isoformat(),
            "rows": len(df),
            "data_start": df.index.min().isoformat() if len(df) else None,
            "data_end": df.index.max().isoformat() if len(df) else None,
            "updated_at": datetime.now(UTC).isoformat(),
        }
        path = self._meta_path(cache_path)
        tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        try:
            tmp.write_text(json.dumps(payload, indent=1))
            os.replace(tmp, path)
        except OSError as exc:  # a missing sidecar only costs a re-download
            log.warning("client.meta.write_failed", path=str(path), error=str(exc))
        finally:
            tmp.unlink(missing_ok=True)

    @staticmethod
    def _parse_ts(value: Any) -> datetime | None:
        if not isinstance(value, str):
            return None
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)

    def _download(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        timeframe: TimeFrame,
    ) -> pd.DataFrame:
        request = StockBarsRequest(
            symbol_or_symbols=[symbol],
            timeframe=timeframe,
            start=start,
            end=end,
            feed=self._feed,
            adjustment=self._adjustment,
        )
        try:
            response = self._client.get_stock_bars(request)
        except Exception as exc:
            raise AlpacaClientError(f"Alpaca get_stock_bars failed for {symbol}: {exc}") from exc

        if not hasattr(response, "df"):
            raise AlpacaClientError(
                f"Unexpected Alpaca response shape for {symbol}: {type(response).__name__}"
            )
        df: pd.DataFrame = response.df
        if df is None or df.empty:
            return self._empty_frame()

        if isinstance(df.index, pd.MultiIndex):
            df = df.xs(symbol, level=0)

        df = (
            df.tz_convert(MARKET_TZ)
            if df.index.tz is not None
            else df.tz_localize("UTC").tz_convert(MARKET_TZ)
        )

        return self._enforce_schema(df)

    def _merge(self, cached: pd.DataFrame | None, fresh: pd.DataFrame) -> pd.DataFrame:
        if cached is None or cached.empty:
            return fresh.sort_index()
        if fresh.empty:
            return cached.sort_index()
        combined = pd.concat([cached, fresh])
        combined = combined[~combined.index.duplicated(keep="last")].sort_index()
        return combined

    def _slice_and_finalize(
        self,
        df: pd.DataFrame,
        symbol: str,
        start: datetime,
        end: datetime,
        include_extended_hours: bool = False,
    ) -> pd.DataFrame:
        start_local = pd.Timestamp(start).tz_convert(MARKET_TZ)
        end_local = pd.Timestamp(end).tz_convert(MARKET_TZ)
        sliced = df.loc[(df.index >= start_local) & (df.index < end_local)].copy()
        if not include_extended_hours:
            sliced = self._filter_rth(sliced)
        sliced.attrs["symbol"] = symbol
        return sliced

    def _filter_rth(self, df: pd.DataFrame) -> pd.DataFrame:
        """Keep only bars stamped during NYSE regular trading hours.

        Honours holidays and early closes by intersecting each bar's timestamp
        with the official NYSE schedule from `pandas_market_calendars`.
        """
        if df.empty:
            return df

        first = df.index.min().date()
        last = df.index.max().date()
        schedule = self._calendar.schedule(start_date=first, end_date=last)
        if schedule.empty:
            return df.iloc[0:0]

        opens = schedule["market_open"].dt.tz_convert(MARKET_TZ)
        closes = schedule["market_close"].dt.tz_convert(MARKET_TZ)

        mask = pd.Series(False, index=df.index)
        for day_open, day_close in zip(opens, closes, strict=True):
            mask |= (df.index >= day_open) & (df.index < day_close)
        return df.loc[mask]

    @classmethod
    def _covers_range(
        cls,
        df: pd.DataFrame,
        start: datetime,
        end: datetime,
        meta: dict[str, Any] | None = None,
    ) -> bool:
        """Is `[start, end]` already downloaded?

        Prefers the sidecar's recorded *requested* window. Falls back to the
        data's own bounds only when no sidecar exists — that fallback is the
        historical behaviour and is wrong in one specific, expensive way: a
        request whose start precedes the symbol's first-ever bar (a weekend,
        a holiday, or an IPO date) can never be satisfied, so it re-downloads
        forever. See META_SUFFIX and docs/DATA-CACHE.md.
        """
        if df.empty:
            return False
        if meta is not None:
            covered_start = cls._parse_ts(meta.get("covered_start"))
            covered_end = cls._parse_ts(meta.get("covered_end"))
            if covered_start and covered_end:
                return bool(covered_start <= start and covered_end >= end)
        start_local = pd.Timestamp(start).tz_convert(MARKET_TZ)
        end_local = pd.Timestamp(end).tz_convert(MARKET_TZ)
        return bool(df.index.min() <= start_local and df.index.max() >= end_local)

    @staticmethod
    def _to_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @staticmethod
    def _timeframe_label(tf: TimeFrame) -> str:
        unit_map = {
            TimeFrameUnit.Minute: "m",
            TimeFrameUnit.Hour: "h",
            TimeFrameUnit.Day: "d",
            TimeFrameUnit.Week: "w",
            TimeFrameUnit.Month: "mo",
        }
        return f"{tf.amount_value}{unit_map.get(tf.unit_value, str(tf.unit_value))}"

    @staticmethod
    def _enforce_schema(df: pd.DataFrame) -> pd.DataFrame:
        missing = [col for col in BARS_SCHEMA if col not in df.columns]
        if missing:
            raise AlpacaClientError(f"Alpaca response missing required columns: {missing}")
        out = df[list(BARS_SCHEMA)].astype(
            {
                "open": "float64",
                "high": "float64",
                "low": "float64",
                "close": "float64",
                "volume": "int64",
                "trade_count": "int64",
                "vwap": "float64",
            }
        )
        out.index.name = "timestamp"
        return out

    @staticmethod
    def _empty_frame() -> pd.DataFrame:
        idx = pd.DatetimeIndex([], tz=MARKET_TZ, name="timestamp")
        return pd.DataFrame(
            {
                "open": pd.Series(dtype="float64"),
                "high": pd.Series(dtype="float64"),
                "low": pd.Series(dtype="float64"),
                "close": pd.Series(dtype="float64"),
                "volume": pd.Series(dtype="int64"),
                "trade_count": pd.Series(dtype="int64"),
                "vwap": pd.Series(dtype="float64"),
            },
            index=idx,
        )


class AlpacaLiveClient:
    """Stub for Phase 2 live trading. All methods raise NotImplementedError.

    The signatures are intentionally pinned so the backtest engine can be
    written against the same interface the live executor will expose.
    """

    _PHASE2_MSG = "AlpacaLiveClient is a Phase 2 stub — not implemented yet"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings: Settings = settings or default_settings

    def subscribe_bars(self, symbols: Iterable[str]) -> None:
        raise NotImplementedError(self._PHASE2_MSG)

    def get_account(self) -> Any:
        raise NotImplementedError(self._PHASE2_MSG)

    def get_positions(self) -> list[Any]:
        raise NotImplementedError(self._PHASE2_MSG)

    def submit_market_order(self, symbol: str, qty: float, side: str) -> Any:
        raise NotImplementedError(self._PHASE2_MSG)

    def submit_bracket_order(
        self,
        symbol: str,
        qty: float,
        side: str,
        stop_price: float,
        take_profit_price: float,
    ) -> Any:
        raise NotImplementedError(self._PHASE2_MSG)

    def cancel_order(self, order_id: str) -> None:
        raise NotImplementedError(self._PHASE2_MSG)
