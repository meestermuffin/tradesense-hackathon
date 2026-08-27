"""Black-Scholes and the inversion.

IV is computed here, never read: greeks and impliedVolatility are OPRA-gated and absent from the
response on this account. That makes the inverter load-bearing for the entire signal.
"""

import pytest

from src.options.iv import greeks, implied_vol, price, realized_vol

S, K, T, R = 100.0, 100.0, 30 / 365, 0.04


@pytest.mark.parametrize("cp", ["C", "P"])
@pytest.mark.parametrize("sigma", [0.10, 0.25, 0.50, 1.00])
@pytest.mark.parametrize("strike", [95.0, 100.0, 105.0])
def test_inversion_recovers_the_volatility_it_was_priced_at(cp, sigma, strike):
    """Near the money, where the extrinsic value that carries the information actually lives."""
    p = price(S, strike, T, R, sigma, cp)
    got = implied_vol(p, S, strike, T, R, cp)
    assert got is not None
    assert got == pytest.approx(sigma, abs=1e-3)


@pytest.mark.parametrize("strike,cp", [(80.0, "P"), (120.0, "C")])
def test_a_strike_with_no_extrinsic_value_inverts_to_nothing(strike, cp):
    """Deep out of the money at 10% vol over 30 days is worth ~0, and carries no vol information.

    Returning None is correct: there is no volatility that the price identifies. Filtering on
    moneyness upstream is what keeps these out of the series in the first place.
    """
    p = price(S, strike, T, R, 0.10, cp)
    assert p < 1e-6
    assert implied_vol(p, S, strike, T, R, cp) is None


@pytest.mark.parametrize("strike,cp", [(80.0, "C"), (120.0, "P")])
def test_a_strike_that_is_all_intrinsic_inverts_to_nothing(strike, cp):
    """Deep in the money at low vol is intrinsic plus rounding; same conclusion, other side."""
    p = price(S, strike, T, R, 0.10, cp)
    assert implied_vol(p, S, strike, T, R, cp) is None


def test_put_call_parity_holds():
    import math

    c = price(S, K, T, R, 0.30, "C")
    p = price(S, K, T, R, 0.30, "P")
    assert c - p == pytest.approx(S - K * math.exp(-R * T), abs=1e-9)


def test_a_price_below_intrinsic_implies_no_volatility():
    """Returns None rather than a fabricated number -- the quote is broken, not informative."""
    assert implied_vol(0.0001, S, 150.0, T, R, "P") is None


def test_price_is_monotonic_in_volatility():
    prices = [price(S, K, T, R, v, "C") for v in (0.1, 0.2, 0.4, 0.8)]
    assert prices == sorted(prices)


def test_greeks_signs_for_a_long_option():
    g = greeks(S, K, T, R, 0.30, "P")
    assert -1 < g["delta"] < 0  # long put
    assert g["gamma"] > 0
    assert g["vega"] > 0  # long options are long vol
    assert g["theta"] < 0  # and pay for it in time


def test_realized_vol_of_a_flat_series_is_zero():
    assert realized_vol([100.0] * 30) == pytest.approx(0.0)


def test_realized_vol_rises_with_dispersion():
    calm = realized_vol([100 + (i % 2) * 0.1 for i in range(60)])
    wild = realized_vol([100 + (i % 2) * 5.0 for i in range(60)])
    assert wild > calm > 0
