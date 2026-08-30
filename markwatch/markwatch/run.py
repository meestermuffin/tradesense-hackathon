"""CLI: the capture loop, and the report.

    python3 -m markwatch.run --interval 60
    python3 -m markwatch.run --report
    python3 -m markwatch.run --until 2026-09-03T20:05:00Z

Runs in its own process. It reads and writes its own SQLite file, never places
an order, and never touches the agent's state.
"""

import argparse
import datetime as dt
import sys
from typing import List, Optional

from .alpaca import Client, parse_ts
from .collector import Collector, report_latest
from .journal import Journal


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="markwatch capture loop")
    ap.add_argument("--db", default="journal.db")
    ap.add_argument("--interval", type=float, default=60.0, help="seconds between passes")
    ap.add_argument("--freshness", type=float, default=15.0,
                    help="a quote older than this is stale, not a price")
    ap.add_argument("--until", default=None,
                    help="stop at this RFC3339 instant, e.g. 2026-09-03T20:05:00Z")
    ap.add_argument("--once", action="store_true", help="single pass, then exit")
    ap.add_argument("--report", action="store_true", help="print the latest snapshot and exit")
    ap.add_argument("--live", action="store_true", help="live endpoint (default: paper)")
    args = ap.parse_args(argv)

    journal = Journal(args.db)
    journal.connect()

    if args.report:
        print(report_latest(journal, freshness_s=args.freshness))
        return 0

    client = Client(paper=not args.live)
    collector = Collector(
        journal=journal,
        get_positions=client.get_positions,
        get_quotes=client.get_quotes,
        get_account=client.get_account,
        freshness_s=args.freshness,
    )

    if args.once:
        result = collector.sample()
        print(result["verdict"])
        return 0

    until = parse_ts(args.until) if args.until else None
    if args.until and until is None:
        print("could not parse --until %r" % args.until, file=sys.stderr)
        return 2

    print("markwatch capturing every %.0fs%s  (ctrl-c to stop)"
          % (args.interval, (" until %s" % until.isoformat()) if until else ""), flush=True)
    try:
        collector.run(interval_s=args.interval, until=until)
    except KeyboardInterrupt:
        print("\nstopped. %d snapshots recorded." % len(journal.snapshot_ids()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
