# Cost model — options execution

**Status: PROVISIONAL.** The execution rule is measured (n=2 round trips). The spread estimator is
**not yet fitted** and currently runs on a placeholder. **No backtest number computed with the
placeholder may be quoted in the deck, the video, the README or anywhere else** until the estimator
is fitted on captured NBBO. This document exists so that rule has something to point at.

## Why cost has to be estimated rather than charged

Alpaca serves **no historical options quote data**. Confirmed three ways: 404 on a live contract,
404 on an expired one, and absent from Alpaca's own endpoint catalogue, which lists historical
*bars* and *trades* and separately *latest* quotes.

**A backtest that charges bid/ask against history is charging against data that does not exist.** So
cost is modelled in two independent pieces:

| piece | what it answers | status |
|---|---|---|
| **spread estimator** | how wide was the book, on a past day nobody quoted | **unfitted — placeholder** |
| **execution rule** | what fraction of that spread you actually pay | **measured, n=2** |

Keeping them separate matters: the second is now measured and the first is not, and a single blended
"slippage" number would hide which half is evidence.

## The execution rule — measured 2026-08-26

Two round trips, paper account `PA382RL5C7X8`, NBBO captured at each submission (unreconstructable
afterwards). Raw evidence in `.claude/private/artifacts/2026-08-26-testorder{,-2}/`.

| | SPY 755/750 | AMD 475/470 |
|---|---|---|
| leg spreads | 0.03 / 0.03 | 0.14–0.66 |
| resting limit **at mid**, entry | **filled 0.620 vs 0.610 mid** (better than mid), 127 ms | **filled at the limit**, ~20 s |
| resting limit **at mid**, exit | filled 0.670 vs 0.675 mid, 5.4 s | **never filled** — rested 26 s, cancelled |
| **marketable** (crossed 0.10 through touch) | not tested | **filled 2.30**: 0.07 better than touch, **0.315 worse than mid**, 14 ms |

Two behaviours, and they must not be averaged:

**Patient orders resting at mid cost ≈ 0 versus mid — when they fill.** Three of four did. The one
that did not was on the widest book, and it did not fill at all in 26 seconds. **Fill probability for
patient orders is unmeasured**, and a strategy that assumes it is assuming the thing least in
evidence.

**Marketable orders fill instantly and pay most of the half-spread.** The single observation paid
**0.315 of a 0.385 half-spread = 82%**. Better than the touch, but not by much.

### The rule, stated conservatively

```
execution_cost_per_leg = 0.82 × half_spread          # fraction measured n=1
fees                   = 0.025 × legs × contracts    # measured n=2, exact both times
```

**The backtest charges the marketable cost on every fill, always.** This is deliberate and it is the
conservative direction: patient fills were sometimes free, so charging as if every order crossed can
only understate live performance. **Live may beat the backtest; it should not lose to it for
execution reasons.** That asymmetry is the point — the opposite error is the one that cannot be
defended to a judge.

### Fees are settled

Equity moved **−5.10** against a trade P&L of **−5.00**, and **−45.10** against **−45.00**. Residual
**−0.10** both times, on four contract-legs both times, across a 9× difference in notional.
Notional-independent, leg-count-dependent: **$0.025 per contract-leg**. `accrued_fees` and
`pending_reg_taf_fees` report **0** in both cases, so the charge is real but is not surfaced in the
fields that name fees — do not read it from the API, compute it.

## The spread estimator — NOT FITTED

This is the half with no evidence behind it, and it is the half the backtest is most sensitive to.

**Placeholder in use:** spread as a fixed percentage of option mid, from four contracts captured on
2026-08-26:

| contract | spread / mid |
|---|---|
| SPY 755P | 1.8% |
| SPY 750P | 2.8% |
| AMD 475P | 1.5%, later **5.1%** |
| AMD 470P | 1.3%, later 2.3% |

**n = 4 contracts, 2 underlyings, one afternoon, and the range within a single contract is 3×.** The
SPY short leg went 3¢ → 8¢ in 61 seconds; AMD's went 0.20 → 0.66. Any point estimate from this is
decoration.

### Attempted 2026-08-26, and it does not work from historical data

**132 NBBO quotes captured across all eleven universe names**, two tenors (9 and 30 DTE), six
near-ATM strikes each, at 15:50 ET. Evidence in
`.claude/private/artifacts/2026-08-26-nbbo-capture/nbbo_universe.json`.

Median spread as a share of mid, by name:

| SPY | TSLA | NVDA | AAPL | MSFT | AMZN | AMD | META | INTC | GOOGL | MU |
|---|---|---|---|---|---|---|---|---|---|---|
| 0.96% | 1.52% | 1.63% | 3.01% | 3.21% | 3.42% | 3.62% | 4.75% | 5.14% | 5.21% | 5.61% |

**A 6× range across the universe** — and GOOGL is wider than TSLA despite higher equity dollar
volume, which is the "equity volume is blind to spread width" caveat appearing in data.

**Attempt 1 — regress on price, tenor, moneyness.** In-sample R² 0.62 in log space. But
**leave-one-name-out error is 1.72× typical**, ranging 0.43× (INTC) to 3.68× (SPY). The observables
do not generalise across names; **name identity dominates**.

**Attempt 2 — proxy the spread from historical option bars**, which is what a backtest would actually
have. Prior-session bar statistics against the captured spread:

| proxy | vs absolute spread | vs spread % |
|---|---|---|
| bar close (price level) | +0.655 | +0.143 |
| (high − low), absolute | +0.536 | — |
| 1 / √(trade count `n`) | +0.464 | +0.374 |
| (high − low) / close | −0.227 | −0.068 |
| **cross-name, (h−l)/close vs spread%** | — | **+0.036** |

**No bar-derived proxy tracks the cross-name variation.** The one predictor that works at all — price
level — recovers the tick grid, which was never the hard part. The +0.036 cross-name correlation is
the number that closes this route.

### Consequence: a defensible leg-2 P&L number may not be reachable

The only remaining path is to capture NBBO forward through the live week, build per-name spread
distributions, and **assume 2026 per-name spread levels apply to 2024–25**. That assumption is
**untestable with available data** — there are no historical quotes to check it against, which is the
same absence that created the problem.

**So the honest position is to not quote a backtested P&L at all.** The evidence this project has is
the **rank-IC result**, which requires no cost model: it is measured on implied versus subsequent
realized volatility and charges nothing. Live P&L over the judged sessions is the other number, and
it is real by construction. A backtested return sitting between them, resting on an unfalsifiable
spread assumption, is the one figure a judge could take apart — and the plan has said so since the
24th.

**Known bias to carry:** any estimator fitted on *executed prints* rather than quotes understates the
cost of demanding liquidity, because prints are what traded, not what was offered.

## What this model does not cover

- **Fill probability for patient orders** — unmeasured, and the reason the rule charges as if every
  order crossed.
- **Size.** Both measurements were 1 lot. Paper does **not** check order size against NBBO quantity,
  so a 1-lot is the most favourable case that exists.
- **Assignment and early exercise.** Not modelled.
- **Alpaca's mark convention for open positions** — unresolved. Equity showed −35.05 unrealized where
  mid-based marking implies ≈−13.5 and touch-based ≈−52. This does not affect realised cost but it
  **does** affect the equity curve judges look at.
- **Whether the paper engine prices multi-leg fills off its own internal mid.** If it does, measuring
  "execution versus captured NBBO" is the simulator grading its own homework, and no amount of
  NBBO instrumentation can detect it. The honest phrase for what is measured is **"paper execution
  quality against captured NBBO"**, never "execution edge".
