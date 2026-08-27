"""The caps, and the one that had stopped binding."""

import datetime

import pytest

from src.models import Position, Quote, Spread, StrikeCandidate
from src.risk import check_entry, defined_risk, round_trip_fees, size_position
from src.universe import KILL_SWITCH_DRAWDOWN_PCT, MAX_OPEN_POSITIONS


def sc(strike, mid, delta=-0.25):
    return StrikeCandidate(
        strike=strike,
        symbol=f"X{strike:g}",
        mid=mid,
        iv=0.3,
        delta=delta,
        quote=Quote(bp=mid - 0.05, ap=mid + 0.05),
    )


def spread(underlying="XYZ", credit=1.0, width=5.0, expiry=None):
    expiry = expiry or (datetime.date.today() + datetime.timedelta(days=7))
    return Spread(
        underlying=underlying,
        structure="put_credit",
        expiry=expiry,
        dte=7,
        short=sc(100, 1.5),
        long=sc(95, 1.5 - credit),
        width=width,
        spot=100.0,
        credit_mid=credit,
        credit_touch=credit - 0.05,
        max_loss=width - credit,
        short_delta=-0.25,
    )


def test_defined_risk_is_width_less_credit_times_multiplier():
    assert defined_risk(5.0, 1.0, 2) == pytest.approx(800.0)


def test_credit_at_or_above_width_has_no_risk_left_to_size():
    assert defined_risk(5.0, 5.0, 1) == 0.0


def test_size_position_respects_the_per_position_cap():
    # 2% of 100k = $2,000. One 5-wide spread at 1.00 credit risks $400 -> 5 contracts.
    n, why = size_position(100_000, 5.0, 1.0)
    assert (n, why) == (5, None)


def test_size_position_refuses_when_one_contract_breaches_the_cap():
    n, why = size_position(1_000, 5.0, 1.0)  # 2% of 1k = $20, one contract risks $400
    assert n == 0
    assert "over the" in why


def test_size_position_refuses_a_structure_with_no_defined_risk():
    n, why = size_position(100_000, 5.0, 5.0)
    assert n == 0
    assert "no defined risk" in why


def test_entry_allowed_on_a_clean_book():
    n, reasons = check_entry(spread(), 100_000, set(), 0.0, 100_000)
    assert reasons == []
    assert n == 5


def test_per_name_cap_binds_on_a_name_already_held():
    """This is the cap that had never fired -- `held` was OCC contract symbols, not underlyings."""
    held = {Position(symbol="XYZ260904P00100000").underlying}
    assert held == {"XYZ"}
    n, reasons = check_entry(spread(underlying="XYZ"), 100_000, held, 0.0, 100_000)
    assert n == 0
    assert any("already holding XYZ" in r for r in reasons)


def test_a_different_name_is_unaffected_by_the_per_name_cap():
    n, reasons = check_entry(spread(underlying="ABC"), 100_000, {"XYZ"}, 0.0, 100_000)
    assert reasons == []


def test_position_count_cap():
    held = {f"S{i}" for i in range(MAX_OPEN_POSITIONS)}
    n, reasons = check_entry(spread(underlying="NEW"), 100_000, held, 0.0, 100_000)
    assert n == 0
    assert any(f"cap is {MAX_OPEN_POSITIONS}" in r for r in reasons)


def test_total_defined_risk_cap():
    # 20% of 100k = $20,000 already committed leaves no room.
    n, reasons = check_entry(spread(), 100_000, set(), 20_000, 100_000)
    assert n == 0
    assert any("total defined risk" in r for r in reasons)


def test_kill_switch_fires_past_the_drawdown_threshold():
    high_water = 100_000
    equity = high_water * (1 - KILL_SWITCH_DRAWDOWN_PCT - 0.01)
    n, reasons = check_entry(spread(), equity, set(), 0.0, high_water)
    assert n == 0
    assert any("kill switch" in r for r in reasons)


def test_kill_switch_silent_just_inside_the_threshold():
    high_water = 100_000
    equity = high_water * (1 - KILL_SWITCH_DRAWDOWN_PCT + 0.01)
    _, reasons = check_entry(spread(), equity, set(), 0.0, high_water)
    assert not any("kill switch" in r for r in reasons)


def test_expiry_past_the_deadline_is_refused():
    """The judged window ends; a position that outlives it cannot be closed inside it."""
    deadline = datetime.date.today() + datetime.timedelta(days=3)
    n, reasons = check_entry(spread(), 100_000, set(), 0.0, 100_000, deadline=deadline)
    assert n == 0
    assert any("past the deadline" in r for r in reasons)


def test_earnings_inside_the_holding_window_is_refused():
    as_of = datetime.date.today()
    expiry = as_of + datetime.timedelta(days=7)
    reports = (as_of + datetime.timedelta(days=3)).isoformat()
    n, reasons = check_entry(
        spread(expiry=expiry),
        100_000,
        set(),
        0.0,
        100_000,
        earnings_dates={"XYZ": [reports]},
        as_of=as_of,
    )
    assert n == 0
    assert any("reports" in r for r in reasons)


def test_earnings_after_expiry_is_not_a_reason_to_refuse():
    as_of = datetime.date.today()
    expiry = as_of + datetime.timedelta(days=7)
    after = (expiry + datetime.timedelta(days=5)).isoformat()
    _, reasons = check_entry(
        spread(expiry=expiry),
        100_000,
        set(),
        0.0,
        100_000,
        earnings_dates={"XYZ": [after]},
        as_of=as_of,
    )
    assert reasons == []


def test_round_trip_fees_charge_both_legs_both_ways():
    # $0.025 per contract-leg, measured twice on 2026-08-26.
    assert round_trip_fees(1) == pytest.approx(0.10)
    assert round_trip_fees(5) == pytest.approx(0.50)
