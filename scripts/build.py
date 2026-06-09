#!/usr/bin/env python3
"""Compute standings and render the dashboard (index.html) + standings.json.

Reads data/{fixtures,picks,results,teams}.json, recomputes everything from scratch
(deterministic / self-healing), and writes index.html using scripts/template.html.
Run:  python3 scripts/build.py
"""
import json, os, datetime
import lib

HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, "..", "data")
ROOT = os.path.join(HERE, "..")
LEAGUE_NAME = "World Cup Lads"
LEAGUE_SIZE = 8                 # players in the pool ($25 each -> $200)
HOSTS = "2026 · United States · Canada · México"
ROUND_LABEL = {"R32":"Round of 32","R16":"Round of 16","QF":"Quarterfinals","SF":"Semifinals","Final":"Final","3P":"Third place"}

def load(name, default):
    p = os.path.join(DATA, name)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else default

def et_now():
    et = datetime.datetime.utcnow() - datetime.timedelta(hours=4)   # EDT
    return f'{et.strftime("%b")} {et.day}, {et.strftime("%I:%M %p").lstrip("0")} ET'

def date_label(iso):
    if not iso: return ""
    try:
        d = datetime.datetime.fromisoformat(iso.replace("Z","+00:00"))
        return f'{d.strftime("%b")} {d.day}'
    except Exception:
        return ""

def phase(fixtures, results):
    m = results.get("matches", {})
    ko_final = any(m.get(k["id"],{}).get("status")=="final" for k in fixtures.get("knockout",[]))
    gp_final = any(m.get(f["id"],{}).get("status")=="final" for f in fixtures["group_stage"])
    if ko_final: return "Knockout Stage"
    if gp_final: return "Group Stage"
    return "Kicks Off June 11"

def results_feed(fixtures, results, limit=8):
    by_id = {f["id"]: f for f in fixtures["group_stage"] + fixtures.get("knockout", [])}
    m = results.get("matches", {})
    feed = []
    for mid, res in m.items():
        if res.get("status") != "final": continue
        fx = by_id.get(mid)
        if not fx: continue
        sa, sb = res.get("team1_goals"), res.get("team2_goals")
        if sa is None or sb is None: continue
        rnd = f'Group {fx["group"]}' if fx.get("phase")=="group" else ROUND_LABEL.get(fx.get("round"),"")
        feed.append({"a":fx["team1"],"b":fx["team2"],"sa":sa,"sb":sb,
                     "pen":res.get("pens"),"round":rnd,"date":date_label(fx.get("kickoff_utc")),
                     "_sort":fx.get("kickoff_utc") or ""})
    feed.sort(key=lambda r: r["_sort"], reverse=True)
    for r in feed: r.pop("_sort", None)
    return feed[:limit]

def bracket_view(fixtures, results):
    ko = fixtures.get("knockout", [])
    if not ko: return None
    m = results.get("matches", {})
    out = {}
    for kx in ko:
        if kx.get("round") == "3P": continue
        label = ROUND_LABEL.get(kx["round"], kx["round"])
        t1, t2 = kx.get("team1") or "TBD", kx.get("team2") or "TBD"
        res = m.get(kx["id"], {})
        w = None; s = [None, None]
        if res.get("status") == "final":
            s = [res.get("team1_goals"), res.get("team2_goals")]
            w = 0 if res.get("winner") == t1 else (1 if res.get("winner") == t2 else None)
        out.setdefault(label, []).append({"t":[t1,t2],"s":s,"w":w,"pen":bool(res.get("pens"))})
    return out

def main():
    fixtures = load("fixtures.json", {"group_stage": [], "knockout": []})
    picks = load("picks.json", {"players": []})
    results = load("results.json", {"matches": {}})
    prev_path = os.path.join(ROOT, "standings.json")
    prev = json.load(open(prev_path, encoding="utf-8")) if os.path.exists(prev_path) else {"leaderboard": []}
    prev_ranks = {r["name"]: r["rank"] for r in prev.get("leaderboard", [])}

    # final total goals (for the payout tiebreaker) once the Final is in
    fin = results.get("matches", {}).get("K-104", {})
    final_goals = (fin.get("team1_goals",0)+fin.get("team2_goals",0)) if fin.get("status")=="final" else None

    rows = lib.standings(picks["players"], fixtures, results.get("matches", {}), prev_ranks, final_goals)

    players = [{
        "name": r["name"], "total": r["total"], "grp": r["grp"], "ko": r["ko"],
        "correct": r["correct"], "graded": r["graded"], "rank": r["rank"], "move": r["move"], "champ": r["champ"],
        "rounds": {"R32":r["rounds"]["R32"],"R16":r["rounds"]["R16"],"QF":r["rounds"]["QF"],
                   "SF":r["rounds"]["SF"],"F":r["rounds"]["Final"]},
    } for r in rows]

    leader = None
    if rows:
        second = rows[1]["total"] if len(rows) > 1 else 0
        leader = {"name":rows[0]["name"],"total":rows[0]["total"],"correct":rows[0]["correct"],
                  "graded":rows[0]["graded"],"champ":rows[0]["champ"],"lead":rows[0]["total"]-second}

    n = len(players)
    data = {
        "meta": {"name": LEAGUE_NAME, "overline": "The Friends League", "hosts": HOSTS,
                 "phase": phase(fixtures, results), "updated": et_now(),
                 "managers": LEAGUE_SIZE, "pot": LEAGUE_SIZE*25, "submitted": n},
        "leader": leader, "players": players,
        "results": results_feed(fixtures, results), "bracket": bracket_view(fixtures, results),
        "championName": (results.get("matches",{}).get("K-104",{}) or {}).get("winner"),
    }

    tpl = open(os.path.join(HERE, "template.html"), encoding="utf-8").read()
    html = tpl.replace("__DATA__", json.dumps(data, ensure_ascii=False))
    open(os.path.join(ROOT, "index.html"), "w", encoding="utf-8").write(html)
    open(os.path.join(ROOT, "standings.json"), "w", encoding="utf-8").write(
        json.dumps({"generated_utc": datetime.datetime.utcnow().isoformat()+"Z",
                    "leaderboard": rows}, ensure_ascii=False, indent=2))

    top = ", ".join(f'{r["name"]} {r["total"]}' for r in rows[:3]) or "(no picks yet)"
    print(f"Built index.html · {n} managers · phase: {data['meta']['phase']} · top: {top}")

if __name__ == "__main__":
    main()
