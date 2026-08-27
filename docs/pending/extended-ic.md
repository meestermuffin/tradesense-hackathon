# Pre-registration — the IC on the data we did not spend

**Written 2026-08-27, before the run.** Every prior IC test — the baseline, job 2, the block
permutation and the cost bound — ran on `iv_series_2024-03_2025-02.csv.gz`: **249 sessions, about
11 independent windows at H=21.** A longer series is committed and no test has touched it.

| series | sessions | independent windows |
|---|---:|---:|
| `2024-03_2025-02` *(all prior tests)* | 249 | ~11 |
| `2024-03_2026-08` | **597** | **~28** |

Verified before registering: the long series is a **strict superset** — all 2,731 overlapping rows
are byte-identical, so this extends the sample rather than changing the measurement.

## This is a re-test after a failure, and that is declared

The block-permutation run returned **WEAK** (p 0.0660). Re-running on more data after a result you
did not like is the garden of forking paths, and the only thing separating it from fishing is that
the registration precedes the run and binds both outcomes.

**The decision table below is unchanged from `8a45517`,** written before any corrected null had been
computed. It is not being adjusted now that we know where the previous run landed.

**Stated in advance:** if the primary arm collapses, that is the answer and signal work stops. It
will be recorded with the same prominence as a favourable result.

## What this run cannot do — the event-free arm is unavailable

The prior **primary** was the event-free sample: name-days whose 21-session forward window contains
no earnings announcement. `data/earnings_8k_2024_2025.json` covers **2023-12-20 → 2025-06-25**, and
`earnings_next_2026.json` carries **no dates**. Beyond mid-2025 the exclusion cannot be applied.

So the primary here is the **baseline** arm, on all name-days. **A survival on baseline is strictly
weaker than the event-free survival it replaces** — job 2 exists because 35.8% of name-days have an
announcement inside the forward window, and the baseline cannot separate the ranking from a
scheduled-event detector. This is registered as a limitation, not resolved.

## Design

| | |
|---|---|
| **primary** | **A · baseline · out-of-sample window 2025-03-01 → 2026-08-25** — the sessions no test has touched |
| secondary | A · baseline · full series 2024-03 → 2026-08 |
| anchor | A · baseline · original window, which must reproduce IC +0.1753 and p 0.0105 |
| reported, not decision-bearing | event-free arm where earnings data exists (through 2025-06); variant B, already known confounded |
| **control** | **C · raw IV level, on every arm** |
| null | block-constant name permutation, **L=21**, 2,000 draws, **seed 20260827** — identical to the corrected null |
| also reported | Newey–West t(21), and the null's standard deviation per arm |

The panel is built on the **full** series and then filtered by date, so every record keeps its 126-
session trailing percentile window. Filtering the source first would silently truncate that window
at the boundary.

## Decision table — carried unchanged from `8a45517`

On the primary arm:

| p | verdict | consequence |
|---|---|---|
| ≤ 0.05 | **SURVIVES** | the ranking is significant out-of-sample; quotable with the corrected p, the baseline-vs-event-free limitation stated beside it |
| 0.05 – 0.20 | **WEAK** | may not be called significant. Two independent samples now say underpowered, and signal work stops |
| > 0.20 | **NO EVIDENCE** | withdrawn. Signal work stops |

## The null's validity check

**Control C must remain non-significant on the primary arm.** The previous design was voided by
exactly this check. If C turns significant, no arm is readable, including a favourable one.

## Contamination that is not fixed by more data

**Universe selection reaches into the test window.** The 11 names were chosen on **2026** liquidity,
and the out-of-sample window runs to 2026-08. The names were therefore picked using information from
inside the period they are being tested on. This is look-ahead on the *universe*, not on the signal,
and it biases the result **optimistic**. It cannot be removed without a universe chosen on 2024
information, which does not exist here.

A SURVIVES verdict must be reported carrying this caveat. It is the strongest reason a judge could
discount a favourable result, and it should not be theirs to discover.
