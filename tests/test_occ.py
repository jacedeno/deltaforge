from datetime import date

import pytest

from deltaforge.data.occ import (
    build_occ_symbol,
    candidate_strikes,
    fridays_between,
    parse_occ_symbol,
    strike_spacing,
)


def test_build_matches_alpaca_format():
    assert build_occ_symbol("INTC", date(2026, 9, 18), "C", 25.0) == "INTC260918C00025000"
    assert build_occ_symbol("bac", date(2024, 3, 1), "p", 37.5) == "BAC240301P00037500"


def test_fractional_strike_no_float_drift():
    # 32.5 * 1000 must encode as 00032500 even when the float is 32.499999...
    assert build_occ_symbol("F", date(2025, 1, 17), "C", 32.5).endswith("00032500")


def test_parse_round_trips():
    sym = build_occ_symbol("UBER", date(2026, 10, 16), "C", 87.5)
    assert parse_occ_symbol(sym) == ("UBER", date(2026, 10, 16), "C", 87.5)


def test_parse_rejects_garbage():
    with pytest.raises(ValueError):
        parse_occ_symbol("NOT_AN_OCC")


def test_build_rejects_bad_side():
    with pytest.raises(ValueError):
        build_occ_symbol("F", date(2025, 1, 17), "X", 10)


def test_strike_spacing_bands():
    assert strike_spacing(12) == 0.5
    assert strike_spacing(60) == 1.0
    assert strike_spacing(150) == 2.5
    assert strike_spacing(400) == 5.0


def test_candidate_strikes_covers_band_inclusive():
    ks = candidate_strikes(spot=40.0, lo=38.0, hi=42.0)
    assert ks == [38.0, 39.0, 40.0, 41.0, 42.0]


def test_candidate_strikes_never_zero_or_negative():
    ks = candidate_strikes(spot=1.0, lo=0.0, hi=1.0)
    assert all(k > 0 for k in ks)


def test_fridays_between():
    # 2026-08-28 is a Friday.
    out = fridays_between(date(2026, 8, 28), date(2026, 9, 18))
    assert out == [date(2026, 8, 28), date(2026, 9, 4), date(2026, 9, 11), date(2026, 9, 18)]
    assert fridays_between(date(2026, 8, 29), date(2026, 9, 3)) == []
