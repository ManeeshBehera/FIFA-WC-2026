"""Goalscorer probabilities via Poisson thinning of team expected goals.

Each squad player gets a scoring index blending:
  - career international rate (goals / caps, shrunk toward position prior)
  - recent international goals (last 3 years, exponentially decayed)
  - live World Cup goals (heavily weighted — tournament form)
  - position prior (FW > MF > DF, GK ~ 0)
  - participation estimate from caps rank within squad (proxy for starters)

P(player scores in match) = 1 - exp(-lambda_team * share_player).
~6% of team goals are reserved for own goals / unlisted scorers.
"""

import unicodedata

import numpy as np
import pandas as pd

POS_PRIOR = {"FW": 0.30, "MF": 0.10, "DF": 0.03, "GK": 0.001}  # goals/match prior
POS_WEIGHT = {"FW": 1.00, "MF": 0.55, "DF": 0.20, "GK": 0.005}
RECENT_HALF_LIFE_DAYS = 365.0
WC_GOAL_BONUS = 0.35          # scoring-index bump per live WC goal
UNLISTED_SHARE = 0.06


def _norm(s):
    s = unicodedata.normalize("NFKD", str(s))
    return "".join(c for c in s if not unicodedata.combining(c)).lower().strip()


def recent_goals(goalscorers, team, as_of=None):
    """Decayed international goals per player over the last 3 years."""
    g = goalscorers[(goalscorers["team"] == team) & (~goalscorers["own_goal"])]
    as_of = as_of or g["date"].max()
    g = g[g["date"] >= as_of - pd.DateOffset(years=3)]
    if g.empty:
        return {}
    age_days = (as_of - g["date"]).dt.days.to_numpy()
    w = 0.5 ** (age_days / RECENT_HALF_LIFE_DAYS)
    out = {}
    for scorer, weight in zip(g["scorer"].map(_norm), w):
        out[scorer] = out.get(scorer, 0.0) + weight
    return out


def team_scorer_table(squad, team, lam_team, goalscorers, wc_goals=None,
                      availability=None):
    """Returns DataFrame: player, position, P(scores), expected goals.

    availability: {normalized player name: multiplier} from the news
    intelligence layer (injury/suspension/return flags).
    """
    sq = squad[squad["team"] == team].copy()
    if sq.empty:
        return pd.DataFrame(columns=["player", "position", "p_score", "xg"])
    recent = recent_goals(goalscorers, team)
    wc_goals = wc_goals or {}
    wc_norm = {_norm(k): v for k, v in wc_goals.items()}
    availability = availability or {}

    idx = []
    max_caps = max(sq["caps"].max(), 1)
    for _, r in sq.iterrows():
        key = _norm(r["player"])
        prior = POS_PRIOR[r["position"]]
        career = (r["goals"] + 8 * prior) / (max(r["caps"], 0) + 8)  # shrunk rate
        rec = recent.get(key, 0.0)
        # last-name fallback for accent/name-form mismatches
        if rec == 0.0:
            last = key.split()[-1] if key.split() else key
            rec = sum(v for k, v in recent.items() if k.split() and k.split()[-1] == last)
        live = wc_norm.get(key, 0)
        score_index = POS_WEIGHT[r["position"]] * (
            0.45 * career + 0.10 * rec + WC_GOAL_BONUS * live + 0.02)
        participation = min(1.0, 0.35 + 0.65 * r["caps"] / max_caps)
        participation *= availability.get(key, 1.0)
        idx.append(score_index * participation)

    sq["index"] = idx
    total = sq["index"].sum() or 1.0
    sq["share"] = sq["index"] / total * (1 - UNLISTED_SHARE)
    sq["xg"] = lam_team * sq["share"]
    sq["p_score"] = 1.0 - np.exp(-sq["xg"])
    return sq.sort_values("p_score", ascending=False)[
        ["player", "position", "caps", "goals", "p_score", "xg"]]
