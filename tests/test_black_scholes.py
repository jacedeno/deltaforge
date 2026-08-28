import math

import pytest

from deltaforge.pricing.black_scholes import bs_greeks, bs_price, implied_vol, intrinsic

# Textbook case: S=100, K=100, T=1y, r=5%, sigma=20%.
S, K, T, R, SIGMA = 100.0, 100.0, 1.0, 0.05, 0.20
CALL_REF = 10.4506
PUT_REF = 5.5735


def test_call_matches_textbook_value():
    assert bs_price(S, K, T, R, SIGMA, "C") == pytest.approx(CALL_REF, abs=1e-3)


def test_put_matches_textbook_value():
    assert bs_price(S, K, T, R, SIGMA, "P") == pytest.approx(PUT_REF, abs=1e-3)


def test_put_call_parity():
    c = bs_price(S, K, T, R, SIGMA, "C")
    p = bs_price(S, K, T, R, SIGMA, "P")
    assert c - p == pytest.approx(S - K * math.exp(-R * T), abs=1e-9)


def test_zero_time_returns_intrinsic():
    assert bs_price(110, 100, 0.0, R, SIGMA, "C") == 10.0
    assert bs_price(90, 100, 0.0, R, SIGMA, "P") == 10.0
    assert intrinsic(90, 100, "C") == 0.0


def test_deep_itm_call_delta_near_one():
    g = bs_greeks(150, 100, 0.05, R, SIGMA, "C")
    assert g.delta > 0.99
    assert g.gamma >= 0


def test_atm_call_delta_near_half():
    g = bs_greeks(S, K, 0.05, R, SIGMA, "C")
    assert 0.45 < g.delta < 0.60


def test_theta_negative_for_long_call():
    assert bs_greeks(S, K, T, R, SIGMA, "C").theta < 0


def test_implied_vol_round_trips():
    price = bs_price(S, K, 30 / 365, R, 0.35, "C")
    iv = implied_vol(price, S, K, 30 / 365, R, "C")
    assert iv == pytest.approx(0.35, abs=1e-4)


def test_implied_vol_below_intrinsic_is_none():
    assert implied_vol(9.0, 110, 100, 30 / 365, R, "C") is None


def test_implied_vol_expired_is_none():
    assert implied_vol(5.0, S, K, 0.0, R, "C") is None
