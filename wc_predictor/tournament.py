"""Full 2026-format tournament simulation.

48 teams, 12 groups of 4. Top two per group advance plus the 8 best
third-placed teams (ranked points / GD / goals scored / random for lots).
Third-placed qualifiers are assigned to their Round-of-32 slots via a
bipartite matching against each slot's allowed-group list, mirroring
FIFA's 495-scenario allocation table.
"""

from .data import TEAMS, GROUPS, ROUND_OF_32, ROUND_OF_16, QUARTERFINALS, SEMIFINALS
from .match_model import simulate_match, simulate_knockout


def simulate_group(group_teams, rng, teams=None):
    """Round-robin. Returns standings: list of (name, pts, gd, gf) sorted."""
    teams = teams or TEAMS
    stats = {t: [0, 0, 0] for t in group_teams}  # pts, gd, gf
    for i in range(4):
        for j in range(i + 1, 4):
            a, b = group_teams[i], group_teams[j]
            ga, gb = simulate_match(teams[a], teams[b], rng)
            stats[a][1] += ga - gb
            stats[a][2] += ga
            stats[b][1] += gb - ga
            stats[b][2] += gb
            if ga > gb:
                stats[a][0] += 3
            elif gb > ga:
                stats[b][0] += 3
            else:
                stats[a][0] += 1
                stats[b][0] += 1
    # points, GD, goals scored, then random (proxy for fair play/lots)
    order = sorted(stats, key=lambda t: (stats[t][0], stats[t][1], stats[t][2], rng.random()),
                   reverse=True)
    return [(t, *stats[t]) for t in order]


def rank_third_place(thirds, rng):
    """thirds: {group_letter: (name, pts, gd, gf)} -> 8 qualifying letters."""
    ranked = sorted(thirds, key=lambda g: (thirds[g][1], thirds[g][2], thirds[g][3], rng.random()),
                    reverse=True)
    return ranked[:8]


def assign_thirds_to_slots(qualified_letters, rng):
    """Match the 8 qualified third-place groups to T3 bracket slots.

    Backtracking perfect matching; slots tried in order of fewest options.
    Returns {slot_index_in_ROUND_OF_32: group_letter}.
    """
    slots = [(idx, set(spec[2][1])) for idx, spec in enumerate(ROUND_OF_32)
             if spec[2][0] == "T3"]
    qual = set(qualified_letters)
    slots = [(idx, allowed & qual) for idx, allowed in slots]
    slots.sort(key=lambda s: len(s[1]))

    assignment = {}

    def backtrack(k, used):
        if k == len(slots):
            return True
        idx, allowed = slots[k]
        options = list(allowed - used)
        rng.shuffle(options)
        for g in options:
            assignment[idx] = g
            if backtrack(k + 1, used | {g}):
                return True
            del assignment[idx]
        return False

    if not backtrack(0, set()):
        # No perfect matching for this combination (rare corner of the 495
        # scenarios given our slot lists) — fall back to greedy with reuse
        # of the least-constrained valid team.
        used = set()
        for idx, allowed in slots:
            pick = next((g for g in qualified_letters if g in allowed and g not in used),
                        next(g for g in qualified_letters if g not in used))
            assignment[idx] = pick
            used.add(pick)
    return assignment


def simulate_tournament(rng, recorder=None, teams=None):
    """One full tournament. Returns dict of result keys -> team names.

    recorder, if given, is called with (stage_key, team_name) for each
    advancement event.
    """
    rec = recorder or (lambda *a: None)
    teams = teams or TEAMS

    winners, runners, thirds = {}, {}, {}
    for letter, members in GROUPS.items():
        table = simulate_group(members, rng, teams)
        winners[letter] = table[0][0]
        runners[letter] = table[1][0]
        thirds[letter] = table[2]
        rec("group_win", table[0][0])

    qualified_letters = rank_third_place(thirds, rng)
    third_slot_map = assign_thirds_to_slots(qualified_letters, rng)

    for letter in GROUPS:
        for name in (winners[letter], runners[letter]):
            rec("r32", name)
    for letter in qualified_letters:
        rec("r32", thirds[letter][0])

    def resolve(slot, idx):
        kind, key = slot
        if kind == "W":
            return winners[key]
        if kind == "R":
            return runners[key]
        return thirds[third_slot_map[idx]][0]

    match_winner = {}
    for idx, (no, slot_a, slot_b, _) in enumerate(ROUND_OF_32):
        a, b = resolve(slot_a, idx), resolve(slot_b, idx)
        w, _l = simulate_knockout(teams[a], teams[b], rng)
        match_winner[no] = w.name
        rec("r16", w.name)

    for stage_key, rounds in (("qf", ROUND_OF_16), ("sf", QUARTERFINALS), ("final", SEMIFINALS)):
        for no, fa, fb, _ in rounds:
            a, b = match_winner[fa], match_winner[fb]
            w, _l = simulate_knockout(teams[a], teams[b], rng)
            match_winner[no] = w.name
            rec(stage_key, w.name)

    a, b = match_winner[101], match_winner[102]
    champ, runner_up = simulate_knockout(teams[a], teams[b], rng)
    rec("champion", champ.name)
    return {"champion": champ.name, "runner_up": runner_up.name}
