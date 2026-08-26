"""Risk limits for the options book.

**The equity strategy's percentage price stop must not carry over.** On a short credit spread it
closes at the local worst price during an IV spike, on a position that would often have expired
worthless — converting a variance-premium strategy into one that buys volatility back at its most
expensive. Max loss is already bounded by the structure; that is the point of using verticals.

Exits are: structural max loss (defined at entry), the portfolio kill switch, time, and liquidity.
"""

import datetime
import math

from .models import Account, PortfolioState, Position, Spread
from .universe import (
    KILL_SWITCH_DRAWDOWN_PCT,
    MAX_LOSS_PER_POSITION_PCT,
    MAX_OPEN_POSITIONS,
    MAX_TOTAL_DEFINED_RISK_PCT,
)

CONTRACT_MULTIPLIER = 100
FEE_PER_CONTRACT_LEG = 0.025  # measured twice, exact both times, 2026-08-26


def defined_risk(width, credit, contracts):
    """Worst case for one vertical, in dollars, before fees."""
    return max(0.0, (width - credit)) * CONTRACT_MULTIPLIER * contracts


def round_trip_fees(contracts, legs=2):
    """Open and close, both legs each way."""
    return FEE_PER_CONTRACT_LEG * legs * 2 * contracts


def size_position(equity, width, credit):
    """Largest contract count whose defined risk stays inside the per-position cap."""
    per_contract = max(0.0, width - credit) * CONTRACT_MULTIPLIER
    if per_contract <= 0:
        return 0, "structure has no defined risk — refusing to size"
    cap = equity * MAX_LOSS_PER_POSITION_PCT
    n = int(math.floor(cap / per_contract))
    if n < 1:
        return 0, f"one contract risks ${per_contract:.0f}, over the ${cap:.0f} per-position cap"
    return n, None


def check_entry(
    candidate: Spread,
    equity,
    held,
    existing_risk,
    high_water,
    earnings_dates=None,
    as_of=None,
    deadline=None,
):
    """Return (contracts, [reasons to refuse]). An empty reason list means the trade may go.

    `held` is the set of underlyings already open. It was a list of one-key dicts built at the call
    site purely so this function could read `["underlying"]` back out of it.
    """
    as_of = as_of or datetime.date.today()
    reasons = []

    drawdown = 0.0 if high_water <= 0 else (high_water - equity) / high_water
    if drawdown > KILL_SWITCH_DRAWDOWN_PCT:
        reasons.append(
            f"kill switch: drawdown {drawdown * 100:.1f}% over "
            f"{KILL_SWITCH_DRAWDOWN_PCT * 100:.0f}% — flatten, open nothing"
        )

    held = set(held)
    if len(held) >= MAX_OPEN_POSITIONS:
        reasons.append(f"{len(held)} open, cap is {MAX_OPEN_POSITIONS}")

    sym = candidate.underlying
    if sym in held:
        reasons.append(f"already holding {sym} — doubling up concentrates the risk the cap spreads")

    n, why = size_position(equity, candidate.width, candidate.credit_mid)
    if why:
        reasons.append(why)
        n = 0

    if n:
        new_risk = defined_risk(candidate.width, candidate.credit_mid, n)
        if existing_risk + new_risk > equity * MAX_TOTAL_DEFINED_RISK_PCT:
            reasons.append(
                f"total defined risk ${existing_risk + new_risk:.0f} would exceed "
                f"{MAX_TOTAL_DEFINED_RISK_PCT * 100:.0f}% of ${equity:.0f}"
            )

    expiry = candidate.expiry
    if deadline and expiry > deadline:
        reasons.append(f"expires {expiry} past the deadline {deadline}")

    for d in (earnings_dates or {}).get(sym, []):
        ed = datetime.date.fromisoformat(d)
        if as_of <= ed <= expiry:
            reasons.append(f"{sym} reports {d}, inside the holding window to {expiry}")
            break

    return (0 if reasons else n), reasons


def portfolio_state(account: Account, positions: list[Position]) -> PortfolioState:
    return PortfolioState(
        equity=account.equity,
        last_equity=account.last_equity if account.last_equity is not None else account.equity,
        open_count=len(positions),
    )
