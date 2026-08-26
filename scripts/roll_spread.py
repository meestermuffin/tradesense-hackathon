#!/usr/bin/env python3
"""Estimate effective spread from trade sequences (Roll 1984), and validate against measured NBBO.

Committed because it was not, the first time. The result +0.500 was reported on 2026-08-26 from a
throwaway heredoc, which made it unreproducible — the exact defect the standing rule about
committing a measurement script before running it exists to prevent, broken the same day that rule
was quoted in the file the result went into. Review verdict: UNRESOLVABLE.

Method: absent information-driven price moves, consecutive trade-price changes have autocovariance
-s^2/4 purely from bid-ask bounce, so s = 2*sqrt(-cov). Needs only trade prices, which Alpaca serves
historically — unlike quotes, which it does not.

Writes per-contract output including every drop reason, so coverage can be audited rather than
assumed. Roll goes silent where price changes trend rather than bounce, and that is not random.
"""

import argparse
import csv
import datetime
import math
import os
import random
import statistics as st
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.data.alpaca import DATA_HOST, AlpacaClient

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIN_TRADES, MIN_CHANGES = 20, 10


def roll_estimate(prices):
    if len(prices) < MIN_TRADES:
        return None, "too_few_trades"
    d = [prices[i + 1] - prices[i] for i in range(len(prices) - 1)]
    n = len(d) - 1
    if n < MIN_CHANGES:
        return None, "too_few_changes"
    m = sum(d) / len(d)
    cov = sum((d[i] - m) * (d[i + 1] - m) for i in range(n)) / n
    if cov >= 0:
        return None, "non_negative_autocov"
    return 2 * math.sqrt(-cov), None


def spearman(a, b):
    def rk(x):
        o = sorted(range(len(x)), key=lambda i: x[i])
        r = [0] * len(x)
        for i, j in enumerate(o):
            r[j] = i + 1
        return r

    ra, rb = rk(a), rk(b)
    n = len(ra)
    ma, mb = sum(ra) / n, sum(rb) / n
    num = sum((ra[i] - ma) * (rb[i] - mb) for i in range(n))
    da = math.sqrt(sum((x - ma) ** 2 for x in ra))
    db = math.sqrt(sum((x - mb) ** 2 for x in rb))
    return num / (da * db) if da and db else float("nan")


def perm_p(a, b, draws=200000, seed=42):
    """One-sided permutation p. With n=11 the asymptotics are worthless; the review computed
    p = 0.0609 for rho = +0.500, which is why this is reported wherever the rho is."""
    obs = spearman(a, b)
    rng = random.Random(seed)
    hits = 0
    bb = list(b)
    for _ in range(draws):
        rng.shuffle(bb)
        if spearman(a, bb) >= obs:
            hits += 1
    return obs, (hits + 1) / (draws + 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nbbo", default=None, help="capture CSV to validate against")
    ap.add_argument("--trade-date", default=None, help="session to read trades from")
    ap.add_argument("--draws", type=int, default=200000)
    a = ap.parse_args()

    nbbo = a.nbbo or sorted(f"data/nbbo/{f}" for f in os.listdir(f"{ROOT}/data/nbbo"))[-1]
    rows = list(csv.DictReader(open(os.path.join(ROOT, nbbo))))
    day = (
        a.trade_date
        or (
            datetime.date.fromisoformat(os.path.basename(nbbo)[5:15]) - datetime.timedelta(days=1)
        ).isoformat()
    )
    print(f"nbbo   {nbbo}  ({len(rows)} contracts)")
    print(f"trades {day}  (previous session — a window including today 403s)\n")

    c = AlpacaClient()
    out = []
    for r in rows:
        try:
            d = c.request(
                "GET",
                DATA_HOST,
                "/v1beta1/options/trades",
                {"symbols": r["symbol"], "start": day, "end": day, "limit": 10000},
            )
            tr = (d.get("trades") or {}).get(r["symbol"]) or []
        except Exception:
            tr = []
        est, why = roll_estimate([t["p"] for t in tr])
        out.append(
            dict(
                day=day,
                symbol=r["symbol"],
                underlying=r["underlying"],
                tenor=r["tenor"],
                strike=r["strike"],
                type=r["type"],
                n_trades=len(tr),
                roll=("" if est is None else round(est, 4)),
                drop_reason=why or "",
                measured_spread=r["spread"],
                measured_spread_pct=r["spread_pct"],
                mid=r["mid"],
            )
        )

    od = os.path.join(ROOT, "data", "roll")
    os.makedirs(od, exist_ok=True)
    op = os.path.join(od, f"roll_{day}.csv")
    with open(op, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)

    ok = [o for o in out if o["roll"] != ""]
    print(f"estimated {len(ok)} of {len(out)}")
    drops = {}
    for o in out:
        if o["drop_reason"]:
            drops[o["drop_reason"]] = drops.get(o["drop_reason"], 0) + 1
    for k, v in sorted(drops.items()):
        print(f"  dropped {v:3}  {k}")

    byname = {}
    for o in ok:
        byname.setdefault(o["underlying"], []).append(o)
    nm = sorted(byname)
    x = [st.median([float(o["roll"]) / float(o["mid"]) for o in byname[u]]) for u in nm]
    y = [st.median([float(o["measured_spread_pct"]) for o in byname[u]]) for u in nm]
    rho, p = perm_p(x, y, draws=a.draws)
    print(
        f"\nCROSS-NAME rho = {rho:+.3f}   permutation p = {p:.4f}  (n={len(nm)}, {a.draws} draws)"
    )
    print("  p is reported alongside rho deliberately: n=11 has no usable asymptotics, and the")
    print("  review computed p ~ 0.061 for rho +0.500 — a lead, not a settled result.")
    print(f"\nwrote {os.path.relpath(op, ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
