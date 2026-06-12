#!/usr/bin/env python3
"""Exit 0 if any match is live or kicking off within 15 minutes (i.e. the live loop
should keep polling), exit 1 otherwise. A match counts as possibly-live from KO-15m
to KO+2h40m (covers delays; knockout extra time + pens fits within the buffer)."""
import json, os, sys, datetime

HERE = os.path.dirname(__file__); DATA = os.path.join(HERE, "..", "data")
fx = json.load(open(os.path.join(DATA, "fixtures.json"), encoding="utf-8"))
M = json.load(open(os.path.join(DATA, "results.json"), encoding="utf-8")).get("matches", {})
now = datetime.datetime.now(datetime.timezone.utc)

for f in fx["group_stage"] + fx.get("knockout", []):
    if M.get(f["id"], {}).get("status") == "final":
        continue
    iso = f.get("kickoff_utc")
    if not iso:
        continue
    ko = datetime.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    if ko - datetime.timedelta(minutes=15) <= now <= ko + datetime.timedelta(hours=2, minutes=40):
        sys.exit(0)
sys.exit(1)
