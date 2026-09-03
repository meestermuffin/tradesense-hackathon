"""Closing a condor: the mirrored sign invariant.

Issue #33. `CondorPlan` refuses to construct with a non-credit limit, so an opening order cannot
carry the wrong sign. Nothing guarded the exit, because until now there was no exit. Closing
inverts the convention -- opening a condor takes a credit, closing it pays a debit -- and the
inversion raises nothing at the API. It places a real order at the wrong price.

These tests exist so the exit invariant lives on the type, not in whoever is watching at 15:14.
"""

import datetime as dt

import pytest
from pydantic import ValidationError

from src.options.close import CondorClose, build_close_legs, price_close

EXPIRY = dt.date(2026, 9, 3)
# tranche 2 as held: long 753P, short 758P, short 772C, long 777C
HELD = [
    ("SPY260903P00753000", 13),
    ("SPY260903P00758000", -13),
    ("SPY260903C00772000", -13),
    ("SPY260903C00777000", 13),
]
QUOTES = {
    "SPY260903P00753000": {"bid": 0.01, "ask": 0.04},
    "SPY260903P00758000": {"bid": 0.01, "ask": 0.04},
    "SPY260903C00772000": {"bid": 1.71, "ask": 1.74},
    "SPY260903C00777000": {"bid": 0.04, "ask": 0.05},
}


def a_close(**kw):
    base = dict(
        underlying="SPY",
        expiry=EXPIRY,
        contracts=13,
        limit_price=1.78,
        debit_at_touch=1.73,
        rationale="pin risk: short 772C in the money, 777 wing not",
    )
    return CondorClose(**{**base, **kw})


# ---- the sign, which is the whole point


def test_a_close_must_be_a_debit():
    """Positive is correct here. The opening invariant is the exact opposite."""
    assert a_close().limit_price > 0


def test_a_credit_signed_close_is_refused():
    """The bug this file exists for: entry sign copied onto an exit.

    A negative net on a close reads as 'pay me to take this off', which never fills -- or fills
    somewhere nobody intended. It raises nothing at the API, so it has to raise here.
    """
    with pytest.raises(ValidationError, match="debit"):
        a_close(limit_price=-1.78)


def test_a_zero_limit_is_refused():
    with pytest.raises(ValidationError):
        a_close(limit_price=0.0)


def test_the_limit_must_not_undercut_the_touch():
    """A limit below the touch is not marketable and will rest while the position expires."""
    with pytest.raises(ValidationError, match="touch"):
        a_close(limit_price=1.50, debit_at_touch=1.73)


def test_paying_far_over_the_touch_is_refused():
    """A fat-fingered limit is the other half of the sign bug. 0.50 over touch is not a cross."""
    with pytest.raises(ValidationError, match="over the touch"):
        a_close(limit_price=3.00, debit_at_touch=1.73)


def test_contracts_must_be_positive():
    with pytest.raises(ValidationError):
        a_close(contracts=0)


# ---- legs


def test_longs_are_sold_and_shorts_are_bought_back():
    legs = build_close_legs(HELD)
    by = {x["symbol"]: x for x in legs}
    assert by["SPY260903P00753000"]["side"] == "sell"
    assert by["SPY260903P00753000"]["position_intent"] == "sell_to_close"
    assert by["SPY260903C00772000"]["side"] == "buy"
    assert by["SPY260903C00772000"]["position_intent"] == "buy_to_close"


def test_every_leg_closes_and_none_opens():
    """A close that opens a leg is a new position, not an exit."""
    assert all(x["position_intent"].endswith("_to_close") for x in build_close_legs(HELD))


def test_ratio_qty_is_per_contract_not_the_position_size():
    """`qty` carries the count; the ratio is the structure. Putting 13 here would send 169."""
    assert all(x["ratio_qty"] == "1" for x in build_close_legs(HELD))


def test_a_flat_leg_is_refused():
    with pytest.raises(ValueError, match="not held"):
        build_close_legs([("SPY260903C00772000", 0)])


# ---- pricing


def test_touch_buys_at_the_ask_and_sells_at_the_bid():
    """Crossing means paying up on what we buy back and hitting the bid on what we sell."""
    mid, touch = price_close(HELD, QUOTES)
    assert touch == pytest.approx(-0.01 + 0.04 + 1.74 - 0.04, abs=1e-9)
    assert touch > mid, "the touch must cost more than the mid on a debit"


def test_both_prices_come_back_positive_on_a_real_debit():
    mid, touch = price_close(HELD, QUOTES)
    assert mid > 0 and touch > 0


def test_a_missing_quote_refuses_rather_than_guessing():
    """Three of four legs is not an approximate net. Same rule as the fill-quality work."""
    partial = {k: v for k, v in QUOTES.items() if not k.endswith("C00772000")}
    with pytest.raises(ValueError, match="no two-sided quote"):
        price_close(HELD, partial)


# ---- picking legs out of a book holding overlapping structures


class _P:
    def __init__(self, symbol, qty):
        self.symbol, self.qty = symbol, qty


# The real 3 Sep book: tranche 2 is 753/758P 772/777C, tranche 3 is 750/755P 768/773C.
# Every leg is the same expiry, so proximity cannot tell the structures apart.
BOOK = [
    _P("SPY260903P00750000", 13),
    _P("SPY260903P00753000", 13),
    _P("SPY260903P00755000", -13),
    _P("SPY260903P00758000", -13),
    _P("SPY260903C00768000", -13),
    _P("SPY260903C00772000", -13),
    _P("SPY260903C00773000", 13),
    _P("SPY260903C00777000", 13),
]


def test_explicit_legs_are_taken_verbatim():
    from scripts.close_condor import legs_for

    got = legs_for(BOOK, EXPIRY, ["772C", "777C"])
    assert [s for s, _ in got] == ["SPY260903C00772000", "SPY260903C00777000"]
    assert [q for _, q in got] == [-13, 13]


def test_the_nearest_long_is_not_assumed_to_be_the_wing():
    """The bug the first dry run caught, one strike from a live order.

    Tranche 2 is 772/777 and tranche 3 is 768/773. Asked to close 772C, a nearest-long heuristic
    picks 773 -- tranche 3's wing -- which closes a spread nobody opened and leaves 768 short
    against 777, a nine-wide with a different max loss. Proximity cannot identify a structure in a
    book that holds two at the same expiry, so the caller names every leg.
    """
    from scripts.close_condor import legs_for

    got = legs_for(BOOK, EXPIRY, ["772C", "777C"])
    assert "SPY260903C00773000" not in [s for s, _ in got]


def test_a_leg_not_in_the_book_refuses():
    from scripts.close_condor import legs_for

    with pytest.raises(ValueError, match="not held"):
        legs_for(BOOK, EXPIRY, ["772C", "999C"])


def test_a_wrong_expiry_refuses():
    from scripts.close_condor import legs_for

    with pytest.raises(ValueError, match="no open legs"):
        legs_for(BOOK, dt.date(2026, 9, 4), ["772C"])


def test_closing_a_spread_needs_both_sides():
    """One leg of a vertical is a naked position, not a close."""
    from scripts.close_condor import legs_for

    with pytest.raises(ValueError, match="unbalanced"):
        legs_for(BOOK, EXPIRY, ["772C"])
