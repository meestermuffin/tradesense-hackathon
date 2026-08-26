#!/usr/bin/env python3
"""Print-agreement filter: how often do the two IV estimators disagree enough to distrust the day?

The IV series inverts from the option bar's last-trade close. Inverting the same bar's
volume-weighted price gives a second reading of the same day. Where the two produce materially
different percentiles, that day's ranking is a statement about which print was used rather than
about volatility, and the name should be skipped.

The margin is derived, not chosen: skip when the disagreement exceeds the name's own median
day-over-day percentile move. Above that, the uncertainty about *today* is larger than a typical
day's real movement, so the reading carries less information than the noise in it.

Reports the rejection rate each candidate rule costs, because a filter nobody has priced is a filter
that gets switched off the first time it rejects something inconvenient.
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

PCT_WINDOW, PCT_MIN_OBS = 126, 63


def pct_rank(win, x):
    return 100.0 * sum(1 for v in win if v <= x) / len(win)


def series_for(client_mode, sym):
    closes = P.stock_closes(sym)
    cands = P.candidates(sym, closes)
    idx = {
        (t, b["t"][:10]): b
        for t, bl in P.option_bars(P.all_symbols(cands, client_mode), P.START, P.END).items()
        for b in bl
    }
    sc, sw = [], []
    for c in cands:
        got = P.pick(c, idx, client_mode)
        if not got:
            continue
        K, cb, pb = got
        a_, w_ = [], []
        for b, cp in ((cb, "C"), (pb, "P")):
            if not b:
                continue
            x = P.implied_vol(b["c"], c["S"], K, c["T"], P.RATE, cp)
            y = P.implied_vol(b["vw"], c["S"], K, c["T"], P.RATE, cp)
            if x:
                a_.append(x)
            if y:
                w_.append(y)
        if a_ and w_:
            sc.append((c["day"], sum(a_) / len(a_)))
            sw.append((c["day"], sum(w_) / len(w_)))
    return sc, sw


def percentiles(series):
    out = {}
    for i, (d, v) in enumerate(series):
        win = [x for _, x in series[max(0, i - PCT_WINDOW) : i]]
        if len(win) >= PCT_MIN_OBS:
            out[d] = pct_rank(win, v)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--names", default="SPY,MU,NVDA,AAPL,AMZN,MSFT,META,INTC,GOOGL,TSLA,AMD")
    ap.add_argument("--select", default="traded")
    a = ap.parse_args()
    names = [x.strip().upper() for x in a.names.split(",") if x.strip()]

    print(
        f"{'name':6} {'days':>5} {'med|dp|':>8} {'margin':>7} {'med disagree':>13} {'rejected':>9}"
    )
    print("-" * 56)
    rates, rows = [], []
    for sym in names:
        sc, sw = series_for(a.select, sym)
        pc, pw = percentiles(sc), percentiles(sw)
        both = [d for d in pc if d in pw]
        if len(both) < 10:
            print(f"{sym:6} insufficient overlap")
            continue
        both.sort()
        dp = [abs(pc[both[i + 1]] - pc[both[i]]) for i in range(len(both) - 1)]
        margin = st.median(dp)  # the name's own typical daily move
        dis = [abs(pc[d] - pw[d]) for d in both]
        rejected = sum(1 for x in dis if x > margin) / len(dis)
        rates.append(rejected)
        rows.append((sym, margin, st.median(dis), rejected))
        print(
            f"{sym:6} {len(both):5} {margin:8.2f} {margin:7.2f} {st.median(dis):13.2f} "
            f"{rejected * 100:8.1f}%"
        )
    if rates:
        print(f"\nuniverse mean rejection rate: {sum(rates) / len(rates) * 100:.1f}%")
        print("A filter is only worth registering with its cost stated. At this rate the book")
        print("trades fewer names on a given day, which interacts with the position cap.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
