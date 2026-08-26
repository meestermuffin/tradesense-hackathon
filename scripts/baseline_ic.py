#!/usr/bin/env python3
"""Baseline signal IC — protocol registered at docs/probes/2026-08-26-baseline-ic-registration.md

Reads the committed series through the data boundary, so it runs for anyone who clones the repo.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.data.files import FileFeatureSource
from src.options.iv import realized_vol
from src.measurement.stats import spearman, newey_west_t, permutation_p

H, PCT_WINDOW, PCT_MIN_OBS, TRAIL_RV, SEED, DRAWS = 21, 126, 63, 21, 42, 1000
DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "data", "iv_series_2024-03_2025-02.csv.gz")

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
            fwd = realized_vol(spot[i:i + H + 1])
            trail = realized_vol(spot[i - TRAIL_RV:i + 1])
            if fwd is None or trail is None or trail <= 0:
                continue
            win = iv[max(0, i - PCT_WINDOW):i]
            if len(win) < PCT_MIN_OBS:
                continue
            pct = 100.0 * sum(1 for v in win if v <= iv[i]) / len(win)
            rec.append(dict(day=days[i], A=pct, B=iv[i] / trail, C=iv[i],
                            out=(iv[i] - fwd) / iv[i]))   # return on premium sold (addendum)
        per[sym] = rec
    return per

def daily(per, key):
    byday = {}
    for sym, rec in per.items():
        for r in rec:
            byday.setdefault(r["day"], []).append((r[key], r["out"]))
    out = []
    for d in sorted(byday):
        pairs = byday[d]
        if len(pairs) >= 5:
            out.append(([p[0] for p in pairs], [p[1] for p in pairs]))
    return out

def mean_ic(ds):
    vals = [spearman(s, o) for s, o in ds]
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else None

def main():
    src = FileFeatureSource(DATA)
    per = build(src)
    print(f"names {len(per)}   name-days {sum(len(v) for v in per.values())}\n")
    print(f"{'variant':38} {'mean IC':>9} {'NW t(21)':>9} {'perm p':>8}  verdict")
    print("-" * 82)
    res, ics_by = {}, {}
    for key, label in (("A", "A · IV percentile (126/63 trailing)"),
                       ("B", "B · IV / trailing 21d realized vol"),
                       ("C", "C · raw IV level  [CONTROL, not a strategy]")):
        ds = daily(per, key)
        ics = [spearman(s, o) for s, o in ds]
        ics = [v for v in ics if v is not None]
        ic = sum(ics) / len(ics)
        t = newey_west_t(ics, H)
        _, p = permutation_p(ds, mean_ic, draws=DRAWS, seed=SEED)
        if ic > 0:
            v = "EVIDENCE" if p <= 0.05 else ("WEAK" if p <= 0.20 else "NO EVIDENCE")
        else:
            v = "CONTRARY" if p <= 0.05 else "NO EVIDENCE"
        res[key] = v; ics_by[key] = ic
        print(f"{label:38} {ic:>9.4f} {t if t is None else round(t,2):>9} {p:>8.4f}  {v}")
    order = ["EVIDENCE", "WEAK", "NO EVIDENCE", "CONTRARY"]
    weaker = max(res[k] for k in ("A", "B")), None
    weaker = max((res["A"], res["B"]), key=lambda x: order.index(x))
    print(f"\ndays used {len(daily(per,'A'))}   horizon {H}   seed {SEED}   draws {DRAWS}")
    print(f"REGISTERED VERDICT (weaker of A and B): {weaker}")
    if res["A"] != res["B"]:
        print("A and B DISAGREE — reported as a finding per the registration")
    ica, icb, icc = (ics_by[k] for k in ("A", "B", "C"))
    print(f"\ncontrol comparison:  A {ica:+.4f}   B {icb:+.4f}   C(raw IV) {icc:+.4f}")
    best = max(ica, icb)
    if icc >= best:
        print("  -> C MATCHES OR EXCEEDS A/B: the percentile machinery adds nothing over "
              "selling whatever has the highest IV. Signal as designed NOT JUSTIFIED.")
    elif best - icc < 0.25 * abs(best) if best else False:
        print("  -> A/B exceed C only marginally: ranking against own history is doing little work.")
    else:
        print("  -> A/B materially exceed C: ranking against the name's own history is doing work.")

if __name__ == "__main__":
    main()
