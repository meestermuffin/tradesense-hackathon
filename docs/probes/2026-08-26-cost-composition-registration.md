# Pre-registration — how cost is charged in the delta sweep

**Written 2026-08-26, before any sweep runs.** Review found the sweep's cost line contradicted the
registered cost model without saying so (C11, REFUTED). This pins the composition.

## The contradiction being resolved

`docs/cost-model.md` registers **0.82 × half-quoted spread, charged on every fill, always** —
deliberately conservative, because patient fills were sometimes free and charging as if every order
crossed can only understate live performance.

The sweep proposal then said "Roll-estimated effective spread". Roll measures the **effective**
spread, roughly 0.51× quoted on the one session measured. Charging that directly **halves the
registered charge** and silently abandons the conservative rule, using the market's patient-flow
average for a book whose measured execution is marketable.

## Registered composition

**Keep the conservative rule.** Roll is used to estimate the *quoted* spread, and the registered
marketable charge is applied to it:

```
quoted_est   = roll_effective / ratio
cost_per_leg = 0.82 × quoted_est / 2
```

With `ratio = 0.51`, that reduces to **≈ 0.80 × roll_effective per leg**. Fees are added separately
at **$0.025 per contract-leg**, measured exactly twice.

## The ratio is not a point estimate and is not treated as one

Measured on one session across 11 names, the Roll-to-quoted ratio ranged **0.32 to 0.87**, median
≈ 0.51. A single day is not a calibration.

**Every sweep result is reported at three ratios — 0.32, 0.51, 0.87 — as a sensitivity band, never
as a point estimate.** If the ranking of delta arms changes across that band, the sweep has not
answered the question and must say so.

## Unestimable contract-days

Roll returns nothing for **42%** of contract-days, and the drops are **not random**: estimable rate
falls from 75.8% in the tightest measured spread quartile to 60.6% in the widest, with dropped
contracts carrying a higher median spread than estimable ones.

**Registered rule: impute the name's 75th-percentile Roll estimate**, not its median.

Conservative by construction, and the direction is chosen to match the measured bias — drops
concentrate on wider books, so imputing a central value would understate cost precisely where it is
highest. Dropping unestimable days entirely is **not** permitted: it would silently restrict the
sweep to tighter books, which are disproportionately the higher-delta arms, reintroducing the bias
the sweep exists to remove.

**Report the imputed share per arm.** An arm whose cost is mostly imputed is not measured, and a
result resting on it says so.

## Exit cost

The sweep exits at **expiry intrinsic**, so it charges **entry cost only**. That is optimistic, and
the size of the optimism is bounded by one entry cost — the live book may close early, which the
sweep does not model.

Registered as an assumption, not hidden: **sweep P&L is an upper bound relative to a book that
closes before expiry.**

## What would falsify this composition

If forward NBBO captures put the Roll-to-quoted ratio outside 0.32–0.87, the sensitivity band is
wrong and every sweep result computed under it needs recomputing. The accruing captures test this
directly, and this document should be revisited once more than one session exists.
