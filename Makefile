# Manual entry points for everything the scheduler runs automatically.
#
# The scheduled agents and these targets invoke the same scripts, so a manual run and a scheduled
# run cannot drift. Run `make` for the list.

PY       := python3
ROOT     := $(shell pwd)
DEADLINE ?= 2026-09-04
LIVE     ?= 0
ACCOUNT  ?=
SERIES   ?=
START    ?= 2024-03-01
END      ?= $(shell $(PY) -c "import datetime;print(datetime.date.today()-datetime.timedelta(days=1))")

.DEFAULT_GOAL := help
.PHONY: help status heartbeat capture cycle cycle-live snapshot \
        series ic job2 probe roll risk verify schedule cleanup logs check lint fmt

## ---- everyday ----

help:  ## show this list
	@echo "tradesense — manual runs (the scheduler calls the same scripts)"
	@echo
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN{FS=":.*?## "}{printf "  \033[1m%-16s\033[0m %s\n",$$1,$$2}'
	@echo
	@echo "  vars: DEADLINE=$(DEADLINE)  START=$(START)  END=$(END)"

status:  ## scheduler, wake schedule, account, and last session — the one-look check
	@echo "── scheduled agents ─────────────────────────────"
	@launchctl list 2>/dev/null | grep tradesense || echo "  none installed — run 'make schedule'"
	@echo
	@echo "── wake schedule (launchd will not fire while asleep) ──"
	@pmset -g sched | grep -iE 'wakepoweron|wake at' | head -4 || true
	@pmset -g sched | grep -q -i 'repeating' \
	  || echo "  NO REPEATING WAKE. A closed lid at 15:50 means no capture and no error."
	@echo
	@echo "── account ──────────────────────────────────────"
	@$(PY) -c "import sys;sys.path.insert(0,'.');from src.data.alpaca import AlpacaClient as A;\
a=A();ac=a.account();p=a.positions();\
print(f\"  {ac['account_number']}  equity \$${float(ac['equity']):,.2f}  open legs {len(p)}\");\
print('  market open' if a.clock().get('is_open') else '  market closed')"
	@echo
	@echo "── last session ─────────────────────────────────"
	@$(PY) scripts/heartbeat.py || true

risk:  ## portfolio risk profile — correlation, effective bets, worst common days
	@$(PY) scripts/risk_correlation.py

verify:  ## check this account has the entitlements the project needs
	@$(PY) scripts/verify_account.py

heartbeat:  ## did yesterday's capture, cycle and equity row happen?
	@$(PY) scripts/heartbeat.py

capture:  ## capture NBBO across the universe (refuses outside market hours)
	@$(PY) scripts/capture_nbbo.py

cycle:  ## rank, select, size — DRY RUN, places nothing
	@$(PY) scripts/run_cycle.py --deadline $(DEADLINE) $(if $(SERIES),--series $(SERIES),)

snapshot:  ## append one row to the equity curve
	@$(PY) scripts/snapshot_equity.py

## ---- trading (guarded) ----

cycle-live:  ## PLACE REAL ORDERS. Requires CONFIRM=i-mean-it
ifneq ($(CONFIRM),i-mean-it)
	@echo "refusing: this places real orders in whichever account .env points at."
	@echo
	@$(PY) -c "import sys;sys.path.insert(0,'.');from src.data.alpaca import AlpacaClient as A;\
a=A().account();print(f\"  .env currently points at {a['account_number']}, equity \$${float(a['equity']):,.2f}\")"
	@echo
	@echo "  re-run as:  make cycle-live CONFIRM=i-mean-it"
	@exit 1
else
	@$(PY) scripts/run_cycle.py --live --deadline $(DEADLINE) $(if $(SERIES),--series $(SERIES),)
endif

## ---- data and measurement ----

series:  ## build the IV series (START..END; END defaults to yesterday, today 403s)
	@f="data/iv_series_$$(echo $(START) | cut -c1-7)_$$(echo $(END) | cut -c1-7).csv.gz"; \
	if [ -f "$$f" ]; then \
	  echo "refusing: $$f already exists."; \
	  echo "  Registered results were computed on these files and must stay reproducible."; \
	  echo "  To build a different window, pass START= and END=."; \
	  exit 1; \
	fi; \
	echo "building $(START) .. $(END)  — historical options data excludes the current session"; \
	$(PY) scripts/build_iv_series.py --start $(START) --end $(END)

ic:  ## baseline signal IC, per the registered protocol
	@$(PY) scripts/baseline_ic.py

job2:  ## does the ranking survive removing scheduled-event name-days?
	@$(PY) scripts/job2_earnings.py

probe:  ## IV-series gate probe, stage 2, v2 selection
	@$(PY) scripts/iv_series_probe.py --stage 2 --select traded

## ---- scheduler ----

schedule:  ## install the four agents. Arm with: make schedule LIVE=1 ACCOUNT=PA...
	@LIVE=$(LIVE) ACCOUNT=$(ACCOUNT) bash scripts/install_schedule.sh

cleanup:  ## remove THIS project's four agents. Requires CONFIRM=yes
	@echo "This removes only these four labels, by name — never by wildcard:"
	@for n in capture cycle snapshot heartbeat; do echo "    com.tradesense.$$n"; done
	@echo
	@echo "Anything else stays. Currently loaded and NOT touched by this target:"
	@other=$$(launchctl list 2>/dev/null | awk '{print $$3}' \
	  | grep -vE '^com\.tradesense\.(capture|cycle|snapshot|heartbeat)$$' \
	  | grep -iE 'trade|clerk|forge|stock'); \
	if [ -n "$$other" ]; then echo "$$other" | sed 's/^/    /'; \
	else echo "    (none loaded — nothing else to preserve)"; fi
	@echo
ifneq ($(CONFIRM),yes)
	@echo "  re-run as:  make cleanup CONFIRM=yes"
	@exit 1
else
	@for n in capture cycle snapshot heartbeat; do \
	  launchctl bootout gui/$$(id -u)/com.tradesense.$$n 2>/dev/null \
	    && echo "  removed com.tradesense.$$n" || echo "  com.tradesense.$$n was not loaded"; \
	  rm -f $$HOME/Library/LaunchAgents/com.tradesense.$$n.plist; \
	done
	@echo
	@echo "Done. Still loaded:"
	@left=$$(launchctl list 2>/dev/null | grep -iE 'trade|clerk|forge'); \
	if [ -n "$$left" ]; then echo "$$left" | sed 's/^/  /'; else echo "  (nothing)"; fi
	@echo
	@echo "NOTE: the wake schedule is left alone. If trade-sense agents rely on it, removing it"
	@echo "      would stop them too:  sudo pmset repeat cancel"
endif

logs:  ## tail the scheduled-job logs
	@tail -n 25 logs/*.log 2>/dev/null || echo "no logs yet — nothing has run"

## ---- housekeeping ----
#
# Deliberately absent, because a one-word target makes them too easy to reach by accident:
#   capture-force  wrote knowingly-stale quotes into an append-only dataset
#   unschedule     deleted the launchd agents and their plists
#   clean-lock     deleted the interlock that stops two cycles trading the same signal twice
# Each is still doable by hand when it is genuinely wanted; see docs or run the command directly.

lint:  ## report lint issues without changing anything
	@ruff check . && ruff format --check . && echo "  clean"

fmt:  ## fix what can be fixed automatically, then format
	@ruff check . --fix
	@ruff format .
	@echo "  run 'make check' to confirm nothing broke"

roll:  ## estimate effective spread from trade sequences, validate against the latest capture
	@$(PY) scripts/roll_spread.py

check:  ## import every module and assert no database driver leaked in
	@$(PY) -c "import sys;sys.path.insert(0,'.');import importlib;\
[importlib.import_module(m) for m in ['src.universe','src.risk','src.data.alpaca','src.data.files',\
'src.options.iv','src.options.signal','src.options.selection','src.options.execution',\
'src.options.live_iv','src.measurement.stats']];print('  all modules import')"
	@! grep -rqE '^[[:space:]]*(import|from)[[:space:]]+(psycopg|sqlalchemy|asyncpg|sqlite3)' src/ \
	  && echo "  no database driver in src/" || (echo "  DATABASE DRIVER FOUND"; exit 1)

