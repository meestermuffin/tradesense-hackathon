# Results — baseline signal IC

Registration `010fee8`; addendum voiding the original statistic `beeb80a`. Both are ancestors of this
commit. Series: `data/iv_series_2024-03_2025-02.csv.gz`, 11 names, 1807 name-days, 165 usable
sessions.

## Run 1 — VOID

| variant | mean IC | NW t(21) | perm p | verdict |
|---|---|---|---|---|
| A · IV percentile | 0.1645 | 2.24 | 0.0010 | EVIDENCE |
| B · IV ÷ trailing RV | 0.2359 | 3.39 | 0.0010 | EVIDENCE |

**Void.** Outcome was `IV_t − RV_forward`; both signals are functions of `IV_t`, so `IV_t` entered
both sides positively. Kept in the record because deleting it would hide that the protocol was wrong
rather than the world being surprising.

## Run 2 — corrected outcome `(IV_t − RV_fwd)/IV_t`, with a control arm

| variant | mean IC | NW t(21) | perm p | verdict |
|---|---|---|---|---|
| **A · IV percentile (126/63 trailing)** | **+0.1753** | **2.45** | **0.0010** | **EVIDENCE** |
| B · IV ÷ trailing 21d RV | +0.2727 | 4.57 | 0.0010 | EVIDENCE — **but see below** |
| C · raw IV level *(control, not a strategy)* | **−0.1055** | −1.48 | 1.0000 | NO EVIDENCE |

## B is confounded and should not be quoted

`B = IV / RV_trail` and `outcome = 1 − RV_fwd / IV`. Measured on this data, the cross-sectional rank
correlation between trailing and forward 21-day realized vol is **+0.8166** over 207 days. So
`RV_fwd ≈ RV_trail`, and the outcome collapses toward `1 − 1/B` — a deterministic monotone function
of the signal.

**B's +0.2727 is largely measuring volatility persistence.** Same defect class as run 1: the signal
shares a term with its own outcome. B is reported, per the registration, and is not treated as
evidence.

## A survives, and the control is why

A is the IV percentile against the name's **own trailing history**. It contains no realized-vol term,
so the persistence confound does not reach it.

The remaining shared term is `IV_t` in the outcome's denominator — and the control arm measures that
channel directly. **C is −0.1055.** The pure-IV-level channel runs *against* A, so if it biases A at
all it biases it **downward**. A's +0.1753 is achieved despite that channel, not because of it.

This also confirms the plan's own design argument by measurement rather than assertion: *"the raw gap
mostly re-measures which names are structurally expensive; cross-sectional ranking removes the common
level effect, per-name percentile removes the rest."* Selling the highest absolute IV is mildly
harmful; selling the highest IV **relative to a name's own history** is not.

## What this is, stated at its actual weight

**The first evidence in this project that the premise holds.** Ranking names by how rich their
implied vol is against their own history selects name-days that retain a larger fraction of premium
sold — rank IC +0.1753, Newey–West t 2.45 on lag 21, permutation p 0.001 at seed 42 over 1000
within-day shuffles, against a negative control.

**What it is not:**

- **Not a P&L number.** No option was priced, no spread constructed, no cost charged. The cost model
  is provisional and its spread estimator is unfitted; nothing here may be quoted as a return.
- **Survivorship-biased.** Eleven names chosen on 2026 liquidity, applied to 2024–25. Optimistic by an
  unmeasured amount.
- **One 12-month window**, one volatility regime, 165 usable sessions, 11 names per day. A daily
  Spearman over 11 points is noisy; the permutation null carries more weight here than the t.
- **Wrong tenor.** The series is 30-DTE ATM; the strategy trades 5–9 DTE. This tests the regime
  measure, not the contract.
- **Measured on a noisy input.** `|p_c − p_vw|` has a p90 of 8–20 percentile points — roughly a tenth
  of name-days are print-sensitive, and that noise sits inside the signal being tested.
- **Job 2 has not run.** Whether this IC survives removing earnings-proximate name-days is unknown,
  and per the registration it is reported as NOT RUN — never as passed.

## Registration defects found today, all three by self-audit after the run

| # | defect |
|---|---|
| 1 | v1's attribution rule covered a noise failure, not the coverage failure that occurred |
| 2 | v2's decision table omitted CONDITIONAL, the outcome that occurred |
| 3 | the IC statistic shared a term with its own outcome — **would have produced a headline number** |

The pattern is consistent and worth naming: thresholds keep being registered carefully while the
*structure* around them — decision tables, and whether the statistic matches the objective — does
not. Next registration writes the structure first.
