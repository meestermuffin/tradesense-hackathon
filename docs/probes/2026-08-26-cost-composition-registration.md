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

---

# Addendum — the imputation rule registered above does not survive measurement

**Written 2026-08-26, after the regime-coverage probe, which was registered before it ran
(`scripts/roll_regime.py`).**

## The result

324 contract-days across SPY, AMD and MU, 2026-03 to 2026-08, Roll estimability against the
underlying's same-day realized range:

| realized range quartile | range | estimable |
|---|---|---:|
| Q1 calmest | 0.34–1.27% | **70.4%** |
| Q2 | 1.28–3.93% | 39.5% |
| Q3 | 3.96–6.08% | 30.9% |
| Q4 most volatile | 6.10–14.40% | **29.6%** |

**A 40.7 point drop against a registered 10-point threshold.** Median realized range is **1.82%**
where Roll works and **4.56%** where it does not.

## Why this breaks the rule above, not just qualifies it

The rule registered imputing the name's **75th-percentile Roll estimate** for unestimable days,
chosen to be conservative because drops skew toward wider books.

**That reasoning assumed the drops were a spread effect. They are mostly a regime effect.** On the
most volatile quartile, **70% of contract-days have no estimate at all** — and the distribution the
imputation would draw from is composed almost entirely of calm days, because those are the only days
Roll returns anything. Imputing a calm-regime value into a volatile day understates cost precisely
where cost is highest, and does so for the majority of days in that regime.

**This is structural, not a filtering problem.** Roll requires bid-ask bounce to dominate directional
drift. A volatility expansion *is* directional drift. The estimator is blind by construction in the
state where a short-vega book takes its losses.

## What follows

**Roll cannot carry the cost model for this book.** It measures calm-regime execution cost, and this
strategy's losses arrive in the other regime. Three responses are available and none is free:

1. **Report gross, with this limitation stated.** Honest, and leaves the cost question open.
2. **Restrict any cost-adjusted conclusion to the calm regime** and say so explicitly — which is a
   much narrower claim than the sweep was designed to make.
3. **Find a regime-robust estimator.** No candidate identified; the bar proxies already failed at
   +0.036, and there is no time before the window.

**A backtested P&L number is now further out of reach, not closer.** The Roll result made it look
conceivable this afternoon. This probe shows the estimator is absent in the regime that determines
whether a short-premium book survives, which is the regime a judge would most want costed.

**The registered sweep should not charge Roll costs as specified.** Until one of the three responses
above is chosen and registered, the cost line in `2026-08-26-delta-sweep-registration.md` is
unsupported.
