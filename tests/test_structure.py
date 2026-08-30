"""Strike selection, and the day-count mismatch that hid inside a plan.

A trading plan computed expected move on a 252-day basis while every implied vol in this repo is
inverted on 365. A genuine 20-delta strike then appeared to sit at 0.67x the expected move instead
of 0.84x. The discrepancy was visible and was rationalised as an aggressive strike rather than
traced. An outside reviewer caught it, and read it as a broken delta calculation -- the delta was
right and the expected move was wrong.

These tests fail if the two ever drift apart again.
"""

import math

import pytest

from src.options.structure import (
    DAY_COUNT,
    em_multiple_exact,
    em_multiple_for_delta,
    expected_move,
    strike_at_delta,
    verify_delta_em_consistency,
    years,
)

SPOT, IV = 766.0, 0.127


def test_twenty_delta_sits_at_the_textbook_multiple():
    """N(-d1) = 0.20 puts the strike 0.8416 standard deviations out. Not 0.67."""
    assert em_multiple_for_delta(0.20) == pytest.approx(0.8416, abs=1e-3)
    assert em_multiple_for_delta(0.50) == pytest.approx(0.0, abs=1e-6)
    assert em_multiple_for_delta(0.30) == pytest.approx(0.5244, abs=1e-3)


def test_inverse_normal_matches_the_forward():
    for p in (0.01, 0.1, 0.2, 0.5, 0.8, 0.99):
        x = em_multiple_for_delta(1 - p)
        assert 0.5 * (1 + math.erf(x / math.sqrt(2))) == pytest.approx(p, abs=1e-6)


@pytest.mark.parametrize("dte", [1, 2, 3, 7, 30])
@pytest.mark.parametrize("cp", ["P", "C"])
def test_solved_strike_agrees_with_its_expected_move(dte, cp):
    """The cross-check: solve from delta, measure in EM units, require agreement.

    This is the assertion a mismatched day count cannot survive. It carries the drift term, without
    which puts and calls diverge from the driftless 0.8416 in opposite directions as T grows: ~0.02
    at 2 DTE, ~0.12 at 30, which is exactly how this test first failed.
    """
    ok, actual, want = verify_delta_em_consistency(SPOT, IV, dte, 0.20, cp)
    assert ok, f"{dte} DTE {cp}: strike at {actual:.3f}xEM, expected {want:.3f}xEM"


def test_a_mismatched_day_count_is_caught():
    """The regression. Recompute EM on 252 while the strike was solved on 365.

    The ratio is sqrt(252/365) = 0.8309, so the multiple reads ~0.70 instead of ~0.84 -- outside
    tolerance, which is the whole point. Had this test existed, the plan would not have shipped a
    0.67xEM book believing it was 1.0x.
    """
    dte = 2
    k = strike_at_delta(SPOT, IV, dte, 0.20, "P", grid=0.01)
    em_correct = expected_move(SPOT, IV, dte)
    em_wrong = SPOT * IV * math.sqrt(dte / 252.0)

    good = abs(SPOT - k) / em_correct
    bad = abs(SPOT - k) / em_wrong

    assert good == pytest.approx(0.84, abs=0.08)
    assert bad == pytest.approx(0.70, abs=0.08)
    assert bad < 0.75 < good, "the mismatch must be visible, not marginal"
    assert em_wrong / em_correct == pytest.approx(math.sqrt(365 / 252), abs=1e-6)


def test_drift_pushes_puts_in_and_calls_out():
    """Symmetric only in the driftless limit. The asymmetry grows with sqrt(T)."""
    near_p = em_multiple_exact(0.20, IV, 2, "P")
    near_c = em_multiple_exact(0.20, IV, 2, "C")
    far_p = em_multiple_exact(0.20, IV, 30, "P")
    far_c = em_multiple_exact(0.20, IV, 30, "C")
    assert near_p < 0.8416 < near_c
    assert far_p < near_p and far_c > near_c
    assert (near_c - near_p) < (far_c - far_p)
    # At the tenor actually traded the correction is small enough that 0.84 remains a fair heuristic
    assert abs(near_p - 0.8416) < 0.03


def test_expected_move_and_black_scholes_share_one_day_count():
    """Neither may carry its own basis. One constant, used by both."""
    assert DAY_COUNT == 365.0
    assert years(365) == pytest.approx(1.0)
    assert expected_move(100.0, 0.20, 365) == pytest.approx(20.0)


def test_strike_at_delta_actually_returns_that_delta():
    from src.options.iv import greeks

    for target in (0.15, 0.20, 0.25, 0.30):
        k = strike_at_delta(SPOT, IV, 2, target, "P", grid=0.01)
        d = abs(greeks(SPOT, k, years(2), 0.04, IV, "P")["delta"])
        assert d == pytest.approx(target, abs=0.005)


def test_further_out_strikes_carry_lower_delta():
    ks = [strike_at_delta(SPOT, IV, 2, d, "P", grid=0.01) for d in (0.30, 0.25, 0.20, 0.15)]
    assert ks == sorted(ks, reverse=True)


def test_expected_move_scales_with_root_time():
    a, b = expected_move(SPOT, IV, 1), expected_move(SPOT, IV, 4)
    assert b / a == pytest.approx(2.0, abs=1e-6)


def test_a_one_delta_move_in_iv_moves_the_strike_the_right_way():
    calm = strike_at_delta(SPOT, 0.10, 2, 0.20, "P", grid=0.01)
    wild = strike_at_delta(SPOT, 0.30, 2, 0.20, "P", grid=0.01)
    assert wild < calm, "higher vol must push the 20-delta strike further out"
