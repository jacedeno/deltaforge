from datetime import UTC, date, datetime

from conftest import make_bars

from deltaforge.engine.lifecycle import replay_trade
from deltaforge.engine.trade import EXIT_DTE, EXIT_STOP, EXIT_TARGET
from deltaforge.pricing.fees import FeeSchedule
from deltaforge.pricing.fills import FillModel
from deltaforge.pricing.iv import IVModel
from deltaforge.pricing.marks import MarkEngine
from deltaforge.pricing.spreads import SpreadWidthModel
from deltaforge.structures.base import Leg, Position

FEES = FeeSchedule()
FILLS = FillModel(spread_model=SpreadWidthModel(), haircut=0.5)
RV = 0.30


def synthetic_marks() -> MarkEngine:
    return MarkEngine(None, IVModel(), synthetic_only=True)


def spread_position(entry_ts: datetime, expiry: date) -> Position:
    legs = (
        Leg("TEST" + expiry.strftime("%y%m%d") + "C00100000", expiry, 100.0, +1, 2.50),
        Leg("TEST" + expiry.strftime("%y%m%d") + "C00109000", expiry, 109.0, -1, 0.80),
    )
    return Position(
        structure="debit_spread",
        legs=legs,
        contracts=1,
        entry_ts=entry_ts,
        debit_per_share=1.70,
        open_fees=FEES.one_way(2, 1),
    )


def test_stop_touch_exits_with_partial_loss(event):
    bars = make_bars("2026-03-02", days=10, open_price=100.0)
    # Force a stop touch on day 3.
    bars.iloc[30, bars.columns.get_loc("low")] = 96.5
    pos = spread_position(event.signal_ts, date(2026, 3, 20))
    t = replay_trade(event, pos, bars, synthetic_marks(), FILLS, FEES, RV)
    assert t.exit_reason == EXIT_STOP
    assert t.exit_ts == bars.index[30].to_pydatetime()
    # Loss, but not a total loss of the debit (the "needs measuring" claim).
    assert -100.0 < t.pnl_pct_of_debit < 0.0
    assert all(s == "bs_model" for s in t.exit_mark_sources)


def test_target_touch_wins_and_pays(event):
    bars = make_bars("2026-03-02", days=10, open_price=100.0)
    bars.iloc[40, bars.columns.get_loc("high")] = 109.5
    pos = spread_position(event.signal_ts, date(2026, 3, 20))
    t = replay_trade(event, pos, bars, synthetic_marks(), FILLS, FEES, RV)
    assert t.exit_reason == EXIT_TARGET
    assert t.pnl_dollars > 0


def test_same_bar_stop_beats_target(event):
    bars = make_bars("2026-03-02", days=10, open_price=100.0)
    bars.iloc[20, bars.columns.get_loc("low")] = 96.0
    bars.iloc[20, bars.columns.get_loc("high")] = 110.0
    pos = spread_position(event.signal_ts, date(2026, 3, 20))
    t = replay_trade(event, pos, bars, synthetic_marks(), FILLS, FEES, RV)
    assert t.exit_reason == EXIT_STOP


def test_dte_clock_closes_at_session_end(event):
    # No touch ever: flat bars, tight range around 100.
    bars = make_bars("2026-03-02", days=15, open_price=100.0, bar_range=0.2)
    pos = spread_position(event.signal_ts, date(2026, 3, 13))
    t = replay_trade(event, pos, bars, synthetic_marks(), FILLS, FEES, RV, dte_exit_days=5)
    assert t.exit_reason == EXIT_DTE
    # 5 days before 2026-03-13 expiry = cutoff 03-08 (Sun) -> first session 03-09.
    assert t.exit_ts.date() == date(2026, 3, 9)
    # Last bar of the session, 19:30 UTC (15:30 ET start of last 30m bar).
    assert t.exit_ts.hour == 20 and t.exit_ts.minute == 30 or t.exit_ts.hour == 20


def test_next_bar_exit_moves_one_bar_later(event):
    bars = make_bars("2026-03-02", days=10, open_price=100.0)
    bars.iloc[30, bars.columns.get_loc("low")] = 96.5
    pos = spread_position(event.signal_ts, date(2026, 3, 20))
    base = replay_trade(event, pos, bars, synthetic_marks(), FILLS, FEES, RV)
    shifted = replay_trade(
        event, pos, bars, synthetic_marks(), FILLS, FEES, RV, next_bar_exit=True
    )
    assert shifted.exit_ts > base.exit_ts


def test_fees_charged_both_ways(event):
    bars = make_bars("2026-03-02", days=10, open_price=100.0)
    bars.iloc[40, bars.columns.get_loc("high")] = 109.5
    pos = spread_position(event.signal_ts, date(2026, 3, 20))
    t = replay_trade(event, pos, bars, synthetic_marks(), FILLS, FEES, RV)
    assert t.total_fees == FEES.round_trip(n_legs=2, n_contracts=1)
