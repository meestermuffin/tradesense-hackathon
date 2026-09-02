"""Recover the NBBO for a submitted condor from the markwatch journal.

Monday's probe verdict carries `bid: null, ask: null` on all four legs, so
`vs_touch` is absent and `vs_mid` cannot be checked against a real midpoint.
The registration called that unreconstructable. It isn't: `submit()` passed a
`Recorder`, so the NBBO WAS captured at submit time. It went into `journal.db`
and nothing ever joined it back to the verdict file.

`_place` builds CondorLegFill with symbol/side/signed_qty/fill_price only --
`bid` and `ask` default to None -- which is the whole gap.

Reads only. Writes a corrected copy beside the verdict rather than editing it.

    python3 scripts/recover_probe_nbbo.py \
        --journal journal.db \
        --verdict data/probe/2026-08-31-verdict.json

Add --order-id to disambiguate if the journal holds several submissions.
"""

import argparse
import json
import os
import sqlite3
import sys

MULTIPLIER = 100


def load_journal_quotes(db_path, order_id=None):
    """Every NBBO capture in the journal, newest first, as {order_id|None: {sym: {...}}}."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    out = []
    # The capture lives on the decision, written before the order went out.
    for row in conn.execute("SELECT id, ts, kind, inputs_json FROM decisions ORDER BY id DESC"):
        try:
            inputs = json.loads(row["inputs_json"] or "{}")
        except (TypeError, ValueError):
            continue
        nbbo = inputs.get("nbbo_at_submit") or {}
        if not nbbo:
            continue
        # Join to the order placed inside that same decision, when there is one.
        orow = conn.execute(
            "SELECT broker_id, status FROM orders WHERE decision_id = ? ORDER BY id DESC LIMIT 1",
            (row["id"],),
        ).fetchone()
        out.append(
            {
                "decision_id": row["id"],
                "ts": row["ts"],
                "kind": row["kind"],
                "order_id": orow["broker_id"] if orow else None,
                "nbbo": nbbo,
            }
        )

    # Per-leg rows written at fill time carry the same capture, as a cross-check.
    fills = {}
    for row in conn.execute(
        "SELECT symbol, quote_bid, quote_ask, quote_status, quote_age_s, order_id"
        " FROM fills ORDER BY id"
    ):
        fills.setdefault(row["order_id"], {})[row["symbol"]] = {
            "bid": row["quote_bid"],
            "ask": row["quote_ask"],
            "status": row["quote_status"],
            "age_s": row["quote_age_s"],
        }
    conn.close()

    if order_id:
        out = [c for c in out if c["order_id"] == order_id]
    return out, fills


def leg_touch_price(side, bid, ask):
    """The touch this leg had to cross: a buyer lifts the ask, a seller hits the bid."""
    if bid is None or ask is None:
        return None
    return ask if str(side).lower() == "buy" else bid


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--journal", default="journal.db")
    ap.add_argument("--verdict", required=True)
    ap.add_argument("--order-id", default=None)
    ap.add_argument("--out", default=None, help="default: <verdict>.recovered.json")
    a = ap.parse_args(argv)

    if not os.path.exists(a.journal):
        print(f"journal not found: {a.journal}", file=sys.stderr)
        print(
            "It is runtime state and gitignored -- run this on the machine that ran the probe.",
            file=sys.stderr,
        )
        return 2

    verdict = json.load(open(a.verdict))
    order_id = a.order_id or verdict.get("order_id")
    captures, fills = load_journal_quotes(a.journal, order_id=None)

    if not captures:
        print(
            "no NBBO captures in the journal. The recorder was not passed, or the "
            "capture failed and was logged as a quote_error decision.",
            file=sys.stderr,
        )
        return 1

    chosen = None
    for c in captures:
        if order_id and c["order_id"] == order_id:
            chosen = c
            break
    if chosen is None:
        # Fall back to symbol overlap with the verdict's legs.
        want = {l["symbol"] for l in verdict.get("legs", [])}
        for c in captures:
            if want & set(c["nbbo"]):
                chosen = c
                break
    if chosen is None:
        print(
            f"found {len(captures)} captures but none match this verdict's order_id or symbols.",
            file=sys.stderr,
        )
        for c in captures[:5]:
            print(
                "   decision {} {} order={} syms={}".format(
                    c["decision_id"], c["ts"], c["order_id"], sorted(c["nbbo"])[:2]
                ),
                file=sys.stderr,
            )
        return 1

    nbbo = chosen["nbbo"]
    print(
        "matched decision {} ({}), order {}".format(
            chosen["decision_id"], chosen["ts"], chosen["order_id"]
        )
    )
    print()

    legs = []
    net_mid = 0.0
    net_touch = 0.0
    complete = True
    for leg in verdict.get("legs", []):
        sym = leg["symbol"]
        q = nbbo.get(sym) or {}
        bid, ask = q.get("bid"), q.get("ask")
        side = leg.get("side") or ""
        int(leg.get("signed_qty", 0))
        merged = dict(leg)
        merged["bid"], merged["ask"] = bid, ask
        merged["quote_ts"] = q.get("ts")

        if bid is None or ask is None:
            complete = False
            merged["nbbo_status"] = "missing in journal"
        else:
            mid = (bid + ask) / 2.0
            touch = leg_touch_price(side, bid, ask)
            # Signed the way the net price is: a buy pays out, a sell takes in.
            sign = -1.0 if str(side).lower() == "buy" else 1.0
            net_mid += sign * mid
            net_touch += sign * touch
            merged["mid"] = round(mid, 4)
            merged["touch"] = round(touch, 4)
            merged["nbbo_status"] = "recovered"
        legs.append(merged)

        print(
            f"  {sym:<22} {side:<4}  bid={str(bid):<7} ask={str(ask):<7}  "
            f"fill={str(leg.get('fill_price')):<6}  {merged['nbbo_status']}"
        )

    print()
    fill = verdict.get("fill")
    claimed_mid = verdict.get("credit_at_mid")
    result = {
        "source": "recovered from markwatch journal by scripts/recover_probe_nbbo.py",
        "journal_decision_id": chosen["decision_id"],
        "journal_ts": chosen["ts"],
        "order_id": chosen["order_id"] or order_id,
        "nbbo_complete": complete,
        "legs": legs,
    }

    if complete:
        real_mid = round(net_mid, 4)
        real_touch = round(net_touch, 4)
        result["net_credit_at_real_mid"] = real_mid
        result["net_credit_at_touch"] = real_touch
        print(f"net credit at REAL mid      {real_mid:+.4f}")
        print(f"net credit at touch         {real_touch:+.4f}")
        if claimed_mid is not None:
            drift = round(real_mid - claimed_mid, 4)
            result["computed_mid_vs_real_mid"] = drift
            print(f"credit_at_mid as computed   {claimed_mid:+.4f}   (drift {drift:+.4f})")
        if fill is not None:
            got = abs(fill)
            result["vs_real_mid"] = round(got - real_mid, 4)
            result["vs_touch"] = round(got - real_touch, 4)
            print()
            print(f"fill (magnitude)            {got:+.4f}")
            print(
                "vs REAL mid                 {:+.4f}   <- what tuesday_gate should read".format(
                    result["vs_real_mid"]
                )
            )
            print("vs touch                    {:+.4f}".format(result["vs_touch"]))
            print()
            print("per contract, vs mid        %+.2f USD" % (result["vs_real_mid"] * MULTIPLIER))
    else:
        print(
            "NBBO incomplete -- reporting per-leg only, no net figure. "
            "A partial net would be worse than none."
        )

    out_path = a.out or (a.verdict + ".recovered.json")
    with open(out_path, "w") as fh:
        json.dump(result, fh, indent=2, sort_keys=True)
    print()
    print(f"written: {out_path}  (the original verdict is untouched)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
