# Results — universe IV-series quality, and the universe decision

Characterization across the full candidate universe, plus the estimator diagnostic registered at
`ca30287` before it ran. **Neither run can change v1's or v2's gate verdicts.**

## Series quality, 13 candidates

| name | IV days | missing | med\|Δp\| | R | autocorr | S/M | gate |
|---|---|---|---|---|---|---|---|
| SPY | 249 | 0.4% | 4.91 | 0.17 | 0.886 | 0.46 | PASS |
| TSLA | 249 | 0.4% | 5.34 | 0.18 | 0.929 | 0.55 | PASS |
| NVDA | 249 | 0.4% | 3.97 | 0.14 | 0.909 | 0.58 | PASS |
| MSFT | 249 | 0.4% | 5.11 | 0.17 | 0.904 | 0.60 | PASS |
| AAPL | 249 | 0.4% | 5.56 | 0.19 | 0.912 | 0.62 | PASS |
| META | 249 | 0.4% | 6.35 | 0.22 | 0.933 | 0.66 | PASS |
| AMZN | 249 | 0.4% | 4.72 | 0.16 | 0.927 | 0.67 | PASS |
| INTC | 249 | 0.4% | 4.84 | 0.17 | 0.944 | 0.70 | PASS |
| AVGO | 207 | 17.2% | 5.56 | 0.19 | 0.802 | 0.74 | **CONDITIONAL** |
| GOOGL | 249 | 0.4% | 5.56 | 0.19 | 0.891 | 0.75 | PASS |
| AMD | 249 | 0.4% | 4.90 | 0.17 | 0.914 | 0.75 | PASS |
| MU | 241 | 3.6% | 6.35 | 0.22 | 0.854 | 0.91 | PASS |
| NFLX | 197 | 21.2% | 7.94 | 0.27 | 0.885 | 0.94 | **CONDITIONAL** |

**Coverage is solved** — 11 of 13 at 0.4% missing, all three registered criteria passing.
**Percentile persistence is uniform and strong** — R between 0.14 and 0.27 against 1.0 for noise.

## An eligibility filter that was proposed, tested, and discarded

`S/M ≤ 0.50` was floated as an eligibility gate. Applied, it leaves **exactly one name (SPY)**.

**That filter was not legitimate and the record should say why.** `S/M ≥ 0.5` was registered in v1 as
an *attribution rule for interpreting a failure* — never as an eligibility line. Repurposing it as
one was a decision made after v2's results, and it is not entitled to a pre-registered threshold's
authority.

It is also biased upward by construction: `S` compares IV from the **last trade** (near the close,
matched to the 16:00 spot) against IV from the **volume-weighted average** (spanning the session, not
matched). Part of what it measures is intraday drift, not measurement error.

## The diagnostic that settled it — reading registered before the run

Registered at `ca30287`: median `|p_c − p_vw|` ≤ 5 points → print choice immaterial, `S/M` invalid as
an eligibility gate. ≥ 15 → it matters. Between → ambiguous, conservative reading wins.

| name | days | med \|p_c − p_vw\| | p90 | max | reading |
|---|---|---|---|---|---|
| SPY | 186 | 2.38 | 8.73 | 24.68 | immaterial |
| NVDA | 186 | 2.38 | 7.94 | 24.62 | immaterial |
| TSLA | 186 | 2.45 | 9.64 | 49.21 | immaterial |
| AMZN | 186 | 3.17 | 10.32 | 33.33 | immaterial |
| INTC | 186 | 3.39 | 11.11 | 38.89 | immaterial |
| AAPL | 186 | 3.74 | 9.52 | 34.78 | immaterial |
| AMD | 186 | 3.78 | 11.90 | 54.76 | immaterial |
| MSFT | 186 | 3.97 | 12.31 | 45.12 | immaterial |
| META | 186 | 3.97 | 13.64 | 33.67 | immaterial |
| GOOGL | 186 | 3.97 | 14.29 | 37.30 | immaterial |
| MU | 178 | 4.76 | 19.84 | 51.33 | immaterial |
| AVGO | 144 | 4.76 | 19.84 | 78.57 | immaterial |
| NFLX | 134 | **5.75** | 18.25 | 46.83 | **ambiguous** |

**12 of 13 fall under the registered line.** The print choice moves the percentile ~2–5 points, against
a signal whose own daily move is ~5 and a noise level of 29.3. `S/M` was measuring drift, not
corruption.

**The tail is real and the median hides it.** p90 runs 8–20 points, maxima past 50. On roughly a tenth
of sessions the print choice moves the percentile enough to flip a selection.

## The decision

**Eligibility is the three gate criteria registered before any data was seen — not `S/M`.**

**Universe (11):** SPY · TSLA · NVDA · MSFT · AAPL · META · AMZN · INTC · GOOGL · AMD · MU

**Excluded (2), each for two independent reasons:**

| name | reason 1 | reason 2 |
|---|---|---|
| AVGO | CONDITIONAL on coverage (17.2%) | **prints 2 Sep, inside the judged window** |
| NFLX | CONDITIONAL on coverage (21.2%) | the only name the diagnostic calls **ambiguous** |

Two independent instruments selecting the same two names is the cut making itself.

**Per-day print-agreement filter replaces the per-name `S/M` filter.** Compute the percentile from
both estimators; if they disagree by more than a registered margin **on the day a position would be
opened**, skip that name that day. This targets the measured tail where it actually lives instead of
discarding a name permanently for a problem that bites 10% of the time. *The margin still needs
registering before first use.*

**`max_open_positions = 10`** — 20% total defined risk ÷ 2% per position. The live value is **0** and
the column default is **5**, both inherited from the shelved equity strategy and neither derived for
this book. Eleven eligible names cover ten positions with one spare, so the budget fills without
doubling up on a name.

## What this does not establish

Two names, then thirteen, over one 12-month window, all selected on **today's** liquidity and applied
to 2024 data — survivorship, disclosed. The inverter is still unvalidated against known-IV inputs.
And the per-day filter's margin is unregistered, so it is not yet usable.
