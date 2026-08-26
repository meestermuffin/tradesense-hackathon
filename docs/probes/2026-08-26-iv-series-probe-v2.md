# Pre-registration v2 — IV-series probe, coverage on mid-liquidity names

**Written 2026-08-26 after v1 ran, before v2 ran.** Committed before execution. v1's verdicts stand
as recorded — this does not amend them.

## Why there is a v2, stated honestly

v1 returned **SPY PASS, AMD FAIL on coverage** (37.2% of sessions with no IV). v1's registered
remediation for a FAIL was "filter harder", which was written for a *noise* failure and is
**counterproductive against a coverage failure**. That is a defect in v1's registration, recorded in
its results rather than patched in place.

**The change below is a post-hoc degree of freedom.** It was chosen after seeing that coverage
failed. There is no way to make that not true. Three things constrain it:

1. **The thresholds are unchanged from v1**, character for character. Only *contract selection*
   changes.
2. **Exactly one change is made**, stated below, and no other parameter moves.
3. **Two names are added that v1 never touched.** If the new selection rule only rescues the name
   whose failure motivated it, that is visible; if it also works on names chosen before their results
   were known, that is evidence rather than fitting.

## The one change

| | v1 | **v2** |
|---|---|---|
| contract selection | the strike **nearest spot** inside the moneyness band, unconditionally | the strike **nearest spot inside the moneyness band whose bar that session passes the staleness filter** |

**Hypothesis being tested:** AMD's exact nearest-ATM strike does not trade every session, and v1
recorded a missing day whenever that one strike was quiet — even when a strike one increment away had
a perfectly good bar. If true, v1 measured *strike-level* sparsity and reported it as *name-level*
coverage.

**What would falsify it:** coverage stays below the PASS band under v2. Then the sparsity is genuine
at the name level and no selection rule fixes it.

Note the band still binds: a strike outside `0.95 ≤ K/S ≤ 1.05` is never selected however well it
trades. v2 widens *which* in-band strike may be used, not the band.

## Names

| name | role | in v1? |
|---|---|---|
| SPY | liquid control — must still PASS, or v2 broke something | yes |
| AMD | the name that failed | yes |
| **NFLX** | mid-liquidity, **out-of-sample for this rule** | **no** |
| **AVGO** | mid-liquidity, **out-of-sample for this rule** | **no** |

## Everything else — unchanged from v1

Period 2024-03-01 → 2025-02-28 · Friday expiries · DTE nearest 30 within [21,45] · moneyness
`0.95 ≤ K/S ≤ 1.05` · `MIN_TRADES = 10`, `MIN_VOLUME = 50` · call/put mean · `r = 0.04` · dividends
ignored · percentile over trailing 126 sessions with minimum 63 valid observations.

## Verdict rules — identical to v1, restated so they cannot drift

| criterion | PASS | CONDITIONAL | FAIL |
|---|---|---|---|
| missing-day share | ≤ 10% | 10–30% | **> 30%** |
| median \|Δp\| ÷ 29.29 (`R`) | ≤ 0.40 | 0.40–0.70 | **> 0.70** |
| lag-1 autocorrelation, log IV | ≥ 0.80 | 0.50–0.80 | **< 0.50** |

Any single FAIL fails that name. Attribution `S/M` is reported for every name; per v1's recorded
defect it is **not** used to license a remediation for a coverage failure.

## Consequences, registered before the run

| outcome | what it means |
|---|---|
| **AMD passes and both out-of-sample names pass** | v1 measured strike-level sparsity, not name-level. The IV series is buildable across the universe and the gate is genuinely open |
| **AMD passes, out-of-sample names fail** | the rule rescued the name it was designed against and nothing else. Treat as **fitting**, not a result, and the gate stays shut |
| **AMD still fails** | name-level sparsity is genuine. **A cross-sectional percentile signal is not supportable on mid-liquidity names with this data**, and the week is re-planned around a liquid-name-only book or a different signal |

**No v3.** If v2 fails, the answer is a change of strategy, not a third selection rule.
