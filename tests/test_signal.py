"""The look-ahead properties of the ranking.

These are the tests worth having. A signal that quietly sees its own outcome is the defect this
project has already had once -- a baseline IC of 0.16 where the outcome and both signals were
functions of the same IV_t, so the statistic measured itself. That was caught by review, not by
code. This is the code version of the same check.
"""

from src.options.signal import PCT_MIN_OBS, PCT_WINDOW, percentile_rank, rank_universe


def series(vals, start="2026-01-01"):
    import datetime

    d0 = datetime.date.fromisoformat(start)
    return [((d0 + datetime.timedelta(days=i)).isoformat(), v) for i, v in enumerate(vals)]


def test_scored_value_is_outside_its_own_reference_window():
    """The scored day must not appear in the window it is ranked against.

    Proven by construction rather than by inequality: rank the value against the prior window
    computed independently here, and require the two to agree exactly. A value included in its own
    window would score higher, because `percentile_rank` counts ties as beaten.
    """
    window = [0.10 + 0.001 * i for i in range(PCT_WINDOW)]
    scored = 0.15
    got = rank_universe({"A": series(window + [scored])})[0]
    assert got.eligible
    assert got.obs == PCT_WINDOW
    assert got.percentile == percentile_rank(window, scored)
    # And it is strictly below the self-inclusive figure, which is the biased one.
    assert got.percentile < percentile_rank(window + [scored], scored)


def test_a_spike_does_not_move_its_own_window():
    """Changing only the scored day must leave the reference window identical."""
    window = [0.10 + 0.001 * i for i in range(PCT_WINDOW)]
    calm = rank_universe({"A": series(window + [0.10])})[0]
    spike = rank_universe({"A": series(window + [0.99])})[0]
    assert calm.obs == spike.obs == PCT_WINDOW
    assert calm.percentile == percentile_rank(window, 0.10)
    assert spike.percentile == percentile_rank(window, 0.99) == 100.0


def test_as_of_truncates_the_future():
    """Scoring as of a past date must not see observations after it."""
    vals = [0.10] * PCT_WINDOW + [0.20, 0.99]
    s = series(vals)
    full = rank_universe({"A": s})[0]
    earlier = rank_universe({"A": s}, as_of=s[-2][0])[0]
    assert full.day == s[-1][0]
    assert earlier.day == s[-2][0]
    assert earlier.iv == 0.20


def test_short_history_is_ineligible_not_guessed():
    ranked = rank_universe({"A": series([0.2] * (PCT_MIN_OBS - 1))})
    assert ranked[0].eligible is False
    assert ranked[0].percentile is None
    assert "insufficient" in ranked[0].reason


def test_ineligible_names_sort_after_eligible_ones():
    ranked = rank_universe(
        {"short": series([0.2] * 10), "long": series([0.2] * PCT_WINDOW + [0.5])}
    )
    assert [r.symbol for r in ranked] == ["long", "short"]


def test_percentile_rank_is_inclusive_of_ties():
    assert percentile_rank([1, 2, 3, 4], 4) == 100.0
    assert percentile_rank([1, 2, 3, 4], 0) == 0.0
    assert percentile_rank([1, 2, 3, 4], 2) == 50.0
