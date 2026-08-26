#!/usr/bin/env python3
"""Check that an Alpaca paper account can actually run this project.

Entitlements are per-account, not per-user. An account that looks identical in the dashboard can be
missing the one endpoint everything rests on, and the failure mode is a 200 response with keys
quietly absent rather than an error. Run this against a new account before building on it.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.alpaca import DATA_HOST, AlpacaClient, AlpacaError  # noqa: E402

EXPIRED = "SPY240315C00195000"  # a contract that expired in 2024


def check(label, fn, expect_fail=False):
    try:
        ok, detail = fn()
    except AlpacaError as e:
        ok, detail = (True, f"{e.status} (expected)") if expect_fail else (False, f"{e.status}")
    except Exception as e:  # noqa: BLE001
        ok, detail = False, str(e)[:60]
    print(f"  {'PASS' if ok else 'FAIL'}  {label:44} {detail}")
    return ok


def main():
    c = AlpacaClient()
    a = c.account()
    print(f"account {a['account_number']}  status {a['status']}  equity ${float(a['equity']):,.2f}")
    print(
        f"options approval level {a.get('options_approved_level')}  (3 is required for spreads)\n"
    )

    results = []

    def bars():
        d = c.option_bars([EXPIRED], "2024-02-01", "2024-03-01")
        n = len(d.get(EXPIRED, []))
        return n > 0, f"{n} bars on an expired 2024 contract"

    def contracts():
        cs = c.option_contracts("SPY", expiration_date="2024-03-15", status="inactive", limit=5)
        return len(cs) > 0, f"{len(cs)}+ expired contracts enumerable"

    def latest():
        q = c.option_quotes_latest([EXPIRED])
        return True, "reachable" if q else "reachable (empty for expired, expected)"

    def greeks():
        d = c.request("GET", DATA_HOST, "/v1beta1/options/snapshots/SPY", {"limit": 3})
        keys = {k for s in (d.get("snapshots") or {}).values() for k in s}
        has = "greeks" in keys or "impliedVolatility" in keys
        return (not has), (
            "greeks absent — IV must be inverted (expected)"
            if not has
            else "greeks PRESENT — this account differs from ours"
        )

    results.append(check("options/bars on an expired contract", bars))
    results.append(check("options/contracts status=inactive", contracts))
    results.append(check("options/quotes/latest", latest))
    results.append(check("greeks absent from snapshots", greeks))
    results.append(
        check(
            "account has options level 3",
            lambda: (
                int(a.get("options_approved_level") or 0) >= 3,
                f"level {a.get('options_approved_level')}",
            ),
        )
    )

    print()
    if all(results):
        print("This account can run the project. options/bars on expired contracts is the")
        print("load-bearing one — without it the IV series cannot be built at all.")
        return 0
    print("Something this project depends on is missing on this account. The IV series, and")
    print("therefore the signal, cannot be rebuilt without options/bars on expired contracts.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
