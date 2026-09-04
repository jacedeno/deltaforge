# Vendored from ml30-sp500-strategy @ c7ad990 (2026-09-02) — see deltaforge/ml30/__init__.py.
# Only the import paths and PROJECT_ROOT were changed.
"""Trade direction — the one axis that mirrors the whole strategy.

The momentum-bracket logic is directional but otherwise symmetric: a short
is the same machine with every comparison flipped. Rather than fork the
modules into long/short copies (which drift apart the moment one side gets
a fix), each piece of pure logic takes a `Direction` and mirrors itself.

What flips, per module:

    entry     close ABOVE both SMAs on a bullish bar, crossing UP
              -> close BELOW both SMAs on a bearish bar, crossing DOWN
    sizing    stop = LOWEST LOW of the prior N bars (below entry)
              -> stop = HIGHEST HIGH of the prior N bars (above entry)
    exit      stop hit when low <= stop, target when high >= target
              -> stop hit when high >= stop, target when low <= target
    trade     pnl = (exit - entry) * shares
              -> pnl = (entry - exit) * shares

What does NOT flip: same-bar precedence (STOP > TARGET > SMA_EXIT), the
frozen-stop rule, the one-position-per-symbol rule, and R-multiple
semantics — a -1R loss is a -1R loss in either direction.

`sign` exists so P&L and R-multiples stay single expressions rather than
branches: `(exit - entry) * sign` is the realised move in the trade's
favour for both directions.
"""

from __future__ import annotations

from enum import StrEnum


class Direction(StrEnum):
    """Which way a position is taken."""

    LONG = "LONG"
    SHORT = "SHORT"

    @property
    def sign(self) -> int:
        """+1 for long, -1 for short.

        Multiply a raw price move `(exit - entry)` by this to get the move
        in the position's favour.
        """
        return 1 if self is Direction.LONG else -1

    @property
    def is_long(self) -> bool:
        return self is Direction.LONG

    @property
    def is_short(self) -> bool:
        return self is Direction.SHORT
