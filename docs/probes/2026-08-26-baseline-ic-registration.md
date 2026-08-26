# Pre-registration — baseline signal IC, and job 2

**Written 2026-08-26, before either ran.** Committed before execution.

## What is being tested

The strategy's premise is that ranking names by rich implied vol selects names where **IV exceeds
subsequent realized vol** by more than average. That is the variance risk premium, and it is
testable directly on the IV series built today — without simulating a single option trade.

Testing the premise directly is deliberate. An option-P&L backtest would confound the premise with
strike selection, the cost model (still provisional) and fill assumptions. **If the premise has no
evidence, no amount of execution detail rescues it.**

## Data

Eleven universe names — SPY, TSLA, NVDA, MSFT, AAPL, META, AMZN, INTC, GOOGL, AMD, MU — over
2024-03-01 → 2025-02-28, using the v2 `traded` selection rule. Underlying closes from Alpaca daily
bars.

## Statistic

For each session `t`, across the names with a valid signal that day:

```
outcome_t,i = IV_t,i  −  RV_(t → t+21),i        # realized vol, close-to-close, annualized
IC_t        = Spearman rank correlation( signal_t , outcome_t )
```

Reported: **mean IC**, its **Newey–West t-statistic with lag 21**, and an **empirical p-value from a
permutation null**.

**Rank correlation, not linear** — selection acts on ordering, and this project has read +0.0261 and
+0.0011 on identical data from that difference alone.

**Newey–West with lag 21** — consecutive 21-day forward windows share 20 of 21 days. A naive
t-statistic here runs roughly double.

**Permutation null, seed 42, 1000 draws** — the signal is shuffled across names *within* each day,
preserving the cross-sectional distribution and the time structure, destroying only the name↔outcome
link. With only 11 names per day, asymptotic standard errors are not trustworthy on their own, and
the seed is recorded because reseeding alone has previously moved a headline result across most of
its own effect.

## Signal variants — both registered, both reported

| | signal |
|---|---|
| **A** | IV percentile, trailing 126 sessions, minimum 63 valid observations |
| **B** | IV ÷ trailing 21-day realized vol |

**Both are reported whatever they show.** Reporting only the better one would be selection over two
tests, and this document exists partly to make that impossible.

## Decision table — registered in advance, covering every outcome

Today, twice, a registration omitted the outcome that actually occurred. This table is exhaustive
over the sign of the mean IC and the permutation p-value.

| mean IC | permutation p | verdict | what happens |
|---|---|---|---|
| > 0 | ≤ 0.05 | **EVIDENCE** | premise supported; proceed to the option-P&L backtest |
| > 0 | 0.05 – 0.20 | **WEAK** | proceed, but the writeup states the signal is not separable from noise on 12 months |
| > 0 | > 0.20 | **NO EVIDENCE** | premise unsupported. The book still runs — short premium does not require the ranking to work — but **the ranking is described as unvalidated**, not as the edge |
| ≤ 0 | ≤ 0.05 | **CONTRARY** | the ranking selects *against* the premium. Invert or abandon it; do not ship it as-is |
| ≤ 0 | > 0.05 | **NO EVIDENCE** | as above |

**If A and B disagree**, the verdict is the weaker of the two. Two signals disagreeing on the same
data is itself a finding and is reported as one.

**No threshold moves after the run.** If the outcome is uncomfortable, it is reported.

## Job 2 — the earnings test, and why it cannot run today

**Job 2 asks:** does the ranking still separate once earnings-proximate name-days are removed? If
most of the IV-percentile variance is earnings timing, filtering does not protect the strategy — it
deletes it.

**Blocked, and the blocker is stated rather than worked around.** It needs earnings announcement
dates for eleven names across twelve months — roughly 44 announcements. **Alpaca has no earnings
calendar**: the corporate-actions endpoint carries 15 types and none is earnings, confirmed via
`llms.txt` and the endpoint schema. There is no upstream to ingest from, so the dates must be
assembled by hand.

**Registered now so the protocol cannot be written after seeing the result:**

- Same statistic, same variants, same permutation seed.
- Exclusion window: **±2 sessions** around each announcement, matching `earnings_blackout_days = 2`.
- Reported as a **pair**: IC on all name-days, and IC with earnings-proximate name-days removed.

| outcome | verdict |
|---|---|
| IC survives removal within its own confidence interval | the ranking is not merely an earnings detector |
| IC collapses toward zero | **the signal is substantially an earnings-proximity detector**, and a quiet judged window contains none of what the backtest measured |
| IC unavailable — dates never assembled | **job 2 is reported as NOT RUN.** It is not reported as passed, and no claim about earnings independence is made anywhere |

That last row is the one that matters, because it is the outcome an unfinished week produces by
default.

## Known limits, stated before the run

- **Survivorship.** The eleven names were chosen on 2026 liquidity and applied to 2024–25 data. The
  result is optimistic by an unmeasured amount.
- **Eleven names per day** is a thin cross-section; a daily Spearman on 11 points is very noisy, which
  is why the permutation null carries more weight here than the t-statistic.
- **One 12-month window**, containing one particular volatility regime.
- **The IV series carries its own measurement noise** — `|p_c − p_vw|` has a p90 of 8–20 percentile
  points. Roughly a tenth of name-days are print-sensitive, and that noise is inside the signal being
  tested.
- **The 30-DTE reference tenor is not the 5–9 DTE traded tenor.** This tests the regime measure, not
  the contract.
