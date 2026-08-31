"""Adapter + hooks tests. No network: every call is a stub."""

import datetime as dt
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from markwatch.alpaca import normalise_quote, option_positions, parse_ts  # noqa: E402
from markwatch.hooks import Recorder  # noqa: E402
from markwatch.journal import Journal  # noqa: E402


# ---------- timestamp parsing (3.9 cannot do this natively) ----------

def test_parses_nanosecond_rfc3339():
    t = parse_ts("2026-08-31T13:45:01.123456789Z")
    assert t is not None
    assert t.tzinfo is not None
    assert t.year == 2026 and t.hour == 13 and t.minute == 45
    assert t.microsecond == 123456          # truncated, not rounded or crashed


def test_parses_plain_z():
    t = parse_ts("2026-08-31T13:45:01Z")
    assert t is not None and t.second == 1


def test_parses_offset_form():
    t = parse_ts("2026-08-31T09:45:01.5-04:00")
    assert t is not None and t.tzinfo is not None


def test_unparseable_returns_none_not_now():
    # Critical: a bogus timestamp must NOT look fresh. None -> stale downstream.
    assert parse_ts("not a date") is None
    assert parse_ts(None) is None
    assert parse_ts("") is None


def test_naive_datetime_is_assumed_utc():
    t = parse_ts(dt.datetime(2026, 8, 31, 13, 0, 0))
    assert t.tzinfo is not None


# ---------- quote normalisation ----------

def test_normalises_alpaca_compact_keys():
    q = normalise_quote({"bp": 1.00, "ap": 1.20, "bs": 4, "as": 7,
                         "t": "2026-08-31T13:45:01.100Z"})
    assert q["bid"] == 1.00 and q["ask"] == 1.20
    assert q["bid_size"] == 4 and q["ask_size"] == 7
    assert q["ts"] is not None


def test_normalises_verbose_keys():
    q = normalise_quote({"bid_price": 2.0, "ask_price": 2.5, "timestamp": "2026-08-31T13:45:01Z"})
    assert q["bid"] == 2.0 and q["ask"] == 2.5


def test_zero_bid_passes_through_untouched():
    # normalise must not editorialise; classify_quote decides unquotable.
    q = normalise_quote({"bp": 0, "ap": 0.15, "t": "2026-08-31T13:45:01Z"})
    assert q["bid"] == 0.0


def test_missing_fields_are_none_not_zero():
    q = normalise_quote({"t": "2026-08-31T13:45:01Z"})
    assert q["bid"] is None and q["ask"] is None


def test_garbage_price_is_none():
    q = normalise_quote({"bp": "abc", "ap": 1.2})
    assert q["bid"] is None and q["ask"] == 1.2


# ---------- position filtering ----------

def test_filters_to_options_only():
    rows = [{"symbol": "SPY", "asset_class": "us_equity"},
            {"symbol": "SPY260903P00760000", "asset_class": "us_option"}]
    assert [p["symbol"] for p in option_positions(rows)] == ["SPY260903P00760000"]


# ---------- hooks / reconciliation ----------

def _journal():
    return Journal(os.path.join(tempfile.mkdtemp(), "t.db"))


def test_records_decision_veto_order_and_fill():
    j = _journal(); j.connect()
    now = dt.datetime.now(dt.timezone.utc)
    quotes = {"L1": {"bid": 1.00, "ask": 1.20, "ts": now}}
    rec = Recorder(j, get_quotes=lambda syms: quotes)

    with rec.submission(kind="submit", underlying="SPY", expiry="2026-09-03",
                        inputs={"spot": 766.0}, intent={"net_limit": -1.25},
                        symbols=["L1"]) as sub:
        assert not sub.vetoed
        sub.submitted(intended={"net_limit": -1.25}, order_id="abc123", status="accepted")
        out = sub.filled([{"symbol": "L1", "signed_qty": -1,
                           "side": "sell", "fill_price": 1.10}])

    assert abs(out[0]["position_in_spread"] - 0.5) < 1e-9    # filled at mid
    rows = j.reconciliation_rows()
    assert len(rows) == 1
    assert rows[0]["quote_bid"] == 1.00 and rows[0]["quote_ask"] == 1.20


def test_veto_marks_submission_and_persists_rule():
    j = _journal(); j.connect()
    rec = Recorder(j, get_quotes=lambda syms: {})
    with rec.submission(kind="submit", inputs={}, symbols=[]) as sub:
        sub.veto("guardrail_2_min_credit", {"credit_pct": 0.11, "floor": 0.18})
        assert sub.vetoed
    with j.cursor() as cur:
        cur.execute("SELECT rule FROM vetoes")
        assert cur.fetchone()[0] == "guardrail_2_min_credit"


def test_nbbo_captured_at_submit_is_stored_on_the_decision():
    j = _journal(); j.connect()
    now = dt.datetime.now(dt.timezone.utc)
    rec = Recorder(j, get_quotes=lambda syms: {"L1": {"bid": 1.0, "ask": 1.2, "ts": now}})
    with rec.submission(kind="submit", inputs={"spot": 766.0}, symbols=["L1"]):
        pass
    with j.cursor() as cur:
        cur.execute("SELECT inputs_json FROM decisions")
        assert "nbbo_at_submit" in cur.fetchone()[0]


def test_quote_failure_is_logged_not_raised():
    j = _journal(); j.connect()

    def boom(_syms):
        raise RuntimeError("429")

    rec = Recorder(j, get_quotes=boom)
    with rec.submission(kind="submit", inputs={}, symbols=["L1"]) as sub:
        sub.submitted(intended={})          # submission still proceeds
    with j.cursor() as cur:
        cur.execute("SELECT kind FROM decisions WHERE kind='quote_error'")
        assert cur.fetchone() is not None


def test_exception_inside_block_is_recorded_and_reraised():
    j = _journal(); j.connect()
    rec = Recorder(j, get_quotes=lambda syms: {})
    raised = False
    try:
        with rec.submission(kind="submit", inputs={}, symbols=[]):
            raise ValueError("broker rejected")
    except ValueError:
        raised = True
    assert raised                            # never swallowed
    with j.cursor() as cur:
        cur.execute("SELECT rule FROM vetoes WHERE rule='exception'")
        assert cur.fetchone() is not None


def test_fill_without_captured_quote_is_unreconcilable_not_zero():
    j = _journal(); j.connect()
    rec = Recorder(j, get_quotes=lambda syms: {})
    with rec.submission(kind="submit", inputs={}, symbols=["L1"]) as sub:
        sub.submitted(intended={})
        out = sub.filled([{"symbol": "L1", "signed_qty": -1,
                           "side": "sell", "fill_price": 1.10}])
    assert out[0]["position_in_spread"] is None


def test_closing_fill_records_the_spread_it_paid():
    """REGRESSION: closing legs were journaled as price improvement."""
    j = _journal(); j.connect()
    now = dt.datetime.now(dt.timezone.utc)
    rec = Recorder(j, get_quotes=lambda syms: {"S1": {"bid": 1.00, "ask": 1.20, "ts": now}})
    with rec.submission(kind="close", inputs={}, symbols=["S1"]) as sub:
        sub.submitted(intended={})
        out = sub.filled([{"symbol": "S1", "signed_qty": -1,
                           "side": "buy", "fill_price": 1.20}])   # bought back at the ask
    assert abs(out[0]["position_in_spread"]) < 1e-9
    assert out[0]["vs_mid"] < 0
    assert out[0]["side_inferred"] is False


def test_missing_side_is_flagged_not_silently_guessed():
    j = _journal(); j.connect()
    now = dt.datetime.now(dt.timezone.utc)
    rec = Recorder(j, get_quotes=lambda syms: {"S1": {"bid": 1.00, "ask": 1.20, "ts": now}})
    with rec.submission(kind="submit", inputs={}, symbols=["S1"]) as sub:
        sub.submitted(intended={})
        out = sub.filled([{"symbol": "S1", "signed_qty": -1, "fill_price": 1.10}])
    assert out[0]["side_inferred"] is True


def test_stale_capture_is_recorded_as_stale_not_ok():
    """REGRESSION: quote_status was hardcoded 'ok' whenever both sides existed."""
    j = _journal(); j.connect()
    old = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=45)
    rec = Recorder(j, get_quotes=lambda syms: {"S1": {"bid": 1.00, "ask": 1.20, "ts": old}})
    with rec.submission(kind="submit", inputs={}, symbols=["S1"]) as sub:
        sub.submitted(intended={})
        sub.filled([{"symbol": "S1", "signed_qty": -1, "side": "sell", "fill_price": 1.10}])
    rows = j.reconciliation_rows()
    assert rows[0]["quote_status"] == "stale"


def test_one_bad_leg_does_not_lose_the_snapshot():
    """REGRESSION: a single NOT NULL violation rolled back all four legs."""
    j = _journal(); j.connect()
    rows = [
        {"symbol": "A", "signed_qty": -1, "broker_mark": -110.0, "bid": 1.0,
         "ask": 1.2, "quote_age_s": 1.0, "status": "ok"},
        {"symbol": None, "signed_qty": 1, "broker_mark": 5.0, "bid": 0.0,
         "ask": 0.1, "quote_age_s": 1.0, "status": "ok"},          # violates NOT NULL
        {"symbol": "C", "signed_qty": 1, "broker_mark": 40.0, "bid": 0.4,
         "ask": 0.5, "quote_age_s": 1.0, "status": "ok"},
    ]
    written = j.record_marks("2026-08-31T13:45:00+00:00", "snap1", rows)
    assert written == 2                       # the good legs survived
    assert len(j.snapshot_rows("snap1")) == 2


def test_unparseable_qty_returns_none_rather_than_raising():
    from markwatch.collector import signed_qty_from_position
    assert signed_qty_from_position({"symbol": "X", "side": "long"}) is None
    assert signed_qty_from_position({"symbol": "X", "qty": "2", "side": "short"}) == -2
