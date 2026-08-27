# Pre-registration — bound the cost instead of estimating it

**Written 2026-08-27, before the run.** Proposed by Solo: *"don't estimate it, bound it. find what
cost level kills the edge."*

## Why this replaces the cost model rather than waiting for it

`docs/cost-model.md` records that the cost model may not be buildable. Alpaca serves **no historical
option quotes**, name identity dominates the spread (leave-one-out error 1.72× typical), and the
best bar proxy correlates with spread at **+0.036 cross-name**. Waiting for a volatile week to
widen the sample does not fix a proxy that does not generalise.

A bound needs none of that. **What cost level drives the edge to zero?** If the answer is far above
anything plausibly payable, the missing number stops being load-bearing. If it is below what we
already measured, that is decisive and no further data will rescue it.

## The arithmetic this rests on

The registered outcome is `(IV_t − RV_fwd) / IV_t` — **the fraction of premium sold that is
retained**. It is already a return on premium, so it is directly comparable to a cost expressed the
same way:

> **breakeven cost, as a share of premium = mean outcome on the selected name-days**

No option repricing, no path simulation, no data we do not have.

## Design

| | |
|---|---|
| samples | baseline (1,807 name-days) and event-free (1,145), as the IC run |
| selection | top-N by IV percentile each session, **N ∈ {1, 3, 5, 10}** |
| gross edge | mean outcome across selected name-days |
| reported | breakeven cost as % of premium, overall **and per name** |
| comparison | the measured round-trip costs below |
| inference | block-constant name permutation, **L=21, seed 20260827**, matching the corrected IC null |

### Measured costs it is compared against, all from committed data

| source | round-trip cost |
|---|---|
| per-name median spread % of mid, 132-quote capture 2026-08-26 | SPY 0.96% … MU 5.61% |
| marketable fill, measured | paid **82% of the half-spread**, so ≈ 0.82 × spread per round trip |
| fees | $0.025 per contract-leg; 4 crossings per vertical round trip — negligible |
| **vertical, cost as share of net credit** | SPY test order **9.7%**, AMD **34%** *(both legs crossed, both ways)* |

The last row is the one that matters and it is why this is not a single number. A vertical crosses
two legs to collect a credit smaller than either leg's premium, so cost as a share of *credit* is
several times cost as a share of *mid*.

## Decision table, written before the run

On the **event-free** sample at **N = 10**, the deployed configuration:

| breakeven ÷ measured round-trip cost | verdict | consequence |
|---|---|---|
| **> 2×** | **SURVIVES** | Solo's bar met. The precise cost model is no longer blocking; the bound is quotable in its place |
| 1× – 2× | **MARGINAL** | survives at measured cost with no margin. Cost model still blocks any quoted number |
| **≤ 1×** | **DOES NOT SURVIVE** | the edge does not clear its own transaction costs. No backtest number is ever quotable, and that is the finding |

Reported per name as well as pooled, because the 6× spread range across the universe means a pooled
verdict can hide names on both sides of the line.

## What this run cannot do, stated now

**The signal it prices is WEAK.** The block-permutation run on 2026-08-27 returned p 0.0660 on this
same sample; the significance claim is withdrawn. A favourable bound therefore says only *"granting
the signal for argument, here is the cost ceiling."* **It does not restore significance and must
never be quoted as if it does.**

**The spread data is one calm afternoon**, 132 quotes, single regime. Every measured cost here is a
**floor**. A bound that only just clears a floor has not cleared anything.

**Mean outcome is not P&L.** It ignores path, assignment, and the fact that a defined-risk spread
truncates both tails. It is the right quantity for a *ceiling on affordable cost*, which is all this
claims.

## Expected, stated in advance

The wide names will not clear. SPY at 0.96% against AMD and MU above 5% is a 6× range, and the test
orders already put vertical cost at 9.7% of credit on SPY versus 34% on AMD. **If the verdict splits
by name, that split is the finding** — and it is the evidence for or against Solo's proposal to
trade only the tight names.

---

# Addendum — the run, and a defect in this registration's own statistic

**Written 2026-08-27, after the run at `eb86625`.**

## Registered result

Event-free, N=10: gross edge **−8.36%** of premium against a measured round-trip of **55.4%** of
net credit. Ratio −0.15×. **DOES NOT SURVIVE.** No name clears 2×; the best is SPY at **0.29×**.

## The defect, found while checking the result

The mean of `(IV_t − RV_fwd)/IV_t` is **not** the fraction of premium a *vertical* retains. The
outcome is unbounded below and capped at +1 above, and dividing by `IV_t` makes it explode when
implied vol is small. On the selected name-days:

| | |
|---|---:|
| mean | −8.36% |
| **median** | **+2.72%** |
| minimum | **−1732%** |
| mean of the worst 5% | −237% |
| mean excluding the worst 5% | +3.61% |
| share losing more than 100% of premium | 0.9% |

**A defined-risk vertical cannot lose 1732% of its credit.** It is capped at `width − credit`.
Flooring the outcome accordingly:

| loss floor | mean gross edge |
|---|---:|
| unfloored *(as registered)* | −8.36% |
| −100% of premium | **−0.33%** |
| −400% of credit *(a 5-wide at 1.00)* | **−1.89%** |

**This is why the rank IC and this bound disagree without contradicting each other.** Rank IC is
invariant to the tail pathology — ranks do not care that one observation is −1732%. Any *mean*-based
statistic on the same outcome is dominated by it. The two were never measuring compatible things,
and this registration did not notice before specifying the mean.

## What the verdict is, after the correction

**Unchanged, and for a stronger reason.** Under every flooring, the gross edge on the selected names
is **negative or indistinguishable from zero before any transaction cost is charged at all**. Cost
never becomes the binding constraint, so the bound cannot be cleared by trading tighter names:
SPY is the tightest in the universe and returns +4.38% gross against a 15.3% round-trip, 0.29×.

## Status

The registered arm stands as run. **A mean-based edge on this outcome needs its own registration
with the structural cap specified before it can be quoted as a number** — the floored figures above
are a diagnosis of why the registered statistic was the wrong one, not a result.
