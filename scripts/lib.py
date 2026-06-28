#!/usr/bin/env python3
"""Pure, deterministic scoring for the World Cup friends league.

Rules:
  Group stage  : 100 pts per correct result (team1 / draw / team2).
  Knockout     : a pick scores only if that exact team actually advanced from that match.
                 R32=100, R16=200, QF=400, SF=800, Final=1600 (3rd-place playoff = 0).
A pick can only ever score once its match has a FINAL result (locking is inherent).
A busted bracket earns 0 for every downstream round automatically — it falls out of plain
equality, no special-casing.  Everything recomputes from scratch each run, so it self-heals.
"""

ROUND_POINTS = {"R32":100, "R16":200, "QF":400, "SF":800, "Final":1600, "3P":0}
GROUP_MAX = 7200            # 72 matches x 100
KO_MAX    = 8000            # 16*100 + 8*200 + 4*400 + 2*800 + 1*1600

def _final(results, mid):
    r = results.get(mid)
    return r if (r and r.get("status") == "final") else None

def resolve_bracket(fixtures, results):
    """Walk the knockout tree, filling each match's (team1, team2) from the winners of its feeder
    matches as results come in. R32 teams are known up front; later rounds resolve as the bracket
    plays; the 3rd-place match is fed by the semifinal LOSERS. Unresolved slots return None.
    Returns {fixture_id: (team1_or_None, team2_or_None)}."""
    ko = {k["id"]: k for k in fixtures.get("knockout", [])}
    out = {}
    def win(mid):
        r = results.get(mid) or {}
        return r.get("winner") if r.get("status") == "final" else None
    def loser(mid):
        w = win(mid); a, b = out.get(mid, (None, None))
        return None if not w else (a if w == b else (b if w == a else None))
    def resolve(mid):
        if mid in out: return out[mid]
        k = ko[mid]
        if k.get("round") == "R32" or not k.get("feeds"):
            out[mid] = (k.get("team1"), k.get("team2")); return out[mid]
        f1, f2 = k["feeds"]; resolve(f1); resolve(f2)
        if k.get("loser_feed"):
            out[mid] = (loser(f1), loser(f2))
        else:
            out[mid] = (win(f1), win(f2))
        return out[mid]
    for k in fixtures.get("knockout", []): resolve(k["id"])
    return out

def score_group(player, group_fixtures, results):
    pts = correct = graded = 0
    picks = player.get("group_picks", {})
    for fx in group_fixtures:
        res = _final(results, fx["id"])
        if not res:
            continue                       # not played yet -> worth nothing to anyone (locking)
        graded += 1
        pick = picks.get(fx["id"])
        if pick is not None and pick == res.get("outcome"):
            pts += 100; correct += 1
    return {"points": pts, "correct": correct, "graded": graded}

def score_knockout(player, knockout_fixtures, results):
    pts = 0
    rounds = {k: 0 for k in ("R32","R16","QF","SF","Final")}
    picks = player.get("knockout_picks", {})
    for kx in knockout_fixtures:
        res = _final(results, kx["id"])
        if not res:
            continue
        pick = picks.get(kx["id"])
        if pick is not None and pick == res.get("winner"):
            rp = ROUND_POINTS.get(kx["round"], 0)
            pts += rp
            if kx["round"] in rounds:
                rounds[kx["round"]] += rp
    return {"points": pts, "rounds": rounds}

def score_player(player, fixtures, results):
    g = score_group(player, fixtures["group_stage"], results)
    k = score_knockout(player, fixtures.get("knockout", []), results)
    base = player.get("baseline", 0)        # handicap for a late entrant who skipped the group stage
    ko_only = bool(base) and not (player.get("group_picks") or {})
    return {
        "name": player["name"],
        "grp": g["points"] + base, "correct": g["correct"], "graded": g["graded"],
        "ko": k["points"], "rounds": k["rounds"],
        "total": g["points"] + k["points"] + base,
        "baseline": base, "ko_only": ko_only,
        "champ": (player.get("knockout_picks", {}) or {}).get("K-104"),  # Final-winner pick
        "final_goals_guess": player.get("final_goals_guess"),
    }

def standings(players, fixtures, results, prev_ranks=None, actual_final_goals=None):
    """Return players scored, sorted, ranked (ties share a rank), with movement vs prev_ranks.

    Tiebreakers, in order:
      1) total points (desc)
      2) closest guess to the actual Final total goals — only once the Final is played
      3) more correct group picks (desc)
      4) name (stable)
    """
    rows = [score_player(p, fixtures, results) for p in players]

    def goal_delta(r):
        if actual_final_goals is None or r.get("final_goals_guess") is None:
            return 10**9
        return abs(r["final_goals_guess"] - actual_final_goals)

    rows.sort(key=lambda r: (-r["total"], goal_delta(r), -r["correct"], r["name"].lower()))

    # ranks with ties sharing a number (standard competition ranking)
    prev_ranks = prev_ranks or {}
    last_total, last_rank = None, 0
    for i, r in enumerate(rows, start=1):
        if r["total"] != last_total:
            rank = i; last_total, last_rank = r["total"], i
        else:
            rank = last_rank
        r["rank"] = rank
        pr = prev_ranks.get(r["name"])
        r["move"] = (pr - rank) if pr is not None else 0   # +ve = climbed
    return rows
