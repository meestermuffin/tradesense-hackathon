# Options volatility-premium agent

Sell defined-risk option premium where implied volatility is rich **relative to a name's own
history** — not where it is high in absolute terms, which turns out to be mildly harmful.

Built for the Alpaca AI Trading Agents Hackathon, 28 Aug – 4 Sep 2026. MIT licensed.

---

## Running it against your own account

Everything below works on your own Alpaca paper account. Nothing you write can collide with anyone
else's data — every artifact is namespaced by account number.

```bash
cp .env.sample .env      # your own paper credentials
make verify              # does this account have what the project needs?
make status              # scheduler, wake schedule, account, last session
make cycle               # rank, select, size — DRY RUN, places nothing
```

**Run `make verify` first.** Entitlements are per-account, not per-user, and the failure mode is a
200 response with keys quietly missing rather than an error. It checks the five things this depends
on, of which `options/bars` on expired contracts is load-bearing — without it the IV series cannot
be rebuilt at all.

`make cycle` is always a dry run. Real orders need `make cycle-live CONFIRM=i-mean-it`, which prints
which account the credentials resolve to before refusing, because a key pair does not announce which
account it belongs to.

### Scheduled agents

`make schedule` installs four `launchd` agents: NBBO capture at 15:50, the cycle at 16:05, an equity
snapshot at 16:45, and a heartbeat at 09:00. Installed dry — arming takes
`make schedule LIVE=1 ACCOUNT=<your account>`, and the account is baked into the plist as an
assertion so swapping `.env` without re-installing aborts rather than trading the wrong book.

**Data written by these is namespaced by account** (`data/nbbo/<account>/`, `data/equity/<account>.csv`,
`data/selection/<account>/`), so running them alongside someone else's is safe.

**The one thing that is not safe: two machines armed live against the *same* account.** Each sizes
against the same 20% risk budget independently, so the account carries double the intended exposure
while each cycle believes it is within limits. The overlap lock is a file inside the clone and cannot
see across machines — it exists to stop a scheduler retry double-trading on one host, and it gives
no protection here. Use your own account, or make sure only one machine is armed.

They also do not survive sleep. `launchd` does not fire calendar jobs while a machine is asleep; it
fires them late, on wake, which is useless for a job whose value is being inside market hours. An
operating machine needs `sudo pmset repeat wakeorpoweron MTWRF 15:40:00`.

## Layout

```
src/            data boundary, BS inverter, signal, selection, execution, risk
                standard library only, no database driver — runs anywhere
scripts/        measurement runners and the operational jobs
docs/probes/    pre-registrations and results, one pair per measurement
docs/           cost model, findings summary
data/           IV series, earnings dates; captures and equity namespaced by account
```

`make` lists every target.

## Dependencies

Runtime: **none.** Standard library only, which is why the measurements run on a fresh clone.

Development: `ruff` for lint and formatting, installed separately (`pipx install ruff`). It is not
imported by anything that ships.
