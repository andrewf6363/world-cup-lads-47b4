#!/usr/bin/env python3
"""Create 8 filled demo sheets (/tmp/wc_demo) + a sample data/results.json, so we can run the
real ingest->score->render pipeline and eyeball the dashboard. Demo only; reset_data.py clears it."""
import os, json, openpyxl
HERE=os.path.dirname(__file__); DATA=os.path.join(HERE,"..","data")
TEMPLATE="/Users/andrewfahey/World Cup/World Cup Selections.xlsx"
fixtures=json.load(open(os.path.join(DATA,"fixtures.json")))["group_stage"]

NAMES=["Andrew","Diego","Priya","Marcus","Liam","Sofia","Theo","Owen"]
GRADED=30                                  # first 30 fixtures have results
OUTCOMES=["team1","draw","team2"]
def goals(o): return {"team1":(2,0),"draw":(1,1),"team2":(0,2)}[o]
def wrong(o): return {"team1":"team2","draw":"team1","team2":"draw"}[o]

# sample results.json for the first GRADED fixtures
matches={}
for i,fx in enumerate(fixtures[:GRADED]):
    o=OUTCOMES[i%3]; g=goals(o)
    matches[fx["id"]]={"status":"final","outcome":o,"team1_goals":g[0],"team2_goals":g[1]}
json.dump({"last_fetched_utc":"demo","matches":matches},
          open(os.path.join(DATA,"results.json"),"w"),indent=2)

os.makedirs("/tmp/wc_demo",exist_ok=True)
def name_for(fx,o): return fx["team1"] if o=="team1" else fx["team2"] if o=="team2" else "tie"
for j,name in enumerate(NAMES):
    wb=openpyxl.load_workbook(TEMPLATE); ws=wb.worksheets[0]
    for i,fx in enumerate(fixtures):
        r,c=fx["pick_cells"][0]
        if i<GRADED:
            want=OUTCOMES[i%3]
            o = want if i < (GRADED-2*j) else wrong(want)   # player j: distinct descending accuracy
        else:
            o="team1"
        ws.cell(row=r,column=c).value=name_for(fx,o)
    wb.save(f"/tmp/wc_demo/{name}.xlsx")
print(f"wrote 8 demo sheets + results.json ({GRADED} finals)")
