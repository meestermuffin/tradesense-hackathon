# The signal-gated volatility-premium strategy is shelved

**2026-08-30.** This supersedes every prior description of what this repository trades on.

## What was claimed

> Rank the universe by where each name's implied volatility sits against **its own** trailing
> history. Sell defined-risk premium on the names ranking richest. Ranking on the *absolute* IV
> level is mildly harmful; ranking on the percentile is the signal.

Supported at the time by rank IC **+0.1753** (baseline) and **+0.1561** (earnings-event-free) at a
permutation p of 0.0010, with a control arm at −0.1055.

## What killed it, in order

Three registered runs on 2026-08-27, each committed before it was executed.

**1 · The permutation null was too narrow.** `docs/2026-08-27-block-permutation-registration.md`,
registered `8a45517`. The published null shuffled the signal among names *within* each session,
leaving the time structure of both panels intact — while the outcome is realized volatility over the
next **21 sessions**, so consecutive name-days share 20 of 21 outcome days. Corrected to a
block-constant name permutation, the event-free sample went **p 0.0005 → 0.0660**. Verdict WEAK.

The record had already contained the contradiction: every published row read p 0.0010, the floor,
including the row where Newey–West had fallen to **1.69**. Two statistics on the same data
disagreeing by two orders of magnitude, and nobody reconciled them.

**2 · The cost bound.** `docs/2026-08-27-cost-breakeven-registration.md`, registered `eb86625`.
Gross edge **−8.36%** of premium against a measured round-trip of 55.4% of net credit. That
statistic was then found to price a *naked short* rather than the defined-risk vertical actually
traded, so it is **not** decisive on its own — but under every correct flooring the gross edge was
still negative or indistinguishable from zero **before any cost was charged**.

**3 · It does not replicate.** `docs/2026-08-27-extended-ic-registration.md`, registered `96c85ca`.
Every prior test had used 249 of the 597 sessions committed in `data/`. On the **327 sessions no
test had touched**:

| | IC | NW t(21) | p |
|---|---:|---:|---:|
| anchor · original window *(reproduces exactly)* | +0.1753 | 2.45 | 0.0100 |
| **out-of-sample 2025-03 → 2026-08** | **+0.0414** | **0.72** | **0.2184** |

The anchor reproduces the prior run to four decimals, so this is the same measurement on more data.
The original result rested on ~11 independent windows; 15 fresh ones do not reproduce it.

## What is shelved

**The claim that IV-percentile ranking selects names whose premium is richer than what is
subsequently realized.** Every downstream artifact of that claim goes with it: the signal gate, the
top-N selection, and any assertion of predictive skill in a deck, a video, this repo or a
conversation.

`src/options/signal.py` stays in the tree because the cycle uses it to order candidates and because
deleting it would make the measurement record unreproducible. **It is no longer evidence of
anything.**

## What is NOT shelved — because it was never refuted

Precision matters here; over-shelving discards work that is still sound.

- **The variance risk premium as a market-wide effect.** Never tested here. Unconditional selling was
  not the strategy and has no registered result either way.
- **The defined-risk vertical as a structure.** It was a vehicle for the signal, never independently
  claimed. Its risk properties are measured and stand.
- **Whether cost is payable.** Run 2's statistic was wrong for the structure. Genuinely unresolved.
- **The risk profile.** Mean pairwise correlation **+0.409**, ten positions behaving as **2.14**
  independent bets, and all eleven names falling together on 3, 4 and 10 April 2025. Measured on
  committed data, reproducible, untouched by any of this.
- **The execution findings.** Multi-leg paper fills better than touch; a mid limit resting 26 seconds
  and never filling on the widest book; $0.025 per contract-leg, measured twice.
- **Everything Alpaca.** No IV on this account, `status=inactive` for expired chains, contract
  metadata on the trading host, historical options data excluding the current session, `limit_price`
  as a net price.
- **The infrastructure**, the boundary, the tests, the scheduler.

## The one thing that persisted

Ranking on **raw IV level** was negative in every arm and got more so out-of-sample: −0.1055 →
−0.1425. Ranking a name against its own history stayed above it throughout.

**This has never been tested as a paired comparison and is not a claim.** It is recorded because it
is the only structure in the data that survived extension, and because a future test should start
there rather than rediscover it.

## What would have to be true to revive this

Not a lower bar — a different sample. All of:

1. A pre-registered test on data **not overlapping 2024-03 → 2026-08**, since that window is now
   thoroughly looked at and the universe was selected using information inside it.
2. A universe chosen on information available **before** the test period. The current 11 names were
   picked on 2026 liquidity, which is look-ahead on the universe regardless of the signal.
3. Significance under a **block-constant name permutation** null, `L ≥ H`, with a control arm that
   stays non-significant.
4. An edge statistic that prices the **structure actually traded**, with its loss floor specified
   before the run.

Anything less repeats what has already been done.

## Precedent

The measurement rules in `CLAUDE.md` were "carried from a strategy that was measured, falsified and
shelved." **This is the second.** The first produced those rules; this one produced the correction
to the permutation null, and the discovery that a test can be run on less than half the committed
data without anyone noticing for a week.

Both were caught by their own registrations rather than by review, which is the only part of this
worth being pleased about.
