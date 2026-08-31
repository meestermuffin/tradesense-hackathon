#!/usr/bin/env bash
# Create the sprint issues on GitHub. Idempotent by title -- safe to re-run.
#
#   brew install gh && gh auth login      # once
#   bash scripts/create_issues.sh         # then this
#
# Mirrors the sprint section of TODO.md. If they disagree, TODO.md is the record.
set -euo pipefail

command -v gh >/dev/null || { echo "gh not installed: brew install gh"; exit 1; }
gh auth status >/dev/null 2>&1 || { echo "not authenticated: gh auth login"; exit 1; }

REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner)
echo "repo: $REPO"

for L in "blocking:b60205:must land before Mon 09:30" \
         "monday:0e8a16:Monday 31 Aug runbook" \
         "in-window:1d76db:Tue-Thu, inside the scored window" \
         "deliverable:5319e7:required for submission" \
         "decision:fbca04:needs a human call"; do
  IFS=: read -r name colour desc <<< "$L"
  gh label create "$name" --color "$colour" --description "$desc" --force >/dev/null 2>&1 || true
done

mk () {  # title  labels  body
  if gh issue list --state all --search "$1 in:title" --json title \
       -q '.[].title' | grep -qxF "$1"; then
    echo "  = $1"
  else
    gh issue create --title "$1" --label "$2" --body "$3" >/dev/null
    echo "  + $1"
  fi
}

mk "Wire the markwatch collector into the agent runner" "blocking" \
"\`AgentLoop\` refuses to trade live without it, deliberately: quotes do not exist after the fact on
this account, so a fill placed before the collector starts can never be reconciled against the NBBO
it crossed.

Import \`Collector\` directly with \`src.agent.adapter.callables()\`. \`markwatch.run\` hard-codes its
own client at \`run.py:41\` and cannot be pointed at ours."

mk "Confirm the judged account and point .env at it" "blocking" \
"Everything so far has run against the rehearsal book \`PA382RL5C7X8\`. The judged account must be
brand new per the rules.

Trading the wrong book is the only error in this project that produces **no signal at all** — it
just quietly scores nothing. Guardrail 10 asserts the account, but it has to be told which one."

mk "Re-run markwatch preflight against the judged account" "blocking" \
"Verified working on the rehearsal account 2026-08-30: credentials, options level 3, positions,
collector pass, and \`feed=indicative\` returning 10/10 symbols.

Never run against the judged book. Position-shape and mark checks only mean anything with an open
position, so re-run after the first fill too."

mk "Rebuild the IV series" "blocking" \
"Ends 2026-08-25. \`run_cycle\` refuses past five days, and a percentile computed against a stale
window looks confident and means nothing.

\`make series\`"

mk "Verify macro release times for Sep 1-3" "blocking" \
"Plan §5a has these **inferred from the standard first-week pattern, not verified**.

Market-day structure *is* confirmed from Alpaca's calendar: Sep 1–4 all open, Labor Day is Sep 7, so
it is a full week. The release schedule is not confirmed.

The exposure is Thursday: claims and ISM Services land on the scored day with every Sep 3 position
at peak gamma and no session left to react. NFP is the first Friday, Sep 4, after the snapshot.

A web search returned a calendar shifted by a year and claimed Sep 1 was Labor Day — use a real
source."

mk "Monday 09:45 — run the registered 4-leg fill probe" "monday" \
"\`docs/pending/condor-fill-realism.md\`, committed before the run.

One condor, one contract, a single resting mid limit, no walking. Decides condors versus paired
verticals **for the whole book**, because everything is placed Monday.

Record fill vs BS mid and vs touch — Tuesday's gate needs the realized \`vs_mid\`."

mk "Monday 10:00 — place both tranches" "monday" \
"\`uv run python scripts/run_agent.py --live --expect-account <judged> --collector-running\`

Dry run verified against live prices: 758/763P 776/781C at 13x, and 757/762P 777/782C at 13x.
Total \$9,997 of the \$16,000 book."

mk "Tuesday 09:35 — evaluate the conditional tranche gate" "in-window" \
"Two registered conditions, **both** required:

- Monday's fill cleared at **mid − 0.05 or better**
- Live IV **≤ 0.16**

EV per contract is −\$38 to −\$47 unconditional, +\$21 to +\$34 at mid fills in a calm regime, and
+\$1 to +\$14 touch-ish. The sign lives on both inputs.

If either fails: no entry, and **record which one**. Running at two tranches is the correct outcome,
not a shortfall."

mk "Pin-risk checks Wed and Thu 15:15" "in-window" \
"If spot sits inside either wing in the last 45 minutes of an expiry day, close that condor.

**An mleg market order has never been verified on this account** — every order verified was a limit.
Use a marketable limit unless that changes."

mk "One-page write-up" "deliverable" \
"Required deliverable, not started. Thursday evening is free — the result is known by then.

The honest story: the signal was measured, failed to replicate out-of-sample (+0.1753 → +0.0414,
p 0.2184) and was shelved with the record public. The book that trades rests on payoff shape, not
prediction, and makes no edge claim."

mk "Demo video" "deliverable" "Required deliverable, not started."

mk "Does the agent decide enough for criterion 2?" "decision" \
"Judging is P&L **and** *\"the creativity, autonomy, and robustness of the agent trading workflow\"*.

Right now strikes are solved deterministically, sizing is capped, and entry days are fixed. What the
model actually decides is the Tuesday go/no-go, the rationale text, and breach handling.

That is thin for a criterion about autonomy. Either widen its remit, or defend the narrowness as the
design — the guardrails are the interesting part and they are genuinely unusual.

Raised by Solo."

mk "Response to Thursday's macro cluster" "decision" \
"Accept it, widen Thursday-expiry strikes, or size tranche 2 smaller. Needs the verified calendar
first (see the macro issue).

Two of three positions expire Sep 3, so 67% of max loss rides that single print against 50% with two
tranches."

echo "done"
