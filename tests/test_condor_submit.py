"""Placing the condor: leg construction, the sign, and the journal wrapper.

The sign is the one that matters. `limit_price` on a multi-leg order is a NET price where negative
means credit, and inverting it does not raise -- it places a real order at the wrong price. The
invariant lives on `CondorPlan`, so these tests check it survives the trip to the wire.
"""

import datetime as dt

import pytest

from src.models import CondorFill, Order, OrderLeg, Quote
from src.options.condor import (
    BookState,
    CondorPlan,
    CondorRequest,
    Veto,
    _occ,
    build_legs,
    build_plan,
    submit,
    validate,
)
from src.options.iv import price
from src.universe import CONDOR_LIMITS

SPOT, IV, RATE = 766.0, 0.127, 0.04
TODAY, EXPIRY = dt.date(2026, 8, 31), dt.date(2026, 9, 2)
JUDGED = "PA3BUA9MX72C"


def chain():
    T = (EXPIRY - TODAY).days / 365.0
    out = {}
    for k in range(int(SPOT) - 40, int(SPOT) + 40):
        p, c = price(SPOT, k, T, RATE, IV, "P"), price(SPOT, k, T, RATE, IV, "C")
        out[float(k)] = (
            Quote(bp=max(0.01, p * 0.99), ap=p * 1.01 + 0.01),
            Quote(bp=max(0.01, c * 0.99), ap=c * 1.01 + 0.01),
        )
    return out


def a_plan():
    req = CondorRequest(
        underlying="SPY",
        expiry=EXPIRY,
        short_delta=0.20,
        wing_width=5.0,
        contracts=14,
        rationale="tranche 1",
    )
    p = build_plan(req, SPOT, IV, chain(), as_of=TODAY, grid=1.0)
    assert isinstance(p, CondorPlan), p
    return p


class FakeClient:
    def __init__(self, status="filled", fill=-1.24):
        self.status, self.fill, self.submitted = status, fill, []

    def submit_mleg(self, legs, qty, limit_price, tif="day"):
        self.submitted.append({"legs": legs, "qty": qty, "limit_price": limit_price})
        return Order(
            id="ord-1",
            status=self.status,
            filled_avg_price=self.fill,
            filled_at="2026-08-31T14:00:00Z" if self.status == "filled" else None,
            legs=[OrderLeg(symbol=x["symbol"], side=x["side"], filled_avg_price=0.5) for x in legs],
        )

    def get_order(self, oid):
        return Order(id=oid, status=self.status, filled_avg_price=self.fill)


# ---- OCC symbols


def test_occ_symbols_match_the_exchange_format():
    """Verified against the live SPY chain: 6/6 real strikes matched on 2026-08-30."""
    p = a_plan()
    assert _occ(p, 760.0, "P") == "SPY260902P00760000"
    assert _occ(p, 772.0, "C") == "SPY260902C00772000"
    assert len(_occ(p, 760.0, "P")) == len("SPY") + 6 + 1 + 8


def test_occ_encodes_strikes_in_thousandths():
    p = a_plan()
    assert _occ(p, 5.0, "P").endswith("00005000")
    assert _occ(p, 1234.5, "C").endswith("01234500")


# ---- legs


def test_both_wings_are_bought_and_both_bodies_sold():
    """An mleg order needs every leg covered; a naked short is rejected outright."""
    legs = build_legs(a_plan())
    sides = [x["side"] for x in legs]
    assert sides == ["buy", "sell", "sell", "buy"]
    assert all(x["position_intent"].endswith("_open") for x in legs)


def test_four_legs_exactly():
    """Alpaca's mleg schema caps at four, and a condor uses all of them."""
    assert len(build_legs(a_plan())) == 4


# ---- the sign


def test_the_limit_reaching_the_wire_is_negative():
    c = FakeClient()
    submit(c, a_plan())
    assert c.submitted[0]["limit_price"] < 0, "positive would pay to open a credit structure"


def test_the_wire_limit_is_exactly_the_plan_limit():
    p, c = a_plan(), FakeClient()
    submit(c, p)
    assert c.submitted[0]["limit_price"] == p.limit_price == -p.credit


def test_contracts_reach_the_wire_unmodified():
    p, c = a_plan(), FakeClient()
    submit(c, p)
    assert c.submitted[0]["qty"] == p.contracts == 14


# ---- vetoes are honoured, not merely recorded


def test_a_veto_refuses_and_places_nothing():
    c = FakeClient()
    got = submit(c, a_plan(), vetoes=[Veto(rule="10_account", reason="wrong book")])
    assert got.ok is False
    assert c.submitted == [], "a vetoed plan must not reach the wire"
    assert "wrong book" in got.error


def test_the_refusal_carries_every_rule_that_fired():
    got = submit(
        FakeClient(), a_plan(), vetoes=[Veto(rule="a", reason="one"), Veto(rule="b", reason="two")]
    )
    assert len(got.vetoes) == 2


def test_validate_and_submit_agree_on_a_clean_book():
    p = a_plan()
    state = BookState(
        account_number=JUDGED,
        equity=100_000.0,
        high_water=100_000.0,
        cash=100_000.0,
        open_positions=0,
        open_defined_risk=0.0,
    )
    v = validate(
        p,
        state,
        CONDOR_LIMITS,
        expected_account=JUDGED,
        as_of=TODAY,
        last_entry=dt.date(2026, 9, 2),
        max_expiry=dt.date(2026, 9, 3),
        cash_floor=35_000.0,
    )
    assert v == []
    c = FakeClient()
    assert submit(c, p, vetoes=v).ok is True
    assert len(c.submitted) == 1


# ---- the result


def test_price_improvement_reads_positive():
    """Collecting more than mid is improvement. `fill` is a net price, so it compares
    on magnitude."""
    p = a_plan()
    got = submit(FakeClient(fill=-(p.credit + 0.10)), p)
    assert got.vs_mid == pytest.approx(0.10)


def test_a_worse_than_mid_fill_reads_negative():
    p = a_plan()
    assert submit(FakeClient(fill=-(p.credit - 0.05)), p).vs_mid == pytest.approx(-0.05)


def test_an_unfilled_order_reports_so_without_a_fill_price():
    got = submit(FakeClient(status="new", fill=None), a_plan(), poll_seconds=0)
    assert got.filled is False and got.fill is None and got.vs_mid is None


def test_leg_fills_carry_signed_quantities():
    got = submit(FakeClient(), a_plan())
    assert len(got.legs) == 4
    assert sum(1 for x in got.legs if x.signed_qty < 0) == 2, "two short legs"
    assert sum(1 for x in got.legs if x.signed_qty > 0) == 2, "two bought wings"


def test_the_record_round_trips_through_json():
    """It is written as evidence; the NBBO in it can never be re-fetched."""
    got = submit(FakeClient(), a_plan())
    assert CondorFill.model_validate_json(got.model_dump_json()) == got


# ---- journal integration


class FakeSub:
    def __init__(self):
        self.vetoes, self.orders, self.fills = [], [], []

    @property
    def vetoed(self):
        return bool(self.vetoes)

    def veto(self, rule, detail):
        self.vetoes.append((rule, detail))

    def submitted(self, intended, order_id=None, status=None, response=None):
        self.orders.append((intended, order_id, status))
        return 1

    def filled(self, legs):
        self.fills.extend(legs)
        return legs


class FakeRecorder:
    def __init__(self):
        self.sub, self.kwargs = FakeSub(), None

    def submission(self, **kw):
        self.kwargs = kw
        rec = self

        class _Ctx:
            def __enter__(self):
                return rec.sub

            def __exit__(self, *a):
                return False

        return _Ctx()


def test_the_journal_is_given_every_leg_symbol_to_capture_nbbo():
    """Without `symbols` no NBBO is captured, and every fill is unreconcilable afterwards --
    there is no historical options quote endpoint on this account."""
    r = FakeRecorder()
    submit(FakeClient(), a_plan(), recorder=r)
    assert len(r.kwargs["symbols"]) == 4
    assert all(s.startswith("SPY2609") for s in r.kwargs["symbols"])


def test_the_journal_records_the_net_limit_as_intent():
    r = FakeRecorder()
    p = a_plan()
    submit(FakeClient(), p, recorder=r)
    assert r.kwargs["intent"]["net_limit"] == p.limit_price
    assert r.sub.orders[0][1] == "ord-1"


def test_vetoes_are_journalled_before_the_refusal():
    r = FakeRecorder()
    got = submit(
        FakeClient(), a_plan(), recorder=r, vetoes=[Veto(rule="09_kill_switch", reason="breached")]
    )
    assert r.sub.vetoes[0][0] == "09_kill_switch"
    assert r.sub.orders == [], "nothing submitted after a veto"
    assert got.ok is False


def test_filled_legs_reach_the_journal_with_the_keys_it_indexes():
    r = FakeRecorder()
    submit(FakeClient(), a_plan(), recorder=r)
    assert len(r.sub.fills) == 4
    for leg_ in r.sub.fills:
        assert leg_["symbol"] and leg_["signed_qty"] is not None
        assert leg_["side"] in ("buy", "sell"), "explicit side, never inferred"
