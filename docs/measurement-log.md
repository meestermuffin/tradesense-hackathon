# Measurement log — 26 August 2026

Every measurement below was written down and committed **before** it ran. The registration commit is
an ancestor of its own results commit in all six cases, so the ordering is checkable against the git
history rather than asserted:

```bash
git merge-base --is-ancestor 7fe2797 294bc93 && echo "registered first"
```

The registration documents themselves were folded into this log; their original text is in
the commits cited above. `scripts/iv_series_probe.py` still points at the old paths in its
docstring and is left that way deliberately — two registrations name that file **and its
commit**, so it is kept byte-identical rather than tidied.

Read top to bottom — it is roughly chronological, and several entries only make sense as corrections
to the one above them.

---

## 1 · Is a per-name IV series buildable at all? · `886486f` → `e5fb308`

The signal ranks on IV percentile against a name's own history, which needs a daily IV series. Alpaca
returns no implied volatility to this account, so IV is computed by Black-Scholes inversion from
option bar closes — a last-trade price at an unknown intraday time, paired with a 16:00 underlying
close.

**Registered first.** Two-stage, so thresholds could not be chosen after seeing the distribution they
judge: stage 1 characterised the chain and was *barred from issuing a verdict*; only stage 2 could.
Moneyness band 0.95–1.05, staleness filter `n ≥ 10` and `v ≥ 50`, percentile over a trailing 126
sessions with a minimum of 63 observations.

The percentile threshold is **derived, not chosen**. For a percentile resampled independently each
day, median day-over-day change is exactly `100(1 − √2⁄2) = 29.29` points. That is what a dead signal
produces, so the criterion is stated as a ratio to it.

**Result.**

| | SPY | AMD |
|---|---|---|
| missing-day share | 0.8% **PASS** | 37.2% **FAIL** |
| median \|Δpercentile\| | 4.95 (R = 0.17) **PASS** | 5.56 (R = 0.19) **PASS** |
| lag-1 autocorrelation, log IV | 0.885 **PASS** | 0.867 **PASS** |

Stage 1 found the chain **denser** than assumed, so no filter was loosened and no degrees of freedom
were spent between stages. The `n:1` sparsity that motivated the whole concern came from a deep-ITM
contract with open interest 1; near-ATM 30-DTE bars trade ~100×/day. **The moneyness restriction was
the load-bearing decision.**

**A defect in the registration, recorded rather than patched.** The attribution instrument was written
to separate "signal dead" from "filter harder" on a *noise* failure. AMD failed on **coverage**, where
filtering harder is counterproductive. The registered remedy did not apply to the failure that
occurred.

---

## 2 · Was AMD's failure strike-level or name-level? · `41ebf11` → `57e6747`

**Registered first, and the post-hoc freedom named as one.** v1 demanded the single nearest-ATM
strike. v2 walks in-band strikes until one has a bar passing the filter. That change was chosen after
seeing a failure, which cannot be undone — so thresholds were held character-for-character, exactly
one parameter moved, and **two names v1 never touched (NFLX, AVGO) were added** so the rule could not
be judged only on the name whose failure motivated it.

**Result.** `--select strict` reproduced v1 exactly before v2 ran.

| | v1 missing | v2 missing | v1 `S/M` | v2 `S/M` | v2 gate |
|---|---:|---:|---:|---:|---|
| SPY *(control)* | 0.8% | 0.4% | 0.46 | 0.46 | PASS |
| AMD *(the failure)* | **37.2%** | **0.4%** | 0.60 | **0.75** | PASS |
| NFLX *(out-of-sample)* | — | 21.2% | — | **0.94** | CONDITIONAL |
| AVGO *(out-of-sample)* | — | 17.2% | — | **0.74** | CONDITIONAL |

v1 measured *strike-level* sparsity and reported it as *name-level* coverage. But **no registered
branch fired** — v2 named three outcomes and the out-of-sample names came back CONDITIONAL, which was
none of them. Second registration in a row to omit the outcome that occurred.

**Coverage was bought with measurement quality, exactly where predicted.** Walking off the nearest
strike selects lower-vega contracts, where the same price uncertainty implies more IV.

---

## 3 · Which names are eligible? · `e9b9aa8` → `57a98fd`

An `S/M ≤ 0.50` eligibility filter was floated. Applied, it leaves **exactly one name**.

**That filter was not legitimate, and the record says so.** `S/M ≥ 0.5` was registered as an
*attribution rule for reading a failure*, never an eligibility line, and it is biased upward by
construction: it compares IV from the last trade (near the close, matched to the 16:00 spot) against
IV from the volume-weighted price (spanning the session, unmatched). Part of what it measures is
intraday drift.

**Registered before running:** median `|p_c − p_vw|` ≤ 5 points → print choice immaterial and `S/M`
invalid as a gate; ≥ 15 → it matters; between → conservative reading wins.

**Result:** 2.38–4.76 points for **12 of 13 names**, against a signal whose own daily move is ~5
points and a noise level of 29.3. NFLX alone came back ambiguous at 5.75.

**Universe decided — 11 names**, on the three criteria registered before any data was seen:

> SPY · TSLA · NVDA · MSFT · AAPL · META · AMZN · INTC · GOOGL · AMD · MU

AVGO and NFLX excluded, each on two independent grounds — coverage CONDITIONAL for both, plus AVGO
reporting inside the judged window and NFLX being the only name the diagnostic called ambiguous. Two
instruments agreeing on the same two names is what makes the cut defensible.

**The tail survives the pass.** p90 of `|p_c − p_vw|` runs 8–20 points: on roughly a tenth of
sessions the print choice moves the ranking enough to flip a selection.

---

## 4 · Does the premise hold? · `79224da` → *voided* `4d1aff1` → `4d1aff1`

**The first run was voided for a defect in its own statistic.** Outcome was `IV_t − RV_forward` and
both signals were functions of `IV_t`, so it entered both sides positively — the statistic measured
itself. It returned IC 0.16 at p 0.001 and meant nothing. **This would have shipped a headline
number.**

Re-registered with a scale-free outcome, `(IV_t − RV_fwd)/IV_t` — the return on premium sold — and a
**control arm**: raw IV level, which is not a strategy but a measurement of how much of any IC is
available from the level alone.

**Result.** 1,807 name-days, 165 sessions, 11 names.

| variant | mean IC | NW t(21) | permutation p |
|---|---:|---:|---:|
| **A · IV percentile vs own history** | **+0.1753** | 2.45 | **0.0010** |
| B · IV ÷ trailing 21d RV | +0.2727 | 4.57 | 0.0010 | 
| **C · raw IV level** *(control)* | **−0.1055** | −1.48 | 1.0000 |

**B is confounded and is not evidence.** Trailing and forward 21-day realized vol rank-correlate at
**+0.8166** here, so `B = IV/RV_trail` and `outcome = 1 − RV_fwd/IV` collapse toward a deterministic
monotone pair. Same defect class as the voided run.

**A survives, and the control is why.** A carries no realized-vol term. The only term it shares with
the outcome is `IV_t` in the denominator, and the control measures that channel as **negative** — so
A's result is achieved *against* it, not because of it. Selling the highest absolute IV is mildly
harmful; selling the highest IV relative to a name's own history is not.

---

## 5 · Is it just an earnings detector? · `f66bc9e` → `f66bc9e` → `bc9c1aa`

The strongest external objection: a large share of "this name's IV is unusually high" is earnings
approaching, and if that is what the ranking detects, filtering earnings out does not protect the
strategy — it deletes it.

Earnings dates from **SEC 8-K filings carrying Item 2.02**, where the filing date *is* the
announcement date. 67 announcements. SPY correctly returns zero, which checks the extraction.

**The first version was underpowered and the log says so.** The ±2 session window came from
`earnings_blackout_days`, a *risk* parameter about when it is unwise to hold a position. The outcome
measures volatility over the next 21 sessions, so an announcement sits inside it even when the entry
is weeks away.

| | share of name-days |
|---|---:|
| forward window contains an announcement | **35.8%** |
| removed by the ±2 exclusion | **7.4%** |

**Powered test registered separately**, excluding every name-day whose forward outcome window contains
an announcement.

| | name-days | A | permutation p | NW t(21) |
|---|---:|---:|---:|---:|
| baseline | 1,807 | +0.1753 | 0.0010 | 2.45 |
| ±2 sessions removed | 1,674 | +0.1831 | 0.0010 | 2.41 |
| **forward window event-free** | **1,145** | **+0.1561** | **0.0010** | 1.69 |

**The ranking is not a scheduled-event detector.** 36.6% of the sample removed and the IC holds, with
the permutation p at the floor — the observed IC exceeded all 1,000 within-day shuffles. The
Newey–West t falls to 1.69, which is what removing a third of a sample does to a standard error and
is reported rather than buried; the registration named the permutation null as primary because a
daily Spearman over 11 names has no trustworthy asymptotics.

---

## 6 · What does execution actually cost? · `79224da`, `f66bc9e`, `b4853b6` → `ee4ff5d`

Alpaca serves **no historical options quotes**. Four paths 404 against a 200 control on `quotes/latest`,
and their catalogue lists *Historical bars* and *Historical trades* but only *Latest quotes*. That is
a product boundary. It does **not** mean the data does not exist — OPRA history is sold commercially
and was ruled out here on cost, licensing and time.

**Measured directly instead.** Two live round trips, NBBO captured per leg before and after each
submit, because it cannot be reconstructed afterwards.

| | leg spreads | limit | fill | vs mid | vs touch |
|---|---|---|---|---:|---:|
| SPY 755/750 entry | 3¢ | net mid | 0.620 cr | **+0.010** | +0.040 |
| SPY exit | 3¢ | 0.67 | 0.670 db | +0.005 | +0.060 |
| AMD 475/470 entry | 14–66¢ | net mid | 1.850 cr | 0.000 | — |
| AMD exit at mid | — | 1.78 | **never filled** | — | — |
| AMD exit crossed | — | 2.47 | 2.300 db | **−0.315** | +0.070 |

**Fills clear better than the touch by a small absolute amount that does not scale with spread width**,
and on a wide book a mid-priced order may not fill at all. The second clause is what changes how the
book is operated: fill probability for patient orders is unmeasured, which is why the cost model
charges the marketable cost on every fill regardless.

Fees resolved exactly: **$0.025 per contract-leg**, identical residual across two trades differing 9×
in notional.

### The historical-cost route, opened and then closed

Bar-derived spread proxies failed — cross-name rank correlation **+0.036** against measured NBBO.
Roll's estimator on trade sequences reached **+0.500**, which looked like a route.

**Two problems.** It was reported from an uncommitted script, so nobody could reproduce it — the
standing commit-before-run rule, broken the same day it was quoted in the file the result went into.
Now committed, and it reports its permutation p, which is **0.0604**: a lead, not a finding.

And a regime probe, **registered with a 10-point threshold before it ran**, returned 40.7:

| realized range quartile | range | Roll estimable |
|---|---|---:|
| Q1 calmest | 0.34–1.27% | **70.4%** |
| Q4 most volatile | 6.10–14.40% | **29.6%** |

Roll needs bid-ask bounce to dominate drift, and a volatility expansion *is* drift. **It is blind by
construction in the regime where a short-vega book takes its losses** — which is the regime a judge
would most want costed. That also breaks the imputation rule registered an hour earlier, since on
volatile days 70% of contract-days would draw an imputed value from a distribution composed almost
entirely of calm days.

**No backtested return is quotable.** That is the operative conclusion and it has not moved all day.

---

## What this log does not establish

- **No backtested P&L.** The spread estimator is unfitted and the one historical route is blind in
  the loss regime.
- **The structure and strike selection have never been reviewed.**
- **The scheduled cycle has never placed an order** — both round trips were placed by hand.
- **Survivorship.** The 11 names were chosen on 2026 liquidity and applied to 2024–25 data.
- **Wrong tenor.** A 30-day reference series stands in for a 5–9 day traded structure, deliberately
  and untested.
- The IC has not been re-run on the 30-month series, which is 2.4× the data.

## Registration defects, all found by self-audit

| | |
|---|---|
| v1's attribution rule | covered a noise failure; the failure was coverage |
| v2's decision table | omitted CONDITIONAL, the outcome that occurred |
| the IC statistic | shared a term with its own outcome — **would have shipped a number** |
| the Roll imputation rule | assumed a spread effect; it is a regime effect |

The pattern is consistent and worth naming: thresholds were registered carefully, and the structure
around them — the decision table, and whether the statistic matches the objective — was not.


---

## 2026-08-27 — the permutation null was 2.7× too narrow, and the IC is WEAK

**Registration:** `docs/2026-08-27-block-permutation-registration.md`, committed at `8a45517`
before the run. Raised by Solo. **Script:** `scripts/block_permutation.py`.

This re-tests the *significance* of the baseline IC. It does not touch the point estimate.

### The defect

`permutation_p` shuffles the signal among names **within each session**, which breaks the
name-to-outcome link but leaves both panels' time structure intact. The outcome is realized
volatility over the **next 21 sessions** on daily data, so consecutive name-days share 20 of their
21 outcome days. A null more independent than the data has too narrow a spread and returns a p that
is too small.

The record already showed it. Every published row read p = 0.0010, the floor at 1,000 draws,
including the event-free row where Newey–West falls to **1.69** — about p 0.09 two-sided. A p-value
that cannot distinguish a t of 2.45 from a t of 1.69 is not measuring anything.

165 sessions at a 21-session horizon is roughly **7 independent windows**, not 1,807.

### First design VOID — its own control caught it

The primary null registered at `f898dea` was an exhaustive circular time shift. It came back with
control C **significant** (p 0.0081), which the registration had named as the stop condition.

The shift rotates a name's signal in time and pairs it with **that same name's** outcome. Name
identity survives, so it tests *the association lagged*, not *no association*. Measured, it centres
at −0.0470 on A and −0.1915 on C where a valid null centres at zero; C only scored "significant"
because its actual of −0.1055 sat at the top of a null dragged downward.

**Four registration defects have now been caught by their own registrations rather than by review.**

### Corrected null — block-constant name permutation

Permute the name labels as the within-day shuffle does, but hold one permutation fixed across a
contiguous block of `L` sessions. Breaks the pairing *and* keeps the day-to-day persistence the
overlap creates. `L=1` reduces to the published shuffle. **L=21 primary, 2,000 draws, seed
20260827.**

### Result

Variant A, event-free sample (1,145 name-days) — the row the book actually trades:

| | IC | NW t(21) | L=1 *(published)* | **L=21 primary** | L=42 | shift *(void)* |
|---|---:|---:|---:|---:|---:|---:|
| **A · IV percentile** | **+0.1561** | 1.69 | 0.0005 | **0.0660** | 0.0785 | ~~0.0081~~ |
| B · IV ÷ trailing RV | +0.2563 | 3.38 | 0.0005 | 0.0145 | 0.0130 | ~~0.1694~~ |
| C · raw IV level *(control)* | −0.0938 | −0.75 | 0.9940 | **0.7626** | 0.7556 | ~~0.0081~~ |

Baseline sample (1,807 name-days): A +0.1753, L=21 p **0.0100** — still significant there.
*(Erratum 2026-08-30: this read 0.0105, which is the L=42 column. The committed script deterministically prints 0.0100 at L=21. The coded anchor gate checks IC only, so no run was affected.)*

Null spread, variant A: sd 0.0387 at L=1 → **0.1042 at L=21**. The published null was **2.7× too
narrow** on the event-free sample, 3.0× on the baseline.

### Verdict — WEAK, per the table registered before the run

> 0.05 < p ≤ 0.20 → **may not be called significant anywhere; reported as suggestive, with both
> p-values shown.**

**+0.1561 stands as a measurement. Its significance does not.** The two corrections agree without
being related: Newey–West t 1.69 and block-permutation p 0.0660 both put it just outside
conventional significance, which is the finding.

The control behaved (p 0.7626), so the null is readable.

### What this changes

- The **p 0.0010 figure is withdrawn.** It was an artifact of a null too narrow by ~3×.
- +0.1561 may be shown as suggestive with both p's, never as significant.
- The baseline p 0.0100 survives, but the baseline includes name-days whose forward window contains
  an earnings announcement — the sample the event-free arm exists to exclude.
- **Nothing here rescues a backtest number.** Cost is still uncharged.


---

## 2026-08-27 — the cost bound: the edge is gone before cost is charged

**Registration:** `docs/2026-08-27-cost-breakeven-registration.md`, committed at `eb86625` before
the run. Proposed by Solo. **Script:** `scripts/cost_breakeven.py`.

Bound the cost rather than estimate it, because the estimate may not be buildable: no historical
option quotes, name identity dominates the spread, best bar proxy +0.036 cross-name.

### Measured round-trip cost, as a share of NET CREDIT

Crossing twice at the 82% of half-spread a marketable order actually paid, scaled by what a vertical
costs against its credit rather than against mid (9.7% SPY / 34% AMD, from the two test orders):

| SPY | TSLA | NVDA | AAPL | MSFT | AMZN | AMD | META | INTC | GOOGL | MU |
|---|---|---|---|---|---|---|---|---|---|---|
| 7.7% | 12.2% | 13.0% | 24.1% | 25.7% | 27.3% | 28.9% | 38.0% | 41.1% | 41.6% | 44.8% |

**Erratum 2026-08-30.** This table read 15.3%–89.7%, exactly **2.00× too high**. The 9.7% (SPY) and
34% (AMD) calibrators are taken from complete round trips — both legs, both ways — and the code then
multiplied by two again. Found by review, not by us. The verdict is re-derived below and stands.

### Result — DOES NOT SURVIVE

Event-free, N=10: gross edge **−8.36%** of premium, measured cost **27.7%**, ratio **−0.30×**.
**No name clears 2×. The best is SPY at 0.55×.** *(Corrected for the 2.00× erratum above; the
figures first published were −0.15× and 0.29×.)*

### The registered statistic was the wrong one, and it does not change the verdict

The mean of `(IV−RV_fwd)/IV` is unbounded below, capped at +1 above, and explodes when `IV_t` is
small. Median **+2.72%** against a mean of −8.36%; minimum **−1732%**; the worst 5% average −237%.
A vertical caps loss at `width − credit` and cannot lose 1732% of its credit.

Flooring the loss: **−0.33%** at −100% of premium, **−1.89%** at −400% of credit.

**Under every flooring the gross edge is negative or indistinguishable from zero *before any cost is
charged*.** Cost is not the binding constraint, so trading only the tight names does not rescue it.

This also explains why the rank IC and this bound disagree without contradicting: rank IC is
invariant to the tail, and any mean-based statistic on the same outcome is dominated by it. They
were never measuring compatible quantities.

### Combined with the same day's null correction

- The IC is **WEAK** (p 0.0660, corrected null) — the ranking is suggestive, not significant.
- The **gross edge on the names it selects is ≈0 or negative before cost.**

**No backtest number is quotable, and the cost model is no longer the thing blocking it.** A
mean-based edge on this outcome needs its own registration with the structural cap specified before
any figure from it is quoted.


---

## 2026-08-27 — the signal does not replicate out-of-sample. WITHDRAWN.

**Registration:** `docs/2026-08-27-extended-ic-registration.md`, committed at `96c85ca` before the
run, anchor corrected at `7ce4f4e`. **Script:** `scripts/extended_ic.py`.

Every prior IC test used 249 sessions (~11 independent windows). The committed longer series has
597, and is a strict superset — all 2,731 overlapping rows byte-identical.

### Result

| arm | name-days | sessions | IC | NW t(21) | p | null sd |
|---|---:|---:|---:|---:|---:|---:|
| **anchor** · original 2024-03 → 2025-02 | 1,807 | 165 | **+0.1753** | 2.45 | 0.0100 | 0.0736 |
| **PRIMARY · A · out-of-sample 2025-03 → 2026-08** | **3,590** | **327** | **+0.0414** | **0.72** | **0.2184** | 0.0507 |
| C · out-of-sample *(control)* | 3,590 | 327 | −0.1425 | −1.80 | 0.9915 | 0.0602 |
| A · full series | 5,628 | 513 | +0.0931 | 2.04 | 0.0150 | 0.0411 |
| A · event-free through 2025-06 | 1,852 | 256 | +0.1432 | 2.30 | 0.0415 | 0.0814 |

The anchor reproduces the prior run exactly, so the panel is the same one.

### Verdict — NO EVIDENCE, per the table registered before the run

> p > 0.20 → **withdrawn. Signal work stops.**

**+0.1753 → +0.0414 on 327 sessions no test had touched.** Newey–West t 0.72. The control validates
the null at p 0.9915.

The full-series arm reads p 0.0150, but it *contains* the original window and is not independent
evidence. The event-free arm is likewise almost entirely the original period, since earnings data
stops 2025-06-25.

### What this settles

**The IV-percentile ranking does not replicate.** The original result was 11 independent windows,
and 15 fresh ones do not reproduce it. Combined with the same day's other two runs:

| | |
|---|---|
| significance on the original sample | WEAK (p 0.0660, corrected null) |
| **replication out-of-sample** | **NO EVIDENCE (p 0.2184)** |
| gross edge before cost | unresolved; the registered statistic priced the wrong structure |

**No signal claim survives.** Nothing in the deck, video or repo may assert predictive skill.

### The one thing that did not collapse

Raw IV level, the control, is **consistently harmful** and gets more so out-of-sample: −0.1055 →
−0.1425, t −1.80. Ranking each name against its own history stays above ranking on absolute IV in
every arm. **That gap has never been tested as a paired comparison** and is not a claim — but it is
the only structure in the data that persisted.

### Anchor defect, recorded

The first run halted on its own stop condition: the anchor returned +0.1839 on 2,038 name-days
instead of +0.1753 on 1,807. The difference was exactly 21 sessions × 11 names — the final `H`
sessions, unscoreable when the series ended in 2025-02 and scoreable on the longer one. Filtering
the long series to the original dates is not the original sample. The anchor now also requires the
forward window to close in-sample. **The primary result was printed before the stop condition was
evaluated and had been seen, so the re-run is recorded as confirmatory rather than exploratory; the
correction is adverse-neutral and the decision table never moved.**
