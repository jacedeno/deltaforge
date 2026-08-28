import pytest

from deltaforge.pricing.fees import DEFAULT_FEES, FeeSchedule


def test_analysis_md_planning_number():
    # docs/ANALYSIS.md: 2-leg spread round trip ~ $2.60 at $0.65/contract/leg.
    assert DEFAULT_FEES.per_contract == pytest.approx(0.65)
    assert DEFAULT_FEES.round_trip(n_legs=2, n_contracts=1) == pytest.approx(2.60)


def test_scales_with_contracts():
    assert DEFAULT_FEES.round_trip(n_legs=1, n_contracts=3) == pytest.approx(3.90)


def test_custom_schedule():
    free = FeeSchedule(commission_per_contract=0.0, regulatory_per_contract=0.05)
    assert free.round_trip(2) == pytest.approx(0.20)


def test_rejects_nonpositive():
    with pytest.raises(ValueError):
        DEFAULT_FEES.one_way(0)
