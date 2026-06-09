#!/usr/bin/env python3
"""Pull match results from the free openfootball feed, normalize to our fixture IDs, and write
data/results.json. Manual entries in data/results_manual.json always win (the commissioner's, or
web-search results the scheduled agent fills when the feed lags). Never overwrites good data on a
failed fetch. Run:  python3 scripts/fetch_results.py
"""
import json, os, sys, re, datetime, urllib.request, unicodedata

HERE = os.path.dirname(__file__); DATA = os.path.join(HERE, "..", "data")
FEED_URLS = [
    "https://raw.githubusercontent.com/openfootball/worldcup.json/master/2026/worldcup.json",
    "https://raw.githubusercontent.com/openfootball/worldcup.json/main/2026/worldcup.json",
]
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

def main():
    fixtures = load("fixtures.json", {"group_stage": [], "knockout": []})
    feed, used = fetch()
    if not feed:
        print("FETCH FAILED — keeping existing data/results.json untouched."); return 0
    matches, mapped, unmatched, finals = normalize_feed(feed, fixtures)

    manual = load("results_manual.json", {"matches": {}}).get("matches", {})
    for mid, rec in manual.items():
        matches[mid] = rec

    out = {"last_fetched_utc": datetime.datetime.utcnow().isoformat()+"Z", "source": used, "matches": matches}
    json.dump(out, open(os.path.join(DATA, "results.json"), "w"), ensure_ascii=False, indent=2)
    print(f"group feed matches mapped: {mapped}/72" + (f"  ({finals} final)" if finals else "  (none played yet)"))
    if unmatched:
        print("  UNMATCHED (add an alias):"); [print("   -", u) for u in unmatched[:12]]
    print(f"+ {len(manual)} manual override(s)" if manual else "no manual overrides")
    print(f"wrote data/results.json ({len(matches)} final result(s))")
    return 0

if __name__ == "__main__":
    sys.exit(main())
