"""The agent loop: what it decides, and what it is not allowed to decide.

Written before the implementation. The decisions worth testing are the ones with a registered
threshold behind them -- the ladder schedule and the Tuesday gate -- because those are the places
where a wrong answer places or withholds real money, and both were argued about at length before
being written down.

The rest of the loop is orchestration over pieces already tested elsewhere: `build_plan` and
`validate` in test_condor.py, `submit` in test_condor_submit.py, the markwatch bridge in
test_adapter.py.
"""

import datetime as dt

import pytest

from src.agent.loop import (
    LADDER,
    AgentLoop,
    TrancheSpec,
    book_state,
    tranches_for,
    tuesday_gate,
)
from src.models import CondorFill
from src.options.condor import BookState, Veto

MON, TUE, WED, THU = (dt.date(2026, 8, 31), dt.date(2026, 9, 1),
                      dt.date(2026, 9, 2), dt.date(2026, 9, 3))


# ---- the ladder schedule


def test_monday_opens_two_tranches():
    got = tranches_for(MON)
    assert len(got) == 2
    assert {t.expiry for t in got} == {dt.date(2026, 9, 2), dt.date(2026, 9, 3)}
    assert all(t.conditional is False for t in got), "Monday's two are committed"


def test_tuesday_offers_one_conditional_tranche():
    got = tranches_for(TUE)
    assert len(got) == 1
    assert got[0].expiry == dt.date(2026, 9, 3)
    assert got[0].conditional is True, "gated on the fill and the regime, not committed"


def test_wednesday_and_thursday_open_nothing():
    """The Wednesday redeploy was cut on gamma: 1 DTE is worst on every axis."""
    assert tranches_for(WED) == []
    assert tranches_for(THU) == []


def test_no_tranche_expires_after_the_scored_close():
    """Equity is measured EOD Thu 3 Sep. A later expiry is marked, not settled."""
    for specs in (tranches_for(MON), tranches_for(TUE)):
        for t in specs:
            assert t.expiry <= dt.date(2026, 9, 3)


def test_every_tranche_is_at_least_two_dte():
    """1 DTE was cut on gamma -- net structure gamma 0.0822 against 0.0438 at 2 DTE."""
    for day in (MON, TUE):
        for t in tranches_for(day):
            assert (t.expiry - day).days >= 2


def test_the_ladder_is_declared_data_not_derived():
    """It is a registered decision. It should be readable, not computed at runtime."""
    assert isinstance(LADDER, tuple)
    assert all(isinstance(x, TrancheSpec) for x in LADDER)


# ---- the Tuesday gate, both registered conditions


def test_the_gate_opens_when_both_conditions_hold():
    ok, why = tuesday_gate(fill_vs_mid=-0.02, live_iv=0.13)
    assert ok is True
    assert why == ""


def test_a_poor_monday_fill_closes_the_gate():
    """EV is +$21 to +$34 at mid fills and +$1 to +$14 at the touch. The sign lives on the fill."""
    ok, why = tuesday_gate(fill_vs_mid=-0.12, live_iv=0.13)
    assert ok is False
    assert "fill" in why.lower()


def test_elevated_iv_closes_the_gate():
    """EV is -$38 to -$47 unconditional; positive only conditioned on calm entry IV."""
    ok, why = tuesday_gate(fill_vs_mid=-0.01, live_iv=0.22)
    assert ok is False
    assert "iv" in why.lower()


def test_the_gate_reports_every_failing_condition_not_just_the_first():
    ok, why = tuesday_gate(fill_vs_mid=-0.30, live_iv=0.25)
    assert ok is False
    assert "fill" in why.lower() and "iv" in why.lower()


def test_a_missing_monday_fill_closes_the_gate():
    """No fill means the probe never resolved. Absence is not permission."""
    ok, why = tuesday_gate(fill_vs_mid=None, live_iv=0.13)
    assert ok is False


@pytest.mark.parametrize("vs_mid,expected", [(-0.05, True), (-0.051, False)])
def test_the_fill_threshold_is_exactly_mid_minus_five_cents(vs_mid, expected):
    assert tuesday_gate(fill_vs_mid=vs_mid, live_iv=0.13)[0] is expected


@pytest.mark.parametrize("iv,expected", [(0.16, True), (0.161, False)])
def test_the_iv_threshold_is_exactly_sixteen(iv, expected):
    assert tuesday_gate(fill_vs_mid=-0.01, live_iv=iv)[0] is expected


# ---- book state comes from the broker, never from cache


def test_book_state_is_built_from_broker_payloads():
    """Local state is a cache and never truth: every wake re-reads and reconciles."""
    acct = {"account_number": "PA3BUA9MX72C", "equity": "98000", "cash": "90000"}
    positions = [
        {"symbol": "SPY260902P00760000", "qty": "-14", "asset_class": "us_option"},
        {"symbol": "SPY260902P00755000", "qty": "14", "asset_class": "us_option"},
    ]
    st = book_state(acct, positions, high_water=100_000.0, open_defined_risk=5264.0)
    assert isinstance(st, BookState)
    assert st.account_number == "PA3BUA9MX72C"
    assert st.equity == 98_000.0
    assert st.cash == 90_000.0
    assert st.high_water == 100_000.0


def test_open_positions_counts_spreads_not_legs():
    """Four legs is one condor. Counting legs would trip the position cap after one entry."""
    legs = [{"symbol": f"SPY260902{cp}00{k}000", "qty": q, "asset_class": "us_option"}
            for cp, k, q in (("P", "755", "14"), ("P", "760", "-14"),
                             ("C", "772", "-14"), ("C", "777", "14"))]
    st = book_state({"account_number": "X", "equity": "100000", "cash": "100000"},
                    legs, high_water=100_000.0, open_defined_risk=0.0)
    assert st.open_positions == 1, f"4 legs is 1 condor, got {st.open_positions}"


def test_equity_positions_are_ignored_when_counting_the_options_book():
    rows = [{"symbol": "AAPL", "qty": "10", "asset_class": "us_equity"}]
    st = book_state({"account_number": "X", "equity": "100000", "cash": "100000"},
                    rows, high_water=100_000.0, open_defined_risk=0.0)
    assert st.open_positions == 0


def test_high_water_never_falls_below_current_equity():
    """Drawdown is measured against a running peak; a peak below spot would read negative."""
    st = book_state({"account_number": "X", "equity": "105000", "cash": "100000"},
                    [], high_water=100_000.0, open_defined_risk=0.0)
    assert st.high_water >= st.equity


# ---- what the loop refuses to do


def test_the_loop_never_constructs_a_limit_price():
    """The model emits a CondorRequest, which has no price field. submit_condor computes the net.

    This is enforced by schema, not by instruction: sign inversion is removed from reach rather
    than caught downstream.
    """
    import inspect

    from src.agent import loop as m

    src = inspect.getsource(m)
    assert "limit_price=" not in src, "the loop must never name a limit price"


def test_a_dry_run_places_nothing():
    calls = []

    class C:
        def submit_mleg(self, *a, **k):
            calls.append(a)
            raise AssertionError("dry run must not reach the wire")

    loop = AgentLoop(client=C(), dry_run=True)
    assert loop.dry_run is True
    assert calls == []


def test_vetoes_block_submission_and_are_returned():
    """A refusal is a first-class result the journal and the model can both read."""
    fill = CondorFill(
        ok=False, error="[10_account] wrong book", underlying="SPY",
        expiry=dt.date(2026, 9, 2), contracts=1, limit_price=-1.0,
        credit_at_mid=1.0, submitted_at="2026-08-31T14:00:00Z",
        vetoes=["[10_account] wrong book"],
    )
    assert fill.ok is False and fill.vetoes


# ---- the session runner: ordering, and what must happen before the first order


def test_markwatch_must_start_before_any_order_is_placed():
    """Quotes do not exist after the fact on this account.

    If the collector is not up before the first entry, the mark-drift question is unanswerable for
    the whole window -- and that question decides whether the scored number is a price we could
    have got.
    """
    from src.agent.loop import SessionPlan

    p = SessionPlan.for_session(MON)
    order = [s.name for s in p.steps]
    assert order.index("start_markwatch") < order.index("enter_tranches")


def test_the_fill_probe_runs_before_any_sized_entry():
    """Registered in docs/pending/condor-fill-realism.md: one lot, before sizing."""
    from src.agent.loop import SessionPlan

    order = [s.name for s in SessionPlan.for_session(MON).steps]
    assert order.index("fill_probe") < order.index("enter_tranches")


def test_monday_reconciles_before_it_decides():
    from src.agent.loop import SessionPlan

    order = [s.name for s in SessionPlan.for_session(MON).steps]
    assert order.index("observe") < order.index("enter_tranches")


def test_tuesday_evaluates_the_gate_and_has_no_fill_probe():
    """The probe is Monday's. Tuesday reads its result rather than repeating it."""
    from src.agent.loop import SessionPlan

    names = [s.name for s in SessionPlan.for_session(TUE).steps]
    assert "evaluate_gate" in names
    assert "fill_probe" not in names


def test_wednesday_and_thursday_are_monitor_only():
    from src.agent.loop import SessionPlan

    for day in (WED, THU):
        names = [s.name for s in SessionPlan.for_session(day).steps]
        assert "enter_tranches" not in names, f"{day} must not open anything"
        assert "pin_check" in names, f"{day} carries expiring positions"


def test_thursday_pin_check_precedes_the_scored_close():
    """Spot inside a wing at the close means assignment, and ITM settles T+1 -- which straddles
    the snapshot."""
    from src.agent.loop import SCORED_CLOSE, SessionPlan

    p = SessionPlan.for_session(THU)
    assert THU == SCORED_CLOSE
    assert any(s.name == "pin_check" for s in p.steps)


def test_every_step_carries_the_time_it_runs():
    from src.agent.loop import SessionPlan

    for day in (MON, TUE, WED, THU):
        for s in SessionPlan.for_session(day).steps:
            assert s.at is not None, f"{day} {s.name} has no scheduled time"


def test_a_session_outside_the_window_plans_nothing():
    from src.agent.loop import SessionPlan

    assert SessionPlan.for_session(dt.date(2026, 9, 7)).steps == ()


# ---- the tick: what one wake actually does


class _Client:
    """Enough of AlpacaClient for the loop, with the wire calls recorded."""

    trade_host = "https://paper-api.alpaca.markets"

    def __init__(self, account=None, positions=None, spot=766.0):
        self._a = account or {"account_number": "PA3BUA9MX72C", "equity": "100000",
                              "cash": "100000"}
        self._p = positions or []
        self.spot = spot
        self.submitted = []

    def request(self, method, host, path, params=None, body=None, **kw):
        if path == "/v2/account":
            return self._a
        if path == "/v2/positions":
            return self._p
        raise AssertionError(path)

    def stock_closes_latest(self, syms):
        return dict.fromkeys(syms, self.spot)

    def submit_mleg(self, legs, qty, limit_price, tif="day"):
        self.submitted.append(limit_price)
        raise AssertionError("no test here should reach the wire")


def test_a_tick_on_a_day_with_no_tranches_decides_nothing():
    loop = AgentLoop(client=_Client(), dry_run=True, expected_account="PA3BUA9MX72C")
    assert loop.tick(WED, high_water=100_000.0) == []


def test_monday_tick_produces_one_decision_per_tranche():
    loop = AgentLoop(client=_Client(), dry_run=True, expected_account="PA3BUA9MX72C")
    got = loop.tick(MON, high_water=100_000.0)
    assert len(got) == 2
    assert {d.spec.expiry for d in got} == {dt.date(2026, 9, 2), dt.date(2026, 9, 3)}


def test_a_dry_run_tick_reaches_a_plan_but_never_the_wire():
    c = _Client()
    got = AgentLoop(client=c, dry_run=True, expected_account="PA3BUA9MX72C").tick(
        MON, high_water=100_000.0
    )
    assert c.submitted == []
    assert all(d.plan is not None or d.vetoes for d in got)


def test_the_wrong_account_vetoes_every_tranche():
    """Trading the rehearsal book is the only error here that produces no signal at all."""
    c = _Client(account={"account_number": "PA382RL5C7X8", "equity": "100000", "cash": "100000"})
    got = AgentLoop(client=c, dry_run=True, expected_account="PA3BUA9MX72C").tick(
        MON, high_water=100_000.0
    )
    assert got and all(any("10_account" in v for v in d.vetoes) for d in got)
    assert c.submitted == []


def test_tuesday_is_skipped_when_the_gate_is_shut():
    loop = AgentLoop(client=_Client(), dry_run=True, expected_account="PA3BUA9MX72C")
    got = loop.tick(TUE, high_water=100_000.0, fill_vs_mid=-0.40, live_iv=0.30)
    assert len(got) == 1
    assert got[0].skipped is True
    assert got[0].plan is None
    assert "fill" in got[0].reason.lower()


def test_tuesday_proceeds_when_the_gate_opens():
    loop = AgentLoop(client=_Client(), dry_run=True, expected_account="PA3BUA9MX72C")
    got = loop.tick(TUE, high_water=100_000.0, fill_vs_mid=-0.01, live_iv=0.13)
    assert got[0].skipped is False


def test_tuesday_without_gate_inputs_is_skipped_not_guessed():
    loop = AgentLoop(client=_Client(), dry_run=True, expected_account="PA3BUA9MX72C")
    assert loop.tick(TUE, high_water=100_000.0)[0].skipped is True


def test_a_committed_tranche_ignores_the_gate_entirely():
    """Monday's two are committed. The gate governs the conditional tranche only."""
    loop = AgentLoop(client=_Client(), dry_run=True, expected_account="PA3BUA9MX72C")
    got = loop.tick(MON, high_water=100_000.0, fill_vs_mid=-0.99, live_iv=0.99)
    assert all(d.skipped is False for d in got)


def test_live_mode_refuses_without_a_running_collector():
    """markwatch must be up before the first order: quotes do not exist after the fact here,
    so a fill placed before it starts is unreconcilable forever."""
    loop = AgentLoop(client=_Client(), dry_run=False, expected_account="PA3BUA9MX72C")
    with pytest.raises(RuntimeError, match="markwatch"):
        loop.tick(MON, high_water=100_000.0)


def test_live_mode_proceeds_once_the_collector_is_declared_running():
    c = _Client()
    loop = AgentLoop(client=c, dry_run=False, expected_account="PA3BUA9MX72C",
                     collector_running=True)
    got = loop.tick(MON, high_water=100_000.0)
    assert len(got) == 2


# ---- sizing must respect the book, not just the position


def test_three_tranches_at_the_position_cap_would_breach_the_book_cap():
    """The arithmetic that makes the next test necessary.

    Per-position is 6% and the book is 16%. Three tranches sized only against the position cap
    come to 18%, so the third would be refused on book risk after the first two are already on --
    the worst time to discover it.
    """
    from src.universe import CONDOR_LIMITS as L

    assert 3 * L.max_loss_per_position_pct > L.max_total_defined_risk_pct


def test_sizing_leaves_room_for_the_tranches_still_to_come():
    """Monday must not consume the budget Tuesday's conditional tranche needs."""
    loop = AgentLoop(client=_Client(), dry_run=True, expected_account="PA3BUA9MX72C")
    got = loop.tick(MON, high_water=100_000.0, quotes=_chain(), spot=766.0)
    assert len(got) == 2
    total = sum(d.plan.defined_risk for d in got if d.plan)
    room = 100_000 * loop.limits.max_total_defined_risk_pct
    assert total <= room * 2 / 3 + 1, (
        f"Monday used ${total:,.0f} of ${room:,.0f}; the third tranche needs a share"
    )


def test_each_tranche_still_respects_the_per_position_cap():
    loop = AgentLoop(client=_Client(), dry_run=True, expected_account="PA3BUA9MX72C")
    for d in loop.tick(MON, high_water=100_000.0, quotes=_chain(), spot=766.0):
        if d.plan:
            assert d.plan.defined_risk <= 100_000 * loop.limits.max_loss_per_position_pct


def test_all_three_tranches_together_fit_the_registered_book():
    """The whole ladder, sized as the loop would size it, must not breach 16%."""
    loop = AgentLoop(client=_Client(), dry_run=True, expected_account="PA3BUA9MX72C")
    mon = loop.tick(MON, high_water=100_000.0, quotes=_chain(), spot=766.0)
    tue = loop.tick(TUE, high_water=100_000.0, fill_vs_mid=-0.01, live_iv=0.13,
                    quotes=_chain(expiry=dt.date(2026, 9, 3)), spot=766.0)
    total = sum(d.plan.defined_risk for d in mon + tue if d.plan)
    assert total <= 100_000 * loop.limits.max_total_defined_risk_pct


def _chain(expiry=None, spot=766.0, iv=0.127):
    from src.models import Quote
    from src.options.iv import price

    expiry = expiry or dt.date(2026, 9, 2)
    T = (expiry - MON).days / 365.0
    out = {}
    for k in range(int(spot) - 40, int(spot) + 40):
        p, c = price(spot, k, T, 0.04, iv, "P"), price(spot, k, T, 0.04, iv, "C")
        out[float(k)] = (Quote(bp=max(0.01, p * 0.99), ap=p * 1.01 + 0.01),
                         Quote(bp=max(0.01, c * 0.99), ap=c * 1.01 + 0.01))
    return out
