#!/usr/bin/env python3
"""Clear picks, results, and the standings snapshot for a clean slate (before real sheets)."""
import json, os
HERE = os.path.dirname(__file__); DATA = os.path.join(HERE, "..", "data"); ROOT = os.path.join(HERE, "..")
json.dump({"players": []}, open(os.path.join(DATA, "picks.json"), "w"), indent=2)
json.dump({"last_fetched_utc": None, "matches": {}}, open(os.path.join(DATA, "results.json"), "w"), indent=2)
sp = os.path.join(ROOT, "standings.json")
if os.path.exists(sp):
    os.remove(sp)
print("reset: picks + results cleared, standings snapshot removed")
