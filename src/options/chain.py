"""Assembling one expiry's chain: quotes by strike, and the vol inverted from those same quotes.

Lives here rather than in a script because two entry points need it -- the agent and the fill probe
-- and having the probe import it from `run_agent` made the two circular the moment `run_agent`
started reading the probe's gate.
"""

from src.models import Quote
from src.options.atm import atm_iv


def chain_quotes(client, bridge, underlying, expiry, spot, span=40):
    """Quotes by strike for `build_plan`, plus the raw quotes and the ATM vol for this expiry.

    Returns `(by_strike, raw, iv)`. The raw dict is handed to `atm_iv` so the vol is inverted from
    the same quotes the strikes are solved against — fetching twice would let them disagree.
    """

    cs = client.option_contracts(
        underlying,
        expiration_date=expiry.isoformat(),
        status="active",
        strike_gte=spot - span,
        strike_lte=spot + span,
        limit=2000,
    )
    puts = {c.strike_price: c.symbol for c in cs if c.type == "put"}
    calls = {c.strike_price: c.symbol for c in cs if c.type == "call"}
    syms = list(puts.values()) + list(calls.values())
    raw = bridge.get_quotes(syms)

    def q(sym):
        r = raw.get(sym)
        if not r or r.get("bid") is None or r.get("ask") is None:
            return None
        return Quote(bp=r["bid"], ap=r["ask"])

    out = {}
    for k in sorted(set(puts) & set(calls)):
        p, c = q(puts[k]), q(calls[k])
        if p and c:
            out[k] = (p, c)
    iv = atm_iv(client, underlying, expiry, spot, raw)
    return out, raw, iv
