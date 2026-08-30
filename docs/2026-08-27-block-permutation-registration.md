# Pre-registration — does the permutation null survive the overlap correction?

**Written 2026-08-27, before the run.** Raised by Solo. Registers a re-test of the significance —
not the point estimate — of the baseline IC result recorded in `docs/measurement-log.md`.

## The defect

`permutation_p` shuffles the signal **among names within each session**. That destroys the
name-to-outcome link and preserves the cross-sectional distribution, which is what it was built for.
It leaves the *temporal* structure of both panels completely untouched.

The outcome is realized volatility over the **next 21 sessions**, computed on daily data. Consecutive
name-days therefore share 20 of their 21 outcome days. Under the within-day null the resampled
mean-IC series is independent across sessions; the observed one is not. A null that is more
independent than the data understates the variance of the mean, and the p-value comes out too small.

This is the project's own first measurement rule — *overlapping windows inflate significance* —
applied to the Newey-West t and never to the permutation beside it.

## The evidence that it is already too narrow

From the committed results, no new computation required:

| sample | mean IC (A) | NW t(21) | within-day permutation p |
|---|---:|---:|---:|
| baseline, 1,807 name-days | +0.1753 | 2.45 | 0.0010 |
| ±2 sessions removed, 1,674 | +0.1831 | 2.41 | 0.0010 |
| **forward window event-free, 1,145** | **+0.1561** | **1.69** | **0.0010** |

The permutation p sits at the floor (1/1001) in every row, including the one where Newey-West falls
to **1.69** — roughly p 0.09 two-sided. Two statistics on identical data, disagreeing by two orders
of magnitude, and the one that corrects for the 21-session overlap is the one reporting no
significance. A p-value that cannot distinguish a t of 2.45 from a t of 1.69 is not measuring.

165 sessions at a 21-session horizon is about **8 non-overlapping windows**. That is the number that
governs what this sample can resolve, and it is not 1,807.

## Design

| | |
|---|---|
| samples | baseline (1,807 name-days, 165 sessions) **and** forward-window event-free (1,145) |
| variants | A · IV percentile · B · IV ÷ trailing 21d RV · **C · raw IV level (control)** |
| statistic | mean daily rank IC, unchanged from the registered protocol |
| data | `data/iv_series_2024-03_2025-02.csv.gz`, unchanged |
| H, windows | H=21, percentile 126/63, trailing RV 21 — all unchanged |

Three nulls, run side by side:

**Reproduction arm — within-day shuffle.** The published null. Must return 0.0010 or the script is
not measuring the same thing the log records, and nothing else in the run is readable.

**Primary — exhaustive circular shift.** Each name's signal series is rotated in time by a common
offset `s`, outcomes held in place. This preserves every autocorrelation in the signal, every
autocorrelation in the outcome, and the cross-name co-movement of both; it destroys only the
temporal *alignment* between them, which is exactly the association being tested.

`s` ranges over `[H, T−H]` = `[21, 144]`, giving **124 offsets**, and **every one is evaluated**.
The test is therefore exact over the shift group and **deterministic — there is no seed**, which is
stronger than recording one. Minimum attainable p is 1/125 = 0.008.

**Secondary — block permutation.** Contiguous blocks of sessions, `L ∈ {21, 42}`, blocks reassigned
at random. 10,000 draws, **seed 20260827**. Reported alongside as a robustness reading; the circular
shift is the arm the decision hangs on.

## Decision table, written before the run

On **variant A, event-free sample** — the weakest published row and the one the book actually trades:

| primary p | verdict | consequence |
|---|---|---|
| ≤ 0.05 | **SURVIVES** | +0.1561 may be quoted, with the corrected p stated beside it |
| 0.05 – 0.20 | **WEAK** | may not be called significant anywhere; reported as suggestive, both p's shown |
| > 0.20 | **NO EVIDENCE** | the headline is withdrawn from deck, video and repo |

Baseline sample reported the same way, secondary to the event-free row.

## The null's own validity check

**Control C must remain non-significant under the new null.** C is raw IV level and reads −0.1055;
it is not a strategy. If C turns significant under the circular shift, the shift has introduced an
artifact and **no arm from this run is readable**, including a favourable one.

## Stated in advance

**We expect the p to rise.** Writing that here so a rise cannot later be narrated as a hunch
confirmed, and a non-rise cannot be quietly dropped.

**This does not touch the point estimate.** +0.1753 and +0.1561 are unchanged by anything here. Only
the claim that they are distinguishable from chance is under test. A WEAK or NO EVIDENCE verdict
retracts a significance claim, not a measurement.

**The bar is the same for both directions.** If the corrected p is favourable, the corrected number
is what gets quoted — not the smaller within-day one that happens to look better.

---

# Addendum — the first design was void, and its own control said so

**Written 2026-08-27, after the run registered above and before the corrected one.** The run at
`f898dea` is **VOID**. It is recorded here rather than deleted, because the reason it failed is the
finding.

## What happened

The registered validity check fired: control C came back significant (shift p 0.0081) alongside a
"SURVIVES" reading for A. Per the registration, no arm from that run is readable — including the
favourable one.

## Why — the circular shift never breaks the pairing

It rotates each name's signal in time and pairs it with **that same name's** outcome. Name identity
survives the shift, so the null is not "no association between this name's signal and its outcome" —
it is "the association, lagged". For a persistent signal that is barely a perturbation at all.

Where each null sits, measured:

| | null mean | null sd |
|---|---:|---:|
| within-day, variant A | +0.0009 | 0.0265 |
| within-day, control C | +0.0013 | 0.0278 |
| **circular shift, variant A** | **−0.0470** | 0.0780 |
| **circular shift, control C** | **−0.1915** | 0.0232 |

A valid null centres near zero. The shift centres at −0.19 on the control, which is why C scored
"significant" against it: C's actual of −0.1055 sits at the *top* of a null that has been dragged
downward. The shift was not a null. It was a different statistic.

## The corrected null — block-constant name permutation

Three properties are needed at once, and each of the first two designs had only two of them:

| | breaks name↔outcome | keeps 21-session overlap | unbiased |
|---|---|---|---|
| within-day shuffle | yes | **no** | yes |
| circular shift | **no** | yes | **no** |
| **block-constant name permutation** | **yes** | **yes** | **yes** |

Permute the name labels, as the within-day shuffle does, but hold one permutation fixed across a
contiguous block of `L` sessions instead of redrawing every session. The pairing is broken, and the
resampled IC series acquires the same day-to-day persistence the observed one has.

Validated on the **control only**, deliberately blind to variant A:

| L | null mean | null sd |
|---|---:|---:|
| 1 *(reduces to within-day)* | −0.0022 | 0.0245 |
| **21** *(primary — the outcome horizon)* | −0.0029 | **0.0924** |
| 42 *(secondary)* | −0.0015 | **0.1030** |

Unbiased at every length, and **the published within-day null is 3.8× too narrow.** That factor is
the whole of Solo's objection, and it is close to what Newey-West already implied.

| | |
|---|---|
| primary | `L = 21`, 2,000 draws, **seed 20260827** |
| secondary | `L = 42`, same draws and seed |
| reproduction arm | `L = 1`, which must reproduce the published within-day p |
| decision | **the table above, unchanged** |

**The thresholds are not being touched.** 0.05 and 0.20 were committed at `f898dea` before any of
this was measured. Having now seen the null's spread, we can anticipate roughly where A will land —
which is exactly the circumstance in which moving a threshold would be indefensible. They stand.

**What is expected, stated before the run:** a p near the 0.05 boundary, since +0.1561 against a
null sd of 0.0924 is about 1.7 sigma, and the Newey-West t on that sample is 1.69. If the two
independent corrections agree, that is the finding, whichever side of 0.05 it lands.
