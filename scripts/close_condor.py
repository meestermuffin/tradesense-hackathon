#!/usr/bin/env python3
"""Close one condor. Prints the order and refuses to send it without an explicit confirm.

Issue #33. The entry path has had a sign invariant on the type since it was written; this is its
counterpart. Opening a condor takes a credit and its net limit is negative. Closing pays a debit
and its net limit is positive. Inverting it raises nothing at the API -- it places a real order at
a price nobody intended -- so `CondorClose` refuses to construct with the wrong sign and this
script cannot send an order it could not build.

Dry by default. `--confirm i-mean-it` sends. The account assertion runs before anything else,
because trading the wrong book is the one error here that produces no signal at all.

    uv run python scripts/close_condor.py --expiry 2026-09-03 --legs 772C,777C
    uv run python scripts/close_condor.py --expiry 2026-09-03 --legs 772C,777C --confirm i-mean-it
"""

import argparse
import datetime
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "markwatch"))

from src.agent.adapter import MarkwatchBridge  # noqa: E402
from src.data.alpaca import AlpacaClient  # noqa: E402
from src.options.close import (  # noqa: E402
    CondorClose,
    build_close_legs,
    price_close,
)

CROSS = 0.05
"""How far past the touch to reach. Marketable, not a market order -- mleg market orders have
never been verified on this account and an expiry afternoon is the wrong time to find out."""


def legs_for(positions, expiry: datetime.date, want: list[str]) -> list[tuple[str, int]]:
    """The named legs, taken verbatim from the book. No inference.

    `want` is every strike to close, e.g. `["772C", "777C"]`. The caller names all of them, and
    that is deliberate: on 3 September the book held tranche 2 at 772/777C and tranche 3 at
    768/773C, same expiry. Asked to close 772C, a nearest-long heuristic picked 773 -- the other
    structure's wing -- which would have closed a spread nobody opened and left 768 short against
    777, a nine-wide with a different max loss. It got one strike from a live order.

    Proximity cannot identify a structure in a book holding two at one expiry, and the broker does
    not record which ticket a leg arrived on. So nothing is inferred here.
    """
    tag = f"{expiry:%y%m%d}"
    same = {}
    for p in positions:
        if p.symbol[3:9] != tag or int(p.qty) == 0:
            continue
        same[f"{int(p.symbol[10:]) // 1000}{p.symbol[9]}"] = (p.symbol, int(p.qty))
    if not same:
        raise ValueError(f"no open legs expiring {expiry}")

    out = []
    for w in want:
        k = w.strip().upper()
        if k not in same:
            raise ValueError(f"{k} is not held at {expiry}. Book has {sorted(same)}")
        out.append(same[k])

    longs = sum(1 for _, q in out if q > 0)
    shorts = len(out) - longs
    if longs != shorts:
        raise ValueError(
            f"unbalanced: {shorts} short and {longs} long. Closing one side of a vertical leaves "
            f"a naked position, which is not a close."
        )
    sizes = {abs(q) for _, q in out}
    if len(sizes) != 1:
        raise ValueError(f"legs are not the same size: {sizes}. Refusing to guess the ratio.")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--expiry", required=True, help="YYYY-MM-DD")
    ap.add_argument(
        "--legs",
        required=True,
        help="EVERY strike to close, comma-separated, e.g. 772C,777C. Nothing is inferred.",
    )
    ap.add_argument("--expect-account", default=None)
    ap.add_argument("--cross", type=float, default=CROSS)
    ap.add_argument("--confirm", default=None, help="'i-mean-it' to actually send")
    ap.add_argument("--rationale", default="pin risk: short in the money, wing not")
    a = ap.parse_args(argv)

    expiry = datetime.date.fromisoformat(a.expiry)
    client = AlpacaClient()
    acct = client.account()
    if a.expect_account and acct.account_number != a.expect_account:
        print(
            f"  REFUSED: credentials resolve to {acct.account_number}, expected {a.expect_account}"
        )
        return 2
    print(f"  account {acct.account_number}   equity ${acct.equity:,.2f}")

    held = legs_for(client.positions(), expiry, a.legs.split(","))
    bridge = MarkwatchBridge(client)
    raw = bridge.get_quotes([s for s, _ in held])
    quotes = {k: {"bid": v.get("bid"), "ask": v.get("ask")} for k, v in raw.items()}

    mid, touch = price_close(held, quotes)
    contracts = abs(held[0][1])
    limit = round(touch + a.cross, 2)

    order = CondorClose(
        underlying="SPY",
        expiry=expiry,
        contracts=contracts,
        limit_price=limit,
        debit_at_touch=touch,
        rationale=a.rationale,
    )
    legs = build_close_legs(held)

    print(f"\n  CLOSING {contracts}x SPY {expiry}")
    for (sym, qty), leg in zip(held, legs, strict=True):
        q = quotes[sym]
        print(
            f"    {sym} {qty:>+4}  bid {q['bid']:>5.2f} ask {q['ask']:>5.2f}  "
            f"-> {leg['side']:<4} {leg['position_intent']}"
        )
    print(f"\n    net at mid    {mid:+.3f}")
    print(f"    net at touch  {touch:+.3f}")
    print(f"    LIMIT         {order.limit_price:+.2f}   POSITIVE = a debit, we pay")
    print(f"    cost          ${order.cost:,.0f}")

    if a.confirm != "i-mean-it":
        print("\n  DRY RUN — nothing sent. Add --confirm i-mean-it to place this.")
        return 0

    resp = client.submit_mleg(legs, order.contracts, order.limit_price)
    print(f"\n  sent: {resp.id}  status={resp.status}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
