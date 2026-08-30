#!/usr/bin/env python3
"""What transaction cost drives the edge to zero?

Protocol registered at docs/pending/cost-breakeven.md, committed before this ran. Proposed by Solo:
bound the cost rather than estimate it, because the estimate may not be buildable at all -- Alpaca
serves no historical option quotes and the best bar proxy correlates at +0.036 cross-name.

The registered outcome is (IV_t - RV_fwd)/IV_t, the FRACTION OF PREMIUM RETAINED. It is already a
return on premium, so the breakeven cost is simply the mean outcome on the selected name-days, in
the same units. No repricing, no path simulation, no data we do not have.

**The signal being priced here is WEAK** -- the block-permutation run returned p 0.0660 on this
sample. A favourable bound grants the signal for argument. It does not restore significance.
"""

import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json  # noqa: E402

import block_permutation as BP  # noqa: E402
import job2_earnings as J  # noqa: E402

from src.data.files import FileFeatureSource  # noqa: E402

TOPN = (1, 3, 5, 10)
SEED, DRAWS, L = 20260827, 2000, 21

# Median spread as a share of mid, 132-quote capture 2026-08-26. docs/cost-model.md
SPREAD_PCT = dict(
    SPY=0.96,
    TSLA=1.52,
    NVDA=1.63,
    AAPL=3.01,
    MSFT=3.21,
    AMZN=3.42,
    AMD=3.62,
    META=4.75,
    INTC=5.14,
    GOOGL=5.21,
    MU=5.61,
)
# Measured: a marketable order paid 82% of the half-spread.
MARKETABLE_FRACTION = 0.82
# Two legs crossed BOTH WAYS, against a credit smaller than either leg. From the two test orders:
# SPY 0.06 cost / 0.62 credit = 9.7%; AMD 0.63 / 1.85 = 34%. These are COMPLETE ROUND TRIPS
# already -- do not multiply by 2 again. Ratio of credit-cost to mid-spread:
VERTICAL_MULTIPLIER = {"SPY": 9.7 / 0.96, "AMD": 34.0 / 3.62}


def selected(per, n, excl=None):
    """Top-n by IV percentile each session. Returns the outcomes of the selected name-days."""
    byday = {}
    for sym, (_, rec) in per.items():
        skip = excl.get(sym, set()) if excl else set()
        for r in rec:
            if r["day"] not in skip:
                byday.setdefault(r["day"], []).append((sym, r["A"], r["out"]))
    picked = []
    for _, v in sorted(byday.items()):
        if len(v) < 5:
            continue
        v.sort(key=lambda x: x[1], reverse=True)
        picked.extend(v[:n])
    return picked


def main():
    src = FileFeatureSource(BP.DATA)
    per = J.build(src)
    earn = json.load(open(J.EARN))
    contaminated = J.forward_contaminated(per, earn)

    # ERRATUM 2026-08-30: this carried a `* 2` for the round trip. The 9.7% / 34% calibrators
    # below are already both-legs-both-ways -- they come from complete round trips -- so the
    # multiplier re-applied it and every cost figure was overstated by exactly 2.00x.
    rt_mid = {s: v * MARKETABLE_FRACTION for s, v in SPREAD_PCT.items()}
    mult = statistics.mean(VERTICAL_MULTIPLIER.values())
    rt_credit = {s: v * mult for s, v in rt_mid.items()}

    print("Round-trip cost, measured, as a share of premium")
    print(f"  at {MARKETABLE_FRACTION:.0%} of the half-spread, and a vertical")
    print(f"  multiplier of {mult:.1f}x from the two test orders (cost vs NET CREDIT).\n")
    print(f"  {'name':6} {'spread %mid':>12} {'rt %mid':>9} {'rt %credit':>11}")
    for s in sorted(SPREAD_PCT, key=lambda x: SPREAD_PCT[x]):
        print(f"  {s:6} {SPREAD_PCT[s]:>11.2f}% {rt_mid[s]:>8.2f}% {rt_credit[s]:>10.1f}%")

    for label, excl in (("BASELINE", None), ("EVENT-FREE", contaminated)):
        print(f"\n{'=' * 78}\n{label}\n{'=' * 78}")
        print(
            f"  {'top-N':>6} {'name-days':>10} {'gross edge':>11} {'breakeven':>10}"
            f" {'vs rt cost':>11}"
        )
        print("  " + "-" * 54)
        for n in TOPN:
            picks = selected(per, n, excl)
            outs = [o for _, _, o in picks]
            g = statistics.mean(outs)
            costs = [rt_credit[s] / 100.0 for s, _, _ in picks]
            avg_cost = statistics.mean(costs)
            ratio = g / avg_cost if avg_cost else float("inf")
            print(f"  {n:>6} {len(picks):>10} {g:>10.2%} {g:>9.2%} {ratio:>10.2f}x")

        print("\n  per name at N=10 — breakeven vs that name's own measured cost")
        print(f"    {'name':6} {'n':>5} {'gross':>8} {'rt %credit':>11} {'ratio':>7}  verdict")
        picks = selected(per, 10, excl)
        byname = {}
        for s, _, o in picks:
            byname.setdefault(s, []).append(o)
        rows = []
        for s in sorted(byname, key=lambda x: SPREAD_PCT[x]):
            g = statistics.mean(byname[s])
            c = rt_credit[s] / 100.0
            r = g / c
            v = "SURVIVES" if r > 2 else ("MARGINAL" if r > 1 else "no")
            rows.append((s, r, v))
            print(f"    {s:6} {len(byname[s]):>5} {g:>7.2%} {rt_credit[s]:>10.1f}% {r:>6.2f}x  {v}")

        if excl is not None:
            picks10 = selected(per, 10, excl)
            outs = [o for _, _, o in picks10]
            g = statistics.mean(outs)
            avg_cost = statistics.mean([rt_credit[s] / 100.0 for s, _, _ in picks10])
            ratio = g / avg_cost
            print(f"\n{'=' * 78}\nREGISTERED DECISION — event-free, N=10\n{'=' * 78}")
            print(
                f"  gross edge {g:.2%} of premium   measured round-trip {avg_cost:.2%}"
                f"   ratio {ratio:.2f}x"
            )
            verdict = "SURVIVES" if ratio > 2 else "MARGINAL" if ratio > 1 else "DOES NOT SURVIVE"
            print(f"\n  VERDICT: {verdict}")
            print(
                {
                    "SURVIVES": "  Solo's bar met. Bound replaces the cost model.",
                    "MARGINAL": "  Survives with no margin. Cost model still blocks.",
                    "DOES NOT SURVIVE": "  The edge does not clear its own transaction costs.",
                }[verdict]
            )
            survivors = [s for s, r, v in rows if r > 2]
            print(f"\n  names clearing 2x: {survivors if survivors else 'NONE'}")
            print("\n  Reminder registered before the run: the signal priced here returned")
            print("  p 0.0660 under the corrected null. This bound grants the signal for")
            print("  argument; it does not restore significance. The spread data is one calm")
            print("  afternoon, so every cost above is a FLOOR.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
