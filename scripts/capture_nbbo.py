#!/usr/bin/env python3
"""Capture NBBO across the universe. Run once per session, near the decision point.

**This dataset cannot be backfilled.** Alpaca serves no historical options quotes, so a session
missed is a session lost from the spread model forever. That is the entire reason this runs on a
schedule rather than on demand.

Writes data/nbbo/nbbo_YYYY-MM-DD.csv. Exits non-zero on failure so a scheduler can notice.
"""

import argparse
import csv
import datetime
import os
import platform
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.data.alpaca import AlpacaClient
from src.universe import UNIVERSE

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTDIR = os.path.join(ROOT, "data", "nbbo")

# Outputs are namespaced by account number. Two people running this against different accounts
# must not write the same path -- otherwise a second clone silently doubles the observations the
# spread model is fitted on, and per-cell counts (the thing that model is most fragile about)
# become wrong in a way nobody would notice.
# Strike selection is driven by moneyness, not by a count of nearest-ATM strikes.
#
# The first capture took the 6 nearest strikes, which put every contract at |delta| 0.36-0.56 --
# the entire 0.15-0.35 sweep grid fell outside it, so the capture could not answer the question it
# was collected for. A moneyness grid gives comparable delta coverage across names regardless of
# share price, which a fixed count does not: 6 strikes spans a very different delta range on a
# $87 underlying than on a $937 one.
#
# Puts run out to 0.82x spot to reach ~0.05 delta at 30 DTE; the near tenor needs less distance for
# the same delta but the extra strikes are cheap and their coverage is recorded either way.
PUT_MONEYNESS = [1.00, 0.985, 0.97, 0.955, 0.94, 0.925, 0.91, 0.89, 0.87, 0.85, 0.82]
CALL_MONEYNESS = [1.00, 1.02, 1.05]  # kept for put-call comparison at the money


def next_expiries(today, near_dte=9, far_dte=30):
    """Nearest listed Friday at or beyond each target DTE."""
    out = []
    for target in (near_dte, far_dte):
        d = today + datetime.timedelta(days=target)
        d += datetime.timedelta((4 - d.weekday()) % 7)  # roll to Friday
        out.append((d.isoformat(), f"{target}dte"))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--force",
        action="store_true",
        help="capture even when the market is closed (marks the rows rth=false)",
    )
    a = ap.parse_args()

    c = AlpacaClient()
    account = c.account()["account_number"]
    clock = c.clock()
    is_open = bool(clock.get("is_open"))
    if not is_open and not a.force:
        print(f"market closed (next open {clock.get('next_open')}) — not capturing.")
        print("Quotes outside regular hours are stale and wide; capturing them would pollute the")
        print("spread model with data that describes the overnight book. Use --force to override.")
        return 0

    spot = c.stock_closes_latest(UNIVERSE)
    today = datetime.date.today()
    meta, syms = {}, []
    for expiry, tenor in next_expiries(today):
        for s in UNIVERSE:
            if s not in spot:
                print(f"  no spot for {s}, skipping", file=sys.stderr)
                continue
            try:
                cs = c.option_contracts(s, expiration_date=expiry, limit=500)
            except Exception as e:
                print(f"  chain fetch failed {s} {expiry}: {e}", file=sys.stderr)
                continue
            chosen = {}
            for kind, grid in (("put", PUT_MONEYNESS), ("call", CALL_MONEYNESS)):
                avail = [x for x in cs if x["type"] == kind]
                if not avail:
                    continue
                for target in grid:
                    want = spot[s] * target
                    best = min(avail, key=lambda x: abs(float(x["strike_price"]) - want))
                    chosen[best["symbol"]] = best
            for k in chosen.values():
                syms.append(k["symbol"])
                meta[k["symbol"]] = dict(
                    underlying=s,
                    expiry=expiry,
                    tenor=tenor,
                    strike=float(k["strike_price"]),
                    type=k["type"],
                    spot=spot[s],
                )
    if not syms:
        print("no contracts resolved — nothing to capture", file=sys.stderr)
        return 1

    captured_at = datetime.datetime.now(datetime.UTC).isoformat()
    quotes = c.option_quotes_latest(syms)
    rows = []
    for sym, q in quotes.items():
        bid, ask = q.get("bp", 0), q.get("ap", 0)
        if bid <= 0 or ask <= 0 or ask < bid:
            continue  # a crossed or one-sided book is not a spread observation
        m = meta[sym]
        mid = (bid + ask) / 2
        rows.append(
            dict(
                captured_at=captured_at,
                account=account,
                host=platform.node(),
                rth=is_open,
                symbol=sym,
                **m,
                bid=bid,
                ask=ask,
                bid_sz=q.get("bs"),
                ask_sz=q.get("as"),
                mid=round(mid, 4),
                spread=round(ask - bid, 4),
                spread_pct=round((ask - bid) / mid, 6),
                moneyness=round(m["strike"] / m["spot"], 4),
                quote_t=q.get("t"),
            )
        )
    if not rows:
        print("no usable two-sided quotes returned", file=sys.stderr)
        return 1

    outdir = os.path.join(OUTDIR, account)
    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, f"nbbo_{today.isoformat()}.csv")
    new = not os.path.exists(path)
    with open(path, "a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        if new:
            w.writeheader()
        w.writerows(rows)

    import statistics as st

    med = st.median([r["spread_pct"] for r in rows])
    print(
        f"captured {len(rows)} quotes across {len({r['underlying'] for r in rows})} names "
        f"-> {os.path.relpath(path, ROOT)}"
    )
    print(f"  median spread {med * 100:.2f}% of mid   rth={is_open}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
