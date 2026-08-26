---
name: orient
description: Use at the start of any session in this repo, or when picking work back up after a gap — rebuilds what is actually true from the plan, the databases and the clock rather than from memory or a summary.
---

# /orient — start on verified ground

**Run this first.** It reconstructs state from files and running systems, not from recall.

The rule it exists for, inherited from the project next door and re-earned here twice in one day:

> **Verify before asserting.** If a claim can be checked in one command, check it. Say "let me check"
> and check. Never "I believe" or "as I recall".

Two failures it guards against. **Stale recall** — a number that was true this morning. And
**documented-not-measured** — Alpaca's docs have been contradicted by a probe three times now, on
implied volatility, the data floor, and expired chains.

## Step 1 — read the ground truth

```bash
REPO=$(git rev-parse --show-toplevel)
sed -n '1,140p' $REPO/.claude/private/PLAN.md    # decisions and the dated timeline
ls -la $REPO/.claude/private/                     # prior reviews live here
```

`CLAUDE.md` loads on its own and carries the data boundary, the Alpaca gotchas and the measurement
rules. Do not restate it back to the user.

**Do not read the whole plan.** It is ~900 lines. Read the timeline and whichever section the
session's work touches.

## Step 2 — verify live state

**First establish which machine you are on.** Only one has the pipeline; on any other the checks
below do not apply and their absence is not a problem to report.

```bash
docker ps --format '{{.Names}}' | grep -E 'timescale|trader' || echo "no pipeline on this machine"
```

**If the containers are absent:** this is a teammate checkout. Data comes from the parquet in
`data/` through `FileFeatureSource`, everything still runs, and Step 2 is done. Skip to Step 3.

**If they are present**, read state from them — never write, they belong to another project:

```bash
docker exec clerk_timescaledb psql -U postgres -d clerk_dev -t -A \
  -c "SELECT 'bars fresh to ' || max(day)::date FROM ohlcv_daily;"

docker exec forge_timescaledb psql -U postgres -d forge_dev -t -A \
  -c "SELECT 'features fresh to ' || max(ts)::date FROM feature_vectors_1d;"

docker exec trader_postgres psql -U postgres -d trader_dev -t -A \
  -c "SELECT 'max_open_positions=' || max_open_positions FROM risk_config;"
```

**Freshness is the failure mode that costs judged sessions.** There is no scheduler. When bars go
stale the trader places nothing, and every service still reports healthy. If `max(day)` is behind the
last trading day, that is the first thing to fix.

## Step 3 — the clock is a state variable

```bash
python3 - <<'PY'
from datetime import date
today=date.today()
sessions=[date(2026,8,28),date(2026,8,31),date(2026,9,1),date(2026,9,2),date(2026,9,3),date(2026,9,4)]
left=[d for d in sessions if d>=today]
print(f"today {today}  ·  judged sessions remaining: {len(left)}  ·  "
      f"days to submission (4 Sep 11:00 ET): {(date(2026,9,4)-today).days}")
PY
```

The plan states in advance that the baseline **starts mid-window**. Sessions already gone are not a
slip to report; they were budgeted.

## Step 4 — check what has actually run

Probe results live in the plan, not in memory. Confirm against it:

| | how to tell |
|---|---|
| IV endpoints probed | plan section *The IV-history dependency* — done 25 Aug, no IV on this account |
| Expired chains enumerable | done 25 Aug, `status=inactive`, 416 contracts |
| **Test order placed** | check `trader_dev` for orders, or the plan's timeline |
| **Competition accounts created** | three of them, `account_id` on the three trader tables |
| **IV-series probe (the gate)** | nothing downstream is trustworthy until this passes |

## Step 5 — if the plan changed since the last review, say so

Two reviews sit in `.claude/private/`. If `PLAN.md` has moved substantially since the newest one,
**recommend `/quant-review` before work starts** rather than after — a plan reviewed once is not a
plan reviewed. It matters most when new figures, features or cost models have gone in, which is
exactly when a session is least inclined to re-check them.

Do not dispatch it unasked. Surface it in the briefing as the outstanding item it is.

## Step 6 — brief in five lines

Where it stands · what is verified versus assumed · what is outstanding today · anything that
contradicts the plan · the one decision needing the user. Then stop and ask. Never start work off a
briefing.

## Traps this project has already hit

**Alpaca**
- **A documented behaviour is not a measured one.** The paper-fill rule is from the spec and says
  nothing about multi-leg. The data floor was asserted twice before being measured.
- **Absence needs more than one 404.** Test a live *and* an expired symbol, then check
  `docs.alpaca.markets/us/llms.txt`.
- **Entitlements are per-account.** "OPRA agreement is not signed" is a property of one account. The
  competition account is new and unprobed.

**Measurement**
- **The gate:** nothing — no feature, no cost model, no signal — gets built on an implied-volatility
  series nobody has confirmed is computable.
- **There is no historical quote data.** A cost model charging bid/ask against history charges
  against data that does not exist.
- **Short vega and gamma is this book's hidden exposure**, the way beta was the last one's. A raw
  P&L with no decomposition into premium collected versus vol-spike losses is the same defect.

**Working**
- **Check what a counter counts before trusting it.** Three scripted measurements were wrong in one
  day; list items and numbered steps both masquerade as sentence fragments.
- **One live plan.** `PLAN.md` here is canonical. The copy in the neighbouring project was deleted
  because two drift within a session.
- **`.claude/private/` is gitignored** and the repo is public. Strategy detail stays there.
