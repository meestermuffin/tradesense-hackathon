# Pre-registration v2 — does the signal carry directional information?

**Written 2026-08-26, before the test runs.** Supersedes the version in the structure proposal,
which review returned **REFUTED** on three counts (C9).

## What was wrong with v1

**It could not answer its own question.** A cross-sectional rank IC demeans the common component by
construction, and compensation for market delta *is* the common component. No value of that
statistic settles whether short-delta exposure is compensated.

**Its bands were undeclared.** 0.03 and 0.08 had no derivation, where the baseline IC test derived
its 29.29-point floor from an explicit null. The statistic was also underspecified — no forward
horizon, no Newey–West lag — so the standard error the bands should calibrate against was
uncomputable.

**It read absence of evidence as evidence of absence.** |IC| ≤ 0.03 was to be read as "no directional
information", which a null result does not support.

## The question, restated to what the statistic can answer

> Does the IV-percentile ranking select, cross-sectionally, for names that subsequently move in a
> particular direction?

A null answers **"the signal adds no cross-sectional directional selection"** — nothing more. It does
**not** license "the delta exposure is uncompensated", which is a separate question answered below.

## Specification

| | |
|---|---|
| statistic | daily cross-sectional Spearman of IV percentile vs **forward 21-session underlying return** |
| horizon | 21 sessions, matching the premium-retention outcome |
| aggregation | mean daily IC, Newey–West **lag 21** |
| null | permutation, signal shuffled **within each day**, **seed 42**, 10,000 draws |
| universe | the 11 decided names, 30-month series |

## Bands, derived from the statistic's own null

**No thresholds are stated in advance as numbers.** The permutation null is computed first, and the
bands are its own percentiles:

- **directional** — observed mean IC outside the null's central 95%
- **no cross-sectional directional selection detected at this power** — inside it

The second wording is deliberate. It records what a null result means, which is that the test did not
detect an effect, not that no effect exists.

**Report the null's spread alongside the result** so a reader can see what size of effect this test
could have detected. A test that could not have found a real effect has not ruled one out.

## The compensation question, which this test does not answer

Whether the book is *paid* for its delta exposure is a **time-series** question about the position,
not a cross-sectional question about the signal. It is answered by regressing each sweep arm's P&L on
the underlying return — the Jensen analog, and the same decomposition this project's standing rules
require for any P&L claim.

**Registered as belonging inside the sweep, not here.** The delta decision then rests on two numbers:
whether the signal selects directionally (this test) and whether the position is compensated for
carrying delta (the sweep regression). Neither alone settles it.
