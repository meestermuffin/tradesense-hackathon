"""Portfolio risk profile — what the book is short, and what happens when it all moves together.

The limits in `risk.py` are per-position: max loss 2% of equity, 20% total, 10 positions. Those are
correct and they are not a risk profile. They say nothing about **what** the book is exposed to, and
they assume the positions are independent.

Measured on this universe over 581 sessions, they are not. Mean pairwise daily-return correlation is
**+0.409**, which puts the effective number of independent bets among 10 equally-weighted positions
at roughly **2.2**. On 3, 4 and 10 April 2025 every one of the eleven names fell together, 6-7.6% on
the day. A book of ten short put spreads has ten positions and about two bets.

So `max_loss x positions` is not a tail scenario for this book. It is a bad Tuesday.
"""

from .models import BookPosition, BookProfile, Exposure, StressResult
from .options.iv import greeks

CONTRACT_MULTIPLIER = 100

# Measured, not assumed. scripts/risk_correlation.py recomputes both from the committed IV series.
MEAN_PAIRWISE_CORRELATION = 0.409
CORRELATION_SESSIONS = 581


def effective_bets(n, rho=MEAN_PAIRWISE_CORRELATION):
    """How many independent positions `n` correlated ones behave like."""
    if n <= 1:
        return float(n)
    return n / (1 + (n - 1) * rho)


def position_exposure(spot, short_strike, long_strike, iv, T, r, cp, contracts) -> Exposure:
    """Net greeks for one vertical, signed for a short-premium structure."""
    s = greeks(spot, short_strike, T, r, iv, cp)
    lo = greeks(spot, long_strike, T, r, iv, cp)
    mult = CONTRACT_MULTIPLIER * contracts
    return Exposure(**{k: (lo[k] - s[k]) * mult for k in ("delta", "gamma", "vega", "theta")})


def book_profile(positions: list[BookPosition], equity) -> BookProfile:
    agg = {
        k: sum(getattr(p.exposure, k) for p in positions)
        for k in ("delta", "gamma", "vega", "theta")
    }
    n = len(positions)
    worst = sum(p.max_loss for p in positions)
    return BookProfile(
        positions=n,
        effective_bets=round(effective_bets(n), 2),
        net_delta=round(agg["delta"], 1),
        net_gamma=round(agg["gamma"], 4),
        net_vega=round(agg["vega"], 1),
        net_theta=round(agg["theta"], 1),
        defined_risk=round(worst, 2),
        defined_risk_pct=round(100 * worst / equity, 2) if equity else None,
        # The number the per-position cap does not give you: everything hitting max loss at once is
        # what a correlated selloff looks like, and correlation says that is not a rare state.
        correlated_worst_case_pct=round(100 * worst / equity, 2) if equity else None,
    )


def stress(
    positions: list[BookPosition], equity, vol_points=10.0, underlying_move_pct=-7.0
) -> StressResult:
    """First-order shock. Deliberately crude, and labelled as such.

    Greeks are local. A 7% move with vol up 10 points is well outside where a delta-vega
    approximation holds, so this is a direction-and-rough-magnitude tool, not a valuation. The
    -7% default is not arbitrary: it is what this universe actually did on 2025-04-04, when all
    eleven names fell together.
    """
    vega = sum(p.exposure.vega for p in positions)
    spot_pnl = sum(p.exposure.delta * p.spot * (underlying_move_pct / 100.0) for p in positions)
    vega_pnl = vega * vol_points
    total = spot_pnl + vega_pnl
    capped = -sum(p.max_loss for p in positions)
    return StressResult(
        scenario=f"underlying {underlying_move_pct:+.1f}%, implied vol {vol_points:+.0f} points",
        delta_pnl=round(spot_pnl, 0),
        vega_pnl=round(vega_pnl, 0),
        first_order_pnl=round(total, 0),
        floor_from_defined_risk=round(capped, 0),
        pct_of_equity=round(100 * max(total, capped) / equity, 2) if equity else None,
        note="first-order only; the structure caps loss at the floor regardless",
    )
