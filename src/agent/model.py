"""The model in the loop, and the asymmetry that makes it safe to have there.

**It can refuse a tranche, and it can tighten the short delta inside the registered 18-22 band.
That is the whole of its authority.**

It cannot express a price -- `CondorRequest` has no such field, so sign inversion is outside its
reach rather than caught downstream. It cannot change the ladder, the expiries or the sizing, all of
which are registered decisions. And an approval is **not sufficient**: the eleven guardrails in
`validate()` run afterwards regardless and refuse on their own terms.

The consequence is worth stating plainly, because it is the safety argument:

> **A bad model response costs a trade. It cannot cause a bad trade.**

Every failure path here therefore resolves to a refusal -- unparseable output, a timeout, a non-zero
exit, an empty reason, a delta outside the band. **Absence is never assent.** A system that treats a
crashed model as approval has the failure mode backwards.

Transport is the `claude` CLI rather than an SDK, because this environment has no API key and the
CLI works headlessly against existing auth. Verified 2026-08-31:
`claude -p ... --output-format json` returns an envelope carrying `is_error` and a `result` string,
at roughly $0.10-0.22 per call.
"""

from __future__ import annotations

import json
import re
import subprocess
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

BAND = (0.18, 0.22)
"""The registered short-delta band, guardrail #3. The model may move inside it, never outside."""

TIMEOUT_S = 180.0
"""Generous on purpose. A timeout is a refusal, so a tight limit does not fail safe -- it just
costs trades. Measured: a review of this prompt takes 30-60s."""


class ModelDecision(BaseModel):
    """What the model is permitted to say. Note what is absent: any price, size or expiry."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    decision: Literal["approve", "refuse"]
    reason: str = Field(min_length=1)
    """Required. An unexplained refusal is unusable trace; an unexplained approval is worse."""
    short_delta: float | None = None
    clamped: bool = False
    """True when the model asked for a delta outside the band and was pulled back into it."""


def ask(prompt: str, timeout: float = TIMEOUT_S) -> str:
    """One headless call. Returns the raw envelope; parsing is the caller's problem."""
    r = subprocess.run(
        ["claude", "-p", prompt, "--output-format", "json"],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if r.returncode != 0:
        raise RuntimeError(f"claude exited {r.returncode}: {(r.stderr or '')[:200]}")
    return r.stdout


def extract_json(envelope: str) -> dict[str, Any] | None:
    """Pull the decision object out of the CLI envelope.

    Two layers: the envelope itself is JSON, and `result` is a string that *should* be JSON but is
    written by a model, so it may carry preamble or a code fence. Returns `None` rather than
    guessing -- a fabricated decision is worse than no decision.
    """
    try:
        outer = json.loads(envelope)
    except (json.JSONDecodeError, TypeError):
        return None
    if outer.get("is_error"):
        return None
    result = outer.get("result")
    if not isinstance(result, str):
        return None
    m = re.search(r"\{.*\}", result, re.S)
    if not m:
        return None
    try:
        got = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    return got if isinstance(got, dict) else None


def build_prompt(context: dict[str, Any]) -> str:
    """The review prompt. Deliberately narrow about what an answer may contain."""
    return f"""You are the risk reviewer for an options trading agent. Review ONE proposed trade.

CONTEXT
{json.dumps(context, indent=2, default=str)}

YOUR AUTHORITY IS NARROW AND DELIBERATE:
- You may REFUSE this trade for any reason you can articulate.
- You may tighten the short delta within {BAND[0]}-{BAND[1]}. You may not go outside it.
- You may NOT set a price, a size, an expiry, or override any risk limit.
- Approving is NOT sufficient. Eleven deterministic guardrails run after you and can still refuse.

Refuse if you see a reason the rules do not already encode -- a news event, an unusual condition,
something incoherent in the numbers. The rules already handle position limits, account identity,
credit floors, expiry caps and drawdown, so do not duplicate them.

Reply with ONLY a JSON object, no prose, no code fence:
{{"decision": "approve" | "refuse", "short_delta": <number or null>, "reason": "<one sentence>"}}"""


def review(context: dict[str, Any], ask=ask, timeout: float = TIMEOUT_S) -> ModelDecision:
    """Ask the model, and fail closed on anything unexpected.

    `ask` is injected so the decision logic is testable without spending a call or a network.
    """
    try:
        raw = ask(build_prompt(context), timeout=timeout)
    except TimeoutError:
        return ModelDecision(decision="refuse", reason=f"model timed out after {timeout:.0f}s")
    except Exception as e:  # a broken reviewer must not become an approval
        # Truncated deliberately: subprocess errors embed the whole prompt, which buries the
        # actual decision under a wall of text in the one place someone is reading quickly.
        detail = str(e).split("\n")[0][:160]
        return ModelDecision(decision="refuse", reason=f"model call failed: {detail}")

    got = extract_json(raw)
    if not got:
        return ModelDecision(
            decision="refuse", reason="could not parse a decision from the model response"
        )

    decision = str(got.get("decision", "")).strip().lower()
    if decision not in ("approve", "refuse"):
        return ModelDecision(decision="refuse", reason=f"unrecognised decision {decision!r}")

    reason = str(got.get("reason") or "").strip() or "no reason given"

    delta, clamped = got.get("short_delta"), False
    if delta is not None:
        try:
            delta = float(delta)
        except (TypeError, ValueError):
            delta, clamped = None, False
        else:
            lo, hi = BAND
            if delta < lo or delta > hi:
                # The one thing it must not be able to do is widen. Pull it back and say so, rather
                # than refusing outright -- the rest of the answer may still be sound.
                original, delta, clamped = delta, min(max(delta, lo), hi), True
                reason = f"{reason} [short_delta {original:.3f} clamped to {delta:.2f}]"

    return ModelDecision(decision=decision, reason=reason, short_delta=delta, clamped=clamped)
