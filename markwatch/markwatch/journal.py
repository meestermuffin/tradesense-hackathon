"""Decision journal + mark ledger.

SQLite, WAL mode. Local state is a cache, never the truth: the broker is.
Everything here is append-only so a bad run can be re-read, never re-written.
"""

import json
import sqlite3
from contextlib import contextmanager
from typing import Any, Dict, Iterable, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            TEXT    NOT NULL,
    kind          TEXT    NOT NULL,   -- screen | structure | submit | pin_check | redeploy
    underlying    TEXT,
    expiry        TEXT,
    inputs_json   TEXT    NOT NULL,   -- everything the decision saw
    intent_json   TEXT,               -- what it wanted to do
    note          TEXT
);

CREATE TABLE IF NOT EXISTS vetoes (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            TEXT    NOT NULL,
    decision_id   INTEGER,
    rule          TEXT    NOT NULL,   -- guardrail number/name that fired
    detail_json   TEXT    NOT NULL,
    FOREIGN KEY (decision_id) REFERENCES decisions(id)
);

CREATE TABLE IF NOT EXISTS orders (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            TEXT    NOT NULL,
    decision_id   INTEGER,
    broker_id     TEXT,
    status        TEXT,
    intended_json TEXT    NOT NULL,   -- legs + net limit we sent
    response_json TEXT,               -- what the broker echoed back
    FOREIGN KEY (decision_id) REFERENCES decisions(id)
);

-- One row per leg per fill event. Reconciliation lives here.
CREATE TABLE IF NOT EXISTS fills (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    ts             TEXT    NOT NULL,
    order_id       INTEGER,
    broker_id      TEXT,
    symbol         TEXT    NOT NULL,
    signed_qty     INTEGER NOT NULL,
    fill_price     REAL,
    quote_bid      REAL,               -- NBBO captured at submit time
    quote_ask      REAL,
    quote_ts       TEXT,
    quote_age_s    REAL,
    quote_status   TEXT,               -- ok | stale | unquotable
    FOREIGN KEY (order_id) REFERENCES orders(id)
);

-- The scored number is a mark, not money. This table is the whole point.
CREATE TABLE IF NOT EXISTS marks (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    ts             TEXT    NOT NULL,
    snapshot_id    TEXT    NOT NULL,   -- groups legs sampled in one pass
    symbol         TEXT    NOT NULL,
    signed_qty     INTEGER NOT NULL,
    broker_mark    REAL,               -- broker's market_value for the leg
    bid            REAL,
    ask            REAL,
    quote_ts       TEXT,
    quote_age_s    REAL,
    status         TEXT    NOT NULL,   -- ok | stale | unquotable
    feed           TEXT                -- which options feed priced this row
);

CREATE TABLE IF NOT EXISTS equity (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    ts             TEXT    NOT NULL,
    snapshot_id    TEXT    NOT NULL,
    broker_equity  REAL,
    cash           REAL,
    note           TEXT
);

CREATE INDEX IF NOT EXISTS idx_marks_snapshot ON marks(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_decisions_ts   ON decisions(ts);
"""


class Journal:
    def __init__(self, path: str = "journal.db"):
        self.path = path
        self._conn: Optional[sqlite3.Connection] = None

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        # WAL so a read never blocks the writer. Learned the hard way on a
        # 4.5GB screener DB where analysis queries stalled the trading loop.
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.executescript(SCHEMA)
        conn.commit()
        self._conn = conn
        return conn

    @contextmanager
    def cursor(self):
        if self._conn is None:
            self.connect()
        cur = self._conn.cursor()
        try:
            yield cur
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
        finally:
            cur.close()

    # ---------- writers ----------

    def record_decision(
        self,
        ts: str,
        kind: str,
        inputs: Dict[str, Any],
        intent: Optional[Dict[str, Any]] = None,
        underlying: Optional[str] = None,
        expiry: Optional[str] = None,
        note: Optional[str] = None,
    ) -> int:
        with self.cursor() as cur:
            cur.execute(
                "INSERT INTO decisions (ts, kind, underlying, expiry, inputs_json, intent_json, note)"
                " VALUES (?,?,?,?,?,?,?)",
                (ts, kind, underlying, expiry, json.dumps(inputs, default=str),
                 json.dumps(intent, default=str) if intent is not None else None, note),
            )
            return cur.lastrowid

    def record_veto(self, ts: str, decision_id: Optional[int], rule: str, detail: Dict[str, Any]) -> int:
        with self.cursor() as cur:
            cur.execute(
                "INSERT INTO vetoes (ts, decision_id, rule, detail_json) VALUES (?,?,?,?)",
                (ts, decision_id, rule, json.dumps(detail, default=str)),
            )
            return cur.lastrowid

    def record_order(
        self,
        ts: str,
        decision_id: Optional[int],
        intended: Dict[str, Any],
        broker_id: Optional[str] = None,
        status: Optional[str] = None,
        response: Optional[Dict[str, Any]] = None,
    ) -> int:
        with self.cursor() as cur:
            cur.execute(
                "INSERT INTO orders (ts, decision_id, broker_id, status, intended_json, response_json)"
                " VALUES (?,?,?,?,?,?)",
                (ts, decision_id, broker_id, status, json.dumps(intended, default=str),
                 json.dumps(response, default=str) if response is not None else None),
            )
            return cur.lastrowid

    def record_fill(self, ts: str, order_id: Optional[int], leg: Dict[str, Any]) -> int:
        with self.cursor() as cur:
            cur.execute(
                "INSERT INTO fills (ts, order_id, broker_id, symbol, signed_qty, fill_price,"
                " quote_bid, quote_ask, quote_ts, quote_age_s, quote_status)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (ts, order_id, leg.get("broker_id"), leg["symbol"], leg["signed_qty"],
                 leg.get("fill_price"), leg.get("quote_bid"), leg.get("quote_ask"),
                 leg.get("quote_ts"), leg.get("quote_age_s"), leg.get("quote_status", "ok")),
            )
            return cur.lastrowid

    def record_marks(self, ts: str, snapshot_id: str, rows: Iterable[Dict[str, Any]],
                     feed: Optional[str] = None) -> int:
        """Insert legs individually.

        A single transaction meant one constraint violation rolled back the
        whole snapshot -- and these quotes cannot be recovered afterwards, so
        losing three good legs to one bad one loses them permanently.
        """
        n = 0
        for r in rows:
            try:
                with self.cursor() as cur:
                    cur.execute(
                        "INSERT INTO marks (ts, snapshot_id, symbol, signed_qty, broker_mark,"
                        " bid, ask, quote_ts, quote_age_s, status, feed)"
                        " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        (ts, snapshot_id, r.get("symbol"), r.get("signed_qty"),
                         r.get("broker_mark"), r.get("bid"), r.get("ask"),
                         r.get("quote_ts"), r.get("quote_age_s"), r.get("status"), feed),
                    )
                n += 1
            except sqlite3.Error as exc:
                try:
                    self.record_decision(
                        ts, "mark_write_failed",
                        {"symbol": r.get("symbol"), "error": repr(exc)},
                    )
                except sqlite3.Error:
                    pass
        return n

    def record_equity(self, ts: str, snapshot_id: str, broker_equity: Optional[float],
                      cash: Optional[float], note: Optional[str] = None) -> int:
        with self.cursor() as cur:
            cur.execute(
                "INSERT INTO equity (ts, snapshot_id, broker_equity, cash, note) VALUES (?,?,?,?,?)",
                (ts, snapshot_id, broker_equity, cash, note),
            )
            return cur.lastrowid

    # ---------- readers ----------

    def snapshot_rows(self, snapshot_id: str):
        with self.cursor() as cur:
            cur.execute("SELECT * FROM marks WHERE snapshot_id = ?", (snapshot_id,))
            return [dict(r) for r in cur.fetchall()]

    def snapshot_ids(self):
        with self.cursor() as cur:
            cur.execute("SELECT DISTINCT snapshot_id FROM marks ORDER BY id")
            return [r[0] for r in cur.fetchall()]

    def reconciliation_rows(self):
        with self.cursor() as cur:
            cur.execute("SELECT * FROM fills ORDER BY id")
            return [dict(r) for r in cur.fetchall()]
