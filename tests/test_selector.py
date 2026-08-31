"""Contract selection from a live chain.

The case that motivates most of this: a DTE window routinely holds two or
three expiries, and on the big names the Monday and Wednesday weeklies list
the same strikes as the Friday at a fraction of the volume. Choosing among
them by anything other than quote quality throws away liquid contracts.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from deltaforge.live.broker import Quote
from deltaforge.live.selector import select_call

TODAY = date(2026, 8, 31)
FRIDAY = date(2026, 9, 11)     # 11 DTE — the liquid weekly
MONDAY = date(2026, 9, 14)     # 14 DTE — the thin one, and the furthest


class FakeBroker:
    """Only ``call_quotes`` is exercised by the selector."""

    def __init__(self, quotes: list[Quote]) -> None:
        self._quotes = quotes
        self.calls: list[tuple] = []

    def call_quotes(self, symbol, lo, hi, strike_lo, strike_hi):
        self.calls.append((symbol, lo, hi, strike_lo, strike_hi))
        return [
            q for q in self._quotes
            if lo <= q.expiry <= hi and strike_lo <= q.strike <= strike_hi
        ]


def q(expiry: date, strike: float, bid: float, ask: float, delta: float) -> Quote:
    return Quote(
        occ=f"AAPL{expiry:%y%m%d}C{int(strike * 1000):08d}",
        bid=bid, ask=ask, delta=delta, iv=0.3, strike=strike, expiry=expiry,
    )


# Both expiries carry a 0.55-delta call; only the Friday is tightly quoted.
AAPL_CHAIN = [
    q(FRIDAY, 275.0, 10.05, 10.15, 0.55),   # 1.0% wide
    q(FRIDAY, 280.0, 7.50, 7.60, 0.45),
    q(MONDAY, 275.0, 9.00, 12.00, 0.55),    # 28.6% wide — would be rejected
    q(MONDAY, 280.0, 6.50, 9.00, 0.45),
]


def test_picks_the_best_quoted_expiry_not_the_furthest():
    broker = FakeBroker(AAPL_CHAIN)
    sel = select_call(broker, "AAPL", spot=277.0, budget=5000.0, today=TODAY)

    assert not hasattr(sel, "reason"), getattr(sel, "detail", "")
    assert sel.quote.expiry == FRIDAY
    assert sel.quote.strike == 275.0


def test_the_thin_expiry_alone_is_still_rejected():
    """Choosing the best available must not become a way to accept anything."""
    broker = FakeBroker([x for x in AAPL_CHAIN if x.expiry == MONDAY])
    sel = select_call(broker, "AAPL", spot=277.0, budget=5000.0, today=TODAY)

    assert getattr(sel, "reason", None) == "illiquid"


def test_delta_target_still_decides_the_strike():
    """Expiry is chosen on spread; strike is still chosen on delta."""
    chain = [
        q(FRIDAY, 270.0, 14.00, 14.10, 0.70),
        q(FRIDAY, 275.0, 10.05, 10.15, 0.55),
        q(FRIDAY, 285.0, 4.00, 4.05, 0.30),
    ]
    sel = select_call(FakeBroker(chain), "AAPL", spot=277.0, budget=5000.0, today=TODAY)

    assert sel.quote.strike == 275.0


def test_a_tighter_spread_does_not_override_a_worse_delta_within_an_expiry():
    """The 0.30-delta call is quoted tighter; the 0.55 target must still win."""
    chain = [
        q(FRIDAY, 275.0, 10.00, 10.20, 0.55),   # 2.0%
        q(FRIDAY, 285.0, 4.00, 4.01, 0.30),     # 0.2%
    ]
    sel = select_call(FakeBroker(chain), "AAPL", spot=277.0, budget=5000.0, today=TODAY)

    assert sel.quote.delta == 0.55


def test_expiries_without_greeks_are_skipped_not_fatal():
    chain = [
        Quote(occ="X", bid=9.0, ask=12.0, delta=None, iv=None,
              strike=275.0, expiry=MONDAY),
        q(FRIDAY, 275.0, 10.05, 10.15, 0.55),
    ]
    sel = select_call(FakeBroker(chain), "AAPL", spot=277.0, budget=5000.0, today=TODAY)

    assert sel.quote.expiry == FRIDAY


def test_no_greeks_anywhere_is_reported():
    chain = [
        Quote(occ="X", bid=10.05, ask=10.15, delta=None, iv=None,
              strike=275.0, expiry=FRIDAY),
    ]
    sel = select_call(FakeBroker(chain), "AAPL", spot=277.0, budget=5000.0, today=TODAY)

    assert getattr(sel, "reason", None) == "no_greeks"


def test_budget_still_binds_after_the_expiry_choice():
    broker = FakeBroker(AAPL_CHAIN)
    sel = select_call(broker, "AAPL", spot=277.0, budget=300.0, today=TODAY)

    assert getattr(sel, "reason", None) == "over_budget"
    assert "$1010" in sel.detail


@pytest.mark.parametrize("dte_min,dte_max", [(7, 14), (14, 21)])
def test_the_dte_window_is_passed_through(dte_min, dte_max):
    broker = FakeBroker(AAPL_CHAIN)
    select_call(broker, "AAPL", spot=277.0, budget=5000.0, today=TODAY,
                dte_min=dte_min, dte_max=dte_max)

    _, lo, hi, _, _ = broker.calls[0]
    assert (lo, hi) == (TODAY + timedelta(days=dte_min), TODAY + timedelta(days=dte_max))
