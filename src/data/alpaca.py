"""Thin Alpaca client. Standard library only — no SDK, no database driver.

Facts encoded here that cost time to learn, so they are not re-learned:

- Contract metadata lives on the **trading** host, not the data host. A data key there returns 401.
- Past expiries need `status=inactive`. `all` and `expired` return an empty list with no error, and
  omitting `status` silently defaults to active contracts only.
- There is **no historical options quote endpoint**. Latest quotes only. Anything needing a past
  spread must have captured it at the time.
- Greeks and implied volatility are OPRA-gated and simply absent from an otherwise-200 response.
- For multi-leg orders `limit_price` is a **net** price: positive is a debit, negative a credit.
- Latest-quote requests fail at large symbol batches; 40 per request is known-good.
- **Historical options data excludes the current session.** A bars or trades window whose `end` is
  today returns 403 "OPRA agreement is not signed"; ending at the previous session returns 200 with
  data right up to it. There is no multi-day lag. Equity bars carry no such restriction and are
  available for the current day. Consequence: a live signal takes its trailing history from bars
  (through yesterday) and today's observation from `quotes/latest`, which is real-time.
"""
import json, os, time, urllib.error, urllib.parse, urllib.request

DATA_HOST = "https://data.alpaca.markets"
PAPER_HOST = "https://paper-api.alpaca.markets"
LIVE_HOST = "https://api.alpaca.markets"
QUOTE_BATCH = 40


class AlpacaError(RuntimeError):
    def __init__(self, status, body, url):
        super().__init__(f"HTTP {status} for {url}: {body[:300]}")
        self.status, self.body, self.url = status, body, url


def _load_dotenv():
    """Fall back to a gitignored .env at the repo root.

    launchd gives a job almost no environment, so a scheduled run has no exported keys. Putting
    them in the plist would leave credentials in a file launchd users can read; a chmod 600 .env
    keeps them in one place with one owner.
    """
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    path = os.path.join(root, ".env")
    if not os.path.exists(path):
        return
    for line in open(path):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip("'\""))


class AlpacaClient:
    def __init__(self, key=None, secret=None, paper=True):
        if not (key or os.environ.get("ALPACA_KEY_ID")):
            _load_dotenv()
        self.key = key or os.environ.get("ALPACA_KEY_ID")
        self.secret = secret or os.environ.get("ALPACA_SECRET_KEY")
        if not self.key or not self.secret:
            raise SystemExit("no credentials: set ALPACA_KEY_ID/ALPACA_SECRET_KEY or create .env")
        self.trade_host = PAPER_HOST if paper else LIVE_HOST

    # ---- transport ----
    def _headers(self):
        return {"APCA-API-KEY-ID": self.key, "APCA-API-SECRET-KEY": self.secret,
                "Content-Type": "application/json"}

    def request(self, method, host, path, params=None, body=None, timeout=45, retries=4):
        url = host + path
        if params:
            url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        data = json.dumps(body).encode() if body is not None else None
        for attempt in range(retries):
            req = urllib.request.Request(url, data=data, headers=self._headers(), method=method)
            try:
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    raw = r.read()
                    return json.loads(raw) if raw else {}
            except urllib.error.HTTPError as e:
                body_txt = e.read().decode(errors="replace")
                # 429 and 5xx are worth retrying; 4xx are not — they mean the request is wrong.
                if e.code == 429 or 500 <= e.code < 600:
                    if attempt == retries - 1:
                        raise AlpacaError(e.code, body_txt, url)
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise AlpacaError(e.code, body_txt, url)
            except urllib.error.URLError:
                if attempt == retries - 1:
                    raise
                time.sleep(1.5 * (attempt + 1))
        raise RuntimeError("unreachable")

    def _paged(self, host, path, key, params=None, limit_pages=200):
        out, tok, params = [], None, dict(params or {})
        for _ in range(limit_pages):
            params["page_token"] = tok
            d = self.request("GET", host, path, params)
            chunk = d.get(key)
            out += chunk if isinstance(chunk, list) else []
            tok = d.get("next_page_token")
            if not tok:
                break
        return out

    # ---- account and clock ----
    def account(self):
        return self.request("GET", self.trade_host, "/v2/account")

    def clock(self):
        return self.request("GET", self.trade_host, "/v2/clock")

    def positions(self):
        return self.request("GET", self.trade_host, "/v2/positions")

    # ---- market data ----
    def stock_closes_latest(self, symbols):
        d = self.request("GET", DATA_HOST, "/v2/stocks/bars/latest",
                         {"symbols": ",".join(symbols), "feed": "iex"})
        return {s: b["c"] for s, b in (d.get("bars") or {}).items()}

    def option_contracts(self, underlying, expiration_date=None, exp_gte=None, exp_lte=None,
                         type_=None, strike_gte=None, strike_lte=None,
                         status="active", limit=10000):
        """Contract metadata — TRADING host. `status='inactive'` is what reaches past expiries.

        **Pass an expiry bound.** With no `expiration_date`/`exp_lte`, the endpoint silently
        defaults `expiration_date_lte` to next weekend, so "list all expiries" quietly returns only
        the next few days and every downstream DTE filter comes back empty with no error.
        """
        return self._paged(self.trade_host, "/v2/options/contracts", "option_contracts", {
            "underlying_symbols": underlying, "expiration_date": expiration_date,
            "expiration_date_gte": exp_gte, "expiration_date_lte": exp_lte,
            "type": type_, "strike_price_gte": strike_gte, "strike_price_lte": strike_lte,
            "status": status, "limit": limit})

    def option_quotes_latest(self, symbols):
        """Latest NBBO. There is no historical equivalent — capture at the time or lose it."""
        out = {}
        for i in range(0, len(symbols), QUOTE_BATCH):
            d = self.request("GET", DATA_HOST, "/v1beta1/options/quotes/latest",
                             {"symbols": ",".join(symbols[i:i + QUOTE_BATCH])})
            out.update(d.get("quotes") or {})
        return out

    @staticmethod
    def history_end_cap():
        """Latest `end` that historical options endpoints will serve: yesterday, not today."""
        import datetime as _dt
        return (_dt.date.today() - _dt.timedelta(days=1)).isoformat()

    def option_bars(self, symbols, start, end, timeframe="1Day"):
        end = min(end, self.history_end_cap())   # a window including today 403s
        out = {}
        for i in range(0, len(symbols), 100):
            batch = symbols[i:i + 100]
            tok = None
            while True:
                d = self.request("GET", DATA_HOST, "/v1beta1/options/bars",
                                 {"symbols": ",".join(batch), "timeframe": timeframe,
                                  "start": start, "end": end, "limit": 10000, "page_token": tok})
                for s, bars in (d.get("bars") or {}).items():
                    out.setdefault(s, []).extend(bars)
                tok = d.get("next_page_token")
                if not tok:
                    break
        return out

    # ---- orders ----
    def submit_mleg(self, legs, qty, limit_price, tif="day"):
        """Multi-leg order. limit_price is NET: positive = debit, negative = credit."""
        return self.request("POST", self.trade_host, "/v2/orders", body={
            "order_class": "mleg", "qty": str(qty), "type": "limit",
            "limit_price": f"{limit_price:.2f}", "time_in_force": tif, "legs": legs})

    def get_order(self, order_id):
        return self.request("GET", self.trade_host, f"/v2/orders/{order_id}")

    def cancel_order(self, order_id):
        try:
            self.request("DELETE", self.trade_host, f"/v2/orders/{order_id}")
            return True
        except AlpacaError as e:
            return e.status in (404, 422)

    def open_orders(self, limit=100):
        return self.request("GET", self.trade_host, "/v2/orders",
                            {"status": "open", "limit": limit})


def leg(symbol, side, intent, ratio=1):
    return {"symbol": symbol, "ratio_qty": str(ratio), "side": side, "position_intent": intent}
