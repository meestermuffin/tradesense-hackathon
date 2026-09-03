"""`vs_mid` against the captured NBBO, and the label that says where it came from.

The patch that put the NBBO on the legs did not make anything read it: `vs_mid` still compared the
fill to `credit_at_mid`, our own pre-submission estimate. These tests pin the consumer side.

The distinction is not cosmetic. Our estimate and the market's midpoint are two different numbers,
and when they disagree the estimate is the one that flatters us -- it is computed from the same
chain snapshot that chose the strikes. `test_estimate_reads_improvement_where_market_reads_worse`
is that case in miniature.
"""

import datetime as dt

import pytest

from src.models import CondorFill, CondorLegFill


def _condor(legs, fill, credit_at_mid, contracts=1):
    return CondorFill(
        ok=True,
        filled=fill is not None,
        underlying="SPY",
        expiry=dt.date(2026, 9, 2),
        contracts=contracts,
        limit_price=-abs(fill) if fill is not None else -credit_at_mid,
        credit_at_mid=credit_at_mid,
        submitted_at="2026-08-31T14:19:38+00:00",
        fill=fill,
        legs=legs,
    )


def _leg(symbol, side, signed_qty, fill_price, bid=None, ask=None):
    return CondorLegFill(
        symbol=symbol, side=side, signed_qty=signed_qty, fill_price=fill_price, bid=bid, ask=ask
    )


# Monday's probe legs, with plausible spreads around the recorded fills.
MONDAY = [
    _leg("SPY260902P00755000", "buy", 1, 0.37, 0.35, 0.40),
    _leg("SPY260902P00760000", "sell", -1, 0.88, 0.85, 0.92),
    _leg("SPY260902C00771000", "sell", -1, 0.73, 0.70, 0.77),
    _leg("SPY260902C00776000", "buy", 1, 0.12, 0.10, 0.15),
]


# ---------- net credit, signed by trade direction ----------


def test_net_credit_at_mid_sums_sells_in_and_buys_out():
    rec = _condor(MONDAY, fill=-1.12, credit_at_mid=1.12)
    # (-0.375) + 0.885 + 0.735 + (-0.125)
    assert rec.net_credit_at_mid == pytest.approx(1.12, abs=1e-4)


def test_net_credit_at_touch_sells_the_bid_and_buys_the_ask():
    rec = _condor(MONDAY, fill=-1.12, credit_at_mid=1.12)
    # (-0.40) + 0.85 + 0.70 + (-0.15)
    assert rec.net_credit_at_touch == pytest.approx(1.00, abs=1e-4)


def test_touch_is_never_better_than_mid_on_a_credit():
    rec = _condor(MONDAY, fill=-1.12, credit_at_mid=1.12)
    assert rec.net_credit_at_touch < rec.net_credit_at_mid


def test_side_beats_position_sign_on_a_closing_order():
    """Closing a short is a BUY: the same strike moves to the other side of the ledger."""
    closing = [
        _leg("SPY260902P00760000", "buy", -1, 0.88, 0.85, 0.92),
        _leg("SPY260902P00755000", "sell", 1, 0.37, 0.35, 0.40),
    ]
    rec = _condor(closing, fill=-0.51, credit_at_mid=0.51)
    # buy pays the 0.885 mid, sell takes in the 0.375 mid
    assert rec.net_credit_at_mid == pytest.approx(-0.51, abs=1e-4)


def test_falls_back_to_signed_qty_when_side_is_blank():
    legs = [_leg("A", "", -1, 0.88, 0.85, 0.92), _leg("B", "", 1, 0.37, 0.35, 0.40)]
    rec = _condor(legs, fill=-0.51, credit_at_mid=0.51)
    assert rec.net_credit_at_mid == pytest.approx(0.51, abs=1e-4)


# ---------- the label ----------


def test_full_capture_is_labelled_market():
    rec = _condor(MONDAY, fill=-1.12, credit_at_mid=1.12)
    assert rec.vs_mid_source == "market"
    assert rec.nbbo_complete is True
    assert rec.nbbo_legs == 4


def test_no_capture_falls_back_and_says_so():
    """Monday's verdict: four null legs. The number is still produced, and labelled."""
    bare = [_leg(x.symbol, x.side, x.signed_qty, x.fill_price) for x in MONDAY]
    rec = _condor(bare, fill=-1.12, credit_at_mid=1.12)
    assert rec.vs_mid_source == "estimate"
    assert rec.vs_mid == pytest.approx(0.0, abs=1e-4)
    assert rec.nbbo_legs == 0


def test_partial_capture_does_not_produce_a_net():
    """Three of four legs is a different quantity, not an approximate one."""
    partial = list(MONDAY[:3]) + [_leg("SPY260902C00776000", "buy", 1, 0.12)]
    rec = _condor(partial, fill=-1.12, credit_at_mid=1.12)
    assert rec.nbbo_complete is False
    assert rec.nbbo_legs == 3
    assert rec.net_credit_at_mid is None
    assert rec.vs_mid_source == "estimate"


def test_vs_touch_has_no_estimated_fallback():
    """We compute a mid before submitting, never a touch. An estimate would be invented."""
    bare = [_leg(x.symbol, x.side, x.signed_qty, x.fill_price) for x in MONDAY]
    assert _condor(bare, fill=-1.12, credit_at_mid=1.12).vs_touch is None
    assert _condor(MONDAY, fill=-1.12, credit_at_mid=1.12).vs_touch == pytest.approx(0.12, abs=1e-4)


def test_fill_quality_carries_the_number_and_its_provenance_together():
    q = _condor(MONDAY, fill=-1.12, credit_at_mid=1.12).fill_quality
    assert q["source"] == "market"
    assert q["nbbo_legs"] == "4/4"
    assert q["vs_mid"] is not None and q["vs_touch"] is not None
    # the estimate is kept alongside, so the two can always be compared
    assert q["credit_at_mid_estimated"] == 1.12


# ---------- the case this exists for ----------


def test_estimate_reads_improvement_where_market_reads_worse():
    """The shape of the order-3 regression: +0.02 by our estimate, negative against the market.

    Our `credit_at_mid` is computed from the chain snapshot that chose the strikes. When the book
    moves between selection and submission the estimate is stale, and it is stale in our favour --
    it reports price improvement on a fill that gave up money against the real midpoint.
    """
    legs = [
        _leg("P755", "buy", 1, 0.40, 0.38, 0.44),
        _leg("P760", "sell", -1, 0.86, 0.83, 0.91),
        _leg("C771", "sell", -1, 0.71, 0.68, 0.76),
        _leg("C776", "buy", 1, 0.15, 0.12, 0.18),
    ]
    # market mids: 0.41 / 0.87 / 0.72 / 0.15  ->  -0.41 +0.87 +0.72 -0.15 = 1.03
    rec = _condor(legs, fill=-1.02, credit_at_mid=1.00)

    assert rec.net_credit_at_mid == pytest.approx(1.03, abs=1e-4)
    assert rec.vs_mid_source == "market"
    assert rec.vs_mid == pytest.approx(-0.01, abs=1e-4)  # gave up a cent to the market

    stale = _condor(
        [_leg(x.symbol, x.side, x.signed_qty, x.fill_price) for x in legs],
        fill=-1.02,
        credit_at_mid=1.00,
    )
    assert stale.vs_mid == pytest.approx(+0.02, abs=1e-4)  # our estimate says improvement
    assert stale.vs_mid_source == "estimate"

    assert rec.vs_mid < 0 < stale.vs_mid, "the sign flips: this is the whole point"


def test_unfilled_order_has_no_fill_quality_numbers():
    rec = _condor(MONDAY, fill=None, credit_at_mid=1.12)
    assert rec.vs_mid is None and rec.vs_touch is None
