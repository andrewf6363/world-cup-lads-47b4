# World Cup Lads — 2026 Dashboard

An auto-updating leaderboard for our 8-person World Cup 2026 prediction pool ($25 each, winner takes all).
The live page is published via GitHub Pages — share the link; no login needed to view.

**Live URL:** https://andrewf6363.github.io/world-cup-lads-47b4/

## How it works

- **Group stage:** everyone fills the pink box under each match in `World Cup Selections.xlsx` with the
  winning country's name (or `tie`) and sends it back. 100 pts per correct result.
- **Knockout (from June 28):** a fresh bracket, scoring doubles each round — R32 100, R16 200, QF 400,
  SF 800, Final 1,600. (Separate sheet, added near June 28.)
- Tiebreaker for the pot: closest guess to the Final's total goals.

## Commissioner commands

Run these from this folder (`wc26-league/`).

```bash
# 1. Ingest a returned sheet (player name comes from the file name; --name to override)
python3 scripts/ingest_picks.py "/path/to/Brendan.xlsx"
python3 scripts/ingest_picks.py picks_inbox/*.xlsx        # or a whole folder at once

# 2. Publish: rebuild + commit + push (only if something changed)
bash scripts/update.sh
```

**Add a friend's picks:** drop their returned `.xlsx` anywhere, run command 1 on it (it auto-finds
the right sheet even if their file has extra tabs), then run command 2. They appear on the board in ~1 min.

- Ingest **prints a summary** and flags anything it can't read cleanly (e.g. a typo) so you can confirm —
  it never guesses. Re-ingesting the same person just updates their picks.
- **Override a result by hand:** edit `data/results_manual.json` — it always wins over the auto-feed.
- **Start over:** `python3 scripts/reset_data.py` clears all picks + results.

## Auto-updates

`bash scripts/update.sh` runs the whole loop: pull → fetch results → recompute → publish **only if
something changed** (no empty commits, safe to run repeatedly). Run it manually anytime, or let a
scheduled Claude Code **Routine** run it a few times a day during the tournament — that runs in the
cloud, so it updates the leaderboard even with your laptop closed.

## Calendar file

`build.py` also writes `wc26-group-stage.ics` (all 72 group matches, correct ET times) to the site
root. Friends tap **Add to Cal** on the dashboard (or the footer link) and import once — the fixtures
never change, so there's nothing to maintain.

## iMessage recap bot (runs on this Mac)

Apple allows no cloud path into iMessage, so the nightly recap posts from this machine via
Messages.app. The site's **Copy** button on the Daily card is the from-your-phone fallback.

```bash
# One-time: pick which chat gets the recaps (start with a chat to yourself, to test)
python3 scripts/setup_imessage.py

# Test / preview / post
python3 scripts/post_imessage.py --test      # sends a fixed hello message
python3 scripts/post_imessage.py --dry-run   # prints the real recap, sends nothing
python3 scripts/post_imessage.py             # posts if there's a new recap (dedupes)
```

- Posts only once per new recap (state in `~/.wc26-imessage-state`); nothing posts before June 11.
- First run asks permission for Terminal to control Messages — click **Allow**
  (System Settings → Privacy & Security → Automation if you missed the prompt).
- Scheduled nightly at **10:45 PM** by `~/Library/LaunchAgents/com.wc26.recap.plist`
  (`launchctl unload` that file to stop it; logs in `/tmp/wc26-recap.log`). If the Mac is asleep at
  10:45 it posts on next wake. If a scheduled post ever doesn't arrive, check for a one-time
  Automation permission prompt for the first scheduled (non-Terminal) run.
- When you're happy with the test, re-run `setup_imessage.py` and point it at the lads' group.
- **After the Final (July 19):** `launchctl unload ~/Library/LaunchAgents/com.wc26.recap.plist`
  and disable the GitHub Actions workflow.

## What's in here

| Path | What it is |
|---|---|
| `index.html` | The published dashboard (generated — don't hand-edit) |
| `data/teams.json` | 48 teams + groups + name aliases |
| `data/fixtures.json` | All fixtures with stable IDs (the backbone) |
| `data/picks.json` | Everyone's picks (built by `ingest_picks.py`) |
| `data/results.json` | Match results (built by `fetch_results.py`) |
| `data/results_manual.json` | Your manual result overrides (win over the feed) |
| `scripts/` | The engine: `lib.py` (scoring), `build.py` (render), `ingest_picks.py`, `fetch_results.py` |

Scoring is fully deterministic and recomputes from scratch every run, so a re-run or a corrected
result can never corrupt the standings — it just heals on the next pass.
