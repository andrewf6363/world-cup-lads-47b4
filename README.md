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

# 2. Rebuild the dashboard from current picks + results
python3 scripts/build.py

# 3. Publish (or let the scheduled Routine do this automatically)
git add -A && git commit -m "update" && git push
```

- Ingest **prints a summary** and flags anything it can't read cleanly (e.g. a typo) so you can confirm —
  it never guesses. Re-ingesting the same person just updates their picks.
- **Override a result by hand:** edit `data/results_manual.json` — it always wins over the auto-feed.
- **Start over:** `python3 scripts/reset_data.py` clears all picks + results.

## Auto-updates

A scheduled Claude Code **Routine** runs a few times a day during the tournament: pull the latest
results → recompute every score → rebuild → commit & push. Runs in the cloud, so it works with your
laptop closed. (Set up separately; see the project notes.)

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
