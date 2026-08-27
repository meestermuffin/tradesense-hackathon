# Alpaca API surface — endpoint reference

Companion to `SKILL.md`. Paths only; parameters live in Alpaca's reference pages, which are fetchable
as markdown by appending `.md` to any docs URL.

**Discovering anything not listed here:**
```bash
curl -s https://docs.alpaca.markets/us/llms.txt | grep -i <topic>
```

## Trading API — `paper-api.alpaca.markets` / `api.alpaca.markets`

| area | path |
|---|---|
| Account | `GET /v2/account` |
| Orders | `GET|POST /v2/orders` · `GET|PATCH|DELETE /v2/orders/{id}` · `DELETE /v2/orders` |
| Positions | `GET /v2/positions` · `GET|DELETE /v2/positions/{symbol}` · `DELETE /v2/positions` |
| Assets | `GET /v2/assets` — `attributes=options_enabled` finds optionable underlyings |
| **Option contracts** | `GET /v2/options/contracts` · `GET /v2/options/contracts/{symbol_or_id}` |
| Option exercise | `POST /v2/positions/{symbol_or_id}/exercise` · do-not-exercise endpoint |
| Account activities | `GET /v2/account/activities` |
| Portfolio history | `GET /v2/account/portfolio/history` |
| Watchlists, calendar, clock | `GET /v2/watchlists` · `/v2/calendar` · `/v2/clock` |

### Order types and classes

`market` · `limit` · `stop` · `stop_limit` · `trailing_stop`
Classes: `simple` · `bracket` · `oco` · `oto` · **`mleg`** (multi-leg options)

Multi-leg legs carry `symbol`, `ratio_qty`, `side`, `position_intent`
(`buy_to_open` / `buy_to_close` / `sell_to_open` / `sell_to_close`).

### Option contract query parameters

`underlying_symbols` · `expiration_date` · `expiration_date_gte` · `expiration_date_lte` ·
`strike_price_gte` · `strike_price_lte` · `type` (call/put) · `style` · `root_symbol` · `limit` ·
`page_token` · **`status`**

Defaults: `expiration_date_lte` = next weekend, `limit` = 100.
**`status=inactive` for expired contracts.** `all` and `expired` silently return nothing.

## Market Data API — `data.alpaca.markets`

### Equities

| data | path |
|---|---|
| Bars | `GET /v2/stocks/bars` · `/v2/stocks/{symbol}/bars` |
| Trades | `GET /v2/stocks/trades` · latest variants |
| Quotes | `GET /v2/stocks/quotes` · latest variants |
| Snapshots | `GET /v2/stocks/snapshots` |
| Auctions | `GET /v2/stocks/auctions` |
| Condition / exchange codes | `GET /v2/stocks/meta/conditions/{ticktype}` · `/v2/stocks/meta/exchanges` |

Feeds: `sip` · `iex` · `otc`. Recent (< 15 min) SIP requires **Algo Trader Plus**; the error is
`subscription does not permit querying recent SIP data`.

### Options — `/v1beta1/options/…`

| data | path | notes |
|---|---|---|
| Historical bars | `GET /v1beta1/options/bars` | OHLCV per contract: `o h l c v vw n` |
| Historical trades | `GET /v1beta1/options/trades` | ticks |
| Latest trades | `GET /v1beta1/options/trades/latest` | |
| Latest quotes | `GET /v1beta1/options/quotes/latest` | `bp bs ap as bx ax t` |
| Snapshots | `GET /v1beta1/options/snapshots/{underlying}` | greeks/IV **only with OPRA** |
| Option chain | `GET /v1beta1/options/chain/{underlying}` | current chain |
| Condition / exchange codes | `GET /v1beta1/options/meta/conditions` · `/meta/exchanges` | |
| ~~Historical quotes~~ | — | **does not exist** |

Feeds: `indicative` (free, 15-min delayed, no greeks) · `opra` (paid, greeks + real-time BBO).

### News

`GET /v1beta1/news` — Benzinga, back to 2015, ~130 articles/day, stocks and crypto in one endpoint.
WebSocket stream available for real-time.

### Corporate actions

`GET /v1/corporate-actions`

## Streaming — `stream.data.alpaca.markets`

WebSocket. Separate streams for equities, options and news. Subscription-gated the same way as REST.

## Broker API — `broker-api.alpaca.markets` (sandbox: `.sandbox.`)

Only relevant if building a brokerage product rather than trading your own account.

| area | path |
|---|---|
| Accounts | `GET|POST /v1/accounts` · `/v1/accounts/{id}` |
| Trading on behalf of | `/v1/trading/accounts/{account_id}/orders` · `/positions` |
| Funding | ACH, wires, journals, funding wallets |
| Documents, KYC, events | `/v1/documents` · `/v1/events/*` (SSE) |
| Auth | OAuth2 client credentials at `authx.alpaca.markets/v1/oauth2/token`, 15-min tokens |

Broker API has its own rate limits, documented separately from the Trading API's.

## SDKs

`alpaca-py` (Python) · `@alpacahq/alpaca-trade-api` (JS) · `alpaca-trade-api-go/v3` (Go) ·
`Alpaca.Markets` (C#)

## MCP server and CLI

- **MCP** — `alpacahq/alpaca-mcp-server`, for LLM-driven interaction with the trading API.
- **CLI** — same trading functions, structured JSON output. Alpaca positions it for *"long-running
  agent sessions, cron jobs and CI, where MCP is heavier than needed."* Prefer it for scheduled work.
