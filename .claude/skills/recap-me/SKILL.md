---
name: recap-me
description: "Catch me up: read back existing session recaps from .claude/private/recaps/ and report what happened, what changed, and what's still open. Use when the user asks 'recap me', 'what did we do last time', 'where did we leave off', 'what's still open', 'any follow-ups', 'catch me up', or opens a session wanting context on prior work. Read-only — never writes. To CREATE a recap at the end of a session, use the `recap` skill instead."
---

# /recap-me

Read the recaps and tell the user where things stand. **Read-only — this skill never writes files.**

Recaps live in `<project-root>/.claude/private/recaps/`, with `INDEX.md` listing them newest first. If that
directory doesn't exist, say so plainly and offer the `recap` skill to start one — don't invent
history.

## Arguments

| Invocation | Behaviour |
|---|---|
| `/recap-me` | The **most recent** recap |
| `/recap-me open` | **Only unticked follow-ups + open questions**, across all recaps |
| `/recap-me all` / `list` | One line per recap (date, topic, open count) |
| `/recap-me <date>` | The recap(s) for that date, e.g. `2026-08-19` |
| `/recap-me <topic>` | Recaps whose filename or title matches, e.g. `metrics` |
| `/recap-me last N` | The last N recaps, condensed |

## How to read

1. `ls .claude/private/recaps/` and read `INDEX.md` first — it's the map.
2. Read the file(s) the request selects. For `open`, grep every recap for unticked boxes
   (`- [ ]`) and read the surrounding sections for context.
3. Don't read every recap when one will do; don't answer from the index alone when the user
   asked what happened — the index has titles, the files have substance.

## How to report

Synthesise — **do not dump the file**. The user wants to be caught up, not handed a document
they could have opened.

- Lead with the one-line outcome, then what changed, grouped by area, at the altitude of "what
  this means" rather than a file list.
- **Always end with open follow-ups and open questions.** That's the actionable part and the
  main reason to run this. If everything is ticked, say so.
- Keep the write-up's distinction between **verified** and **not verified**. Never upgrade a
  "not verified" item into a settled fact while summarising.
- Preserve the **Corrections** section when relevant — it's what stops a repeat of a mistake.
  If the user is about to work on something a past recap got wrong, lead with that.
- Note the recap's date and flag staleness: a recap is a point-in-time record. If it names a
  file, table, metric, or flag, **verify current state before asserting it's still true** —
  say "as of <date>" or check.
- Multiple recaps: order newest first, and call out follow-ups that appear in more than one
  (repeatedly deferred work is a signal worth surfacing).

## Acting on what you find

Reporting is the default. If the user then wants to work on a follow-up, do it — and mention that
the recap can be updated at the end of the session via the `recap` skill (which ticks resolved
follow-ups). Don't tick boxes during a read; a follow-up is only resolved once the work is done.
