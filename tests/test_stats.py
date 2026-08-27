"""Measurement primitives.

The rules these encode each cost a wrong headline number here: rank correlation rather than linear,
Newey-West rather than a naive t on overlapping windows, and a recorded seed.
"""

import pytest

from src.measurement.stats import newey_west_t, permutation_p, rank, spearman


def test_rank_averages_ties():
    assert rank([10, 20, 20, 30]) == [1.0, 2.5, 2.5, 4.0]


def test_spearman_is_one_for_a_monotonic_relationship():
    assert spearman([1, 2, 3, 4, 5], [10, 20, 30, 40, 50]) == pytest.approx(1.0)


def test_spearman_is_minus_one_when_reversed():
    assert spearman([1, 2, 3, 4, 5], [50, 40, 30, 20, 10]) == pytest.approx(-1.0)


def test_spearman_ignores_the_shape_of_a_monotonic_transform():
    """Selection acts on ordering. Rank and linear correlation have read +0.0261 and +0.0011 on
    identical data in this project, which is why the registered statistic is the rank one."""
    xs = [1, 2, 3, 4, 5, 6, 7, 8]
    assert spearman(xs, [x**3 for x in xs]) == pytest.approx(1.0)


def overlapping(seed=7, n=400, window=5):
    """Overlapping forward windows, which is exactly what a 5-day forecast series is."""
    import random

    rng = random.Random(seed)
    noise = [rng.gauss(0.02, 1.0) for _ in range(n)]
    return [sum(noise[i : i + window]) for i in range(n - window)]


def test_newey_west_runs_lower_than_a_naive_t_on_overlapping_data():
    """Consecutive 5-day forecasts share four days; a naive t-statistic runs roughly double.

    Measured on this construction: naive 1.671, Newey-West at lag 21 0.815. A result reported on
    the naive figure would clear a 5% threshold that the corrected one does not come close to.
    """
    import statistics as st

    series = overlapping()
    naive = st.mean(series) / (st.stdev(series) / len(series) ** 0.5)
    corrected = newey_west_t(series, lag=21)
    assert naive == pytest.approx(1.671, abs=0.01)
    assert corrected == pytest.approx(0.815, abs=0.01)
    assert abs(corrected) < abs(naive) / 1.9


def test_newey_west_correction_grows_with_the_lag():
    series = overlapping()
    t = [abs(newey_west_t(series, lag=L)) for L in (0, 5, 21)]
    assert t[0] > t[1] > t[2]


def test_zero_lag_matches_the_naive_t():
    """With no correction applied the two must agree, or the correction is not what moved it."""
    import statistics as st

    series = overlapping()
    naive = st.mean(series) / (st.stdev(series) / len(series) ** 0.5)
    assert newey_west_t(series, lag=0) == pytest.approx(naive, rel=0.01)


def pooled_ic(d):
    """Rank IC pooled across days -- the shape the registered statistic takes."""
    sig = [x for s, _ in d for x in s]
    out = [x for _, o in d for x in o]
    return spearman(sig, out)


def aligned_days(n=20):
    """Signal and outcome perfectly ordered within each day: the strongest possible link."""
    return [([1.0, 2.0, 3.0, 4.0, 5.0], [1.0, 2.0, 3.0, 4.0, 5.0]) for _ in range(n)]


def test_permutation_shuffles_within_days_and_finds_a_real_link():
    actual, p = permutation_p(aligned_days(), pooled_ic, draws=200, seed=42)
    assert actual == pytest.approx(1.0)
    assert p < 0.01


def test_permutation_p_is_reproducible_from_its_seed():
    """Reseeding alone once moved a headline result across most of its own effect here."""
    a = permutation_p(aligned_days(), pooled_ic, draws=200, seed=42)
    b = permutation_p(aligned_days(), pooled_ic, draws=200, seed=42)
    assert a == b


def test_permutation_p_is_a_probability():
    _, p = permutation_p(aligned_days(), pooled_ic, draws=100, seed=1)
    assert 0.0 <= p <= 1.0


def test_permutation_p_cannot_reach_zero():
    """(hits + 1) / (draws + 1): a p of exactly zero would claim more resolution than draws give."""
    _, p = permutation_p(aligned_days(), pooled_ic, draws=100, seed=1)
    assert p >= 1 / 101


def null_days(seed, n=40):
    """Outcomes shuffled independently each day, so no name-to-outcome link survives."""
    import random

    rng = random.Random(seed)
    out = []
    for _ in range(n):
        o = [1.0, 2.0, 3.0, 4.0, 5.0]
        rng.shuffle(o)
        out.append(([1.0, 2.0, 3.0, 4.0, 5.0], o))
    return out


def test_the_test_is_calibrated_under_a_true_null():
    """A single null draw is not evidence of calibration -- one of them reads p 0.02.

    That is the point rather than a nuisance: with a thin cross-section, an honestly null signal
    clears a 5% threshold often enough that a single run proves nothing. So this checks the
    distribution across 40 independent nulls instead. A permutation that failed to shuffle would
    put every p at the floor and fail here immediately.
    """
    import statistics as st

    ps = [permutation_p(null_days(seed), pooled_ic, draws=200, seed=42)[1] for seed in range(40)]
    assert st.median(ps) > 0.25
    assert sum(p < 0.05 for p in ps) <= 10  # nominal 2/40; this bound catches a broken shuffle
