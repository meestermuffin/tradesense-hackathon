"""Supervising Solo's markwatch collector.

It must be capturing **before the first order exists**. There is no historical options quote
endpoint on this account, so a fill placed before it starts can never be reconciled against the
NBBO it crossed — the loss is permanent and silent, which is why `AgentLoop` refuses to trade live
without it.

The collector runs as its own process against `python -m markwatch.run`, rather than importing
`Collector` and injecting our callables. That was the original plan, and it turned out to be
unnecessary: markwatch's own client already sends `feed=indicative`, reads the credentials it
expects, and was verified doing a live pass on 2026-08-31. Wrapping his tested loop in our own
would add integration surface for nothing.
"""

import pathlib

import pytest

from src.agent.collector import CollectorHandle, collector_env


def test_env_maps_our_credential_names():
    """markwatch reads ALPACA_API_KEY and never loads a .env; we store ALPACA_KEY_ID."""
    env = collector_env(key="abc", secret="xyz", base={})
    assert env["ALPACA_API_KEY"] == "abc"
    assert env["ALPACA_SECRET_KEY"] == "xyz"


def test_env_defaults_to_paper():
    assert collector_env(key="k", secret="s", base={})["ALPACA_PAPER_TRADE"] == "True"


def test_live_must_be_explicit():
    env = collector_env(key="k", secret="s", paper=False, base={})
    assert env["ALPACA_PAPER_TRADE"] == "False"


def test_a_handle_is_not_running_before_start():
    h = CollectorHandle(key="k", secret="s", db="x.db")
    assert h.is_running is False


def test_the_command_names_solos_module_not_ours():
    h = CollectorHandle(key="k", secret="s", db="/tmp/j.db", interval=60.0)
    cmd = h.command()
    assert "markwatch.run" in cmd
    assert "--db" in cmd and "/tmp/j.db" in cmd
    assert "--interval" in cmd and "60.0" in cmd


def test_the_interval_reaches_the_command():
    assert "30.0" in CollectorHandle(key="k", secret="s", db="j.db", interval=30.0).command()


def test_an_until_is_passed_through_when_given():
    """The window ends at the Thursday close; the collector should stop with it."""
    h = CollectorHandle(key="k", secret="s", db="j.db", until="2026-09-03T20:05:00Z")
    assert "--until" in h.command() and "2026-09-03T20:05:00Z" in h.command()


def test_no_until_flag_when_not_given():
    assert "--until" not in CollectorHandle(key="k", secret="s", db="j.db").command()


def test_stopping_a_handle_that_never_started_is_harmless():
    CollectorHandle(key="k", secret="s", db="j.db").stop()


def test_the_db_path_is_resolved_absolute():
    """The collector runs with its own cwd; a relative path would write somewhere unexpected."""
    h = CollectorHandle(key="k", secret="s", db="journal.db")
    assert pathlib.Path(h.db).is_absolute()


def test_require_running_raises_with_an_actionable_message():
    """This is the guard that stands between a fill and an unreconcilable one."""
    h = CollectorHandle(key="k", secret="s", db="j.db")
    with pytest.raises(RuntimeError, match="not running"):
        h.require_running()
