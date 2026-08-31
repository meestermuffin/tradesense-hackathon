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

## Sprint — Mon 31 Aug → Fri 4 Sep 09:30

P&L measured **Mon 09:30 → EOD Thu 3 Sep**. Submission **Fri 09:30**. Scored on total equity.

### Blocking before Monday 09:30

- [x] **Wire the markwatch collector into the runner.** Done — `src/agent/collector.py` supervises
      `python -m markwatch.run` as a subprocess and `require_running()` raises before any order.
      `run_agent.py --live` starts it. Journal wired too: `Journal` + `Recorder`, passed into
      `submit()`, so the NBBO at submission is captured — it cannot be recovered afterwards.
- [x] **Confirm which account trades, and point `.env` at it.** Done 31 Aug 02:30. `.env` now
      holds the `PA3BUA9MX72C` keys (mode 600); `/v2/account` confirms `PA3BUA9MX72C`, ACTIVE,
      equity $100,000 untouched, options level 3, not blocked. Rehearsal keys backed up outside
      the repo. **Rotate these after submission — they were pasted into a chat transcript.**
- [x] **Re-run `markwatch.preflight` against the judged account.** Done, green: account matches,
      level 3, positions endpoint ok, indicative quotes work, collector pass completed. The
      stale-quote warning is the weekend (last tick Fri 19:59 UTC), not a fault. Re-run after the
      first fill — the position-shape and mark checks need an open book.
- [ ] **Rebuild the IV series.** Ends 2026-08-25; `run_cycle` refuses past five days. `make series`.
- [ ] **Verify macro release times** against a real economic calendar. Plan §5a has them
      *inferred*. Market-day structure is confirmed (Sep 1–4 open, Labor Day is Sep 7), the release
      schedule is not. Claims and ISM Services land on the scored day.

### Monday 31 Aug

**Scheduled.** `make agent-schedule` installs the four dated launchd jobs (09:35 dry, 09:45 probe,
10:00 tranches, Tue 09:35). Currently **installed but UNARMED** — no `--live`, nothing will place.
To arm: `make agent-schedule LIVE=1 ACCOUNT=PA3BUA9MX72C`, which re-verifies the credentials
resolve to that account before writing the plists. Remove with `make agent-unschedule`.

**A closed laptop means no trade, not a late one.** launchd runs a missed job on wake, so every
job passes `--at HH:MM` and refuses outside a ten-minute window. Keep the machine awake and
plugged in.

- [ ] 09:31 — re-probe options quote latency. Our measurement says real-time, the docs say 15-min
      delayed. A weekend run cannot settle it.
- [ ] 09:35 — `run_agent.py` dry run on live spot and IV, eyeball the strikes.
- [ ] **09:45 — the registered fill probe.** One condor, one contract, single resting mid limit, no
      walking. `docs/pending/condor-fill-realism.md`. Decides condors vs paired verticals for the
      whole book.
- [ ] 10:00 — place both Monday tranches. Record the realized `vs_mid`; Tuesday's gate needs it.

### Tuesday 1 Sep

- [ ] 09:35 — evaluate the two gate conditions: Monday's fill at mid − 0.05 or better, **and** live
      IV ≤ 0.16. Enter tranche 3 or **record which condition failed**. A refusal is the correct
      outcome, not a shortfall.

### Wednesday 2 Sep – Thursday 3 Sep

- [ ] Wed 15:15 and Thu 15:15 — pin-risk check. If spot is inside either wing in the last 45
      minutes of an expiry day, close that condor. **An mleg market order has never been verified**;
      use a marketable limit unless it is.
- [ ] **Thu 16:00 — equity snapshot. This is the scored moment.**

### Before Friday 09:30

- [ ] One-page write-up. Not started.
- [ ] Demo video. Not started.
- [ ] Push everything.

### Decisions still open

- [x] **Does the agent decide enough?** Resolved as *defend the narrowness*, with evidence. The
      model reviews every tranche and on its first live run **refused one and was right**: it caught
      that both short deltas were computed off a single flat IV, so guardrail #3 was validating
      deltas that did not describe the position (true 0.221/0.171 against a reported 0.197/0.198).
      A rules engine could not have found that. Written up in `docs/submission.md` and issue #16.
- [ ] **Thursday's macro cluster.** Accept it, widen Thursday-expiry strikes, or size tranche 2
      smaller. Needs the verified calendar first.

### Known gaps, carried deliberately

- 4-leg **fill** behaviour is unmeasured until Monday's probe.
- mleg **market** orders unverified — every order verified here was a limit.
- The $35,000 cash floor assumes the broker nets assignment against same-day exercise. Unverified.
- NBBO for 27 and 28 Aug are **permanently lost** to a bug in the pydantic port. Not recoverable.

---

## Mandatory — the submission fails without these

- [x] **The trading agent.** Done. `src/agent/` — two MCP instances (read-only `account,assets,news`
      for the agent, `trading` behind the guardrails), `AgentLoop.tick`, and a model reviewer in
      `src/agent/model.py` that can refuse a tranche or tighten the short delta inside the
      registered band, and can do nothing else. Every failure path resolves to a refusal.
- [ ] **One-page write-up.** Drafted at `docs/submission.md` (~880 words). Needs the Thursday
      close for the Results section, and a read-through once the numbers are real.
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
