#!/usr/bin/env python3
"""The IC on the sessions no prior test touched.

Protocol registered at docs/pending/extended-ic.md, committed before this ran.

Every prior IC test used iv_series_2024-03_2025-02 -- 249 sessions, ~11 independent windows at
H=21. iv_series_2024-03_2026-08 is a committed strict superset with 597 sessions, ~28 windows.

This is a re-test after a WEAK result, so the decision table is carried unchanged from 8a45517 and
binds both outcomes. The null is the corrected block-constant name permutation, identical to the
one that produced the WEAK verdict -- only the sample changes.

The panel is built on the FULL series and filtered by date afterwards, so every record keeps its
126-session trailing percentile window. Filtering the source first truncates that window silently.
"""

import json
import os
import random
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import block_permutation as BP  # noqa: E402
import job2_earnings as J  # noqa: E402

from src.data.files import FileFeatureSource  # noqa: E402
from src.measurement.stats import newey_west_t  # noqa: E402

LONG = os.path.join(BP.ROOT, "data", "iv_series_2024-03_2026-08.csv.gz")
L, DRAWS, SEED = 21, 2000, 20260827
OOS_START = "2025-03-01"
ORIG_END = "2025-02-28"


def window(per, lo=None, hi=None, excl=None, fwd_hi=None):
    """Filter built records by day. The trailing window is already baked in by J.build.

    `fwd_hi` additionally requires the FORWARD window to close by that date. Without it, filtering
    the long series to the original dates is not the original sample: the final H sessions had no
    forward outcome when the series ended there and gain one when it does not. That difference is
    exactly 21 sessions x 11 names, and it is what tripped the anchor on the first run.
    """
    out = {}
    for sym, (days, rec) in per.items():
        skip = excl.get(sym, set()) if excl else set()
        keep = []
        for r in rec:
            if lo is not None and r["day"] < lo:
                continue
            if hi is not None and r["day"] > hi:
                continue
            if r["day"] in skip:
                continue
            if fwd_hi is not None:
                j = r["i"] + J.H
                if j >= len(days) or days[j] > fwd_hi:
                    continue
            keep.append(r)
        out[sym] = (days, keep)
    return out


def arm(label, per, key, excl=None, lo=None, hi=None, fwd_hi=None):
    sub = window(per, lo, hi, excl, fwd_hi)
    pan = BP.panel(sub, key, None)
    actual, ics = BP.mean_ic_from(pan)
    if actual is None:
        print(f"  {label:44} — no data")
        return None
    t = newey_west_t(ics, BP.H)
    rng = random.Random(SEED)
    draws = [BP.mean_ic_from(BP.block_name_perm(pan, L, rng))[0] for _ in range(DRAWS)]
    draws = [d for d in draws if d is not None]
    p = BP.p_from(actual, draws)
    nd = sum(len(r) for _, r in sub.values())
    sessions = len({d for _, r in sub.values() for d in [x["day"] for x in r]})
    print(
        f"  {label:44} {nd:>6} {sessions:>5} {actual:>+8.4f} {t:>7.2f} {p:>8.4f} "
        f"{statistics.stdev(draws):>7.4f}"
    )
    return dict(ic=actual, t=t, p=p, n=nd, sessions=sessions)


def verdict(p):
    return "SURVIVES" if p <= 0.05 else ("WEAK" if p <= 0.20 else "NO EVIDENCE")


def main():
    per = J.build(FileFeatureSource(LONG))
    earn = json.load(open(J.EARN))
    cont = J.forward_contaminated(per, earn)

    hdr = f"  {'arm':44} {'n-days':>6} {'sess':>5} {'IC':>8} {'NW t':>7} {'p':>8} {'null sd':>7}"

    print("=" * 96)
    print("ANCHOR — must reproduce the prior run on the original window")
    print("=" * 96)
    print(hdr)
    anchor = arm("A · original 2024-03 → 2025-02", per, "A", hi=ORIG_END, fwd_hi=ORIG_END)
    arm("C · original [CONTROL]", per, "C", hi=ORIG_END, fwd_hi=ORIG_END)

    print("\n" + "=" * 96)
    print("PRIMARY — out-of-sample, sessions no prior test has touched")
    print("=" * 96)
    print(hdr)
    oos_a = arm("A · OOS 2025-03 → 2026-08", per, "A", lo=OOS_START)
    oos_c = arm("C · OOS [CONTROL]", per, "C", lo=OOS_START)
    arm("B · OOS [confounded, not decision-bearing]", per, "B", lo=OOS_START)

    print("\n" + "=" * 96)
    print("SECONDARY — full series")
    print("=" * 96)
    print(hdr)
    arm("A · full 2024-03 → 2026-08", per, "A")
    arm("C · full [CONTROL]", per, "C")

    print("\n" + "=" * 96)
    print("REPORTED, NOT DECISION-BEARING — event-free, only where earnings data exists")
    print("=" * 96)
    print(hdr)
    arm("A · event-free, through 2025-06", per, "A", excl=cont, hi="2025-06-25")

    print("\n" + "=" * 96)
    print("REGISTERED DECISION — A, baseline, out-of-sample window")
    print("=" * 96)
    if anchor:
        ok = abs(anchor["ic"] - 0.1753) < 0.0005
        got = f"{anchor['ic']:+.4f}"
        msg = "YES" if ok else "NO — " + got
        print(f"  anchor reproduces prior IC +0.1753: {msg}")
        if not ok:
            print("  !! The anchor does not reproduce. The panel differs from the prior run and")
            print("     nothing below is comparable to it. Stop.")
            return 1
    p = oos_a["p"]
    v = verdict(p)
    print(
        f"\n  IC {oos_a['ic']:+.4f}   NW t {oos_a['t']:.2f}   p {p:.4f}   "
        f"({oos_a['sessions']} sessions, ~{oos_a['sessions'] // BP.H} independent windows)"
    )
    print(f"\n  VERDICT: {v}")
    print(
        {
            "SURVIVES": "  Significant out-of-sample. Quotable WITH the corrected p, the\n"
            "  baseline-vs-event-free limitation, and the universe look-ahead caveat.",
            "WEAK": "  May not be called significant. Two independent samples now say\n"
            "  underpowered. Signal work stops.",
            "NO EVIDENCE": "  Withdrawn. Signal work stops.",
        }[v]
    )

    print(f"\n  null validity — control C out-of-sample: p {oos_c['p']:.4f}")
    if oos_c["p"] <= 0.05:
        print("  !! C IS SIGNIFICANT. No arm is readable, including a favourable one.")
        return 1
    print("  C non-significant. The null is behaving.")

    print("\n  Registered caveats that travel with any favourable reading:")
    print("   - baseline arm only; earnings exclusion unavailable past 2025-06, so this")
    print("     cannot separate the ranking from a scheduled-event detector.")
    print("   - the 11 names were chosen on 2026 liquidity and the window runs to 2026-08,")
    print("     so universe selection reaches into the test period. Biases optimistic.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
