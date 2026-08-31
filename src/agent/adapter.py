"""Bridge between this repo's Alpaca client and Solo's `markwatch` package.

`markwatch` answers the question that decides the headline: **is the scored equity number a price
we could actually get?** It is scored on a mark, not a fill, so if the paper engine marks at mid it
credits us spread we could never have collected -- about $35 per one-lot condor, roughly $1,015 at
29 contracts. No guardrail in the trading plan can see that, because the book moves with no trade.

It takes three injected callables rather than a client, which is what makes this possible. But its
expectations and `src.data.alpaca.AlpacaClient` disagree in eleven places, and the dangerous ones
are silent:

- **Positions.** `src.models.Position` keeps only `symbol` and `qty`; `Wire` is `extra="ignore"`,
  so `market_value`, `asset_class` and `side` are *discarded at parse time*. Feed those to the
  collector and every `broker_mark` is `None`, the verdict reads "broker marks missing", and the
  whole question goes unanswered with no error. **This adapter reads the raw payload instead.**
- **Quotes.** Ours are pydantic objects; markwatch calls `.get()` on them. Our `timestamp` is a
  string; it wants a tz-aware `datetime` under the key `ts`. A string there fails an `isinstance`
  check, every age becomes `None`, every leg reads stale, and coverage lands at 0%.
- **Feed.** Our client never sends one. Omitted, Alpaca defaults to `opra` server-side, which 403s
  without an OPRA agreement.
- **One-sided quotes.** Our `Quote` requires both `bp` and `ap`, so a missing side raises and takes
  the whole batch of 40 down. markwatch treats an absent side as data and classifies it
  `unquotable` -- which is the statistic it exists to report. Absent symbols must be *omitted*, not
  present with nulls.

The conversions themselves are markwatch's own `normalise_quote` and `parse_ts`, reused rather than
reimplemented, so the fill path and the mark path cannot drift apart on what a quote is.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

_MW = Path(__file__).resolve().parents[2] / "markwatch"
if str(_MW) not in sys.path:
    sys.path.insert(0, str(_MW))

from markwatch.alpaca import normalise_quote  # noqa: E402

from ..data.alpaca import DATA_HOST, QUOTE_BATCH, AlpacaClient  # noqa: E402

FEED = "indicative"
"""Verified working against a live Basic-plan account on 2026-08-30.

Not a default we can rely on: the MCP tools and the REST endpoint both fall back to `opra`, which
this account is not entitled to. It has to be sent explicitly on every call.
"""


class MarkwatchBridge:
    """Exposes `get_quotes` / `get_positions` / `get_account` in markwatch's shape.

    Methods are **bound**, deliberately. `Collector.feed_name()` reaches through
    `get_quotes.__self__` to find a `.feed` attribute; a closure has no `__self__` and the
    `marks.feed` column silently goes NULL, which drops the "derived quotes, not true OPRA NBBO"
    caveat from every report.
    """

    feed = FEED

    def __init__(self, client: AlpacaClient | None = None):
        self.client = client or AlpacaClient()
        # markwatch's own Client reads ALPACA_API_KEY and never loads .env. If anything in the
        # package constructs one (preflight does), it needs the alias present.
        if self.client.key and not os.environ.get("ALPACA_API_KEY"):
            os.environ["ALPACA_API_KEY"] = self.client.key
        if self.client.secret and not os.environ.get("ALPACA_SECRET_KEY"):
            os.environ["ALPACA_SECRET_KEY"] = self.client.secret

    # ---- the three callables the Collector takes ----

    def get_quotes(self, symbols: list[str]) -> dict[str, dict[str, Any]]:
        """Latest NBBO as plain dicts: bid, ask, bid_size, ask_size, ts (tz-aware datetime).

        A symbol with no usable quote is **omitted**, never returned with nulls -- markwatch reads
        absence as "unquotable" and that rate is one of the things it is measuring.

        Batched at this repo's `QUOTE_BATCH` of 40, not markwatch's 100: large batches on this
        endpoint have failed here before and 40 is the known-good size.
        """
        out: dict[str, dict[str, Any]] = {}
        for i in range(0, len(symbols), QUOTE_BATCH):
            batch = symbols[i : i + QUOTE_BATCH]
            d = self.client.request(
                "GET",
                DATA_HOST,
                "/v1beta1/options/quotes/latest",
                {"symbols": ",".join(batch), "feed": FEED},
            )
            for sym, raw in (d.get("quotes") or {}).items():
                try:
                    q = normalise_quote(raw)
                except Exception:
                    continue  # one bad quote must not cost the batch
                if q.get("bid") is None and q.get("ask") is None:
                    continue  # nothing usable; absence is the signal
                out[sym] = q
        return out

    def get_positions(self) -> list[dict[str, Any]]:
        """Raw position payloads, NOT `src.models.Position`.

        The model drops `market_value`, `asset_class` and `side`. Without `market_value` there is no
        broker mark to compare against, which is the entire measurement.
        """
        return self.client.request("GET", self.client.trade_host, "/v2/positions")

    def get_account(self) -> dict[str, Any]:
        """Raw account payload. The collector needs `equity` and `cash`."""
        return self.client.request("GET", self.client.trade_host, "/v2/account")


def callables(client: AlpacaClient | None = None) -> dict[str, Any]:
    """The shape `markwatch.alpaca.make_callables` returns, backed by our client."""
    b = MarkwatchBridge(client)
    return {
        "get_positions": b.get_positions,
        "get_quotes": b.get_quotes,
        "get_account": b.get_account,
        "client": b.client,
        "bridge": b,
    }


def fill_legs(order, submitted_legs: list[dict], contracts: int) -> list[dict[str, Any]]:
    """Convert an `Order` into the leg dicts `Submission.filled()` requires.

    Needed because `sub.filled()` indexes `leg["symbol"]` and `leg["signed_qty"]` directly and
    raises `KeyError` on either, and our `OrderLeg` is an object with neither `signed_qty` nor a
    `fill_price` key -- it has `filled_avg_price`.

    `signed_qty` does not exist anywhere in the order response, so it is reconstructed from the
    submitted legs: `ratio_qty x contracts`, negative for a sell.

    `side` is passed through explicitly. It is the **trade direction**, which is what
    `reconcile_fill` wants; letting markwatch infer it flags `side_inferred` and assumes an opening
    trade, which scores every close as maximum price improvement.
    """
    by_symbol = {leg_["symbol"]: leg_ for leg_ in submitted_legs}
    out = []
    for leg_ in getattr(order, "legs", None) or []:
        sym = getattr(leg_, "symbol", None)
        if not sym:
            continue
        sub = by_symbol.get(sym, {})
        side = (sub.get("side") or getattr(leg_, "side", None) or "").lower()
        ratio = int(float(sub.get("ratio_qty", 1) or 1))
        qty = ratio * int(contracts)
        out.append(
            {
                "symbol": sym,
                "signed_qty": -qty if side == "sell" else qty,
                "fill_price": getattr(leg_, "filled_avg_price", None),
                "side": side or None,
                "broker_id": getattr(leg_, "id", None),
            }
        )
    return out
