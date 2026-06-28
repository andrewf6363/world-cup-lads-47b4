#!/usr/bin/env python3
"""Compute standings and render the dashboard (index.html) + standings.json.

Reads data/{fixtures,picks,results,teams}.json, recomputes everything from scratch
(deterministic / self-healing), and writes index.html using scripts/template.html.
Run:  python3 scripts/build.py
"""
import json, os, datetime, math, random, re, hashlib
from collections import Counter
from itertools import product
import lib

HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, "..", "data")
ROOT = os.path.join(HERE, "..")
LEAGUE_NAME = "World Cup Lads"
LEAGUE_SIZE = 8                 # players in the pool ($25 each -> $200)
HOSTS = "2026 · United States · Canada · México"
BASE_URL = "https://andrewf6363.github.io/world-cup-lads-47b4"
ROUND_LABEL = {"R32":"Round of 32","R16":"Round of 16","QF":"Quarterfinals","SF":"Semifinals","Final":"Final","3P":"Third place"}
# FIFA ranks (June 2026) — used as a tiebreaker for predicted tables and the win-probability model
RANK = {
 "Argentina":1,"Spain":2,"France":3,"England":4,"Portugal":5,"Brazil":6,"Morocco":7,"Netherlands":8,
 "Belgium":9,"Germany":10,"Croatia":11,"Colombia":13,"Mexico":14,"Senegal":15,"Uruguay":16,"USA":17,
 "Japan":18,"Switzerland":19,"IR Iran":20,"Türkiye":22,"Ecuador":23,"Austria":24,"South Korea":25,
 "Australia":27,"Algeria":28,"Egypt":29,"Canada":30,"Norway":31,"Côte d'Ivoire":33,"Panama":34,
 "Czechia":39,"Paraguay":40,"Scotland":42,"Sweden":43,"Congo DR":45,"Tunisia":46,"Uzbekistan":48,"Iraq":56,
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

def win_probabilities(rows, fixtures, M, pmap, nsim=10000):
    """Monte Carlo: simulate every UNPLAYED match — group outcomes AND the knockout bracket
    (advancing sim-winners through the tree) — versus each manager's picks, awarding doubling
    knockout points, and tally how often each finishes 1st. Deterministic for a given input."""
    random.seed(20260611)
    names = [r["name"] for r in rows]
    if not names: return {}
    group_unplayed = [(f["id"], match_probs(f["team1"], f["team2"]))
                      for f in fixtures["group_stage"] if M.get(f["id"], {}).get("status") != "final"]
    ko = [k for k in fixtures.get("knockout", []) if k.get("round") != "3P"]
    resolved = lib.resolve_bracket(fixtures, M)                  # R32 teams known; later via sim
    gpicks = {n: pmap.get(n, {}).get("group_picks", {}) for n in names}
    kpicks = {n: pmap.get(n, {}).get("knockout_picks", {}) for n in names}
    base = {r["name"]: r["total"] for r in rows}
    wins = {n: 0.0 for n in names}
    for _ in range(nsim):
        tot = dict(base)
        for fid, (p1, pd, p2) in group_unplayed:
            r = random.random()
            o = "team1" if r < p1 else ("draw" if r < p1 + pd else "team2")
            for n in names:
                if gpicks[n].get(fid) == o: tot[n] += 100
        simwin = {}
        for k in ko:                                            # num order -> feeders resolve first
            res = M.get(k["id"], {})
            if res.get("status") == "final":
                w = res.get("winner")
            else:
                if k.get("round") == "R32": a, b = k.get("team1"), k.get("team2")
                else: a, b = simwin.get(k["feeds"][0]), simwin.get(k["feeds"][1])
                if not a or not b: continue                     # bracket not resolved this far yet
                p1, pd, p2 = match_probs(a, b)
                w = a if random.random() < p1 + pd / 2 else b   # split the draw mass (KO has no draws)
            simwin[k["id"]] = w
            rp = lib.ROUND_POINTS.get(k["round"], 0)
            for n in names:
                if kpicks[n].get(k["id"]) == w: tot[n] += rp
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

def _ics_esc(s):
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")

def _ics_fold(line):
    """RFC 5545 folding: physical lines ≤75 octets, continuations start with one space,
    and breaks only land on UTF-8 character boundaries (Google Calendar import is strict)."""
    b = line.encode("utf-8"); out = []; first = True
    while True:
        cap = 74 if first else 73                      # leave room for the continuation space
        if len(b) <= cap:
            out.append(("" if first else " ") + b.decode("utf-8")); return out
        i = cap
        while (b[i] & 0xC0) == 0x80: i -= 1            # back off to a character boundary
        out.append(("" if first else " ") + b[:i].decode("utf-8"))
        b = b[i:]; first = False

def write_ics(fixtures):
    """All 72 group matches as a one-time-import calendar file at the site root.
    DTSTAMP is a constant so the file is byte-identical every build (no commit churn)."""
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//World Cup Lads//WC26 Group Stage//EN",
             "CALSCALE:GREGORIAN", "METHOD:PUBLISH", "X-WR-CALNAME:World Cup Lads — 2026 Group Stage"]
    n = 0
    for f in sorted(fixtures["group_stage"], key=lambda x: (x.get("kickoff_utc") or "", x["id"])):
        iso = f.get("kickoff_utc")
        if not iso: continue
        dt = datetime.datetime.fromisoformat(iso.replace("Z", "+00:00"))
        lines += ["BEGIN:VEVENT",
                  f"UID:wc26-{f['id']}@world-cup-lads",
                  "DTSTAMP:20260609T000000Z",
                  f"DTSTART:{dt.strftime('%Y%m%dT%H%M%SZ')}",
                  f"DTEND:{(dt + datetime.timedelta(hours=2)).strftime('%Y%m%dT%H%M%SZ')}",
                  "SUMMARY:" + _ics_esc(f"{f['team1']} vs {f['team2']} — Group {f['group']} (World Cup Lads)"),
                  "DESCRIPTION:" + _ics_esc(f"World Cup Lads live table: {BASE_URL}"),
                  "END:VEVENT"]
        n += 1
    lines.append("END:VCALENDAR")
    out = "\r\n".join(l for line in lines for l in _ics_fold(line)) + "\r\n"
    open(os.path.join(ROOT, "wc26-group-stage.ics"), "w", encoding="utf-8", newline="").write(out)
    return n

def qual_top2(fixtures, M):
    """Brute-force top-2 qualification status per team over every remaining group-match outcome.
    Points only (no goal data), so ties break AGAINST a team for clinching and FOR it when checking
    elimination — 'through'/'third' are only claimed when mathematically certain either way.
    Returns (status{team: through|alive|third}, notes{fixture_id: [scenario strings]})."""
    status, notes = {}, {}
    groups = {}
    for f in fixtures["group_stage"]:
        groups.setdefault(f["group"], []).append(f)
    for g, fxs in groups.items():
        teams = sorted({t for f in fxs for t in (f["team1"], f["team2"])})
        base = {t: 0 for t in teams}
        rem = []
        for f in fxs:
            res = M.get(f["id"], {})
            if res.get("status") == "final":
                o = res.get("outcome")
                if o == "team1": base[f["team1"]] += 3
                elif o == "team2": base[f["team2"]] += 3
                else: base[f["team1"]] += 1; base[f["team2"]] += 1
            else:
                rem.append(f)
        combos = list(product(("team1", "draw", "team2"), repeat=len(rem)))
        def table(combo):
            pts = dict(base)
            for f, o in zip(rem, combo):
                if o == "team1": pts[f["team1"]] += 3
                elif o == "team2": pts[f["team2"]] += 3
                else: pts[f["team1"]] += 1; pts[f["team2"]] += 1
            return pts
        all_pess = {t: True for t in teams}; any_opt = {t: False for t in teams}
        per = [(combo, table(combo)) for combo in combos]
        for t in teams:
            for combo, pts in per:
                others = [pts[o] for o in teams if o != t]
                if sum(1 for v in others if v >= pts[t]) > 1: all_pess[t] = False
                if sum(1 for v in others if v > pts[t]) <= 1: any_opt[t] = True
        for t in teams:
            status[t] = "through" if all_pess[t] else ("third" if not any_opt[t] else "alive")
        # per-match scenarios for teams still alive ("clinch with a win" etc.)
        for idx, f in enumerate(rem):
            for side, t in (("team1", f["team1"]), ("team2", f["team2"])):
                if status[t] != "alive": continue
                win_p, draw_p, lose_o = True, True, False
                for combo, pts in per:
                    others = [pts[o] for o in teams if o != t]
                    ge = sum(1 for v in others if v >= pts[t]); gt = sum(1 for v in others if v > pts[t])
                    oc = combo[idx]
                    if oc == side and ge > 1: win_p = False
                    if oc == "draw" and ge > 1: draw_p = False
                    if oc not in (side, "draw") and gt <= 1: lose_o = True
                if win_p and draw_p: msg = f"{t} are through top-two with a draw or better"
                elif win_p: msg = f"{t} clinch a top-two spot with a win"
                elif not lose_o: msg = f"a loss ends {t}'s top-two hopes"
                else: continue
                notes.setdefault(f["id"], []).append(msg)
    return status, notes

def golden_boot(fixtures, M, limit=8):
    by_id = {f["id"]: f for f in fixtures["group_stage"] + fixtures.get("knockout", [])}
    c = {}
    for mid, res in M.items():
        fx = by_id.get(mid)
        if not fx or res.get("status") != "final": continue
        for e in res.get("events", []):
            if e.get("kind") in ("goal", "pen") and e.get("player"):
                team = fx.get(e.get("team"), "") if e.get("team") in ("team1", "team2") else ""
                c[(e["player"], team)] = c.get((e["player"], team), 0) + 1
    rows = sorted(c.items(), key=lambda kv: (-kv[1], kv[0][0]))
    return [{"p": p, "team": t, "g": n} for (p, t), n in rows[:limit]]

def recap_prose(f, res, stats):
    """4–5 sentence deterministic recap: the result shape, the scoring story with running score,
    the stats picture, and discipline. Degrades gracefully when events/stats are missing
    (e.g. commissioner-entered results)."""
    t1, t2 = f["team1"], f["team2"]; a, b = res["team1_goals"], res["team2_goals"]
    name = {"team1": t1, "team2": t2}
    ev = res.get("events", [])
    goals = [e for e in ev if e["kind"] in ("goal", "pen", "og")]
    reds = [e for e in ev if e["kind"] == "red"]
    def mval(m):
        nums = re.findall(r"\d+", m or ""); return sum(int(x) for x in nums) if nums else 0
    def var(opts):
        return opts[int(hashlib.md5(f["id"].encode()).hexdigest(), 16) % len(opts)]
    sents = []
    win = lose = None; late = False
    if a != b:
        win, lose = (t1, t2) if a > b else (t2, t1)
        ws, ls = max(a, b), min(a, b)
        wside = "team1" if a > b else "team2"
        wgoals = [g for g in goals if g["team"] == wside and g["kind"] != "og"]
        late = bool(wgoals) and mval(wgoals[-1]["min"]) >= 75 and ws - ls == 1

    # 1) the result shape
    if a == b == 0:
        sents.append(var([f"{t1} and {t2} cancelled each other out — a goalless draw and a point apiece.",
                          f"No way through: {t1} and {t2} ground out a 0–0 that never caught fire."]))
    elif a == b:
        sents.append(f"{t1} and {t2} shared the points at {a}–{b}.")
    elif rank(win) > rank(lose) + 15:
        sents.append(f"{win} stunned {lose} {ws}–{ls} — a result almost nobody had on their sheet.")
    elif ws - ls >= 3:
        sents.append(var([f"{win} put on a show, running out {ws}–{ls} winners over {lose}.",
                          f"A statement from {win} — {lose} swept aside {ws}–{ls}."]))
    elif ws - ls == 2:
        sents.append(f"{win} controlled it, a comfortable {ws}–{ls} over {lose}.")
    elif late:
        g = wgoals[-1]
        sents.append(f"{win} snatched it {ws}–{ls}, {g['player'] or 'the winner'} striking in the {g['min']} — heartbreak for {lose}.")
    else:
        sents.append(f"{win} edged a tight one, {ws}–{ls} over {lose}.")

    # 2) the scoring story, with the running score
    if goals:
        sa = sb = 0; moments = []
        for g in goals:
            sa, sb = (sa + 1, sb) if g["team"] == "team1" else (sa, sb + 1)
            moments.append((g, f"{sa}–{sb}"))
        if late: moments = moments[:-1]                            # the shape line already told it
        if a == b and a > 0 and mval(goals[-1]["min"]) >= 75:
            g = goals[-1]
            art = "an" if (g["min"] or "").lstrip().startswith(("8", "11", "18")) else "a"
            sents.append(f"{g['player'] or name[g['team']]} rescued it for {name[g['team']]} with {art} {g['min']} equalizer.")
            moments = moments[:-1]
        story = []
        for i, (g, sc) in enumerate(moments[:3]):
            who = g["player"] or name[g["team"]]
            tag = " (pen)" if g["kind"] == "pen" else " (og)" if g["kind"] == "og" else ""
            story.append(f"{who}{tag} opened the scoring in the {g['min']}" if i == 0 and sc in ("1–0", "0–1")
                         else f"{who}{tag} made it {sc} in the {g['min']}")
        if len(moments) > 3: story.append("the goals kept coming from there")
        if story:
            s = "; ".join(story)
            sents.append(s[0].upper() + s[1:] + ".")
        braces = Counter(g["player"] for g in goals if g["player"]).most_common(1)
        if braces and braces[0][1] >= 2:
            sents.append(f"{'A hat-trick' if braces[0][1] >= 3 else 'A brace'} for {braces[0][0]}.")
        if mval(goals[0]["min"]) > 45:
            sents.append("The first half finished goalless.")

    # 3) the stats picture
    srow = {s[0]: (s[1], s[2]) for s in (stats or [])}
    pos, sh, sot = srow.get("Possession"), srow.get("Shots"), srow.get("On target")
    if pos and sh:
        try:
            p1 = float(pos[0].rstrip("%")); s1i, s2i = int(sh[0]), int(sh[1])
            wi = 0 if (win == t1 or (win is None and p1 >= 50)) else 1
            pw = pos[wi].rstrip("%"); shw, shl = (s1i, s2i) if wi == 0 else (s2i, s1i)
            side_w = t1 if wi == 0 else t2; side_l = t2 if wi == 0 else t1
            sotw = sot[wi] if sot else None
            if win and shw >= shl:
                sents.append(f"{side_w} backed it up with {pw}% of the ball and a {shw}–{shl} edge in shots"
                             + (f" ({sotw} on target)" if sotw else "") + ".")
            elif win:
                sents.append(f"The numbers leaned the other way — {side_l} out-shot them {shl}–{shw} — but {win} took the chances that mattered.")
            else:
                sents.append(f"{side_w} had the better of it ({pw}% possession, {shw} shots to {shl}) without finding a winner.")
        except (ValueError, IndexError):
            pass

    # 4) discipline
    if reds:
        by_side = {}
        for r in reds: by_side.setdefault(r["team"], []).append(r)
        bits = []
        for side, rs in by_side.items():
            men = {1: "ten men", 2: "nine men", 3: "eight men"}.get(len(rs), "short-handed")
            names_ = ", ".join(f"{x['player']} ({x['min']})" for x in rs if x["player"]) or f"{len(rs)} sent off"
            bits.append(f"{name[side]} finished with {men} — {names_}")
        sents.append(("It boiled over: " if len(reds) >= 2 else "") + "; ".join(bits) + ".")

    def side_goals(side):
        gs = [g for g in goals if g["team"] == side]
        return ", ".join(f"{g['player'] or '—'} {g['min']}"
                         + (" (og)" if g["kind"] == "og" else " (pen)" if g["kind"] == "pen" else "") for g in gs)
    sg1, sg2 = side_goals("team1"), side_goals("team2")
    scorers = " &nbsp;·&nbsp; ".join(p for p in
              ((f"<b>{t1}:</b> {sg1}" if sg1 else ""), (f"<b>{t2}:</b> {sg2}" if sg2 else "")) if p)
    return " ".join(sents), scorers

def build_briefing(fixtures, M, players, pmap, dist, minfo, qnotes):
    """Match Center: recaps of finals from the last ~26h + a watch guide for the next 24h.
    Prose is generated deterministically from score shape, scorer/red-card events, FIFA-rank
    upsets, and the league's pick splits — same inputs always render the same text."""
    now = datetime.datetime.now(datetime.timezone.utc)
    allfx = fixtures["group_stage"] + fixtures.get("knockout", [])

    def kdt(f):
        iso = f.get("kickoff_utc")
        return datetime.datetime.fromisoformat(iso.replace("Z", "+00:00")) if iso else None
    def first(n): return n.split()[0]
    def mval(m):
        nums = re.findall(r"\d+", m or ""); return sum(int(x) for x in nums) if nums else 0
    def et(dt):
        l = dt - datetime.timedelta(hours=4)
        return f'{l.strftime("%a")} {l.strftime("%I:%M %p").lstrip("0")} ET'
    def label(f):
        return f'Group {f["group"]}' if f.get("group") else ROUND_LABEL.get(f.get("round"), "")
    def pick_var(fid, opts):                                   # stable variety, never random
        return opts[int(hashlib.md5(fid.encode()).hexdigest(), 16) % len(opts)]
    def gp(name): return pmap.get(name, {}).get("group_picks", {}) or {}
    def kp(name): return pmap.get(name, {}).get("knockout_picks", {}) or {}
    RP = {"R32": 100, "R16": 200, "QF": 400, "SF": 800, "Final": 1600, "3P": 0}
    ko_round = {k["id"]: k.get("round") for k in fixtures.get("knockout", [])}

    def fantasy_line(f, res):
        if not players: return ""
        fid = f["id"]
        if fid.startswith("G-"):
            target, pick, pool, unit = res.get("outcome"), lambda nm: gp(nm).get(fid), players, 100
        else:
            target, pick = res.get("winner"), lambda nm: kp(nm).get(fid)
            pool, unit = [p for p in players if pmap.get(p["name"], {}).get("submitted_knockout")], RP.get(ko_round.get(fid), 0)
        n = len(pool)
        if not n or target is None: return ""
        right = [first(p["name"]) for p in pool if pick(p["name"]) == target]
        wrong = [first(p["name"]) for p in pool if first(p["name"]) not in right]
        plus = f"+{unit:,}"
        if len(right) == n: return f"All {n} called it ({plus} each)."
        if not right: return "Nobody called it — the whole league blanked."
        if len(right) == 1: return f"{right[0]} alone called it — {plus} solo."
        if len(right) >= n - 2: return f"{len(right)} of {n} banked it — only {' and '.join(wrong)} missed."
        return f"Only {', '.join(right[:-1])} and {right[-1]} called it ({plus} each)."

    recaps, window = [], []
    for f in sorted(allfx, key=lambda x: x.get("kickoff_utc") or "", reverse=True):
        res = M.get(f["id"], {})
        ko = kdt(f)
        if res.get("status") != "final" or not ko or (now - ko) > datetime.timedelta(hours=26):
            continue
        window.append((f["id"], res.get("outcome")))
        text, scorers = recap_prose(f, res, minfo.get(f["id"], {}).get("stats", []))
        recaps.append({"a": f["team1"], "b": f["team2"], "sa": res["team1_goals"], "sb": res["team2_goals"],
                       "label": label(f), "when": date_label(f.get("kickoff_utc")), "pen": res.get("pens"),
                       "text": text, "scorers": scorers, "fantasy": fantasy_line(f, res),
                       "stats": minfo.get(f["id"], {}).get("stats", [])})

    # who won the day — fantasy points banked on the recap window (group + knockout), bucketed
    day = ""
    if window and players:
        def day_pts(p):
            t = 0
            for fid, _ in window:
                res = M.get(fid, {})
                if fid.startswith("G-"):
                    if gp(p["name"]).get(fid) == res.get("outcome"): t += 100
                elif pmap.get(p["name"], {}).get("submitted_knockout") and kp(p["name"]).get(fid) == res.get("winner"):
                    t += RP.get(ko_round.get(fid), 0)
            return t
        pts = {p["name"]: day_pts(p) for p in players}
        buckets = {}
        for n, v in pts.items(): buckets.setdefault(v, []).append(first(n))
        if len(buckets) == 1:
            v = next(iter(buckets))
            day = f"All {len(players)} lads +{v}" if v else "Nobody scored in the last 24h"
        else:
            day = " · ".join((f"+{v} " if v else "0 ") + ", ".join(sorted(buckets[v]))
                             for v in sorted(buckets, reverse=True))

    previews = []
    for f in sorted(allfx, key=lambda x: x.get("kickoff_utc") or ""):
        ko = kdt(f)
        if M.get(f["id"], {}).get("status") == "final" or not ko: continue
        ls = minfo.get(f["id"], {}).get("live")
        live = bool(ls) or (ko <= now < ko + datetime.timedelta(hours=2, minutes=15))
        if not live and not (now < ko <= now + datetime.timedelta(hours=24)): continue
        c = dist.get(f["id"], {"team1": 0, "draw": 0, "team2": 0})
        # who's on what — names grouped by pick (Kyle's group-chat request); knockout = who's advancing the team
        pick_rows = []
        if f["id"].startswith("G-"):
            lbl = {"team1": f["team1"], "draw": "Draw", "team2": f["team2"]}
            for k in ("team1", "draw", "team2"):
                if not c.get(k): continue
                who = [first(p["name"]) for p in players if gp(p["name"]).get(f["id"]) == k]
                if who:
                    pick_rows.append({"o": lbl[k],
                                      "n": f"all {len(players)}" if len(who) == len(players) else ", ".join(who)})
        else:
            subs = [p for p in players if pmap.get(p["name"], {}).get("submitted_knockout")]
            for team in (f.get("team1"), f.get("team2")):
                if not team: continue
                who = [first(p["name"]) for p in subs if kp(p["name"]).get(f["id"]) == team]
                if who:
                    pick_rows.append({"o": team,
                                      "n": f"all {len(subs)}" if (len(who) == len(subs) == len(players)) else ", ".join(who)})
        od = minfo.get(f["id"], {}).get("odds") or {}
        ml = od.get("ml", {})
        oline = ""
        if ml:
            fav = od.get("fav")
            def fmt(side, nm):
                if not ml.get(side): return None
                s = f"{nm} {ml[side]}"
                return f"<b>{s}</b>" if side == fav else s
            parts = [p for p in (fmt("team1", f["team1"]),
                                 f"Draw {ml['draw']}" if ml.get("draw") else None,
                                 fmt("team2", f["team2"])) if p]
            oline = " · ".join(parts)
            if od.get("ou") is not None: oline += f" · O/U {od['ou']}"

        # swing: what each outcome does to the top of the table (once points exist)
        sw = []
        if f["id"].startswith("G-") and players and any(p["total"] > 0 for p in players):
            base = {p["name"]: p["total"] for p in players}
            top0 = max(base.values()); lead0 = sorted(n for n, v in base.items() if v == top0)
            for o, lab in (("team1", f["team1"]), ("draw", "Draw"), ("team2", f["team2"])):
                gain = [p["name"] for p in players if gp(p["name"]).get(f["id"]) == o]
                new = {n: base[n] + (100 if n in gain else 0) for n in base}
                top1 = max(new.values()); lead1 = sorted(n for n, v in new.items() if v == top1)
                if lead1 == lead0: head = "top unchanged"
                elif len(lead1) == 1:
                    head = f"{first(lead1[0])} {'clear on top' if lead1[0] in lead0 else 'takes top spot'}"
                else:
                    head = ", ".join(first(x) for x in lead1[:2]) + (f" +{len(lead1)-2}" if len(lead1) > 2 else "") + " tied on top"
                gtxt = ", ".join(first(x) for x in gain) if gain else "nobody"
                sw.append(f"<b>{lab}</b> · +100 {gtxt} — {head}")

        previews.append({"t1": f["team1"], "t2": f["team2"], "label": label(f), "et": et(ko),
                         "picks": pick_rows, "live": live,
                         "tv": " · ".join(minfo.get(f["id"], {}).get("tv", [])), "odds": oline,
                         "ls": ls, "swing": sw, "qual": "; ".join(qnotes.get(f["id"], [])[:2]),
                         "id": f["id"]})

    race_line = ""
    if players and any(p["total"] > 0 for p in players):
        lead = players[0]
        tied_top = sum(1 for p in players if p["rank"] == 1)
        if tied_top == len(players):
            race_line = f"All {tied_top} level on {lead['total']:,}"
        elif tied_top > 1:
            race_line = f"{tied_top} tied at the top on {lead['total']:,}"
        else:
            race_line = f"{first(lead['name'])} leads on {lead['total']:,}"
            gap = lead["total"] - players[1]["total"] if len(players) > 1 else 0
            if gap > 0: race_line += f" · {first(players[1]['name'])} {gap:,} back"
        if len({p["total"] for p in players}) > 1:
            mv = max(players, key=lambda p: p["move"])
            if mv["move"] > 0: race_line += f" · {first(mv['name'])} up {mv['move']}"
    return {"recaps": recaps[:6], "previews": previews[:6], "race": race_line, "day": day}

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
    # fill knockout matchups as the bracket plays (R32 known up front; later rounds resolve from results)
    for k, (t1, t2) in lib.resolve_bracket(fixtures, M).items():
        kx = next((x for x in fixtures["knockout"] if x["id"] == k), None)
        if kx: kx["team1"], kx["team2"] = t1, t2
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

    wp = win_probabilities(rows, fixtures, M, pmap)
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
        # singular callouts only mean something once the table has actually separated
        separated = len({p["total"] for p in players}) > 1
        tied_top = sum(1 for p in players if p["rank"] == 1)
        items = []
        if separated:
            up = max(players, key=lambda p: p["move"]); dn = min(players, key=lambda p: p["move"])
            if up["move"] > 0: items.append(f"Biggest riser — {up['name']}, up {up['move']} spot{'s' if up['move'] > 1 else ''}")
            if dn["move"] < 0: items.append(f"Biggest faller — {dn['name']}, down {abs(dn['move'])}")
        f0, r0 = min(finals[:8], key=lambda x: dist[x[0]["id"]].get(x[1].get("outcome"), 99))
        n0 = dist[f0["id"]].get(r0.get("outcome"), 0)
        if n0 < len(players):                          # a unanimous result surprised nobody
            items.append(f"Least-expected result — {f0['team1']} {r0.get('team1_goals','')}–{r0.get('team2_goals','')} {f0['team2']} ({n0}/{len(players)} called it)")
        if tied_top == 1:
            lead_txt = f"{players[0]['name']} leads on {players[0]['total']} pts"
        elif tied_top == len(players):
            lead_txt = f"all {tied_top} level on {players[0]['total']} pts"
        else:
            lead_txt = f"{tied_top} tied at the top on {players[0]['total']} pts"
        daily = {"headline": f"Latest · {date_label(finals[0][0].get('kickoff_utc'))}",
                 "line": f"{len(finals)} match{'es' if len(finals) != 1 else ''} played · {lead_txt}",
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
        if pl["rank"] == 1 and pl["total"] > 0 and sum(1 for q in players if q["rank"] == 1) == 1:
            b.append("Front-runner")                   # only a SOLE leader is a front-runner
        pl["badges"] = b

    # ---- Streaks + wooden spoon ----
    graded_order = sorted((f for f in fixtures["group_stage"] if M.get(f["id"], {}).get("status") == "final"),
                          key=lambda f: (f.get("kickoff_utc") or "", f["id"]))
    for pl in players:
        gpicks = pmap.get(pl["name"], {}).get("group_picks", {}) or {}
        s = 0
        for f in reversed(graded_order):
            if gpicks.get(f["id"]) == M[f["id"]].get("outcome"): s += 1
            else: break
        pl["streak"] = s
        pl["spoon"] = False
    if finals and players and any(p["total"] > 0 for p in players):
        worst = max(p["rank"] for p in players)
        if worst > 1:                                  # nobody gets the spoon while everyone's tied
            for pl in players: pl["spoon"] = (pl["rank"] == worst)

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
                  "graded":rows[0]["graded"],"champ":rows[0]["champ"],"lead":rows[0]["total"]-second,
                  "tied":sum(1 for r in rows if r["rank"] == 1)}

    minfo = load("matchinfo.json", {})
    qual, qnotes = qual_top2(fixtures, M)
    briefing = build_briefing(fixtures, M, players, pmap, dist, minfo, qnotes)

    # tag group-table rows with qualification status (only meaningful once it's mathematically set)
    for gt in group_tables:
        for r in gt["rows"]:
            r["qual"] = qual.get(r["team"], "alive")

    # ---- The Book: market record, who's beating the closing favorite, lads-vs-Vegas splits ----
    def first_name(n): return n.split()[0]
    fav_record = {"w": 0, "l": 0}
    beat = Counter()
    nfin = ndraw = 0
    for f in fixtures["group_stage"]:
        res = M.get(f["id"], {})
        if res.get("status") != "final": continue
        nfin += 1
        if res.get("outcome") == "draw": ndraw += 1
        fav = (minfo.get(f["id"], {}).get("odds") or {}).get("fav")
        if not fav: continue
        fav_record["w" if res["outcome"] == fav else "l"] += 1
        for p in picks["players"]:
            pk = p.get("group_picks", {}).get(f["id"])
            if pk and pk != fav and pk == res["outcome"]: beat[first_name(p["name"])] += 1
    dis = []
    for pv in briefing["previews"]:
        od = minfo.get(pv["id"], {}).get("odds") or {}
        fav, ml = od.get("fav"), od.get("ml", {})
        c = dist.get(pv["id"])
        if not fav or not c: continue
        mx = max(c.values())
        tops = [k for k, v in c.items() if v == mx]
        if len(tops) != 1 or tops[0] == fav: continue
        lbl = {"team1": pv["t1"], "team2": pv["t2"], "draw": "the draw"}
        dis.append(f"{pv['t1']} v {pv['t2']} — lads lean {lbl[tops[0]]} ({mx} of {len(players)}); "
                   f"Vegas likes {lbl[fav]} {ml.get(fav, '')}")
    book = {
        "record": (f"Favorites {fav_record['w']}–{fav_record['l']} against the lads' board · "
                   f"draws {ndraw}/{nfin}") if (fav_record["w"] + fav_record["l"]) else
                  ("No graded matches with a closing line yet — the market record starts with tonight's games."),
        "beat": (" · ".join(f"{n} {v}" for n, v in beat.most_common(3)) if beat else ""),
        "dis": dis[:3],
    }
    boot = golden_boot(fixtures, M)

    data = {
        "briefing": briefing, "boot": boot, "book": book,
        "meta": {"name": LEAGUE_NAME, "overline": "The Friends League", "hosts": HOSTS,
                 "phase": phase(fixtures, results), "updated": et_now(),
                 "managers": len(roster), "pot": len(roster)*25, "submitted": len(players),
                 "started": bool(finals), "graded": len(finals),
                 "ko_pending": sum(1 for p in picks["players"] if not p.get("submitted_knockout"))},
        "leader": leader, "players": players, "pending": pending, "groups": group_tables, "splits": splits,
        "daily": daily, "race": race, "upcoming": upcoming, "knockoutStart": "2026-06-28T16:00:00Z",
        "champions": champions,
        "results": results_feed(fixtures, results), "bracket": bracket_view(fixtures, results),
        "championName": (M.get("K-104",{}) or {}).get("winner"),
    }

    nev = write_ics(fixtures)

    # social link preview (baked at build time; og.png is rendered by make_cards.py)
    if data["meta"]["started"] and leader and leader.get("tied", 1) > 1:
        og_desc = f"{leader['tied']} tied at the top on {leader['total']:,} pts — {data['meta']['phase']}"
    elif data["meta"]["started"] and leader:
        og_desc = f"{leader['name']} leads on {leader['total']:,} pts — {data['meta']['phase']}"
    else:
        og_desc = f"{len(players)} of {len(roster)} sheets in · ${len(roster)*25} pot · kicks off June 11"
    og_desc = og_desc.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")
    og_v = datetime.datetime.utcnow().strftime("%Y%m%d%H%M")

    tpl = open(os.path.join(HERE, "template.html"), encoding="utf-8").read()
    html = (tpl.replace("__DATA__", json.dumps(data, ensure_ascii=False))
               .replace("__OG_DESC__", og_desc).replace("__OG_V__", og_v))
    open(os.path.join(ROOT, "index.html"), "w", encoding="utf-8").write(html)
    open(os.path.join(ROOT, "standings.json"), "w", encoding="utf-8").write(
        json.dumps({"generated_utc": datetime.datetime.utcnow().isoformat()+"Z",
                    "leaderboard": rows}, ensure_ascii=False, indent=2))

    top = ", ".join(f'{r["name"]} {r["total"]}' for r in rows[:3]) or "(no picks yet)"
    print(f"Built index.html · {len(players)}/{len(roster)} managers in · phase: {data['meta']['phase']} · top: {top} · {nev} calendar events")

if __name__ == "__main__":
    main()
