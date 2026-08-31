# tradesense — Alpaca AI Trading Agents Hackathon

An autonomous options agent that sells defined-risk premium on SPY — and the record of the signal it
was built to trade on, which we tested, falsified and shelved before the window opened.

## We do not claim an edge

We built a volatility-premium signal: rank names by where implied vol sits against their own
history, sell the richest. On the sample we developed it on it looked good — rank IC **+0.1753**.
Then we found every test had used 249 of the 597 sessions committed in the repo. On the **327
sessions no test had touched**, the same measurement reads **+0.0414, p 0.2184** — significant
in-sample, absent out-of-sample, the textbook signature of overfitting. Shelved, publicly, in
`docs/2026-08-30-strategy-shelved.md`.

**What trades instead rests on payoff shape.** A short-premium book collects decay every session and
loses only on a large move, so over four sessions it finishes modestly green more often than not.
That is a structural argument, and we state it as the hypothesis it is.

## How the measurement stayed honest

Every result was registered before it ran — design, thresholds and decision table committed to git
first, so `git merge-base --is-ancestor` proves the prediction preceded the outcome.

That caught four defects in our own work, three previously unnoticed: a permutation null **~3× too
narrow** because it ignored a 21-session overlap, so every published p-value read the floor; a cost
figure overstated by exactly **2.00×**; and a day-count mismatch that made a genuine 20-delta strike
appear to sit at 0.67× the expected move. The plan had described that last one as a deliberate
choice. It was a bug. Two adversarial reviews are in the repo, including the one that refuted us.

## The agent

The model emits a **template** — underlying, expiry, short delta, width, contracts, rationale. It
**cannot express a price**; the tool solves the strikes and computes the net limit itself. On a
multi-leg Alpaca order `limit_price` is a *net* price where negative means credit, and inverting it
does not raise — it places a real order at the wrong price, silently. Rather than check the model's
arithmetic downstream, the field is absent from the schema it writes.

**Its authority is narrow and asymmetric.** The model may refuse a trade, and may *tighten* the
short delta inside a registered band. It cannot change the ladder, the sizing or the expiries, and
approving is not sufficient — the guardrails run afterwards regardless. Every failure path resolves
to a refusal: unparseable output, a timeout, an empty reason. **A bad model response costs a trade
and cannot cause one.**

**On its first live run it refused a trade, and it was right.** It objected that both short deltas
came from a single flat implied vol, so the 763 put and 776 call reported a near-identical 0.197
despite unequal distance from spot — and that under SPY's real put skew the put was nearer 0.24, the
call nearer 0.17. Checked against live quotes: their own vols invert to 0.1488 and 0.1201, making
the true deltas **0.221 and 0.171**. The delta guardrail had been passing a position whose actual
deltas sat outside the band it exists to enforce. Strikes are now solved on the skew surface. It
caught what the rules could not, because the rules were checking a number that did not describe the
position.

**Capability isolation is a property of the process, not a prompt.** The agent's MCP server starts
with `ALPACA_TOOLSETS=account,assets,news` — 20 tools, and `place_option_order` is not among them.
Ordering lives on a second instance behind the guardrails. Verified by listing tools on each.

**Eleven guardrails** stand between decision and submission, each returning a structured veto naming
the rule that fired — including an account assertion, because trading the wrong paper book is the
one error that produces no signal at all, and a kill switch keyed on mark-to-market drawdown rather
than realised loss, because a book that closes nothing realises nothing until expiry.

**The score is a mark, not a fill.** If the paper engine marks a multi-leg book at mid it credits us
spread we could never have collected — roughly $1,015 here, about a third of the expected result —
and no guardrail sees it, because the book moves with no trade. So `markwatch/` samples every 60
seconds and values the book three ways: what the broker says, what it is worth at mid, and what
closing now would realise.

## Measured, and not

Measured: pairwise correlation **+0.409**, rising to **+0.554** in volatile regimes, so ten
positions behave like 1.67 independent bets; fees at $0.025 per contract-leg; and that this account
serves no implied volatility at all, so IV is computed by Black–Scholes inversion rather than read.

Not measured, and labelled so: whether four-leg orders fill at a mid limit — a registered one-lot
probe settles that before anything is sized — and whether the broker nets assignment against
same-day exercise.

**333 tests** in the trading path and **51** in the mark instrumentation, no network needed, on a fresh clone.

## Results

*(Filled after the Thursday 3 September close.)*

---

MIT licensed. The measurement log, the registrations, the reviews that refuted us, and the record of
what we got wrong are all in this repository.
