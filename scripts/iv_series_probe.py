#!/usr/bin/env python3
"""IV-series probe — see docs/probes/2026-08-26-iv-series-probe.md

Stage 1 characterizes the chain and is BARRED from issuing a verdict.
Stage 2 builds the IV series and judges it against thresholds registered before any data was seen.

Stdlib only, on purpose: the repo is MIT and must run for anyone who clones it.
"""
import argparse, json, math, os, statistics as st, sys, time, urllib.parse, urllib.request
from datetime import date, datetime, timedelta

DATA, TRADE = "https://data.alpaca.markets", "https://paper-api.alpaca.markets"

# ---- registered parameters (docs/probes/2026-08-26-iv-series-probe.md) ----
NAMES        = ["SPY", "AMD"]        # v1; v2 adds NFLX, AVGO via --names
START, END   = date(2024, 3, 1), date(2025, 2, 28)
DTE_LO, DTE_HI, DTE_TARGET = 21, 45, 30
MNY_LO, MNY_HI = 0.95, 1.05
MIN_TRADES, MIN_VOLUME = 10, 50      # stage 1 may lower these, with a recorded reason
RATE         = 0.04
PCT_WINDOW, PCT_MIN_OBS = 126, 63
NOISE_MEDIAN = 100 * (1 - math.sqrt(0.5))   # 29.289 — median |U-V| for iid uniforms

def _hdr():
    k, s = os.environ.get("ALPACA_KEY_ID"), os.environ.get("ALPACA_SECRET_KEY")
    if not k or not s:
        sys.exit("set ALPACA_KEY_ID and ALPACA_SECRET_KEY")
    return {"APCA-API-KEY-ID": k, "APCA-API-SECRET-KEY": s}

def get(host, path, **params):
    url = f"{host}{path}?{urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})}"
    for attempt in range(5):
        try:
            req = urllib.request.Request(url, headers=_hdr())
            with urllib.request.urlopen(req, timeout=45) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(2 * (attempt + 1)); continue
            if e.code == 404:
                return {}
            raise
    raise RuntimeError(f"giving up on {url}")

def paged(host, path, key, **params):
    out, tok = [], None
    while True:
        d = get(host, path, page_token=tok, **params)
        out += d.get(key) or []
        tok = d.get("next_page_token")
        if not tok:
            return out

# ---------- Black-Scholes ----------
def _N(x): return 0.5 * (1 + math.erf(x / math.sqrt(2)))

def bs(S, K, T, r, sig, cp):
    if T <= 0 or sig <= 0:
        return max(0.0, S - K) if cp == "C" else max(0.0, K - S)
    d1 = (math.log(S / K) + (r + sig * sig / 2) * T) / (sig * math.sqrt(T))
    d2 = d1 - sig * math.sqrt(T)
    if cp == "C":
        return S * _N(d1) - K * math.exp(-r * T) * _N(d2)
    return K * math.exp(-r * T) * _N(-d2) - S * _N(-d1)

def implied_vol(price, S, K, T, r, cp):
    """Bisection. Returns None outside no-arbitrage bounds — a price that implies no IV is data,
    not an error to paper over."""
    intrinsic = max(0.0, S - K * math.exp(-r * T)) if cp == "C" else max(0.0, K * math.exp(-r * T) - S)
    cap = S if cp == "C" else K * math.exp(-r * T)
    if not (intrinsic + 1e-8 < price < cap - 1e-8):
        return None
    lo, hi = 1e-4, 5.0
    if bs(S, K, T, r, hi, cp) < price:
        return None
    for _ in range(80):
        mid = (lo + hi) / 2
        if bs(S, K, T, r, mid, cp) < price: lo = mid
        else: hi = mid
    return (lo + hi) / 2

# ---------- data ----------
def stock_closes(sym):
    out, tok = {}, None
    while True:
        d = get(DATA, f"/v2/stocks/{sym}/bars", timeframe="1Day", adjustment="raw",
                start=START.isoformat(), end=END.isoformat(), limit=10000, page_token=tok)
        for b in d.get("bars") or []:
            out[b["t"][:10]] = b["c"]
        tok = d.get("next_page_token")
        if not tok:
            return out

def fridays(a, b):
    d = a + timedelta((4 - a.weekday()) % 7)
    while d <= b:
        yield d
        d += timedelta(7)

def chain(sym, expiry):
    """Both statuses: contracts expiring after today are 'active', earlier ones 'inactive'."""
    out = []
    for status in ("inactive", "active"):
        out += paged(TRADE, "/v2/options/contracts", "option_contracts",
                     underlying_symbols=sym, expiration_date=expiry.isoformat(),
                     status=status, limit=10000)
        if out:
            break
    return out

def option_bars(symbols, start, end):
    out = {}
    for i in range(0, len(symbols), 100):
        batch = symbols[i:i + 100]
        tok = None
        while True:
            d = get(DATA, "/v1beta1/options/bars", symbols=",".join(batch), timeframe="1Day",
                    start=start.isoformat(), end=end.isoformat(), limit=10000, page_token=tok)
            for s, bars in (d.get("bars") or {}).items():
                out.setdefault(s, []).extend(bars)
            tok = d.get("next_page_token")
            if not tok:
                break
    return out

def candidates(sym, closes):
    """Per session: the Friday expiry with DTE nearest 30 in [21,45], and every in-band strike
    ordered by distance from spot. v1 uses element 0; v2 walks the list."""
    exps = sorted(fridays(START, END + timedelta(60)))
    chains, out = {}, []
    for day_s in sorted(closes):
        day = date.fromisoformat(day_s)
        cands = [e for e in exps if DTE_LO <= (e - day).days <= DTE_HI]
        if not cands:
            continue
        exp = min(cands, key=lambda e: abs((e - day).days - DTE_TARGET))
        if exp not in chains:
            chains[exp] = chain(sym, exp)
        S = closes[day_s]
        by = {}
        for c in chains[exp]:
            K = float(c["strike_price"])
            if MNY_LO <= K / S <= MNY_HI:
                by.setdefault(K, {})[c["type"]] = c["symbol"]
        if not by:
            continue
        opts = [(K, v.get("call"), v.get("put")) for K, v in sorted(by.items(), key=lambda kv: abs(kv[0] - S))]
        out.append(dict(day=day_s, exp=exp.isoformat(), S=S, T=(exp - day).days / 365.0, opts=opts))
    return out

def all_symbols(cands, mode):
    if mode == "strict":
        return sorted({x for c in cands for x in c["opts"][0][1:] if x})
    return sorted({x for c in cands for K, cs, ps in c["opts"] for x in (cs, ps) if x})

def ok(b):
    return b and b["n"] >= MIN_TRADES and b["v"] >= MIN_VOLUME

def pick(c, idx, mode):
    """Return (K, call_bar, put_bar) for this session, or None."""
    for K, cs, ps in c["opts"]:
        cb, pb = idx.get((cs, c["day"])) if cs else None, idx.get((ps, c["day"])) if ps else None
        if ok(cb) or ok(pb):
            return K, (cb if ok(cb) else None), (pb if ok(pb) else None)
        if mode == "strict":
            return None
    return None

# ---------- stages ----------
def stage1(names, mode):
    print(f"STAGE 1 — chain characterization ({mode}).  BARRED from any verdict.\n")
    rep = {}
    for sym in names:
        closes = stock_closes(sym)
        cands = candidates(sym, closes)
        syms = all_symbols(cands, mode)
        idx = {(t, b["t"][:10]): b for t, bl in option_bars(syms, START, END).items() for b in bl}
        got = kept = 0
        ns = []
        for c in cands:
            for K, cs, ps in (c["opts"] if mode != "strict" else c["opts"][:1]):
                for t in (cs, ps):
                    b = idx.get((t, c["day"])) if t else None
                    if b:
                        got += 1; ns.append(b["n"])
                        if ok(b): kept += 1
        covered = sum(1 for c in cands if pick(c, idx, mode))
        rep[sym] = dict(sessions=len(closes), cands=len(cands), contracts=len(syms),
                        legbars=got, passing=kept, covered=covered,
                        n_med=st.median(ns) if ns else 0)
        r = rep[sym]
        print(f"{sym}:  sessions {r['sessions']}  contracts {r['contracts']}  leg-bars {r['legbars']}"
              f"  passing {r['passing']}")
        print(f"      sessions with a usable strike: {r['covered']}/{r['cands']} "
              f"({100*r['covered']/max(r['cands'],1):.1f}%)   median n {r['n_med']:.0f}\n")
    json.dump(rep, open(f"stage1_{mode}.json", "w"), indent=2)
    print(f"wrote stage1_{mode}.json — stage 1 issues NO verdict by construction")

def pct_rank(win, x):
    return 100.0 * sum(1 for v in win if v <= x) / len(win)

def stage2(names, mode):
    print(f"STAGE 2 ({mode}) — judged against thresholds registered before any data was seen.\n")
    for sym in names:
        closes = stock_closes(sym)
        cands = candidates(sym, closes)
        idx = {(t, b["t"][:10]): b for t, bl in
               option_bars(all_symbols(cands, mode), START, END).items() for b in bl}
        series, div = [], []
        for c in cands:
            got = pick(c, idx, mode)
            if not got:
                continue
            K, cb, pb = got
            a_, w_ = [], []
            for b, cp in ((cb, "C"), (pb, "P")):
                if not b:
                    continue
                x = implied_vol(b["c"], c["S"], K, c["T"], RATE, cp)
                y = implied_vol(b["vw"], c["S"], K, c["T"], RATE, cp)
                if x: a_.append(x)
                if y: w_.append(y)
            if a_:
                iv = sum(a_) / len(a_)
                series.append((c["day"], iv))
                if w_:
                    m = sum(w_) / len(w_)
                    if m > 0: div.append(abs(iv - m) / m)
        sessions = len(closes)
        missing = 1 - len(series) / sessions
        vals = [v for _, v in series]
        lg = [math.log(v) for v in vals]
        if len(lg) > 2:
            mu = sum(lg) / len(lg)
            num = sum((lg[i] - mu) * (lg[i+1] - mu) for i in range(len(lg)-1))
            den = sum((x - mu) ** 2 for x in lg)
            ac = num / den if den else 0.0
        else:
            ac = 0.0
        pcts, unusable = {}, 0
        for i, (d, v) in enumerate(series):
            win = [x for _, x in series[max(0, i - PCT_WINDOW):i]]
            if len(win) < PCT_MIN_OBS:
                unusable += 1; continue
            pcts[d] = pct_rank(win, v)
        days = [d for d, _ in series]
        dp = [abs(pcts[days[i+1]] - pcts[days[i]]) for i in range(len(days)-1)
              if days[i] in pcts and days[i+1] in pcts]
        med_dp = st.median(dp) if dp else float("nan")
        R = med_dp / NOISE_MEDIAN if dp else float("nan")
        M = st.median([abs(math.log(vals[i+1]/vals[i])) for i in range(len(vals)-1)]) if len(vals) > 1 else 0
        S_ = st.median(div) if div else float("nan")
        def band(x, p, c_, hi=False):
            if hi: return "PASS" if x >= p else ("CONDITIONAL" if x >= c_ else "FAIL")
            return "PASS" if x <= p else ("CONDITIONAL" if x <= c_ else "FAIL")
        v1, v2, v3 = band(missing, .10, .30), band(R, .40, .70), band(ac, .80, .50, hi=True)
        print(f"=== {sym} ===")
        print(f"  IV days {len(series)}/{sessions}   unusable (window rule) {unusable}")
        print(f"  1 missing-day share      {missing*100:6.1f}%              {v1}")
        print(f"  2 median|dp| {med_dp:6.2f}  R={R:5.2f}                    {v2}")
        print(f"  3 lag-1 autocorr log IV  {ac:6.3f}                {v3}")
        print(f"  attribution S/M = {S_/M if M else float('nan'):.2f}")
        print(f"  GATE: {'FAIL' if 'FAIL' in (v1,v2,v3) else ('CONDITIONAL' if 'CONDITIONAL' in (v1,v2,v3) else 'PASS')}\n")

def diag(names, mode):
    """Does the choice of print change the PERCENTILE? Registered reading, before running:
    median |p_c - p_vw| <= 5 -> print choice immaterial, S/M invalid as an eligibility gate.
    >= 15 -> it matters. Between -> ambiguous, conservative reading wins."""
    print(f"DIAGNOSTIC ({mode}) — percentile from last-trade vs volume-weighted print\n")
    print(f"{'name':6} {'days':>5} {'med|pc-pvw|':>12} {'p90':>7} {'max':>7}   reading")
    print("-"*62)
    for sym in names:
        closes = stock_closes(sym)
        cands = candidates(sym, closes)
        idx = {(t, b["t"][:10]): b for t, bl in
               option_bars(all_symbols(cands, mode), START, END).items() for b in bl}
        sc, sw = [], []
        for c in cands:
            got = pick(c, idx, mode)
            if not got: continue
            K, cb, pb = got
            a_, w_ = [], []
            for b, cp in ((cb, "C"), (pb, "P")):
                if not b: continue
                x = implied_vol(b["c"], c["S"], K, c["T"], RATE, cp)
                y = implied_vol(b["vw"], c["S"], K, c["T"], RATE, cp)
                if x: a_.append(x)
                if y: w_.append(y)
            if a_ and w_:
                sc.append((c["day"], sum(a_)/len(a_))); sw.append((c["day"], sum(w_)/len(w_)))
        def pcts(series):
            out={}
            for i,(d,v) in enumerate(series):
                win=[x for _,x in series[max(0,i-PCT_WINDOW):i]]
                if len(win)>=PCT_MIN_OBS: out[d]=pct_rank(win,v)
            return out
        pc, pw = pcts(sc), pcts(sw)
        both=[d for d in pc if d in pw]
        if not both:
            print(f"{sym:6} {'-':>5}  no overlapping days"); continue
        d=sorted(abs(pc[x]-pw[x]) for x in both)
        med=st.median(d); p90=d[int(.9*len(d))-1]; mx=d[-1]
        rd = "immaterial" if med<=5 else ("MATTERS" if med>=15 else "ambiguous")
        print(f"{sym:6} {len(both):>5} {med:>12.2f} {p90:>7.2f} {mx:>7.2f}   {rd}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", type=int, required=True, choices=(1, 2, 3))
    ap.add_argument("--select", choices=("strict", "traded"), default="strict",
                    help="strict = v1 (nearest strike only); traded = v2 (nearest strike with a passing bar)")
    ap.add_argument("--names", default=",".join(NAMES))
    a = ap.parse_args()
    names = [x.strip().upper() for x in a.names.split(",") if x.strip()]
    {1: stage1, 2: stage2, 3: diag}[a.stage](names, a.select)
