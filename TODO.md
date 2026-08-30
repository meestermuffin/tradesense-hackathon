# TODO

Hackathon window **Fri 28 Aug 09:30 ET → Fri 4 Sep 09:30 ET**. Submission **Fri 4 Sep 09:30 ET**.

**P&L is measured over a shorter window than the hackathon runs**, quoted from the event page:

> Official P&L measurement: Monday, August 31 at 9:30 a.m. ET to Friday, September 4 at 9:30 a.m.
> ET. We will be looking at the portfolio's total equity as of EOD Thursday Sep 3rd. Any option
> exercises and assignments for options expiring on Sep 3rd will be reflected in the EOD value.

So the scored moment is **EOD Thursday 3 Sep**, not Friday. Positions expiring 3 Sep settle *into*
the scored number. Fri 28 Aug sat inside the hackathon window but **outside P&L measurement** — the
flat book that session cost nothing on the P&L criterion.

**The signal is shelved** — see `docs/2026-08-30-strategy-shelved.md`. The submission is now an
agent, a risk layer, and a measurement record that falsified its own hypothesis. Items below that
assumed a working edge are struck.

---

## Mandatory — the submission fails without these

- [ ] **The trading agent.** MCP server or CLI. This is one of three mandatory core requirements and
      it is **completely untouched.** Today's decision path is a percentile rank and a hardcoded
      template — deterministic end to end, with no AI anywhere in it. Every measured result in this
      repo is worth nothing to a judge if the submission does not satisfy the rules.
      *Largest remaining piece of work. Nothing else on this list competes with it.*
- [ ] **One-page write-up.** Required deliverable, not started.
- [ ] **Demo video.** Not started.
- [ ] **Application URL.** The plan's cheapest option is a thin read-only page in this repo reading a
      JSON snapshot the cycle writes, so the demo's source is public. Not started.

## Decisions that gate other work

- [ ] **Structure: put credit spreads or iron condor.** Currently `put_credit` at 0.25 delta because
      it was needed to build against, never reviewed. Directional short-delta versus vol-pure. One
      line in `scripts/run_cycle.py:TEMPLATE`. **Gates arming Friday, not Thursday's rehearsal.**
- [ ] **Response to the regime finding.** Roll is estimable on 70.4% of calm days and 29.6% of
      volatile ones, so `docs/pending/cost-composition.md`'s imputation rule is broken. Choose and
      register one: report gross with the limitation stated · restrict cost-adjusted claims to calm
      regimes · find a regime-robust estimator (no candidate). **The sweep's cost line is unsupported
      until this is done.**
- [ ] **Total risk cap.** Mean pairwise correlation is +0.409, so ten positions behave like 2.14
      independent bets. Either lower the 20% cap so the correlated case sits where 20% was meant to,
      or keep it and state the exposure. Doing neither leaves a number implying diversification the
      measurement says is absent.
- [ ] **Print-agreement filter.** Registered and costing 34.3% of name-days, which drops the tradeable
      universe below the position cap. Accept the smaller book, or reject the margin on an argument.

## Dated

- [ ] **Thu 27, before 15:50** — `make schedule LIVE=1 ACCOUNT=PA382RL5C7X8` for a live rehearsal in
      the test account. Thursday is outside the judged window, so it is a free dress rehearsal with
      real orders and real fills.
- [ ] **Fri 28** — swap `.env` to competition credentials **and** `make schedule LIVE=1
      ACCOUNT=PA3BUA9MX72C`. Both, or the account assertion aborts. Do not arm both on Thursday: it
      would put rehearsal fills in the judged book.
- [ ] **Wed 2 Sep** — feature freeze per the plan. Anything not working by then does not ship.

## Measurement, mostly blocked on data that does not exist yet

- [ ] **Delta sweep** — registered in `docs/pending/delta-sweep.md`. Blocked on the widened NBBO
      capture settling claim 3, which is the only thing that can. Capture runs itself at 15:50.
- [ ] **Test A, directional IC** — registered in `docs/pending/test-a-directional-ic.md`. Not blocked;
      can run whenever.
- [ ] **Roll → quoted ratio** — one session is not a calibration. Needs captures to accumulate.
- [ ] **Bar close vs 15:50 mid drift** — needs tomorrow's bar for today's capture.
- [ ] **Re-run the IC on the 30-month series** — 2.4× the data. Needs its own registration; re-running
      a registered test on new data and reporting the number is the defect this project keeps
      catching.
- [ ] **Kill switch has never fired.** The 5% drawdown flatten-and-stop path is untested.
- [ ] **The scheduled cycle has never placed an order.** Both live round trips were placed by hand.

## Judged criteria we are not working on

- [ ] **Social engagement** — a separate $1,000 prize and one of five judged criteria, worth up to
      five post links tagging the organisers. Budgeted at ~20 minutes a day in the plan and currently
      getting zero.
- [ ] **The LLM ablation** — LLM versus deterministic versus random, three accounts. This is what
      makes the agent non-cosmetic: not that it exists, but that we measured whether it earns its
      place. Needs the agent first, and a third paper account.
