"""Black-Scholes and implied-volatility inversion.

Imports nothing but the standard library, and in particular no database driver — this module
must run for anyone who clones the repo, on a machine with none of the pipeline containers.
"""

import math


def _N(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def price(S, K, T, r, sigma, cp):
    """European option price. cp is 'C' or 'P'."""
    if T <= 0 or sigma <= 0:
        return max(0.0, S - K) if cp == "C" else max(0.0, K - S)
    d1 = (math.log(S / K) + (r + sigma * sigma / 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    if cp == "C":
        return S * _N(d1) - K * math.exp(-r * T) * _N(d2)
    return K * math.exp(-r * T) * _N(-d2) - S * _N(-d1)


def implied_vol(observed, S, K, T, r, cp, lo=1e-4, hi=5.0, iters=80):
    """Invert by bisection. Returns None when the price implies no volatility.

    A price outside the no-arbitrage bounds is data about the print, not an error to paper over:
    returning None keeps those days out of the series instead of silently clamping them to a
    boundary value that would look like a real observation.
    """
    disc = K * math.exp(-r * T)
    intrinsic = max(0.0, S - disc) if cp == "C" else max(0.0, disc - S)
    cap = S if cp == "C" else disc
    if not (intrinsic + 1e-8 < observed < cap - 1e-8):
        return None
    if price(S, K, T, r, hi, cp) < observed:
        return None
    for _ in range(iters):
        mid = (lo + hi) / 2
        if price(S, K, T, r, mid, cp) < observed:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def realized_vol(closes, annualize=252):
    """Close-to-close realized volatility, annualized. `closes` in chronological order."""
    if len(closes) < 3:
        return None
    rets = [math.log(closes[i + 1] / closes[i]) for i in range(len(closes) - 1)]
    mu = sum(rets) / len(rets)
    var = sum((x - mu) ** 2 for x in rets) / (len(rets) - 1)
    return math.sqrt(var * annualize)
