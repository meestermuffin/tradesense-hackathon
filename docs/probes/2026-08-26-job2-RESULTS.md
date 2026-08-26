# Results — job 2: is the ranking a scheduled-event detector?

Registrations `1ea57dc` + addenda `237bb2c`, `2eca3b5`, and the powered test's own, all ancestors of
this commit. Earnings dates: `data/earnings_8k_2024_2025.json`, **SEC 8-K Item 2.02 filing dates**,
67 announcements across ten single-name underlyings. SPY returns zero — correct, it is an ETF.

## The question

The external reviewer's attack on the premise, 2026-08-25: a large share of "this name's IV is
unusually high" is simply **earnings approaching**, so the ranking may be an earnings-proximity
detector. Selling premium into a scheduled binary event is not selling an overpricing — the IV is
high *because* a real move is coming, and it is usually priced about right for it.

**If most of the IV-percentile variance is event timing, filtering does not protect the strategy — it
deletes it.**

## Results

| | name-days | **A · IV percentile** | perm p | NW t(21) | C · control |
|---|---|---|---|---|---|
| baseline, all name-days | 1807 | **+0.1753** | 0.0010 | 2.45 | −0.1055 |
| ±2 sessions around announcements removed | 1674 | **+0.1831** | 0.0010 | 2.41 | −0.0863 |
| ±2, TSLA deliveries not treated as events | 1689 | +0.1679 | 0.0010 | 2.25 | −0.0933 |
| **powered: forward outcome window clean** | **1145** | **+0.1561** | **0.0010** | 1.69 | −0.0938 |

## Why the powered row exists

The ±2 window came from `earnings_blackout_days = 2` — a **risk** parameter, governing when it is
unwise to hold a position. Job 2 asks a **validity** question, and the outcome is realized volatility
over the next 21 sessions, so an announcement anywhere in that window sits inside the *outcome* even
when the name-day is weeks from the event.

| | share of name-days |
|---|---|
| forward 21-session window contains an announcement | **35.8%** |
| removed by the ±2 exclusion | **7.4%** |

**The registered exclusion reached about a fifth of the contamination it existed to test for.** The
powered test removes every name-day whose forward window contains an announcement — 36.6% of the
sample — leaving only name-days where no scheduled event contributed to realized vol at all.

## Verdict

**The ranking is not a scheduled-event detector.** Measured on clean name-days only, A holds at
**+0.1561** against a baseline of +0.1753 — an 11% relative decline — with permutation p at the floor
of **0.0010**, meaning the observed IC exceeded all 1000 within-day shuffles at seed 42.

Events contribute modestly. They do not drive it. **The reviewer's attack on the premise is answered
at full power, and it was the strongest attack anyone had made on this strategy.**

The Newey–West t falls to **1.69**, below the conventional 2. That is what removing a third of the
sample does to a standard error, and it is reported rather than buried. The registration named the
permutation null as primary because a daily Spearman over 11 names does not have trustworthy
asymptotics — but a reader who prefers the t should read this as *significant by permutation, not by
t, on 111 days*.

The control arm stays negative across every cut (−0.086 to −0.106): selling the highest absolute IV
remains mildly harmful whether or not events are in the sample.

## What this still does not establish

- **Not a P&L number.** No option priced, no cost charged. The spread estimator is unfittable from
  historical data — see `docs/cost-model.md` — so a backtested return remains unquotable.
- **Survivorship.** Eleven names on 2026 liquidity applied to 2024–25.
- **One regime**, one 12-month window, 111 usable days in the powered cut.
- **Wrong tenor** — 30-DTE reference series, 5–9 DTE traded structure.
- **Only scheduled events are removed.** Unscheduled vol events — macro prints, guidance, sector
  shocks — are still in both samples and are not testable this way.
- The judged window's own composition still cuts the other way: NVDA and CRM print 26 Aug, so the
  window opens into post-earnings IV crush on two large names. That is a fact about the week, not
  about the signal.
