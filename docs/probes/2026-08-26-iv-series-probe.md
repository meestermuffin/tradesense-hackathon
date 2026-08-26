# Pre-registration — IV-series probe

**Written 2026-08-26, before the probe ran.** Committed before execution. If this document's git
commit is not an ancestor of the commit containing the results, the results are void.

## What this probe decides

The strategy ranks each underlying on **its own IV percentile against its own history**. That
requires a per-name daily implied-volatility series over ~2.5 years. Alpaca returns no implied
volatility to this account, so IV must be **computed** by Black-Scholes inversion from option daily
bars, whose close is a **last-trade price at an unknown intraday time** paired with a 16:00
underlying close.

This probe decides whether that series is stable enough for a percentile computed on it to carry
information. **Noisy → the percentile signal fails for a structural reason no filtering can fix,
because the percentile *is* the signal.**

## Two stages, and what each may conclude

The failure this structure prevents: choosing thresholds after seeing the distribution they judge.

| stage | may conclude | may not |
|---|---|---|
| **1 — characterize** | how much of the chain survives filtering; how many API calls stage 2 costs; whether stage 2 is runnable at all | **nothing about signal quality.** Stage 1 is barred from computing an IV percentile or issuing a verdict |
| **2 — judge** | pass / conditional / fail against the thresholds below | nothing not registered here |

Stage 1 may adjust only **`MIN_TRADES` and `MIN_VOLUME`** (below), and only downward if the chain is
sparser than assumed, and the adjustment must be recorded with its reason. **It may not touch any
threshold in *Verdict rules*.**

## Fixed parameters

| parameter | value | why this value |
|---|---|---|
| names | **SPY** (liquid), **AMD** (mid-liquidity) | the plan requires one of each; both are in the candidate universe and both had listed options throughout the window |
| period | **2024-03-01 → 2025-02-28** | 12 months. Shorter cannot fill the percentile window below |
| expiries considered | **Fridays only** | SPY lists daily expiries; using all of them multiplies chain enumeration ~5× for no gain in a reference series |
| target maturity | expiry with **DTE closest to 30**, within **[21, 45]** | vega is largest near ATM/30d, so IV is best identified there. The traded structure is 5–9 DTE — see *A stated decision* below |
| moneyness band | **0.95 ≤ K/S ≤ 1.05** | deep-ITM options are nearly all intrinsic value and IV is barely identified there. This is the restriction the plan promised and never stated |
| contract | nearest-ATM strike; invert the **call and the put**, take the mean where both survive filtering | put–call parity means they should agree; their divergence is a free second quality instrument |
| staleness filter | bar must have **`n` ≥ 10 trades** and **`v` ≥ 50 contracts** | `n:1` bars are one trade at an unknown time against a 16:00 close — non-synchronous by construction |
| underlying price | Alpaca daily stock bars, same session close | keeps the probe runnable by anyone who clones the repo; no database dependency |
| risk-free rate | **constant r = 0.04** | at 30 DTE the IV sensitivity to r is negligible; a term structure would be false precision |
| dividends | **ignored** | biases call IV down and put IV up; the call/put mean cancels most of it. Recorded as a known, signed bias |
| percentile window | **trailing 126 trading days, minimum 63 valid observations** | closes rev-6 defect D-8, open in two prior documents. Days with fewer than 63 valid observations in the window emit **no percentile** and are counted separately as unusable — coverage of *presence* is not coverage of *window* |
| seed | not applicable — no sampling | recorded so its absence is deliberate |

## Verdict rules — registered before any data was seen

Three primary criteria. **Any single FAIL fails the gate**, subject to the attribution read below.

### 1. Missing-day share

Fraction of trading days in the period with no valid IV after filtering.

| | |
|---|---|
| PASS | ≤ 10% |
| CONDITIONAL | 10 – 30% |
| **FAIL** | **> 30%** |

### 2. Percentile-change distribution — measured against an explicit null

The statistic is the **median absolute day-over-day change in the IV percentile**, over days where
both days emit a percentile.

For a percentile that is pure noise — resampled independently each day — the day-over-day change is
`|U − V|` for two independent uniforms, whose median is exactly **1 − √2⁄2 = 29.29 percentile
points**. That is the number a dead signal produces, and it is derived, not chosen.

Define the **persistence ratio** `R = median|Δp| / 29.29`. `R = 1` is indistinguishable from noise;
`R = 0` is perfect persistence.

| | R | median\|Δp\| |
|---|---|---|
| PASS | ≤ 0.40 | ≤ 11.7 |
| CONDITIONAL | 0.40 – 0.70 | 11.7 – 20.5 |
| **FAIL** | **> 0.70** | **> 20.5** |

### 3. Lag-1 autocorrelation of log IV

A real volatility series is strongly persistent in level.

| | |
|---|---|
| PASS | ≥ 0.80 |
| CONDITIONAL | 0.50 – 0.80 |
| **FAIL** | **< 0.50** |

## The attribution instrument — what a FAIL means

Without this, "noisy" is ambiguous between *the signal is dead* and *filter harder*, which is the
decision the gate exists to make.

Invert IV twice from the same bar: once from **`c`** (last trade) and once from **`vw`**
(volume-weighted). Both describe the same day; their divergence is a **lower bound on the
measurement noise** contributed by non-synchronicity and tick discreteness.

Let `S = median |IV_c − IV_vw| / IV_vw` and let `M = median |Δ log IV|` day-over-day.

| reading | consequence |
|---|---|
| **S ≥ 0.5 × M** | measurement noise dominates the observed variation. A FAIL means **filter harder** — tighten `MIN_TRADES`, narrow the moneyness band, and re-run stage 2. It does **not** license "the signal is dead" |
| **S < 0.5 × M** | observed variation is mostly genuine. A FAIL means **the signal is dead**, and the week changes shape |

## Both readings' consequences, stated in advance

| outcome | what happens next |
|---|---|
| **PASS** | the IV-series build is an engineering task; the plan's shape survives; leg 2 proceeds |
| **CONDITIONAL** | one re-run with tightened filters is permitted, **once**, and the tightening is recorded here before it runs. A second conditional is a FAIL |
| **FAIL, S ≥ 0.5M** | filter harder per above; if still FAIL, treat as FAIL below |
| **FAIL, S < 0.5M** | **the percentile signal is abandoned.** The baseline reverts to `IV / trailing_RV` computed from live snapshots forward only, with no historical percentile, and the week is re-planned around it |

## A stated decision, so it is not mistaken for an oversight

The reference series is built at **~30 DTE** while the strategy trades **5–9 DTE**. This is
deliberate: at 5–9 DTE vega is small enough that $0.01 tick discreteness produces large IV jumps, so
a short-dated reference series would measure tick noise as volatility. The percentile is therefore a
**regime measure for the name**, not a price for the contract being traded. If that substitution is
wrong, it is wrong in a way this probe cannot detect, and it should be attacked separately.

## Known limits of this probe

- **Two names, one 12-month window.** Neither generalises to the full universe.
- **Survivorship:** both names are chosen on today's liquidity and applied to 2024 data.
- **The 2024-01-18 data floor was measured on SPY only.** AMD's floor is unknown and stage 1 records it.
- **Nothing here validates the inverter itself.** A unit test against known-IV inputs is a separate
  obligation and is not satisfied by this probe.
