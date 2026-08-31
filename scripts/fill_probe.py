#!/usr/bin/env python3
"""The registered 4-leg fill probe. One condor, one contract, one resting limit.

Registered in `docs/pending/condor-fill-realism.md`, which is committed and is the definition of
what this measures and what each outcome means. **Read it before changing anything here.** The
decision table below is transcribed from it and must not diverge; if the two disagree, the
registration wins and this file is wrong.

The question is narrow: do four legs clear at a single mid limit on a tight book, or do they not?
That is the only thing the sizing decision turns on. It is n = 1 -- one order, one underlying, one
session -- and it cannot establish a fill *rate*. Nothing here may later be quoted as one.

Writes a verdict to `data/probe/<session>-verdict.json`. `run_agent.py --live` reads it and
refuses to size into a STOP, so this file is a gate and not just a record.

    uv run python scripts/fill_probe.py --expect-account PA3BUA9MX72C          # dry, places nothing
    uv run python scripts/fill_probe.py --live --expect-account PA3BUA9MX72C   # the real probe
"""

import argparse
import datetime
import json
import os
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "markwatch"))

from markwatch.hooks import Recorder  # noqa: E402
from markwatch.journal import Journal  # noqa: E402

from src.agent.adapter import MarkwatchBridge  # noqa: E402
from src.agent.collector import CollectorHandle  # noqa: E402
from src.agent.window import parse, within  # noqa: E402
from src.data.alpaca import AlpacaClient  # noqa: E402
from src.options.chain import chain_quotes  # noqa: E402
from src.options.condor import CondorPlan, CondorRequest, build_plan, submit  # noqa: E402

# Transcribed from the registration's decision table. Verbatim, deliberately.
CONDORS = "CONDORS"
CONDORS_WALKED = "CONDORS_WALKED"
PAIRED_VERTICALS = "PAIRED_VERTICALS"
STOP = "STOP"

FILL_FLOOR = -0.05  # "at >= mid - 0.05"
POLL_SECONDS = 20.0  # "does not fill in 20 s"

PROBE_DIR = os.path.join(REPO, "data", "probe")


def verdict_for(rec) -> tuple[str, str]:
    """Classify one probe result. Returns (verdict, the sentence that justifies it).

    The registration's table, in its own order. `vs_mid` is positive for price improvement, so the
    floor is a lower bound on a signed quantity, not a magnitude.
    """
    if rec is None or not rec.ok:
        return STOP, "the probe did not reach the broker"
    status = (rec.status or "").lower()
    if status in ("rejected", "canceled_by_broker") or (not rec.filled and status == "rejected"):
        return STOP, f"broker rejected the order (status {rec.status}) -- a platform problem"
    if rec.filled:
        vs = rec.vs_mid
        if vs is None:
            return (
                CONDORS_WALKED,
                "filled, but no mid to compare against; treat the credit as achieved",
            )
        if vs >= FILL_FLOOR:
            return (
                CONDORS,
                f"filled within {POLL_SECONDS:.0f}s at vs_mid {vs:+.3f}, "
                f"at or above mid{FILL_FLOOR:+.2f}",
            )
        return (
            CONDORS_WALKED,
            f"filled within {POLL_SECONDS:.0f}s but at vs_mid {vs:+.3f}, "
            f"below mid{FILL_FLOOR:+.2f}",
        )
    return (
        PAIRED_VERTICALS,
        f"did not fill in {POLL_SECONDS:.0f}s (status {rec.status}); fall back to two 2-leg orders",
    )


CONSEQUENCE = {
    CONDORS: "run 4-leg as designed; record vs_mid as the cost estimate",
    CONDORS_WALKED: (
        "4-leg is viable but not at mid; limit-walk and re-price the ceiling on the achieved credit"
    ),
    PAIRED_VERTICALS: "submit two 2-leg orders together; same strikes, same risk, two tickets",
    STOP: "do not size into it",
}


def verdict_path(session: datetime.date) -> str:
    return os.path.join(PROBE_DIR, f"{session:%Y-%m-%d}-verdict.json")


def read_verdict(session: datetime.date) -> dict | None:
    """What `run_agent.py --live` calls. Absent is not the same as passing."""
    try:
        with open(verdict_path(session)) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--live", action="store_true", help="actually place the probe order")
    ap.add_argument("--session", default=None, help="YYYY-MM-DD, defaults to today")
    ap.add_argument("--expect-account", default=None)
    ap.add_argument("--expiry", default=None, help="YYYY-MM-DD; defaults to the registered Sep 2")
    ap.add_argument("--journal", default="journal.db")
    ap.add_argument("--collector-running", action="store_true")
    ap.add_argument(
        "--at",
        default=None,
        help="HH:MM this run was scheduled for. Refuses if the wake arrived outside the window "
        "-- launchd runs missed jobs on wake, and a late entry is a different trade.",
    )
    a = ap.parse_args()

    session = datetime.date.fromisoformat(a.session) if a.session else datetime.date.today()
    if a.at:
        ok, why = within(parse(a.at))
        if not ok:
            print(f"  REFUSED: {why}")
            return 3
        print(f"  window  {why}")
    expiry = datetime.date.fromisoformat(a.expiry) if a.expiry else datetime.date(2026, 9, 2)
    print("  registered 4-leg fill probe -- docs/pending/condor-fill-realism.md")
    print(f"  session {session:%Y-%m-%d %A}   expiry {expiry}   n = 1")

    client = AlpacaClient()
    bridge = MarkwatchBridge(client)
    acct = client.account()
    print(f"  account {acct.account_number}   equity ${acct.equity:,.2f}")

    # The wrong book is the only error here that produces no signal at all, so it is checked before
    # anything else can fail for a more interesting reason and mask it.
    if a.expect_account and acct.account_number != a.expect_account:
        print(
            f"  REFUSED: credentials resolve to {acct.account_number}, expected {a.expect_account}"
        )
        return 2

    print(f"  mode    {'LIVE — one real order' if a.live else 'DRY RUN — places nothing'}")

    collector = None
    if a.live and not a.collector_running:
        # The NBBO on all four legs at submission is the measurement. It cannot be reconstructed
        # afterwards on this account, so the collector has to be up before the order exists.
        collector = CollectorHandle(
            key=client.key, secret=client.secret, db=a.journal, interval=60.0
        ).start(log=os.path.join(REPO, "logs", "markwatch.log"))
        time.sleep(3)
        collector.require_running()
        print(f"  markwatch started -> {collector.db}")

    spot = client.stock_closes_latest(["SPY"])["SPY"]
    quotes, _raw, iv = chain_quotes(client, bridge, "SPY", expiry, spot)
    if iv is None:
        print("  REFUSED: no ATM quote inverts; refusing to guess a vol")
        return 2
    print(f"  SPY     {spot:.2f}   IV {iv:.4f}")

    req = CondorRequest(
        underlying="SPY",
        expiry=expiry,
        short_delta=0.20,
        wing_width=5.0,
        contracts=1,  # registered: ONE contract. Not a sizing decision.
        rationale="registered fill probe, n=1",
    )
    plan = build_plan(req, spot, iv, quotes, as_of=session)
    if not isinstance(plan, CondorPlan):
        print(f"  REFUSED: {plan}")
        return 2

    print(
        f"  {plan.long_put:g}/{plan.short_put:g}P {plan.short_call:g}/{plan.long_call:g}C  "
        f"credit {plan.credit:.2f}  deltas {plan.short_put_delta:.3f}/{plan.short_call_delta:.3f}  "
        f"net limit {plan.limit_price:+.2f}"
    )

    if not a.live:
        print("\n  DRY RUN — no order placed, no verdict written.")
        return 0

    journal = Journal(os.path.join(REPO, a.journal))
    journal.connect()
    recorder = Recorder(journal, get_quotes=bridge.get_quotes)

    started = time.time()
    # cancel_unfilled: the registration says cancelled at 20s, not walked. A walked probe measures
    # the walk rather than the fill, and a probe left resting can fill later into the sized book.
    rec = submit(
        client, plan, vetoes=[], recorder=recorder, poll_seconds=POLL_SECONDS, cancel_unfilled=True
    )
    elapsed = time.time() - started

    v, why = verdict_for(rec)
    out = {
        "session": session.isoformat(),
        "expiry": expiry.isoformat(),
        "verdict": v,
        "why": why,
        "consequence": CONSEQUENCE[v],
        "registration": "docs/pending/condor-fill-realism.md",
        "n": 1,
        "seconds_to_settle": round(elapsed, 2),
        "status": rec.status,
        "filled": rec.filled,
        "fill": rec.fill,
        "vs_mid": rec.vs_mid,
        "credit_at_mid": rec.credit_at_mid,
        "limit_price": rec.limit_price,
        "order_id": rec.order_id,
        "legs": [x.model_dump() for x in rec.legs],
        "spot": spot,
        "iv": iv,
        "written_at": datetime.datetime.now(datetime.UTC).isoformat(),
    }
    os.makedirs(PROBE_DIR, exist_ok=True)
    with open(verdict_path(session), "w") as f:
        json.dump(out, f, indent=2, sort_keys=True)

    print(f"\n  status {rec.status}  fill {rec.fill}  vs_mid {rec.vs_mid}  in {elapsed:.1f}s")
    print(f"  VERDICT  {v}")
    print(f"           {why}")
    print(f"           -> {CONSEQUENCE[v]}")
    print(f"  written  {os.path.relpath(verdict_path(session), REPO)}")

    recorder.note("fill_probe", {"expiry": expiry.isoformat(), "n": 1}, note=f"{v}: {why}")
    if collector is not None:
        print(f"  markwatch still capturing (pid {collector.proc.pid})")
    return 0


if __name__ == "__main__":
    sys.exit(main())


# ---- the gate `run_agent.py --live` applies


PROCEED = (CONDORS, CONDORS_WALKED)


def gate(session: datetime.date) -> tuple[bool, str]:
    """May the sized tranches go? Returns (ok, the reason either way).

    Fails closed on every path. A missing verdict file is a refusal, not a pass -- the probe not
    having run is exactly the state this gate exists to catch, and it is indistinguishable from a
    probe that crashed. Absence is never permission.

    PAIRED_VERTICALS also refuses, for a different reason: the fallback it calls for is not built.
    Placing condors after condors failed to fill would contradict the registration while claiming
    to follow it, so the honest behaviour is to stop and put the decision in front of a person.
    """
    v = read_verdict(session)
    if v is None:
        return False, (
            f"no probe verdict for {session}. The 09:45 probe has not run, or it crashed. "
            f"Run scripts/fill_probe.py --live, or pass --skip-probe-gate to place without it."
        )
    verdict = v.get("verdict")
    if verdict in PROCEED:
        return True, f"probe verdict {verdict}: {v.get('why', '')}"
    if verdict == PAIRED_VERTICALS:
        return False, (
            "probe verdict PAIRED_VERTICALS: four legs did not clear at one limit. The registered "
            "fallback is two 2-leg orders, which is not implemented -- this needs a person."
        )
    return False, f"probe verdict {verdict}: {v.get('why', '')}. {CONSEQUENCE.get(verdict, '')}"
