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

---

# Addendum — the registered statistic is mechanically inflated

**Written 2026-08-26 after the first run, before the corrected run.** The original protocol's result
(A: IC 0.1645, t 2.24, p 0.001 · B: IC 0.2359, t 3.39, p 0.001 — both **EVIDENCE**) is **recorded and
then set aside**, for a defect in the statistic rather than in the data.

## The defect

`outcome = IV_t − RV_forward`, and both signals are functions of `IV_t`. **`IV_t` enters both sides
with a positive sign.** A high-IV name scores high on the signal and high on the outcome for
arithmetic reasons, independent of whether any variance premium is harvested. If IV were pure noise
and RV constant, this statistic would approach IC = 1 for a signal with no economic content.

This is falsification item 4 — *the statistic must match the deployed objective* — failed inside a
registration written to be exhaustive over outcomes. **The original verdict is void, not weakened.**

## What the deployed objective actually is

Selling a spread collects premium proportional to `IV_t` and pays out against `RV_forward`. The
**return on premium sold** is therefore approximately

```
outcome_normalised = (IV_t − RV_forward) / IV_t
```

which is scale-free in `IV_t`. Ranking should select name-days where a *larger fraction* of the
premium sold is retained — not merely name-days where more premium is sold.

## Corrected protocol — registered before the run

Unchanged: universe, period, horizon 21, Newey–West lag 21, permutation seed 42, 1000 draws,
within-day shuffle, both signal variants reported.

**Changed: the outcome is `(IV_t − RV_forward) / IV_t`.**

**Added: a control arm.** Signal **C = raw `IV_t` level**, no percentile, no normalisation against the
name's own history. C is not a strategy — it is a measurement of how much of any IC is available from
the IV level alone.

### Reading, registered in advance

| condition | consequence |
|---|---|
| A and B materially exceed C | the *ranking against a name's own history* is doing work beyond the IV level. This is the claim the strategy makes |
| A and B ≈ C | the percentile machinery adds nothing over "sell whatever has the highest IV right now". **The signal as designed is not justified**, even if IC is positive |
| C exceeds A and B | the percentile machinery is actively destroying information |

Verdicts use the same decision table as the original protocol, applied to the normalised outcome, and
the reported verdict remains **the weaker of A and B**.

**The original run stays in the record.** It is what the registration asked for, it is what the
protocol produced, and deleting it would hide that the protocol was wrong rather than the world
surprising.

---

# Addendum 2 — job 2 is unblocked, and one judgement registered before the run

**Written 2026-08-26, before job 2 ran.**

## The dates come from a primary source

`data/earnings_8k_2024_2025.json` — **SEC 8-K filings carrying Item 2.02 (Results of Operations)**,
pulled from EDGAR's submissions API. The filing date *is* the announcement date. This is not an
aggregator, and it replaces the hand-assembly the original registration assumed would be needed.

**67 announcements across the ten single-name underlyings.** SPY returns zero, correctly — it is an
ETF and has no earnings, which is a useful check that the extraction is doing what it claims.

## The judgement call, registered rather than resolved after the fact

**TSLA returns 12 filings where every other name returns 6.** The extra six are quarterly
**production and delivery** reports, filed under the same Item 2.02 because they are results of
operations. They are not earnings — but they *are* scheduled, binary, pre-announced events with an
implied-vol run-up, which is precisely the mechanism job 2 exists to detect.

**Registered decision:** the primary run uses **all Item 2.02 filings**, because the hypothesis under
test is "the ranking is a scheduled-binary-event detector", not "the ranking is an earnings detector",
and delivery reports are scheduled binary events.

**A sensitivity is reported alongside it** with TSLA's six delivery dates removed. If the two
readings differ materially, that difference is reported as a finding rather than resolved by picking
one.

## Everything else unchanged

Exclusion window **±2 sessions** around each announcement, matching `earnings_blackout_days = 2`.
Corrected outcome `(IV − RV_fwd)/IV`. Variants A, B and control C. Newey–West lag 21. Permutation
seed 42, 1000 draws, within-day shuffle.

**B remains confounded** — trailing and forward realized vol rank-correlate at +0.8166 on this data,
so B and its outcome collapse toward a deterministic pair. B is reported and is not evidence. **The
job-2 verdict rests on A**, read against control C.

## Reading, registered in advance

| outcome | verdict |
|---|---|
| A's IC survives removal, within its own permutation interval | the ranking is **not** merely a scheduled-event detector |
| A's IC collapses toward zero | **the ranking is substantially a scheduled-event detector.** A quiet judged window contains none of what the measurement rewarded, and live underperformance would not mean the strategy broke |
| A's IC *rises* on removal | events were adding noise, not signal; the exclusion filter earns its place on evidence rather than on caution |
