# Defined-risk options agent

Sells short-premium iron condors on SPY, with a model in the loop that can veto any entry and a
risk layer that can veto the model.

Built for the Alpaca AI Trading Agents Hackathon, 28 Aug – 4 Sep 2026. MIT licensed.

We set out to trade a volatility-premium signal: rank names by where implied volatility sits
against their own history, sell the richest. On the sample we developed it on it looked good, with
a rank information coefficient of +0.1753 and a control arm on raw IV level reading −0.1055.

Late in development we found that every test had been run against 249 of the 597 sessions committed
to this repository. On the remaining 327, which no test had touched, the same measurement reads
+0.0414 with a p-value of 0.2184. Significant in sample, absent out of sample. We shelved it and
wrote down what had happened, including the parts that survive, in
[`docs/2026-08-30-strategy-shelved.md`](docs/2026-08-30-strategy-shelved.md).

What trades in its place makes no prediction. It is a ladder of defined-risk iron condors on SPY,
sold short-premium and held to expiry, which profits from the passage of time rather than from
knowing where the underlying is going. The payoff shape is structural. The profitability is not,
and we are careful to separate the two below.

The interesting result is not the strategy but the review layer. A language model sits between the
plan and the order, and its authority is deliberately one-directional: it may refuse an entry, or
tighten the short delta within a registered band, and it can do nothing else. It cannot express a
price, because the field is absent from the schema it writes. Approval is not sufficient, since
eleven deterministic guardrails run afterwards regardless. Every failure path resolves to a
refusal, so a bad response from the model costs a trade and cannot cause one.

On its first live run it refused a trade, and it was right for a reason we had not anticipated. It
observed that both short deltas had been computed from a single flat implied volatility, which made
a put and a call at unequal distance from spot report near-identical deltas of 0.197 and 0.198.
Inverting each strike against its own quote gave true deltas of 0.221 and 0.171. The guardrail
responsible for keeping short deltas inside a band had therefore been validating a figure that did
not describe the position it was protecting. We had written that guardrail, tested it, and watched
it pass. A rules engine could not have caught the error, because the rule was checking the wrong
number rather than checking it wrongly.

We make no claim to predictive skill, and quote no backtest anywhere in this repository, since the
only one we produced was falsified. What we do claim is narrower: that the execution findings are
measured rather than assumed, that the risk layer refuses what it says it refuses, and that the
discipline which caught our own signal failing is the same discipline that caught the guardrail
defect. Both were found before they cost anything.

**Live snapshot:** <https://meestermuffin.github.io/tradesense-hackathon/> — equity, every
structure submitted, and each leg fill against the NBBO captured at submission. It is a **static
page** built by `scripts/build_site.py` and committed; it calls no broker and holds no credentials,
so it is only as current as its last build. The build timestamp is on the page.

---

## What actually trades

Not the shelved signal. A short-premium ladder of defined-risk SPY iron condors.

**The payoff shape is structural; the profitability is not.** A condor is theta-positive and its
loss is bounded and requires a move — both true by construction. But selling premium is
compensation for gamma risk, and it pays only while implied volatility runs above what is
subsequently realized. If the two are equal the expected value is zero before costs and negative
after.

On the entry days implied did run richer — 2-DTE ATM implied 0.126 against realized of 0.065 (5d),
0.077 (10d) and 0.103 (21d). That is a hint, not a measurement: close-to-close understates
intraday range, and a 2-DTE implied is not cleanly comparable to 21-day realized. It is stated as
the hypothesis it is, and it is the reason this is not presented as an edge.

```bash
uv run python scripts/run_agent.py                       # dry run, today's session
uv run python scripts/fill_probe.py --expect-account PA...  # the registered 1-lot fill probe
uv run python scripts/pin_check.py                       # expiry-day assignment risk; reports only
```

The model reviews every tranche and may refuse one, or tighten the short delta inside a registered band. 
It cannot express a price — the field is absent from the schema it writes — and approving is not sufficient, because eleven deterministic guardrails run afterwards regardless. Every failure path resolves to a refusal:
unparseable output, a timeout, an empty reason. **A bad model response costs a trade and cannot
cause one.

On its first live run it refused a trade and was right: it caught that both short deltas were
computed from a single flat implied vol, so the delta guardrail was validating numbers that did not
describe the position (true deltas 0.221/0.171 against a reported 0.197/0.198). The strikes are now
solved on the skew surface.

`run_agent.py --live` refuses unless the markwatch collector is capturing, and refuses again unless
a fill-probe verdict says four-leg orders clear at a single mid limit on this venue. There is no
historical options quote endpoint here, so a fill placed before the collector starts can never be
reconciled against the NBBO it crossed.

## Running the shelved path against your own account

Everything below works on your own Alpaca paper account. Nothing you write can collide with anyone
else's data — every artifact is namespaced by account number.

```bash
cp .env.sample .env      # your own paper credentials
make verify              # does this account have what the project needs?
make status              # scheduler, wake schedule, account, last session
make cycle               # rank, select, size — DRY RUN, places nothing
```

**Run `make verify` first.** Entitlements are per-account, not per-user, and the failure mode is a
200 response with keys quietly missing rather than an error. It checks the five things this depends
on, of which `options/bars` on expired contracts is load-bearing — without it the IV series cannot
be rebuilt at all.

`make cycle` is always a dry run. Real orders need `make cycle-live CONFIRM=i-mean-it`, which prints
which account the credentials resolve to before refusing, because a key pair does not announce which
account it belongs to.

### Dashboard

```bash
make server        # http://localhost:3100
```

Account, orders and the equity curve for whichever account `.env` points at. Credentials are read
server-side in route handlers and never reach the browser; the page fetches from its own `/api`
routes.

The equity curve reads the committed per-session file rather than querying Alpaca, because that file
is written by a job kept independent of the trading cycle and therefore has no gaps when a cycle is
skipped — Sharpe and max drawdown are computed from consecutive daily returns, so a gap distorts
both.

It does not display Sharpe. Over a handful of sessions that number cannot separate skill from luck,
and showing one would imply a precision the sample does not support.

## Layout

```
src/            data boundary, BS inverter, signal, selection, execution, risk
                pydantic models at the edges, no database driver — runs anywhere
src/models.py   every shape that crosses a boundary, in one file
src/agent/      the trading agent: loop, model reviewer, MCP toolsets, collector supervisor
src/options/    condor construction, guardrails, IV inversion, chain assembly
scripts/        measurement runners and the operational jobs
markwatch/      Mark-quality instrumentation — samples the book every 60s and
                values it three ways: broker, mid, and what closing now would realise
tests/          fakes only — the suite runs on a fresh clone with no keys
docs/           measurement log, cost model — and the published dashboard (Pages root)
docs/pending/   registrations for measurements that have not run
data/           IV series, earnings dates; captures namespaced by account
data/probe/     fill-probe verdicts; `run_agent.py --live` gates on these
ui/             the local dashboard — Next.js, credentials server-side only
```

`make` lists every target.

## Setup

[uv](https://docs.astral.sh/uv/) manages the Python side. From a fresh clone:

```bash
uv sync                 # creates .venv from uv.lock — pydantic, plus ruff and pytest for development
make test               # 400 tests, no network and no credentials needed
make verify             # confirms your Alpaca account has the entitlements the project needs
make cycle              # dry run: rank, select, size. Places nothing.
```

Every `make` target runs through `uv run`, so there is no virtualenv to activate. To run a script
directly, prefix it: `uv run python scripts/heartbeat.py`.

Credentials come from a gitignored `.env` at the repo root (`ALPACA_KEY_ID`, `ALPACA_SECRET_KEY`),
which is also where the scheduled jobs read them — `launchd` gives a job almost no environment.

## Tests

`make test`. Everything runs against fakes, because a test needing a live account can only be run
by the one person holding the keys, which in practice means it is not run.

They are weighted toward the things that fail quietly rather than loudly:

- **The ranking cannot see its own outcome.** The scored day is excluded from the window it is
  ranked against, proven by computing that window independently and requiring exact agreement.
  This project has already published an IC of 0.16 where the outcome and both signals were
  functions of the same term.
- **The sign conventions on `limit_price`.** Net price, negative for a credit. Inverting it does
  not raise — it places a real order at the wrong price.
- **Newey-West against a naive t on overlapping windows**, pinned at the measured values: naive
  1.671, corrected 0.815 at lag 21.
- **The permutation test is calibrated**, checked across 40 independent nulls rather than one.
  A single null draw here reads p 0.02, which is exactly why one draw proves nothing.

## Dependencies

Runtime: **pydantic**, and nothing else. It parses Alpaca responses at the boundary, which matters
here because the recurring failure on this API is a *missing key in an otherwise-200 response* —
`greeks` and `impliedVolatility` are simply absent without an OPRA agreement, and a plain dict
answers `.get()` with `None` and lets the run continue on a number that was never served.

`src/` was standard-library-only until 2026-08-26. That bought a clone-and-run repo and cost
validation at the one place it earns its keep. No database driver, still — that rule is unchanged.

Development: `ruff` for lint and formatting, pinned in `uv.lock` and run via `make lint` / `make fmt`.
