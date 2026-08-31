#!/usr/bin/env bash
# Install the condor agent's dated runs as launchd agents.
#
# Separate from install_schedule.sh deliberately. That one schedules the *shelved* path -- NBBO
# capture, the ranking cycle, the equity snapshot -- on a Mon-Fri repeat. These are one-shot jobs
# on named dates during the judged window, and coupling them would mean re-installing the capture
# every time an entry time moves.
#
# WHAT THIS DOES NOT SOLVE. launchd runs a missed job when the machine next wakes, so a laptop
# asleep at 10:00 fires the entry at whatever time it opens. Every job below therefore passes
# --at HH:MM and the script refuses outside a ten-minute window (src/agent/window.py). A closed
# laptop means no trade, not a late one. **Keep the machine awake and plugged in.**
#
# Times are LOCAL. This machine runs America/New_York, so local == ET. Check `date` elsewhere.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AGENTS="$HOME/Library/LaunchAgents"
mkdir -p "$AGENTS" "$ROOT/logs"

# The project venv, NOT `command -v python3`. On 2026-08-27 the plists named a python without
# pydantic, every job died on import, and that session's NBBO is gone permanently -- there is no
# historical options quote endpoint to backfill it from. So the interpreter is proved against a
# real project import BEFORE anything is installed.
uv sync --frozen --quiet 2>/dev/null || uv sync --quiet
PY="$ROOT/.venv/bin/python"
if [ ! -x "$PY" ]; then
  echo "!! $PY is missing. Run 'uv sync' first."
  exit 1
fi
if ! "$PY" -c "import sys; sys.path.insert(0,'$ROOT'); import src.options.condor, src.agent.window" 2>/dev/null; then
  echo "!! $PY cannot import the condor path. Refusing to schedule an interpreter that cannot run"
  echo "   the jobs. Reproduce with:"
  echo "   $PY -c \"import sys; sys.path.insert(0,'$ROOT'); import src.options.condor\""
  exit 1
fi
echo "  interpreter $PY -- verified it can import the condor path"

# The model reviewer shells out to the `claude` CLI, and a launchd job's PATH is roughly
# /usr/bin:/bin -- so a bare `claude` is not found. That fails in the worst way: the call raises,
# review() fails closed, every tranche is refused, and the log says only that the model declined.
# The absolute path is therefore baked into each plist and proved here first.
CLAUDE_BIN="${CLAUDE_BIN:-$(command -v claude || true)}"
if [ -z "$CLAUDE_BIN" ] || [ ! -x "$CLAUDE_BIN" ]; then
  echo "!! claude CLI not found. The model reviewer cannot run, and every tranche would be"
  echo "   refused with no indication why. Install it, or pass CLAUDE_BIN=/path/to/claude."
  exit 1
fi
if ! "$CLAUDE_BIN" --version >/dev/null 2>&1; then
  echo "!! $CLAUDE_BIN is not runnable (--version failed)."
  exit 1
fi
echo "  reviewer    $CLAUDE_BIN -- verified runnable"

if [ ! -f "$ROOT/.env" ]; then
  echo "!! $ROOT/.env is missing. Scheduled jobs get almost no environment and will fail."
  exit 1
fi
chmod 600 "$ROOT/.env"

if [ "${LIVE:-0}" = "1" ]; then
  if [ -z "${ACCOUNT:-}" ]; then
    echo "!! LIVE=1 requires ACCOUNT=<account_number> -- refusing to arm without naming the book."
    exit 1
  fi
  # Prove the credentials resolve to the named account before arming, not at 10:00.
  ACTUAL=$("$PY" - <<PYEOF
import sys; sys.path.insert(0, "$ROOT")
from src.data.alpaca import AlpacaClient
try:
    print(AlpacaClient().account().account_number)
except Exception as e:
    print(f"ERROR {e}")
PYEOF
)
  if [ "$ACTUAL" != "$ACCOUNT" ]; then
    echo "!! .env resolves to '$ACTUAL', but ACCOUNT=$ACCOUNT."
    echo "   Trading the wrong book is the only error here that produces no signal at all."
    exit 1
  fi
  echo "  credentials verified -> $ACTUAL"
fi

emit () {  # name  month  day  hour  minute  script  [args...]
  # Read every positional BEFORE shifting -- shifting first makes $2..$5 the *arguments*, which
  # is how this produced "10#09:35: syntax error" on its first run.
  #
  # 10# forces decimal. Bash reads a leading-zero literal as octal, so "09" is an invalid number
  # and "08" is too -- the same trap install_schedule.sh already guards.
  local name=$1 month=$((10#$2)) day=$((10#$3)) hour=$((10#$4)) min=$((10#$5)) script=$6
  shift 6
  local label="com.tradesense.agent.$name"
  local args=""
  for a in "$@"; do args="$args        <string>$a</string>"$'\n'; done
  cat > "$AGENTS/$label.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$label</string>
  <key>ProgramArguments</key><array>
        <string>$PY</string>
        <string>$ROOT/scripts/$script</string>
$args  </array>
  <key>WorkingDirectory</key><string>$ROOT</string>
  <key>EnvironmentVariables</key><dict>
    <key>CLAUDE_BIN</key><string>$CLAUDE_BIN</string>
    <key>PATH</key><string>$(dirname "$CLAUDE_BIN"):/usr/bin:/bin:/usr/sbin:/sbin</string>
  </dict>
  <key>StandardOutPath</key><string>$ROOT/logs/agent-$name.out.log</string>
  <key>StandardErrorPath</key><string>$ROOT/logs/agent-$name.err.log</string>
  <key>StartCalendarInterval</key><dict>
    <key>Month</key><integer>$month</integer>
    <key>Day</key><integer>$day</integer>
    <key>Hour</key><integer>$hour</integer>
    <key>Minute</key><integer>$min</integer>
  </dict>
</dict></plist>
PLIST
  launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$AGENTS/$label.plist"
  printf "  installed %-30s %02d-%02d %02d:%02d local\n" "$label" "$month" "$day" "$hour" "$min"
}

ARM=""
if [ "${LIVE:-0}" = "1" ]; then ARM="--live --expect-account $ACCOUNT"; fi

# 09:35 Mon -- the eyeball. Always dry, never armed: its job is to show the strikes against live
# spot before anything is placed, and an armed rehearsal is not a rehearsal.
emit dryrun 8 31 09 35 run_agent.py --at 09:35 --session 2026-08-31

# 09:45 Mon -- the registered probe. One condor, one contract, cancelled at 20s.
# docs/pending/condor-fill-realism.md. Its verdict gates the 10:00 entry.
emit probe 8 31 09 45 fill_probe.py --at 09:45 --session 2026-08-31 $ARM

# 10:00 Mon -- both committed tranches. Refuses unless the probe wrote a verdict it accepts.
emit tranches 8 31 10 00 run_agent.py --at 10:00 --session 2026-08-31 $ARM

# 09:35 Tue -- the conditional third tranche. Both registered gate conditions are evaluated inside
# the loop; a refusal here is the correct outcome and is recorded as one, not as a shortfall.
emit tuesday 9 1 09 35 run_agent.py --at 09:35 --session 2026-09-01 $ARM

echo
echo "Installed. Verify:  launchctl list | grep tradesense.agent"
echo "Logs:               $ROOT/logs/agent-*.log"
echo "Remove:             scripts/uninstall_agent_schedule.sh"
echo
if [ "${LIVE:-0}" = "1" ]; then
  cat <<NOTE
ARMED against $ACCOUNT. Real orders at 09:45 (one probe contract) and 10:00 (both tranches).

  Still true, and worth reading once before you sleep:
  - A closed laptop means NO trade. The window guard refuses a late wake rather than
    entering hours after the fact. Keep it awake and plugged in.
  - No order has ever filled on this system (issue #18). 09:45 is the first.
  - Pin-risk checks on Wed/Thu 15:15 are NOT scheduled -- no script exists for them yet
    (issue #13). Those remain manual.
NOTE
else
  echo "DRY RUN ONLY. Nothing here will place an order."
  echo "  To arm:  make agent-schedule LIVE=1 ACCOUNT=PA3BUA9MX72C"
fi
