# Pre-registration — delta and structure sweep

**Written 2026-08-26, before the sweep runs.** Review found the sweep as proposed did not clear its
own registration bar: C11, C13 and C14 were unregistered degrees of freedom. C11 is registered in
`2026-08-26-cost-composition-registration.md`. This registers the rest.

## Design

| | |
|---|---|
| arms | short delta ∈ {0.15, 0.20, 0.25, 0.30, 0.35} × structure ∈ {put credit, call credit, iron condor} = **15 arms** |
| universe | the 11 decided names |
| period | 2024-03-01 → 2026-08-25 |
| entry | option **bar close** for the actual strikes; IV inverted **per contract**, so skew is preserved |
| exit | expiry intrinsic from the underlying close |
| staleness filter | `n ≥ 10`, `v ≥ 50` — the rule already validated by the IV-series probe |
| cost | per `2026-08-26-cost-composition-registration.md`, reported across the 0.32/0.51/0.87 ratio band |

## Entries are unconditional, and the conditional reading is reported too

The sweep enters **every eligible name-day**, not the signal-gated top N. Unconditional gives every
arm the same sample and isolates the structure question from the signal question.

**But the deployed book is signal-gated**, so the unconditional result answers a different question
from the one the book asks. Both are reported: unconditional as primary, and restricted to name-days
the signal would have selected as the secondary reading. **Where they disagree, that disagreement is
the finding**, not something to resolve by preferring one.

## Inference

| | |
|---|---|
| clustering | by **date** — names co-move and 5–9 DTE windows on consecutive days overlap |
| block bootstrap | **block length 10 trading days**, longer than the longest holding period so blocks are near-independent |
| draws | 10,000 |
| **seed** | **20260826** |
| comparison | each arm against the **incumbent 0.25-delta put credit**, with a joint interval across all 14 comparisons |
| multiplicity | Holm correction over the 14 comparisons |

Effective N is roughly **85 independent windows per arm**, not the ~6,600 name-days the grid
suggests. That number is stated because it is the one that governs what the sweep can resolve.

## "No arm is distinguishable" — the criterion, written now

> If no arm's Holm-corrected interval excludes the incumbent, the sweep is **uninformative** and is
> reported as such.

In that case the delta is chosen on risk-management grounds — lower delta, further from the money,
more room for error — and the sweep is cited as having failed to separate the arms, not as having
endorsed the choice.

**This is the most likely single outcome** at 85 effective windows across 15 correlated arms, and
naming it in advance is the point.

## Metrics

- **P&L per unit defined risk** — the sizing basis, so it matches how the book is actually scaled
- **Decomposition into premium collected versus loss from volatility expansion** — required by
  standing rule; a raw P&L on a short-vega book hides where the money came from
- **Time-series regression of arm P&L on underlying return** — the Jensen analog, and the only test
  here that speaks to whether delta exposure is compensated
- Win rate, worst single outcome, full distribution — not a Sharpe, given the sample structure

## Known biases, stated before the run

**Survivorship.** The 11 names were chosen on 2026 liquidity and applied to 2024–25. Every sweep
number is optimistic by an unmeasured amount, and this carries into any arm comparison that is not
purely relative.

**Market drift through delta.** The sample period is mostly upward. P&L per unit risk rising with
delta may measure drift rather than any credit-versus-cost relationship — which is exactly what the
regression above is there to separate. **An arm ranking that survives only before the regression is
not a result.**

**Entry timing.** Bar close is a last trade at an unknown time of day and unknown side, while the
live cycle decides at 16:05 and fills the next session. The gap is unmodelled. Its size is being
measured separately from accruing captures (|bar close − 15:50 mid| per name); if that turns out
comparable to the modelled cost, entry-pricing noise rivals the effect being swept and the sweep's
stated error must include it.

## The gate this sweep sits behind

Claim 3 — that cost as a fraction of credit rises as delta falls — is **UNTESTED**, and the widened
NBBO capture is the only thing that can settle it. **If claim 3 fails, the cost treatment registered
here is unmotivated and the sweep should not be believed regardless of what it returns.** Running the
capture first is the cheaper order.
