"""Multi-leg order placement, with the NBBO captured at submission.

Two things measured on 2026-08-26 shape this:

- Fills clear **better than the touch but not reliably at mid**, and the improvement is a small
  absolute amount that does not scale with spread width. On a 3-cent book a mid limit filled better
  than mid in 127 ms; on a 14-66 cent book a mid limit rested 26 seconds and never filled.
- The NBBO at submission is **unreconstructable** — there is no historical options quote endpoint.
  Capture it in the same breath as the order or the fill is uninterpretable forever.
"""
import datetime, json, os, time
from ..data.alpaca import leg


def build_legs(candidate, closing=False):
    short_sym, long_sym = candidate["short"]["symbol"], candidate["long"]["symbol"]
    if not closing:
        return [leg(short_sym, "sell", "sell_to_open"), leg(long_sym, "buy", "buy_to_open")]
    return [leg(short_sym, "buy", "buy_to_close"), leg(long_sym, "sell", "sell_to_close")]


def _net(quotes, short_sym, long_sym, closing):
    s, l = quotes.get(short_sym), quotes.get(long_sym)
    if not s or not l:
        return None
    smid, lmid = (s["bp"] + s["ap"]) / 2, (l["bp"] + l["ap"]) / 2
    mid = smid - lmid
    touch = (s["ap"] - l["bp"]) if closing else (s["bp"] - l["ap"])
    return dict(mid=round(mid, 4), touch=round(touch, 4),
                short=dict(bid=s["bp"], ask=s["ap"]), long=dict(bid=l["bp"], ask=l["ap"]))


def place(client, candidate, contracts, closing=False, cross=0.0, poll_seconds=30, log_dir=None):
    """Submit at mid (or `cross` through the touch), capture NBBO either side, return the record.

    `limit_price` is a NET price: positive is a debit, negative a credit. Opening a credit spread
    submits a negative limit; closing it submits a positive one.
    """
    short_sym, long_sym = candidate["short"]["symbol"], candidate["long"]["symbol"]
    syms = [short_sym, long_sym]

    pre = client.option_quotes_latest(syms)
    net = _net(pre, short_sym, long_sym, closing)
    if net is None:
        return dict(ok=False, error="no two-sided quote on one or both legs at submission")

    if closing:
        price = net["touch"] + cross if cross else net["mid"]
    else:
        price = -(net["touch"] - cross) if cross else -net["mid"]

    submitted_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    order = client.submit_mleg(build_legs(candidate, closing), contracts, price)
    post = client.option_quotes_latest(syms)          # bounds quote drift across the submit window

    oid = order.get("id")
    state = order
    deadline = time.time() + poll_seconds
    while oid and state.get("status") not in ("filled", "canceled", "rejected", "expired"):
        if time.time() > deadline:
            break
        state = client.get_order(oid)

    filled = state.get("status") == "filled"
    rec = dict(ok=True, filled=filled, order_id=oid, status=state.get("status"),
               underlying=candidate["underlying"], structure=candidate["structure"],
               expiry=candidate["expiry"], contracts=contracts, closing=closing,
               limit=price, submitted_at=submitted_at, filled_at=state.get("filled_at"),
               fill=float(state["filled_avg_price"]) if state.get("filled_avg_price") else None,
               nbbo_pre=net, nbbo_post=_net(post, short_sym, long_sym, closing),
               legs=[{k: lg.get(k) for k in ("symbol", "side", "status", "filled_avg_price")}
                     for lg in (state.get("legs") or [])])
    if rec["fill"] is not None:
        rec["vs_mid"] = round((abs(rec["fill"]) - net["mid"]) * (1 if not closing else -1), 4)
        rec["vs_touch"] = round((abs(rec["fill"]) - net["touch"]) * (1 if not closing else -1), 4)

    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
        p = os.path.join(log_dir, f"fills_{datetime.date.today().isoformat()}.jsonl")
        with open(p, "a") as fh:
            fh.write(json.dumps(rec) + "\n")
    return rec


def cancel_if_resting(client, rec):
    if rec.get("order_id") and not rec.get("filled"):
        return client.cancel_order(rec["order_id"])
    return False
