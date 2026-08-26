# Results — IV-series probe v2

Registration `bb633d6`, committed before this ran. `--select strict` was re-run first and
**reproduced v1 exactly** (SPY 248/250, 0.8%, R 0.17, ac 0.885; AMD 157/250, 37.2%, R 0.19,
ac 0.867) — the selection rewrite did not disturb v1's numbers.

| | v1 missing | v2 missing | v1 `S/M` | v2 `S/M` | v2 median\|Δp\| | v2 autocorr | **v2 gate** |
|---|---|---|---|---|---|---|---|
| SPY *(control)* | 0.8% | **0.4%** | 0.46 | 0.46 | 4.91 | 0.886 | **PASS** |
| AMD *(the failure)* | **37.2%** | **0.4%** | 0.60 | **0.75** | 4.90 | 0.914 | **PASS** |
| NFLX *(out-of-sample)* | — | 21.2% | — | **0.94** | 7.94 | 0.885 | **CONDITIONAL** |
| AVGO *(out-of-sample)* | — | 17.2% | — | **0.74** | 5.56 | 0.802 | **CONDITIONAL** |

## The hypothesis is confirmed

AMD's missing-day share fell **37.2% → 0.4%**. v1 was measuring **strike-level** sparsity and
reporting it as **name-level** coverage: on most sessions a perfectly good bar existed one strike
increment away from the one v1 insisted on. The liquid control barely moved (0.8% → 0.4%, R and
autocorrelation unchanged to three digits), so the rule does not distort a name that never needs to
walk.

## The registration under-specified the outcome space — again

v2 registered three consequences: AMD passes and both out-of-sample names pass · AMD passes and they
fail · AMD still fails. **The realized outcome is none of them** — the out-of-sample names came back
**CONDITIONAL**, which is neither.

This is the **second consecutive registration** to omit the outcome that actually occurred (v1's
attribution rule did not cover a coverage failure). The pattern is worth naming: the thresholds have
been carefully pre-registered while the *decision table over them* has not. Recorded, not patched.

**Read conservatively, since no registered branch fires:** this is **not** pure fitting — AMD's
improvement is two orders of magnitude, the control is undisturbed, and both out-of-sample names
improved into CONDITIONAL rather than staying at FAIL. But it is **not the clean generalisation**
that would have opened the gate either. Mid-liquidity coverage remains materially worse than liquid.

## Buying coverage cost measurement quality — visible in the numbers

`S/M` is the divergence between inverting from `c` and from `vw`, as a fraction of the daily IV move.
v1 registered `S/M ≥ 0.5` as "measurement noise dominates".

| name | v1 → v2 `S/M` |
|---|---|
| SPY | 0.46 → 0.46 *(rarely walks; undisturbed)* |
| AMD | 0.60 → **0.75** |
| NFLX | — → **0.94** |
| AVGO | — → **0.74** |

**This is the expected cost of the v2 rule and it shows up exactly where predicted.** Walking away
from the nearest strike means selecting lower-vega contracts, where the same price uncertainty
implies more IV. Coverage was bought with measurement quality.

At NFLX's **0.94**, the divergence between two ways of pricing the *same day* is nearly the size of
the day-to-day move the signal reads. **All three headline criteria pass for NFLX, and the series is
still mostly measurement artifact.** That is a case the three criteria cannot see, and it is the
strongest argument in this document against trusting the gate.

## What the week should conclude

1. **A usable IV series is buildable** — for SPY and AMD, cleanly.
2. **Mid-liquidity coverage is real but degraded** — NFLX and AVGO sit at 17–21% missing.
3. **The binding constraint is no longer coverage, it is measurement noise at mid-liquidity names**,
   and no selection rule fixes that — it is a property of inverting IV from daily last-trade prices.
4. **No v3.** Per the v2 registration, the next move is a strategy decision, not a third rule.
