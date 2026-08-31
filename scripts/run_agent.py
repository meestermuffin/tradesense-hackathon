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
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "markwatch")
)

from markwatch.hooks import Recorder  # noqa: E402
from markwatch.journal import Journal  # noqa: E402

from src.agent.adapter import MarkwatchBridge  # noqa: E402
from src.agent.collector import CollectorHandle  # noqa: E402
from src.agent.loop import AgentLoop, tranches_for  # noqa: E402
from src.agent.model import review  # noqa: E402
from src.agent.window import parse, within  # noqa: E402
from src.data.alpaca import AlpacaClient  # noqa: E402
from src.options.chain import chain_quotes  # noqa: E402
from src.options.condor import submit  # noqa: E402

sys.path.insert(0, os.path.join(REPO, "scripts"))
from fill_probe import gate as probe_gate  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="actually place orders")
    ap.add_argument("--session", default=None, help="YYYY-MM-DD, defaults to today")
    ap.add_argument("--expect-account", default=None)
    ap.add_argument(
        "--collector-running",
        action="store_true",
        help="markwatch is already capturing elsewhere; do not start one here",
    )
    ap.add_argument("--journal", default="journal.db", help="markwatch SQLite path")
    ap.add_argument("--collector-interval", type=float, default=60.0)
    ap.add_argument(
        "--no-review",
        action="store_true",
        help="skip the model review; the deterministic path only",
    )
    ap.add_argument(
        "--fill-vs-mid",
        type=float,
        default=None,
        help="Monday's realized fill against mid, for the Tuesday gate",
    )
    ap.add_argument(
        "--live-iv",
        type=float,
        default=None,
        help="override the Tuesday gate's IV; measured from the chain by default",
    )
    ap.add_argument("--high-water", type=float, default=100_000.0)
    ap.add_argument(
        "--at",
        default=None,
        help="HH:MM this run was scheduled for. Refuses if the wake arrived outside the window "
        "-- launchd runs missed jobs on wake, and a late entry is a different trade.",
    )
    ap.add_argument(
        "--skip-probe-gate",
        action="store_true",
        help="place without a probe verdict. Deliberate override; the reason is printed.",
    )
    a = ap.parse_args()

    session = datetime.date.fromisoformat(a.session) if a.session else datetime.date.today()
    if a.at:
        ok, why = within(parse(a.at))
        if not ok:
            print(f"  REFUSED: {why}")
            return 3
        print(f"  window  {why}")
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

    # The registered 09:45 probe decides condors vs paired verticals for the whole book, so sizing
    # into an unread or failed probe is placing the order the probe existed to prevent. Fails
    # closed: a missing verdict refuses, because a probe that crashed is indistinguishable from one
    # that never ran. --skip-probe-gate is the deliberate human override.
    if a.live:
        ok, why = probe_gate(session)
        if a.skip_probe_gate:
            print(f"  probe   OVERRIDDEN — {why}")
        elif not ok:
            print(f"  REFUSED: {why}")
            return 2
        else:
            print(f"  probe   {why}")

    # markwatch first, always. Quotes do not exist after the fact on this account, so the
    # collector has to be capturing before an order can exist -- otherwise the fill can never be
    # reconciled against the NBBO it crossed, and nothing downstream can tell that it happened.
    collector = None
    running = a.collector_running
    if a.live and not a.collector_running:
        collector = CollectorHandle(
            key=client.key,
            secret=client.secret,
            db=a.journal,
            interval=a.collector_interval,
        ).start(
            log=os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs", "markwatch.log"
            )
        )
        time.sleep(3)  # let it take its first sample before anything is placed
        collector.require_running()
        running = True
        print(f"  markwatch started -> {collector.db}")

    # The journal is Solo's, and it captures the NBBO on all four legs at submission. That cannot
    # be recovered afterwards on this account, so it has to exist before the order does.
    journal = Journal(os.path.join(REPO, a.journal))
    journal.connect()
    recorder = Recorder(journal, get_quotes=bridge.get_quotes)

    reviewer = None if a.no_review else review
    loop = AgentLoop(
        client=client,
        dry_run=not a.live,
        expected_account=a.expect_account,
        collector_running=running,
        reviewer=reviewer,
    )
    print(f"  review  {'OFF — deterministic only' if a.no_review else 'model in the loop'}")

    spot = client.stock_closes_latest(["SPY"])["SPY"]
    print(f"  SPY     {spot:.2f}")

    placed = 0
    planned = 0
    for spec in specs:
        quotes, _raw, iv = chain_quotes(client, bridge, "SPY", spec.expiry, spot)
        if iv is None:
            print(f"  {spec.expiry}  SKIPPED — no ATM quote inverts; refusing to guess a vol")
            continue
        # The gate reads a measured IV unless overridden. A hand-passed number is a way to open
        # the gate on a stale figure without noticing.
        gate_iv = a.live_iv if a.live_iv is not None else iv
        decisions = loop.tick(
            session,
            high_water=a.high_water,
            fill_vs_mid=a.fill_vs_mid,
            live_iv=gate_iv,
            quotes=quotes,
            spot=spot,
            iv=iv,
            only=spec,
        )
        d = next((x for x in decisions if x.spec.expiry == spec.expiry), None)
        if d is None:
            continue
        head = f"  {spec.expiry} ({spec.dte} DTE, IV {iv:.4f})"
        if d.skipped:
            print(f"{head}  SKIPPED — {d.reason}")
            # Journal the refusal. A trade not taken, with a written reason, is the most
            # interesting trace this system produces and it leaves no other record.
            recorder.note(
                "tranche_skipped",
                {"expiry": spec.expiry.isoformat(), "dte": spec.dte, "iv": iv},
                note=d.reason,
            )
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
            rec = submit(client, p, vetoes=[], recorder=recorder)
            print(f"      -> {rec.status} fill={rec.fill} vs_mid={rec.vs_mid}")
            placed += 1 if rec.filled else 0

    # Counts what was actually planned, not what was scheduled. A skipped or refused tranche
    # reported as "would place" is the kind of line someone reads at 09:45 and believes.
    n = placed if a.live else planned
    print(f"\n  {'placed' if a.live else 'would place'} {n} of {len(specs)} scheduled")
    if collector is not None:
        # Left running deliberately: the mark question needs samples across the whole window,
        # not just the moment of entry.
        print(f"  markwatch still capturing (pid {collector.proc.pid}) -> {collector.db}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
