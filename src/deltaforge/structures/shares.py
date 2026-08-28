"""Shares benchmark leg — the same event traded in the underlying.

Not a ``Structure``: no legs, no marks, no chain. The three-way harness
computes it directly from the event's own Phase 1 fills so every event's
shares outcome exists even where an options structure skipped.
"""

from __future__ import annotations

from deltaforge.signals.events import SignalEvent


def shares_pnl(event: SignalEvent, budget: float) -> dict[str, float] | None:
    """Fractional-share P&L of the event with ``budget`` dollars at entry.

    None while the underlying trade never closed inside the window.
    """
    if event.underlying_exit_price is None:
        return None
    shares = budget / event.entry_price
    pnl = (event.underlying_exit_price - event.entry_price) * shares
    return {
        "shares": shares,
        "invested": budget,
        "pnl_dollars": pnl,
        "pnl_pct_of_invested": pnl / budget * 100,
    }
