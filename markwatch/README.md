# markwatch

Decision journal + mark-quality capture for the SPY condor ladder.
Stdlib only — no `alpaca-py`, no `pip install`, runs on Python 3.9+.

Owns two things from the plan:

- **§11 Journal** — every decision with its inputs, every veto with the rule that
  fired, and reconciliation of intended against actual fills.
- **§13 open item** — *"how Alpaca's paper engine marks a multi-leg book in the
  scored equity number."* Unowned in rev 3. It decides the headline number.

Also covers **§6.1** (the fill probe, recorded rather than eyeballed) and gives
**§6.3** its limit-walk interval from data instead of a guess.

## Why this is time-critical

`options/quotes` 404s on this account and history covers bars and trades only.
**Quotes not captured while the market is open do not exist afterward.** Nothing
here can be reconstructed on Thursday night. It has to be running before the
first order.

## The question it answers

The hackathon scores broker equity at one instant. Broker equity contains a
*mark* for every open leg. A mark is an estimate, not money.

Each pass values the book three ways:

| | meaning |
|---|---|
| `broker` | what Alpaca says the position is worth |
| `mid` | value at the NBBO midpoint — a price nobody trades at |
| `exec` | value if you closed now: sell longs at bid, buy back shorts at ask |

- `broker ≈ mid` → the score overstates by the full cost of crossing the spread
  on every leg. On a 4-leg condor that is four crossings.
- `broker ≈ exec` → the mark is honest.

Measured on a 1-lot condor at plausible spreads (0.20/0.15/0.20/0.15):
**$35 per condor.** At ~29 contracts that is **~$1,015**, against §4's realistic
outcome of $2,500–3,500. If the engine marks at mid, roughly a third of the
scored result is money that was never collectable.

No guardrail in §8 can see this: the book moves with no trade and no rule fires.

## Run it

```bash
export ALPACA_API_KEY=...            # or APCA_API_KEY_ID
export ALPACA_SECRET_KEY=...         # or APCA_API_SECRET_KEY

python3 -m markwatch.preflight --underlying SPY    # reads only, places nothing
python3 -m markwatch.run --interval 60             # the capture loop
python3 -m markwatch.run --report                  # read the latest snapshot
```

**Run preflight first.** It checks credentials, which account it is pointed at,
the shape of the positions payload, which options feed actually works
(the §6.0 blocker), whether quote timestamps parse, and how stale they really
are — then does one full collector pass. It reports what it found rather than
asserting a pass, because several of these are open questions on this account.

## Journal integration

One context manager around the existing submit path:

```python
from markwatch.hooks import Recorder

rec = Recorder(journal, get_quotes=client.get_quotes)

with rec.submission(kind="submit", underlying="SPY", expiry="2026-09-03",
                    inputs={"spot": spot, "iv": iv, "em": em},
                    intent={"legs": legs, "net_limit": net},
                    symbols=[l["symbol"] for l in legs]) as sub:
    for rule, detail in run_guardrails(legs):     # §8
        sub.veto(rule, detail)
    if sub.vetoed:
        return
    order = broker.submit(legs, net)
    sub.submitted(intended={"legs": legs, "net_limit": net},
                  order_id=order.id, status=order.status)
    sub.filled(order.legs)        # reconciled against NBBO captured at submit
```

The NBBO is captured *before* the order goes out — the only moment the
comparison means anything.

`reconcile_fill` places each fill inside that spread: `0.0` = we crossed the
full spread, `0.5` = mid, `1.0` = price improvement. Normalised so a buy and a
sell mean the same thing.

## Measurement discipline

Carried over from a project where a paper ledger read +$22,737 and executable
prices read −10.58% on the same trades. The failure there was not the strategy,
it was that the measurement quietly dropped its ugliest rows.

- **Freshness guard** — a quote sampled more than `freshness_s` (default 15s)
  from the snapshot instant is `stale`, not a price. An unparseable timestamp
  is stale too, never "now".
- **Unquotable is a rate, never a cost** — no bid, no ask, or a crossed book is
  reported as its own rate. A short leg nobody will buy back is a risk fact;
  averaging it into a percentage hides exactly the leg that hurts.
- **Coverage floor** — under 70% cleanly quoted, the report returns *no verdict*
  rather than a confident average over whichever legs happened to quote.
- **Failures are data** — a 429, a timeout, a missing symbol are recorded and
  classified, never swallowed and never crash the loop.
- **Append-only, WAL** — reads never block the writer, and legs are written
  individually so one malformed row cannot roll back a snapshot that can never
  be recaptured.
- **Priceability is per-leg and directional** — closing a long needs a bid,
  closing a short needs an ask. A zero bid on a long wing is a real value
  (worthless), not missing data. Treating it as missing drops exactly the leg a
  mid-marking broker overstates most, which understates the headline gap.
- **Whatever is still unpriced is carried, not hidden** — its broker mark is
  reported separately and the verdict says the gap is a LOWER BOUND.
- **Coverage is measured by exposure too** — nine $10 wings and one $5,000
  short is not 90% covered in any sense that matters.
- **The feed is recorded per row** — `indicative` quotes are derived, not the
  true OPRA NBBO, and the write-up should be able to say which produced a
  number.

### Verified

The first version of this package had twelve defects, found by a fan-out of
research and adversarial review agents before any of it ran against a live
account. Two are worth naming because they are the exact failure this package
exists to detect:

- Excluded legs were dropped from **both** sides of the comparison, so the
  reported overstatement was systematically too small — on a condor with one
  decayed wing it read $27.50 against a true $52.50.
- `reconcile_fill` inferred trade direction from position sign, so every
  **closing** fill scored as maximum price improvement when it had paid the
  entire spread.

Both now have regression tests. The `side` argument on `reconcile_fill` is
required for this reason: closing a short is a BUY.

## Layout

```
markwatch/alpaca.py      REST adapter (stdlib urllib), feed resolution
markwatch/markcheck.py   the pure math: classification, valuation, verdict
markwatch/collector.py   the sampling loop
markwatch/hooks.py       Recorder — journal integration for submit_condor
markwatch/journal.py     SQLite, append-only, WAL
markwatch/preflight.py   validate every assumption against the live account
markwatch/run.py         CLI entry point
```

## Tests

51 tests, pure functions, no network and no broker:

```bash
python3 -m pytest tests/ -q
```

---

## Live-account verification, 2026-08-30

Run against paper account `PA382RL5C7X8` from the tradesense repo. **First contact with a real
Alpaca account** — the package's own note said the maths was tested and the plumbing was not.

**Working:** credentials, account resolution, options level 3 detected, positions endpoint,
`feed=indicative` quotes (10/10 symbols returned), collector pass, snapshot written.

**This closes the §6.0 blocker in the trading plan** — `feed=indicative` is confirmed against a live
Basic-plan account, not just documented.

### Two things to fix

**1. Freshness is not market-hours aware.** Run on a Sunday, every quote classified stale at a median
age of 185,634s — 51.6 hours, which is Friday's 16:00 close. Correct data, meaningless verdict. The
15s guard will fire spuriously on every out-of-hours run, and it means a weekend run **cannot** settle
whether the feed is real-time during RTH (a question the plan still has open).

Suggest: skip or flag the freshness verdict when the market is closed. Alpaca's `/v2/calendar` and
`/v2/clock` both answer this.

**2. Ran against the rehearsal account.** It reads whatever the environment points at and reports the
account it reached, which is right. Worth an explicit `--expect-account` that refuses on mismatch —
trading the wrong book is the only error in this project that produces no signal at all.

Neither affects the mark-drift maths, which is the part that matters.
