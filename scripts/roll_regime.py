#!/usr/bin/env python3
"""Does Roll go silent when volatility expands?

Registered reading, written before this ran:

  Roll is estimable only where bid-ask bounce dominates directional drift. In a volatility
  expansion -- exactly when spreads widen and a short-vega book takes its losses -- trade sequences
  trend, autocovariance turns non-negative, and Roll returns nothing.

  If estimable rate falls materially in the highest realized-range quartile, then a cost model built
  on Roll is silent precisely in the states where cost is highest, and it will understate cost where
  that matters most. Threshold: a drop of more than 10 percentage points from the lowest-range
  quartile to the highest is treated as confirmed.

  A flat or rising rate refutes the concern, and the estimator's coverage can be treated as
  regime-independent.

This is the failure mode the review said no item on its own list could have detected.
"""

import argparse
import os
import statistics as st
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
)
import iv_series_probe as P  # noqa: E402

from src.data.alpaca import DATA_HOST, AlpacaClient  # noqa: E402

MIN_TRADES, MIN_CHANGES = 20, 10


def roll_ok(prices):
    if len(prices) < MIN_TRADES:
        return False, "too_few_trades"
    d = [prices[i + 1] - prices[i] for i in range(len(prices) - 1)]
    n = len(d) - 1
    if n < MIN_CHANGES:
        return False, "too_few_changes"
    m = sum(d) / len(d)
    cov = sum((d[i] - m) * (d[i + 1] - m) for i in range(n)) / n
    return (cov < 0), ("" if cov < 0 else "non_negative_autocov")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--names", default="SPY,AMD,MU")
    ap.add_argument("--start", default="2026-03-02")
    ap.add_argument("--end", default="2026-08-25")
    a = ap.parse_args()
    names = [x.strip().upper() for x in a.names.split(",") if x.strip()]

    P.START = __import__("datetime").date.fromisoformat(a.start)
    P.END = __import__("datetime").date.fromisoformat(a.end)
    c = AlpacaClient()

    rows = []
    for sym in names:
        closes = P.stock_closes(sym)
        # same-day realized range from the underlying's own bar
        bars = {}
        tok = None
        while True:
            d = c.request(
                "GET",
                DATA_HOST,
                f"/v2/stocks/{sym}/bars",
                {
                    "timeframe": "1Day",
                    "start": a.start,
                    "end": a.end,
                    "limit": 10000,
                    "adjustment": "raw",
                    "page_token": tok,
                },
            )
            for b in d.get("bars") or []:
                bars[b["t"][:10]] = (b["h"] - b["l"]) / b["c"]
            tok = d.get("next_page_token")
            if not tok:
                break
        cands = P.candidates(sym, closes)
        for cd in cands:
            K, cs, ps = cd["opts"][0]
            sym_opt = cs or ps
            if not sym_opt or cd["day"] not in bars:
                continue
            try:
                d = c.request(
                    "GET",
                    DATA_HOST,
                    "/v1beta1/options/trades",
                    {"symbols": sym_opt, "start": cd["day"], "end": cd["day"], "limit": 10000},
                )
                tr = (d.get("trades") or {}).get(sym_opt) or []
            except Exception:
                continue
            ok, why = roll_ok([t["p"] for t in tr])
            rows.append(
                dict(underlying=sym, day=cd["day"], rng=bars[cd["day"]], ok=ok, why=why, n=len(tr))
            )
        print(f"  {sym}: {len(rows)} contract-days so far")

    rows.sort(key=lambda r: r["rng"])
    n = len(rows)
    print(f"\n{n} contract-days across {len(names)} names, {a.start}..{a.end}\n")
    print(f"{'realized range quartile':26} {'range %':>13} {'estimable':>10} {'trending':>9}")
    print("-" * 62)
    rates = []
    for i in range(4):
        blk = rows[i * n // 4 : (i + 1) * n // 4]
        if not blk:
            continue
        r = sum(1 for x in blk if x["ok"]) / len(blk)
        rates.append(r)
        trend = sum(1 for x in blk if x["why"] == "non_negative_autocov")
        lab = ["Q1 calmest", "Q2", "Q3", "Q4 most volatile"][i]
        print(
            f"{lab:26} {blk[0]['rng'] * 100:5.2f}-{blk[-1]['rng'] * 100:5.2f}% "
            f"{r * 100:9.1f}% {trend:9}"
        )
    if len(rates) == 4:
        drop = (rates[0] - rates[3]) * 100
        print(
            f"\ncalmest {rates[0] * 100:.1f}%  ->  most volatile {rates[3] * 100:.1f}%   "
            f"drop {drop:+.1f} pp"
        )
        print("registered threshold: a drop of more than 10 pp confirms the concern")
        print(f"VERDICT: {'CONFIRMED' if drop > 10 else 'NOT CONFIRMED at this sample'}")
        ok_rng = st.median([r["rng"] for r in rows if r["ok"]])
        no_rng = st.median([r["rng"] for r in rows if not r["ok"]])
        print(f"\nmedian range: estimable {ok_rng * 100:.2f}%  unestimable {no_rng * 100:.2f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
