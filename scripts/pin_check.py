#!/usr/bin/env python3
"""Pin-risk check for open condors on an expiry day. Reports; never closes.

Issue #13. On an expiry day, spot sitting between a short strike and its wing means the short is
in the money and the long is not — the leg gets assigned and the wing does not offset it. Spot
past the wing is fully defined and is the loss we already priced. The dangerous zone is the gap
between them.

**This does not close anything, deliberately.** Two things make an automated close worse than a
human one here, and neither is settled:

  - An mleg **market** order has never been verified on this account. Every order this project has
    placed was a limit. A close path would have to use a marketable limit and nobody has measured
    what that does to four legs at once.
  - `limit_price` is a **NET** price whose sign flips on a close: entering a condor takes a credit,
    closing it pays a debit. `CondorPlan` asserts the entry direction, and there is no equivalent
    guard on the way out. Inverting it does not raise — it places a real order at the wrong price.

So this prints, exits non-zero when something needs a human, and stops there.

    uv run python scripts/pin_check.py
    uv run python scripts/pin_check.py --expiry 2026-09-03   # only that expiry

Exit codes: 0 clear · 3 pin risk or breach · 2 could not evaluate.
"""

import argparse
import collections
import datetime
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from src.data.alpaca import AlpacaClient  # noqa: E402

WARN_POINTS = 2.0
"""How close spot may come to a short strike before a human is asked to look.

Two points on SPY is roughly a quarter of a percent. Inside that, an ordinary intraday move can
carry the short through on the last afternoon, which is the only session where there is no time
left to recover.
"""


def structures(positions):
    """Group option legs into (expiry, [(strike, right, qty)]) so shorts can be identified.

    Positions come back as individual legs. A short strike is one held negative; its wing is the
    long on the same side. Grouping by expiry rather than by order because that is how assignment
    actually resolves -- the broker does not care which ticket a leg arrived on.
    """
    by = collections.defaultdict(list)
    for p in positions:
        sym = p.symbol
        if len(sym) < 15 or not sym[3:9].isdigit():
            continue  # not an OCC option symbol
        exp = datetime.date(2000 + int(sym[3:5]), int(sym[5:7]), int(sym[7:9]))
        right = sym[9]
        strike = int(sym[10:]) / 1000.0
        by[exp].append((strike, right, int(p.qty)))
    return by


def pair_wings(legs):
    """Match each short to its own wing, consuming each long exactly once.

    A book can hold two condors at one expiry, and the broker does not record which ticket a leg
    arrived on. Taking the *nearest* long above a short therefore reaches into the other structure:
    on 3 September the 772 call's nearest long was 773, tranche 3's wing, while its own was 777.
    That made a short with no protection read as fully covered, and the check reported `watch`
    while an unprotected short sat in the money.

    Pairing by rank fixes it. Calls ascend away from spot and puts descend, so sorting both sides
    the same direction and zipping pairs each structure with itself: calls 768,772 against longs
    773,777 gives 768/773 and 772/777. A long consumed by one short cannot cover another, which is
    the property that was actually missing -- protection we do not own was being counted twice.

    Returns {(strike, right): wing_strike or None}.
    """
    out = {}
    for right in ("P", "C"):
        desc = right == "P"
        shorts = sorted((k for k, r, q in legs if r == right and q < 0), reverse=desc)
        longs = sorted((k for k, r, q in legs if r == right and q > 0), reverse=desc)
        for i, k in enumerate(shorts):
            out[(k, right)] = longs[i] if i < len(longs) else None
    return out


def assess(spot, legs, warn=WARN_POINTS):
    """Classify one expiry. Returns (severity, message) with severity 0 clear, 1 warn, 2 breach."""
    shorts = [(k, r) for k, r, q in legs if q < 0]
    if not shorts:
        return 0, "no short legs"
    wings = pair_wings(legs)

    worst, msg = 0, []
    for strike, right in sorted(shorts):
        if right == "P":
            itm = spot <= strike
            dist = spot - strike
        else:
            itm = spot >= strike
            dist = strike - spot
        wing = wings.get((strike, right))
        if itm:
            beyond = (wing is not None) and ((spot <= wing) if right == "P" else (spot >= wing))
            if beyond:
                worst = max(worst, 1)
                msg.append(f"{strike:g}{right} ITM and past its {wing:g} wing — fully defined loss")
            else:
                worst = 2
                msg.append(
                    f"{strike:g}{right} IN THE MONEY, spot {spot:.2f} short of the "
                    f"{wing if wing is not None else '?'} wing — assignment is not offset"
                )
        elif dist < warn:
            worst = max(worst, 2)
            msg.append(f"{strike:g}{right} only {dist:.2f} away — inside the {warn:g}pt guard")
        else:
            msg.append(f"{strike:g}{right} clear by {dist:.2f}")
    return worst, "; ".join(msg)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--expiry", default=None, help="YYYY-MM-DD; default is every open expiry")
    ap.add_argument("--warn", type=float, default=WARN_POINTS)
    ap.add_argument("--expect-account", default=None)
    a = ap.parse_args(argv)

    client = AlpacaClient()
    acct = client.account()
    if a.expect_account and acct.account_number != a.expect_account:
        print(
            f"  REFUSED: credentials resolve to {acct.account_number}, expected {a.expect_account}"
        )
        return 2

    spot = client.stock_closes_latest(["SPY"])["SPY"]
    groups = structures(client.positions())
    if not groups:
        print("  no open option positions")
        return 0

    today = datetime.date.today()
    print(
        f"  {datetime.datetime.now():%Y-%m-%d %H:%M:%S}   SPY {spot:.2f}   "
        f"account {acct.account_number}"
    )
    worst = 0
    for exp in sorted(groups):
        if a.expiry and exp.isoformat() != a.expiry:
            continue
        sev, msg = assess(spot, groups[exp], warn=a.warn)
        expiring = " EXPIRES TODAY" if exp == today else ""
        # Only an expiry that settles today can pin. Earlier ones still report, at lower severity.
        if exp != today:
            sev = min(sev, 1)
        worst = max(worst, sev)
        tag = {0: "clear", 1: "watch", 2: "** NEEDS A HUMAN **"}[sev]
        print(f"  {exp}{expiring}  {tag}")
        print(f"      {msg}")

    if worst >= 2:
        print("\n  Close by hand if this is the last 45 minutes. Use a MARKETABLE LIMIT, not a")
        print("  market order — mleg market orders are unverified here — and remember the net")
        print("  price sign flips on a close: closing a credit structure pays a debit.")
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
