#!/usr/bin/env python3
"""How independent are the universe's positions, really?

The risk limits size each position at 2% of equity and cap the book at 20%. That arithmetic assumes
ten positions are ten separate risks. This measures whether they are.

Committed because the number it produces (MEAN_PAIRWISE_CORRELATION in src/risk_profile.py) is used
in a risk calculation, and a figure feeding a risk calculation should be recomputable by whoever
doubts it.

Reads only the committed IV series -- no credentials, no network.
"""

import csv
import gzip
import math
import os
import statistics as st
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPLIT_LO, SPLIT_HI = 0.5, 2.0  # far outside any real single-session move


def corr(a, b):
    ma, mb = st.mean(a), st.mean(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    da = math.sqrt(sum((x - ma) ** 2 for x in a))
    db = math.sqrt(sum((y - mb) ** 2 for y in b))
    return num / (da * db) if da and db else float("nan")


def main():
    path = sorted(
        os.path.join(ROOT, "data", f)
        for f in os.listdir(os.path.join(ROOT, "data"))
        if f.startswith("iv_series_")
    )[-1]
    rows = list(csv.DictReader(gzip.open(path, "rt")))
    spot = {}
    for r in rows:
        spot.setdefault(r["symbol"], {})[r["day"]] = float(r["spot"])
    syms = sorted(spot)
    days = sorted(set.intersection(*[set(v) for v in spot.values()]))

    # The series stores RAW spot on purpose -- an option struck at 500 on pre-split NVDA references
    # the raw price, so pairing raw spot with raw option price is what makes the inversion valid.
    # It is wrong for returns, so split-sized jumps are dropped rather than treated as moves.
    rets, dropped = {}, 0
    for s in syms:
        out = []
        for i in range(len(days) - 1):
            ratio = spot[s][days[i + 1]] / spot[s][days[i]]
            out.append(None if (ratio < SPLIT_LO or ratio > SPLIT_HI) else math.log(ratio))
        rets[s] = out
    keep = [i for i in range(len(days) - 1) if all(rets[s][i] is not None for s in syms)]
    dropped = (len(days) - 1) - len(keep)

    v = {s: [rets[s][i] for i in keep] for s in syms}
    pairs = [corr(v[a], v[b]) for i, a in enumerate(syms) for b in syms[i + 1 :]]
    rbar = st.mean(pairs)
    n = len(syms)

    print(
        f"{os.path.basename(path)}  {n} names  {len(keep)} sessions  ({dropped} split-sized dropped)\n"
    )
    print("  pairwise daily-return correlation")
    print(
        f"    mean {rbar:+.3f}   median {st.median(pairs):+.3f}   "
        f"range {min(pairs):+.3f} to {max(pairs):+.3f}"
    )
    for k in (5, 10):
        print(
            f"    {k} equal positions behave like {k / (1 + (k - 1) * rbar):.2f} independent bets"
        )
    print()
    worst = sorted(keep, key=lambda i: st.mean([rets[s][i] for s in syms]))[:5]
    print("  worst common sessions")
    for i in worst:
        m = st.mean([rets[s][i] for s in syms])
        down = sum(1 for s in syms if rets[s][i] < 0)
        print(f"    {days[i + 1]}   mean {m * 100:+6.2f}%   {down}/{n} names down")
    print()
    print(
        "  A book of short put spreads loses on every one of those days at once. The per-position"
    )
    print("  cap bounds each loss; it does not make them independent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
