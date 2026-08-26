#!/usr/bin/env python3
"""Job 2 — does the ranking still separate once scheduled-event name-days are removed?

Protocol: docs/probes/2026-08-26-baseline-ic-registration.md, addendum 2.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.data.files import FileFeatureSource
from src.measurement.stats import newey_west_t, permutation_p, spearman
from src.options.iv import realized_vol

H, PCT_WINDOW, PCT_MIN_OBS, TRAIL_RV, SEED, DRAWS, BLACKOUT = 21, 126, 63, 21, 42, 1000, 2
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "iv_series_2024-03_2025-02.csv.gz")
EARN = os.path.join(ROOT, "data", "earnings_8k_2024_2025.json")
TSLA_DELIVERY = {"2024-01-02", "2024-04-02", "2024-07-02", "2024-10-02", "2025-01-02", "2025-04-02"}


def build(src):
    per = {}
    for sym in src.symbols():
        rows = sorted(src.rows(sym), key=lambda r: r["day"])
        days = [r["day"] for r in rows]
        iv = [float(r["iv"]) for r in rows]
        spot = [float(r["spot"]) for r in rows]
        rec = []
        for i in range(len(rows)):
            if i + H >= len(rows) or i < max(PCT_MIN_OBS, TRAIL_RV):
                continue
            fwd = realized_vol(spot[i : i + H + 1])
            trail = realized_vol(spot[i - TRAIL_RV : i + 1])
            if fwd is None or trail is None or trail <= 0:
                continue
            win = iv[max(0, i - PCT_WINDOW) : i]
            if len(win) < PCT_MIN_OBS:
                continue
            pct = 100.0 * sum(1 for v in win if v <= iv[i]) / len(win)
            rec.append(
                dict(day=days[i], i=i, A=pct, B=iv[i] / trail, C=iv[i], out=(iv[i] - fwd) / iv[i])
            )
        per[sym] = (days, rec)
    return per


def forward_contaminated(per, earn):
    """Name-days whose 21-session FORWARD outcome window contains an announcement (addendum 3)."""
    out = {}
    for sym, (days, _) in per.items():
        ds = set(earn.get(sym, []))
        bad = set()
        for i in range(len(days)):
            if i + H >= len(days):
                continue
            lo, hi = days[i], days[i + H]
            if any(lo <= d <= hi for d in ds):
                bad.add(days[i])
        out[sym] = bad
    return out


def blackout_days(per, earn, drop_delivery):
    """Sessions within +/-BLACKOUT trading days of an announcement, per name."""
    out = {}
    for sym, (days, _) in per.items():
        dates = [
            d
            for d in earn.get(sym, [])
            if not (drop_delivery and sym == "TSLA" and d in TSLA_DELIVERY)
        ]
        idx = set()
        for d in dates:
            after = [k for k, x in enumerate(days) if x >= d]
            if not after:
                continue
            k = after[0]
            for j in range(k - BLACKOUT, k + BLACKOUT + 1):
                if 0 <= j < len(days):
                    idx.add(days[j])
        out[sym] = idx
    return out


def daily(per, key, excl=None):
    byday = {}
    for sym, (_, rec) in per.items():
        skip = excl.get(sym, set()) if excl else set()
        for r in rec:
            if r["day"] in skip:
                continue
            byday.setdefault(r["day"], []).append((r[key], r["out"]))
    return [([p[0] for p in v], [p[1] for p in v]) for d, v in sorted(byday.items()) if len(v) >= 5]


def mean_ic(ds):
    v = [spearman(s, o) for s, o in ds]
    v = [x for x in v if x is not None]
    return sum(v) / len(v) if v else None


def report(label, per, excl):
    print(f"\n--- {label} ---")
    n_days = len(daily(per, "A", excl))
    tot = sum(len(r) for _, r in per.values())
    dropped = (
        sum(len([x for x in r if x["day"] in excl.get(s, set())]) for s, (_, r) in per.items())
        if excl
        else 0
    )
    print(f"    name-days {tot - dropped} of {tot} ({dropped} excluded)   days {n_days}")
    res = {}
    for k, lab in (
        ("A", "A · IV percentile"),
        ("B", "B · IV/trailing RV [confounded]"),
        ("C", "C · raw IV [control]"),
    ):
        ds = daily(per, k, excl)
        ics = [spearman(s, o) for s, o in ds]
        ics = [x for x in ics if x is not None]
        ic = sum(ics) / len(ics)
        t = newey_west_t(ics, H)
        _, p = permutation_p(ds, mean_ic, draws=DRAWS, seed=SEED)
        res[k] = ic
        print(f"    {lab:32} IC {ic:+.4f}  NW t {t if t is None else round(t, 2):>6}  p {p:.4f}")
    return res


def main():
    src = FileFeatureSource(DATA)
    per = build(src)
    earn = json.load(open(EARN))
    base = report("ALL name-days (baseline)", per, None)
    prim = report(
        "scheduled-event days REMOVED (primary: all Item 2.02)",
        per,
        blackout_days(per, earn, drop_delivery=False),
    )
    sens = report(
        "sensitivity: TSLA delivery dates NOT treated as events",
        per,
        blackout_days(per, earn, drop_delivery=True),
    )
    print(f"\n{'=' * 70}\nJOB 2 — verdict rests on A, read against control C")
    print(
        f"  A: baseline {base['A']:+.4f}  ->  events removed {prim['A']:+.4f} "
        f"(change {prim['A'] - base['A']:+.4f})"
    )
    print(f"  C: baseline {base['C']:+.4f}  ->  events removed {prim['C']:+.4f}")
    print(
        f"  sensitivity A (delivery kept in sample): {sens['A']:+.4f} "
        f"(vs primary {prim['A']:+.4f}, diff {sens['A'] - prim['A']:+.4f})"
    )
    pw = report(
        "POWERED: forward outcome window contains NO announcement",
        per,
        forward_contaminated(per, earn),
    )
    print(f"  POWERED A: {pw['A']:+.4f}  (base {base['A']:+.4f}, chg {pw['A'] - base['A']:+.4f})")
    ch = prim["A"] - base["A"]
    if abs(ch) < 0.25 * abs(base["A"]):
        v = "SURVIVES — the ranking is NOT merely a scheduled-event detector"
    elif ch < 0:
        v = "COLLAPSES — the ranking is substantially a scheduled-event detector"
    else:
        v = "RISES — events were adding noise; the exclusion filter earns its place on evidence"
    print(f"  VERDICT: {v}")


if __name__ == "__main__":
    main()
