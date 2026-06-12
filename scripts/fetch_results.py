#!/usr/bin/env python3
"""Pull match results, normalize to our fixture IDs, and write data/results.json.

Sources, layered (later wins): existing results.json (never lose a known final) -> openfootball feed
(backup, but lags hours) -> ESPN live scoreboard (PRIMARY — near-real-time, updates within minutes of
full time, no API key) -> data/results_manual.json (commissioner overrides, always win).

Never overwrites good data when sources fail. Run:  python3 scripts/fetch_results.py
"""
import json, os, sys, re, datetime, urllib.request, unicodedata

HERE = os.path.dirname(__file__); DATA = os.path.join(HERE, "..", "data")
FEED_URLS = [
    "https://raw.githubusercontent.com/openfootball/worldcup.json/master/2026/worldcup.json",
    "https://raw.githubusercontent.com/openfootball/worldcup.json/main/2026/worldcup.json",
]
# ESPN's public scoreboard (no key). One range query returns the whole tournament; finals are
# flagged status.state=="post"/completed. Team names match ours via the same ALIASES + norm().
ESPN_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard?dates=20260611-20260719"
# feed spelling -> our template spelling (true-name differences; accents/punct handled by norm())
ALIASES = {
    "Czech Republic":"Czechia", "Cape Verde":"Cabo Verde", "DR Congo":"Congo DR",
    "Ivory Coast":"Côte d'Ivoire", "Iran":"IR Iran", "Turkey":"Türkiye",
    "Korea Republic":"South Korea", "United States":"USA",
    "Bosnia & Herzegovina":"Bosnia-Herzegovina", "Curaçao":"Curacao",
}
KO_ROUNDS = {"round of 32","round of 16","quarter-finals","quarterfinals","quarter finals",
             "semi-finals","semifinals","semi finals","final","match for third place",
             "third place","play-off for third place"}

def norm(s):
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return "".join(c for c in s.lower() if c.isalnum())
def canon(name): return ALIASES.get(name, name)
def is_placeholder(n):
    n = str(n or "")
    return (not n) or n[0].isdigit() or "/" in n or bool(re.match(r"^[WL]\d", n))

def load(name, default):
    p = os.path.join(DATA, name)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else default

def fetch():
    for u in FEED_URLS:
        try:
            with urllib.request.urlopen(u, timeout=25) as r:
                return json.load(r), u
        except Exception as e:
            print(f"  feed miss {u}: {str(e)[:80]}")
    return None, None

def winner_of(t1, t2, score):
    """Knockout: team name that advanced, from penalties -> extra time -> full time."""
    for key in ("p", "et", "ft"):
        if score.get(key):
            a, b = score[key]
            if a != b:
                return t1 if a > b else t2
    return None

def normalize_feed(feed, fixtures):
    """Map every played feed match to our fixture IDs. Returns (matches, mapped_group, unmatched, finals)."""
    group_by_pair = {frozenset((norm(f["team1"]), norm(f["team2"]))): f for f in fixtures["group_stage"]}
    ko_by_num = {}
    for kx in fixtures.get("knockout", []):
        try: ko_by_num[int(kx["id"].split("-")[1])] = kx
        except Exception: pass

    matches, mapped, unmatched, finals = {}, 0, [], 0
    for m in feed.get("matches", []):
        t1f, t2f = m.get("team1"), m.get("team2")
        num = m.get("num")
        rnd = (m.get("round") or "").lower()
        score = m.get("score") or {}
        is_ko = (isinstance(num, int) and num >= 73) or rnd in KO_ROUNDS or is_placeholder(t1f) or is_placeholder(t2f)

        if not is_ko:  # group match
            fx = group_by_pair.get(frozenset((norm(canon(t1f)), norm(canon(t2f)))))
            if not fx:
                unmatched.append(f"{t1f} v {t2f}"); continue
            mapped += 1
            if not score.get("ft"): continue
            a, b = score["ft"]
            if norm(canon(t1f)) != norm(fx["team1"]): a, b = b, a   # orient to OUR team1/team2
            outcome = "team1" if a > b else "team2" if b > a else "draw"
            matches[fx["id"]] = {"status":"final","outcome":outcome,"team1_goals":a,"team2_goals":b}
            finals += 1
        else:  # knockout
            kx = ko_by_num.get(num)
            if not kx or not score.get("ft"): continue
            a, b = score["ft"]; p = score.get("p")
            w = winner_of(canon(t1f), canon(t2f), score)        # winner from feed-order score
            if kx.get("team1") and norm(canon(t1f)) != norm(kx["team1"]):
                a, b = b, a                                      # orient goals + pens to OUR team1/team2
                if p: p = [p[1], p[0]]
            pens = f'{p[0]}–{p[1]} pens' if p else None
            matches[kx["id"]] = {"status":"final","winner":w,"team1_goals":a,"team2_goals":b,"pens":pens}
            finals += 1
    return matches, mapped, unmatched, finals

def fetch_espn():
    try:
        with urllib.request.urlopen(urllib.request.Request(ESPN_URL, headers={"User-Agent":"Mozilla/5.0"}), timeout=25) as r:
            return json.load(r)
    except Exception as e:
        print(f"  ESPN miss: {str(e)[:80]}"); return None

def _ev_kind(text):
    t = (text or "").lower()
    if "own goal" in t: return "og"
    if "penalty" in t and "scored" in t: return "pen"
    if t.startswith("goal"): return "goal"
    if "red card" in t: return "red"
    return None

def _espn_events(competition, id_to_side):
    """Scoring plays + red cards from ESPN's details array, oriented to OUR team1/team2."""
    out = []
    for x in competition.get("details", []):
        kind = _ev_kind(x.get("type", {}).get("text"))
        side = id_to_side.get(str(x.get("team", {}).get("id")))
        if not kind or not side: continue
        who = (x.get("athletesInvolved") or [{}])[0].get("displayName") or ""
        out.append({"min": x.get("clock", {}).get("displayValue", ""), "team": side,
                    "player": who, "kind": kind})
    return out

def normalize_espn(data, fixtures):
    """Map ESPN's finished events to our fixture IDs. ESPN gives a per-competitor winner flag and
    shootoutScore, so knockouts (incl. penalties) resolve directly. Goal/red-card details ride along
    as an 'events' list (feeds the Match Center recaps). Returns (matches, finals, unmatched)."""
    group_by_pair = {frozenset((norm(f["team1"]), norm(f["team2"]))): f for f in fixtures["group_stage"]}
    ko_by_pair = {frozenset((norm(kx["team1"]), norm(kx["team2"]))): kx
                  for kx in fixtures.get("knockout", []) if kx.get("team1") and kx.get("team2")}
    matches, finals, unmatched = {}, 0, []
    for e in data.get("events", []):
        st = e.get("status", {}).get("type", {})
        if not (st.get("state") == "post" and st.get("completed")):
            continue                                              # only truly-final matches score
        competition = (e.get("competitions") or [{}])[0]
        comp = competition.get("competitors", [])
        teams = []                                                # (our-name, goals, winner_bool, pens, espn_id)
        for c in comp:
            nm = canon(c.get("team", {}).get("displayName", ""))
            try: g = int(c.get("score"))
            except (TypeError, ValueError): g = None
            sp = c.get("shootoutScore")
            teams.append((nm, g, c.get("winner"), int(sp) if sp not in (None, "") else None,
                          str(c.get("team", {}).get("id"))))
        if len(teams) != 2 or any(t[1] is None for t in teams):
            continue
        by = {norm(t[0]): t for t in teams}
        pair = frozenset(by)
        fx = group_by_pair.get(pair)
        if fx:
            t1, t2 = by.get(norm(fx["team1"])), by.get(norm(fx["team2"]))
            if not t1 or not t2: unmatched.append(f"{teams[0][0]} v {teams[1][0]} (group)"); continue
            a, b = t1[1], t2[1]
            rec = {"status":"final","outcome":("team1" if a>b else "team2" if b>a else "draw"),
                   "team1_goals":a, "team2_goals":b}
            ev = _espn_events(competition, {t1[4]:"team1", t2[4]:"team2"})
            if ev: rec["events"] = ev
            matches[fx["id"]] = rec
            finals += 1
        else:
            kx = ko_by_pair.get(pair)
            if not kx: continue                                   # placeholder/unscheduled KO slot — skip silently
            t1, t2 = by.get(norm(kx["team1"])), by.get(norm(kx["team2"]))
            if not t1 or not t2: continue
            winner = next((t[0] for t in teams if t[2]), None)
            pens = f"{t1[3]}–{t2[3]} pens" if (t1[3] is not None and t2[3] is not None) else None
            rec = {"status":"final","winner":winner,"team1_goals":t1[1],"team2_goals":t2[1],"pens":pens}
            ev = _espn_events(competition, {t1[4]:"team1", t2[4]:"team2"})
            if ev: rec["events"] = ev
            matches[kx["id"]] = rec
            finals += 1
    return matches, finals, unmatched

def main():
    fixtures = load("fixtures.json", {"group_stage": [], "knockout": []})
    srcs = []                                                     # which sources contributed (for the stamp)

    # base layer: keep every final we already know, so a transient source outage never drops a result
    merged = dict(load("results.json", {"matches": {}}).get("matches", {}))

    # backup layer: openfootball (lags, but resilient if ESPN's endpoint ever changes)
    feed, used = fetch()
    of_finals = 0
    if feed:
        of_matches, mapped, of_unmatched, of_finals = normalize_feed(feed, fixtures)
        merged.update(of_matches)
        if of_finals: srcs.append("openfootball")
        if of_unmatched:
            print("  openfootball UNMATCHED (add an alias):"); [print("   -", u) for u in of_unmatched[:8]]
    else:
        print("  openfootball unavailable")

    # PRIMARY layer: ESPN live (near-real-time) — wins over openfootball
    espn = fetch_espn()
    espn_finals = 0
    if espn:
        espn_matches, espn_finals, espn_unmatched = normalize_espn(espn, fixtures)
        merged.update(espn_matches)
        if espn_finals: srcs.append("espn")
        if espn_unmatched:
            print("  ESPN UNMATCHED (add an alias):"); [print("   -", u) for u in espn_unmatched[:8]]
    else:
        print("  ESPN unavailable")

    if not feed and not espn and not merged:
        print("ALL SOURCES FAILED and no prior results — data/results.json untouched."); return 0

    # commissioner overrides always win
    manual = load("results_manual.json", {"matches": {}}).get("matches", {})
    merged.update(manual)
    if manual: srcs.append(f"{len(manual)} manual")

    # idempotent: only rewrite when results actually changed (no empty auto-update commits)
    if load("results.json", {}).get("matches") == merged:
        print(f"no change since last run ({len(merged)} final · sources: {', '.join(srcs) or 'none'}) — results.json untouched")
        return 0
    out = {"last_fetched_utc": datetime.datetime.utcnow().isoformat()+"Z",
           "source": " + ".join(srcs) or "none", "matches": merged}
    json.dump(out, open(os.path.join(DATA, "results.json"), "w"), ensure_ascii=False, indent=2)
    print(f"updated data/results.json — {len(merged)} final result(s) "
          f"(ESPN {espn_finals}, openfootball {of_finals}, manual {len(manual)})")
    return 0

if __name__ == "__main__":
    sys.exit(main())
