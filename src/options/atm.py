"""At-the-money implied volatility, for the expiry actually being traded.

**Why this exists.** The agent shipped with `iv = 0.127` as a constructor default — a constant read
off 25 August data — and solved every strike against it. That is harmless on a day the tape happens
to agree and wrong on any other: at 0.20 the 20-delta strike lands 3 points closer than it should,
at 0.28 it is 7 points, and in both cases the realised delta sits well outside the 18–22 band that
guardrail #3 exists to enforce. The guardrail would then veto the trade it was given, which is the
right failure but an avoidable one.

**Why not `live_iv.py`.** That inverts at ~30 DTE, deliberately, to mirror how the committed IV
series was built. Correct for the series and wrong here: term structure is real, and a 2-day condor
is priced against 2-day vol, not 30-day.

**IV is computed, never read.** Greeks and `impliedVolatility` are OPRA-gated and absent from a 200
response on this account, so this inverts from the quote midpoint by bisection.
"""

from __future__ import annotations

import datetime

from .iv import implied_vol

RATE = 0.04


def nearest_strike(strikes, spot: float) -> float | None:
    """Closest listed strike to spot. Ties go to the higher strike, which is arbitrary but fixed."""
    ks = sorted(strikes)
    return min(ks, key=lambda k: (abs(k - spot), -k)) if ks else None


def atm_iv(
    client,
    underlying: str,
    expiry: datetime.date,
    spot: float,
    quotes: dict[str, dict],
    as_of: datetime.date | None = None,
    rate: float = RATE,
    max_strikes: int = 5,
) -> float | None:
    """Invert IV from the ATM contract of `expiry`, averaging call and put.

    `quotes` is the markwatch shape — `{symbol: {"bid": float, "ask": float, ...}}` — so the caller
    passes whatever it already fetched rather than this making its own round trip.

    Walks outward from the money if the nearest strike will not invert. A one-sided book on the ATM
    contract is an ordinary market state close to expiry, not an error, and the strike beside it is
    usually fine. Returns `None` rather than a guess when nothing inverts: a fabricated vol here
    would misplace every strike in the book.
    """
    as_of = as_of or datetime.date.today()
    dte = (expiry - as_of).days
    if dte <= 0:
        return None
    T = dte / 365.0

    cs = [
        c
        for c in client.option_contracts(
            underlying,
            expiration_date=expiry.isoformat(),
            status="active",
            strike_gte=spot - 15,
            strike_lte=spot + 15,
            limit=500,
        )
        if c.expiration_date == expiry
    ]
    if not cs:
        return None

    by_strike: dict[float, dict[str, str]] = {}
    for c in cs:
        if c.type:
            by_strike.setdefault(c.strike_price, {})[c.type] = c.symbol

    ordered = sorted(by_strike, key=lambda k: abs(k - spot))[:max_strikes]
    for k in ordered:
        pair = by_strike[k]
        vols = []
        for cp, key in (("C", "call"), ("P", "put")):
            sym = pair.get(key)
            q = quotes.get(sym) if sym else None
            if not q:
                continue
            bid, ask = q.get("bid"), q.get("ask")
            if bid is None or ask is None or bid <= 0 or ask <= 0 or ask < bid:
                continue
            v = implied_vol((bid + ask) / 2, spot, k, T, rate, cp)
            if v:
                vols.append(v)
        if vols:
            return sum(vols) / len(vols)
    return None
