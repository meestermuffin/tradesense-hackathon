#!/usr/bin/env python3
"""Two probes the 2026-08-30 review asked for.

Protocol registered at docs/pending/review-remediation.md, committed before this ran.

PROBE 1 -- availability-preserving null (defect D2). `block_name_perm` permutes across the full
universe and DROPS a name-day when the permuted source name has no row that day. On the ragged
event-free panel that is 25.2% of name-days per draw, so the null is computed on a panel smaller
and differently shaped than the observed one, and its spread is inflated ~10-13%. Run 1's reported
p of 0.0660 sits against a 0.05 threshold and the drop-corrected estimate is ~0.046-0.049 -- the
recorded WEAK may be wrong.

The fix draws one priority ordering per block and induces a permutation ON THE NAMES PRESENT EACH
DAY, so nothing is dropped and the day/name-count structure is preserved exactly.

PROBE 2 -- claim 23, the one UNTESTED. The outcome contains IV_t and signal A is a function of
IV_t. Arm C closes the cross-name LEVEL channel; A's within-name DEVIATION channel is unprobed.
Re-run A against -RV_fwd, which carries no IV term. RV_fwd is recoverable exactly from the panel:
out = 1 - RV_fwd/IV_t and C = IV_t, so RV_fwd = C * (1 - out).
"""

import json
import os
import random
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import block_permutation as BP  # noqa: E402
import extended_ic as EI  # noqa: E402
import job2_earnings as J  # noqa: E402

from src.data.files import FileFeatureSource  # noqa: E402
from src.measurement.stats import newey_west_t  # noqa: E402

L, DRAWS = 21, 2000
SEEDS = list(range(20260830, 20260840))


def avail_block_perm(pan, L, rng):
    """Block-constant permutation that NEVER drops a name-day.

    One priority ordering per block. On each session the i-th present name in natural order maps to
    the i-th present name in priority order -- a bijection on the observed set, so the day and
    name-count structure of every draw matches the observed panel exactly.
    """
    days = sorted({d for rows in pan.values() for d, _, _ in rows})
    names = sorted(pan)
    sig = {(s, d): v for s, rows in pan.items() for d, v, _ in rows}
    present = {}
    for s, rows in pan.items():
        for d, _, _ in rows:
            present.setdefault(d, []).append(s)

    order_for = {}
    for bi in range(0, len(days), L):
        pri = names[:]
        rng.shuffle(pri)
        rank = {n: i for i, n in enumerate(pri)}
        for d in days[bi : bi + L]:
            order_for[d] = rank

    new = {s: [] for s in names}
    for d in days:
        here = sorted(present[d])
        by_pri = sorted(here, key=lambda n: order_for[d][n])
        mapping = dict(zip(here, by_pri, strict=True))
        for s in here:
            new[s].append((d, sig[(mapping[s], d)], None))
    # reattach the observed outcomes
    out_of = {(s, d): o for s, rows in pan.items() for d, _, o in rows}
    return {s: [(d, v, out_of[(s, d)]) for d, v, _ in rows] for s, rows in new.items()}


def drop_rate(pan, perm_fn, seed):
    obs = sum(len(r) for r in pan.values())
    rng = random.Random(seed)
    got = sum(len(r) for r in perm_fn(pan, L, rng).values())
    return 100.0 * (obs - got) / obs


def run_null(pan, perm_fn, seed):
    rng = random.Random(seed)
    draws = [BP.mean_ic_from(perm_fn(pan, L, rng))[0] for _ in range(DRAWS)]
    return [d for d in draws if d is not None]


def probe1(per, cont):
    print("=" * 84)
    print("PROBE 1 — availability-preserving null on run 1's decision arm (defect D2)")
    print("=" * 84)
    pan = BP.panel(EI.window(per, excl=cont), "A", None)
    actual, ics = BP.mean_ic_from(pan)
    t = newey_west_t(ics, BP.H)
    print(f"  variant A, event-free: IC {actual:+.4f}, NW t {t:.2f}")

    d_old = drop_rate(pan, BP.block_name_perm, SEEDS[0])
    d_new = drop_rate(pan, avail_block_perm, SEEDS[0])
    print(
        print(
            f"\n  drop rate per draw — dropping null {d_old:.1f}%   "
            f"availability-preserving {d_new:.1f}%"
        )
    )
    if d_new > 0.05:
        print("  !! VALIDITY CHECK FAILED: the fix still drops name-days. Run is void.")
        return None

    print(f"\n  {'seed':>10} {'p':>8} {'null mean':>10} {'null sd':>9}")
    ps = []
    for seed in SEEDS:
        draws = run_null(pan, avail_block_perm, seed)
        p = BP.p_from(actual, draws)
        ps.append(p)
        print(
            f"  {seed:>10} {p:>8.4f} {statistics.mean(draws):>+10.4f} "
            f"{statistics.stdev(draws):>9.4f}"
        )

    old = run_null(pan, BP.block_name_perm, SEEDS[0])
    mean_p = statistics.mean(ps)
    print(
        f"\n  dropping null (as published, seed {SEEDS[0]}): p {BP.p_from(actual, old):.4f}, "
        f"sd {statistics.stdev(old):.4f}"
    )
    print(
        f"  availability-preserving: mean p {mean_p:.4f}, range {min(ps):.4f}-{max(ps):.4f}, "
        f"se {statistics.stdev(ps) / len(ps) ** 0.5:.4f}"
    )

    verdict = "SURVIVES" if mean_p <= 0.05 else "WEAK"
    print(
        f"\n  REGISTERED DECISION: run 1's record becomes {verdict} — ON THE ORIGINAL SAMPLE ONLY."
    )
    print("  Registered before the run: this cannot unshelve. Run 3 is drop-free at 0.2%, tests")
    print("  327 sessions no other run touched, and reads p 0.2184 at z 0.82.")
    return verdict


def probe2(per, cont):
    print("\n" + "=" * 84)
    print("PROBE 2 — does A survive an outcome with no IV term? (claim 23)")
    print("=" * 84)
    sub = EI.window(per, lo=EI.OOS_START)
    print(f"  {'arm':34} {'outcome':>14} {'IC':>9} {'NW t':>7} {'p':>8}")
    for key in ("A", "C"):
        for label, iv_free in (("registered (IV-t)", False), ("-RV_fwd (IV-free)", True)):
            rows = {}
            for sym, (_, rec) in sub.items():
                rows[sym] = [
                    (r["day"], r[key], (-(r["C"] * (1 - r["out"])) if iv_free else r["out"]))
                    for r in rec
                ]
            actual, ics = BP.mean_ic_from(rows)
            t = newey_west_t(ics, BP.H)
            draws = run_null(rows, avail_block_perm, SEEDS[0])
            print(
                f"  {key + ' · out-of-sample':34} {label:>14} {actual:>+9.4f} {t:>7.2f} "
                f"{BP.p_from(actual, draws):>8.4f}"
            )
    print("\n  Registered reading: persists with the same sign -> the +0.0414 residual is not")
    print("  shared-term arithmetic. Vanishes or reverses -> the in-sample +0.1753 was partly")
    print("  mechanical, and the shelving is strengthened. Either way it supports the shelving.")


def main():
    per = J.build(FileFeatureSource(EI.LONG))
    cont = J.forward_contaminated(per, json.load(open(J.EARN)))
    probe1(per, cont)
    probe2(per, cont)
    return 0


if __name__ == "__main__":
    sys.exit(main())
