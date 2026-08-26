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
PY="$(command -v python3)"
mkdir -p "$AGENTS" "$ROOT/logs"

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
  echo "  installed $label at $(printf '%02d:%02d' "$hour" "$min") local, Mon-Fri"
}

# 15:50 — near the decision point, and inside RTH so the quotes mean something.
emit capture  15 50 capture_nbbo.py
# 16:05 — after the close, matching the existing pipeline's EOD trigger. Dry run until --live is
# added here deliberately; a scheduler must not be able to trade by accident.
emit cycle    16 05 run_cycle.py --deadline 2026-09-04
# 16:45 — independent of the cycle, so a failed cycle still leaves a P&L row.
emit snapshot 16 45 snapshot_equity.py
# 09:00 - goes looking for the silence. A laptop asleep at 15:50 produces no capture, no
# cycle and no equity row, and nothing says so, because nothing ran to say it.
emit heartbeat 09 00 heartbeat.py --notify

echo
echo "Installed. Verify with:  launchctl list | grep tradesense"
echo "Logs:                    $ROOT/logs/"
echo
echo "NOTE: the cycle runs in DRY RUN. To trade, add --live to com.tradesense.cycle.plist"
echo "      and reload it. That is deliberately a manual edit."
