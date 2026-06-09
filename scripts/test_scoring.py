#!/usr/bin/env python3
"""Hand-checked scoring tests for lib.py."""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
import lib

FIX = {
  "group_stage": [
    {"id":"G1","team1":"Mexico","team2":"South Africa"},
    {"id":"G2","team1":"Brazil","team2":"Morocco"},
    {"id":"G3","team1":"USA","team2":"Paraguay"},          # never played -> locking
  ],
  "knockout": [
    {"id":"K-73","round":"R32"},{"id":"K-89","round":"R16"},
    {"id":"K-97","round":"QF"},{"id":"K-101","round":"SF"},{"id":"K-104","round":"Final"},
  ],
}
RES = {
  "G1":{"status":"final","outcome":"team1"},      # Mexico win
  "G2":{"status":"final","outcome":"draw"},        # draw
  # G3 absent -> not played
  "K-73":{"status":"final","winner":"France"},
  "K-89":{"status":"final","winner":"France"},
  "K-97":{"status":"final","winner":"Brazil"},     # France knocked out here
  # K-101, K-104 not played
}

ALICE = {"name":"Alice",
  "group_picks":{"G1":"team1","G2":"team1","G3":"team1"},          # G1 right, G2 wrong, G3 locked
  "knockout_picks":{"K-73":"France","K-89":"France","K-97":"France","K-101":"France","K-104":"France"}}
BOB = {"name":"Bob",
  "group_picks":{"G1":"team2","G2":"draw","G3":"team1"},           # G2 right
  "knockout_picks":{"K-73":"Norway","K-89":"France"}, "final_goals_guess":3}
CAROL = {"name":"Carol",
  "group_picks":{"G2":"draw"},                                     # ties Bob on total
  "knockout_picks":{"K-89":"France"}, "final_goals_guess":5}

def expect(label, got, want):
    ok = got == want
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}: got {got}" + ("" if ok else f"  WANT {want}"))
    return ok

ok = True
a = lib.score_player(ALICE, FIX, RES)
print("Alice:", {k:a[k] for k in ("grp","correct","graded","ko","total","rounds")})
ok &= expect("Alice group pts (1 correct, G3 locked out)", a["grp"], 100)
ok &= expect("Alice graded (only played matches)", a["graded"], 2)
ok &= expect("Alice knockout = R32 100 + R16 200, then busted", a["ko"], 300)
ok &= expect("Alice round breakdown", a["rounds"], {"R32":100,"R16":200,"QF":0,"SF":0,"Final":0})
ok &= expect("Alice total", a["total"], 400)

b = lib.score_player(BOB, FIX, RES)
ok &= expect("Bob group pts", b["grp"], 100)
ok &= expect("Bob knockout (wrong R32, right R16)", b["ko"], 200)
ok &= expect("Bob total", b["total"], 300)

# standings + movement (Alice was 2nd, Bob 1st last run) ; Bob & Carol tie at 300
rows = lib.standings([ALICE,BOB,CAROL], FIX, RES, prev_ranks={"Alice":2,"Bob":1,"Carol":3})
order = [(r["name"], r["rank"], r["move"]) for r in rows]
print("standings:", order)
ok &= expect("Alice ranked 1st", rows[0]["name"], "Alice")
ok &= expect("Alice climbed +1", rows[0]["move"], 1)
ok &= expect("Bob & Carol share rank 2", (rows[1]["rank"], rows[2]["rank"]), (2,2))

# Final played: tiebreaker = closest guess to actual final goals (2). Bob(3)=1 off beats Carol(5)=3 off
RES2 = dict(RES); RES2["K-104"]={"status":"final","winner":"Brazil"}
rows2 = lib.standings([ALICE,BOB,CAROL], FIX, RES2, actual_final_goals=2)
tied = [r["name"] for r in rows2 if r["total"]==300]
ok &= expect("goals tiebreaker orders Bob before Carol", tied, ["Bob","Carol"])

print("\nRESULT:", "ALL PASS" if ok else "FAILURES ABOVE")
sys.exit(0 if ok else 1)
