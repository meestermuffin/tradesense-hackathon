# Pre-registration — print-agreement filter

**Written 2026-08-26, before the filter is used in live selection.** Third time this filter has been
acknowledged as needed without being specified: it appears in the universe results, in the structure
proposal, and in `PLAN.md`. Live selection has been running without it. This registers it.

## What it protects against

The IV series inverts from each option bar's **last-trade close**. Inverting the same bar's
**volume-weighted price** gives a second reading of the same day. Where the two produce materially
different percentiles, that day's ranking states which print was used rather than what volatility
did.

Measured across 11 names over 186 usable days: median disagreement **2.38–4.76** percentile points,
p90 **7.94–19.84**, maximum **24.68–54.76**. The median is immaterial. The tail is not.

## The rule

> **Skip a name on a day when `|percentile(last-trade) − percentile(volume-weighted)|` exceeds that
> name's own median day-over-day percentile move.**

**The margin is derived, not chosen.** Above it, the uncertainty about *today* is larger than a
typical day's genuine movement, so the reading carries less information than the noise inside it.
Per-name rather than universe-wide, because both quantities are name-specific.

| name | margin (median \|Δp\|) | median disagreement | days rejected |
|---|---:|---:|---:|
| SPY | 4.91 | 2.38 | 25.3% |
| NVDA | 3.97 | 2.38 | 28.0% |
| TSLA | 5.34 | 2.45 | 28.5% |
| META | 6.35 | 3.97 | 30.1% |
| AAPL | 5.56 | 3.74 | 33.3% |
| AMD | 4.90 | 3.78 | 35.5% |
| AMZN | 4.72 | 3.17 | 35.5% |
| MSFT | 5.11 | 3.97 | 36.6% |
| GOOGL | 5.56 | 3.97 | 39.8% |
| INTC | 4.84 | 3.39 | 41.4% |
| MU | 6.35 | 4.76 | 43.3% |

**Universe mean rejection: 34.3%.**

## The cost, stated because a filter nobody has priced gets switched off

At 34.3%, roughly **7 of 11 names survive on a typical day**. The position cap is **10**. So the
filter, not the risk budget, becomes the binding constraint on book size, and total deployed risk
falls below the 20% the sizing assumes.

That is a real consequence and it is registered rather than discovered later. **Two readings are
legitimate and the choice is the user's:**

1. **Accept it.** A smaller book on days when the data is ambiguous is the behaviour the filter
   exists to produce. Deployed risk falls; that is the price.
2. **Reject the margin as too strict** — but only on a stated argument, not because 34.3% is
   inconvenient. Loosening after seeing the rejection rate is the post-hoc move this project keeps
   catching.

## A better-targeted variant, registered as not-yet-measured

The rule above protects the **number**. What the book actually needs protected is the **decision**.

> Skip only when the two estimators place the name on **opposite sides of the selection cutoff** —
> one inside the top N, the other outside.

If both agree the name ranks 3rd or 9th, the disagreement is irrelevant to what gets traded. This
should reject far less and target exactly the days that matter.

**It is not adopted here because it has not been measured**, and adopting an unmeasured rule because
it promises a nicer rejection rate would be choosing the convenient answer. Measuring it requires the
cross-sectional ranking under both estimators across the series. **If it is measured before Friday it
supersedes the rule above; if not, the rule above is what runs.**

## What would falsify the whole filter

If the powered IC is materially unchanged when computed on rejected days only, the disagreement is
not corrupting the signal and the filter costs 34.3% of the book for nothing. Not yet measured, and
worth measuring before the filter is credited with anything.
