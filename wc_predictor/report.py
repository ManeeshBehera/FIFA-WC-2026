"""Detailed tournament scan: groups, matchups, difficulty, dark horses."""

import numpy as np

from .data import TEAMS, GROUPS
from .match_model import win_draw_loss, goal_rates


def group_strength():
    """Average Elo per group and a 'group of death' index (depth of top 3)."""
    out = []
    for g, members in GROUPS.items():
        elos = sorted((TEAMS[t].elo for t in members), reverse=True)
        out.append({
            "group": g,
            "teams": ", ".join(sorted(members, key=lambda t: -TEAMS[t].elo)),
            "avg_elo": np.mean(elos),
            "death_index": np.mean(elos[:3]),  # depth of the top three
        })
    return sorted(out, key=lambda r: -r["death_index"])


def group_match_table(letter):
    """All six group fixtures with analytic W/D/L probabilities and xG."""
    members = GROUPS[letter]
    rows = []
    for i in range(4):
        for j in range(i + 1, 4):
            a, b = TEAMS[members[i]], TEAMS[members[j]]
            pw, pd_, pl = win_draw_loss(a, b)
            la, lb = goal_rates(a, b)
            rows.append({
                "fixture": f"{a.name} vs {b.name}",
                "xg": f"{la:.2f} - {lb:.2f}",
                "p_win_a": pw, "p_draw": pd_, "p_win_b": pl,
            })
    return rows


def dark_horses(df, elo_threshold=1900, prob_floor=0.02):
    """Teams outside the elite Elo tier with real semifinal chances."""
    mask = (df["elo"] < elo_threshold) & (df["Reach SF"] >= prob_floor)
    return df[mask][["team", "group", "elo", "Reach QF", "Reach SF", "Champion"]]
