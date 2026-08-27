---
name: quant-review
description: "Dispatch the quant-reviewer agent to adversarially attack a document's quantitative claims by recomputation, then relay its claims table and falsification coverage. Use before a number enters the plan or a shared document, before anything is shown to judges or teammates, after any backtest, IV-series or fill-distribution run, or on 'review this / check my work / did I overclaim / is this safe to publish'. Triggers: quant-review, review this record, check my work, did I overclaim, attack this claim, before we send."
---

# /quant-review

`/quant-review <file>` — dispatch `quant-reviewer` on a document and relay what it finds.

**This skill does one thing: dispatch and relay.** All the judgement lives in
[`.claude/agents/quant-reviewer.md`](../../agents/quant-reviewer.md). Do not restate its playbook
here — a second copy is the document-drift failure this project fights, and the agent file is the
single home.

## Why an agent and not a skill

**A skill cannot catch a mistake its own instructions caused.** If the reviewing instructions run in
the same context that produced the claim, they inherit its anchoring. The agent starts cold, with
tools, and recomputes. Independent recomputation is the only mechanism that has ever caught a
*novel* defect here — defect #7 is "the only one found while checking someone else's work."

Cost of the cold start: the agent must re-derive context, and it will sometimes miss things a
same-context reader would know. That is the price of independence — do not "help" it by pre-digesting
the answer in the dispatch prompt.

## Procedure

1. **Resolve the target.** With no argument, ask which document. Confirm the file exists before
   dispatching — a reviewer sent at a missing path burns a whole agent run.
2. **Dispatch** `quant-reviewer` via the Agent tool. The prompt should carry:
   - the absolute path to the target, and the instruction to orient before reviewing;
   - **the strongest counter-evidence against the document's own conclusions, named explicitly.**
     A reviewer optimises for the questions asked — the v7 review missed the levered-SPY comparison
     because nothing pointed at it. Name what you most fear is wrong;
   - anything already independently verified, so the run is not spent re-checking settled facts;
   - the constraint that it must not **author** strategy content (variants, features, signal
     families) — measurement next steps, probes and remediations are expected output, not a
     violation.
3. **Do not pre-judge.** Never tell it your expected verdict.
4. **Relay** the claims table **verbatim** (never paraphrased), the falsification-coverage section,
   the proposed next steps, the `VERDICTS:` tally line, and the path of the on-disk report the agent
   wrote to `.claude/private/`. The agent's report is not shown to the user — if you
   do not relay it, it does not exist. A relay without the file path is incomplete.
5. **Act on REFUTED and UNTESTED before publishing.** UNTESTED is not a pass; it means nobody looked.

## The producer is the relay — the file wins

The session dispatching this skill usually produced the document under review, and it is the only
channel through which the user sees the verdict. That is a conflict of interest: summaries of
adverse reviews soften ("REFUTED" → "methodological disagreement", dropped coverage sections). The
defence is structural: the agent persists its full report to disk before replying, and **when the
relay and the file disagree, the file is the record.** For any decision that hangs on a review —
re-enabling entries, publishing a number, spending a fork — the user reads the file (or hands it to
a separate adjudicating session), not the relay.

## Reading the verdicts

VERIFIED (recomputed, matches) · DERIVED (follows from VERIFIED by stated arithmetic) · PLAUSIBLE
(consistent, not recomputed) · **UNTESTED (no evidence — the default when evidence is missing)** ·
REFUTED (outside tolerance or self-contradictory) · UNRESOLVABLE (cannot be settled with what
exists).

**A verdict is only worth the recomputation behind it.** If the evidence column does not name a
command and its output, treat the row as PLAUSIBLE regardless of what it claims.

## When not to use this

- **Generating a strategy** — out of scope; the agent will decline. Signals, features and variants
  are the user's call, made on the agent's verdicts.
- **Running the measurement itself** — dispatch the agent to *check* a number, not to produce one.
- **Freshness questions** — whether the pipeline is current is never evidence that anything works.

## What to point it at here

`PLAN.md` is the usual target. Two prior reviews sit in `.claude/private/`; name them in the dispatch
so the run is spent on what changed rather than re-deriving settled ground, and so the agent can
check whether earlier defects were **remediated or merely acknowledged**.

The counter-evidence worth naming explicitly, since a reviewer optimises for the questions asked:
every figure the plan states as measured, anything asserted from Alpaca's docs rather than a probe,
and any feature or cost model planned on top of an implied-volatility series nobody has confirmed is
computable.

