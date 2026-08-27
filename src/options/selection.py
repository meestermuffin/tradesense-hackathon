"""Resolve a trade template into concrete contracts.

The LLM emits a template — {structure, target_delta, width, dte} — and this resolves it to
strikes. Deliberate: it keeps stale chains, missing strikes, contract multipliers and one-sided
books out of the model's surface, and makes the decision interface backtestable, which direct
contract selection is not.

**Delta is computed, not read.** Greeks are OPRA-gated and absent from the API response on this
account, so IV is inverted from the quote midpoint and delta derived from it.

The result is `Spread | Rejection` rather than a dict that may or may not carry a `rejected` key.
Both are real outcomes and the caller must handle both; a union says so where `dict.get` did not.
"""

import datetime
import math

from ..models import Rejection, SelectionResult, Spread, StrikeCandidate, Template
from .iv import implied_vol

RATE = 0.04


def bs_delta(S, K, T, r, sigma, cp):
    if T <= 0 or sigma <= 0:
        return (1.0 if S > K else 0.0) if cp == "C" else (-1.0 if S < K else 0.0)
    d1 = (math.log(S / K) + (r + sigma * sigma / 2) * T) / (sigma * math.sqrt(T))
    Nd1 = 0.5 * (1 + math.erf(d1 / math.sqrt(2)))
    return Nd1 if cp == "C" else Nd1 - 1.0


def select_vertical(client, underlying, spot, template: Template, as_of=None) -> SelectionResult:
    """Resolve `template` against the live chain for `underlying`."""
    as_of = as_of or datetime.date.today()
    cp = template.cp

    # candidate expiries in the DTE band
    # explicit expiry bounds: the endpoint defaults to next weekend otherwise
    expiries = sorted(
        {
            c.expiration_date
            for c in client.option_contracts(
                underlying,
                exp_gte=(as_of + datetime.timedelta(days=template.dte_min)).isoformat(),
                exp_lte=(as_of + datetime.timedelta(days=template.dte_max)).isoformat(),
                status="active",
                limit=10000,
            )
        }
    )
    if not expiries:
        return Rejection(reason=f"no expiry in {template.dte_min}-{template.dte_max} DTE")
    mid_dte = (template.dte_min + template.dte_max) / 2
    expiry = min(expiries, key=lambda e: abs((e - as_of).days - mid_dte))
    dte = (expiry - as_of).days
    T = max(dte, 1) / 365.0

    band = 0.25 * spot
    chain = client.option_contracts(
        underlying,
        expiration_date=expiry.isoformat(),
        type_="put" if cp == "P" else "call",
        strike_gte=spot - band,
        strike_lte=spot + band,
        status="active",
        limit=1000,
    )
    if not chain:
        return Rejection(reason=f"empty chain for {expiry}")
    by_strike = {c.strike_price: c.symbol for c in chain}
    quotes = client.option_quotes_latest([by_strike[k] for k in sorted(by_strike)])

    # invert IV from the mid, then derive delta — greeks are not served to this account
    cands: list[StrikeCandidate] = []
    for K in sorted(by_strike):
        q = quotes.get(by_strike[K])
        if q is None or not q.two_sided or q.spread_pct > template.max_spread_pct:
            continue
        iv = implied_vol(q.mid, spot, K, T, RATE, cp)
        if not iv:
            continue
        cands.append(
            StrikeCandidate(
                strike=K,
                symbol=by_strike[K],
                mid=q.mid,
                iv=iv,
                delta=bs_delta(spot, K, T, RATE, iv, cp),
                quote=q,
            )
        )
    considered = len(by_strike)
    if not cands:
        return Rejection(
            reason=f"0 of {considered} strikes passed quote quality "
            f"(spread cap {template.max_spread_pct * 100:.0f}%) and inversion"
        )

    target = abs(template.target_delta)
    short = min(cands, key=lambda c: abs(abs(c.delta) - target))
    achieved = abs(short.delta)
    if abs(achieved - target) > template.delta_tolerance:
        # No strike sits near the target. Taking the nearest anyway is how a 0.25-delta template
        # ends up selling a 0.93-delta contract that is almost entirely intrinsic.
        #
        # Usually this means the quality filter survived only near-ATM strikes: percentage spreads
        # are tightest near the money, so a wide book leaves exactly the high-delta strikes and
        # discards the ones the template wants. Report the surviving range so that is legible
        # rather than looking like a missing chain.
        deltas = sorted(abs(c.delta) for c in cands)
        return Rejection(
            reason=f"nearest delta {achieved:.2f} vs target {target:.2f}; only "
            f"{len(cands)}/{considered} strikes passed quality, spanning delta "
            f"{deltas[0]:.2f}-{deltas[-1]:.2f}"
        )

    # Strike spacing varies by name and price: a $5 wing does not exist on a $937 underlying.
    # Take the nearest *listed* strike to the requested distance rather than demanding it exactly.
    wing_side = [
        c for c in cands if (c.strike < short.strike if cp == "P" else c.strike > short.strike)
    ]
    if not wing_side:
        return Rejection(reason="no tradable strike on the protective side")
    long_ = min(wing_side, key=lambda c: abs(abs(c.strike - short.strike) - template.width))
    actual_width = abs(short.strike - long_.strike)
    if actual_width > template.width_cap:
        return Rejection(
            reason=f"nearest wing is {actual_width:g} wide, over the {template.width_cap:g} cap"
        )

    credit_mid = short.mid - long_.mid
    credit_touch = short.quote.bid - long_.quote.ask
    # `Spread` refuses a non-crediting or wider-than-width structure on construction; catching it
    # here turns that invariant into the same Rejection the other refusals produce.
    try:
        return Spread(
            underlying=underlying,
            structure=template.structure,
            expiry=expiry,
            dte=dte,
            short=short,
            long=long_,
            width=actual_width,
            spot=spot,
            credit_mid=round(credit_mid, 4),
            credit_touch=round(credit_touch, 4),
            max_loss=round(actual_width - credit_mid, 4),
            short_delta=round(short.delta, 4),
        )
    except ValueError as e:
        return Rejection(reason=str(e).split("\n")[-1].strip() or str(e))
