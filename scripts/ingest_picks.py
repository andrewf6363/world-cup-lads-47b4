#!/usr/bin/env python3
"""Parse returned copies of the friend's template into data/picks.json.

Each person types the winning country's name (or "tie") in the pink box under each match.
Usage:
    python3 scripts/ingest_picks.py "/path/Picks - Diego.xlsx" ["/path/Picks - Maria.xlsx" ...]
    python3 scripts/ingest_picks.py picks_inbox/*.xlsx          # whole folder
Player name is taken from the file name (text after the last ' - ', else the stem); override
a single file with --name "Diego".  Merges (never clobbers other players); flags anything
that doesn't clearly resolve so you can confirm before it counts.
"""
import json, os, sys, re, difflib
import openpyxl

HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, "..", "data")

DRAW_WORDS = {"tie","tied","draw","drew","d","x","-","="}

def load(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as f:
        return json.load(f)

def player_name(path, override=None):
    if override:
        return override.strip()
    stem = os.path.splitext(os.path.basename(path))[0]
    stem = re.sub(r"(?i)\b(world cup selections?|picks?|copy of|final|v\d+)\b", "", stem)
    if " - " in stem:
        stem = stem.split(" - ")[-1]
    return re.sub(r"[_\-\s]+", " ", stem).strip() or os.path.basename(path)

def resolve(raw, t1, t2, aliases):
    """Map a typed cell value to 'team1' | 'team2' | 'draw' | (None, reason)."""
    if raw is None:
        return None, None
    s = str(raw).strip()
    if not s:
        return None, None
    low = s.lower()
    if low in DRAW_WORDS:
        return "draw", None
    canon = aliases.get(s, s)
    cl = canon.lower()
    t1l, t2l = t1.lower(), t2.lower()
    if cl == t1l: return "team1", None
    if cl == t2l: return "team2", None
    def partial(a, b):
        return a.startswith(b) or b.startswith(a) or b in a or a in b
    p1, p2 = partial(t1l, cl), partial(t2l, cl)
    if p1 and not p2: return "team1", None
    if p2 and not p1: return "team2", None
    r1 = difflib.SequenceMatcher(None, cl, t1l).ratio()
    r2 = difflib.SequenceMatcher(None, cl, t2l).ratio()
    if max(r1, r2) >= 0.6 and abs(r1 - r2) >= 0.08:
        return ("team1" if r1 > r2 else "team2"), None
    return None, f"{s!r} did not clearly match '{t1}', '{t2}', or 'tie'"

def ingest_one(path, fixtures, aliases, override=None):
    name = player_name(path, override)
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb.worksheets[0]
    picks, issues = {}, []
    read = 0
    for fx in fixtures:
        vals = []
        for (r, c) in fx["pick_cells"]:
            v = ws.cell(row=r, column=c).value
            if v is not None and str(v).strip():
                vals.append(v)
        if not vals:
            continue  # left blank -> unpicked (scores 0, not an error)
        outcomes, reasons = [], []
        for v in vals:
            o, why = resolve(v, fx["team1"], fx["team2"], aliases)
            (outcomes if o else reasons).append(o or why)
        uniq = set(outcomes)
        if len(uniq) == 1:
            picks[fx["id"]] = outcomes[0]; read += 1
        elif len(uniq) > 1:
            issues.append(f"{fx['id']} {fx['team1']} v {fx['team2']}: conflicting entries {vals}")
        else:
            issues.append(f"{fx['id']} {fx['team1']} v {fx['team2']}: " + "; ".join(reasons))
    return name, picks, issues, read

def merge(name, picks, store):
    for p in store["players"]:
        if p["name"].lower() == name.lower():
            p["group_picks"] = picks
            p["submitted_group"] = True
            return p
    p = {"name": name, "submitted_group": True, "submitted_knockout": False,
         "group_picks": picks, "knockout_picks": {}, "final_goals_guess": None}
    store["players"].append(p)
    return p

def main(argv):
    override = None
    if "--name" in argv:
        i = argv.index("--name"); override = argv[i+1]; del argv[i:i+2]
    files = argv
    if not files:
        print("usage: ingest_picks.py <file.xlsx> [...] [--name NAME]"); return 1

    fixtures = load("fixtures.json")["group_stage"]
    aliases = load("teams.json")["aliases"]
    store_path = os.path.join(DATA, "picks.json")
    store = json.load(open(store_path, encoding="utf-8")) if os.path.exists(store_path) else {"players": []}

    print(f"Ingesting {len(files)} sheet(s) against {len(fixtures)} fixtures\n")
    for path in files:
        name, picks, issues, read = ingest_one(path, fixtures, aliases, override if len(files)==1 else None)
        merge(name, picks, store)
        status = "OK" if not issues else f"{len(issues)} to confirm"
        print(f"  {name:<14} {read}/{len(fixtures)} picks read · {status}")
        for it in issues:
            print(f"       - {it}")

    with open(store_path, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=2)
    print(f"\nSaved {len(store['players'])} player(s) -> data/picks.json")
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
