#!/usr/bin/env bash
# Remove the condor agent's dated jobs. Leaves install_schedule.sh's jobs alone.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AGENTS="$HOME/Library/LaunchAgents"
for name in dryrun probe tranches tuesday; do
  label="com.tradesense.agent.$name"
  launchctl bootout "gui/$(id -u)/$label" 2>/dev/null && echo "  booted out $label" || true
  rm -f "$AGENTS/$label.plist" && echo "  removed  $AGENTS/$label.plist"
done
echo "Done. Verify: launchctl list | grep tradesense.agent"
