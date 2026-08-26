"""Today's IV, from the live quote — because historical bars stop at yesterday.

`options/bars` refuses any window including the current session (403). The trailing percentile
window therefore ends yesterday, and today's observation has to come from `quotes/latest`.

**This is a definitional seam and it is not papered over.** The history is inverted from last-trade
closes; today's value is inverted from a quote midpoint. Measured on 2026-08-26, those two
definitions disagree by 46-94% of a typical daily IV move depending on the name. The seam is
recorded on every reading so the size of the resulting error is measurable rather than assumed:
tomorrow the same session appears in bars, and the two can be compared directly.
"""
import datetime
from .iv import implied_vol
from .selection import RATE

DTE_LO, DTE_HI, DTE_TARGET = 21, 45, 30
MNY_LO, MNY_HI = 0.95, 1.05


def live_iv(client, symbol, spot, as_of=None):
    """Mirror the series construction: Friday expiry nearest 30 DTE, nearest-ATM strike in band,
    call/put mean. Returns None with a reason rather than guessing."""
    as_of = as_of or datetime.date.today()
    chain = client.option_contracts(
        symbol, exp_gte=(as_of + datetime.timedelta(days=DTE_LO)).isoformat(),
        exp_lte=(as_of + datetime.timedelta(days=DTE_HI)).isoformat(),
        status="active", limit=10000)
    fridays = sorted({c["expiration_date"] for c in chain
                      if datetime.date.fromisoformat(c["expiration_date"]).weekday() == 4})
    if not fridays:
        return None, f"no Friday expiry in {DTE_LO}-{DTE_HI} DTE"
    expiry = min(fridays, key=lambda e: abs(
        (datetime.date.fromisoformat(e) - as_of).days - DTE_TARGET))
    T = (datetime.date.fromisoformat(expiry) - as_of).days / 365.0

    by_strike = {}
    for c in chain:
        if c["expiration_date"] != expiry:
            continue
        K = float(c["strike_price"])
        if MNY_LO <= K / spot <= MNY_HI:
            by_strike.setdefault(K, {})[c["type"]] = c["symbol"]
    if not by_strike:
        return None, "no in-band strike"

    for K in sorted(by_strike, key=lambda k: abs(k - spot)):
        pair = by_strike[K]
        syms = [s for s in (pair.get("call"), pair.get("put")) if s]
        quotes = client.option_quotes_latest(syms)
        ivs = []
        for cp, key in (("C", "call"), ("P", "put")):
            s = pair.get(key)
            q = quotes.get(s) if s else None
            if not q or q.get("bp", 0) <= 0 or q.get("ap", 0) <= 0:
                continue
            v = implied_vol((q["bp"] + q["ap"]) / 2, spot, K, T, RATE, cp)
            if v:
                ivs.append(v)
        if ivs:
            return dict(iv=sum(ivs) / len(ivs), strike=K, expiry=expiry, spot=spot,
                        legs=len(ivs), source="quote_mid",
                        seam="history is last-trade close; this is quote mid"), None
    return None, "no in-band strike produced an invertible two-sided quote"
