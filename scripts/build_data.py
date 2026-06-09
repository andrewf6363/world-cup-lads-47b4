#!/usr/bin/env python3
"""One-time: read the friend's template and emit data/teams.json + data/fixtures.json (group stage).
The template is the source of truth for team names, group membership, and the 72 group fixtures.
Run:  python3 scripts/build_data.py
"""
import json, datetime, re, os
import openpyxl

TEMPLATE = "/Users/andrewfahey/World Cup/World Cup Selections.xlsx"
OUT = os.path.join(os.path.dirname(__file__), "..", "data")

# group letter -> (team1 column, team2 column).  9th group's header is mislabeled "K" in the
# sheet but is really Group I (France/Senegal/Iraq/Norway); we assign letters left-to-right.
GROUPS = [("A",2,3),("B",5,6),("C",8,9),("D",11,12),("E",14,15),("F",17,18),
          ("G",20,21),("H",23,24),("I",26,27),("J",29,30),("K",32,33),("L",35,36)]
ROSTER_ROWS = [4,5,6,7]                 # the four teams of each group
DATE_ROWS   = [10,15,20,25,30,35]       # kickoff date (team1 col) + time (team2 col)
TEAM_ROWS   = [11,16,21,26,31,36]       # team1 (team1 col) vs team2 (team2 col)
PICK_ROWS   = [12,17,22,27,32,37]       # pink input cells

# feed spelling -> our template spelling (extended as the results feed reveals mismatches)
ALIASES = {
    "Korea Republic":"South Korea","South Korea":"South Korea","IR Iran":"IR Iran","Iran":"IR Iran",
    "Turkey":"Türkiye","Turkiye":"Türkiye","Ivory Coast":"Côte d'Ivoire","Cote d'Ivoire":"Côte d'Ivoire",
    "Cape Verde":"Cabo Verde","DR Congo":"Congo DR","Congo DR":"Congo DR","United States":"USA",
    "Czech Republic":"Czechia","Bosnia and Herzegovina":"Bosnia-Herzegovina",
}

def parse_kickoff(date_val, time_val):
    """Combine the sheet's date + time (US Eastern) into ET / UTC ISO strings. Best-effort."""
    d = None
    if isinstance(date_val, datetime.datetime):
        d = date_val.date()
    elif isinstance(date_val, datetime.date):
        d = date_val
    elif isinstance(date_val, str):
        m = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", date_val)   # "Sat, 6.13.2026"
        if m:
            mo, da, yr = map(int, m.groups()); d = datetime.date(yr, mo, da)
    if d is None:
        return None, None
    # time
    hh = mm = 0
    if isinstance(time_val, datetime.time):
        hh, mm = time_val.hour, time_val.minute
    elif isinstance(time_val, datetime.datetime):
        hh, mm = time_val.hour, time_val.minute
    elif isinstance(time_val, str):
        m = re.match(r"(\d{1,2}):(\d{2})", time_val.strip())
        if m: hh, mm = int(m.group(1)), int(m.group(2))
    et = datetime.datetime(d.year, d.month, d.day, hh, mm)
    utc = et + datetime.timedelta(hours=4)  # EDT = UTC-4 in Jun/Jul
    return et.strftime("%Y-%m-%dT%H:%M:00-04:00"), utc.strftime("%Y-%m-%dT%H:%M:00Z")

def main():
    wb = openpyxl.load_workbook(TEMPLATE, data_only=True)
    ws = wb.worksheets[0]
    cell = lambda r,c: ws.cell(row=r, column=c).value

    groups, fixtures = {}, []
    for letter, c1, c2 in GROUPS:
        groups[letter] = [str(cell(r, c1)).strip() for r in ROSTER_ROWS]
        for i in range(6):
            t1 = str(cell(TEAM_ROWS[i], c1)).strip()
            t2 = str(cell(TEAM_ROWS[i], c2)).strip()
            ket, kutc = parse_kickoff(cell(DATE_ROWS[i], c1), cell(DATE_ROWS[i], c2))
            fixtures.append({
                "id": f"G-{letter}-{i+1}", "phase":"group", "group": letter, "matchday": i+1,
                "team1": t1, "team2": t2, "kickoff_et": ket, "kickoff_utc": kutc,
                # where this match's pick lives in a returned sheet:
                "pick_cells": [[PICK_ROWS[i], c1], [PICK_ROWS[i], c2]],
                "result": None,
            })
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT,"teams.json"),"w",encoding="utf-8") as f:
        json.dump({"groups":groups,"aliases":ALIASES}, f, ensure_ascii=False, indent=2)
    with open(os.path.join(OUT,"fixtures.json"),"w",encoding="utf-8") as f:
        json.dump({"group_stage":fixtures,"knockout":[]}, f, ensure_ascii=False, indent=2)

    print(f"teams.json: {len(groups)} groups, {sum(len(v) for v in groups.values())} teams")
    print(f"fixtures.json: {len(fixtures)} group fixtures")
    print("\nGroup A:", groups["A"])
    print("first 3 fixtures:")
    for fx in fixtures[:3]:
        print(" ", fx["id"], fx["team1"],"vs",fx["team2"], fx["kickoff_et"], "picks@", fx["pick_cells"])
    print("matchday-1 kickoffs:", [f["kickoff_et"] for f in fixtures if f["matchday"]==1][:4])

if __name__ == "__main__":
    main()
