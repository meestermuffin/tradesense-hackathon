#!/usr/bin/env python3
"""Did yesterday's session actually happen?

This pipeline's signature failure is going stale while every service reports healthy. A laptop
asleep at 15:50 produces no capture, no cycle and no equity row -- and nothing anywhere says so,
because nothing ran to say it.

Run this every morning. Silence from the scheduler is the failure signal, so something has to go
looking for the silence.

Exits non-zero when a session is missing, so it can drive a notification.
"""

import datetime
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def last_session(today=None):
    d = (today or datetime.date.today()) - datetime.timedelta(days=1)
    while d.weekday() > 4:  # crude: weekends only, not market holidays
        d -= datetime.timedelta(days=1)
    return d


def accounts():
    """Every account this clone has written data for.

    Deliberately derived from the filesystem rather than from credentials: the heartbeat has to work
    when credentials are the thing that is broken, and a clone may legitimately hold data for more
    than one account -- your own paper account alongside a shared one.
    """
    found = set()
    for sub in ("nbbo", "selection", "equity"):
        d = os.path.join(ROOT, "data", sub)
        if not os.path.isdir(d):
            continue
        for name in os.listdir(d):
            if sub == "equity" and name.endswith(".csv"):
                found.add(name[:-4])
            elif os.path.isdir(os.path.join(d, name)):
                found.add(name)
    return sorted(found)


def check_account(acct, day):
    iso = day.isoformat()
    problems, notes = [], []

    cap = os.path.join(ROOT, "data", "nbbo", acct, f"nbbo_{iso}.csv")
    if os.path.exists(cap):
        n = sum(1 for _ in open(cap)) - 1
        notes.append(f"capture  {n} quotes")
        if n < 50:
            problems.append(f"capture for {iso} has only {n} rows — expected ~130+")
    else:
        problems.append(
            f"NO NBBO CAPTURE for {iso}. That session's spreads are gone permanently — "
            f"there is no historical quote endpoint to backfill from."
        )

    eq = os.path.join(ROOT, "data", "equity", f"{acct}.csv")
    if os.path.exists(eq) and any(line.startswith(iso) for line in open(eq)):
        notes.append("equity   row present")
    else:
        problems.append(
            f"NO EQUITY ROW for {iso}. Max drawdown runs against a running peak, "
            f"so a missing session moves the peak and understates it."
        )
    return problems, notes


def main():
    day = last_session()
    accts = accounts()
    if not accts:
        print("no account data in this clone yet — nothing has run.")
        print("If you have just cloned: you do not need the scheduled agents to reproduce results.")
        return 0

    all_problems = 0
    print(f"heartbeat for last session {day.isoformat()} ({day.strftime('%A')})")
    for acct in accts:
        problems, notes = check_account(acct, day)
        print(f"\n  account {acct}")
        for n in notes:
            print(f"    ok   {n}")
        for p in problems:
            print(f"    FAIL {p}")
        all_problems += len(problems)

    log = os.path.join(ROOT, "logs", "cycle.out.log")
    if os.path.exists(log):
        age_h = (datetime.datetime.now().timestamp() - os.path.getmtime(log)) / 3600
        print(f"\n  cycle log {age_h:.1f}h old")
        if age_h > 24:
            print("    FAIL the scheduled cycle has not run in over 24h")
            all_problems += 1
    else:
        print("\n  no cycle log — the scheduler has never run run_cycle.py")
        all_problems += 1

    if all_problems:
        print(
            f"\n{all_problems} problem(s). On a machine that is meant to be running the book, the "
            f"likeliest cause is sleep — `pmset -g sched` should show a weekday wake before 15:50."
        )
        if "--notify" in sys.argv:
            os.system(
                "osascript -e "
                + chr(39)
                + "display notification "
                + chr(34)
                + f"{all_problems} problem(s) — see logs"
                + chr(34)
                + " with title "
                + chr(34)
                + "tradesense heartbeat"
                + chr(34)
                + chr(39)
                + " >/dev/null 2>&1"
            )
        return 1
    print("\nall checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
