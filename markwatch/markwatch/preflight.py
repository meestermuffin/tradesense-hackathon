"""Check every assumption this package makes, against the real account.

Run before the first order. It writes nothing, trades nothing, and signs
nothing -- it reads and reports. Exit code 0 means the collector will work.

    python3 -m markwatch.preflight
    python3 -m markwatch.preflight --underlying SPY   # also probe a live chain

What it checks, in the order that matters:

    1. credentials present
    2. trading API reachable, and WHICH account (equity, cash, blocked flags)
    3. positions endpoint shape -- the fields the collector reads
    4. option quotes reachable, and on which feed
    5. quote timestamps parse, and how old they actually are
    6. a full collector pass end to end

Every check reports what it found rather than asserting a pass, because on
this account several of these are open questions rather than known values.
"""

import argparse
import datetime as dt
import urllib.parse
import sys
from typing import Any, Dict, List, Optional

from .alpaca import AlpacaError, Client, credentials, option_positions, parse_ts
from .collector import Collector
from .journal import Journal
from .markcheck import classify_quote, format_report

OK = "  ok   "
WARN = " warn  "
FAIL = " FAIL  "
INFO = " info  "


def line(tag: str, msg: str) -> None:
    print("[%s] %s" % (tag, msg), flush=True)


def check_credentials() -> bool:
    try:
        key, _ = credentials()
    except RuntimeError as exc:
        line(FAIL, str(exc))
        return False
    line(OK, "credentials present (key ends ...%s)" % key[-4:])
    return True


def check_account(client: Client) -> Optional[Dict[str, Any]]:
    try:
        acct = client.get_account()
    except AlpacaError as exc:
        line(FAIL, "account unreachable: %s" % exc)
        return None
    # Guardrail #10: trading the wrong book is the only silent error here.
    line(OK, "account %s  status=%s" % (acct.get("account_number", "?"), acct.get("status")))
    line(INFO, "equity=%s  cash=%s  buying_power=%s"
         % (acct.get("equity"), acct.get("cash"), acct.get("options_buying_power")
            or acct.get("buying_power")))
    # options_trading_level is the EFFECTIVE level (min of approved and the
    # account-configuration cap) and is what order acceptance is gated on.
    # Approved 3 / configured 2 accepts no condor, so report the effective one.
    approved = acct.get("options_approved_level")
    effective = acct.get("options_trading_level")
    lvl = effective if effective is not None else approved
    if lvl is not None:
        try:
            ok = int(lvl) >= 3
        except (TypeError, ValueError):
            ok = False
        line(OK if ok else WARN, "options level = %s effective (condors need 3)" % lvl)
        try:
            if approved is not None and effective is not None and int(effective) < int(approved):
                line(WARN, "approved level %s but effective %s -- raise "
                           "max_options_trading_level in account configurations"
                     % (approved, effective))
        except (TypeError, ValueError):
            pass
    for flag in ("trading_blocked", "account_blocked", "transfers_blocked"):
        if acct.get(flag):
            line(WARN, "%s is TRUE" % flag)
    return acct


def check_positions(client: Client) -> List[Dict[str, Any]]:
    try:
        positions = client.get_positions()
    except AlpacaError as exc:
        line(FAIL, "positions unreachable: %s" % exc)
        return []
    opts = option_positions(positions)
    line(OK, "positions endpoint ok: %d total, %d options" % (len(positions), len(opts)))
    if not positions:
        line(INFO, "book is empty -- shape checks below are skipped, rerun after the first fill")
        return []
    sample = (opts or positions)[0]
    for field in ("symbol", "qty", "side", "market_value", "asset_class"):
        if field in sample:
            line(OK, "  position.%s = %r" % (field, sample[field]))
        else:
            line(FAIL, "  position.%s MISSING -- collector assumes it exists" % field)
    return opts


def check_quotes(client: Client, symbols: List[str], underlying: Optional[str]) -> None:
    if not symbols and underlying:
        line(INFO, "no open option positions; probing the %s chain instead" % underlying)
        symbols = discover_chain_symbols(client, underlying)
    if not symbols:
        line(WARN, "no option symbols to probe -- pass --underlying SPY to test the feed")
        return

    feed = client.resolve_feed(symbols)
    if feed is None:
        line(FAIL, "no options feed works on this account. "
                   "Tried: indicative, opra. This is the §6.0 blocker.")
        return
    line(OK, "options quotes work on feed=%s" % feed)
    if feed != "opra":
        line(WARN, "%s quotes are DERIVED, not the true OPRA NBBO -- "
                   "recorded per row so the write-up can say which" % feed)

    try:
        quotes = client.get_quotes(symbols)
    except AlpacaError as exc:
        line(FAIL, "quote fetch failed: %s" % exc)
        return
    line(INFO, "requested %d symbols, got %d quotes" % (len(symbols), len(quotes)))
    if not quotes:
        line(WARN, "feed responded but returned no quotes for these symbols -- "
                   "the feed works; these contracts are not quoting")
        return

    missing = [s for s in symbols if s not in quotes]
    if missing:
        line(WARN, "%d symbol(s) returned no quote (recorded unquotable): %s"
             % (len(missing), ", ".join(missing[:3])))

    now = dt.datetime.now(dt.timezone.utc)
    unparsed = 0
    ages = []
    statuses = {}
    for sym, q in quotes.items():
        ts = q.get("ts")
        if ts is None:
            unparsed += 1
            age = None
        else:
            age = (now - ts).total_seconds()
            ages.append(age)
        st = classify_quote(q.get("bid"), q.get("ask"), age)
        statuses[st] = statuses.get(st, 0) + 1

    if unparsed:
        line(FAIL, "%d quote timestamp(s) did not parse -- every such leg reads stale" % unparsed)
    if ages:
        ages.sort()
        med = ages[len(ages) // 2]
        line(OK if med <= 15 else WARN,
             "quote age: median %.1fs  min %.1fs  max %.1fs" % (med, ages[0], ages[-1]))
        if med > 15:
            line(WARN, "median age exceeds the 15s freshness guard -- "
                       "either the feed is delayed or raise freshness_s deliberately")
    line(INFO, "classification: %s" % (", ".join("%s=%d" % kv for kv in sorted(statuses.items()))))

    sample_sym = sorted(quotes)[0]
    s = quotes[sample_sym]
    line(INFO, "sample %s  bid=%s ask=%s ts=%s" % (sample_sym, s["bid"], s["ask"], s["ts"]))


def discover_chain_symbols(client: Client, underlying: str, limit: int = 10) -> List[str]:
    """Pull a few real contract symbols so the feed can be probed with an empty book."""
    today = dt.date.today()
    params = urllib.parse.urlencode({
        "underlying_symbols": underlying,
        "status": "active",
        "expiration_date_gte": today.isoformat(),
        "expiration_date_lte": (today + dt.timedelta(days=30)).isoformat(),
        "limit": 100,
    })
    try:
        payload = client._get(client.trading_base + "/v2/options/contracts?" + params)
    except AlpacaError as exc:
        line(WARN, "could not list contracts for %s: %s" % (underlying, exc))
        return []
    contracts = (payload or {}).get("option_contracts", []) or []
    if not contracts:
        line(WARN, "contracts endpoint returned an empty list for %s "
                   "(not a transport failure)" % underlying)
        return []

    # An arbitrary slice is typically deep-ITM strikes that never print a
    # quote, which would make a healthy feed look like the §6.0 blocker.
    # Prefer contracts with real open interest.
    def oi(c):
        try:
            return float(c.get("open_interest") or 0)
        except (TypeError, ValueError):
            return 0.0

    contracts.sort(key=oi, reverse=True)
    syms = [c.get("symbol") for c in contracts if c.get("symbol")][:max(limit, 10)]
    if syms:
        line(OK, "found %d live %s contracts to probe (highest open interest)"
             % (len(syms), underlying))
    return syms


def check_collector_pass(client: Client, db_path: str) -> None:
    journal = Journal(db_path)
    journal.connect()
    col = Collector(
        journal=journal,
        get_positions=client.get_positions,
        get_quotes=client.get_quotes,
        get_account=client.get_account,
    )
    try:
        result = col.sample()
    except Exception as exc:  # noqa: BLE001 - preflight reports, never crashes
        line(FAIL, "collector pass raised: %r" % (exc,))
        return
    line(OK, "collector pass completed, snapshot %s" % result["snapshot_id"])
    print()
    print(format_report(result))
    print()


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Validate markwatch against the live account.")
    ap.add_argument("--underlying", default=None,
                    help="probe this chain when the book is empty, e.g. SPY")
    ap.add_argument("--live", action="store_true", help="use the live endpoint (default: paper)")
    ap.add_argument("--db", default="preflight.db", help="scratch journal path")
    args = ap.parse_args(argv)

    print("markwatch preflight -- reads only, places no orders\n")

    if not check_credentials():
        return 1

    client = Client(paper=not args.live)
    line(INFO, "trading endpoint: %s" % client.trading_base)

    acct = check_account(client)
    if acct is None:
        return 1

    opts = check_positions(client)
    symbols = [p["symbol"] for p in opts if p.get("symbol")]

    check_quotes(client, symbols, args.underlying)
    check_collector_pass(client, args.db)

    print("preflight complete. Re-run once the first condor is filled -- "
          "the position-shape and mark checks only mean something with an open book.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
