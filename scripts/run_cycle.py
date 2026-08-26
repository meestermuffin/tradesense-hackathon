#!/usr/bin/env python3
"""The daily cycle: rank, select, check risk, place.

**Dry run is the default.** Trading requires --live, explicitly. A scheduler invoking this by
mistake must not be able to open positions.

A lockfile guards against overlapping cycles. That guard is carried from the existing trader-api,
where it exists because a scheduler retry after a timeout would otherwise double-trade.
"""
import argparse, datetime, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.data.alpaca import AlpacaClient
from src.data.files import FileFeatureSource
from src.options.signal import rank_universe
from src.options.selection import select_vertical
from src.options.live_iv import live_iv
from src.options import execution
from src.risk import check_entry, defined_risk, portfolio_state
from src.universe import UNIVERSE, MAX_OPEN_POSITIONS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCK = os.path.join(ROOT, ".cycle.lock")
LOGDIR = os.path.join(ROOT, "logs")

TEMPLATE = dict(structure="put_credit", target_delta=0.25, width=5.0, max_width=25.0,
                dte_min=5, dte_max=9, max_spread_pct=0.08, delta_tolerance=0.15)


def acquire_lock():
    try:
        fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, f"{os.getpid()} {datetime.datetime.now().isoformat()}\n".encode())
        os.close(fd)
        return True
    except FileExistsError:
        try:
            age = datetime.datetime.now().timestamp() - os.path.getmtime(LOCK)
        except OSError:
            age = 0
        if age > 3600:      # a cycle that has run an hour is dead, not busy
            os.unlink(LOCK)
            return acquire_lock()
        print(f"a cycle is already running (lock {age:.0f}s old) — refusing to overlap")
        return False


def latest_series(path):
    src = FileFeatureSource(path)
    return {s: src.iv_series(s) for s in src.symbols()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="actually place orders")
    ap.add_argument("--series", default=None)
    ap.add_argument("--top", type=int, default=MAX_OPEN_POSITIONS)
    ap.add_argument("--deadline", default=None, help="refuse expiries past this date")
    a = ap.parse_args()

    if not acquire_lock():
        return 2
    try:
        series_path = a.series or _newest_series()
        if not series_path:
            print("no IV series in data/ — run scripts/build_iv_series.py first")
            return 1
        print(f"series      {os.path.relpath(series_path, ROOT)}")

        c = AlpacaClient()
        clock = c.clock()
        acct = c.account()
        positions = c.positions()
        state = portfolio_state(acct, positions)
        print(f"account     {acct['account_number']}  equity ${state['equity']:,.2f}  "
              f"open legs {len(positions)}  market_open={clock.get('is_open')}")
        print(f"mode        {'LIVE — orders will be placed' if a.live else 'DRY RUN — no orders'}")

        hist = latest_series(series_path)
        last_day = max((r[-1][0] for r in hist.values() if r), default=None)
        if last_day:
            age = (datetime.date.today() - datetime.date.fromisoformat(last_day)).days
            print(f"series ends {last_day} ({age} calendar days ago)")
            if age > 5:
                print(f"REFUSING: the trailing window ends {age} days ago. A percentile computed "
                      f"against a stale window looks confident and means nothing — this is the "
                      f"failure mode where every service reports healthy and the number is junk.")
                print("Rebuild with scripts/build_iv_series.py before trading.")
                return 1
        spots = c.stock_closes_latest(UNIVERSE)

        # today's observation comes from the live quote; bars stop at yesterday
        for sym in UNIVERSE:
            if sym not in spots:
                continue
            got, why = live_iv(c, sym, spots[sym])
            if got:
                hist.setdefault(sym, []).append((datetime.date.today().isoformat(), got["iv"]))
            else:
                print(f"  {sym}: no live IV ({why}) — ranked on history through yesterday")

        ranked = rank_universe(hist)
        print("\nrank  name   IV       pct    obs")
        for i, r in enumerate(ranked, 1):
            if not r["eligible"]:
                print(f"  --  {r['symbol']:5}  ineligible: {r['reason']}")
                continue
            print(f"  {i:2}  {r['symbol']:5}  {r['iv']*100:6.2f}%  {r['percentile']:5.1f}  {r['obs']}")

        held = {p["symbol"][:len(p["symbol"])] for p in positions}
        existing_risk = 0.0
        deadline = datetime.date.fromisoformat(a.deadline) if a.deadline else None
        placed = 0
        print()
        for r in [x for x in ranked if x["eligible"]][:a.top]:
            sym = r["symbol"]
            cand = select_vertical(c, sym, spots[sym], TEMPLATE)
            if cand.get("rejected"):
                print(f"  {sym:5} no structure: {cand['rejected']}")
                continue
            n, reasons = check_entry(cand, state["equity"], [{"underlying": p} for p in held],
                                     existing_risk, state["equity"], deadline=deadline)
            head = (f"  {sym:5} {cand['expiry']} {cand['short']['strike']:g}/"
                    f"{cand['long']['strike']:g} d={cand['short_delta']:+.2f} "
                    f"credit {cand['credit_mid']:.2f} (touch {cand['credit_touch']:.2f}) "
                    f"maxloss {cand['max_loss']:.2f}")
            if reasons:
                print(head + "  REFUSED: " + "; ".join(reasons))
                continue
            print(head + f"  -> {n} contracts, risk ${defined_risk(cand['width'], cand['credit_mid'], n):,.0f}")
            existing_risk += defined_risk(cand["width"], cand["credit_mid"], n)
            held.add(sym)
            if a.live:
                rec = execution.place(c, cand, n, log_dir=LOGDIR)
                print(f"        {rec.get('status')} fill={rec.get('fill')} "
                      f"vs_mid={rec.get('vs_mid')} vs_touch={rec.get('vs_touch')}")
                if not rec.get("filled"):
                    execution.cancel_if_resting(c, rec)
                    print("        did not fill — cancelled rather than left resting")
                else:
                    placed += 1
        print(f"\n{'placed' if a.live else 'would place'} {placed if a.live else len(held)} position(s)")
        return 0
    finally:
        if os.path.exists(LOCK):
            os.unlink(LOCK)


def _newest_series():
    d = os.path.join(ROOT, "data")
    files = [os.path.join(d, f) for f in os.listdir(d) if f.startswith("iv_series_")]
    return max(files, key=os.path.getmtime) if files else None


if __name__ == "__main__":
    sys.exit(main())
