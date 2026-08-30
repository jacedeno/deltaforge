"""Append-only event log — the dashboard's brain feed.

One JSON object per line, newest last. The dashboard reads the tail and
narrates each entry in plain English, so the field names here are the
vocabulary of that narration: keep `kind` stable, put everything else in
`data`.

Also maintains the heartbeat file the status strip reads to decide whether
the bot is alive, degraded, or down.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

# Event kinds the dashboard knows how to narrate.
SCAN = "scan"                       # a 30m bar closed and the universe was scanned
SIGNAL = "signal"                   # ML30 entry conditions met on a symbol
SKIP = "skip"                       # signal found but not taken (why in data.reason)
ORDER_OPEN = "order_open"           # entry limit order submitted
ORDER_REPRICE = "order_reprice"     # unfilled entry chased toward the ask
ORDER_FILLED = "order_filled"
ORDER_CANCELLED = "order_cancelled"
EXIT_SIGNAL = "exit_signal"         # underlying touched stop/target, or DTE clock
ORDER_CLOSE = "order_close"
POSITION_CLOSED = "position_closed"
ERROR = "error"


class EventLog:
    def __init__(self, path: Path, heartbeat_path: Path) -> None:
        self.path = Path(path)
        self.heartbeat_path = Path(heartbeat_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
        self._started = datetime.now(UTC)
        self._failures = 0

    def emit(self, kind: str, **data) -> None:
        line = json.dumps(
            {"ts": datetime.now(UTC).isoformat(timespec="seconds"), "kind": kind, "data": data}
        )
        with self.path.open("a") as fh:
            fh.write(line + "\n")

    def beat(self, *, ok: bool, last_scan: str | None = None, note: str = "") -> None:
        """Refresh the heartbeat. Written atomically — the dashboard polls it."""
        self._failures = 0 if ok else self._failures + 1
        payload = {
            "ts": datetime.now(UTC).isoformat(timespec="seconds"),
            "started_at": self._started.isoformat(timespec="seconds"),
            "uptime_seconds": int((datetime.now(UTC) - self._started).total_seconds()),
            "consecutive_failures": self._failures,
            "last_scan": last_scan,
            "note": note,
        }
        tmp = self.heartbeat_path.with_suffix(f".tmp.{os.getpid()}")
        tmp.write_text(json.dumps(payload, indent=1))
        os.replace(tmp, self.heartbeat_path)
