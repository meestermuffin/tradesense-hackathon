"""Alpaca REST adapter over stdlib only.

No alpaca-py dependency. Two reasons: it runs on whatever Python is already
there, and every HTTP call is visible in ~200 lines rather than behind an SDK
whose behaviour we would have to re-verify anyway.

Endpoints used:

    GET {trading}/v2/account
    GET {trading}/v2/positions
    GET {data}/v1beta1/options/quotes/latest?symbols=...&feed=...

Credentials come from the environment and are never logged:

    ALPACA_API_KEY / ALPACA_SECRET_KEY   (or APCA_API_KEY_ID / APCA_API_SECRET_KEY)

The `feed` question is live: this account has no OPRA agreement, so `feed=opra`
is expected to error rather than degrade. `resolve_feed()` probes the options
which actually works and caches it, so the collector never has to care.
"""

import datetime as dt
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

PAPER_TRADING = "https://paper-api.alpaca.markets"
LIVE_TRADING = "https://api.alpaca.markets"
DATA = "https://data.alpaca.markets"

# Tried in order. The first that returns a 200 with a usable quote wins.
FEED_CANDIDATES = ("indicative", "opra")

# Alpaca batches symbols per request; keep well under any URL length limit.
QUOTE_CHUNK = 100


class AlpacaError(RuntimeError):
    def __init__(self, status: int, url: str, body: str):
        self.status = status
        self.url = url
        self.body = body
        # Never interpolate credentials; url carries no secrets.
        super().__init__("HTTP %s on %s: %s" % (status, url.split("?")[0], body[:400]))


def credentials() -> Tuple[str, str]:
    key = os.environ.get("ALPACA_API_KEY") or os.environ.get("APCA_API_KEY_ID")
    sec = os.environ.get("ALPACA_SECRET_KEY") or os.environ.get("APCA_API_SECRET_KEY")
    if not key or not sec:
        raise RuntimeError(
            "Missing credentials. Set ALPACA_API_KEY and ALPACA_SECRET_KEY "
            "(or APCA_API_KEY_ID / APCA_API_SECRET_KEY)."
        )
    return key, sec


def parse_ts(value: Any) -> Optional[dt.datetime]:
    """RFC3339 with up to nanosecond precision, which 3.9's fromisoformat rejects.

    Returns a timezone-aware UTC datetime, or None. A None here makes the leg
    read `stale` downstream, which is the correct conservative failure.
    """
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        return value if value.tzinfo else value.replace(tzinfo=dt.timezone.utc)
    s = str(value).strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    # Trim fractional seconds to microseconds: 3.9 accepts 3 or 6 digits only.
    if "." in s:
        head, rest = s.split(".", 1)
        digits = ""
        for ch in rest:
            if ch.isdigit():
                digits += ch
            else:
                rest = rest[len(digits):]
                break
        else:
            rest = ""
        digits = (digits + "000000")[:6]
        s = "%s.%s%s" % (head, digits, rest)
    try:
        parsed = dt.datetime.fromisoformat(s)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)


class Client:
    def __init__(self, paper: bool = True, timeout: float = 10.0):
        self.trading_base = PAPER_TRADING if paper else LIVE_TRADING
        self.data_base = DATA
        self.timeout = timeout
        self._feed: Optional[str] = None
        self._feed_resolved = False

    # ---------- transport ----------

    def _get(self, url: str) -> Any:
        key, sec = credentials()
        req = urllib.request.Request(url, method="GET")
        req.add_header("APCA-API-KEY-ID", key)
        req.add_header("APCA-API-SECRET-KEY", sec)
        req.add_header("Accept", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", "replace")
            except Exception:
                pass
            raise AlpacaError(e.code, url, body)
        except urllib.error.URLError as e:
            raise AlpacaError(0, url, str(e.reason))

    # ---------- trading ----------

    def get_account(self) -> Dict[str, Any]:
        return self._get(self.trading_base + "/v2/account")

    def get_positions(self) -> List[Dict[str, Any]]:
        return self._get(self.trading_base + "/v2/positions")

    # ---------- market data ----------

    def resolve_feed(self, probe_symbols: List[str]) -> Optional[str]:
        """Find the options feed this account can actually read.

        §6.0 of the plan lists this as blocking: free-plan requests for OPRA
        data error rather than degrading silently, so it must be established
        once rather than discovered mid-session.

        A 200 with an empty `quotes` map means the FEED works and those
        symbols simply had no quote -- accepting only a non-empty map would
        disqualify a working feed on an illiquid probe. Only an AlpacaError
        rejects a feed. The negative result is cached too: re-probing every
        pass is the worst possible behaviour if the cause was a 429.
        """
        if self._feed_resolved:
            return self._feed
        if not probe_symbols:
            return None
        for feed in FEED_CANDIDATES:
            try:
                self._raw_quotes(probe_symbols[:10], feed)
            except AlpacaError:
                continue
            self._feed = feed
            self._feed_resolved = True
            return feed
        self._feed_resolved = True
        return None

    @property
    def feed(self) -> Optional[str]:
        """The feed in use, once resolved. Recorded with every snapshot."""
        return self._feed

    def _raw_quotes(self, symbols: List[str], feed: Optional[str]) -> Dict[str, Any]:
        # An omitted `feed` defaults to opra server-side, which 403s without
        # an OPRA agreement. Always send one explicitly.
        params = {"symbols": ",".join(symbols), "feed": feed or FEED_CANDIDATES[0]}
        url = self.data_base + "/v1beta1/options/quotes/latest?" + urllib.parse.urlencode(params)
        payload = self._get(url)
        return (payload or {}).get("quotes", {}) or {}

    def get_quotes(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """Normalised NBBO per symbol: {"bid","ask","ts","bid_size","ask_size"}.

        A symbol the API omits is simply absent from the result, which the
        collector records as `unquotable` rather than guessing a price.
        """
        out: Dict[str, Dict[str, Any]] = {}
        if not symbols:
            return out
        feed = self.resolve_feed(symbols)
        for i in range(0, len(symbols), QUOTE_CHUNK):
            chunk = symbols[i:i + QUOTE_CHUNK]
            raw = self._raw_quotes(chunk, feed)
            for sym, q in (raw or {}).items():
                out[sym] = normalise_quote(q)
        return out


def normalise_quote(q: Dict[str, Any]) -> Dict[str, Any]:
    """Alpaca's compact quote keys -> the shape markcheck expects.

    bp/ap are bid/ask price, bs/as size, t the exchange timestamp. Zeroes are
    passed through untouched: a 0 bid is a real market condition and
    classify_quote is what decides it is unquotable, not this function.
    """
    def num(*keys):
        for k in keys:
            if k in q and q[k] is not None:
                try:
                    return float(q[k])
                except (TypeError, ValueError):
                    return None
        return None

    return {
        "bid": num("bp", "bid_price", "bid"),
        "ask": num("ap", "ask_price", "ask"),
        "bid_size": num("bs", "bid_size"),
        "ask_size": num("as", "ask_size"),
        "ts": parse_ts(q.get("t") or q.get("timestamp")),
    }


def option_positions(positions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [p for p in positions
            if "option" in str(p.get("asset_class", "")).lower()]


def make_callables(client: Optional[Client] = None, paper: bool = True):
    """The three functions Collector wants, bound to a live account."""
    c = client or Client(paper=paper)
    return {
        "get_positions": c.get_positions,
        "get_quotes": c.get_quotes,
        "get_account": c.get_account,
        "client": c,
    }
