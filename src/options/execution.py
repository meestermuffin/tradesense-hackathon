"""Multi-leg order placement, with the NBBO captured at submission.

Two things measured on 2026-08-26 shape this:

- Fills clear **better than the touch but not reliably at mid**, and the improvement is a small
  absolute amount that does not scale with spread width. On a 3-cent book a mid limit filled better
  than mid in 127 ms; on a 14-66 cent book a mid limit rested 26 seconds and never filled.
- The NBBO at submission is **unreconstructable** — there is no historical options quote endpoint.
  Capture it in the same breath as the order or the fill is uninterpretable forever.

The record this returns is a declared schema (`FillRecord`) rather than an assembled dict, for the
second reason above: it is the only evidence that will ever exist for these quotes.
"""

import datetime
import os
import time

from ..data.alpaca import leg
from ..models import FillRecord, NetQuote, Quote, SideQuote, Spread


def build_legs(candidate: Spread, closing=False):
    short_sym, long_sym = candidate.short.symbol, candidate.long.symbol
    if not closing:
        return [leg(short_sym, "sell", "sell_to_open"), leg(long_sym, "buy", "buy_to_open")]
    return [leg(short_sym, "buy", "buy_to_close"), leg(long_sym, "sell", "sell_to_close")]


def _net(quotes: dict[str, Quote], short_sym, long_sym, closing) -> NetQuote | None:
    s, l = quotes.get(short_sym), quotes.get(long_sym)
    if s is None or l is None:
        return None
    mid = s.mid - l.mid
    touch = (s.ask - l.bid) if closing else (s.bid - l.ask)
    return NetQuote(
        mid=round(mid, 4),
        touch=round(touch, 4),
        short=SideQuote(bid=s.bid, ask=s.ask),
        long=SideQuote(bid=l.bid, ask=l.ask),
    )


def place(
    client, candidate: Spread, contracts, closing=False, cross=0.0, poll_seconds=30, log_dir=None
) -> FillRecord:
    """Submit at mid (or `cross` through the touch), capture NBBO either side, return the record.

    `limit_price` is a NET price: positive is a debit, negative a credit. Opening a credit spread
    submits a negative limit; closing it submits a positive one.
    """
    short_sym, long_sym = candidate.short.symbol, candidate.long.symbol
    syms = [short_sym, long_sym]

    pre = client.option_quotes_latest(syms)
    net = _net(pre, short_sym, long_sym, closing)
    if net is None:
        return FillRecord(ok=False, error="no two-sided quote on one or both legs at submission")

    if closing:
        price = net.touch + cross if cross else net.mid
    else:
        price = -(net.touch - cross) if cross else -net.mid

    submitted_at = datetime.datetime.now(datetime.UTC).isoformat()
    order = client.submit_mleg(build_legs(candidate, closing), contracts, price)
    post = client.option_quotes_latest(syms)  # bounds quote drift across the submit window

    oid = order.id
    state = order
    deadline = time.time() + poll_seconds
    while oid and not state.settled:
        if time.time() > deadline:
            break
        state = client.get_order(oid)

    filled = state.status == "filled"
    fill = state.filled_avg_price
    rec = FillRecord(
        ok=True,
        filled=filled,
        order_id=oid,
        status=state.status,
        underlying=candidate.underlying,
        structure=candidate.structure,
        expiry=candidate.expiry,
        contracts=contracts,
        closing=closing,
        limit=price,
        submitted_at=submitted_at,
        filled_at=state.filled_at,
        fill=fill,
        nbbo_pre=net,
        nbbo_post=_net(post, short_sym, long_sym, closing),
        legs=state.legs,
        vs_mid=None if fill is None else round((abs(fill) - net.mid) * (-1 if closing else 1), 4),
        vs_touch=(
            None if fill is None else round((abs(fill) - net.touch) * (-1 if closing else 1), 4)
        ),
    )

    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
        p = os.path.join(log_dir, f"fills_{datetime.date.today().isoformat()}.jsonl")
        with open(p, "a") as fh:
            fh.write(rec.model_dump_json() + "\n")
    return rec


def cancel_if_resting(client, rec: FillRecord):
    if rec.order_id and not rec.filled:
        return client.cancel_order(rec.order_id)
    return False
