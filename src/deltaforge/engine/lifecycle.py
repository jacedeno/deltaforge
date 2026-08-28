"""Per-trade lifecycle replay.

ml30's philosophy carried over: the *underlying's* levels drive every exit —
options are only the P&L instrument. Walking the underlying 30m bars from
entry, first touch wins with ml30's same-bar precedence (STOP > TARGET),
plus the overlay's clock: on the first session where DTE <= ``dte_exit_days``
the position closes at that day's last bar regardless.

Exit pricing: legs are marked at the trigger bar's timestamp with spot at
the touched level itself (stop or target) — the "close when touched" rule.
``next_bar_exit=True`` prices at the *following* bar's close instead: the
pessimism flag for manual execution that can't watch every bar (and the
options analogue of ml30's measured −1.315R stop-fill reality).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Callable

import pandas as pd

from deltaforge.engine.trade import (
    EXIT_DTE,
    EXIT_STOP,
    EXIT_TARGET,
    EXIT_WINDOW_END,
    OptionTrade,
)
from deltaforge.pricing.fees import FeeSchedule
from deltaforge.pricing.fills import FillModel
from deltaforge.pricing.marks import MarkEngine
from deltaforge.signals.events import SignalEvent
from deltaforge.structures.base import Position


def replay_trade(
    event: SignalEvent,
    position: Position,
    bars_30m: pd.DataFrame,
    mark_engine: MarkEngine,
    fills: FillModel,
    fees: FeeSchedule,
    rv: float,
    spot_at: Callable | None = None,
    dte_exit_days: int = 5,
    next_bar_exit: bool = False,
) -> OptionTrade:
    trade = OptionTrade(symbol=event.symbol, signal_ts=event.signal_ts, position=position)
    trade.underlying_exit_reason = event.underlying_exit_reason

    life = bars_30m.loc[bars_30m.index > event.signal_ts]
    expiry = position.expiry
    dte_cutoff: date = expiry - timedelta(days=dte_exit_days)

    trigger_idx: int | None = None
    reason: str | None = None
    spot_at_exit: float | None = None
    eod = False

    dates = life.index.date
    for i in range(len(life)):
        bar = life.iloc[i]
        if float(bar["low"]) <= event.stop:
            trigger_idx, reason, spot_at_exit = i, EXIT_STOP, event.stop
            break
        if float(bar["high"]) >= event.target:
            trigger_idx, reason, spot_at_exit = i, EXIT_TARGET, event.target
            break
        is_last_of_day = i + 1 == len(life) or dates[i + 1] != dates[i]
        if dates[i] >= dte_cutoff and is_last_of_day:
            trigger_idx, reason, spot_at_exit = i, EXIT_DTE, float(bar["close"])
            eod = True
            break

    if trigger_idx is None:
        if life.empty:
            return trade  # no bars after entry — stays open, caller decides
        trigger_idx, reason, spot_at_exit = len(life) - 1, EXIT_WINDOW_END, float(
            life["close"].iloc[-1]
        )
        eod = True

    if next_bar_exit and not eod and trigger_idx + 1 < len(life):
        trigger_idx += 1
        spot_at_exit = float(life["close"].iloc[trigger_idx])

    exit_ts = life.index[trigger_idx].to_pydatetime()

    # Close every leg: sell what is long, buy back what is short.
    value = 0.0
    sources = []
    for leg in position.legs:
        m = mark_engine.mark(
            leg.occ,
            exit_ts,
            spot_at_exit,
            rv,
            life_start=event.signal_ts.date(),
            spot_at=spot_at,
            eod=eod,
        )
        sources.append(m.source)
        value += fills.sell(m.price) if leg.side > 0 else -fills.buy(m.price)

    trade.exit_ts = exit_ts
    trade.exit_reason = reason
    trade.exit_value_per_share = value
    trade.exit_mark_sources = tuple(sources)
    trade.close_fees = fees.one_way(n_legs=len(position.legs), n_contracts=position.contracts)
    return trade
