#!/usr/bin/env python3
"""Tests for fetch_results.normalize_feed: alias/accent matching, goal orientation when the feed
lists teams in the opposite order, draws, and knockout winners decided on penalties."""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
import fetch_results as fr

FIX = {
  "group_stage": [
    {"id":"G-A-1","team1":"Mexico","team2":"South Africa"},
    {"id":"G-A-2","team1":"Czechia","team2":"South Korea"},      # feed will say "Czech Republic", reversed order
    {"id":"G-A-3","team1":"Curacao","team2":"Côte d'Ivoire"},    # feed: "Curaçao", "Ivory Coast"
  ],
  "knockout": [{"id":"K-73","round":"R32","team1":"France","team2":"Norway"}],
}
FEED = {"matches": [
  {"group":"Group A","team1":"Mexico","team2":"South Africa","score":{"ft":[2,1]}},          # team1 win, same order
  {"group":"Group A","team1":"South Korea","team2":"Czech Republic","score":{"ft":[3,1]}},   # reversed + alias: S.Korea won
  {"group":"Group A","team1":"Curaçao","team2":"Ivory Coast","score":{"ft":[0,0]}},          # accents + draw
  {"num":73,"round":"Round of 32","team1":"Norway","team2":"France","score":{"ft":[1,1],"p":[2,4]}},  # reversed, France win on pens
  {"num":99,"round":"Quarter-finals","team1":"1A","team2":"2B"},                              # unresolved placeholder -> ignored
]}

def expect(label, got, want):
    ok = got == want
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}: {got}" + ("" if ok else f"  WANT {want}"))
    return ok

matches, mapped, unmatched, finals = fr.normalize_feed(FEED, FIX)
ok = True
ok &= expect("3/3 group matches mapped", mapped, 3)
ok &= expect("no unmatched", unmatched, [])
ok &= expect("G-A-1 team1 win 2-1", matches["G-A-1"], {"status":"final","outcome":"team1","team1_goals":2,"team2_goals":1})
# feed reversed (S.Korea listed first, won 3-1) -> oriented to our team1=Czechia: 1-3, outcome team2
ok &= expect("G-A-2 reversed+alias -> team2 win, oriented 1-3", matches["G-A-2"],
             {"status":"final","outcome":"team2","team1_goals":1,"team2_goals":3})
ok &= expect("G-A-3 accents + draw 0-0", matches["G-A-3"],
             {"status":"final","outcome":"draw","team1_goals":0,"team2_goals":0})
# knockout reversed: France advances on pens; goals+pens oriented to our team1=France
ok &= expect("K-73 winner France on pens, oriented", matches["K-73"],
             {"status":"final","winner":"France","team1_goals":1,"team2_goals":1,"pens":"4–2 pens"})
ok &= expect("unresolved QF placeholder ignored", "K-99" in matches, False)

print("\nRESULT:", "ALL PASS" if ok else "FAILURES ABOVE")
sys.exit(0 if ok else 1)
