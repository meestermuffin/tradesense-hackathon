#!/usr/bin/env python3
"""Build the per-name daily IV series and commit it to data/.

Imports `iv_series_probe` rather than reimplementing it. That is deliberate: the selection and
filtering rules are described by two committed pre-registrations, and importing the registered code
means the shipped series is provably produced by it. Reimplementing would silently allow drift
between what was registered and what was shipped.
"""

import argparse
import csv
import datetime
import gzip
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import iv_series_probe as P

UNIVERSE = ["SPY", "TSLA", "NVDA", "MSFT", "AAPL", "META", "AMZN", "INTC", "GOOGL", "AMD", "MU"]
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main(mode="traded", start=None, end=None, out=None):
    # Override the probe module's window rather than editing it: iv_series_probe.py is a
    # registered measurement artifact and its constants are what two pre-registrations describe.
    if start:
        P.START = datetime.date.fromisoformat(start)
    if end:
        P.END = datetime.date.fromisoformat(end)
    OUT = out or os.path.join(
        ROOT, "data", f"iv_series_{P.START.strftime('%Y-%m')}_{P.END.strftime('%Y-%m')}.csv.gz"
    )
    rows = []
    for sym in UNIVERSE:
        closes = P.stock_closes(sym)
        cands = P.candidates(sym, closes)
        idx = {
            (t, b["t"][:10]): b
            for t, bl in P.option_bars(P.all_symbols(cands, mode), P.START, P.END).items()
            for b in bl
        }
        kept = 0
        for c in cands:
            got = P.pick(c, idx, mode)
            if not got:
                continue
            K, cb, pb = got
            ivs = []
            for b, cp in ((cb, "C"), (pb, "P")):
                if not b:
                    continue
                v = P.implied_vol(b["c"], c["S"], K, c["T"], P.RATE, cp)
                if v:
                    ivs.append(v)
            if not ivs:
                continue
            rows.append(
                dict(
                    day=c["day"],
                    symbol=sym,
                    iv=f"{sum(ivs) / len(ivs):.6f}",
                    spot=f"{c['S']:.4f}",
                    strike=f"{K:.2f}",
                    expiry=c["exp"],
                    dte=round(c["T"] * 365),
                    legs=len(ivs),
                )
            )
            kept += 1
        print(f"{sym:6} {kept:4} sessions")
    rows.sort(key=lambda r: (r["day"], r["symbol"]))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with gzip.open(OUT, "wt", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\nwrote {OUT}  ({len(rows)} rows, {os.path.getsize(OUT) / 1024:.0f} KB)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--start")
    ap.add_argument("--end")
    ap.add_argument("--out")
    ap.add_argument("--select", default="traded")
    a = ap.parse_args()
    main(a.select, a.start, a.end, a.out)
