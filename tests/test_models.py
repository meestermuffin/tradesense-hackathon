"""What the types refuse.

Each of these encodes a failure that has either happened here or is one keystroke away.
"""

import pytest
from pydantic import ValidationError

from src.models import Account, Position, Quote, RiskLimits, Spread, StrikeCandidate, Template


def sc(strike, mid, delta=-0.25):
    return StrikeCandidate(
        strike=strike,
        symbol=f"X{strike:g}",
        mid=mid,
        iv=0.3,
        delta=delta,
        quote=Quote(bp=mid - 0.05, ap=mid + 0.05),
    )


# ---- wire models: the absent-key failure


def test_missing_ask_raises_rather_than_defaulting():
    """The project's most-repeated failure: a key simply absent from an otherwise-200 response."""
    with pytest.raises(ValidationError):
        Quote.model_validate({"bp": 1.20})


def test_unknown_fields_are_ignored():
    """Alpaca returns far more than this book reads; a new field upstream must not break a cycle."""
    q = Quote.model_validate({"bp": 1.0, "ap": 1.1, "some_new_field": "x"})
    assert q.mid == pytest.approx(1.05)


def test_string_numerics_are_coerced():
    """strike_price, equity and filled_avg_price all arrive as strings."""
    a = Account.model_validate({"account_number": "PA1", "equity": "99949.80"})
    assert a.equity == pytest.approx(99949.80)


def test_crossed_quote_is_data_to_refuse_not_an_exception():
    """A one-sided or crossed book is a real market state. It must parse, then be rejected."""
    assert Quote(bp=0, ap=1.2).two_sided is False
    assert Quote(bp=1.3, ap=1.2).two_sided is False
    assert Quote(bp=1.2, ap=1.3).two_sided is True


@pytest.mark.parametrize(
    "symbol,expected",
    [("SPY260904P00600000", "SPY"), ("GOOGL260904C00200000", "GOOGL"), ("AAPL", "AAPL")],
)
def test_position_underlying_parses_the_occ_symbol(symbol, expected):
    """A position's `symbol` is the OCC contract, not the name.

    Comparing it directly against a candidate's underlying is a comparison that can never be
    true -- which is how the one-position-per-name cap silently stopped capping anything.
    """
    assert Position(symbol=symbol).underlying == expected


# ---- domain models: the invariants


def test_template_defaults_live_in_one_place():
    t = Template(structure="put_credit", target_delta=0.25, width=5.0)
    assert (t.dte_min, t.dte_max, t.max_spread_pct, t.delta_tolerance) == (5, 9, 0.08, 0.15)
    assert t.cp == "P"
    assert t.width_cap == 10.0  # width * 2 when max_width is unset


def test_template_rejects_incoherent_dte_band():
    with pytest.raises(ValidationError):
        Template(structure="put_credit", target_delta=0.25, width=5.0, dte_min=9, dte_max=5)


def test_template_rejects_a_typo_rather_than_ignoring_it():
    """A misspelled keyword silently doing nothing is how a cap stops applying."""
    with pytest.raises(ValidationError):
        Template(structure="put_credit", target_delta=0.25, width=5.0, max_spred_pct=0.5)


def test_template_rejects_an_unknown_structure():
    with pytest.raises(ValidationError):
        Template(structure="iron_condor", target_delta=0.25, width=5.0)


def spread(credit, width=5.0):
    return Spread(
        underlying="XYZ",
        structure="put_credit",
        expiry="2026-09-04",
        dte=7,
        short=sc(100, 1.50),
        long=sc(95, 1.50 - credit),
        width=width,
        spot=100.0,
        credit_mid=credit,
        credit_touch=credit - 0.05,
        max_loss=width - credit,
        short_delta=-0.25,
    )


def test_spread_refuses_a_credit_wider_than_its_width():
    """Credit above width implies negative max loss.

    Never an arbitrage -- it means a quote is stale, crossed, or one side has not traded.
    """
    with pytest.raises(ValidationError, match="not trustworthy"):
        spread(credit=6.0, width=5.0)


def test_spread_refuses_a_structure_that_does_not_credit():
    with pytest.raises(ValidationError, match="does not credit"):
        spread(credit=-0.10)


def test_spread_is_frozen():
    s = spread(credit=1.0)
    with pytest.raises(ValidationError):
        s.credit_mid = 99.0


def test_risk_limits_reject_a_percentage_entered_as_whole_number():
    """2% written as 20 rather than 0.02 would size every position 1000x too large."""
    with pytest.raises(ValidationError):
        RiskLimits(
            max_open_positions=10,
            max_loss_per_position_pct=20,
            max_total_defined_risk_pct=0.20,
            kill_switch_drawdown_pct=0.05,
        )


def test_the_shipped_limits_are_valid():
    from src.universe import LIMITS

    assert LIMITS.max_open_positions == 10
    assert LIMITS.max_loss_per_position_pct == 0.02
