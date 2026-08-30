# Pre-registration — do 4-leg condor orders actually fill?

**Written 2026-08-30, before Monday's open.** Decides whether the judged book trades iron condors
or paired verticals. Runs 09:45–10:00 ET, Mon 31 Aug, before any sized entry.

## Why this is unmeasured and load-bearing

4-leg multi-leg orders are **verified accepted** — an order id came back with four legs echoed on
2026-08-30 — but **never verified filling**. Everything we know about fills here comes from two-leg
verticals on 2026-08-26:

| | outcome |
|---|---|
| SPY, 3¢ legs, mid limit, entry | filled **better than mid**, 127 ms |
| SPY, mid limit, exit | filled better than mid, 5.4 s |
| AMD, 14–66¢ legs, mid limit, entry | filled **at the limit**, ~20 s |
| **AMD, mid limit, exit** | **never filled — rested 26 s, cancelled** |

Three of four cleared. The one that did not was on the widest book. **A condor crosses four legs
instead of two, so the probability all of them clear at a given limit is strictly worse**, and the
plan sizes 29 contracts on the assumption that it does.

## The probe

| | |
|---|---|
| when | 09:45–10:00 ET, Mon 31 Aug, before any sized entry |
| what | **one** SPY iron condor, **one** contract, 5-wide wings, ~20Δ shorts, Sep 2 expiry |
| limit | the mid credit computed by `submit_condor`, submitted as a negative net price |
| account | the judged account |
| walk | none on the probe. A single resting limit at mid, so the result is not confounded by walking |

## Recorded, whatever happens

- fill price, and **`vs_mid` and `vs_touch`** — the same two fields `execution.py` already records
- time from submission to fill or to cancel
- per-leg fill prices, to see whether legs clear unevenly
- the NBBO on all four legs at submission and immediately after — unreconstructable later, since
  there is no historical options quote endpoint

## Decision table, written before the run

| outcome | verdict | consequence |
|---|---|---|
| fills **within 20 s** at ≥ mid − 0.05 | **CONDORS** | run 4-leg as designed; record `vs_mid` as the cost estimate |
| fills **within 20 s** worse than mid − 0.05 | **CONDORS, WALKED** | 4-leg is viable but not at mid; limit-walk per §6.3 and re-price the ceiling on the achieved credit |
| **does not fill in 20 s** | **PAIRED VERTICALS** | fall back to two 2-leg orders submitted together — measured fill behaviour instead of unmeasured. Accept brief one-sided exposure; both wings are OTM at entry |
| **rejected** | **STOP** | a rejection at 09:45 is a platform problem, not a pricing one. Do not size into it |

## Stated in advance

**n = 1.** This is one order on one underlying in one session. It cannot establish a fill *rate*,
and nothing here should later be quoted as one. What it can do is distinguish "4-leg orders fill at
mid on a tight book" from "they do not", which is the only question the sizing decision turns on.

**A fill is not evidence the paper engine models queue position or adverse selection.** It does
neither. The probe measures what this simulator does, which is what our P&L will be scored on — not
what a live venue would do.

**The fallback is not a worse strategy.** Paired verticals carry the same strikes, the same risk and
the same P&L. The difference is two tickets instead of one, and a few minutes of one-sided exposure
if only one clears. The instrument is an execution detail; the exposure is the strategy.

## Cancel condition

If the probe rests unfilled for 20 seconds it is **cancelled, not walked**. A walked probe measures
the walk rather than the fill, and the walk is already specified separately.
