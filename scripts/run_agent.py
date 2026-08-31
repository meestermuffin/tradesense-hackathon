#!/usr/bin/env python3
"""The trading agent. One wake, one session's decisions.

**Dry run is the default.** Placing orders requires --live, explicitly, and --live additionally
refuses unless markwatch is capturing: quotes do not exist after the fact on this account, so a
fill placed before the collector starts can never be reconciled against the NBBO it crossed.

Order of operations, and why:

  1. start markwatch          before anything, for the reason above
  2. reconcile from broker    local state is a cache and never truth
  3. assert the account       the wrong book is the only silent error here
  4. build and validate       the model emits a template; it never names a price
  5. submit, or explain       a refusal is a result, journalled with the rule that fired

    uv run python scripts/run_agent.py                      # dry run, today's session
    uv run python scripts/run_agent.py --session 2026-08-31 # a specific session
    uv run python scripts/run_agent.py --live --expect-account PA3BUA9MX72C
"""

import argparse
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "markwatch")
)

from src.agent.adapter import MarkwatchBridge  # noqa: E402
from src.agent.loop import AgentLoop, tranches_for  # noqa: E402
from src.data.alpaca import AlpacaClient  # noqa: E402
from src.options.condor import submit  # noqa: E402


def chain_quotes(client, bridge, underlying, expiry, spot, span=40):
    """Quotes keyed by strike, in the shape `build_plan` reads: {strike: (put, call)}."""
    from src.models import Quote

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
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="actually place orders")
    ap.add_argument("--session", default=None, help="YYYY-MM-DD, defaults to today")
    ap.add_argument("--expect-account", default=None)
    ap.add_argument(
        "--collector-running", action="store_true", help="assert markwatch is already capturing"
    )
    ap.add_argument(
        "--fill-vs-mid",
        type=float,
        default=None,
        help="Monday's realized fill against mid, for the Tuesday gate",
    )
    ap.add_argument("--live-iv", type=float, default=None, help="live IV for the Tuesday gate")
    ap.add_argument("--high-water", type=float, default=100_000.0)
    a = ap.parse_args()

    session = datetime.date.fromisoformat(a.session) if a.session else datetime.date.today()
    specs = tranches_for(session)
    print(f"  session {session:%Y-%m-%d %A}   tranches scheduled: {len(specs)}")
    if not specs:
        print("  nothing scheduled. Monitoring only.")
        return 0

    client = AlpacaClient()
    bridge = MarkwatchBridge(client)
    acct = client.account()
    print(f"  account {acct.account_number}   equity ${acct.equity:,.2f}")
    print(f"  mode    {'LIVE — orders will be placed' if a.live else 'DRY RUN — no orders'}")

    loop = AgentLoop(
        client=client,
        dry_run=not a.live,
        expected_account=a.expect_account,
        collector_running=a.collector_running,
    )

    spot = client.stock_closes_latest(["SPY"])["SPY"]
    print(f"  SPY     {spot:.2f}")

    placed = 0
    planned = 0
    for spec in specs:
        quotes = chain_quotes(client, bridge, "SPY", spec.expiry, spot)
        decisions = loop.tick(
            session,
            high_water=a.high_water,
            fill_vs_mid=a.fill_vs_mid,
            live_iv=a.live_iv,
            quotes=quotes,
            spot=spot,
        )
        d = next((x for x in decisions if x.spec.expiry == spec.expiry), None)
        if d is None:
            continue
        head = f"  {spec.expiry} ({spec.dte} DTE)"
        if d.skipped:
            print(f"{head}  SKIPPED — {d.reason}")
            continue
        if d.vetoes:
            print(f"{head}  REFUSED")
            for v in d.vetoes:
                print(f"      {v}")
            continue
        p = d.plan
        print(
            f"{head}  {p.long_put:g}/{p.short_put:g}P {p.short_call:g}/{p.long_call:g}C  "
            f"credit {p.credit:.2f} ({p.credit_pct_of_width:.0%} of width)  "
            f"{p.contracts}x  risk ${p.defined_risk:,.0f}"
        )
        print(
            f"      deltas {p.short_put_delta:.3f}/{p.short_call_delta:.3f}   "
            f"net limit {p.limit_price:+.2f}   touch {p.credit_at_touch:.2f}"
        )
        planned += 1
        if a.live:
            rec = submit(client, p, vetoes=[])
            print(f"      -> {rec.status} fill={rec.fill} vs_mid={rec.vs_mid}")
            placed += 1 if rec.filled else 0

    # Counts what was actually planned, not what was scheduled. A skipped or refused tranche
    # reported as "would place" is the kind of line someone reads at 09:45 and believes.
    n = placed if a.live else planned
    print(f"\n  {'placed' if a.live else 'would place'} {n} of {len(specs)} scheduled")
    return 0


if __name__ == "__main__":
    sys.exit(main())
