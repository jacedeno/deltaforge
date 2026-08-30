"""The trade journal — the contract between the bot and the dashboard.

One row per position, carrying both what the *signal* said and what the
*broker* did, because the point of the paper phase is to compare them. The
dashboard opens this file read-only; the bot is its only writer.

Schema notes:
- Prices are per share (option premium), not per contract. Dollar amounts
  (`debit`, `fees`, `pnl`) are totals for the position.
- `limit_price` is what the bot asked for; `entry_fill` is what it got.
  Keeping both is what makes the fill assumption in the backtest checkable
  after the fact.
- The underlying levels (`entry_price`, `stop_price`, `target_price`) are
  frozen at signal time and never updated — the exits are driven off them,
  so a later revision would make the record unreadable.
- Timestamps are ISO-8601 with timezone, in UTC.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    status            TEXT    NOT NULL,   -- pending | open | closed | aborted
    symbol            TEXT    NOT NULL,   -- underlying
    occ               TEXT    NOT NULL,   -- option contract
    strike            REAL    NOT NULL,
    expiry            TEXT    NOT NULL,   -- YYYY-MM-DD
    dte_at_entry      INTEGER NOT NULL,
    delta_at_entry    REAL,

    signal_ts         TEXT    NOT NULL,   -- 30m bar close that triggered
    entry_price       REAL    NOT NULL,   -- underlying at signal
    stop_price        REAL    NOT NULL,   -- frozen 8-bar pivot low
    target_price      REAL    NOT NULL,   -- entry + 3R
    risk_per_share    REAL    NOT NULL,

    contracts         INTEGER NOT NULL,
    limit_price       REAL,               -- premium the bot asked for
    entry_fill        REAL,               -- premium it got
    entry_ts          TEXT,
    entry_order_id    TEXT,
    debit             REAL,               -- total $ paid
    fees              REAL    NOT NULL DEFAULT 0,

    exit_ts           TEXT,
    exit_limit        REAL,
    exit_fill         REAL,
    exit_order_id     TEXT,
    exit_reason       TEXT,               -- stop | target | dte | manual
    underlying_at_exit REAL,
    pnl               REAL,

    created_at        TEXT    NOT NULL,
    updated_at        TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);
CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
CREATE INDEX IF NOT EXISTS idx_trades_signal_ts ON trades(signal_ts);

-- One row per broker fill, so a partially filled or repriced order leaves a
-- trail the dashboard can show under the trade it belongs to.
CREATE TABLE IF NOT EXISTS fills (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id    INTEGER NOT NULL REFERENCES trades(id),
    order_id    TEXT    NOT NULL,
    side        TEXT    NOT NULL,   -- buy | sell
    qty         INTEGER NOT NULL,
    price       REAL    NOT NULL,
    filled_at   TEXT    NOT NULL,
    leg         TEXT    NOT NULL    -- entry | exit
);
CREATE INDEX IF NOT EXISTS idx_fills_trade ON fills(trade_id);
"""


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass(slots=True)
class TradeRecord:
    symbol: str
    occ: str
    strike: float
    expiry: str
    dte_at_entry: int
    signal_ts: str
    entry_price: float
    stop_price: float
    target_price: float
    risk_per_share: float
    contracts: int
    delta_at_entry: float | None = None
    limit_price: float | None = None
    id: int | None = None
    status: str = "pending"
    fees: float = 0.0
    extra: dict = field(default_factory=dict)


class Journal:
    """Single-writer SQLite journal. The dashboard opens the same file read-only."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        # WAL so the dashboard can read while the bot writes.
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(SCHEMA)

    def close(self) -> None:
        self._conn.close()

    # -- writes -------------------------------------------------------------

    def open_pending(self, t: TradeRecord) -> int:
        ts = now_iso()
        cur = self._conn.execute(
            """INSERT INTO trades (status, symbol, occ, strike, expiry, dte_at_entry,
                   delta_at_entry, signal_ts, entry_price, stop_price, target_price,
                   risk_per_share, contracts, limit_price, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                "pending", t.symbol, t.occ, t.strike, t.expiry, t.dte_at_entry,
                t.delta_at_entry, t.signal_ts, t.entry_price, t.stop_price,
                t.target_price, t.risk_per_share, t.contracts, t.limit_price, ts, ts,
            ),
        )
        return int(cur.lastrowid)

    def mark_filled(
        self, trade_id: int, fill: float, order_id: str, fees: float, filled_at: str
    ) -> None:
        row = self._conn.execute(
            "SELECT contracts FROM trades WHERE id = ?", (trade_id,)
        ).fetchone()
        debit = fill * 100 * int(row["contracts"])
        self._conn.execute(
            """UPDATE trades SET status='open', entry_fill=?, entry_ts=?, entry_order_id=?,
                   debit=?, fees=?, updated_at=? WHERE id=?""",
            (fill, filled_at, order_id, debit, fees, now_iso(), trade_id),
        )

    def mark_closed(
        self,
        trade_id: int,
        exit_fill: float,
        order_id: str,
        reason: str,
        fees_total: float,
        underlying: float | None,
        closed_at: str,
    ) -> None:
        row = self._conn.execute(
            "SELECT contracts, entry_fill FROM trades WHERE id=?", (trade_id,)
        ).fetchone()
        pnl = (exit_fill - float(row["entry_fill"])) * 100 * int(row["contracts"]) - fees_total
        self._conn.execute(
            """UPDATE trades SET status='closed', exit_fill=?, exit_ts=?, exit_order_id=?,
                   exit_reason=?, fees=?, underlying_at_exit=?, pnl=?, updated_at=?
               WHERE id=?""",
            (exit_fill, closed_at, order_id, reason, fees_total, underlying, pnl,
             now_iso(), trade_id),
        )

    def abort(self, trade_id: int, why: str) -> None:
        """An entry that never filled — recorded, not silently dropped."""
        self._conn.execute(
            "UPDATE trades SET status='aborted', exit_reason=?, updated_at=? WHERE id=?",
            (why, now_iso(), trade_id),
        )

    def set_exit_limit(self, trade_id: int, limit: float) -> None:
        self._conn.execute(
            "UPDATE trades SET exit_limit=?, updated_at=? WHERE id=?",
            (limit, now_iso(), trade_id),
        )

    def add_fill(
        self, trade_id: int, order_id: str, side: str, qty: int, price: float,
        filled_at: str, leg: str,
    ) -> None:
        self._conn.execute(
            """INSERT INTO fills (trade_id, order_id, side, qty, price, filled_at, leg)
               VALUES (?,?,?,?,?,?,?)""",
            (trade_id, order_id, side, qty, price, filled_at, leg),
        )

    # -- reads --------------------------------------------------------------

    def open_trades(self) -> list[sqlite3.Row]:
        return list(
            self._conn.execute("SELECT * FROM trades WHERE status IN ('pending','open')")
        )

    def open_symbols(self) -> set[str]:
        return {r["symbol"] for r in self.open_trades()}

    def deployed_debit(self) -> float:
        row = self._conn.execute(
            "SELECT COALESCE(SUM(debit),0) AS d FROM trades WHERE status='open'"
        ).fetchone()
        return float(row["d"])
