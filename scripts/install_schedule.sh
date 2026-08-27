#!/usr/bin/env bash
# Install the three scheduled jobs as launchd agents.
#
# launchd rather than cron: it survives reboot and logout, which cron on macOS does not reliably do.
#
# The jobs are deliberately separate. The capture accrues a dataset that cannot be backfilled, so it
# must run even if the cycle is broken. The equity snapshot must run even if the cycle was skipped,
# or the P&L curve gets holes. Coupling them would make one failure take out all three.
#
# Times are LOCAL. This machine runs America/New_York, so local == ET. On a machine in another zone
# these fire at the wrong moment — check `date` before trusting them.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AGENTS="$HOME/Library/LaunchAgents"
mkdir -p "$AGENTS" "$ROOT/logs"

# The project venv, NOT `command -v python3`.
#
# On 2026-08-27 the plists pointed at the homebrew python3, which has no pydantic. Every job died
# on import: no capture at 15:50, no cycle at 16:05, no equity row at 16:45. That session's NBBO is
# gone permanently -- there is no historical options quote endpoint to backfill it from.
#
# The interpreter is now verified against a real project import BEFORE anything is installed. An
# installer that writes four plists naming an interpreter it never tested is the whole failure.
uv sync --frozen --quiet 2>/dev/null || uv sync --quiet
PY="$ROOT/.venv/bin/python"
if [ ! -x "$PY" ]; then
  echo "!! $PY is missing. Run 'uv sync' first."
  exit 1
fi
if ! "$PY" -c "import sys; sys.path.insert(0, '$ROOT'); import src.data.alpaca" 2>/dev/null; then
  echo "!! $PY cannot import src.data.alpaca. Refusing to schedule an interpreter that cannot run"
  echo "   the jobs. Reproduce with:"
  echo "   $PY -c \"import sys; sys.path.insert(0,'$ROOT'); import src.data.alpaca\""
  exit 1
fi
echo "  interpreter $PY -- verified it can import the project"

if [ ! -f "$ROOT/.env" ]; then
  echo "!! $ROOT/.env is missing. Scheduled jobs have no environment and will fail."
  echo "   Create it with ALPACA_KEY_ID=... and ALPACA_SECRET_KEY=..., then chmod 600."
  exit 1
fi
chmod 600 "$ROOT/.env"

emit () {  # name  hour  minute  script  [args...]
  local name=$1 hour=$2 min=$3 script=$4; shift 4
  local label="com.tradesense.$name"
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
  <key>StandardOutPath</key><string>$ROOT/logs/$name.out.log</string>
  <key>StandardErrorPath</key><string>$ROOT/logs/$name.err.log</string>
  <key>StartCalendarInterval</key><array>
    <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>$hour</integer><key>Minute</key><integer>$min</integer></dict>
    <dict><key>Weekday</key><integer>2</integer><key>Hour</key><integer>$hour</integer><key>Minute</key><integer>$min</integer></dict>
    <dict><key>Weekday</key><integer>3</integer><key>Hour</key><integer>$hour</integer><key>Minute</key><integer>$min</integer></dict>
    <dict><key>Weekday</key><integer>4</integer><key>Hour</key><integer>$hour</integer><key>Minute</key><integer>$min</integer></dict>
    <dict><key>Weekday</key><integer>5</integer><key>Hour</key><integer>$hour</integer><key>Minute</key><integer>$min</integer></dict>
  </array>
</dict></plist>
PLIST
  launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$AGENTS/$label.plist"
  echo "  installed $label at $(printf '%02d:%02d' "$((10#$hour))" "$((10#$min))") local, Mon-Fri"
}

# 15:50 — near the decision point, and inside RTH so the quotes mean something.
emit capture  15 50 capture_nbbo.py
# 16:05 — after the close, matching the existing pipeline's EOD trigger.
#
# Dry by default. LIVE=1 arms it; ACCOUNT= states which account it is meant to trade. The account
# is baked into the plist as an assertion rather than left implicit in .env, so swapping
# credentials without re-installing aborts loudly instead of trading the wrong book.
CYCLE_ARGS="--deadline 2026-09-04"
if [ "${LIVE:-0}" = "1" ]; then
  if [ -z "${ACCOUNT:-}" ]; then
    echo "!! LIVE=1 requires ACCOUNT=<account_number> — refusing to arm without naming the target."
    exit 1
  fi
  CYCLE_ARGS="$CYCLE_ARGS --live --expect-account $ACCOUNT"
  echo "  ARMING LIVE against account $ACCOUNT"
fi
emit cycle    16 05 run_cycle.py $CYCLE_ARGS
# 16:45 — independent of the cycle, so a failed cycle still leaves a P&L row.
emit snapshot 16 45 snapshot_equity.py
# 09:00 - goes looking for the silence. A laptop asleep at 15:50 produces no capture, no
# cycle and no equity row, and nothing says so, because nothing ran to say it.
emit heartbeat 09 00 heartbeat.py --notify

echo
echo "Installed. Verify with:  launchctl list | grep tradesense"
echo "Logs:                    $ROOT/logs/"
echo
if [ "${LIVE:-0}" = "1" ]; then
  echo "CYCLE IS ARMED against $ACCOUNT. It will place real orders at 16:05 on weekdays."
else
  echo "NOTE: the cycle runs in DRY RUN."
  echo "      To arm:  make schedule LIVE=1 ACCOUNT=PA382RL5C7X8   (rehearsal, test account)"
  echo "               make schedule LIVE=1 ACCOUNT=PA3BUA9MX72C   (judged window)"
fi
