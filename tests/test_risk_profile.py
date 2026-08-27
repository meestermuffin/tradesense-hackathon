"""Correlation, effective bets, and the shock.

The number these exist to protect: ten positions in this universe behave like roughly two
independent bets. `max_loss x positions` is not a tail scenario for this book, it is a bad Tuesday.
"""

import pytest

from src.models import BookPosition, Exposure
from src.risk_profile import (
    MEAN_PAIRWISE_CORRELATION,
    book_profile,
    effective_bets,
    position_exposure,
    stress,
)


def pos(delta=5.0, vega=-6.0, max_loss=400.0, spot=100.0):
    """Long delta, short vega -- what a short put spread actually is."""
    return BookPosition(
        exposure=Exposure(delta=delta, gamma=0.1, vega=vega, theta=2.0),
        max_loss=max_loss,
        spot=spot,
    )


def test_uncorrelated_positions_are_their_own_count():
    assert effective_bets(10, rho=0.0) == pytest.approx(10.0)


def test_perfectly_correlated_positions_are_one_bet():
    assert effective_bets(10, rho=1.0) == pytest.approx(1.0)


def test_ten_positions_in_this_universe_are_about_two_bets():
    """The measured figure, and the reason the per-position cap is not a risk profile."""
    assert MEAN_PAIRWISE_CORRELATION == pytest.approx(0.409)
    assert effective_bets(10) == pytest.approx(2.14, abs=0.01)


def test_effective_bets_never_exceeds_the_position_count():
    for n in range(1, 21):
        assert effective_bets(n) <= n


def test_a_single_position_is_one_bet():
    assert effective_bets(1) == 1.0


def test_book_profile_aggregates_and_reports_the_correlated_worst_case():
    profile = book_profile([pos() for _ in range(10)], 100_000)
    assert profile.positions == 10
    assert profile.effective_bets == pytest.approx(2.14, abs=0.01)
    assert profile.net_vega == pytest.approx(-60.0)
    assert profile.defined_risk == pytest.approx(4000.0)
    assert profile.defined_risk_pct == pytest.approx(4.0)
    # Everything hitting max loss at once is what a correlated selloff looks like.
    assert profile.correlated_worst_case_pct == profile.defined_risk_pct


def test_a_short_premium_book_is_short_vega():
    """Sold volatility. A vol spike is a loss, and that is the exposure the equity strategy hid."""
    e = position_exposure(100, 95, 90, 0.30, 30 / 365, 0.04, "P", 1)
    assert e.vega < 0


def test_a_short_put_spread_is_long_delta():
    """Structural, and the reason this book's returns correlate with SPY by construction.

    It is also why a return gap against SPY is a comparison rather than alpha: crediting the gap to
    skill pays the strategy for exposure it is already carrying.
    """
    e = position_exposure(100, 95, 90, 0.30, 30 / 365, 0.04, "P", 1)
    assert e.delta > 0


def test_stress_loses_on_a_downside_move_with_vol_up():
    """The -7% default is not arbitrary: it is what this universe did on 2025-04-04,
    when all eleven names fell together."""
    result = stress([pos() for _ in range(10)], 100_000)
    assert result.first_order_pnl < 0
    assert result.delta_pnl < 0
    assert result.vega_pnl < 0
    assert "-7.0%" in result.scenario and "+10 points" in result.scenario


def test_stress_reports_the_structural_floor_separately():
    """Greeks are local; a 7% move is well outside where the approximation holds.

    The floor is what the structure actually caps the loss at, and it must be reported alongside
    rather than replacing the first-order figure.
    """
    positions = [pos(max_loss=400.0) for _ in range(10)]
    result = stress(positions, 100_000)
    assert result.floor_from_defined_risk == pytest.approx(-4000.0)
    assert "first-order only" in result.note


def test_stress_percentage_never_reports_worse_than_the_floor():
    """A linear approximation can extrapolate past a loss the structure cannot actually take."""
    positions = [pos(delta=500.0, vega=-500.0, max_loss=400.0) for _ in range(10)]
    result = stress(positions, 100_000)
    assert result.first_order_pnl < result.floor_from_defined_risk
    assert result.pct_of_equity == pytest.approx(result.floor_from_defined_risk / 1000)
