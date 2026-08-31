"""The bridge to markwatch, and the eleven ways it could silently not work.

Every test here corresponds to a mismatch found by reading Solo's package against ours. The ones
worth reading twice are the silent failures: a string timestamp, or a Position model that has
already discarded the field the whole measurement depends on. Neither raises. Both produce a clean
report that answers nothing.
"""

import datetime as dt

from src.agent.adapter import FEED, MarkwatchBridge, callables, fill_legs
from src.models import Order, OrderLeg


class FakeClient:
    """Returns Alpaca's raw wire shapes, not our models -- which is the point."""

    key, secret, trade_host = "k", "s", "https://paper-api.alpaca.markets"

    def __init__(self, quotes=None, positions=None, account=None):
        self._q = quotes if quotes is not None else {}
        self._p = positions if positions is not None else []
        self._a = account or {"equity": "100000", "cash": "100000"}
        self.calls = []

    def request(self, method, host, path, params=None, body=None, **kw):
        self.calls.append((path, params))
        if "quotes/latest" in path:
            want = (params or {}).get("symbols", "").split(",")
            return {"quotes": {s: self._q[s] for s in want if s in self._q}}
        if path == "/v2/positions":
            return self._p
        if path == "/v2/account":
            return self._a
        raise AssertionError(path)


RAW = {"bp": 1.20, "ap": 1.26, "bs": 3, "as": 5, "t": "2026-08-31T13:45:00.123456789Z"}


# ---- breakage C: the feed parameter


def test_every_quote_request_sends_feed_indicative():
    """Omitted, Alpaca defaults to opra server-side, which 403s without an OPRA agreement."""
    c = FakeClient(quotes={"X": RAW})
    MarkwatchBridge(c).get_quotes(["X"])
    assert all(p.get("feed") == FEED for _, p in c.calls if p)
    assert FEED == "indicative"


# ---- breakage K: batch size


def test_quotes_batch_at_forty_not_a_hundred():
    """markwatch chunks at 100; this endpoint has failed here at large batches and 40 is known-good."""
    syms = [f"S{i}" for i in range(95)]
    c = FakeClient(quotes=dict.fromkeys(syms, RAW))
    MarkwatchBridge(c).get_quotes(syms)
    sizes = [len(p["symbols"].split(",")) for _, p in c.calls]
    assert max(sizes) <= 40
    assert len(c.calls) == 3


# ---- breakage B: the silent one


def test_ts_is_a_datetime_not_a_string():
    """A string here fails markwatch's isinstance check, so every age is None, every leg reads
    stale, coverage lands at 0%, and the report says 'insufficient coverage' having measured
    nothing. It does not raise."""
    q = MarkwatchBridge(FakeClient(quotes={"X": RAW})).get_quotes(["X"])["X"]
    assert isinstance(q["ts"], dt.datetime)
    assert q["ts"].tzinfo is not None
    age = (dt.datetime.now(dt.UTC) - q["ts"]).total_seconds()
    assert isinstance(age, float)


def test_nanosecond_timestamps_parse():
    """Alpaca sends up to nanosecond precision, which fromisoformat rejects outright."""
    q = MarkwatchBridge(FakeClient(quotes={"X": RAW})).get_quotes(["X"])["X"]
    assert q["ts"].year == 2026 and q["ts"].microsecond == 123456


def test_key_names_match_what_markcheck_reads():
    q = MarkwatchBridge(FakeClient(quotes={"X": RAW})).get_quotes(["X"])["X"]
    assert set(q) == {"bid", "ask", "bid_size", "ask_size", "ts"}
    assert (q["bid"], q["ask"]) == (1.20, 1.26)


# ---- breakage D: one-sided quotes are data, not errors


def test_a_symbol_with_no_usable_quote_is_omitted_not_nulled():
    """markwatch reads absence as 'unquotable' and reports the rate. A null-filled row would be
    counted as a priced leg instead."""
    c = FakeClient(quotes={"GOOD": RAW, "DEAD": {"bp": None, "ap": None, "t": RAW["t"]}})
    got = MarkwatchBridge(c).get_quotes(["GOOD", "DEAD"])
    assert "GOOD" in got and "DEAD" not in got


def test_a_one_sided_quote_survives_and_does_not_take_the_batch_down():
    """Our Quote model requires both bp and ap and would raise, losing all 40 symbols."""
    c = FakeClient(quotes={"A": RAW, "B": {"bp": 0.0, "ap": 1.10, "t": RAW["t"]}})
    got = MarkwatchBridge(c).get_quotes(["A", "B"])
    assert len(got) == 2
    assert got["B"]["bid"] == 0.0, "a zero bid is a real market state, not a missing value"


# ---- breakage E: the one that guts the package


def test_positions_come_back_raw_with_the_fields_the_model_discards():
    """src.models.Position keeps symbol and qty only. Without market_value every broker_mark is
    None and the verdict reads 'broker marks missing' -- the measurement, silently absent."""
    raw = [
        {
            "symbol": "SPY260902P00760000",
            "qty": "-14",
            "side": "short",
            "market_value": "-1736.00",
            "asset_class": "us_option",
        }
    ]
    got = MarkwatchBridge(FakeClient(positions=raw)).get_positions()
    assert got[0]["market_value"] == "-1736.00"
    assert got[0]["asset_class"] == "us_option"
    assert got[0]["side"] == "short"

    from src.models import Position

    assert not hasattr(Position(symbol="X", qty=1), "market_value")


# ---- breakage I: bound methods


def test_get_quotes_is_bound_so_feed_name_resolves():
    """Collector.feed_name reaches through get_quotes.__self__. A closure has no __self__, the
    marks.feed column goes NULL, and the 'derived quotes' caveat drops out of every report."""
    b = MarkwatchBridge(FakeClient())
    assert b.get_quotes.__self__ is b
    assert b.get_quotes.__self__.feed == "indicative"
    assert callables(FakeClient())["get_quotes"].__self__.feed == "indicative"


def test_callables_returns_the_shape_the_collector_takes():
    got = callables(FakeClient())
    assert {"get_positions", "get_quotes", "get_account"} <= set(got)
    assert all(callable(got[k]) for k in ("get_positions", "get_quotes", "get_account"))


# ---- breakage F: fill legs


def test_fill_legs_reconstructs_signed_qty_which_the_order_response_lacks():
    submitted = [
        {"symbol": "P_LONG", "side": "buy", "ratio_qty": "1"},
        {"symbol": "P_SHORT", "side": "sell", "ratio_qty": "1"},
    ]
    order = Order(
        id="o1",
        status="filled",
        legs=[
            OrderLeg(symbol="P_LONG", side="buy", filled_avg_price=0.40),
            OrderLeg(symbol="P_SHORT", side="sell", filled_avg_price=1.60),
        ],
    )
    legs = fill_legs(order, submitted, contracts=14)
    by = {x["symbol"]: x for x in legs}
    assert by["P_SHORT"]["signed_qty"] == -14, "a sold leg is short"
    assert by["P_LONG"]["signed_qty"] == 14
    assert by["P_SHORT"]["fill_price"] == 1.60, "renamed from filled_avg_price"


def test_fill_legs_passes_side_explicitly_rather_than_letting_it_be_inferred():
    """Inferred side assumes an opening trade, which scores every close as maximum price
    improvement when it actually paid the full spread."""
    submitted = [{"symbol": "S", "side": "sell", "ratio_qty": "1"}]
    order = Order(
        id="o", status="filled", legs=[OrderLeg(symbol="S", side="sell", filled_avg_price=1.0)]
    )
    assert fill_legs(order, submitted, 1)[0]["side"] == "sell"


def test_fill_legs_requires_the_two_keys_markwatch_indexes_directly():
    """sub.filled() does leg["symbol"] and leg["signed_qty"] -- KeyError, not .get()."""
    order = Order(
        id="o", status="filled", legs=[OrderLeg(symbol="S", side="buy", filled_avg_price=1.0)]
    )
    for leg_ in fill_legs(order, [{"symbol": "S", "side": "buy", "ratio_qty": "1"}], 2):
        assert leg_["symbol"] and leg_["signed_qty"] is not None


def test_fill_legs_on_an_order_with_no_legs_returns_empty_not_an_exception():
    assert fill_legs(Order(id="o", status="new"), [], 1) == []


# ---- breakage G: credential alias


def test_the_api_key_alias_is_exported_for_markwatch_own_client(monkeypatch):
    """markwatch reads ALPACA_API_KEY and never loads .env; we read ALPACA_KEY_ID."""
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    MarkwatchBridge(FakeClient())
    import os

    assert os.environ.get("ALPACA_API_KEY") == "k"


def test_account_payload_carries_what_the_collector_reads():
    a = MarkwatchBridge(
        FakeClient(account={"equity": "99949.55", "cash": "99949.55"})
    ).get_account()
    assert "equity" in a and "cash" in a
