# CLAUDE.md

Options volatility-premium trading agent, built for the Alpaca AI Trading Agents Hackathon
(28 Aug – 4 Sep 2026). **This repository is public and MIT-licensed.**

## Read first

`.claude/private/PLAN.md` is the working plan — build tracks, dated timeline, decisions and their
reasoning. It is **gitignored** and stays that way; it carries strategy detail that does not belong
in a public repo. Read it before starting work.

`docs/measurement-log.md` is the results record: what was measured, what it returned, what was
voided. Registrations for measurements that have not run yet are in `docs/pending/`.

## Setup

`uv` manages the Python side; every `make` target runs through `uv run`, so there is no virtualenv
to activate. `make` lists the targets. `make test` runs the suite — fakes only, no network and no
credentials, so it works on a fresh clone.

**Runtime dependency: pydantic, and nothing else.** It parses Alpaca responses at the boundary,
because the recurring failure on this API is a *missing key in an otherwise-200 response* and a
plain dict answers `.get()` with `None` and lets the run continue. Adding a second runtime
dependency needs a reason written into `pyproject.toml` next to the first.

**Nothing anywhere may import a database driver.** That rule is unchanged and it is about what
teammates and judges can run.

Credentials live in a gitignored `.env` at the repo root (`ALPACA_KEY_ID`, `ALPACA_SECRET_KEY`),
which is also where the scheduled jobs read them — `launchd` gives a job almost no environment.

## Data

Everything runs from what is committed in `data/`: the IV series as gzipped CSV, earnings dates,
NBBO captures and selection records namespaced by account. No credentials are needed to reproduce
any measurement, which is what makes the results checkable by anyone who clones this.

`src/data/source.py` defines the boundary and **`FileFeatureSource` is its only implementation.**
A second one was planned to abstract historical option quotes; those do not exist, Alpaca serves
none and this project measured that directly. So the live path uses `AlpacaClient` and bypasses the
interface deliberately, rather than wrapping a client in an abstraction over nothing. Do not add
the second implementation back without a reason that survives that finding.

There is a private project on one machine holding six years of market data and a
training/backtesting stack. **Nothing here reads it.** That is a decision, not an omission — a
dependency on containers running on one laptop is exactly what the file-backed path exists to
avoid.

## Alpaca

Use the `alpaca` skill before any API work. It carries endpoint facts verified by live calls and two
failure modes that keep recurring here: trusting the docs about entitlements, and concluding a
capability is absent from one failed request.

The ones that have already cost time:

- **No implied volatility on this account.** Snapshots return `latestQuote` only; `feed=opra` returns
  `"OPRA agreement is not signed"`. IV is **computed** by Black-Scholes inversion, not read.
- **Expired chains need `status=inactive`.** `all` and `expired` return an empty list with no error,
  and omitting `status` defaults to next weekend's expiries.
- **Contract metadata is on the trading host**, not the data host. A data key there returns `401`.
- **Historical options data excludes the current session.** A window ending today returns 403;
  ending yesterday returns 200. So a live signal takes its history from bars and today's
  observation from `quotes/latest`. That seam is real and is recorded on every reading.
- **`limit_price` on a multi-leg order is a NET price** — negative is a credit. Inverting it does
  not raise. It places a real order at the wrong price.

## Measurement rules

Carried from a strategy that was measured, falsified and shelved. Each cost a wrong headline number
to learn. The first three are now also enforced in `tests/`:

- **Overlapping windows inflate significance.** Consecutive 5-day forecasts share four days, so a
  naive t-statistic runs roughly double. Use Newey-West.
- **Rank correlation, not linear.** Selection acts on ordering. The two have read +0.0261 and +0.0011
  on identical data here.
- **Record the random seed.** Reseeding alone moved a headline result across most of its own effect.
- **Check the statistic shares no term with its outcome.** A registered IC of 0.16 was voided
  because the outcome and both signals were functions of the same `IV_t`.
- **Commit the measurement script before running it.** One earlier result is permanently
  unreproducible because this was not done.
- **Write the validation plan before the run**, not after seeing the result.
- **Ask of every statistic: could a live system have known this on that date?**

`scripts/iv_series_probe.py` is **frozen** — byte-identical, excluded from formatting. Two committed
registrations name that file and its commit as the definition of how the IV series was built.

## Public repo hygiene

- **No credentials, ever.** `.env` is gitignored; nothing else holds a key.
- **The universe is selection-biased** — 11 names chosen on 2026 liquidity, applied to 2024–25 data.
  Stated in `docs/measurement-log.md`; results computed on it are optimistic. `src/universe.py`
  enforces its own exclusions at import, so a name cannot be quietly re-admitted by an edit.
- **No backtest number gets quoted** — deck, video or repo — until the cost model exists and is
  written down. There is no historical option quote data to charge against, so cost must be
  estimated. An uncosted result is the one figure a judge can take apart.
- Check dependency licences before adding them. MIT compliance is a stated submission requirement.

## Conventions

Prefer absolute paths and `make -C` over `cd`.
