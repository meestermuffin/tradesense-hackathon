---
name: alpaca
description: Use when calling any Alpaca API — trading, broker, paper or live, market data, OHLCV bars, options chains, greeks, implied volatility, multi-leg orders, news — or when a call returns 404, 401, empty results, "OPRA agreement is not signed", or "subscription does not permit". Also use before estimating an Alpaca-dependent task, or before assuming how paper trading fills orders.
---

# Alpaca

Reference for Alpaca's API surface and the behaviour that is not where you would look for it.

✅ = verified by a live call on the date shown. 📄 = from Alpaca's docs, not re-verified.
Everything else is inference and is marked as such.

**Full API surface:** see [endpoints.md](endpoints.md). This file carries the judgment.

## Two rules this skill exists for

> **1. Alpaca returns different data to different accounts.** Documentation describes endpoints your
> account may not be entitled to. Absent entitlement usually means **missing keys in a 200 response**,
> not an error.
>
> **2. One failed request proves nothing.** A 404 on one path, one symbol, or one date is not
> evidence that a capability is absent.

Both were violated on 2026-08-25 within an hour.

## Hosts and credentials

📄 Credentials are **not** interchangeable across environments. A data key on the trading API returns
`401 {"code": 40110000}`.

| host | purpose |
|---|---|
| `api.alpaca.markets` | live trading |
| `paper-api.alpaca.markets` | paper trading — **and options contract metadata** |
| `data.alpaca.markets` | market data, both environments |
| `stream.data.alpaca.markets` | streaming market data |
| `broker-api.alpaca.markets` · `.sandbox.` | Broker API |
| `authx.alpaca.markets` | OAuth2 tokens (Broker API) |

**Auth:** legacy `APCA-API-KEY-ID` / `APCA-API-SECRET-KEY` headers, or HTTP Basic (key as username).
OAuth2 client-credentials exists on `authx` with 15-minute tokens, but 📄 *"not yet available for
Trading API."*

**Contract metadata lives on the trading host**, not the data host — easy to miss when everything
else options-related is under `data`.

## Paper trading: how fills actually work

📄 The paper spec answers this directly, and it is the opposite of the common assumption:

> *"Orders are filled only when they become **marketable**. A non-marketable buy limit order will not
> be filled until its limit price is **equal to or greater than the best ask**, and a non-marketable
> sell limit order will not be filled until its limit price is **equal to or less than the best
> bid**."*

**That is the documented behaviour. ✅ 2026-08-26 it was measured, and for multi-leg options it is
false.** One SPY 755/750 put credit spread, 7 DTE, 1 lot, NBBO captured at submission:

| | net at touch | net at mid | **fill** | vs mid | latency |
|---|---|---|---|---|---|
| entry | 0.580 cr | 0.610 cr | **0.620 cr** | **+0.010** | 127 ms |
| exit | 0.730 db | 0.675 db | **0.670 db** | **+0.005** | 5.4 s |

**Multi-leg paper fills get price improvement — better than mid on both sides**, on both legs
individually. Charging touch-to-touch would have cost **0.150** round trip against a measured
**+0.015**: a 0.165 gap on a 0.61 credit, **27% of the premium**.

**A second round trip on a wide book (AMD, legs 14–66¢) did not reproduce it** — ✅ 2026-08-26:

| | limit at mid | outcome |
|---|---|---|
| entry | −1.85 (mid 1.845) | filled **at the limit** after ~20 s — no improvement |
| exit | 1.78 (mid 1.985) | **never filled**; rested 26 s, cancelled |
| exit, marketable | 2.47 (0.10 through touch) | filled **2.30** — 0.07 better than touch, **0.315 worse than mid**, 14 ms |

**So the general rule is weaker than "fills at mid": fills clear better than the touch, by a small
absolute amount that does not scale with spread width.** On 3¢ legs that beats the half-spread and
execution earns; on 14–66¢ legs it does not and execution costs. **Any cost model fitted on SPY alone
will be wrong for every wider name.** Mid-priced orders on a wide book may not fill at all — the
engine enforces marketability rather than filling indiscriminately.

**Fees:** ✅ **$0.025 per contract-leg**, reproduced exactly across two round trips of very different
notional (residual −0.10 on both, 4 legs each). `accrued_fees` and `pending_reg_taf_fees` report **0**
regardless — the charge is real but not surfaced there.

📄 What paper does **not** model:

| not simulated | consequence |
|---|---|
| Market impact · information leakage | large orders look free |
| **Price slippage due to latency** | fills are instantaneous at the quote |
| Order queue position | non-marketable limits behave optimistically |
| Price improvement | no better-than-quote fills |
| Regulatory fees · dividends | P&L excludes both |
| **Order size vs NBBO quantity** | *"you can submit and receive a fill for an order much larger than the actual available liquidity"* |

📄 Also: eligible orders receive **random partial fills 10% of the time**; no fill emails; a
Paper-Only account is entitled to **IEX data only**.

**Still measure it.** The spec is general paper trading; options multi-leg behaviour is not stated.
Place one order, capture the NBBO at submission, compare. Docs describe intent; the fill is the fact.

📄 Paper accounts default to **$100k**, and you can **create and delete multiple** from the dashboard
— useful for isolating experiments whose fills would otherwise pollute a P&L you care about.

## Options

### Approval levels — spreads need Level 3

📄

| level | permits |
|---|---|
| 0 | disabled |
| 1 | sell covered call · sell cash-secured put |
| 2 | level 1 + buy call · buy put |
| **3** | levels 1–2 + **buy call spread · buy put spread** |

**"Options approved" is true at every level above 0.** Read `options_approved_level` off the account
rather than inferring it. Note the table names *buying* spreads; if your strategy **sells** them,
confirm against the account instead of assuming Level 3 covers it.

### Multi-leg orders

📄 `POST /v2/orders` with `order_class: "mleg"`. Legs fill together or not at all.

```json
{
  "order_class": "mleg", "qty": "1", "type": "limit",
  "limit_price": "1.00", "time_in_force": "day",
  "legs": [
    {"symbol": "AAPL250117C00190000", "ratio_qty": "1", "side": "buy",  "position_intent": "buy_to_open"},
    {"symbol": "AAPL250117C00210000", "ratio_qty": "1", "side": "sell", "position_intent": "sell_to_open"}
  ]
}
```

**Limit orders let you choose the price**, which changes the fill question: you are not accepting
whatever the simulator offers.

### Chain discovery, including expired contracts

📄 `GET /v2/options/contracts` defaults to `expiration_date_lte = next weekend`, `limit = 100`. That
is why past expiries return an empty list rather than an error.

✅ **2026-08-25** — for historical chains, `status=inactive`:

| `status=` | result |
|---|---|
| *(omitted)* | active only — **0 rows for any past expiry** |
| `inactive` | ✅ **416 contracts** for the 2024-03-15 SPY expiry, strikes 195–660 |
| `all` · `expired` | ❌ 0 rows — the intuitive guesses both fail silently |

📄 To find optionable underlyings: the Assets endpoint exposes an `options_enabled` attribute.

### There is no historical quote data

✅ **2026-08-25**, confirmed three ways — 404 on a live contract, 404 on an expired one, and absent
from Alpaca's own endpoint index, which lists *Historical bars*, *Historical trades*, and separately
*Latest quotes*.

**Any backtest charging bid/ask on options has no data to charge against.** Cost must be estimated —
from trade prices, or from a forward-captured spread model.

### Greeks and IV are OPRA-gated

✅ `?feed=opra` → `{"message": "OPRA agreement is not signed"}`. On an unentitled account, `greeks`
and `impliedVolatility` are **absent from the 200 response** — no error. The free `indicative` feed
carries quotes, 15-minute delayed, no greeks.

So IV is usually **computed**, not read: option price from bars, underlying price, strike/expiry/right
from the OCC symbol, plus a rate.

**Do not sign OPRA to fix a historical gap.** It supplies greeks going *forward* only; history still
needs inversion, leaving two different IV definitions and comparisons that measure method as well as
outcome.

### Data floor and sparsity

📄 Docs say option data exists *"since February 2024."*
✅ Measured: SPY contracts expiring 2024-02-16 and 2024-03-15 **both** return a first bar of
**2024-01-18**. Two expiries sharing one first date indicates a data floor, not a listing date.
**Only SPY was tested** — record the actual first bar per symbol at ingest.

✅ Bars on illiquid strikes are extremely thin:

```
2024-03-01  n:1   v:40   c:314.14     ← one trade all day
2024-03-04  n:1   v:1    c:318.51     ← one trade, one contract
2024-03-05  n:110 v:270  c:312.85
```

`n` is the trade count. `n:1` is **one trade at an unknown intraday time** — pairing it with a 16:00
underlying close is non-synchronous by construction. Filter on moneyness and on `n`.

## Equities and news

✅ **Options quotes are real-time, not delayed** — 2026-08-26, `options/quotes/latest` lagged wall
clock by 1.43 s / −0.06 s / 0.11 s over three samples on a paper account. The docs' 15-minute
indicative delay did not appear. Check this before trusting any mid-based benchmark: if the feed were
delayed, every "fill vs mid" comparison would be against a 15-minute-old number.

⚠️ **Equity quotes on a paper account are IEX-only and can be very wide** — AMD showed a **481.83 /
490** stock NBBO mid-session. Do not use `stocks/*/quotes/latest` as a spot price for option
calculations; take spot from the option chain or from bars.

📄 **Feeds:** SIP (all US exchanges) vs IEX (free, single venue). Querying SIP trades or quotes from
**the last 15 minutes requires an Algo Trader Plus subscription**; older data is available on all
feeds. The error is `subscription does not permit querying recent SIP data`.

### There is no earnings calendar

✅ **2026-08-25.** Corporate actions is the endpoint people reach for, and it does not carry earnings.
Its 15 CA types are cash/stock dividends, forward/reverse splits, the three merger shapes, spin-offs,
redemptions, name changes, rights distributions, unit splits and worthless removals. **No earnings,
no announcement dates.**

Confirmed two ways: absent from `llms.txt`, and absent from the type taxonomy in the endpoint's own
schema. The deprecated `/v2/corporate_actions/announcements` paths redirect to the same endpoint, so
they carry the same types — a deprecation notice is not a different data set.

**Earnings dates come from outside Alpaca**, or they are hardcoded from IR announcements.

📄 **News:** provided by Benzinga, back to **2015**, ~130 articles/day, one endpoint covering stocks
and crypto, plus a WebSocket stream.

## Verification recipe

Run before building on any capability, and **read the body, not the status**:

```bash
H=(-H "APCA-API-KEY-ID: $K" -H "APCA-API-SECRET-KEY: $S")
for u in \
  "https://data.alpaca.markets/v1beta1/options/snapshots/SPY?limit=1" \
  "https://data.alpaca.markets/v1beta1/options/snapshots/SPY?limit=1&feed=opra" \
  "https://paper-api.alpaca.markets/v2/account" ; do
  printf "%s  %s\n" "$(curl -s -o /tmp/o -w '%{http_code}' --max-time 20 "${H[@]}" "$u")" "${u%%\?*}"
  head -c 200 /tmp/o; echo
done
```

A 200 with `{"snapshots":{}}`, or one missing `greeks`, is a failure wearing a success code.

## Common mistakes

| mistake | why | fix |
|---|---|---|
| "IV ships in the snapshot" | docs say so; gating is documented elsewhere | check for the `greeks` key in a real response |
| "Endpoint X doesn't exist" after one 404 | single probe | test live *and* expired symbols, then check `llms.txt` |
| "Data starts on \<date\>" | reading your own `start=` as a data boundary | query from well before the suspected floor, read the **first returned** timestamp |
| Empty chain for a past date | `status` defaults to active | `status=inactive` |
| `401` on contract metadata | used the data key | contract metadata is on the **trading** host |
| "Paper fills at the touch" | it's in the spec | ✅ measured **better than mid** for mleg — the spec does not describe multi-leg |
| "Options approved, so we can trade spreads" | true at any level > 0 | read `options_approved_level` |
| Estimating options work in hours | pricing the maths, not the data assembly | chain discovery, contract selection and filtering dominate |
| "Pull earnings from corporate actions" | CA sounds like it covers announcements | it carries 15 types, none of them earnings — source the calendar elsewhere |

## Red flags

- About to write "the API provides…" without having seen a response body
- Quoting the paper-trading spec's fill rule as though it covered multi-leg options
- About to write "X is unavailable" after one request
- Quoting a date boundary equal to a parameter you chose
- A 200 response you did not read
- An estimate that prices the calculation but not the plumbing

## Discovering the rest

```bash
curl -s https://docs.alpaca.markets/us/llms.txt | grep -i <topic>
```

372 entries. Any page takes `.md` appended for a clean markdown version — cheaper to fetch and read
than the rendered page.
