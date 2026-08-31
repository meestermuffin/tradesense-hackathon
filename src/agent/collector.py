"""Supervises Solo's markwatch collector as its own process.

**It must be capturing before the first order exists.** There is no historical options quote
endpoint on this account, so a fill placed before the collector starts can never be reconciled
against the NBBO it crossed. The loss is permanent and it is silent — nothing in the guardrails can
see it afterwards, because the evidence simply does not exist. `AgentLoop` therefore refuses to
trade live unless this is running.

**Why a subprocess and not an import.** The plan called for importing `Collector` and injecting our
own callables. That turned out to be unnecessary: markwatch's own client already sends
`feed=indicative`, reads the credentials it expects, and was verified doing a live pass on
2026-08-31 — `python -m markwatch.run --once` connected and correctly reported "no open legs"
against a flat book. Re-wiring a tested loop to gain nothing would only add integration surface.

Our adapter still earns its place elsewhere: `run_agent.chain_quotes` needs it because our own
client has no `feed` parameter, and `fill_legs` converts an `Order` into the leg dicts
`Submission.filled()` indexes directly.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
MARKWATCH = REPO / "markwatch"


def collector_env(key: str, secret: str, paper: bool = True, base: dict | None = None) -> dict:
    """Environment for the collector process.

    markwatch reads `ALPACA_API_KEY` / `ALPACA_SECRET_KEY` and **never loads a .env**, while this
    repo stores `ALPACA_KEY_ID`. Without the alias it starts and then fails on the first call.
    """
    env = dict(base if base is not None else os.environ)
    env["ALPACA_API_KEY"] = key
    env["ALPACA_SECRET_KEY"] = secret
    env["ALPACA_PAPER_TRADE"] = "True" if paper else "False"
    return env


class CollectorHandle:
    """Start it, check it is alive, stop it. Deliberately thin.

    `is_running` reflects the process, not a flag we set — a supervisor that believes its own
    bookkeeping is exactly how the guard gets satisfied while nothing is capturing.
    """

    def __init__(
        self,
        key: str,
        secret: str,
        db: str = "journal.db",
        interval: float = 60.0,
        until: str | None = None,
        freshness: float = 15.0,
        paper: bool = True,
    ):
        self.key, self.secret = key, secret
        self.db = str((REPO / db).resolve() if not os.path.isabs(db) else pathlib.Path(db))
        self.interval, self.until, self.freshness, self.paper = interval, until, freshness, paper
        self.proc: subprocess.Popen | None = None

    def command(self) -> list[str]:
        cmd = [
            sys.executable,
            "-m",
            "markwatch.run",
            "--db",
            self.db,
            "--interval",
            str(self.interval),
            "--freshness",
            str(self.freshness),
        ]
        if self.until:
            cmd += ["--until", self.until]
        return cmd

    @property
    def is_running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def start(self, log: str | None = None):
        """Spawn it. Returns self so it can be chained into a `with`-style flow."""
        if self.is_running:
            return self
        out = open(log, "a") if log else subprocess.DEVNULL
        self.proc = subprocess.Popen(
            self.command(),
            cwd=str(MARKWATCH),
            env=collector_env(self.key, self.secret, self.paper),
            stdout=out,
            stderr=subprocess.STDOUT,
        )
        return self

    def require_running(self):
        """Raise unless it is genuinely alive. Called before any order goes out."""
        if not self.is_running:
            raise RuntimeError(
                "markwatch collector is not running. Quotes do not exist after the fact on this "
                "account, so any fill placed now is unreconcilable forever. Start it first: "
                "CollectorHandle(...).start()"
            )

    def stop(self, timeout: float = 5.0):
        if self.proc is None:
            return
        self.proc.terminate()
        try:
            self.proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        self.proc = None
