# tradesense

A defined-risk options agent that sells short-premium iron condors on SPY, with a language model in
the loop that can veto any entry and a risk layer that can veto the model.

## What we set out to do, and what happened

We built a volatility-premium signal: rank names by where implied volatility sits against their own
history, and sell the richest. On the sample we developed it against it looked good, with a rank
information coefficient of +0.1753 and a control arm on raw IV level reading −0.1055.

Late in development we found that every test had run against 249 of the 597 sessions committed to
the repository. On the remaining 327, which no test had touched, the same measurement reads +0.0414
with a p-value of 0.2184. Significant in sample, absent out of sample. We shelved it and published
the account in `docs/2026-08-30-strategy-shelved.md`, including the parts that survive.

What trades in its place makes no prediction. It is a ladder of defined-risk iron condors held to
expiry, which profits from the passage of time rather than from knowing where SPY is going. The
payoff shape is structural: the position is theta-positive, and its loss is bounded and requires a
move. The profitability is not structural. Selling premium is compensation for gamma risk, and it
pays only while implied volatility runs above what is subsequently realized. On our entry days it
did, with 2-DTE implied at 0.126 against realized of 0.065 to 0.103, but that is a hint rather than
a measurement and we do not present it as an edge.

## The review layer, which is the actual result

A model sits between the plan and the order. Its authority is one-directional by construction: it
may refuse an entry, or tighten the short delta within a registered band, and nothing else. It
cannot express a price, because the field is absent from the schema it writes.

That omission is deliberate and it is load-bearing. On a multi-leg Alpaca order the limit price is a
*net* price where negative means a credit, and inverting the sign raises no error. It places a real
order at the wrong price, silently. Rather than validate the model's arithmetic downstream, we
removed its ability to do the arithmetic at all.

Approval is not sufficient either. Eleven deterministic guardrails run afterwards regardless, each
returning a structured veto naming the rule that fired. Every failure path in the model resolves to
a refusal, including an unparseable response, a timeout, and an empty reason. A bad response from
the model therefore costs a trade and cannot cause one.

On its first live run it refused a trade, and it was right for a reason we had not anticipated. It
observed that both short deltas had been computed from a single flat implied volatility, which made
a put and a call at unequal distance from spot report near-identical deltas of 0.197 and 0.198.
Inverting each strike against its own quote gave true deltas of 0.221 and 0.171. The guardrail
responsible for keeping short deltas inside a band had been validating a figure that did not
describe the position it was protecting. We had written that guardrail, tested it, and watched it
pass. A rules engine could not have caught the error, because the rule was checking the wrong number
rather than checking it wrongly.

Capability isolation is enforced by the process rather than by a prompt. The agent's MCP server
starts with `ALPACA_TOOLSETS=account,assets,news`, twenty tools, and `place_option_order` is not
among them. Ordering runs on a second instance behind the guardrail layer. We verified this by
listing the tools available to each.

## Execution, measured rather than assumed

There is no historical options quote endpoint on this account, so a fill not captured at the moment
of submission is uninterpretable afterwards. Before sizing anything we ran a registered
one-contract probe to establish whether four legs clear at a single mid limit here. All four filled
at exactly the captured NBBO mid, thirty-six milliseconds after the order reached the book. That
verdict then gates the sized entries, which refuse without it, because a probe that crashed looks
identical to one that never ran and absence is not permission.

Against the NBBO captured at submission, the four structures filled at +0.000, −0.010, −0.055 and
−0.015 relative to mid. The third is worth naming because we first reported it as price improvement.
That figure had been computed against the mid we estimated at planning time rather than the market
at submission, and the two differed by 0.075. The correction is recorded in the issue tracker rather
than quietly amended.

The scored number is a mark, not a fill. If the paper engine values a multi-leg book at mid it
credits us spread we could never have collected, and no guardrail can see it because the book moves
with no trade. The instrumentation therefore samples every sixty seconds and values the book three
ways: what the broker reports, what it is worth at mid, and what closing it now would realize.

Also measured: pairwise correlation of +0.409, rising to +0.554 in volatile regimes, so ten
positions behave like 1.67 independent bets. Not measured, and labelled as such: whether the broker
nets assignment against same-day exercise.

The concentration that follows from this is worth stating rather than leaving for a reader to
notice. Two of the structures share an underlying, an expiry and near-identical strikes, so they
breach together and the book is closer to one position than to two. We knew that when the second
was placed, because the model raised it as a reason to refuse and a human overrode it. The risk was
accepted with the argument in front of us, and it is bounded: these are defined-risk condors, only
one side of each can breach, and the maximum loss is known at entry.

400 tests cover the trading path and 51 the mark instrumentation, all against fakes, so the suite
runs on a fresh clone with no credentials and no network.

## Results

*(Filled after the Thursday 3 September close.)*

---

MIT licensed. The measurement log, the registrations, the adversarial reviews including the one that
refuted us, and the record of what we got wrong are all in this repository.
