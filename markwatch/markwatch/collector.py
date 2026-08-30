"""Live capture. Runs alongside the agent, touches nothing, signs nothing.

Quotes do not exist after the fact on this account: `options/quotes` 404s and
history covers bars and trades only. Anything not captured while the market is
open is gone permanently. That is the whole reason this runs from before the
first order rather than being added at the end.

The broker adapter is deliberately thin and injectable so the module is
testable without a network and swappable between the SDK and the MCP surface.
"""

import datetime as dt
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

from .alpaca import option_positions
from .journal import Journal
from .markcheck import classify_leg, evaluate_snapshot, format_report


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _iso(t: dt.datetime) -> str:
    return t.isoformat()


def _age_seconds(quote_ts: Optional[dt.datetime], sampled_at: dt.datetime) -> Optional[float]:
    if quote_ts is None:
        return None
    if quote_ts.tzinfo is None:
        quote_ts = quote_ts.replace(tzinfo=dt.timezone.utc)
    return (sampled_at - quote_ts).total_seconds()


def signed_qty_from_position(pos: Any) -> Optional[int]:
    """Alpaca returns qty as a string and side separately. Normalise to signed.

    Short positions already come back negative in some SDK versions, so the
    sign is taken from the side when available rather than trusted blindly.
    """
    raw = getattr(pos, "qty", None)
    if raw is None and isinstance(pos, dict):
        raw = pos.get("qty")
    try:
        qty = int(float(raw))
    except (TypeError, ValueError):
        return None          # one malformed leg must not destroy the snapshot
    side = getattr(pos, "side", None)
    if side is None and isinstance(pos, dict):
        side = pos.get("side")
    side = str(side).lower() if side is not None else ""
    if "short" in side:
        return -abs(qty)
    if "long" in side:
        return abs(qty)
    return qty


class Collector:
    """Samples open option legs and records broker mark vs executable value.

    get_positions()      -> list of position objects/dicts
    get_quotes(symbols)  -> {symbol: {"bid":float,"ask":float,"ts":datetime}}
    get_account()        -> object/dict with equity and cash
    """

    def __init__(
        self,
        journal: Journal,
        get_positions: Callable[[], List[Any]],
        get_quotes: Callable[[List[str]], Dict[str, Dict[str, Any]]],
        get_account: Optional[Callable[[], Any]] = None,
        freshness_s: float = 15.0,
    ):
        self.journal = journal
        self.get_positions = get_positions
        self.get_quotes = get_quotes
        self.get_account = get_account
        self.freshness_s = freshness_s

    def _option_positions(self) -> List[Any]:
        """Single definition, shared with preflight via alpaca.option_positions."""
        raw = self.get_positions()
        dicts = [p for p in raw if isinstance(p, dict)]
        if len(dicts) == len(raw):
            return option_positions(dicts)
        out = []
        for p in raw:                      # object-style positions (SDK path)
            cls = getattr(p, "asset_class", None)
            if cls is None or "option" in str(cls).lower():
                out.append(p)
        return out

    def sample(self) -> Dict[str, Any]:
        """One pass. Returns the evaluation and writes everything to the journal."""
        snapshot_id = uuid.uuid4().hex[:12]
        sampled_at = _utc_now()
        ts = _iso(sampled_at)

        positions = self._option_positions()
        symbols = []
        for p in positions:
            sym = getattr(p, "symbol", None)
            if sym is None and isinstance(p, dict):
                sym = p.get("symbol")
            symbols.append(sym)

        quotes: Dict[str, Dict[str, Any]] = {}
        if symbols:
            try:
                quotes = self.get_quotes(symbols) or {}
            except Exception as exc:  # a failed quote pull is data, not a crash
                quotes = {}
                self.journal.record_decision(
                    ts, "quote_error", {"symbols": symbols, "error": repr(exc)},
                    note="quote pull failed; legs recorded unquotable",
                )
        # Age is measured against the moment the quotes ARRIVED. Using the
        # pass-start instant understates age by the whole round trip, which
        # lets a genuinely stale book slip through the freshness gate.
        recv_at = _utc_now()

        rows = []
        skipped = []
        for p, sym in zip(positions, symbols):
            try:
                sq = signed_qty_from_position(p)
                if sq is None or not sym:
                    skipped.append({"symbol": sym, "reason": "unparseable qty or symbol"})
                    continue
                q = quotes.get(sym) or {}
                bid = q.get("bid")
                ask = q.get("ask")
                qts = q.get("ts")
                age = _age_seconds(qts, recv_at)
                mark = getattr(p, "market_value", None)
                if mark is None and isinstance(p, dict):
                    mark = p.get("market_value")
                try:
                    mark = float(mark) if mark is not None else None
                except (TypeError, ValueError):
                    mark = None
                rows.append({
                    "symbol": sym,
                    "signed_qty": sq,
                    "broker_mark": mark,
                    "bid": bid,
                    "ask": ask,
                    "quote_ts": _iso(qts) if isinstance(qts, dt.datetime) else (str(qts) if qts else None),
                    "quote_age_s": age,
                    "status": classify_leg(sq, bid, ask, age, self.freshness_s),
                })
            except Exception as exc:   # one bad leg must not lose the other three
                skipped.append({"symbol": sym, "reason": repr(exc)})
        if skipped:
            self.journal.record_decision(
                ts, "leg_skipped", {"skipped": skipped},
                note="legs excluded from this snapshot; they are NOT in the coverage figure",
            )

        self.journal.record_marks(ts, snapshot_id, rows, feed=self.feed_name())

        if self.get_account is not None:
            try:
                acct = self.get_account()
                eq = getattr(acct, "equity", None)
                cash = getattr(acct, "cash", None)
                if eq is None and isinstance(acct, dict):
                    eq, cash = acct.get("equity"), acct.get("cash")
                self.journal.record_equity(
                    ts, snapshot_id,
                    float(eq) if eq is not None else None,
                    float(cash) if cash is not None else None,
                )
            except Exception as exc:
                self.journal.record_decision(ts, "account_error", {"error": repr(exc)})

        result = evaluate_snapshot(rows, freshness_s=self.freshness_s)
        result["snapshot_id"] = snapshot_id
        result["ts"] = ts
        result["feed"] = self.feed_name()
        result["legs_skipped"] = len(skipped)
        return result

    def feed_name(self) -> Optional[str]:
        """Which options feed produced these quotes, if the adapter exposes one."""
        client = getattr(self.get_quotes, "__self__", None)
        return getattr(client, "feed", None) if client is not None else None

    def run(self, interval_s: float = 60.0, until: Optional[dt.datetime] = None,
            verbose: bool = True) -> None:
        """Poll until `until`. Never raises out of the loop; a bad pass is logged."""
        while True:
            if until is not None and _utc_now() >= until:
                return
            try:
                result = self.sample()
                if verbose:
                    print("[%s] %s" % (result["ts"], result["verdict"]), flush=True)
            except Exception as exc:
                print("sample failed: %r" % (exc,), flush=True)
                try:
                    self.journal.record_decision(
                        _iso(_utc_now()), "sample_error", {"error": repr(exc)})
                except Exception:
                    pass
            time.sleep(interval_s)


def report_latest(journal: Journal, freshness_s: float = 15.0) -> str:
    ids = journal.snapshot_ids()
    if not ids:
        return "no snapshots recorded"
    rows = journal.snapshot_rows(ids[-1])
    return format_report(evaluate_snapshot(rows, freshness_s=freshness_s))
