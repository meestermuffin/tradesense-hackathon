"""Tests run with no network and no broker. Pure functions only."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from markwatch.markcheck import (  # noqa: E402
    OK,
    STALE,
    UNQUOTABLE,
    classify_leg,
    classify_quote,
    evaluate_snapshot,
    leg_values,
    reconcile_fill,
    side_for_close,
)


# ---------- quote classification ----------

def test_good_quote_is_ok():
    assert classify_quote(1.00, 1.20, age_s=2.0) == OK


def test_old_quote_is_stale_not_a_price():
    assert classify_quote(1.00, 1.20, age_s=60.0) == STALE


def test_missing_age_is_stale():
    assert classify_quote(1.00, 1.20, age_s=None) == STALE


def test_no_bid_is_unquotable():
    # The near-expiry short leg nobody will buy back. This is the one that
    # quietly disappears from a naive average.
    assert classify_quote(0.0, 0.15, age_s=1.0) == UNQUOTABLE
    assert classify_quote(None, 0.15, age_s=1.0) == UNQUOTABLE


def test_crossed_book_is_unquotable():
    assert classify_quote(1.30, 1.10, age_s=1.0) == UNQUOTABLE


def test_unquotable_outranks_stale():
    assert classify_quote(0.0, 0.15, age_s=900.0) == UNQUOTABLE


# ---------- leg valuation ----------

def test_long_leg_liquidates_at_bid():
    v = leg_values(signed_qty=1, bid=1.00, ask=1.20)
    assert abs(v["exec_value"] - 100.0) < 1e-9     # sell 1 contract at 1.00
    assert abs(v["mid_value"] - 110.0) < 1e-9


def test_short_leg_liquidates_at_ask():
    v = leg_values(signed_qty=-1, bid=1.00, ask=1.20)
    assert abs(v["exec_value"] + 120.0) < 1e-9    # buy back at 1.20, a liability
    assert abs(v["mid_value"] + 110.0) < 1e-9


def test_short_leg_costs_more_to_close_than_mid_implies():
    v = leg_values(signed_qty=-1, bid=1.00, ask=1.20)
    assert v["exec_value"] < v["mid_value"]


# ---------- the headline diagnostic ----------

def _condor(broker_at):
    """Short condor: short 2 legs, long 2 wings. broker_at in {'mid','exec'}."""
    legs = [
        {"symbol": "SPY_P760", "signed_qty": -1, "bid": 1.00, "ask": 1.20, "quote_age_s": 1.0},
        {"symbol": "SPY_P755", "signed_qty": 1, "bid": 0.40, "ask": 0.55, "quote_age_s": 1.0},
        {"symbol": "SPY_C772", "signed_qty": -1, "bid": 0.95, "ask": 1.15, "quote_age_s": 1.0},
        {"symbol": "SPY_C777", "signed_qty": 1, "bid": 0.35, "ask": 0.50, "quote_age_s": 1.0},
    ]
    for leg in legs:
        v = leg_values(leg["signed_qty"], leg["bid"], leg["ask"])
        leg["broker_mark"] = v["mid_value"] if broker_at == "mid" else v["exec_value"]
    return legs


def test_detects_broker_marking_at_mid():
    r = evaluate_snapshot(_condor("mid"))
    assert r["marks_at"] == "mid"
    # Marking at mid flatters the account: closing costs more than the mark says.
    assert r["broker_minus_exec"] > 0
    assert abs(r["broker_minus_mid"]) < 1e-9


def test_detects_honest_executable_marks():
    r = evaluate_snapshot(_condor("exec"))
    assert r["marks_at"] == "executable"
    assert abs(r["broker_minus_exec"]) < 1e-9


def test_four_leg_spread_cost_is_all_four_crossings():
    r = evaluate_snapshot(_condor("mid"))
    # half-spread on each leg x 100: (0.20 + 0.15 + 0.20 + 0.15)/2 * 100 = 35
    assert abs(r["mid_minus_exec"] - 35.0) < 1e-9


# ---------- refusing to answer ----------

def test_refuses_verdict_below_coverage_floor():
    legs = _condor("mid")
    for leg in legs[:3]:
        leg["bid"] = None           # three of four have no quote at all
        leg["ask"] = None
    r = evaluate_snapshot(legs)
    assert r["broker_minus_exec"] is None
    assert "insufficient coverage" in r["verdict"]


def test_unquotable_never_averaged_into_the_cost():
    legs = _condor("mid")
    legs[3]["bid"] = None           # long wing with nothing to sell into
    legs[3]["ask"] = None
    r = evaluate_snapshot(legs, coverage_floor=0.70)
    assert r["legs_unquotable"] == 1
    assert r["unquotable_rate"] == 0.25
    assert "SPY_C777" in r["unquotable_symbols"]
    # and it contributed nothing to the valuation
    assert r["legs_clean"] == 3


def test_stale_legs_are_excluded_but_counted():
    legs = _condor("mid")
    legs[0]["quote_age_s"] = 300.0
    r = evaluate_snapshot(legs)
    assert r["legs_stale"] == 1
    assert r["legs_clean"] == 3


def test_empty_book_is_not_an_error():
    r = evaluate_snapshot([])
    assert r["verdict"] == "no open legs"


# ---------- fill reconciliation ----------

def test_fill_at_mid_reads_as_half():
    r = reconcile_fill(fill_price=1.10, side="sell", bid=1.00, ask=1.20)
    assert abs(r["position_in_spread"] - 0.5) < 1e-9
    assert abs(r["vs_mid"]) < 1e-9


def test_seller_hitting_the_bid_is_the_worst_case():
    r = reconcile_fill(fill_price=1.00, side="sell", bid=1.00, ask=1.20)
    assert abs(r["position_in_spread"]) < 1e-9
    assert r["vs_mid"] < 0


def test_buyer_lifting_the_ask_is_the_worst_case():
    r = reconcile_fill(fill_price=1.20, side="buy", bid=1.00, ask=1.20)
    assert abs(r["position_in_spread"]) < 1e-9
    assert r["vs_mid"] < 0


def test_closing_a_short_at_the_ask_is_not_price_improvement():
    # REGRESSION: inferring direction from position sign scored this 1.0
    # (maximum price improvement) when it paid the entire spread.
    side = side_for_close(-1)
    assert side == "buy"
    r = reconcile_fill(fill_price=1.20, side=side, bid=1.00, ask=1.20)
    assert abs(r["position_in_spread"]) < 1e-9
    assert r["vs_mid"] < 0


def test_closing_a_long_at_the_bid_is_not_price_improvement():
    side = side_for_close(1)
    assert side == "sell"
    r = reconcile_fill(fill_price=0.40, side=side, bid=0.40, ask=0.60)
    assert abs(r["position_in_spread"]) < 1e-9
    assert r["vs_mid"] < 0


def test_unpriceable_fill_returns_none_not_zero():
    r = reconcile_fill(fill_price=1.10, side="sell", bid=None, ask=None)
    assert r["position_in_spread"] is None


def test_unknown_side_is_refused_not_guessed():
    r = reconcile_fill(fill_price=1.10, side="", bid=1.00, ask=1.20)
    assert r["position_in_spread"] is None


# ---------- regressions from the verification pass ----------

def test_zero_bid_long_wing_is_priced_not_dropped():
    # REGRESSION: a bid-less far-OTM wing is exactly the leg a mid-marking
    # broker overstates most. Dropping it made the headline gap too small.
    assert classify_leg(1, bid=0.0, ask=0.50, age_s=1.0) == OK
    v = leg_values(1, bid=0.0, ask=0.50)
    assert v["exec_value"] == 0.0            # worthless, and exactly known


def test_short_leg_needs_an_ask_not_a_bid():
    assert classify_leg(-1, bid=1.00, ask=None, age_s=1.0) == UNQUOTABLE
    assert classify_leg(-1, bid=None, ask=1.20, age_s=1.0) == OK


def test_crossed_book_is_unquotable_either_direction():
    assert classify_leg(1, bid=1.30, ask=1.10, age_s=1.0) == UNQUOTABLE
    assert classify_leg(-1, bid=1.30, ask=1.10, age_s=1.0) == UNQUOTABLE


def test_future_dated_quote_is_stale_not_ok():
    # REGRESSION: a host clock behind the exchange silently disabled the
    # freshness guard for the whole session.
    assert classify_quote(1.00, 1.20, age_s=-30.0) == STALE
    assert classify_quote(1.00, 1.20, age_s=-0.5) == OK      # jitter allowed


def test_excluded_broker_mark_is_reported_not_hidden():
    legs = _condor("mid")
    legs[3]["bid"] = None
    legs[3]["ask"] = None                    # genuinely unpriceable
    r = evaluate_snapshot(legs)
    assert r["legs_unquotable"] == 1
    assert r["is_lower_bound"] is True
    assert r["broker_value_excluded"] != 0
    assert "LOWER BOUND" in r["verdict"]


def test_value_coverage_catches_a_small_leg_count_big_exposure_gap():
    # Nine tiny wings priced, one huge short unpriced: 90% of legs, 2% of money.
    legs = [{"symbol": "W%d" % i, "signed_qty": 1, "bid": 0.10, "ask": 0.12,
             "quote_age_s": 1.0, "broker_mark": 10.0} for i in range(9)]
    legs.append({"symbol": "BIG", "signed_qty": -10, "bid": None, "ask": None,
                 "quote_age_s": 1.0, "broker_mark": -5000.0})
    r = evaluate_snapshot(legs)
    assert r["coverage"] == 0.9               # leg count says fine
    assert r["value_coverage"] < 0.1          # exposure says no
    assert "insufficient coverage" in r["verdict"]
