#!/usr/bin/env python3
"""Compute standings and render the dashboard (index.html) + standings.json.

Reads data/{fixtures,picks,results,teams}.json, recomputes everything from scratch
(deterministic / self-healing), and writes index.html using scripts/template.html.
Run:  python3 scripts/build.py
"""
import json, os, datetime, math, random
import lib

HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, "..", "data")
ROOT = os.path.join(HERE, "..")
LEAGUE_NAME = "World Cup Lads"
LEAGUE_SIZE = 8                 # players in the pool ($25 each -> $200)
HOSTS = "2026 · United States · Canada · México"
ROUND_LABEL = {"R32":"Round of 32","R16":"Round of 16","QF":"Quarterfinals","SF":"Semifinals","Final":"Final","3P":"Third place"}
# FIFA ranks (June 2026) — used as a tiebreaker for predicted tables and the win-probability model
RANK = {
 "Argentina":1,"Spain":2,"France":3,"England":4,"Portugal":5,"Brazil":6,"Morocco":7,"Netherlands":8,
 "Belgium":9,"Germany":10,"Croatia":11,"Colombia":13,"Mexico":14,"Senegal":15,"Uruguay":16,"USA":17,
 "Japan":18,"Switzerland":19,"IR Iran":20,"Türkiye":22,"Ecuador":23,"Austria":24,"South Korea":25,
 "Australia":27,"Algeria":28,"Egypt":29,"Canada":30,"Norway":31,"Côte d'Ivoire":33,"Panama":34,
 "Czechia":39,"Paraguay":40,"Scotland":42,"Congo DR":45,"Tunisia":46,"Uzbekistan":48,"Iraq":56,
 "Qatar":58,"Saudi Arabia":59,"South Africa":60,"Jordan":63,"Bosnia-Herzegovina":64,"Cabo Verde":67,
 "Ghana":73,"Curacao":82,"Haiti":83,"New Zealand":85,
}
def rank(t): return RANK.get(t, 90)

def match_probs(t1, t2):
    """P(team1 win), P(draw), P(team2 win) from FIFA-rank difference. Tuned for realistic
    international variance (lots of draws, frequent upsets) so win% isn't overconfident."""
    diff = rank(t2) - rank(t1)                                   # >0 => team1 stronger
    pdraw = max(0.16, min(0.32, 0.30 * math.exp(-abs(diff) / 55.0)))
    p1_dec = 1 / (1 + 10 ** (-diff / 34.0))                      # team1 share of a decisive result
    return (1 - pdraw) * p1_dec, pdraw, (1 - pdraw) * (1 - p1_dec)

def win_probabilities(rows, group_stage, M, pmap, nsim=10000):
    """Monte Carlo: simulate unplayed matches vs each manager's picks; % of sims they finish 1st."""
    random.seed(20260611)                                        # deterministic for a given input
    unplayed = [(f["id"], match_probs(f["team1"], f["team2"]))
                for f in group_stage if M.get(f["id"], {}).get("status") != "final"]
    names = [r["name"] for r in rows]
    if not names: return {}
    picks_by = {n: pmap.get(n, {}).get("group_picks", {}) for n in names}
    base = {r["name"]: r["total"] for r in rows}                 # points already locked
    wins = {n: 0.0 for n in names}
    for _ in range(nsim):
        tot = dict(base)
        for fid, (p1, pd, p2) in unplayed:
            r = random.random()
            o = "team1" if r < p1 else ("draw" if r < p1 + pd else "team2")
            for n in names:
                if picks_by[n].get(fid) == o: tot[n] += 100
        mx = max(tot.values()); lead = [n for n in names if tot[n] == mx]
        for n in lead: wins[n] += 1.0 / len(lead)
    return {n: round(wins[n] / nsim * 100) for n in names}

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

    M = results.get("matches", {})
    rows = lib.standings(picks["players"], fixtures, M, prev_ranks, final_goals)

    # per-player group-pick breakdown (for the expandable "what did they pick" view)
    group_fx = {}
    for f in fixtures["group_stage"]:
        group_fx.setdefault(f["group"], []).append(f)
    pmap = {p["name"]: p for p in picks["players"]}
    # how the league split on each match (over submitted players who picked it)
    dist = {}
    for f in fixtures["group_stage"]:
        c = {"team1": 0, "draw": 0, "team2": 0}
        for p in picks["players"]:
            o = p.get("group_picks", {}).get(f["id"])
            if o in c: c[o] += 1
        dist[f["id"]] = c
    def pick_breakdown(name):
        gp = pmap.get(name, {}).get("group_picks", {})
        out = []
        for letter, fxs in group_fx.items():
            ms = []
            for f in fxs:
                pk = gp.get(f["id"]); res = M.get(f["id"], {})
                status = "pending"
                if res.get("status") == "final" and pk:
                    status = "correct" if pk == res.get("outcome") else "wrong"
                c = dist[f["id"]]; tot = c["team1"] + c["draw"] + c["team2"]; mx = max(c.values()) if tot else 0
                contra = bool(pk) and tot > 1 and c.get(pk, 0) < mx       # not with the plurality
                solo = bool(pk) and tot > 1 and c.get(pk, 0) == 1         # only one who picked it
                ms.append({"t1": f["team1"], "t2": f["team2"], "pick": pk, "status": status,
                           "contra": contra, "solo": solo})
            out.append({"group": letter, "matches": ms})
        return out

    players = [{
        "name": r["name"], "total": r["total"], "grp": r["grp"], "ko": r["ko"],
        "correct": r["correct"], "graded": r["graded"], "rank": r["rank"], "move": r["move"], "champ": r["champ"],
        "rounds": {"R32":r["rounds"]["R32"],"R16":r["rounds"]["R16"],"QF":r["rounds"]["QF"],
                   "SF":r["rounds"]["SF"],"F":r["rounds"]["Final"]},
        "picks": pick_breakdown(r["name"]),
    } for r in rows]

    for pl in players:
        ms = [m for g in pl["picks"] for m in g["matches"]]
        pl["contra"] = sum(1 for m in ms if m["contra"])
        pl["solo"] = sum(1 for m in ms if m["solo"])

    roster = load("roster.json", [r["name"] for r in rows])
    pending = [{"name": nm} for nm in roster if nm.lower() not in {r["name"].lower() for r in rows}]

    # ---- Group-table predictor: a table per group from consensus picks (or live/actual results) ----
    def consensus_outcome(f):
        res = M.get(f["id"])
        if res and res.get("status") == "final": return res.get("outcome")
        c = dist[f["id"]]
        if not (c["team1"] + c["draw"] + c["team2"]):
            return "team1" if rank(f["team1"]) <= rank(f["team2"]) else "team2"
        pref = {"team1": (c["team1"], -rank(f["team1"])), "team2": (c["team2"], -rank(f["team2"])),
                "draw": (c["draw"], -1000)}
        return max(pref, key=lambda o: pref[o])

    def build_table(src):
        tables = []
        for letter, fxs in group_fx.items():
            tm = {}
            for f in fxs:
                for t in (f["team1"], f["team2"]): tm.setdefault(t, {"team": t, "pts": 0, "w": 0, "d": 0, "l": 0})
            nfinal = 0
            for f in fxs:
                if M.get(f["id"], {}).get("status") == "final": nfinal += 1
                o = src(f); t1, t2 = f["team1"], f["team2"]
                if o == "team1": tm[t1]["pts"] += 3; tm[t1]["w"] += 1; tm[t2]["l"] += 1
                elif o == "team2": tm[t2]["pts"] += 3; tm[t2]["w"] += 1; tm[t1]["l"] += 1
                else: tm[t1]["pts"] += 1; tm[t2]["pts"] += 1; tm[t1]["d"] += 1; tm[t2]["d"] += 1
            rows_ = sorted(tm.values(), key=lambda r: (-r["pts"], rank(r["team"])))
            status = "final" if nfinal == 6 else ("live" if nfinal else "predicted")
            tables.append({"group": letter, "status": status,
                           "rows": [{**r, "through": i < 2} for i, r in enumerate(rows_)]})
        return tables

    group_tables = build_table(consensus_outcome)
    for pl in players:                       # each manager's predicted qualifiers (their own picks)
        gp = pmap.get(pl["name"], {}).get("group_picks", {})
        def psrc(f, gp=gp):
            o = gp.get(f["id"])
            return o if o else ("team1" if rank(f["team1"]) <= rank(f["team2"]) else "team2")
        pl["qualifiers"] = {t["group"]: [r["team"] for r in t["rows"][:2]] for t in build_table(psrc)}

    # league splits: matches the group didn't see the same way (most-divided first)
    splits = []
    for f in fixtures["group_stage"]:
        c = dist[f["id"]]; tot = c["team1"] + c["draw"] + c["team2"]
        if tot >= 2 and sum(1 for k in c if c[k] > 0) >= 2:
            splits.append({"t1": f["team1"], "t2": f["team2"], "group": f["group"], "c": c, "total": tot})
    splits.sort(key=lambda s: (max(s["c"].values()) / s["total"], -s["total"]))
    splits = splits[:12]

    wp = win_probabilities(rows, fixtures["group_stage"], M, pmap)
    for pl in players:
        pl["winpct"] = wp.get(pl["name"], 0)

    # ---- The Daily (auto-written recap) ----
    finals = [(f, M[f["id"]]) for f in fixtures["group_stage"] if M.get(f["id"], {}).get("status") == "final"]
    if not finals:
        daily = {"headline": "Kicks off June 11",
                 "line": f"{len(players)} of {len(roster)} managers locked in — the first results and daily recaps land here once the tournament starts.",
                 "items": []}
    else:
        finals.sort(key=lambda x: (x[0].get("kickoff_utc") or ""), reverse=True)
        items = []
        up = max(players, key=lambda p: p["move"]); dn = min(players, key=lambda p: p["move"])
        if up["move"] > 0: items.append(f"Biggest riser — {up['name']}, up {up['move']} spot{'s' if up['move'] > 1 else ''}")
        if dn["move"] < 0: items.append(f"Biggest faller — {dn['name']}, down {abs(dn['move'])}")
        f0, r0 = min(finals[:8], key=lambda x: dist[x[0]["id"]].get(x[1].get("outcome"), 99))
        n0 = dist[f0["id"]].get(r0.get("outcome"), 0)
        items.append(f"Least-expected result — {f0['team1']} {r0.get('team1_goals','')}–{r0.get('team2_goals','')} {f0['team2']} ({n0}/{len(players)} called it)")
        daily = {"headline": f"Latest · {date_label(finals[0][0].get('kickoff_utc'))}",
                 "line": f"{len(finals)} match{'es' if len(finals) != 1 else ''} played · {players[0]['name']} leads on {players[0]['total']} pts",
                 "items": items[:3]}

    # ---- The Race (standings history snapshot for the chart) ----
    hist = load("history.json", [])
    today = et_now().split(",")[0]
    cur = {p["name"]: p["total"] for p in players}
    new_hist = list(hist)
    if new_hist and new_hist[-1].get("t") == today:
        new_hist[-1] = {"t": today, "totals": cur}
    elif (not new_hist) or new_hist[-1].get("totals") != cur:
        new_hist.append({"t": today, "totals": cur})
    new_hist = new_hist[-60:]
    if new_hist != hist:
        json.dump(new_hist, open(os.path.join(DATA, "history.json"), "w"), ensure_ascii=False, indent=2)
    race = {"labels": [h["t"] for h in new_hist],
            "series": [{"name": p["name"], "points": [h["totals"].get(p["name"]) for h in new_hist]} for p in players]}

    # ---- Badges ----
    def chalk(f): return "team1" if rank(f["team1"]) <= rank(f["team2"]) else "team2"
    for pl in players:
        gp = pmap.get(pl["name"], {}).get("group_picks", {})
        picked = [o for o in gp.values() if o]
        nchalk = sum(1 for f in fixtures["group_stage"] if gp.get(f["id"]) == chalk(f))
        ndraw = sum(1 for o in picked if o == "draw")
        b = []
        if picked:
            if nchalk / max(1, len(picked)) >= 0.8: b.append("Mr. Chalk")
            if pl["contra"] >= 12: b.append("Maverick")          # genuine minority picks (needs 3+ managers)
            if ndraw >= 10: b.append("Draw Merchant")
        if pl["rank"] == 1 and pl["total"] > 0: b.append("Front-runner")
        pl["badges"] = b

    # ---- Today / Next (live countdown strip) ----
    upcoming = []
    for f in sorted(fixtures["group_stage"], key=lambda x: (x.get("kickoff_utc") or "")):
        if M.get(f["id"], {}).get("status") == "final": continue
        upcoming.append({"t1": f["team1"], "t2": f["team2"], "kickoff": f.get("kickoff_utc"),
                         "label": f"Group {f['group']}"})
        if len(upcoming) >= 8: break

    # ---- Champion watch (predicted cup winners + still-alive) ----
    elim = set()
    for kx in fixtures.get("knockout", []):
        res = M.get(kx["id"], {})
        if res.get("status") == "final" and res.get("winner"):
            for t in (kx.get("team1"), kx.get("team2")):
                if t and t != res["winner"]: elim.add(t)
    champions = [{"name": pl["name"],
                  "champ": (pmap.get(pl["name"], {}).get("knockout_picks", {}) or {}).get("K-104")} for pl in players]
    for c in champions:
        c["alive"] = (c["champ"] not in elim) if c["champ"] else None

    leader = None
    if rows:
        second = rows[1]["total"] if len(rows) > 1 else 0
        leader = {"name":rows[0]["name"],"total":rows[0]["total"],"correct":rows[0]["correct"],
                  "graded":rows[0]["graded"],"champ":rows[0]["champ"],"lead":rows[0]["total"]-second}

    data = {
        "meta": {"name": LEAGUE_NAME, "overline": "The Friends League", "hosts": HOSTS,
                 "phase": phase(fixtures, results), "updated": et_now(),
                 "managers": len(roster), "pot": len(roster)*25, "submitted": len(players),
                 "started": bool(finals)},
        "leader": leader, "players": players, "pending": pending, "groups": group_tables, "splits": splits,
        "daily": daily, "race": race, "upcoming": upcoming, "knockoutStart": "2026-06-28T16:00:00Z",
        "champions": champions,
        "results": results_feed(fixtures, results), "bracket": bracket_view(fixtures, results),
        "championName": (M.get("K-104",{}) or {}).get("winner"),
    }

    tpl = open(os.path.join(HERE, "template.html"), encoding="utf-8").read()
    html = tpl.replace("__DATA__", json.dumps(data, ensure_ascii=False))
    open(os.path.join(ROOT, "index.html"), "w", encoding="utf-8").write(html)
    open(os.path.join(ROOT, "standings.json"), "w", encoding="utf-8").write(
        json.dumps({"generated_utc": datetime.datetime.utcnow().isoformat()+"Z",
                    "leaderboard": rows}, ensure_ascii=False, indent=2))

    top = ", ".join(f'{r["name"]} {r["total"]}' for r in rows[:3]) or "(no picks yet)"
    print(f"Built index.html · {len(players)}/{len(roster)} managers in · phase: {data['meta']['phase']} · top: {top}")

if __name__ == "__main__":
    main()
