"""Resolve a trade template into concrete contracts.

The LLM emits a template — {structure, target_delta, width, dte} — and this resolves it to
strikes. Deliberate: it keeps stale chains, missing strikes, contract multipliers and one-sided
books out of the model's surface, and makes the decision interface backtestable, which direct
contract selection is not.

**Delta is computed, not read.** Greeks are OPRA-gated and absent from the API response on this
account, so IV is inverted from the quote midpoint and delta derived from it.
"""

import datetime
import math

from .iv import implied_vol

RATE = 0.04


def bs_delta(S, K, T, r, sigma, cp):
    if T <= 0 or sigma <= 0:
        return (1.0 if S > K else 0.0) if cp == "C" else (-1.0 if S < K else 0.0)
    d1 = (math.log(S / K) + (r + sigma * sigma / 2) * T) / (sigma * math.sqrt(T))
    Nd1 = 0.5 * (1 + math.erf(d1 / math.sqrt(2)))
    return Nd1 if cp == "C" else Nd1 - 1.0


def _quality(q, max_spread_pct):
    bid, ask = q.get("bp", 0), q.get("ap", 0)
    if bid <= 0 or ask <= 0 or ask < bid:
        return None, "no two-sided quote"
    mid = (bid + ask) / 2
    if (ask - bid) / mid > max_spread_pct:
        return None, f"spread {100 * (ask - bid) / mid:.1f}% over cap"
    return mid, None


def select_vertical(client, underlying, spot, template, as_of=None):
    """Return a dict describing the spread, or a dict with `rejected` explaining why not.

    template: {structure: 'put_credit'|'call_credit', target_delta, width, dte_min, dte_max,
               max_spread_pct}
    """
    as_of = as_of or datetime.date.today()
    cp = "P" if template["structure"] == "put_credit" else "C"
    lo, hi = template.get("dte_min", 5), template.get("dte_max", 9)
    max_spr = template.get("max_spread_pct", 0.08)
    width = template["width"]
    target = abs(template["target_delta"])
    delta_tol = template.get("delta_tolerance", 0.15)

    # candidate expiries in the DTE band
    # explicit expiry bounds: the endpoint defaults to next weekend otherwise
    expiries = sorted(
        {
            c["expiration_date"]
            for c in client.option_contracts(
                underlying,
                exp_gte=(as_of + datetime.timedelta(days=lo)).isoformat(),
                exp_lte=(as_of + datetime.timedelta(days=hi)).isoformat(),
                status="active",
                limit=10000,
            )
        }
    )
    if not expiries:
        return dict(rejected=f"no expiry in {lo}-{hi} DTE")
    expiry = min(
        expiries, key=lambda e: abs((datetime.date.fromisoformat(e) - as_of).days - (lo + hi) / 2)
    )
    T = max((datetime.date.fromisoformat(expiry) - as_of).days, 1) / 365.0

    band = 0.25 * spot
    chain = [
        c
        for c in client.option_contracts(
            underlying,
            expiration_date=expiry,
            type_="put" if cp == "P" else "call",
            strike_gte=spot - band,
            strike_lte=spot + band,
            status="active",
            limit=1000,
        )
    ]
    if not chain:
        return dict(rejected=f"empty chain for {expiry}")
    by_strike = {float(c["strike_price"]): c["symbol"] for c in chain}
    quotes = client.option_quotes_latest([by_strike[k] for k in sorted(by_strike)])

    # invert IV from the mid, then derive delta — greeks are not served to this account
    cands = []
    for K in sorted(by_strike):
        q = quotes.get(by_strike[K])
        if not q:
            continue
        mid, why = _quality(q, max_spr)
        if mid is None:
            continue
        iv = implied_vol(mid, spot, K, T, RATE, cp)
        if not iv:
            continue
        cands.append(
            dict(
                strike=K,
                symbol=by_strike[K],
                mid=mid,
                iv=iv,
                delta=bs_delta(spot, K, T, RATE, iv, cp),
                q=q,
            )
        )
    considered = len(by_strike)
    if not cands:
        return dict(
            rejected=f"0 of {considered} strikes passed quote quality "
            f"(spread cap {max_spr * 100:.0f}%) and inversion"
        )

    short = min(cands, key=lambda c: abs(abs(c["delta"]) - target))
    achieved = abs(short["delta"])
    if abs(achieved - target) > delta_tol:
        # No strike sits near the target. Taking the nearest anyway is how a 0.25-delta template
        # ends up selling a 0.93-delta contract that is almost entirely intrinsic.
        #
        # Usually this means the quality filter survived only near-ATM strikes: percentage spreads
        # are tightest near the money, so a wide book leaves exactly the high-delta strikes and
        # discards the ones the template wants. Report the surviving range so that is legible
        # rather than looking like a missing chain.
        deltas = sorted(abs(c["delta"]) for c in cands)
        return dict(
            rejected=f"nearest delta {achieved:.2f} vs target {target:.2f}; only "
            f"{len(cands)}/{considered} strikes passed quality, spanning delta "
            f"{deltas[0]:.2f}-{deltas[-1]:.2f}"
        )

    # Strike spacing varies by name and price: a $5 wing does not exist on a $937 underlying.
    # Take the nearest *listed* strike to the requested distance rather than demanding it exactly.
    wing_side = [
        c
        for c in cands
        if (c["strike"] < short["strike"] if cp == "P" else c["strike"] > short["strike"])
    ]
    if not wing_side:
        return dict(rejected="no tradable strike on the protective side")
    long_ = min(wing_side, key=lambda c: abs(abs(c["strike"] - short["strike"]) - width))
    actual_width = abs(short["strike"] - long_["strike"])
    if actual_width > template.get("max_width", width * 2):
        return dict(
            rejected=f"nearest wing is {actual_width:g} wide, over the "
            f"{template.get('max_width', width * 2):g} cap"
        )

    credit_mid = short["mid"] - long_["mid"]
    credit_touch = short["q"]["bp"] - long_["q"]["ap"]
    if credit_mid <= 0:
        return dict(rejected="structure does not credit at mid")
    if credit_mid >= actual_width:
        # Credit above width implies negative max loss, which is an arbitrage, which means the
        # quotes are wrong — stale, crossed, or one side untraded. Never a real opportunity.
        return dict(
            rejected=f"credit {credit_mid:.2f} >= width {actual_width:g}: quotes are "
            f"not trustworthy, not an arbitrage"
        )
    return dict(
        underlying=underlying,
        structure=template["structure"],
        expiry=expiry,
        dte=(datetime.date.fromisoformat(expiry) - as_of).days,
        short=short,
        long=long_,
        width=actual_width,
        spot=spot,
        credit_mid=round(credit_mid, 4),
        credit_touch=round(credit_touch, 4),
        max_loss=round(width - credit_mid, 4),
        short_delta=round(short["delta"], 4),
    )
