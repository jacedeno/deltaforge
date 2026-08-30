from datetime import date

import pandas as pd

from deltaforge.data.chains import DiscoveredContract
from deltaforge.data.occ import build_occ_symbol
from deltaforge.pricing.black_scholes import bs_greeks, bs_price
from deltaforge.pricing.fees import FeeSchedule
from deltaforge.pricing.fills import FillModel
from deltaforge.pricing.iv import risk_free
from deltaforge.pricing.marks import Mark, _t_years
from deltaforge.pricing.spreads import SpreadWidthModel
from deltaforge.structures.base import EntryContext, Position, Skip
from deltaforge.structures.debit_spread import DebitSpread
from deltaforge.structures.long_call import LongCall

SIGMA = 0.30
FILLS = FillModel(spread_model=SpreadWidthModel(), haircut=0.5)
FEES = FeeSchedule()


def make_chain(symbol: str, expiry: date, strikes: list[float]) -> list[DiscoveredContract]:
    empty = pd.DataFrame()
    return [
        DiscoveredContract(build_occ_symbol(symbol, expiry, "C", k), expiry, k, empty)
        for k in strikes
    ]


def make_ctx(event, contracts, max_debit=150.0) -> EntryContext:
    spot = event.entry_price
    r = risk_free(event.signal_ts.year)

    def mark(occ: str) -> Mark:
        for c in contracts:
            if c.occ == occ:
                t = _t_years(event.signal_ts, c.expiry)
                return Mark(bs_price(spot, c.strike, t, r, SIGMA, "C"), "bs_model", iv=SIGMA)
        raise KeyError(occ)

    def entry_delta(c: DiscoveredContract) -> float:
        t = _t_years(event.signal_ts, c.expiry)
        return bs_greeks(spot, c.strike, t, r, SIGMA, "C").delta

    return EntryContext(
        event=event, spot=spot, rv=SIGMA, contracts=contracts,
        mark=mark, entry_delta=entry_delta, fills=FILLS, fees=FEES, max_debit=max_debit,
    )


def test_debit_spread_selection(event):
    # Entry 100, target 109, DTE window 14-21 from 2026-03-02 -> Friday 03-20.
    chain = make_chain("TEST", date(2026, 3, 20), [95, 97.5, 100, 102.5, 105, 107.5, 110])
    # Budget high enough that sizing can't mask the selection logic under test.
    pos = DebitSpread().select(make_ctx(event, chain, max_debit=600.0))
    assert isinstance(pos, Position)
    long_leg, short_leg = pos.legs
    assert long_leg.side == 1 and short_leg.side == -1
    # Long near 0.625 delta => slightly ITM, below spot.
    assert long_leg.strike <= 100
    # Short at the strike nearest the 3R target of 109.
    assert short_leg.strike == 110
    assert pos.debit_per_share > 0
    assert pos.contracts >= 1


def test_debit_spread_skips_when_no_expiry(event):
    chain = make_chain("TEST", date(2026, 5, 15), [100, 105])  # far outside 14-21 DTE
    skip = DebitSpread().select(make_ctx(event, chain))
    assert isinstance(skip, Skip) and skip.reason == "no_expiry_in_window"


def test_debit_spread_skips_when_no_width(event):
    chain = make_chain("TEST", date(2026, 3, 20), [90, 92.5])  # nothing above the long
    skip = DebitSpread().select(make_ctx(event, chain))
    assert isinstance(skip, Skip) and skip.reason == "no_width"


def test_debit_spread_respects_budget(event):
    chain = make_chain("TEST", date(2026, 3, 20), [95, 97.5, 100, 105, 110])
    skip = DebitSpread().select(make_ctx(event, chain, max_debit=10.0))
    assert isinstance(skip, Skip) and skip.reason == "debit_exceeds_budget"


def test_long_call_picks_itm_delta(event):
    # LongCall window is 21-28 DTE from 2026-03-02 -> Friday 03-27.
    chain = make_chain("TEST", date(2026, 3, 27), [90, 92.5, 95, 97.5, 100, 105])
    pos = LongCall().select(make_ctx(event, chain, max_debit=800.0))
    assert isinstance(pos, Position)
    assert len(pos.legs) == 1
    assert pos.legs[0].strike < 100  # 0.675 delta is in the money


def test_short_at_2r_overrides_target(event):
    chain = make_chain("TEST", date(2026, 3, 20), [95, 100, 105, 106, 110])
    pos = DebitSpread(short_at_r=2.0).select(make_ctx(event, chain, max_debit=400.0))
    assert isinstance(pos, Position)
    # 2R = entry 100 + 2*3 = 106.
    assert pos.legs[1].strike == 106


def test_rejects_implausibly_cheap_spread(event):
    """A debit far below the spread's width means a stale mark, not a bargain."""
    chain = make_chain("TEST", date(2026, 3, 20), [95, 97.5, 100, 105, 110])
    ctx = make_ctx(event, chain, max_debit=600.0)
    # Both legs marked identically — what a stale print on one strike looks
    # like. The net debit collapses to the fill haircut alone, far under the
    # spread's width, and the position must be refused rather than sized on it.
    ctx.mark = lambda occ: Mark(5.0, "bs_model", iv=SIGMA)

    result = DebitSpread().select(ctx)
    assert isinstance(result, Skip)
    assert result.reason == "debit_implausible"


def test_long_call_rejects_implausible_premium(event):
    """A near-ATM call with no time value is a stale print, not a bargain."""
    chain = make_chain("TEST", date(2026, 3, 27), [90, 95, 97.5, 100])
    ctx = make_ctx(event, chain, max_debit=800.0)
    # Entry is 100, so a 97.5 strike has $2.50 intrinsic; mark it at barely
    # over intrinsic and the position must be refused rather than sized.
    ctx.mark = lambda occ: Mark(2.51, "minute", iv=SIGMA)

    result = LongCall().select(ctx)
    assert isinstance(result, Skip)
    assert result.reason == "premium_implausible"


def test_long_call_accepts_normal_premium(event):
    chain = make_chain("TEST", date(2026, 3, 27), [90, 92.5, 95, 97.5, 100])
    pos = LongCall().select(make_ctx(event, chain, max_debit=800.0))
    assert isinstance(pos, Position)
