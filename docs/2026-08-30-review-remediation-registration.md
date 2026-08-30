# Pre-registration — two probes the 2026-08-30 review asked for

**Written 2026-08-30, before either runs.** Both come from
`.claude/private/2026-08-30-shelving-runs-review.md`. Neither is a new strategy test.

## Probe 1 — an availability-preserving null (defect D2)

### The defect

`block_name_perm` permutes name labels across the full universe and **drops a name-day when the
permuted source name has no row that day.** On the ragged event-free panel that costs **25.2% of
name-days per draw** (856.7 of 1,145; sessions 98.8 of 111). The null is therefore computed on a
panel *smaller and differently shaped* than the observed one, which inflates its spread by ~10–13%.

Run 3's out-of-sample panel is nearly rectangular and loses **0.2%**, so it is unaffected.

### Why it matters

Run 1's reported p is **0.0660**, against a registered threshold of 0.05. The review's drop-corrected
estimate is **≈ 0.046–0.049**. That straddles the threshold. **Run 1's recorded WEAK may be wrong,
and could as easily read SURVIVES.**

### Design

Draw one random priority ordering of the universe per block of `L=21` sessions. On each session,
induce a permutation **on the names actually present that day**: the i-th present name in natural
order maps to the i-th present name in priority order. This is a bijection on the observed set, so
**no name-day is ever dropped** and the day/name-count structure is preserved exactly, while the
permutation stays block-constant.

| | |
|---|---|
| arm | variant A, event-free sample — run 1's decision arm, unchanged |
| null | availability-preserving block permutation, `L=21` |
| draws | 2,000 per seed |
| **seeds** | **10: 20260830 … 20260839.** The reported p is the mean across seeds, with the spread shown |
| reported alongside | the drop rate (must be 0.0%), the null mean and sd, and the old dropping null for comparison |

Ten seeds because the review measured Monte-Carlo se at **0.0055** at this boundary — one seed
cannot resolve 0.046 from 0.055.

### Decision table

| mean p across seeds | consequence |
|---|---|
| ≤ 0.05 | run 1's record is corrected **WEAK → SURVIVES, on the original sample only** |
| > 0.05 | the WEAK record stands, with the bias now measured and closed |

**This cannot unshelve the strategy, and that is registered before the run rather than argued after
it.** Run 3 is the load-bearing run: it is drop-free at 0.2%, tests 327 sessions no other run
touched, and reads p 0.2184 with z 0.82. Probe 1 speaks only to the *original* sample, which run 3
supersedes. A SURVIVES here changes one line of the record and nothing about the conclusion.

**Validity check:** the drop rate must print 0.0%. If it does not, the fix did not work and the run
is void.

## Probe 2 — does A survive an outcome with no IV term? (claim 23, the one UNTESTED)

### The gap

The registered outcome is `(IV_t − RV_fwd)/IV_t`, which contains `IV_t`. Signal A is the percentile
of `IV_t` against its own history. Arm C closes the *cross-name level* channel of that shared term
and reads negative. **A's within-name deviation channel is unprobed** — this is the same defect class
that voided the very first IC run, and it is only partially closed.

### Design

Recompute run 3's out-of-sample arm against an outcome carrying **no IV term at all**: `−RV_fwd`.
Rank correlation is invariant to monotone transforms, so the sign is what matters.

`RV_fwd` is recoverable exactly from the committed panel — `out = 1 − RV_fwd/IV_t` and `C = IV_t`,
so `RV_fwd = C·(1 − out)`. No rebuild, no new data.

| | |
|---|---|
| arm | A, out-of-sample 2025-03 → 2026-08 |
| outcome | `−RV_fwd`, IV-free |
| null | availability-preserving block permutation, `L=21`, 2,000 draws, seed 20260830 |
| also run | C, same outcome, as a comparison |

### Decision table

| result | reading |
|---|---|
| A's association persists with the same sign | the +0.0414 residual is **not** shared-term arithmetic |
| A vanishes or reverses | the in-sample +0.1753 was **partly mechanical**, and the shelving is *strengthened* |

**Either outcome supports the shelving.** The review noted the direction of this defect inflates A,
so closing it can only reduce the estimate. That is registered here so a null result is not later
presented as a surprise.

## What neither probe is

Neither proposes a signal, a feature or a variant. Both close defects in tests already run. **Nothing
here plans on top of an unconfirmed IV series** — the gate in `CLAUDE.md` is not triggered.

## Amendment to the shelving doc's revival criteria

Criterion 3 in `docs/2026-08-30-strategy-shelved.md` requires significance under a block-constant
name permutation. **It is amended to require an availability-preserving one**, per D2 — a null that
reshapes the panel while resampling is not a null the criterion should accept.
