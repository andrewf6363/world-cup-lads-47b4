#!/bin/bash
# Live-score loop: while a match is in its live window, fetch -> rebuild -> publish
# every ~100s, then exit. This makes live coverage survive GitHub's flaky scheduler:
# any ONE run that lands near kickoff covers the whole match window by itself.
# Capped at ~4.5h so the job never hits the 6h runner limit.
cd "$(dirname "$0")/.."

for i in $(seq 1 160); do
  if ! python3 scripts/in_live_window.py; then
    echo "live loop: no match in window — exiting after $((i-1)) iteration(s)"
    exit 0
  fi
  sleep 100
  git pull -q origin main 2>/dev/null || true
  python3 scripts/fetch_results.py > /dev/null 2>&1 || true
  if ! git diff --quiet -- data/; then
    python3 scripts/build.py > /dev/null
    python3 scripts/make_cards.py > /dev/null 2>&1 || true
    git add -A
    git commit -qm "live: $(date -u +%H:%M)Z" || true
    if ! git push -q origin main 2>/dev/null; then
      git pull -q --rebase origin main 2>/dev/null || true
      git push -q origin main 2>/dev/null || true
    fi
    echo "live loop: published $(date -u +%H:%M:%S)Z"
  fi
done
echo "live loop: hit iteration cap — exiting (a queued run takes over)"
