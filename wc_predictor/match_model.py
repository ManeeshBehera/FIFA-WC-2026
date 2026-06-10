"""Elo-driven bivariate-Poisson-ish match model.

Each team's scoring rate is an exponential function of the Elo difference,
calibrated so that an Elo gap of 0 gives ~1.30 goals per side (typical World
Cup scoring) and a gap of 400 gives roughly a 2.9 vs 0.6 split, which
reproduces the Elo formula's ~91% expected score for the stronger side.

Hosts (USA, Mexico, Canada) get a flat Elo bonus in every match — all of
their games are on home soil. A modest 50 points (about half the standard
home-advantage figure) reflects mixed crowds at a co-hosted tournament.
"""

import numpy as np

BASE_GOALS = 1.30          # per-team expected goals when evenly matched
ELO_GOAL_SLOPE = 0.0021    # goal-rate sensitivity to Elo difference
HOST_ELO_BONUS = 50.0
MAX_LAMBDA = 5.5           # cap to keep blowouts realistic


def configure(params):
    """Adopt Dixon-Coles parameters fitted on the 10-year archive."""
    global BASE_GOALS, ELO_GOAL_SLOPE, HOST_ELO_BONUS
    BASE_GOALS = float(np.exp(params["a"]))
    ELO_GOAL_SLOPE = params["b"] / 400.0
    HOST_ELO_BONUS = min(params["h"] / ELO_GOAL_SLOPE, 120.0)


def effective_elo(team) -> float:
    return team.elo + (HOST_ELO_BONUS if team.is_host else 0.0)


def goal_rates(team_a, team_b):
    """Expected goals (lam_a, lam_b) for a match between two teams."""
    d = effective_elo(team_a) - effective_elo(team_b)
    lam_a = min(BASE_GOALS * np.exp(ELO_GOAL_SLOPE * d), MAX_LAMBDA)
    lam_b = min(BASE_GOALS * np.exp(-ELO_GOAL_SLOPE * d), MAX_LAMBDA)
    return lam_a, lam_b


def simulate_match(team_a, team_b, rng):
    """One 90-minute result: (goals_a, goals_b)."""
    lam_a, lam_b = goal_rates(team_a, team_b)
    return rng.poisson(lam_a), rng.poisson(lam_b)


def simulate_knockout(team_a, team_b, rng):
    """Knockout match -> (winner, loser). Extra time at 1/3 rate, then pens.

    Penalty shootouts are nearly a coin flip; we give the stronger side a
    slight edge via a 100-point-Elo ~ 53.5% mapping.
    """
    ga, gb = simulate_match(team_a, team_b, rng)
    if ga != gb:
        return (team_a, team_b) if ga > gb else (team_b, team_a)
    lam_a, lam_b = goal_rates(team_a, team_b)
    ea, eb = rng.poisson(lam_a / 3.0), rng.poisson(lam_b / 3.0)
    if ea != eb:
        return (team_a, team_b) if ea > eb else (team_b, team_a)
    d = effective_elo(team_a) - effective_elo(team_b)
    p_a = 1.0 / (1.0 + 10.0 ** (-d / 1600.0))
    return (team_a, team_b) if rng.random() < p_a else (team_b, team_a)


def win_draw_loss(team_a, team_b):
    """Analytic 90-minute W/D/L probabilities (for the scan report)."""
    lam_a, lam_b = goal_rates(team_a, team_b)
    n = 11
    from scipy.stats import poisson
    pa = poisson.pmf(np.arange(n), lam_a)
    pb = poisson.pmf(np.arange(n), lam_b)
    grid = np.outer(pa, pb)
    p_win = np.tril(grid, -1).sum()
    p_draw = np.trace(grid)
    p_loss = np.triu(grid, 1).sum()
    s = p_win + p_draw + p_loss
    return p_win / s, p_draw / s, p_loss / s
