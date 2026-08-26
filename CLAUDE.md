# CLAUDE.md

Options volatility-premium trading agent, built for the Alpaca AI Trading Agents Hackathon
(28 Aug – 4 Sep 2026). **This repository is public and MIT-licensed.**

## Read first

`.claude/private/PLAN.md` is the working plan — build tracks, dated timeline, decisions and their
reasoning. It is **gitignored** and stays that way; it carries strategy detail that does not belong
in a public repo. Read it before starting work.

## The pipeline next door

This repo is built **alongside** an existing private project, not inside it. That project holds six
years of market data and a training/backtesting stack. Nothing here modifies it.

**Not everyone has it.** One machine runs those containers; everyone else works from the parquet
committed in `data/`. Which path you are on is discoverable, not something to assume:

```bash
docker ps --format '{{.Names}}' | grep -q clerk_timescaledb \
  && echo "pipeline present — TimescaleFeatureSource available" \
  || echo "no pipeline — use FileFeatureSource, everything still runs"
```

Set `TRADESENSE_PIPELINE=/path/to/trade-sense` if the neighbouring checkout lives somewhere other
than the default. Nothing in this repo should hardcode a path to it.

All data access goes through **one interface** in `src/data/` with two implementations:

| implementation | reads | used by |
|---|---|---|
| `TimescaleFeatureSource` | the running containers, localhost | local dev, the judged run |
| `FileFeatureSource` | parquet committed in `data/` | teammates, judges, anyone cloning |

```
localhost:5434   clerk_dev     ohlcv_daily          open/high/low/close/volume
localhost:5436   forge_dev     feature_vectors_1d   computed indicators
localhost:5437   trader_dev    orders, positions    execution state
```

**Both of the first two are needed.** Computed features live in one; open, high and low exist only
in the other, and the volatility estimators need them.

**Nothing in `model/`, `options/` or `measurement/` may import a database driver.** Teammates cannot
reach those containers — they run on one laptop. The file implementation is what makes the repo
runnable by anyone who clones it, and that includes the judges.

## Alpaca

Use the `alpaca` skill before any API work. It carries endpoint facts verified by live calls and two
failure modes that keep recurring here: trusting the docs about entitlements, and concluding a
capability is absent from one failed request.

The three that have already cost time:

- **No implied volatility on this account.** Snapshots return `latestQuote` only; `feed=opra` returns
  `"OPRA agreement is not signed"`. IV is **computed** by Black-Scholes inversion, not read.
- **Expired chains need `status=inactive`.** `all` and `expired` return an empty list with no error,
  and omitting `status` defaults to next weekend's expiries.
- **Contract metadata is on the trading host**, not the data host. A data key there returns `401`.

## Measurement rules

Carried from a strategy that was measured, falsified and shelved. Each cost a wrong headline number
to learn:

- **Overlapping windows inflate significance.** Consecutive 5-day forecasts share four days, so a
  naive t-statistic runs roughly double. Use Newey-West.
- **Rank correlation, not linear.** Selection acts on ordering. The two have read +0.0261 and +0.0011
  on identical data here.
- **Record the random seed.** Reseeding alone moved a headline result across most of its own effect.
- **Commit the measurement script before running it.** One earlier result is permanently
  unreproducible because this was not done.
- **Write the validation plan before the run**, not after seeing the result.
- **Ask of every statistic: could a live system have known this on that date?**

## Public repo hygiene

- **No credentials, ever.** Config goes in `*.config.yml` (gitignored); commit `*.config.sample.yml`.
- **The bundled data is survivorship-biased** — today's index membership applied back to 2020.
  Say so in `data/` and in the measurement protocol. Results computed on it are optimistic.
- **No leg-2 backtest number gets quoted** — deck, video or repo — until the cost model exists and is
  written down. There is no historical option quote data to charge against, so cost must be
  estimated. An uncosted result is the one figure a judge can take apart.
- Check dependency licences before adding them. MIT compliance is a stated submission requirement.

## Conventions

Prefer absolute paths and `go -C` / `make -C` over `cd`.
