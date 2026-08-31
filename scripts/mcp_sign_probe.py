#!/usr/bin/env python3
"""Does the net-price sign convention survive the MCP surface?

**Blocking before any real order.** `limit_price` on a multi-leg order is a NET price where
negative means a credit. Inverting it does not raise -- it places a real order at the wrong price,
and this project has that recorded as the worst failure mode the API offers.

It is verified against the SDK and pinned in `tests/`. It has **never been verified through MCP**.
V2 of `alpaca-mcp-server` renamed tools and changed parameters, so the MCP schema is a separate
surface and SDK verification does not carry across. The schema *documents* the convention:

    limit_price: "Required for limit orders. For multi-leg, this is the net debit/credit
                  (positive = debit/cost, negative = credit/proceeds)."

Documented is not measured. This measures it.

Safety: the limit is -50.00 net on a five-wide condor, which demands fifty dollars of credit for a
structure worth about one. It cannot fill. The order is cancelled immediately regardless.

    uv run python scripts/mcp_sign_probe.py [--underlying SPY] [--expiry YYYY-MM-DD]
"""

import argparse
import datetime
import itertools
import json
import os
import queue
import subprocess
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.data.alpaca import AlpacaClient  # noqa: E402
from src.options.condor import _occ  # noqa: E402

UNFILLABLE_NET = -50.00


class Mcp:
    """Minimal MCP client over stdio. The agent will use a real one; this needs only three calls."""

    def __init__(self, env):
        self.p = subprocess.Popen(
            ["uvx", "--from", "alpaca-mcp-server", "alpaca-mcp-server", "--transport", "stdio"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
            env=env,
        )
        self.q: queue.Queue = queue.Queue()
        threading.Thread(target=lambda: [self.q.put(x) for x in self.p.stdout], daemon=True).start()
        self.ids = itertools.count(1)
        self.call(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "sign-probe", "version": "1"},
            },
        )
        self.call("notifications/initialized", {}, notify=True)

    def call(self, method, params=None, notify=False, timeout=120):
        msg = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        if not notify:
            msg["id"] = next(self.ids)
        self.p.stdin.write(json.dumps(msg) + "\n")
        self.p.stdin.flush()
        if notify:
            return None
        while True:
            line = self.q.get(timeout=timeout).strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "id" in d:
                return d

    def tool(self, name, args):
        r = self.call("tools/call", {"name": name, "arguments": args})
        content = (r.get("result") or {}).get("content") or []
        text = "\n".join(c.get("text", "") for c in content if c.get("type") == "text")
        return r, text

    def close(self):
        self.p.terminate()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--underlying", default="SPY")
    ap.add_argument("--expiry", default=None, help="YYYY-MM-DD; default is the nearest 2+ DTE")
    a = ap.parse_args()

    client = AlpacaClient()
    acct = client.account()
    print(f"  account {acct.account_number}   options level {acct.options_approved_level}")

    today = datetime.date.today()
    cs = client.option_contracts(
        a.underlying,
        exp_gte=(today + datetime.timedelta(days=2)).isoformat(),
        exp_lte=(today + datetime.timedelta(days=12)).isoformat(),
        status="active",
        limit=10000,
    )
    expiry = (
        datetime.date.fromisoformat(a.expiry)
        if a.expiry
        else sorted({c.expiration_date for c in cs})[0]
    )
    spot = client.stock_closes_latest([a.underlying])[a.underlying]
    listed = {c.strike_price for c in cs if c.expiration_date == expiry}
    if not listed:
        print(f"  no contracts for {expiry}")
        return 1

    def near(target):
        return min(listed, key=lambda k: abs(k - target))

    sp, sc = near(spot * 0.985), near(spot * 1.015)
    lp, lc = near(sp - 5), near(sc + 5)
    print(f"  {a.underlying} {spot:.2f}  expiry {expiry}")
    print(f"  condor {lp:g}/{sp:g}P  {sc:g}/{lc:g}C")

    class P:
        underlying, expiry_ = a.underlying, expiry

    P.expiry = expiry
    legs = [
        {
            "symbol": _occ(P, lp, "P"),
            "ratio_qty": "1",
            "side": "buy",
            "position_intent": "buy_to_open",
        },
        {
            "symbol": _occ(P, sp, "P"),
            "ratio_qty": "1",
            "side": "sell",
            "position_intent": "sell_to_open",
        },
        {
            "symbol": _occ(P, sc, "C"),
            "ratio_qty": "1",
            "side": "sell",
            "position_intent": "sell_to_open",
        },
        {
            "symbol": _occ(P, lc, "C"),
            "ratio_qty": "1",
            "side": "buy",
            "position_intent": "buy_to_open",
        },
    ]

    env = dict(os.environ)
    env["ALPACA_API_KEY"] = client.key
    env["ALPACA_SECRET_KEY"] = client.secret
    env["ALPACA_PAPER_TRADE"] = "True"

    m = Mcp(env)
    try:
        print(f"\n  submitting through MCP at an unfillable net of {UNFILLABLE_NET:+.2f} ...")
        _, text = m.tool(
            "place_option_order",
            {
                "legs": legs,
                # qty is a STRING on the MCP surface. An int fails pydantic validation
                # before the order is built -- caught by this probe, 2026-08-31.
                "qty": "1",
                "type": "limit",
                "limit_price": str(UNFILLABLE_NET),
                "time_in_force": "day",
                "order_class": "mleg",
            },
        )
        print("  response:")
        for line in text.splitlines()[:14]:
            print(f"    {line}")

        low = text.lower()
        order_id = None
        for tok in text.replace(",", " ").replace('"', " ").split():
            if tok.count("-") == 4 and len(tok) >= 32:
                order_id = tok
                break

        signed = "-50" in text or "−50" in text
        four = text.count("SPY") >= 4 or "4" in low
        print(f"\n  negative net echoed back : {'YES' if signed else 'NOT FOUND IN RESPONSE'}")
        print(f"  four legs acknowledged   : {'YES' if four else 'UNCLEAR'}")

        if order_id:
            print(f"  order {order_id} -> cancelling")
            m.tool("cancel_order_by_id", {"order_id": order_id})
            print(f"  cancelled: {client.cancel_order(order_id)}")
        else:
            print("  no order id parsed -- check open orders by hand before trading")

        print(
            "\n  VERDICT:",
            "sign convention holds through MCP"
            if signed
            else "INCONCLUSIVE -- do not route orders through MCP until settled",
        )
        return 0 if signed else 2
    finally:
        m.close()


if __name__ == "__main__":
    sys.exit(main())
