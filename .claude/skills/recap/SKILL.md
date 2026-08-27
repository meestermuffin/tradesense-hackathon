---
name: recap
description: "Write a durable, human-readable recap of the current session to .claude/private/recaps/<date>-<topic>.md — what changed, what was verified, what's still open. Use at the END of any prolonged or multi-part session (several files/services touched, debugging + fixes, data migrations), when the user says 'recap', 'summarize what we did', 'wrap up', 'write this up', or before a session is about to be compacted/closed. To READ past recaps back ('what did we do last time', 'what's still open'), use the `recap-me` skill instead — this one writes."
---

# /recap

Close out a working session by writing a recap file that a human — or a future session with no
memory of this one — can pick up cold.

**The test:** someone reads only this file in three weeks and knows what changed, what's trustworthy,
and what to do next. Optimise for that, not for completeness.

## Modes

| Invocation | Mode |
|---|---|
| `/recap`, "recap this", "wrap up", end of a long session | **Write** — produce a new recap file (this skill, below) |
| `/recap-me`, `/recap read`, "what did we do last time", "what's still open" | **Read** — summarise existing recaps back to the user |

For **read** mode use the `recap-me` skill, which covers reading, filtering and reporting on the
recaps directory. Everything below is write mode.

## Where it goes

```
<project-root>/.claude/private/recaps/
  INDEX.md                      # one line per recap, newest first
  2026-08-19-trader-metrics.md
```

- Project root = the primary working directory (the repo root if in one).
- Slug = 2–4 words describing the session's theme, kebab-case.
- If a file for today's date+slug already exists, **append a new `## Session N` block** rather than
  overwriting — a day can hold several sessions.
- Create `.claude/private/recaps/` and `INDEX.md` if absent. **Under `private/` deliberately:**
the public repo would otherwise publish session records by accident, and `.claude/private/`
is its own git repo, so recaps get version history instead of none.

## How to write it

Write from the transcript, not from memory of intent. Before writing, scan back through the session
for: files edited, commands that mutated state, things that failed and why, and anything the user
asked that you deferred or never answered.

Rules that keep a recap worth reading:

- **Separate verified from assumed.** If you ran a command and saw the result, say so and quote the
  number. If you inferred it or it only compiled, mark it. Never promote "it builds" to "it works".
- **Record state mutations, not just code.** DB updates, backfills, container rebuilds, config edits,
  deleted/rebuilt tables. These are invisible in a diff and are the easiest thing to lose. Include
  where any backup went.
- **Corrections are the most valuable section.** If you diagnosed something wrong and later fixed the
  diagnosis, write down both — that's what stops the next session repeating it. Do not quietly drop
  a wrong earlier claim.
- **Follow-ups are checkboxes** so they can be ticked off later. Each one names the next action, not
  a vague area.
- **Check for work that has quietly come due**, not just work this session touched. In this project
  that means the perishable and the clock-bound:
  ```bash
  make heartbeat                    # did yesterday produce a capture, a cycle and an equity row?
  ls data/nbbo/ | tail -3           # NBBO captures cannot be backfilled — a gap is permanent
  python3 -c "import datetime as d;print('days to submission:',(d.date(2026,9,4)-d.date.today()).days)"
  git log --oneline @{u}..HEAD | wc -l   # unpushed commits
  ```
  A missing NBBO capture is the one that matters most: there is no historical options quote endpoint,
  so a session not captured is gone from the spread model forever. Note it as a permanent loss, not
  a to-do.

  Also check whether the IV series still reaches yesterday. `run_cycle` refuses when it does not, but
  a recap written while it is stale should say so — a percentile computed against a stale window
  looks confident and means nothing.

- **Open questions** are decisions only the human can make. If you asked something and never got an
  answer, it belongs here — don't let it evaporate.
- Keep it scannable: short bullets, real paths (`service/file.go:120`), real numbers. No filler,
  no restating the obvious, no praise.
- Don't include secrets (keys, tokens) — reference the config file instead.

## Template

```markdown
# <Topic> — <YYYY-MM-DD>

**Focus:** <one sentence on what this session was about>
**Outcome:** <one sentence: what is now true that wasn't before>

## TL;DR
- <2–5 bullets a human can read in 15 seconds>

## Changes
### <service / area>
- `path/to/file.ext` — what changed and why (one line each)

## State changes (not in code)
- <DB writes, backfills, rebuilds, config edits — with row counts / dates / backup paths>

## Verified
- <claim> — how it was checked, with the actual output/number
## Not verified
- <anything that compiles/deploys but was never exercised end to end>

## Corrections
- **Thought:** <initial wrong diagnosis> → **Actually:** <what was true> → <what fixed it>

## Follow-ups
- [ ] <next concrete action>
- [ ] <next concrete action>

## Open questions
- <decision the human still needs to make, with the options and your recommendation>
```

Sections that would be empty are omitted — an empty "Corrections" heading is noise.

## Index entry

Prepend one line to `.claude/private/recaps/INDEX.md` (newest first), and add the header if creating it:

```markdown
# Recaps
- [2026-08-19 — Trader metrics](2026-08-19-trader-metrics.md) — fixed trades/win-rate/Sharpe; SPY benchmark added · 3 follow-ups
```

Include the open follow-up count so the index shows where work is outstanding.

## After writing

Tell the user the path, then surface **only** the follow-ups and open questions inline — they've
just lived through the rest. If earlier recaps have unticked follow-ups that this session resolved,
tick them and say which.
