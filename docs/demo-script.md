# Demo video — shot list and script

**Target 3:00.** Record Thursday after the 16:00 close, when the scored number exists. Everything
below except the final figure can be rehearsed today.

No length was specified in the rules, so 3:00 is a judgement: long enough for the skew catch to
land, short enough that nobody skips. If it runs past 3:30, cut section 5 first — it is the
least load-bearing.

**Tone.** The differentiator here is not the P&L, it is that the measurement record is honest.
Lead with the thing most teams would bury. Do not oversell; the restraint *is* the pitch.

---

## 0:00–0:25 · Open on the falsification

**On screen:** `docs/2026-08-30-strategy-shelved.md` open in an editor, scrolled to the IC numbers.

> "We built a volatility-premium signal, and it looked good — rank IC of plus one-seven-five-three.
> Then we found every test had used 249 of the 597 sessions in the repo. On the 327 sessions no
> test had touched, the same measurement reads plus oh-four-one-four, p of point two-two.
> Significant in sample, absent out of sample. So we shelved it, publicly, and we do not claim an
> edge."

**Why this first.** It is the only thing in the submission nobody else will say, and it makes
everything after it credible. It also pre-empts the obvious question about the numbers.

---

## 0:25–0:55 · What actually trades

**On screen:** `src/agent/loop.py` — the `LADDER` constant, then `src/options/condor.py` —
`CondorRequest`, whose docstring reads *"What the model is allowed to ask for. Note what is
absent: any price."* Show the field list under it: underlying, expiry, short delta, wing width,
contracts, rationale. **There is no price field to point at — the point is the absence.**

> "What trades instead rests on payoff shape, not prediction. A short-premium book collects decay
> every session and loses only on a large move.
>
> The model emits a template — underlying, expiry, short delta, width, contracts, rationale. It
> cannot express a price. On a multi-leg Alpaca order the limit price is a *net* price where
> negative means credit, and inverting it does not raise an error — it places a real order at the
> wrong price, silently. So rather than check the model's arithmetic downstream, the field is
> absent from the schema it writes."

**Hold on that field list for a full beat.** It is the clearest single image of the whole design:
the constraint is the schema, not a check.

---

## 0:55–1:45 · The model catches a bug in our own guardrails ← THE CENTREPIECE

**On screen:** split — the model's refusal text on the left, the verification table on the right.

> "On its first live run the model refused a trade. It said both short deltas had been computed
> from a single flat implied vol, so the 763 put and the 776 call both reported point one-nine-seven
> despite unequal distance from spot — and that under SPY's real put skew the put was nearer point
> two-four and the call nearer point one-seven.
>
> We checked it against live quotes. The put's own vol inverted to point one-four-eight-eight, the
> call's to point one-two-oh-one. True deltas: point two-two-one and point one-seven-one.
>
> Our delta guardrail had been passing a position whose actual deltas sat outside the band it
> exists to enforce. A rules engine could not have found that, because the rule was checking a
> number that did not describe the position."

| strike | own IV | delta at flat IV | true delta |
|---|---|---|---|
| 763 put | 0.1488 | 0.197 | **0.221** |
| 776 call | 0.1201 | 0.198 | **0.171** |

**This is the answer to "is the agent doing anything a script could not."** Give it the most time.
Say plainly that the model was right and we were wrong.

---

## 1:45–2:15 · Authority, and why a bad answer is cheap

**On screen:** `src/agent/mcp.py` — `AGENT_TOOLSETS` beside `WRITE_TOOLSETS`. Then a terminal
listing tools on each MCP instance.

> "Its authority is narrow and asymmetric. It may refuse a trade, and it may tighten the short
> delta inside a registered band. It cannot change the ladder, the sizing or the expiries — and
> approving is not sufficient, because eleven deterministic guardrails run afterwards regardless.
>
> Every failure path resolves to a refusal: unparseable output, a timeout, an empty reason. So a
> bad model response costs a trade and cannot cause one.
>
> Capability isolation is a property of the process, not a prompt. The agent's MCP server starts
> with account, assets and news — twenty tools, and place_option_order is not among them. Ordering
> lives on a second instance behind the guardrails."

---

## 2:15–2:40 · Measured, not assumed

**On screen:** terminal running the probe verdict, then `data/probe/2026-08-31-verdict.json`.

> "Before sizing anything we ran a registered one-contract probe to find out whether four legs
> clear at a single mid limit on this venue. All four legs filled at exactly mid — thirty-six
> milliseconds after the order reached the book.
>
> That verdict is a gate, not a note. The sized entry reads it and refuses if it is missing — a
> probe that crashed looks exactly like one that never ran, and absence is never permission."

**Show, briefly:** the run printing `probe verdict CONDORS from 2026-08-31`.

**One caveat to say out loud, in one sentence:** "n equals one — it distinguishes 'four legs fill
at mid here' from 'they do not', and it cannot establish a fill rate."

**Say milliseconds, not seconds.** Broker `submitted_at` 14:19:42.902 → `filled_at` 14:19:42.938 is
**0.036 s**. The ~4 s figure that appears in some earlier notes is the script's whole round trip —
chain fetch, submit, poll — not the fill. On camera that distinction matters: one is a claim about
the venue, the other is a claim about our own latency.

---

## 2:40–3:00 · The score is a mark, not a fill

**On screen:** the dashboard (`make server`, localhost:3100), then the journal row count.

> "If the paper engine marks a multi-leg book at mid it credits us spread we could never have
> collected — and no guardrail can see it, because the book moves with no trade. So we sample every
> sixty seconds and value the book three ways: what the broker says, what it is worth at mid, and
> what closing now would actually realise.
>
> Eleven thousand marks, four orders, sixteen leg fills, all in a SQLite journal with the NBBO
> captured at submission — which cannot be reconstructed afterwards on this account.
>
> Final equity: **[PASTE THURSDAY'S CLOSE]**. The signal we started with does not work, we said so,
> and the thing we shipped is the machinery that found out."

---

## Practical notes

- **Record after Thursday 16:00.** Only the last figure depends on it.
- **Do not read the numbers off the screen wrong.** Every figure above is checkable in the repo;
  a misquote is the one thing that would undercut the honesty pitch.
- **Screen-record at 1440p or better**; terminal font large enough to read at half size.
- **Have these open before you start**, so there is no fumbling:
  - `docs/2026-08-30-strategy-shelved.md`
  - `src/options/condor.py` (`CondorRequest` — the field list with no price in it)
  - `src/agent/mcp.py`
  - `data/probe/2026-08-31-verdict.json`
  - a terminal in the repo root, and `make server` already warm on :3100
- **Do not show `.env`, and do not show the account number on screen.** The repo is public.
- If a live command is risky to run on camera, run it beforehand and show the output — nothing here
  needs to place an order during the recording.

## Still outstanding, and not covered by this script

**Application URL** is listed as a required deliverable in `TODO.md` and has nothing behind it. The
cheapest path is serving the existing `ui/` dashboard read-only off a committed JSON snapshot, so
the demo's source is public. That is a separate task from this video and needs a decision.
