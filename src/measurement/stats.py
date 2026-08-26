"""Measurement primitives. Standard library only; no database driver.

Carried from a strategy that was measured, falsified and shelved. Each rule here cost a wrong
headline number to learn.
"""
import math, random

def rank(xs):
    """Average ranks, ties shared."""
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            r[order[k]] = avg
        i = j + 1
    return r

def spearman(a, b):
    """Rank correlation. Selection acts on ordering, so this is the statistic that matches the
    deployed objective — linear correlation does not."""
    if len(a) < 3:
        return None
    ra, rb = rank(a), rank(b)
    n = len(ra)
    ma, mb = sum(ra) / n, sum(rb) / n
    num = sum((ra[i] - ma) * (rb[i] - mb) for i in range(n))
    da = math.sqrt(sum((x - ma) ** 2 for x in ra))
    db = math.sqrt(sum((x - mb) ** 2 for x in rb))
    return num / (da * db) if da and db else None

def newey_west_t(xs, lag):
    """t-statistic robust to serial correlation.

    Overlapping forward windows share all but one observation, so a naive t runs roughly double.
    """
    n = len(xs)
    if n < 3:
        return None
    mu = sum(xs) / n
    d = [x - mu for x in xs]
    g0 = sum(v * v for v in d) / n
    s = g0
    for L in range(1, min(lag, n - 1) + 1):
        g = sum(d[i] * d[i + L] for i in range(n - L)) / n
        s += 2 * (1 - L / (lag + 1)) * g
    if s <= 0:
        return None
    return mu / math.sqrt(s / n)

def permutation_p(daily, stat_fn, draws=1000, seed=42):
    """Empirical p-value by shuffling the signal WITHIN each day.

    Preserves the cross-sectional distribution and the time structure; destroys only the
    name-to-outcome link. With a thin cross-section the asymptotics are not trustworthy on their
    own. The seed is a parameter and gets recorded: reseeding alone has previously moved a headline
    result across most of its own effect.
    """
    rng = random.Random(seed)
    actual = stat_fn(daily)
    if actual is None:
        return None, None
    hits = 0
    for _ in range(draws):
        shuffled = []
        for sig, out in daily:
            s2 = list(sig)
            rng.shuffle(s2)
            shuffled.append((s2, out))
        v = stat_fn(shuffled)
        if v is not None and v >= actual:
            hits += 1
    return actual, (hits + 1) / (draws + 1)
