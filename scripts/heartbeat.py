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


def main():
    day = last_session()
    iso = day.isoformat()
    problems, notes = [], []

    cap = os.path.join(ROOT, "data", "nbbo", f"nbbo_{iso}.csv")
    if os.path.exists(cap):
        n = sum(1 for _ in open(cap)) - 1
        notes.append(f"capture   {n} quotes")
        if n < 50:
            problems.append(f"capture for {iso} has only {n} rows — expected ~130")
    else:
        problems.append(
            f"NO NBBO CAPTURE for {iso}. That session's spreads are gone permanently — "
            f"there is no historical quote endpoint to backfill from."
        )

    eq = os.path.join(ROOT, "data", "equity_curve.csv")
    if os.path.exists(eq) and any(l.startswith(iso) for l in open(eq)):
        notes.append("equity    row present")
    else:
        problems.append(
            f"NO EQUITY ROW for {iso}. Sharpe and max drawdown are computed from "
            f"consecutive daily returns; a gap distorts both."
        )

    log = os.path.join(ROOT, "logs", "cycle.out.log")
    if os.path.exists(log):
        age_h = (datetime.datetime.now().timestamp() - os.path.getmtime(log)) / 3600
        notes.append(f"cycle log {age_h:.1f}h old")
        if age_h > 24:
            problems.append(
                f"cycle log has not been written in {age_h:.0f}h — the scheduled cycle "
                f"is not running"
            )
    else:
        problems.append("no cycle log at all — the scheduler has never run run_cycle.py")

    print(f"heartbeat for last session {iso} ({day.strftime('%A')})")
    for n in notes:
        print(f"  ok   {n}")
    for p in problems:
        print(f"  FAIL {p}")
    if problems:
        print(
            f"\n{len(problems)} problem(s). Check: laptop asleep at the scheduled time is the "
            f"most likely cause — `pmset -g sched` should show a weekday wake before 15:50."
        )
        # A failure written only to a log file is the same silence this script exists to break.
        if "--notify" in sys.argv:
            head = problems[0].split(".")[0].replace(chr(34), chr(39))
            os.system(
                "osascript -e "
                + chr(39)
                + "display notification "
                + chr(34)
                + head
                + chr(34)
                + " with title "
                + chr(34)
                + "tradesense: "
                + str(len(problems))
                + " problem(s)"
                + chr(34)
                + chr(39)
                + " >/dev/null 2>&1"
            )
        return 1
    print("\nall three ran.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
