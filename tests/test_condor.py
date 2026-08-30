"""`submit_condor`'s guardrails — the layer between a model's decision and a live order.

Each test corresponds to a rule, and most rules exist because of something that has already gone
wrong here or is one keystroke away. The sign test is the important one: `limit_price` on a
multi-leg order is a NET price where negative means credit, inverting it does not raise, and it
places a real order at the wrong price.
"""

import datetime

import pytest
from pydantic import ValidationError

from src.models import Quote
from src.options.condor import BookState, CondorPlan, CondorRequest, Veto, build_plan, validate
from src.options.iv import price
from src.universe import CONDOR_LIMITS

SPOT, IV, RATE = 766.0, 0.127, 0.04
TODAY = datetime.date(2026, 8, 31)
EXPIRY = datetime.date(2026, 9, 2)
JUDGED = "PA3BUA9MX72C"
GATES = dict(
    expected_account=JUDGED,
    last_entry=datetime.date(2026, 9, 2),
    max_expiry=datetime.date(2026, 9, 3),
    cash_floor=35_000.0,
)


def chain(spot=SPOT, iv=IV, expiry=EXPIRY, as_of=TODAY, wide=False):
    T = (expiry - as_of).days / 365.0
    edge = 0.30 if wide else 0.01
    out = {}
    for k in range(int(spot) - 70, int(spot) + 70):
        p, c = price(spot, k, T, RATE, iv, "P"), price(spot, k, T, RATE, iv, "C")
        out[float(k)] = (
            Quote(bp=max(0.01, p * (1 - edge)), ap=p * (1 + edge) + 0.01),
            Quote(bp=max(0.01, c * (1 - edge)), ap=c * (1 + edge) + 0.01),
        )
    return out


def request(**kw):
    base = dict(
        underlying="SPY",
        expiry=EXPIRY,
        short_delta=0.20,
        wing_width=5.0,
        contracts=14,
        rationale="Sep 2 tranche",
    )
    return CondorRequest(**{**base, **kw})


def plan(**kw):
    p = build_plan(request(**kw), SPOT, IV, chain(), as_of=TODAY, grid=1.0)
    assert isinstance(p, CondorPlan), p
    return p


def clean_book(**kw):
    base = dict(
        account_number=JUDGED,
        equity=100_000.0,
        high_water=100_000.0,
        cash=100_000.0,
        open_positions=0,
        open_defined_risk=0.0,
    )
    return BookState(**{**base, **kw})


# ---- the request schema is itself a guardrail


def test_the_model_cannot_express_a_price():
    """Sign inversion is removed from the model's reach rather than caught downstream."""
    assert "limit_price" not in CondorRequest.model_fields
    assert "credit" not in CondorRequest.model_fields
    with pytest.raises(ValidationError):
        CondorRequest(
            underlying="SPY",
            expiry=EXPIRY,
            short_delta=0.20,
            wing_width=5.0,
            contracts=1,
            rationale="x",
            limit_price=-1.20,
        )


def test_a_request_without_a_rationale_is_refused_by_the_schema():
    with pytest.raises(ValidationError):
        request(rationale="")


def test_absurd_deltas_are_refused_by_the_schema():
    for d in (0.01, 0.60):
        with pytest.raises(ValidationError):
            request(short_delta=d)


# ---- the plan asserts its own shape


def test_a_credit_structure_gets_a_negative_limit():
    p = plan()
    assert p.credit > 0
    assert p.limit_price == pytest.approx(-p.credit)


def test_a_positive_limit_on_a_credit_structure_cannot_be_constructed():
    p = plan()
    with pytest.raises(ValidationError, match="not a credit"):
        p.model_copy(update={"limit_price": abs(p.limit_price)}).model_validate(
            p.model_dump() | {"limit_price": abs(p.limit_price)}
        )


def test_strikes_must_be_ordered_as_a_condor():
    p = plan()
    with pytest.raises(ValidationError, match="not a condor"):
        CondorPlan.model_validate(p.model_dump() | {"short_put": p.short_call + 10})


def test_credit_above_width_is_refused_as_a_bad_quote():
    p = plan()
    with pytest.raises(ValidationError, match="stale or crossed"):
        CondorPlan.model_validate(
            p.model_dump() | {"credit": 6.0, "limit_price": -6.0, "wing_width": 5.0}
        )


def test_max_loss_and_defined_risk_reconcile():
    p = plan()
    assert p.max_loss_per_contract == pytest.approx((p.wing_width - p.credit) * 100)
    assert p.defined_risk == pytest.approx(p.max_loss_per_contract * p.contracts)


# ---- build refuses rather than guessing


def test_a_mid_based_credit_floor_cannot_see_spread_width():
    """The reason the touch floor exists.

    Widening a book symmetrically leaves the midpoint untouched, so the mid credit is identical on
    a 1-cent book and a 30%-wide one. A floor checked against mid says nothing about execution.
    """
    tight = build_plan(request(), SPOT, IV, chain(), as_of=TODAY, grid=1.0)
    wide = build_plan(request(), SPOT, IV, chain(wide=True), as_of=TODAY, grid=1.0)
    assert wide.credit == pytest.approx(tight.credit, abs=0.02)
    assert wide.credit_at_touch < tight.credit_at_touch


def test_a_wide_book_fails_on_crossing_cost():
    """Calibrated against measurement: the SPY round trip cost ~8% of credit."""
    wide = build_plan(request(), SPOT, IV, chain(wide=True), as_of=TODAY, grid=1.0)
    assert wide.spread_cost > 0.4
    v = validate(wide, clean_book(), CONDOR_LIMITS, as_of=TODAY, **GATES)
    assert any(x.rule == "02_credit" and "crossing" in x.reason for x in v)


def test_a_wide_book_also_fails_the_touch_floor():
    wide = build_plan(request(), SPOT, IV, chain(wide=True), as_of=TODAY, grid=1.0)
    v = validate(wide, clean_book(), CONDOR_LIMITS, as_of=TODAY, **GATES)
    assert any(x.rule == "02_credit" and "at the touch" in x.reason for x in v)


def test_a_tight_book_clears_both_floors():
    tight = build_plan(request(), SPOT, IV, chain(), as_of=TODAY, grid=1.0)
    assert not any(
        x.rule == "02_credit"
        for x in validate(tight, clean_book(), CONDOR_LIMITS, as_of=TODAY, **GATES)
    )


def test_a_missing_strike_returns_a_veto_not_an_exception():
    thin = {k: v for k, v in chain().items() if k % 10 == 0}
    got = build_plan(request(), SPOT, IV, thin, as_of=TODAY, grid=1.0)
    assert isinstance(got, Veto) and got.rule == "chain"


def test_a_past_expiry_is_refused():
    got = build_plan(
        request(expiry=datetime.date(2026, 8, 30)), SPOT, IV, chain(), as_of=TODAY, grid=1.0
    )
    assert isinstance(got, Veto) and got.rule == "expiry"


# ---- the rules


def test_a_clean_book_passes():
    assert validate(plan(), clean_book(), CONDOR_LIMITS, as_of=TODAY, **GATES) == []


def test_the_wrong_account_is_vetoed():
    v = validate(
        plan(), clean_book(account_number="PA382RL5C7X8"), CONDOR_LIMITS, as_of=TODAY, **GATES
    )
    assert [x.rule for x in v] == ["10_account"]
    assert "silent" in v[0].reason


def test_the_kill_switch_fires_on_mark_to_market_not_realized():
    """A realized-loss switch reads zero in a book that closes nothing."""
    v = validate(plan(), clean_book(equity=91_000.0), CONDOR_LIMITS, as_of=TODAY, **GATES)
    assert any(x.rule == "09_kill_switch" and "drawdown" in x.reason for x in v)


def test_the_kill_switch_also_fires_on_breach_count():
    v = validate(plan(), clean_book(breaches=2), CONDOR_LIMITS, as_of=TODAY, **GATES)
    assert any(x.rule == "09_kill_switch" and "breaches" in x.reason for x in v)


def test_limits_without_a_breach_switch_are_refused():
    from src.models import RiskLimits

    old = RiskLimits(
        max_open_positions=3,
        max_loss_per_position_pct=0.06,
        max_total_defined_risk_pct=0.16,
        kill_switch_drawdown_pct=0.08,
    )
    v = validate(plan(), clean_book(), old, as_of=TODAY, **GATES)
    assert any(x.rule == "11_limits" for x in v)


def test_entries_stop_after_the_deadline():
    v = validate(plan(), clean_book(), CONDOR_LIMITS, as_of=datetime.date(2026, 9, 3), **GATES)
    assert any(x.rule == "08_deadline" for x in v)


def test_an_expiry_past_the_scored_close_is_vetoed():
    """Equity is measured EOD Thu 3 Sep. A Friday expiry is marked, not settled."""
    p = build_plan(
        request(expiry=datetime.date(2026, 9, 4)),
        SPOT,
        IV,
        chain(expiry=datetime.date(2026, 9, 4)),
        as_of=TODAY,
        grid=1.0,
    )
    v = validate(p, clean_book(), CONDOR_LIMITS, as_of=TODAY, **GATES)
    assert any(x.rule == "06_expiry" and "marked rather than settled" in x.reason for x in v)


def test_the_cash_floor_binds():
    v = validate(plan(), clean_book(cash=36_000.0), CONDOR_LIMITS, as_of=TODAY, **GATES)
    assert any(x.rule == "07_cash" for x in v)


def test_the_position_count_cap_binds():
    v = validate(plan(), clean_book(open_positions=3), CONDOR_LIMITS, as_of=TODAY, **GATES)
    assert any(x.rule == "05_book" and "cap 3" in x.reason for x in v)


def test_the_book_risk_cap_binds():
    v = validate(
        plan(), clean_book(open_defined_risk=14_000.0), CONDOR_LIMITS, as_of=TODAY, **GATES
    )
    assert any(x.rule == "05_book" and "book risk" in x.reason for x in v)


def test_the_per_position_cap_binds():
    v = validate(plan(contracts=30), clean_book(), CONDOR_LIMITS, as_of=TODAY, **GATES)
    assert any(x.rule == "04_position" for x in v)


def test_a_strike_outside_the_delta_band_is_vetoed():
    p = plan(short_delta=0.35)
    v = validate(p, clean_book(), CONDOR_LIMITS, as_of=TODAY, **GATES)
    assert any(x.rule == "03_delta" for x in v)


def test_vetoes_are_ordered_and_name_their_rule():
    v = validate(
        plan(contracts=30),
        clean_book(account_number="X", breaches=5),
        CONDOR_LIMITS,
        as_of=TODAY,
        **GATES,
    )
    assert len(v) >= 3
    assert [x.rule for x in v] == sorted(x.rule for x in v)
    assert all(x.rule and x.reason for x in v)


def test_two_tranches_and_a_redeploy_fit_the_registered_book():
    """The ladder as designed must not need the limits raised to run."""
    one = plan().defined_risk
    assert one * 3 <= 100_000 * CONDOR_LIMITS.max_total_defined_risk_pct
    assert one <= 100_000 * CONDOR_LIMITS.max_loss_per_position_pct
