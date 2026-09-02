"""The registered fill probe's decision table.

The table lives in `docs/pending/condor-fill-realism.md` and was committed before the run. These
tests exist so the code cannot quietly disagree with it -- a probe that classifies its own outcome
differently from its registration is worse than no probe, because the number still gets used.
"""

import datetime as dt

from scripts.fill_probe import (
    CONDORS,
    CONDORS_WALKED,
    PAIRED_VERTICALS,
    STOP,
    read_verdict,
    verdict_for,
)
from src.models import CondorFill

BASE = dict(
    ok=True,
    underlying="SPY",
    expiry=dt.date(2026, 9, 2),
    contracts=1,
    limit_price=-1.20,
    credit_at_mid=1.20,
    submitted_at="2026-08-31T13:45:00Z",
)


def rec(**kw):
    return CondorFill(**{**BASE, **kw})


def test_a_fill_at_mid_is_condors():
    v, _ = verdict_for(rec(filled=True, status="filled", fill=-1.20))
    assert v == CONDORS


def test_a_fill_just_inside_the_floor_is_condors():
    """mid - 0.05 exactly. The registration says ">= mid - 0.05", so the boundary passes."""
    v, _ = verdict_for(rec(filled=True, status="filled", fill=-1.15))
    assert v == CONDORS


def test_a_fill_below_the_floor_is_walked_not_condors():
    v, _ = verdict_for(rec(filled=True, status="filled", fill=-1.10))
    assert v == CONDORS_WALKED


def test_price_improvement_is_still_condors():
    """Collecting more than mid is better than the floor, not outside it."""
    v, _ = verdict_for(rec(filled=True, status="filled", fill=-1.35))
    assert v == CONDORS


def test_no_fill_falls_back_to_paired_verticals():
    v, why = verdict_for(rec(filled=False, status="canceled"))
    assert v == PAIRED_VERTICALS
    assert "2-leg" in why or "did not fill" in why


def test_a_rejection_is_a_stop():
    """A rejection at 09:45 is a platform problem, not a pricing one. Do not size into it."""
    v, _ = verdict_for(rec(filled=False, status="rejected"))
    assert v == STOP


def test_an_unreached_broker_is_a_stop():
    """Absence of a result is never a pass."""
    assert verdict_for(None)[0] == STOP
    assert verdict_for(rec(ok=False, error="boom"))[0] == STOP


def test_every_verdict_carries_a_reason_and_a_consequence():
    from scripts.fill_probe import CONSEQUENCE

    for r in (
        rec(filled=True, status="filled", fill=-1.20),
        rec(filled=True, status="filled", fill=-1.10),
        rec(filled=False, status="canceled"),
        rec(filled=False, status="rejected"),
    ):
        v, why = verdict_for(r)
        assert why.strip(), v
        assert CONSEQUENCE[v].strip()


def test_a_missing_verdict_file_reads_as_none_not_as_permission():
    assert read_verdict(dt.date(1999, 1, 1)) is None


# ---- the gate


def test_the_gate_refuses_when_no_probe_has_run(tmp_path, monkeypatch):
    """Absence is never permission. A probe that crashed looks exactly like one that never ran."""
    import scripts.fill_probe as fp

    monkeypatch.setattr(fp, "PROBE_DIR", str(tmp_path))
    ok, why = fp.gate(dt.date(2026, 8, 31))
    assert not ok
    assert "has not run" in why


def _write(tmp_path, monkeypatch, verdict):
    import json

    import scripts.fill_probe as fp

    monkeypatch.setattr(fp, "PROBE_DIR", str(tmp_path))
    (tmp_path / "2026-08-31-verdict.json").write_text(
        json.dumps({"verdict": verdict, "why": "because", "consequence": "c"})
    )
    return fp


def test_the_gate_opens_on_condors(tmp_path, monkeypatch):
    fp = _write(tmp_path, monkeypatch, CONDORS)
    assert fp.gate(dt.date(2026, 8, 31))[0]


def test_the_gate_opens_on_a_walked_fill(tmp_path, monkeypatch):
    """Walked is viable, just not at mid. The registration keeps 4-leg in that case."""
    fp = _write(tmp_path, monkeypatch, CONDORS_WALKED)
    assert fp.gate(dt.date(2026, 8, 31))[0]


def test_the_gate_refuses_a_stop(tmp_path, monkeypatch):
    fp = _write(tmp_path, monkeypatch, STOP)
    ok, why = fp.gate(dt.date(2026, 8, 31))
    assert not ok and "STOP" in why


def test_the_gate_refuses_paired_verticals_because_it_is_not_built(tmp_path, monkeypatch):
    """Placing condors here would contradict the registration while claiming to follow it."""
    fp = _write(tmp_path, monkeypatch, PAIRED_VERTICALS)
    ok, why = fp.gate(dt.date(2026, 8, 31))
    assert not ok and "not implemented" in why


def test_a_corrupt_verdict_file_refuses(tmp_path, monkeypatch):
    import scripts.fill_probe as fp

    monkeypatch.setattr(fp, "PROBE_DIR", str(tmp_path))
    (tmp_path / "2026-08-31-verdict.json").write_text("{ not json")
    assert not fp.gate(dt.date(2026, 8, 31))[0]


def test_the_verdict_payload_only_reads_fields_that_exist():
    """The probe filled and then crashed writing its own result.

    `CondorFill` has `vs_mid` but no `vs_touch`, and the attribute error fired *after* the order
    was live -- so the measurement existed at the broker and nowhere else. Every key written must
    be reachable on the model.
    """
    import scripts.fill_probe as fp

    r = rec(filled=True, status="filled", fill=-1.12, credit_at_mid=1.12, limit_price=-1.12)
    payload_fields = (
        "status",
        "filled",
        "fill",
        "vs_mid",
        "credit_at_mid",
        "limit_price",
        "order_id",
        "legs",
    )
    for f in payload_fields:
        getattr(r, f)
    assert fp.verdict_for(r)[0] == fp.CONDORS


# ---- the verdict is a property of the venue, not of one session


def test_the_gate_accepts_a_recent_earlier_verdict(tmp_path, monkeypatch):
    """The probe answers a question about the simulator, not about today.

    Keying the gate to the session date meant Tuesday demanded its own probe and refused with
    "the 09:45 probe has not run" while Monday's CONDORS verdict sat on disk. That is a false
    refusal: the measured fact -- four legs clear at a single mid limit here -- did not expire
    overnight, and re-probing daily would place an extra unwanted contract every session.
    """
    import json

    import scripts.fill_probe as fp

    monkeypatch.setattr(fp, "PROBE_DIR", str(tmp_path))
    (tmp_path / "2026-08-31-verdict.json").write_text(
        json.dumps({"verdict": CONDORS, "why": "filled at mid", "consequence": "c"})
    )
    ok, why = fp.gate(dt.date(2026, 9, 1))
    assert ok, why
    assert "2026-08-31" in why, "the gate must say which probe it is relying on"


def test_a_stale_verdict_is_refused(tmp_path, monkeypatch):
    """Recent means recent. A verdict from a different market week says nothing about today."""
    import json

    import scripts.fill_probe as fp

    monkeypatch.setattr(fp, "PROBE_DIR", str(tmp_path))
    (tmp_path / "2026-08-03-verdict.json").write_text(
        json.dumps({"verdict": CONDORS, "why": "ancient", "consequence": "c"})
    )
    ok, why = fp.gate(dt.date(2026, 9, 1))
    assert not ok
    assert "stale" in why.lower() or "days" in why.lower()


def test_the_newest_verdict_wins(tmp_path, monkeypatch):
    """A later STOP must not be overridden by an earlier CONDORS still sitting on disk."""
    import json

    import scripts.fill_probe as fp

    monkeypatch.setattr(fp, "PROBE_DIR", str(tmp_path))
    (tmp_path / "2026-08-31-verdict.json").write_text(json.dumps({"verdict": CONDORS, "why": "a"}))
    (tmp_path / "2026-09-01-verdict.json").write_text(json.dumps({"verdict": STOP, "why": "b"}))
    assert not fp.gate(dt.date(2026, 9, 1))[0]
