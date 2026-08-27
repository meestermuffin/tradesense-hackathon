#!/usr/bin/env python3
"""Does the baseline IC survive a null that keeps the 21-session overlap?

Protocol registered at docs/pending/block-permutation.md, committed before this ran.

The published permutation shuffles the signal among names WITHIN each session. That leaves both
panels' time structure intact, and the outcome is 21 forward sessions on daily data, so consecutive
name-days share 20 of 21 outcome days. The null is more independent than the data, so its spread is
too narrow and the p-value comes out too small.

Three nulls, side by side:

  within-day   the published one (L=1), as a reproduction check
  block        PRIMARY. Permute the NAME labels as within-day does, but hold one permutation fixed
               across a contiguous block of L sessions instead of redrawing every session. Breaks
               the name-to-outcome pairing AND keeps the day-to-day persistence the outcome's
               21-session overlap creates. L=21 primary, L=42 secondary.
  shift        VOID, reported only so the record shows why. Rotating a name's signal in time pairs
               it with THAT SAME NAME's outcome, so identity survives and the null is "the
               association, lagged" rather than no association. Measured: it centres at -0.19 on the
               control instead of 0. Its own control caught it. See the addendum in the
               registration.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json  # noqa: E402
import random  # noqa: E402
import statistics  # noqa: E402

import job2_earnings as J  # noqa: E402

from src.data.files import FileFeatureSource  # noqa: E402
from src.measurement.stats import newey_west_t, spearman  # noqa: E402

H = J.H
BLOCK_LENGTHS = (1, 21, 42)
BLOCK_DRAWS = 2000
BLOCK_SEED = 20260827
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "iv_series_2024-03_2025-02.csv.gz")


def panel(per, key, excl=None):
    """{symbol: [(day, signal, outcome)]} in chronological order, exclusions applied."""
    out = {}
    for sym, (_, rec) in per.items():
        skip = excl.get(sym, set()) if excl else set()
        out[sym] = [(r["day"], r[key], r["out"]) for r in rec if r["day"] not in skip]
    return out


def mean_ic_from(pan):
    """Group by session, require 5 names, mean of the daily rank ICs."""
    byday = {}
    for rows in pan.values():
        for day, sig, out in rows:
            byday.setdefault(day, []).append((sig, out))
    ics = []
    for _, v in sorted(byday.items()):
        if len(v) >= 5:
            r = spearman([x[0] for x in v], [x[1] for x in v])
            if r is not None:
                ics.append(r)
    return (sum(ics) / len(ics) if ics else None), ics


def shifted(pan, s):
    """Rotate each name's SIGNAL by s, outcomes stay put. Same s for every name."""
    out = {}
    for sym, rows in pan.items():
        n = len(rows)
        if n == 0:
            out[sym] = rows
            continue
        k = s % n
        sigs = [r[1] for r in rows]
        rot = sigs[-k:] + sigs[:-k] if k else sigs
        out[sym] = [(rows[i][0], rot[i], rows[i][2]) for i in range(n)]
    return out


def block_name_perm(pan, L, rng):
    """PRIMARY null. Permute name labels, one permutation held fixed per block of L sessions.

    L=1 is the published within-day shuffle. Larger L keeps the persistence that the 21-session
    outcome overlap puts into the real IC series, which is the whole correction.
    """
    days = sorted({d for rows in pan.values() for d, _, _ in rows})
    names = sorted(pan)
    sig = {(s, d): v for s, rows in pan.items() for d, v, _ in rows}
    perm_for = {}
    for bi in range(0, len(days), L):
        shuf = names[:]
        rng.shuffle(shuf)
        mapping = dict(zip(names, shuf, strict=True))
        for d in days[bi : bi + L]:
            perm_for[d] = mapping
    new = {s: [] for s in names}
    for s in names:
        for d, _, o in pan[s]:
            src_name = perm_for[d][s]
            if (src_name, d) in sig:
                new[s].append((d, sig[(src_name, d)], o))
    return new


def within_day(pan, rng):
    byday = {}
    for sym, rows in pan.items():
        for idx, (day, sig, out) in enumerate(rows):
            byday.setdefault(day, []).append((sym, idx, sig, out))
    newsig = {}
    for _, v in byday.items():
        sigs = [x[2] for x in v]
        rng.shuffle(sigs)
        for (sym, idx, _, _), s in zip(v, sigs, strict=True):
            newsig[(sym, idx)] = s
    return {
        sym: [(d, newsig[(sym, i)], o) for i, (d, _, o) in enumerate(rows)]
        for sym, rows in pan.items()
    }


def p_from(actual, draws):
    """One-sided, (hits + 1) / (n + 1). A p of exactly zero would overclaim the resolution."""
    hits = sum(1 for v in draws if v is not None and v >= actual)
    return (hits + 1) / (len(draws) + 1)


def run(label, per, excl, sessions):
    print(f"\n{'=' * 78}\n{label}\n{'=' * 78}")
    print(f"  sessions {sessions}   effective independent windows at H={H}: ~{sessions // H}")
    print(
        f"\n  {'variant':34} {'IC':>8} {'NW t':>6} {'within-day':>11} {'SHIFT':>8} "
        f"{'blk21':>7} {'blk42':>7}"
    )
    print("  " + "-" * 84)
    results = {}
    for key, name in (
        ("A", "A · IV percentile"),
        ("B", "B · IV / trailing RV"),
        ("C", "C · raw IV level [CONTROL]"),
    ):
        pan = panel(per, key, excl)
        actual, ics = mean_ic_from(pan)
        t = newey_west_t(ics, H)

        pb, sd = {}, {}
        for L in BLOCK_LENGTHS:
            rng = random.Random(BLOCK_SEED)
            draws = [mean_ic_from(block_name_perm(pan, L, rng))[0] for _ in range(BLOCK_DRAWS)]
            draws = [d for d in draws if d is not None]
            pb[L] = p_from(actual, draws)
            sd[L] = statistics.stdev(draws)

        # Reported only so the record carries why it is void. See the registration addendum.
        longest = max(len(r) for r in pan.values())
        sh = [mean_ic_from(shifted(pan, s))[0] for s in range(H, longest - H)]
        p_sh = p_from(actual, sh)

        print(
            f"  {name:32} {actual:>+8.4f} {t:>6.2f} {pb[1]:>8.4f} {pb[21]:>8.4f} "
            f"{pb[42]:>8.4f} {p_sh:>8.4f}"
        )
        results[key] = dict(ic=actual, t=t, p_blk=pb, sd=sd, p_shift=p_sh)
    a = results["A"]
    print(
        f"\n  null sd, variant A:  L=1 {a['sd'][1]:.4f}   L=21 {a['sd'][21]:.4f}   "
        f"L=42 {a['sd'][42]:.4f}   (L=21 is {a['sd'][21] / a['sd'][1]:.1f}x the published null)"
    )
    print(
        f"  draws {BLOCK_DRAWS}   seed {BLOCK_SEED}   min attainable p {1 / (BLOCK_DRAWS + 1):.4f}"
    )
    return results


def verdict(p):
    if p <= 0.05:
        return "SURVIVES"
    if p <= 0.20:
        return "WEAK"
    return "NO EVIDENCE"


def main():
    src = FileFeatureSource(DATA)
    per = J.build(src)
    earn = json.load(open(J.EARN))
    contaminated = J.forward_contaminated(per, earn)

    base_sessions = len({r["day"] for _, rec in per.values() for r in rec})
    run("BASELINE — all name-days", per, None, base_sessions)

    ev_days = {
        d
        for sym, (_, rec) in per.items()
        for r in rec
        if (d := r["day"]) not in contaminated.get(sym, set())
    }
    ev = run(
        "EVENT-FREE — forward outcome window contains no announcement",
        per,
        contaminated,
        len(ev_days),
    )

    print(f"\n{'=' * 78}")
    print("REGISTERED DECISION — variant A, event-free sample, primary null")
    print("=" * 78)
    p = ev["A"]["p_blk"][21]
    v = verdict(p)
    print(f"  within-day p (L=1, published) {ev['A']['p_blk'][1]:.4f}   ->   block L=21 p {p:.4f}")
    print(f"  IC {ev['A']['ic']:+.4f} unchanged.  NW t {ev['A']['t']:.2f}")
    print(f"\n  VERDICT: {v}")
    print(
        {
            "SURVIVES": "  +0.1561 may be quoted, with the corrected p stated beside it.",
            "WEAK": "  May NOT be called significant. Report as suggestive, both p's shown.",
            "NO EVIDENCE": "  Headline WITHDRAWN from deck, video and repo.",
        }[v]
    )

    pc = ev["C"]["p_blk"][21]
    print(f"\n  null validity check — control C under the same block null: p {pc:.4f}")
    if pc <= 0.05:
        print("  !! C IS SIGNIFICANT. The null has an artifact and NO arm above is")
        print("     readable, including a favourable one. Registration says stop here.")
        return 1
    print("  C remains non-significant. The null is behaving.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
