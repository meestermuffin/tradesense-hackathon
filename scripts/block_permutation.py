#!/usr/bin/env python3
"""Does the baseline IC survive a null that keeps the 21-session overlap?

Protocol registered at docs/pending/block-permutation.md, committed before this ran.

The published permutation shuffles the signal among names WITHIN each session. That leaves both
panels' time structure intact, and the outcome is 21 forward sessions on daily data, so consecutive
name-days share 20 of 21 outcome days. The null is more independent than the data, so its spread is
too narrow and the p-value comes out too small.

Three nulls, side by side:

  within-day   the published one, as a reproduction check
  shift        PRIMARY. Rotate each name's signal in time by a common offset, outcomes held in
               place. Preserves every autocorrelation and the cross-name co-movement; destroys only
               the signal-to-outcome alignment. Exhaustive over 124 offsets, so it is exact and
               DETERMINISTIC -- no seed.
  block        Contiguous session blocks reassigned at random. Robustness reading.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json  # noqa: E402
import random  # noqa: E402

import job2_earnings as J  # noqa: E402

from src.data.files import FileFeatureSource  # noqa: E402
from src.measurement.stats import newey_west_t, spearman  # noqa: E402

H = J.H
BLOCK_LENGTHS = (21, 42)
BLOCK_DRAWS = 10_000
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


def block_shuffled(pan, L, rng):
    """Cut each name's signal into contiguous blocks of L and reassign the blocks."""
    out = {}
    order = None
    for sym, rows in pan.items():
        n = len(rows)
        sigs = [r[1] for r in rows]
        blocks = [sigs[i : i + L] for i in range(0, n, L)]
        if order is None or len(order) != len(blocks):
            order = list(range(len(blocks)))
            rng.shuffle(order)
        flat = [v for b in (blocks[i] for i in order) for v in b][:n]
        while len(flat) < n:
            flat.append(sigs[len(flat)])
        out[sym] = [(rows[i][0], flat[i], rows[i][2]) for i in range(n)]
    return out


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

        rng = random.Random(42)
        wd = [mean_ic_from(within_day(pan, rng))[0] for _ in range(1000)]
        p_wd = p_from(actual, wd)

        longest = max(len(r) for r in pan.values())
        offsets = list(range(H, longest - H))
        sh = [mean_ic_from(shifted(pan, s))[0] for s in offsets]
        p_sh = p_from(actual, sh)

        pb = {}
        for L in BLOCK_LENGTHS:
            rng = random.Random(BLOCK_SEED)
            draws = [mean_ic_from(block_shuffled(pan, L, rng))[0] for _ in range(400)]
            pb[L] = p_from(actual, draws)

        print(
            f"  {name:34} {actual:>+8.4f} {t:>6.2f} {p_wd:>11.4f} {p_sh:>8.4f} "
            f"{pb[21]:>7.4f} {pb[42]:>7.4f}"
        )
        results[key] = dict(ic=actual, t=t, p_wd=p_wd, p_shift=p_sh, p_blk=pb, offsets=len(offsets))
    print(
        f"\n  shift offsets evaluated: {results['A']['offsets']} (exhaustive, deterministic, "
        f"min attainable p {1 / (results['A']['offsets'] + 1):.4f})"
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
    p = ev["A"]["p_shift"]
    v = verdict(p)
    print(f"  within-day p (published) {ev['A']['p_wd']:.4f}   ->   circular-shift p {p:.4f}")
    print(f"  IC {ev['A']['ic']:+.4f} unchanged.  NW t {ev['A']['t']:.2f}")
    print(f"\n  VERDICT: {v}")
    print(
        {
            "SURVIVES": "  +0.1561 may be quoted, with the corrected p stated beside it.",
            "WEAK": "  May NOT be called significant anywhere. Report as suggestive, both p's shown.",
            "NO EVIDENCE": "  Headline WITHDRAWN from deck, video and repo.",
        }[v]
    )

    pc = ev["C"]["p_shift"]
    print(f"\n  null validity check — control C under the same shift: p {pc:.4f}")
    if pc <= 0.05:
        print("  !! C IS SIGNIFICANT. The shift has introduced an artifact and NO arm above is")
        print("     readable, including a favourable one. Registration says stop here.")
        return 1
    print("  C remains non-significant. The null is behaving.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
