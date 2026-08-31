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


# ---- skew: found by the model reviewer, 2026-08-31


def skewed_chain(spot=766.0, atm=0.13, slope=0.0025):
    """A chain with equity put skew: OTM puts richer, OTM calls cheaper."""
    from src.models import Quote
    from src.options.iv import price

    T = (EXPIRY - TODAY).days / 365.0
    out = {}
    for k in range(int(spot) - 40, int(spot) + 40):
        iv = atm + slope * (spot - k)  # rises below spot, falls above
        iv = max(0.05, iv)
        p, c = price(spot, k, T, RATE, iv, "P"), price(spot, k, T, RATE, iv, "C")
        out[float(k)] = (
            Quote(bp=max(0.01, p * 0.995), ap=p * 1.005 + 0.01),
            Quote(bp=max(0.01, c * 0.995), ap=c * 1.005 + 0.01),
        )
    return out


def test_reported_deltas_use_each_strikes_own_vol():
    """The defect the model caught: a flat ATM vol reports deltas that do not describe the book.

    Measured live at spot 769.28 — flat 0.1343 put the 763 put and 776 call both near 0.197, while
    their own quotes inverted to 0.1488 and 0.1201, making the true deltas 0.221 and 0.171. The put
    was outside the band and the call well below it, and guardrail #3 passed both.
    """
    p = build_plan(request(), SPOT, 0.13, skewed_chain(), as_of=TODAY, grid=1.0)
    assert isinstance(p, CondorPlan)
    # Under skew the two sides cannot both sit at the same delta if one flat vol were used.
    assert p.short_put_delta != pytest.approx(p.short_call_delta, abs=1e-6)


def test_strikes_are_solved_on_the_skew_surface_and_land_in_band():
    """Solving flat and measuring on skew puts the strikes outside the band. Both must agree."""
    p = build_plan(request(), SPOT, 0.13, skewed_chain(), as_of=TODAY, grid=1.0)
    assert 0.15 <= p.short_put_delta <= 0.27
    assert 0.15 <= p.short_call_delta <= 0.27


def test_a_flat_chain_still_works():
    """No skew is a valid market. The skew solve must not require skew to exist."""
    p = build_plan(request(), SPOT, IV, chain(), as_of=TODAY, grid=1.0)
    assert isinstance(p, CondorPlan)
    assert p.short_put_delta > 0 and p.short_call_delta > 0


def test_an_unquotable_chain_falls_back_to_the_flat_solve():
    """When nothing inverts there is no surface to solve on; the flat path must still produce."""
    from src.models import Quote

    dead = {k: (Quote(bp=0.0, ap=0.0), Quote(bp=0.0, ap=0.0)) for k in chain()}
    got = build_plan(request(), SPOT, IV, dead, as_of=TODAY, grid=1.0)
    assert isinstance(got, Veto), "no two-sided quote anywhere is a refusal, not a crash"


# ---- band-edge targets: found on the judged account, 2026-08-31 03:00


def test_a_band_edge_target_still_lands_inside_the_band():
    """The solver must satisfy the guardrail it will be judged by, not merely get close.

    Found on the first dry run against the judged account. The model may tighten the short delta
    anywhere inside [0.18, 0.22], and picking the strike with the smallest gap to that target is
    not the same as picking one the band accepts. On the 3 Sep chain the listed calls bracketed
    the target: 776C at 0.211 and 777C at 0.179. Any target below 0.195 makes 777C the nearer of
    the two, so a tightening to 0.19 -- squarely inside the band and exactly what the model is
    allowed to ask for -- selected a strike that guardrail 03 then refused by 0.001. The tranche
    was lost to strike granularity, with an acceptable strike sitting one point away.
    """
    for target in (0.180, 0.185, 0.190, 0.195, 0.200, 0.215, 0.220):
        p = build_plan(
            request(short_delta=target), SPOT, 0.13, skewed_chain(), as_of=TODAY, grid=1.0
        )
        assert isinstance(p, CondorPlan), f"target {target}: {p}"
        assert 0.18 <= p.short_put_delta <= 0.22, f"target {target}: put {p.short_put_delta:.3f}"
        assert 0.18 <= p.short_call_delta <= 0.22, f"target {target}: call {p.short_call_delta:.3f}"


def test_an_in_band_strike_beats_a_nearer_out_of_band_one():
    """Preference is ordinal: any in-band strike outranks every out-of-band one, however near."""
    from src.options.condor import _strike_on_skew

    got = _strike_on_skew(
        skewed_chain(),
        SPOT,
        dte=2,
        target=0.18,
        cp="C",
        rate=RATE,
        fallback_iv=0.13,
        band=(0.18, 0.22),
    )
    assert got is not None
    from src.options.iv import greeks, implied_vol

    q = skewed_chain()[got][1]
    own = implied_vol(q.mid, SPOT, got, 2 / 365.0, RATE, "C")
    assert 0.18 <= abs(greeks(SPOT, got, 2 / 365.0, RATE, own, "C")["delta"]) <= 0.22


def test_no_in_band_strike_falls_back_to_nearest():
    """A chain too coarse to offer an in-band strike must still produce a plan, not vanish.

    The guardrail refuses it afterwards; that refusal is the correct outcome and is not the
    solver's to pre-empt.
    """
    from src.options.condor import _strike_on_skew

    coarse = {k: v for k, v in skewed_chain().items() if int(k) % 25 == 0}
    got = _strike_on_skew(
        coarse, SPOT, dte=2, target=0.20, cp="C", rate=RATE, fallback_iv=0.13, band=(0.18, 0.22)
    )
    assert got is not None


def test_the_solver_never_launders_an_out_of_band_request():
    """Band preference must not rescue a request the band forbids.

    Steering toward the band is for honouring a legitimate target that strike granularity would
    otherwise push outside it. Applied to a target the band already rejects, the same steering
    would silently return a compliant strike and leave guardrail 03 with nothing to fire on --
    turning a refusal into a fill. The preference is therefore conditional on the target itself.
    """
    p = plan(short_delta=0.35)
    v = validate(p, clean_book(), CONDOR_LIMITS, as_of=TODAY, **GATES)
    assert any(x.rule == "03_delta" for x in v), "an out-of-band request must still be refused"
