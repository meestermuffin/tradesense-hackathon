#!/usr/bin/env bash
# Commit the private record and publish a digest of PLAN.md.
#
# Run after editing .claude/private/PLAN.md. Content history lives in the nested private repo
# (recovery); the digest lands in the public repo (verifiability). Neither replaces the other.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PRIV="$ROOT/.claude/private"
MSG="${1:-Update the private record}"
git -C "$PRIV" add -A
git -C "$PRIV" diff --cached --quiet && { echo "private record unchanged"; exit 0; }
git -C "$PRIV" -c user.name="Jamie Min" -c user.email="jamin131@gmail.com" commit -q -m "$MSG"
SHA=$(shasum -a 256 "$PRIV/PLAN.md" | cut -d' ' -f1)
COMMIT=$(git -C "$PRIV" rev-parse HEAD)
DATE=$(TZ=America/New_York date '+%Y-%m-%d %H:%M')
printf '| %s | `%s` | `%s` | %s |\n' "$DATE" "$SHA" "${COMMIT:0:12}" "$MSG" \
  >> "$ROOT/docs/private-record-hashes.md"
echo "private commit ${COMMIT:0:12}"
echo "PLAN.md sha256 $SHA"
echo "appended to docs/private-record-hashes.md — commit the public repo to publish it"
