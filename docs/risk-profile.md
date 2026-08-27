# Risk profile

The limits in `src/risk.py` are per-position and they are not a risk profile. They cap what one
trade can lose. They say nothing about what the book is exposed to, and their arithmetic assumes the
positions are independent.

Reproduce everything here with `make risk` — it reads committed data, no credentials.

## The positions are not independent

| | |
|---|---:|
| mean pairwise daily-return correlation, 11 names, 580 sessions | **+0.409** |
| median | +0.390 |
| range | +0.171 to +0.675 |
| **10 equal positions behave like** | **2.14 independent bets** |
| 5 equal positions behave like | 1.90 independent bets |

The universe is mega-cap technology plus SPY. It was selected on measured IV-series quality, and
nothing in those criteria rewarded diversification — so it did not produce any.

**Worst common sessions in sample:**

| date | mean move | names down |
|---|---:|---|
| 2025-04-04 | −7.62% | **11 / 11** |
| 2025-04-03 | −7.15% | 10 / 11 |
| 2025-04-10 | −6.20% | **11 / 11** |
| 2024-08-02 | −5.66% | 10 / 11 |
| 2025-03-10 | −5.31% | **11 / 11** |

A book of ten short put spreads loses on every one of those days at once.

**So `max_loss × positions` is not the tail. It is a bad Tuesday in April.** The 20% total-risk cap
reads like ten independent 2% risks; it behaves closer to two 10% risks that move together.

## What the book is short

`src/risk_profile.py` computes aggregate exposure from Black-Scholes greeks — computed rather than
read, since greeks are OPRA-gated and absent from the API on this account.

A ten-position short put spread book carries:

- **negative delta** — it loses when the underlying falls, and every name falls together
- **negative vega** — it loses when implied volatility rises, which is what happens on those same days
- **negative gamma** — the delta gets worse as the move continues
- **positive theta** — the thing it is paid for

The plan named this early: *"short vega and gamma is this book's hidden exposure, the way beta was
the last one's."* All four exposures point the same way on a correlated selloff. The strategy is paid
in theta for carrying them, and there is no state where the payment arrives and the risk does not.

## Stress

`stress()` applies a first-order delta-vega shock, defaulting to **−7% with implied vol +10 points**.
That default is not invented: it is roughly what this universe did on 2025-04-04.

**It is deliberately crude and labelled so.** Greeks are local, and a 7% move with a 10-point vol
shock is well outside where a first-order approximation holds. It gives direction and rough
magnitude, not a valuation. The structure caps the true loss at defined risk regardless, and the
output reports that floor alongside the estimate.

## What this does not cover

- **No live book has ever been stressed.** These are computed exposures for a hypothetical
  ten-position book; the scheduled cycle has never placed an order.
- **The kill switch has never fired.** A 5% drawdown triggers flatten-and-stop, and that path is
  untested.
- **Gap risk is not modelled.** Defined risk bounds loss at expiry. Between now and expiry an
  assignment or an early exercise is not accounted for.
- **The correlation is in-sample**, measured over the same 580 sessions the signal was measured on,
  and correlations rise in exactly the selloffs that matter.

## What follows

The 2% and 20% caps are not wrong, but they are describing a book with more diversification than it
has. Two responses are available and both are decisions rather than fixes:

1. **Lower the total cap** so the correlated worst case sits where 20% was intended to put it.
2. **Keep the cap and state the exposure**, on the argument that a defined-risk book cannot lose more
   than its defined risk and 20% of equity is a survivable week.

Doing neither means the number in the config implies a diversification the measurement says is not
there.
