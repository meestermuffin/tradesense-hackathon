"""The operational scripts, which the rest of the suite never touched.

Every test here exists because of a specific failure on 2026-08-27/28: the pydantic port left
`.get()` calls on model objects in `capture_nbbo.py`, and the scheduled capture died on import-time
-- silently, at 15:50, for two sessions. One of them was a judged session, and NBBO cannot be
backfilled. `src/` was well covered; the scripts that actually run were not covered at all.
"""

import importlib
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"

# The four the scheduler runs. If one of these cannot import, a session is lost.
SCHEDULED = ["capture_nbbo", "run_cycle", "snapshot_equity", "heartbeat"]


@pytest.fixture(autouse=True)
def _path():
    for p in (str(ROOT), str(SCRIPTS)):
        if p not in sys.path:
            sys.path.insert(0, p)


@pytest.mark.parametrize("name", SCHEDULED)
def test_scheduled_script_imports(name):
    """A scheduled job that cannot import fails at 15:50 with nobody watching."""
    importlib.import_module(name)


@pytest.mark.parametrize("name", [p.stem for p in sorted(SCRIPTS.glob("*.py"))])
def test_every_script_compiles(name):
    """Catches syntax errors before launchd does."""
    r = subprocess.run(
        [sys.executable, "-m", "py_compile", str(SCRIPTS / f"{name}.py")],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr


def test_quote_exposes_the_fields_capture_writes():
    """capture_nbbo writes bid_size/ask_size/timestamp straight onto its rows.

    It used to reach for them with q.get("bs"), which returns None on a dict and raises on a model.
    Renaming any of these should break a test rather than a Friday capture.
    """
    from src.models import Quote

    q = Quote.model_validate({"bp": 1.0, "ap": 1.1, "bs": 3, "as": 5, "t": "2026-08-28T19:50:00Z"})
    assert (q.bid, q.ask, q.bid_size, q.ask_size) == (1.0, 1.1, 3, 5)
    assert q.timestamp == "2026-08-28T19:50:00Z"


def test_models_raise_on_dict_access_rather_than_returning_none():
    """The property that turns this bug class loud instead of silent.

    A dict answers .get() with None and lets the run continue on a value that was never served.
    A model raises. That is the whole reason for the boundary.
    """
    from src.models import Account, Quote

    for m in (Quote(bp=1.0, ap=1.1), Account(account_number="PA1", equity=1.0)):
        with pytest.raises(AttributeError):
            m.get("anything")
        with pytest.raises(TypeError):
            m["anything"]


def test_no_scheduled_script_calls_get_on_a_model():
    """Static guard over the exact pattern that broke the capture.

    Crude on purpose: it greps for `.get("` on the short single-letter names these scripts bind
    quotes and accounts to. It cannot catch every case, and the import tests above are the real
    net -- but this one names the mistake so the next person sees it.
    """
    import re

    bad = re.compile(r"\b(q|a|ac|acct|clock|pos|p)\.get\(")
    hits = []
    for name in SCHEDULED:
        for i, line in enumerate((SCRIPTS / f"{name}.py").read_text().splitlines(), 1):
            if bad.search(line) and "os.environ" not in line:
                hits.append(f"{name}.py:{i}: {line.strip()}")
    assert not hits, "dict-style .get() on what is probably a model:\n" + "\n".join(hits)
