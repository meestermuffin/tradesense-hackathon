#!/usr/bin/env bash
# Commit the private record.
#
# .claude/private/ is gitignored by this repo and is its own git repository, which is what gives
# PLAN.md a history. Run this after editing it.
#
# An earlier version also published a SHA-256 of PLAN.md into the public repo, on the theory that it
# made private decisions verifiable. It was dropped: a commitment is only worth something if the
# committed document is eventually revealed, and PLAN.md is not published. It also went stale within
# hours of being written, and a digest that no longer matches is worse than none.
#
# The verifiability that matters is already public. Measurement registrations live in this repo's
# history and their ordering is checkable:
#     git merge-base --is-ancestor <registration> <results>
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PRIV="$ROOT/.claude/private"
MSG="${1:-Update the private record}"
git -C "$PRIV" add -A
git -C "$PRIV" diff --cached --quiet && { echo "private record unchanged"; exit 0; }
git -C "$PRIV" -c user.name="Jamie Min" -c user.email="jamin131@gmail.com" commit -q -m "$MSG"
echo "private record committed: $(git -C "$PRIV" rev-parse --short HEAD)"
