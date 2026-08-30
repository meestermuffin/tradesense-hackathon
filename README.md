# Options volatility-premium agent

A defined-risk options agent, its risk layer, and the measurement record that **falsified its own
trading signal**.

Built for the Alpaca AI Trading Agents Hackathon, 28 Aug – 4 Sep 2026. MIT licensed.

> **The signal this was built on is shelved.** Ranking names by where implied volatility sits
> against their own history read rank IC +0.1753 on the sample it was developed on, and **+0.0414
> (p 0.2184) on 327 sessions no test had touched.** It does not replicate. Full account, including
> what is *not* shelved, in [`docs/2026-08-30-strategy-shelved.md`](docs/2026-08-30-strategy-shelved.md).
>
> **Nothing here claims predictive skill.** What is measured and stands: the risk profile, the
> execution findings, the Alpaca behaviour, and a discipline that caught this before it shipped
> rather than after.

---

## Running it against your own account

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

### Scheduled agents

`make schedule` installs four `launchd` agents: NBBO capture at 15:50, the cycle at 16:05, an equity
snapshot at 16:45, and a heartbeat at 09:00. Installed dry — arming takes
`make schedule LIVE=1 ACCOUNT=<your account>`, and the account is baked into the plist as an
assertion so swapping `.env` without re-installing aborts rather than trading the wrong book.

**Data written by these is namespaced by account** — captures under `data/nbbo/<account>/`,
selection records under `data/selection/<account>/`, and one equity curve per account under
`data/equity/`, each created on first run. Running them alongside someone else's is safe.

**The one thing that is not safe: two machines armed live against the *same* account.** Each sizes
against the same 20% risk budget independently, so the account carries double the intended exposure
while each cycle believes it is within limits. The overlap lock is a file inside the clone and cannot
see across machines — it exists to stop a scheduler retry double-trading on one host, and it gives
no protection here. Use your own account, or make sure only one machine is armed.

They also do not survive sleep. `launchd` does not fire calendar jobs while a machine is asleep; it
fires them late, on wake, which is useless for a job whose value is being inside market hours. An
operating machine needs `sudo pmset repeat wakeorpoweron MTWRF 15:40:00`.

## Layout

```
src/            data boundary, BS inverter, signal, selection, execution, risk
                pydantic models at the edges, no database driver — runs anywhere
src/models.py   every shape that crosses a boundary, in one file
scripts/        measurement runners and the operational jobs
tests/          fakes only — the suite runs on a fresh clone with no keys
docs/           measurement log, cost model
docs/pending/   registrations for measurements that have not run
data/           IV series, earnings dates; captures namespaced by account
ui/             the dashboard — Next.js, credentials server-side only
```

`make` lists every target.

## Setup

[uv](https://docs.astral.sh/uv/) manages the Python side. From a fresh clone:

```bash
uv sync                 # creates .venv from uv.lock — pydantic, plus ruff and pytest for development
make test               # 117 tests, no network and no credentials needed
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
