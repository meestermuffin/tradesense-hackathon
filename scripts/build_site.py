#!/usr/bin/env python3
"""Build the public snapshot the GitHub Pages dashboard renders.

The page is **static**. GitHub Pages serves files, not code, and this repo is public — so nothing
on the page may hold a credential, and nothing on it can call Alpaca. It renders exactly what this
script commits and nothing more.

That makes staleness the failure mode to design against, not a caveat to add later: a dashboard
that looks live while showing Tuesday's book is worse than one that plainly says when it was
built. So `generated_at` goes in the payload and the page shows it prominently.

Reads the markwatch journal and, when credentials are present, the broker. Neither is required to
render — a clone with no `.env` still builds a page from the committed journal.

    uv run python scripts/build_site.py            # writes docs/data.json
    uv run python scripts/build_site.py --no-broker

Regenerate after the Thursday close and commit the result; that is what publishes the final
number.
"""

import argparse
import datetime
import json
import os
import sqlite3
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

# Pages serves `docs/` as the site root, so the page lives at docs/index.html rather than in a
# subdirectory. A submission URL should be the bare Pages address, not a path into it -- and a
# root that 404s is the first thing a judge would see.
SITE = os.path.join(REPO, "docs")
START_EQUITY = 100_000.0


def equity_curve(conn, every=10):
    """The equity series, thinned. 1,100 points is more than a sparkline can show honestly."""
    rows = list(conn.execute("SELECT ts, broker_equity FROM equity ORDER BY id"))
    if not rows:
        return []
    keep = rows[::every]
    if keep[-1] != rows[-1]:
        keep.append(rows[-1])  # never drop the latest point; it is the one people read
    return [{"ts": t, "equity": e} for t, e in keep if e is not None]


def fills(conn):
    """Every leg fill with the NBBO captured at submission.

    `vs_mid` here is against the **captured** mid, not the credit we computed at planning time.
    Those differ -- by 0.075 on one order -- and the computed one is what produced a published
    figure that had to be corrected. See issue #24.
    """
    out = []
    for r in conn.execute(
        "SELECT order_id, symbol, signed_qty, fill_price, quote_bid, quote_ask, quote_status"
        " FROM fills ORDER BY id"
    ):
        oid, sym, qty, px, bid, ask, status = r
        mid = None if bid is None or ask is None else round((bid + ask) / 2, 4)
        out.append(
            {
                "order": oid,
                "symbol": sym,
                "signed_qty": qty,
                "fill": px,
                "bid": bid,
                "ask": ask,
                "mid": mid,
                "quote_status": status,
            }
        )
    return out


def structures(conn):
    """Each submitted condor, netted to a credit against the captured NBBO."""
    out = []
    for oid, ts, broker_id, status, intended in conn.execute(
        "SELECT id, ts, broker_id, status, intended_json FROM orders ORDER BY id"
    ):
        legs = list(
            conn.execute(
                "SELECT symbol, signed_qty, fill_price, quote_bid, quote_ask"
                " FROM fills WHERE order_id = ? ORDER BY symbol",
                (oid,),
            )
        )
        if not legs:
            continue
        try:
            net_limit = json.loads(intended or "{}").get("net_limit")
        except ValueError:
            net_limit = None

        mid = touch = 0.0
        complete = True
        for _sym, qty, _px, bid, ask in legs:
            if bid is None or ask is None:
                complete = False
                continue
            short = qty < 0
            mid += (1 if short else -1) * (bid + ask) / 2
            # Sell the shorts at the bid, buy the longs at the ask: what the book actually pays.
            touch += bid if short else -ask
        out.append(
            {
                "order": oid,
                "ts": ts,
                "broker_id": broker_id,
                "status": status,
                "contracts": abs(legs[0][1]) if legs else None,
                "expiry": legs[0][0][3:9] if legs else None,
                "net_limit": net_limit,
                "credit_at_captured_mid": round(mid, 4) if complete else None,
                "credit_at_touch": round(touch, 4) if complete else None,
                "nbbo_complete": complete,
                "legs": [
                    {"symbol": s, "signed_qty": q, "fill": p, "bid": b, "ask": a}
                    for s, q, p, b, a in legs
                ],
            }
        )
    return out


def mark_quality(conn):
    """How much of the book could be priced from a live quote, and how stale those quotes were."""
    row = conn.execute(
        "SELECT COUNT(*), SUM(status = 'ok'), AVG(quote_age_s), MAX(ts) FROM marks"
    ).fetchone()
    total, ok, avg_age, latest = row
    return {
        "samples": total,
        "priced": ok,
        "coverage": round((ok or 0) / total, 4) if total else None,
        "mean_quote_age_s": round(avg_age, 2) if avg_age is not None else None,
        "latest": latest,
        "feed": "indicative",
        "note": "indicative quotes are DERIVED, not the true OPRA NBBO. Recorded per row.",
    }


def broker_state():
    """Live account and positions. Optional: the page must build on a clone with no credentials."""
    try:
        from src.data.alpaca import AlpacaClient

        c = AlpacaClient()
        acct = c.account()
        pos = c.positions()
        return {
            "equity": float(acct.equity),
            "cash": float(acct.cash),
            "open_legs": len(pos),
            "spot": c.stock_closes_latest(["SPY"])["SPY"],
        }
    except Exception as e:
        return {"unavailable": f"{type(e).__name__}: {str(e)[:120]}"}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--journal", default=os.path.join(REPO, "journal.db"))
    ap.add_argument("--no-broker", action="store_true", help="skip the live account read")
    ap.add_argument("--out", default=os.path.join(SITE, "data.json"))
    a = ap.parse_args(argv)

    if not os.path.exists(a.journal):
        print(f"journal not found: {a.journal}", file=sys.stderr)
        return 2

    conn = sqlite3.connect(a.journal)
    curve = equity_curve(conn)
    payload = {
        "generated_at": datetime.datetime.now(datetime.UTC).isoformat(),
        "start_equity": START_EQUITY,
        "equity_curve": curve,
        "latest_equity": curve[-1]["equity"] if curve else None,
        "structures": structures(conn),
        "fills": fills(conn),
        "mark_quality": mark_quality(conn),
        "broker": {"skipped": True} if a.no_broker else broker_state(),
        "disclaimer": (
            "Static snapshot. This page does not call any broker and holds no credentials; it "
            "renders the JSON committed alongside it. The trading signal this project began with "
            "was falsified and shelved -- see docs/2026-08-30-strategy-shelved.md. No predictive "
            "edge is claimed."
        ),
    }
    conn.close()

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)

    eq = payload["latest_equity"]
    print(f"  wrote {os.path.relpath(a.out, REPO)}")
    print(
        f"  equity {eq}   structures {len(payload['structures'])}   fills {len(payload['fills'])}"
    )
    print(f"  mark coverage {payload['mark_quality']['coverage']}")
    print(f"  generated_at {payload['generated_at']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
