"""Strike selection for defined-risk structures, with the day-count fixed in one place.

**The bug this module exists to prevent.** A trading plan drafted 2026-08-30 computed expected move
as `S * IV * sqrt(dte/252)` while every implied vol in this repo is inverted with `T = dte/365`
(`selection.py`, `live_iv.py`, and the frozen `iv_series_probe.py`). Mixing the two makes a genuine
20-delta strike appear to sit at 0.67x the expected move instead of 0.84x -- because
`sqrt(252/365) = 0.8309` and `0.8416 * 0.8309 = 0.699`.

That discrepancy was visible in the plan and was rationalised as a deliberately aggressive strike
rather than traced to its cause. It was caught by an outside reviewer, who read it as a broken delta
calculation; the delta was correct and the expected move was not.

So: **`DAY_COUNT` is defined once and used by both.** A strike solved for delta and the expected
move it is measured against cannot disagree about how long a day is.

The relationship is exact, which makes it a cross-check rather than a convention:

    |delta_put| = N(-d1),  and  d1 = ln(S/K) / (sigma*sqrt(T)) + (r/sigma + sigma/2)*sqrt(T)

so for a target delta the strike sits `N_inv(1 - delta)` standard deviations out, and the expected
move is one standard deviation. At 20 delta that is 0.8416. `verify_delta_em_consistency` asserts
it, and a day-count mismatch anywhere trips it immediately.
"""

import math

from .iv import greeks

# ONE definition. Both the expected move and every Black-Scholes time-to-expiry use it.
# 365 because that is the basis every IV in this repo was inverted on -- see the module docstring.
DAY_COUNT = 365.0


def _norm_ppf(p):
    """Inverse standard normal. Acklam's rational approximation, |error| < 1.15e-9."""
    a = [
        -3.969683028665376e01,
        2.209460984245205e02,
        -2.759285104469687e02,
        1.383577518672690e02,
        -3.066479806614716e01,
        2.506628277459239e00,
    ]
    b = [
        -5.447609879822406e01,
        1.615858368580409e02,
        -1.556989798598866e02,
        6.680131188771972e01,
        -1.328068155288572e01,
    ]
    c = [
        -7.784894002430293e-03,
        -3.223964580411365e-01,
        -2.400758277161838e00,
        -2.549732539343734e00,
        4.374664141464968e00,
        2.938163982698783e00,
    ]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e00, 3.754408661907416e00]
    pl, ph = 0.02425, 1 - 0.02425

    def _tail(q):
        num = ((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]
        den = (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1
        return num / den

    if p < pl:
        return _tail(math.sqrt(-2 * math.log(p)))
    if p > ph:
        return -_tail(math.sqrt(-2 * math.log(1 - p)))
    q = p - 0.5
    rr = q * q
    num = (((((a[0] * rr + a[1]) * rr + a[2]) * rr + a[3]) * rr + a[4]) * rr + a[5]) * q
    den = ((((b[0] * rr + b[1]) * rr + b[2]) * rr + b[3]) * rr + b[4]) * rr + 1
    return num / den


def years(dte):
    """Time to expiry in years, on the one basis this project uses."""
    return max(dte, 0.5) / DAY_COUNT


def expected_move(spot, iv, dte):
    """One standard deviation of the underlying over the holding period, in dollars.

    Uses `years()`, so it cannot drift from the Black-Scholes time used to solve for delta.
    """
    return spot * iv * math.sqrt(years(dte))


def em_multiple_for_delta(delta):
    """Driftless multiple: how many expected moves out a strike of this delta sits.

    0.8416 at 20 delta. Exact only as `T -> 0`; use `em_multiple_exact` for the real check.
    """
    return _norm_ppf(1.0 - abs(delta))


def em_multiple_exact(delta, iv, dte, cp, rate=0.04):
    """The same multiple carrying the Black-Scholes drift term.

    `d1` contains `(r + sigma^2/2)T`, which in expected-move units is `(r/sigma + sigma/2)*sqrt(T)`.
    It pushes puts CLOSER to spot and calls FURTHER out, so the driftless 0.8416 is symmetric and
    the truth is not. At 2 DTE the shift is under 0.02; at 30 DTE it is ~0.12, which is what made a
    tolerance built on the driftless figure fail there.

    Distance is measured in log terms, `ln(S/K)`, because that is what `d1` contains.
    """
    T = years(dte)
    drift = (rate / iv + iv / 2) * math.sqrt(T)
    d1 = _norm_ppf(1.0 - abs(delta))
    return (d1 - drift) if cp == "P" else (d1 + drift)


def strike_at_delta(spot, iv, dte, target_delta, cp, rate=0.04, grid=1.0):
    """Nearest listed strike to `target_delta`, solved from Black-Scholes, not from an EM multiple.

    Solving from delta and *checking* against the expected move is what makes the two independent.
    Solving the strike from an EM multiple and labelling it in delta hides exactly the defect this
    module was written for.
    """
    T = years(dte)
    target = abs(target_delta)
    if cp == "P":
        lo, hi = spot * 0.5, spot
    else:
        lo, hi = spot, spot * 1.5
    for _ in range(100):
        k = (lo + hi) / 2
        d = abs(greeks(spot, k, T, rate, iv, cp)["delta"])
        if cp == "P":
            lo, hi = (k, hi) if d < target else (lo, k)
        else:
            lo, hi = (lo, k) if d < target else (k, hi)
    exact = (lo + hi) / 2
    return round(exact / grid) * grid


def verify_delta_em_consistency(spot, iv, dte, target_delta, cp, rate=0.04, tol=0.08):
    """Assert the solved strike sits where its delta says it should, in expected-move units.

    Returns (ok, actual_multiple, expected_multiple). A day-count mismatch between `expected_move`
    and the Black-Scholes time shows up here as roughly a 0.83x or 1.20x scaling, far outside tol.
    """
    k = strike_at_delta(spot, iv, dte, target_delta, cp, rate, grid=0.01)
    # Log distance, matching what d1 is built from. Equals (S-K)/S to first order for small moves.
    actual = abs(math.log(spot / k)) / (iv * math.sqrt(years(dte)))
    want = abs(em_multiple_exact(target_delta, iv, dte, cp, rate))
    return abs(actual - want) <= tol, actual, want
