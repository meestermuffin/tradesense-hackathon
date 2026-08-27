"""Order construction and the sign conventions, which are the easiest thing here to get backwards.

`limit_price` on a multi-leg order is a NET price: positive is a debit, negative a credit. Opening
a credit spread therefore submits a negative limit and closing it submits a positive one. Getting
that inverted does not error -- it places a real order at the wrong price.
"""

import datetime

import pytest
from conftest import FakeClient

from src.models import FillRecord, Quote, Spread, StrikeCandidate
from src.options.execution import build_legs, cancel_if_resting, place


def sc(strike, symbol, bid, ask):
    return StrikeCandidate(
        strike=strike,
        symbol=symbol,
        mid=(bid + ask) / 2,
        iv=0.3,
        delta=-0.25,
        quote=Quote(bp=bid, ap=ask),
    )


SHORT, LONG = "XYZ100P", "XYZ095P"


def spread():
    return Spread(
        underlying="XYZ",
        structure="put_credit",
        expiry=datetime.date.today() + datetime.timedelta(days=7),
        dte=7,
        short=sc(100, SHORT, 1.45, 1.55),
        long=sc(95, LONG, 0.45, 0.55),
        width=5.0,
        spot=100.0,
        credit_mid=1.00,
        credit_touch=0.90,
        max_loss=4.00,
        short_delta=-0.25,
    )


def client(status="filled", fill=None):
    # short 1.45/1.55 (mid 1.50), long 0.45/0.55 (mid 0.50) -> net mid 1.00, opening touch 0.90
    return FakeClient(
        {100.0: (SHORT, 1.45, 1.55), 95.0: (LONG, 0.45, 0.55)},
        datetime.date.today() + datetime.timedelta(days=7),
        order_status=status,
        fill=fill,
    )


def test_opening_legs_sell_the_short_and_buy_the_wing():
    legs = build_legs(spread(), closing=False)
    assert [(x["symbol"], x["side"], x["position_intent"]) for x in legs] == [
        (SHORT, "sell", "sell_to_open"),
        (LONG, "buy", "buy_to_open"),
    ]


def test_closing_legs_are_the_exact_reverse():
    legs = build_legs(spread(), closing=True)
    assert [(x["symbol"], x["side"], x["position_intent"]) for x in legs] == [
        (SHORT, "buy", "buy_to_close"),
        (LONG, "sell", "sell_to_close"),
    ]


def test_opening_a_credit_spread_submits_a_negative_limit():
    c = client(fill=-1.00)
    place(c, spread(), 1)
    assert c.submitted[0]["limit_price"] == pytest.approx(-1.00)


def test_closing_submits_a_positive_limit():
    c = client(fill=1.00)
    place(c, spread(), 1, closing=True)
    assert c.submitted[0]["limit_price"] == pytest.approx(1.00)


def test_crossing_the_touch_prices_worse_for_us_when_opening():
    """Opening at the touch collects less than mid; `cross` gives up more to get filled."""
    c = client(fill=-0.85)
    place(c, spread(), 1, cross=0.05)
    # touch 0.90, cross 0.05 -> collect 0.85, submitted as a credit
    assert c.submitted[0]["limit_price"] == pytest.approx(-0.85)


def test_nbbo_is_captured_either_side_of_submission():
    """There is no historical quote endpoint. Uncaptured is unreconstructable, permanently."""
    rec = place(client(fill=-1.00), spread(), 1)
    assert rec.nbbo_pre is not None and rec.nbbo_post is not None
    assert rec.nbbo_pre.mid == pytest.approx(1.00)
    assert rec.nbbo_pre.touch == pytest.approx(0.90)
    assert rec.nbbo_pre.short.bid == 1.45 and rec.nbbo_pre.long.ask == 0.55


def test_a_better_than_mid_open_reads_positive_against_mid():
    """Collecting 1.10 on a 1.00 mid is price improvement, so vs_mid must be positive."""
    rec = place(client(fill=-1.10), spread(), 1)
    assert rec.vs_mid == pytest.approx(0.10)
    assert rec.vs_touch == pytest.approx(0.20)


def test_a_worse_than_mid_open_reads_negative():
    rec = place(client(fill=-0.95), spread(), 1)
    assert rec.vs_mid == pytest.approx(-0.05)


def test_paying_less_than_mid_to_close_reads_positive():
    """Closing is the mirror: paying 0.90 against a 1.00 mid is improvement."""
    rec = place(client(fill=0.90), spread(), 1, closing=True)
    assert rec.vs_mid == pytest.approx(0.10)


def test_missing_quote_returns_a_record_rather_than_placing():
    c = FakeClient({}, datetime.date.today() + datetime.timedelta(days=7))
    rec = place(c, spread(), 1)
    assert isinstance(rec, FillRecord)
    assert rec.ok is False and rec.filled is False
    assert c.submitted == []


def test_an_unfilled_order_is_cancelled_rather_than_left_resting():
    c = client(status="new", fill=None)
    rec = place(c, spread(), 1, poll_seconds=0)
    assert rec.filled is False
    assert cancel_if_resting(c, rec) is True


def test_a_filled_order_is_not_cancelled():
    c = client(fill=-1.00)
    rec = place(c, spread(), 1)
    assert rec.filled is True
    assert cancel_if_resting(c, rec) is False


def test_the_record_round_trips_through_json():
    """It is written to JSONL as evidence; the quotes in it can never be re-fetched."""
    rec = place(client(fill=-1.00), spread(), 1)
    again = FillRecord.model_validate_json(rec.model_dump_json())
    assert again == rec
