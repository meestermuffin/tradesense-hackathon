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
NAMES        = ["SPY", "AMD"]
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

def select(sym, closes):
    """For each session, the Friday expiry with DTE nearest 30 in [21,45], and the nearest-ATM
    strike inside the moneyness band. Returns [(day, expiry, call_sym, put_sym, spot, T)]."""
    exps = sorted(fridays(START, END + timedelta(60)))
    chains, picks = {}, []
    for day_s in sorted(closes):
        day = date.fromisoformat(day_s)
        cands = [e for e in exps if DTE_LO <= (e - day).days <= DTE_HI]
        if not cands:
            continue
        exp = min(cands, key=lambda e: abs((e - day).days - DTE_TARGET))
        if exp not in chains:
            chains[exp] = chain(sym, exp)
        S = closes[day_s]
        strikes = sorted({float(c["strike_price"]) for c in chains[exp]
                          if MNY_LO <= float(c["strike_price"]) / S <= MNY_HI})
        if not strikes:
            continue
        K = min(strikes, key=lambda k: abs(k - S))
        by = {(float(c["strike_price"]), c["type"]): c["symbol"] for c in chains[exp]}
        picks.append(dict(day=day_s, exp=exp.isoformat(), K=K, S=S,
                          T=(exp - day).days / 365.0,
                          call=by.get((K, "call")), put=by.get((K, "put"))))
    return picks

# ---------- stages ----------
def stage1():
    print("STAGE 1 — chain characterization.  BARRED from any verdict.\n")
    rep = {}
    for sym in NAMES:
        closes = stock_closes(sym)
        picks = select(sym, closes)
        syms = sorted({s for p in picks for s in (p["call"], p["put"]) if s})
        bars = option_bars(syms, START, END)
        idx = {(s, b["t"][:10]): b for s, bl in bars.items() for b in bl}
        got = kept = 0
        ns, vs, floors = [], [], []
        for p in picks:
            for leg in ("call", "put"):
                b = idx.get((p[leg], p["day"])) if p[leg] else None
                if not b:
                    continue
                got += 1; ns.append(b["n"]); vs.append(b["v"])
                if b["n"] >= MIN_TRADES and b["v"] >= MIN_VOLUME:
                    kept += 1
        for s, bl in bars.items():
            if bl: floors.append(min(b["t"][:10] for b in bl))
        rep[sym] = dict(sessions=len(closes), picks=len(picks), contracts=len(syms),
                        legbars=got, passing=kept,
                        n_med=st.median(ns) if ns else 0, v_med=st.median(vs) if vs else 0,
                        n_p10=(sorted(ns)[len(ns)//10] if ns else 0),
                        floor=min(floors) if floors else None)
        r = rep[sym]
        print(f"{sym}:  sessions {r['sessions']}  selected {r['picks']}  contracts {r['contracts']}")
        print(f"      leg-bars returned {r['legbars']}  passing filter {r['passing']} "
              f"({100*r['passing']/max(r['legbars'],1):.1f}%)")
        print(f"      trade-count n: median {r['n_med']:.0f}  p10 {r['n_p10']:.0f}   volume median {r['v_med']:.0f}")
        print(f"      earliest bar seen: {r['floor']}\n")
    json.dump(rep, open("stage1.json", "w"), indent=2)
    print("wrote stage1.json — stage 1 issues NO verdict by construction")

def pct_rank(win, x):
    return 100.0 * sum(1 for v in win if v <= x) / len(win)

def stage2():
    print("STAGE 2 — judged against thresholds registered before any data was seen.\n")
    for sym in NAMES:
        closes = stock_closes(sym)
        picks = select(sym, closes)
        syms = sorted({s for p in picks for s in (p["call"], p["put"]) if s})
        idx = {(s, b["t"][:10]): b for s, bl in option_bars(syms, START, END).items() for b in bl}
        series, div = [], []
        for p in picks:
            ivs_c, ivs_vw = [], []
            for leg, cp in (("call", "C"), ("put", "P")):
                b = idx.get((p[leg], p["day"])) if p[leg] else None
                if not b or b["n"] < MIN_TRADES or b["v"] < MIN_VOLUME:
                    continue
                a = implied_vol(b["c"], p["S"], p["K"], p["T"], RATE, cp)
                w = implied_vol(b["vw"], p["S"], p["K"], p["T"], RATE, cp)
                if a: ivs_c.append(a)
                if w: ivs_vw.append(w)
            if ivs_c:
                iv = sum(ivs_c) / len(ivs_c)
                series.append((p["day"], iv))
                if ivs_vw:
                    m = sum(ivs_vw) / len(ivs_vw)
                    if m > 0: div.append(abs(iv - m) / m)
        sessions = len(closes)
        missing = 1 - len(series) / sessions
        vals = [v for _, v in series]
        # lag-1 autocorrelation of log IV
        lg = [math.log(v) for v in vals]
        if len(lg) > 2:
            mu = sum(lg) / len(lg)
            num = sum((lg[i] - mu) * (lg[i+1] - mu) for i in range(len(lg)-1))
            den = sum((x - mu) ** 2 for x in lg)
            ac = num / den if den else 0.0
        else:
            ac = 0.0
        # percentile with the registered minimum-window rule
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

        def band(x, p, c, higher_better=False):
            if higher_better: return "PASS" if x >= p else ("CONDITIONAL" if x >= c else "FAIL")
            return "PASS" if x <= p else ("CONDITIONAL" if x <= c else "FAIL")
        v1 = band(missing, 0.10, 0.30)
        v2 = band(R, 0.40, 0.70)
        v3 = band(ac, 0.80, 0.50, higher_better=True)
        print(f"=== {sym} ===")
        print(f"  IV days {len(series)}/{sessions}   unusable (window rule) {unusable}")
        print(f"  1 missing-day share      {missing*100:6.1f}%              {v1}")
        print(f"  2 median|dp| {med_dp:6.2f}  R={R:5.2f} (noise={NOISE_MEDIAN:.2f})   {v2}")
        print(f"  3 lag-1 autocorr log IV  {ac:6.3f}                {v3}")
        print(f"  attribution: S={S_:.4f}  M={M:.4f}  S/M={S_/M if M else float('nan'):.2f}"
              f"  -> {'MEASUREMENT NOISE DOMINATES (filter harder)' if (M and S_ >= 0.5*M) else 'variation mostly genuine'}")
        verdict = "FAIL" if "FAIL" in (v1, v2, v3) else ("CONDITIONAL" if "CONDITIONAL" in (v1, v2, v3) else "PASS")
        print(f"  GATE: {verdict}\n")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", type=int, required=True, choices=(1, 2))
    a = ap.parse_args()
    (stage1 if a.stage == 1 else stage2)()
