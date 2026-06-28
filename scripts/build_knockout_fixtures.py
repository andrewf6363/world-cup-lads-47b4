#!/usr/bin/env python3
"""One-time: build the knockout bracket (K-73..K-104) into data/fixtures.json from the
openfootball feed — real R32 teams, the W-/L-reference tree (feeds), rounds, and kickoff times.
Later-round team1/team2 stay null; build.py propagates winners through the tree as matches finish.
Run once when the bracket is set:  python3 scripts/build_knockout_fixtures.py
"""
import json, os, re, datetime, urllib.request

HERE = os.path.dirname(__file__); DATA = os.path.join(HERE, "..", "data")
FEED = "https://raw.githubusercontent.com/openfootball/worldcup.json/master/2026/worldcup.json"

# openfootball spelling -> our canonical spelling (matches data/teams.json + RANK)
ALIASES = {"DR Congo": "Congo DR", "Bosnia & Herzegovina": "Bosnia-Herzegovina",
           "Cape Verde": "Cabo Verde", "Ivory Coast": "Côte d'Ivoire", "Iran": "IR Iran",
           "Turkey": "Türkiye", "Korea Republic": "South Korea", "United States": "USA",
           "Czech Republic": "Czechia", "Curaçao": "Curacao"}
ROUND = {"Round of 32": "R32", "Round of 16": "R16", "Quarter-final": "QF",
         "Semi-final": "SF", "Match for third place": "3P", "Final": "Final"}

def canon(n): return ALIASES.get(n, n)
def is_ref(s): return bool(re.fullmatch(r"[WL]\d+", str(s or "")))

def to_utc(date, time):
    # "12:00 UTC-7" -> ISO UTC
    m = re.match(r"(\d{1,2}):(\d{2})\s*UTC([+-]\d+)", time or "")
    if not m: return None
    h, mn, off = int(m.group(1)), int(m.group(2)), int(m.group(3))
    dt = datetime.datetime.fromisoformat(f"{date}T{h:02d}:{mn:02d}:00") - datetime.timedelta(hours=off)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

def main():
    feed = json.load(urllib.request.urlopen(urllib.request.Request(FEED, headers={"User-Agent": "M"}), timeout=25))
    ko = sorted([m for m in feed["matches"] if isinstance(m.get("num"), int) and m["num"] >= 73],
                key=lambda x: x["num"])
    out = []
    for m in ko:
        num = m["num"]; utc = to_utc(m.get("date", ""), m.get("time", ""))
        et = None
        if utc:
            et_dt = datetime.datetime.fromisoformat(utc.replace("Z", "+00:00")) - datetime.timedelta(hours=4)
            et = et_dt.strftime("%Y-%m-%dT%H:%M:%S-04:00")
        t1, t2 = m.get("team1"), m.get("team2")
        feeds = None
        if is_ref(t1) or is_ref(t2):
            feeds = [f"K-{int(re.sub('[A-Z]', '', t1))}", f"K-{int(re.sub('[A-Z]', '', t2))}"]
            team1 = team2 = None                         # resolved by build.py as the bracket plays
        else:
            team1, team2 = canon(t1), canon(t2)
        entry = {"id": f"K-{num}", "round": ROUND.get(m.get("round"), "?"), "phase": "knockout",
                 "team1": team1, "team2": team2, "kickoff_utc": utc, "kickoff_et": et}
        if feeds: entry["feeds"] = feeds
        if entry["round"] == "3P": entry["loser_feed"] = True   # fed by the SF LOSERS
        out.append(entry)

    fx = json.load(open(os.path.join(DATA, "fixtures.json"), encoding="utf-8"))
    fx["knockout"] = out
    json.dump(fx, open(os.path.join(DATA, "fixtures.json"), "w"), ensure_ascii=False, indent=2)
    rc = {}
    for e in out: rc[e["round"]] = rc.get(e["round"], 0) + 1
    print(f"wrote {len(out)} knockout fixtures: {rc}")
    print("R32 sample:", ", ".join(f'{e["team1"]} v {e["team2"]}' for e in out[:3]))

if __name__ == "__main__":
    main()
