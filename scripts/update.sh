#!/usr/bin/env bash
# World Cup Lads — one-shot auto-update.
# Fetches latest results, recomputes scores, and publishes ONLY if something changed.
# Run manually anytime (bash scripts/update.sh), or let the scheduled cloud Routine run it.
set -uo pipefail
cd "$(dirname "$0")/.."

git pull --quiet --ff-only origin main 2>/dev/null || true
python3 scripts/fetch_results.py

if git diff --quiet -- data/; then
  echo "No data changes — nothing to publish."
  exit 0
fi

python3 scripts/build.py
python3 scripts/make_cards.py || true     # regenerate shareable cards (skips if Pillow missing)
git add -A
git commit -q -m "auto-update: $(date -u +%Y-%m-%dT%H:%MZ)"
git push -q origin main
echo "Published update."
