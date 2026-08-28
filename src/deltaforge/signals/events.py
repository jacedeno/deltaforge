"""Signal events — the contract between Phase 1 (underlying) and Phase 2 (options).

A ``SignalEvent`` is one uncapped ML30 signal with the three levels the
options overlay anchors to (entry, frozen stop, 3R target), plus how the
*underlying* trade actually resolved in the Phase 1 replay. Phase 2 replays
these events instead of re-running signal logic, so every structure
(debit spread / long call / shares) sees the identical signal stream.

The source of truth is the ``<label>_trades.json`` artifact written by
``scripts/run_phase1_underlying.py`` (same schema as ml30's
``backtest_topn_portfolio.py`` output).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True, slots=True)
class SignalEvent:
    symbol: str
    signal_ts: datetime
    entry_price: float
    stop: float
    target: float
    risk_per_share: float
    # How the underlying trade resolved in the Phase 1 replay.
    underlying_exit_ts: datetime | None
    underlying_exit_price: float | None
    underlying_exit_reason: str | None

    @property
    def target_distance_pct(self) -> float:
        """Entry→target distance as a fraction of entry price."""
        return (self.target - self.entry_price) / self.entry_price

    @property
    def stop_distance_pct(self) -> float:
        """Entry→stop distance as a fraction of entry price (positive)."""
        return (self.entry_price - self.stop) / self.entry_price


def load_events_from_trades_json(path: Path) -> list[SignalEvent]:
    """Parse a Phase 1 ``<label>_trades.json`` into the canonical event list."""
    records = json.loads(Path(path).read_text())
    events = []
    for r in records:
        events.append(
            SignalEvent(
                symbol=r["symbol"],
                signal_ts=datetime.fromisoformat(r["entry_time"]),
                entry_price=float(r["entry_price"]),
                stop=float(r["initial_stop"]),
                target=float(r["target_price"]),
                risk_per_share=float(r["risk_per_share"]),
                underlying_exit_ts=(
                    datetime.fromisoformat(r["exit_time"]) if r.get("exit_time") else None
                ),
                underlying_exit_price=(
                    float(r["exit_price"]) if r.get("exit_price") is not None else None
                ),
                underlying_exit_reason=r.get("exit_reason"),
            )
        )
    events.sort(key=lambda e: (e.signal_ts, e.symbol))
    return events
