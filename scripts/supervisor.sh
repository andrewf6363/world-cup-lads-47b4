#!/bin/bash
# Self-perpetuating supervisor. Runs ~5.5h: every iteration it fetches results and
# publishes if anything changed, polling fast (~90s) while a match is live and slow
# (~4 min) when idle. Before it exits it re-launches its own successor via a PAT, so a
# live process is ALWAYS running — independent of GitHub's (unreliable) cron scheduler.
# Cron remains only as a cold-start in case the chain ever fully dies.
cd "$(dirname "$0")/.."

END=$(( $(date +%s) + 19800 ))           # ~5.5h, safely under the 6h runner cap

publish_if_changed() {
  git pull -q origin main 2>/dev/null || true
  python3 scripts/fetch_results.py >/dev/null 2>&1 || true
  if ! git diff --quiet -- data/; then
    python3 scripts/build.py >/dev/null
    python3 scripts/make_cards.py >/dev/null 2>&1 || true
    git add -A
    git commit -qm "live: $(date -u +%H:%MZ)" || true
    if ! git push -q origin main 2>/dev/null; then
      git pull -q --rebase origin main 2>/dev/null || true
      git push -q origin main 2>/dev/null || true
    fi
    echo "supervisor: published $(date -u +%H:%M:%S)Z"
  fi
}

while [ "$(date +%s)" -lt "$END" ]; do
  if python3 scripts/in_live_window.py; then SLEEP=90; else SLEEP=240; fi
  sleep "$SLEEP"
  publish_if_changed
done

# hand off to a fresh run so coverage never lapses (PAT required — GITHUB_TOKEN can't re-trigger workflows)
if [ -n "$CHAIN_PAT" ]; then
  GH_TOKEN="$CHAIN_PAT" gh workflow run "Update dashboard" 2>/dev/null \
    && echo "supervisor: relaunched successor" \
    || echo "supervisor: relaunch FAILED (check CHAIN_PAT) — cron will cold-start"
else
  echo "supervisor: no CHAIN_PAT secret — relying on cron cold-start (set CHAIN_PAT for a self-sustaining chain)"
fi
