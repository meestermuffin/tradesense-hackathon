#!/usr/bin/env python3
"""Record one equity observation per session.

**Deliberately independent of the trading cycle.** Carried from the existing trader-api, whose
comment says why: a cycle that was skipped, errored, or found the market open still has to leave a
row, because Sharpe and max drawdown are computed from consecutive daily returns and gaps distort
them. For a five-session judged window this file *is* the P&L curve.
"""

import csv
import datetime
import os
import platform
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.data.alpaca import AlpacaClient

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# One file per account. equity_curve.csv is the judged P&L record; a second machine appending
# rows for a different account into the same file is a reconciliation problem during submission
# week, which is the worst possible time to discover it.
OUTDIR = os.path.join(ROOT, "data", "equity")


def main():
    c = AlpacaClient()
    a = c.account()
    pos = c.positions()
    os.makedirs(OUTDIR, exist_ok=True)
    out = os.path.join(OUTDIR, f"{a['account_number']}.csv")
    row = dict(
        day=datetime.date.today().isoformat(),
        host=platform.node(),
        captured_at=datetime.datetime.now(datetime.UTC).isoformat(),
        account=a["account_number"],
        equity=a["equity"],
        last_equity=a.get("last_equity"),
        cash=a["cash"],
        position_market_value=a.get("position_market_value"),
        open_legs=len(pos),
        symbols="|".join(sorted(p["symbol"] for p in pos)),
    )
    new = not os.path.exists(out)
    with open(out, "a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(row.keys()))
        if new:
            w.writeheader()
        w.writerow(row)
    print(
        f"{row['day']}  equity {row['equity']}  open legs {row['open_legs']}  -> "
        f"{os.path.relpath(out, ROOT)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
