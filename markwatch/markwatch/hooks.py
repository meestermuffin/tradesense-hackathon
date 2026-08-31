"""Journal integration for submit_condor, as one context manager.

The plan's §11 wants every decision with its inputs, every veto with the rule
that fired, and reconciliation of intended against actual fills. This wraps
that around an existing submit path without restructuring it:

    from markwatch.hooks import Recorder

    rec = Recorder(journal, get_quotes=client.get_quotes)

    with rec.submission(kind="submit", underlying="SPY", expiry="2026-09-03",
                        inputs={"spot": spot, "iv": iv, "em": em},
                        intent={"legs": legs, "net_limit": -1.25}) as sub:
        for rule, detail in run_guardrails(legs):      # §8
            sub.veto(rule, detail)
        if sub.vetoed:
            return
        order = broker.submit(legs, net_limit)
        sub.submitted(order_id=order.id, response=order.raw)
        ...
        sub.filled(order.legs)     # reconciled against the captured NBBO

The NBBO is captured at submit time, before the order goes out, because that
is the only moment the comparison is meaningful -- and on this account a quote
not captured live is gone permanently.
"""

import datetime as dt
from typing import Any, Callable, Dict, List, Optional

from .journal import Journal
from .markcheck import classify_quote, reconcile_fill, side_for_close


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


class Submission:
    def __init__(self, recorder: "Recorder", decision_id: int,
                 quotes_at_submit: Dict[str, Dict[str, Any]],
                 ages_at_submit: Optional[Dict[str, Optional[float]]] = None):
        self._rec = recorder
        self.decision_id = decision_id
        self.quotes_at_submit = quotes_at_submit
        # Age of each quote WHEN CAPTURED. Measuring it at fill time instead
        # records how long the order rested, not how stale the NBBO was.
        self.ages_at_submit = ages_at_submit or {}
        self.order_id: Optional[int] = None
        self.vetoes: List[str] = []

    @property
    def vetoed(self) -> bool:
        return bool(self.vetoes)

    def veto(self, rule: str, detail: Dict[str, Any]) -> None:
        """Record a guardrail firing. Vetoes are final; this only logs them."""
        self.vetoes.append(rule)
        self._rec.journal.record_veto(_now_iso(), self.decision_id, rule, detail)

    def submitted(self, intended: Dict[str, Any], order_id: Optional[str] = None,
                  status: Optional[str] = None, response: Optional[Dict[str, Any]] = None) -> int:
        self.order_id = self._rec.journal.record_order(
            _now_iso(), self.decision_id, intended,
            broker_id=order_id, status=status, response=response,
        )
        return self.order_id

    def filled(self, legs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Reconcile each filled leg against the NBBO captured at submit.

        `legs` items need: symbol, signed_qty, fill_price, and `side`
        ("buy"/"sell") -- the TRADE direction of this order, which is not the
        sign of the resulting position. Closing a short is a BUY. Without it a
        closing fill that paid the whole spread scores as price improvement.

        If `side` is absent it is inferred as an OPENING trade (side matches
        position sign) and the row is flagged, rather than silently guessing.
        """
        out = []
        ts = _now_iso()
        for leg in legs:
            sym = leg["symbol"]
            q = self.quotes_at_submit.get(sym) or {}
            bid, ask = q.get("bid"), q.get("ask")
            qts = q.get("ts")
            age = self.ages_at_submit.get(sym)
            sq = int(leg["signed_qty"])
            side = leg.get("side") or leg.get("action")
            if side is None:
                side = "buy" if sq >= 0 else "sell"      # opening assumption
                inferred = True
            else:
                inferred = False
            rec = reconcile_fill(leg.get("fill_price"), side, bid, ask)
            rec["side"] = side
            rec["side_inferred"] = inferred
            self._rec.journal.record_fill(ts, self.order_id, {
                "symbol": sym,
                "signed_qty": sq,
                "fill_price": leg.get("fill_price"),
                "quote_bid": bid,
                "quote_ask": ask,
                "quote_ts": qts.isoformat() if isinstance(qts, dt.datetime) else None,
                "quote_age_s": age,
                "quote_status": classify_quote(bid, ask, age, self._rec.freshness_s),
                "broker_id": leg.get("broker_id"),
            })
            out.append(dict(rec, symbol=sym))
        return out


class _SubmissionContext:
    def __init__(self, recorder, kind, inputs, intent, underlying, expiry, note, symbols):
        self._args = (recorder, kind, inputs, intent, underlying, expiry, note, symbols)
        self.sub: Optional[Submission] = None

    def __enter__(self) -> Submission:
        rec, kind, inputs, intent, underlying, expiry, note, symbols = self._args
        quotes: Dict[str, Dict[str, Any]] = {}
        if symbols and rec.get_quotes is not None:
            try:
                quotes = rec.get_quotes(symbols) or {}
            except Exception as exc:  # a failed capture is data, not a crash
                rec.journal.record_decision(
                    _now_iso(), "quote_error",
                    {"symbols": symbols, "error": repr(exc)},
                    note="NBBO capture failed at submit; fills will be unreconcilable",
                )
        captured_at = dt.datetime.now(dt.timezone.utc)
        ages = {}
        for sym, q in quotes.items():
            qts = q.get("ts")
            ages[sym] = ((captured_at - qts).total_seconds()
                         if isinstance(qts, dt.datetime) else None)
        enriched = dict(inputs)
        enriched["nbbo_at_submit"] = {
            s: {"bid": q.get("bid"), "ask": q.get("ask"),
                "ts": q["ts"].isoformat() if isinstance(q.get("ts"), dt.datetime) else None}
            for s, q in quotes.items()
        }
        did = rec.journal.record_decision(
            _now_iso(), kind, enriched, intent=intent,
            underlying=underlying, expiry=expiry, note=note,
        )
        self.sub = Submission(rec, did, quotes, ages)
        return self.sub

    def __exit__(self, exc_type, exc, tb):
        if exc is not None and self.sub is not None:
            self._args[0].journal.record_veto(
                _now_iso(), self.sub.decision_id, "exception",
                {"type": exc_type.__name__, "error": repr(exc)},
            )
        return False  # never swallow


class Recorder:
    def __init__(self, journal: Journal,
                 get_quotes: Optional[Callable[[List[str]], Dict[str, Dict[str, Any]]]] = None,
                 freshness_s: float = 15.0):
        self.journal = journal
        self.get_quotes = get_quotes
        # Shared with the collector so the fill path and the mark path agree
        # on what "stale" means.
        self.freshness_s = freshness_s

    def submission(self, kind: str, inputs: Dict[str, Any],
                   intent: Optional[Dict[str, Any]] = None,
                   underlying: Optional[str] = None, expiry: Optional[str] = None,
                   note: Optional[str] = None,
                   symbols: Optional[List[str]] = None) -> _SubmissionContext:
        return _SubmissionContext(self, kind, inputs, intent, underlying, expiry, note, symbols)

    def note(self, kind: str, inputs: Dict[str, Any], note: Optional[str] = None) -> int:
        """Log a decision that places no order -- a screen, a pin check, a skip."""
        return self.journal.record_decision(_now_iso(), kind, inputs, note=note)
