"""The model layer, and the asymmetry that makes it safe.

The model can **refuse** a tranche and it can **tighten** the short delta inside the registered
18–22 band. That is the whole of its authority. It cannot express a price — the field is absent
from `CondorRequest` — and it cannot change the ladder, the sizing or the expiries. An approval is
not sufficient either: the eleven guardrails still run afterwards and still refuse.

So a bad model response costs a trade and cannot cause one. Every failure path below therefore
resolves to a refusal: unparseable output, a timeout, a non-zero exit, an empty reason. **Absence is
never assent.**
"""

import json

import pytest
from pydantic import ValidationError

from src.agent.model import BAND, ModelDecision, extract_json, review


def envelope(result: str, is_error: bool = False) -> str:
    return json.dumps({"is_error": is_error, "result": result, "total_cost_usd": 0.1})


# ---- extracting a decision from the CLI envelope


def test_it_reads_a_clean_json_result():
    got = extract_json(envelope('{"decision":"approve","short_delta":0.20,"reason":"calm"}'))
    assert got["decision"] == "approve"


def test_it_finds_json_wrapped_in_prose():
    """Models add preamble. The envelope is ours; the content inside is not."""
    got = extract_json(envelope('Sure!\n```json\n{"decision":"refuse","reason":"vol spike"}\n```'))
    assert got["decision"] == "refuse"


def test_unparseable_output_yields_nothing_rather_than_a_guess():
    assert extract_json(envelope("I cannot help with that.")) is None
    assert extract_json("not even json") is None


def test_an_errored_envelope_yields_nothing():
    assert extract_json(envelope('{"decision":"approve","reason":"x"}', is_error=True)) is None


# ---- the decision schema


def test_a_decision_needs_a_reason():
    """An unexplained refusal is not usable trace, and an unexplained approval is worse."""
    with pytest.raises(ValidationError):
        ModelDecision(decision="approve", reason="")


def test_only_two_decisions_exist():
    with pytest.raises(ValidationError):
        ModelDecision(decision="maybe", reason="hedging")


# ---- review(): every failure path refuses


def test_a_valid_approval_passes_through():
    d = review(
        {},
        ask=lambda _p, **k: envelope(
            '{"decision":"approve","short_delta":0.19,"reason":"quiet tape"}'
        ),
    )
    assert d.decision == "approve"
    assert d.short_delta == 0.19


def test_a_refusal_carries_its_reason():
    d = review(
        {},
        ask=lambda _p, **k: envelope(
            '{"decision":"refuse","reason":"ADP prints into this expiry"}'
        ),
    )
    assert d.decision == "refuse"
    assert "ADP" in d.reason


def test_unparseable_output_becomes_a_refusal():
    d = review({}, ask=lambda _p, **k: envelope("no idea"))
    assert d.decision == "refuse"
    assert "parse" in d.reason.lower()


def test_a_timeout_becomes_a_refusal():
    def boom(_p, **k):
        raise TimeoutError("took too long")

    d = review({}, ask=boom)
    assert d.decision == "refuse"


def test_a_crash_becomes_a_refusal_not_an_exception():
    def boom(_p, **k):
        raise RuntimeError("cli exploded")

    d = review({}, ask=boom)
    assert d.decision == "refuse"
    assert "cli exploded" in d.reason or "refus" in d.reason.lower()


def test_an_empty_response_becomes_a_refusal():
    assert review({}, ask=lambda _p, **k: "").decision == "refuse"


# ---- the model may narrow, never widen


def test_a_tighter_delta_is_honoured():
    d = review(
        {},
        ask=lambda _p, **k: envelope(
            '{"decision":"approve","short_delta":0.18,"reason":"closer to the floor"}'
        ),
    )
    assert d.short_delta == 0.18
    assert d.clamped is False


def test_a_delta_above_the_band_is_clamped_and_recorded():
    """Widening is the one thing it must not be able to do."""
    d = review(
        {},
        ask=lambda _p, **k: envelope(
            '{"decision":"approve","short_delta":0.40,"reason":"feeling lucky"}'
        ),
    )
    assert d.short_delta == BAND[1]
    assert d.clamped is True
    assert "clamp" in d.reason.lower()


def test_a_delta_below_the_band_is_clamped_too():
    d = review(
        {},
        ask=lambda _p, **k: envelope(
            '{"decision":"approve","short_delta":0.02,"reason":"very safe"}'
        ),
    )
    assert d.short_delta == BAND[0]
    assert d.clamped is True


def test_a_missing_delta_is_allowed_and_means_use_the_default():
    d = review({}, ask=lambda _p, **k: envelope('{"decision":"approve","reason":"fine"}'))
    assert d.decision == "approve"
    assert d.short_delta is None


def test_the_band_matches_the_registered_guardrail():
    """Guardrail #3 enforces 18-22 delta. The model must not be able to leave it."""
    assert BAND == (0.18, 0.22)


# ---- the prompt


def test_the_prompt_never_offers_the_model_a_price():
    from src.agent.model import build_prompt

    p = build_prompt({"underlying": "SPY", "credit": 1.24, "contracts": 13})
    assert "limit_price" not in p
    assert "approve" in p and "refuse" in p


def test_the_prompt_states_that_approval_is_not_sufficient():
    from src.agent.model import build_prompt

    p = build_prompt({}).lower()
    assert "guardrail" in p or "still" in p


# ---- finding the CLI under a scheduled job's environment


def test_the_binary_is_found_on_a_normal_path(monkeypatch):
    import src.agent.model as m

    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    monkeypatch.setattr(m.shutil, "which", lambda n, path=None: "/somewhere/claude")
    assert m.claude_bin() == "/somewhere/claude"


def test_it_falls_back_to_known_install_locations(monkeypatch, tmp_path):
    """launchd gives a job almost no PATH, so `claude` is not on it.

    Found by running the installed plist under `env -i PATH=/usr/bin:/bin`: the CLI was not found,
    ask() raised, review() failed closed, and every tranche was refused. The schedule would have
    placed nothing at 10:00 and said only that the model declined.
    """
    import src.agent.model as m

    fake = tmp_path / "claude"
    fake.write_text("#!/bin/sh\n")
    fake.chmod(0o755)
    monkeypatch.setattr(m.shutil, "which", lambda n, path=None: None)
    monkeypatch.setattr(m, "FALLBACK_BINS", (str(fake),))
    assert m.claude_bin() == str(fake)


def test_an_explicit_override_wins(monkeypatch, tmp_path):
    import src.agent.model as m

    fake = tmp_path / "mine"
    fake.write_text("#!/bin/sh\n")
    fake.chmod(0o755)
    monkeypatch.setenv("CLAUDE_BIN", str(fake))
    assert m.claude_bin() == str(fake)


def test_a_missing_binary_raises_with_the_fix_in_the_message(monkeypatch):
    """The refusal has to say what to do, or it reads as the model declining on the merits."""
    import src.agent.model as m

    monkeypatch.delenv("CLAUDE_BIN", raising=False)
    monkeypatch.setattr(m.shutil, "which", lambda n, path=None: None)
    monkeypatch.setattr(m, "FALLBACK_BINS", ())
    with pytest.raises(RuntimeError, match="CLAUDE_BIN"):
        m.claude_bin()


def test_a_missing_binary_still_refuses_rather_than_approving(monkeypatch):
    import src.agent.model as m

    monkeypatch.delenv("CLAUDE_BIN", raising=False)
    monkeypatch.setattr(m.shutil, "which", lambda n, path=None: None)
    monkeypatch.setattr(m, "FALLBACK_BINS", ())
    d = m.review({"underlying": "SPY", "expiry": "2026-09-02", "short_delta": 0.20})
    assert d.decision == "refuse"
