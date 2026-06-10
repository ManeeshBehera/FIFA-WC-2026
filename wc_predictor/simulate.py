"""Monte Carlo engine: run N tournaments, aggregate stage probabilities."""

from collections import Counter, defaultdict

import numpy as np
import pandas as pd

from .data import TEAMS, GROUPS
from .tournament import simulate_tournament

STAGES = ["r32", "r16", "qf", "sf", "final", "champion"]
STAGE_LABELS = {
    "group_win": "Win group",
    "r32": "Reach R32",
    "r16": "Reach R16",
    "qf": "Reach QF",
    "sf": "Reach SF",
    "final": "Reach Final",
    "champion": "Champion",
}


def run(n_sims=50_000, seed=2026, teams=None):
    rng = np.random.default_rng(seed)
    teams = teams or TEAMS
    counts = defaultdict(Counter)
    finals = Counter()

    for _ in range(n_sims):
        events = []
        result = simulate_tournament(rng, recorder=lambda k, t: events.append((k, t)), teams=teams)
        for k, t in events:
            counts[k][t] += 1
        finals[tuple(sorted((result["champion"], result["runner_up"])))] += 1

    group_of = {t: g for g, members in GROUPS.items() for t in members}
    rows = []
    for name, team in teams.items():
        row = {
            "team": name,
            "group": group_of[name],
            "confederation": team.confederation,
            "elo": team.elo,
            "host": team.is_host,
        }
        for key in ["group_win"] + STAGES:
            row[STAGE_LABELS[key]] = counts[key][name] / n_sims
        rows.append(row)

    df = pd.DataFrame(rows).sort_values("Champion", ascending=False).reset_index(drop=True)
    top_finals = pd.DataFrame(
        [{"final": f"{a} vs {b}", "probability": c / n_sims}
         for (a, b), c in finals.most_common(12)]
    )
    return df, top_finals
