"""The scheduled-wake guard.

launchd runs a missed job on wake rather than skipping it, so a 10:00 entry can arrive at 14:00
against a book that has moved all day. These tests pin the refusal.
"""

import datetime as dt

import pytest

from src.agent.window import DEFAULT_GRACE_MINUTES, parse, within

TARGET = dt.time(10, 0)


def at(h, m, s=0):
    return dt.datetime(2026, 8, 31, h, m, s)


def test_on_time_is_inside_the_window():
    ok, _ = within(TARGET, at(10, 0))
    assert ok


def test_a_short_delay_is_still_inside():
    ok, _ = within(TARGET, at(10, 9))
    assert ok


def test_the_grace_boundary_is_inclusive():
    assert within(TARGET, at(10, DEFAULT_GRACE_MINUTES))[0]


def test_a_late_wake_is_refused():
    """The failure this exists for: laptop asleep at 10:00, awake at 14:00."""
    ok, why = within(TARGET, at(14, 0))
    assert not ok
    assert "240 min past" in why


def test_early_is_refused_too():
    """A job firing early is a misconfigured plist, not an opportunity."""
    ok, why = within(TARGET, at(9, 30))
    assert not ok
    assert "BEFORE" in why


def test_the_reason_is_never_empty():
    for when in (at(10, 0), at(9, 0), at(23, 59)):
        assert within(TARGET, when)[1].strip()


@pytest.mark.parametrize("s,expect", [("09:35", dt.time(9, 35)), ("10:00", dt.time(10, 0))])
def test_parse_reads_wall_clock(s, expect):
    assert parse(s) == expect
