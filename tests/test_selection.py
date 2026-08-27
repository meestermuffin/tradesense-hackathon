"""Resolving a template to strikes, against a chain priced by the same model that inverts it."""

import datetime

import pytest
from conftest import FakeClient

from src.models import Rejection, Spread, Template
from src.options.iv import price
from src.options.selection import bs_delta, select_vertical

SPOT, SIGMA, RATE, DAYS = 100.0, 0.30, 0.04, 30


def chain(strikes, spread_frac=0.02, spot=SPOT, sigma=SIGMA):
    """A put chain priced by Black-Scholes, so inversion recovers roughly the input vol."""
    T = DAYS / 365.0
    out = {}
    for k in strikes:
        p = price(spot, k, T, RATE, sigma, "P")
        out[float(k)] = (
            f"XYZ{k:03.0f}P",
            round(p * (1 - spread_frac), 2),
            round(p * (1 + spread_frac), 2),
        )
    return FakeClient(out, datetime.date.today() + datetime.timedelta(days=DAYS))


def tmpl(**kw):
    base = dict(structure="put_credit", target_delta=0.25, width=5.0, dte_min=25, dte_max=35)
    return Template(**{**base, **kw})


def test_resolves_a_vertical_near_the_target_delta():
    got = select_vertical(chain(range(70, 131, 5)), "XYZ", SPOT, tmpl())
    assert isinstance(got, Spread)
    assert abs(abs(got.short_delta) - 0.25) <= tmpl().delta_tolerance
    assert got.short.strike > got.long.strike  # protective wing below the short put


def test_max_loss_uses_the_actual_wing_width_not_the_requested_one():
    """The wing snaps to the nearest listed strike.

    A 7-wide request against a 5-point grid gets a 5-wide spread, and max_loss must follow the
    structure that actually exists. Computing it from the requested width made max_loss and
    defined_risk disagree about the same position.
    """
    got = select_vertical(chain(range(70, 131, 5)), "XYZ", SPOT, tmpl(width=7.0))
    assert isinstance(got, Spread)
    actual = abs(got.short.strike - got.long.strike)
    assert actual != 7.0, "grid should force a snap for this test to mean anything"
    assert got.width == pytest.approx(actual)
    assert got.max_loss == pytest.approx(actual - got.credit_mid, abs=1e-4)


def test_defined_risk_agrees_with_the_reported_max_loss():
    from src.risk import defined_risk

    got = select_vertical(chain(range(70, 131, 5)), "XYZ", SPOT, tmpl(width=7.0))
    assert defined_risk(got.width, got.credit_mid, 1) == pytest.approx(got.max_loss * 100, abs=1e-2)


def test_a_wing_wider_than_the_cap_is_refused():
    got = select_vertical(chain(range(50, 151, 25)), "XYZ", SPOT, tmpl(width=5.0, max_width=6.0))
    assert isinstance(got, Rejection)
    assert "cap" in got.reason or "delta" in got.reason


def test_wide_quotes_are_refused_and_the_reason_reports_how_many_survived():
    """A wide book is refused, and the message says how thin the survivors were.

    Note the survivor count is rarely zero even on a 30%-wide book: a deep-OTM strike quoted
    0.01/0.01 has a percentage spread of zero and passes a percentage filter cleanly. That is real
    market structure, not a fixture artifact, and it is why the delta check exists downstream.
    """
    got = select_vertical(chain(range(70, 131, 5), spread_frac=0.30), "XYZ", SPOT, tmpl())
    assert isinstance(got, Rejection)
    assert "passed quality" in got.reason


def test_a_uniformly_wide_near_money_chain_fails_on_quote_quality():
    """No penny strikes to sneak through, so the quality filter is what refuses it."""
    got = select_vertical(chain(range(90, 111, 5), spread_frac=0.30), "XYZ", SPOT, tmpl())
    assert isinstance(got, Rejection)
    assert "quote quality" in got.reason


def test_no_expiry_in_band_is_refused():
    c = chain(range(70, 131, 5))
    c.expiry = datetime.date.today() + datetime.timedelta(days=200)
    got = select_vertical(c, "XYZ", SPOT, tmpl())
    assert isinstance(got, Rejection)
    assert "DTE" in got.reason


def test_delta_far_from_target_is_refused_with_the_surviving_range():
    """Taking the nearest anyway is how a 0.25-delta template sells a 0.93-delta contract."""
    got = select_vertical(chain([99, 100, 101]), "XYZ", SPOT, tmpl())
    assert isinstance(got, Rejection)
    assert "nearest delta" in got.reason and "spanning delta" in got.reason


def test_bs_delta_signs_and_bounds():
    T = DAYS / 365.0
    assert -1 < bs_delta(SPOT, 95, T, RATE, SIGMA, "P") < 0
    assert 0 < bs_delta(SPOT, 105, T, RATE, SIGMA, "C") < 1
    # Deep ITM put approaches -1, deep OTM approaches 0.
    assert bs_delta(SPOT, 200, T, RATE, SIGMA, "P") < -0.9
    assert bs_delta(SPOT, 10, T, RATE, SIGMA, "P") > -0.05
