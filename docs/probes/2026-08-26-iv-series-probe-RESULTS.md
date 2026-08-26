# Results — IV-series probe

**Registration:** `2026-08-26-iv-series-probe.md`, committed as `e93267d` **before any data was
seen**. Script `scripts/iv_series_probe.py`, same commit. Stage 1 output: `2026-08-26-stage1.json`.

## Stage 1 — chain characterization (issued no verdict, by construction)

| | sessions | selected | contracts | leg-bars | passing filter | median `n` | p10 `n` | median `v` |
|---|---|---|---|---|---|---|---|---|
| SPY | 250 | 249 | 428 | 496 | 490 (98.8%) | 130 | 42 | 696 |
| AMD | 250 | 249 | 390 | 316 | 297 (94.0%) | 96 | 28 | 379 |

**No filter adjustment was made.** The registration permitted lowering `MIN_TRADES`/`MIN_VOLUME` only
if the chain proved sparser than assumed; it proved denser. **Zero degrees of freedom were exercised
between the stages.**

The `n:1` sparsity that motivated this whole probe came from a **deep-ITM** contract
(`SPY240315C00195000`, open interest 1). Near-ATM 30-DTE bars trade ~100×/day. **The moneyness
restriction was the load-bearing decision**, and the staleness filter barely binds — it removes 1.2%
of SPY leg-bars and 6.0% of AMD's.

## Stage 2 — judged against the registered thresholds

| criterion | SPY | AMD |
|---|---|---|
| IV days | 248 / 250 | 157 / 250 |
| unusable under the minimum-window rule | 63 | 63 |
| **1 · missing-day share** | **0.8% — PASS** | **37.2% — FAIL** |
| **2 · median\|Δp\|** (noise median 29.29) | **4.95, R = 0.17 — PASS** | **5.56, R = 0.19 — PASS** |
| **3 · lag-1 autocorr, log IV** | **0.885 — PASS** | **0.867 — PASS** |
| attribution `S` / `M` | 0.0172 / 0.0370 = **0.46** | 0.0171 / 0.0283 = **0.60** |
| **GATE** | **PASS** | **FAIL** |

## The registration has a defect, and it is recorded rather than patched

**The attribution rule does not apply to the failure that occurred.** It was written to disambiguate
a *noise* failure — "signal dead" versus "filter harder". AMD failed on **coverage** while passing
both stability criteria, and **filtering harder makes coverage strictly worse.** The registered
remediation is incoherent against this failure mode.

This is a defect in the pre-registration, not a licence to choose a different remediation now that
the data has been seen. It is recorded here, the registered verdict stands as **AMD: FAIL**, and any
re-run requires a **new registration written and committed before it runs**.

The coverage failure has an obvious candidate cause — the nearest-ATM strike on AMD does not trade
every session, and the probe demands that exact strike — but "obvious" is how post-hoc freedoms
enter, so it is a hypothesis for registration v2, not a finding.

## What this establishes

1. **A usable IV series is buildable for a liquid underlying.** SPY's percentile is strongly
   persistent — median day-over-day change of 4.95 points against 29.29 for an independently
   resampled percentile.
2. **It is not established for mid-liquidity names**, which is where the strategy's cross-sectional
   ranking has to operate. A one-name universe has no cross-section.
3. **Roughly half of SPY's day-to-day IV variation is measurement, not volatility.** `S/M = 0.46`
   passes the registered test but sits just under the 0.5 boundary: the divergence between inverting
   from `c` and from `vw` is 46% of the size of the daily IV move itself. This is a **PASS with a
   large caveat**, and any downstream statistic on this series inherits it.
4. **The minimum-window rule (rev-6 D-8) is now implemented, not merely acknowledged** — 63 days per
   name emit no percentile and are excluded rather than silently defaulted.

## Limits, unchanged from the registration

Two names, one 12-month window, both selected on today's liquidity and applied to 2024 data. The
inverter itself is unvalidated against known-IV inputs — a separate obligation this probe does not
discharge.
