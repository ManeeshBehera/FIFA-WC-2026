"""Per-match probability map: Dixon-Coles scoreline grid, outcome odds,
most likely scores, over/unders, BTTS, and named goalscorer candidates."""

import json

import numpy as np
from scipy.stats import poisson

from .data import TEAMS
from .pipeline import DATA_DIR

GRID = 9  # consider scorelines 0..8
FORM_COEF = 0.35  # log-goal multiplier per unit of form (form is ~[-0.3, 0.3])


def load_params():
    p = DATA_DIR / "model_params.json"
    if p.exists():
        return json.loads(p.read_text())
    # fallback to the uncalibrated v1 numbers
    return {"a": np.log(1.30), "b": 0.0021 * 400, "h": 0.30, "rho": 0.0}


def expected_goals(team_a, team_b, elo, form, params, host_home=True):
    """lambda_a, lambda_b using live Elo, fitted params, form and host edge."""
    d = (elo[team_a] - elo[team_b]) / 400.0
    home_a = 1.0 if (TEAMS[team_a].is_host and not TEAMS[team_b].is_host and host_home) else 0.0
    home_b = 1.0 if (TEAMS[team_b].is_host and not TEAMS[team_a].is_host and host_home) else 0.0
    fa = np.mean(form.get(team_a, [])[-8:] or [0.0])
    fb = np.mean(form.get(team_b, [])[-8:] or [0.0])
    lam_a = np.exp(params["a"] + params["b"] * d + params["h"] * home_a + FORM_COEF * fa)
    lam_b = np.exp(params["a"] - params["b"] * d + params["h"] * home_b + FORM_COEF * fb)
    return float(np.clip(lam_a, 0.05, 5.5)), float(np.clip(lam_b, 0.05, 5.5))


def score_grid(lam_a, lam_b, rho):
    """Dixon-Coles-adjusted joint scoreline probabilities (GRID x GRID)."""
    pa = poisson.pmf(np.arange(GRID), lam_a)
    pb = poisson.pmf(np.arange(GRID), lam_b)
    grid = np.outer(pa, pb)
    grid[0, 0] *= max(1.0 - lam_a * lam_b * rho, 0.0)
    grid[0, 1] *= 1.0 + lam_a * rho
    grid[1, 0] *= 1.0 + lam_b * rho
    grid[1, 1] *= 1.0 - rho
    return grid / grid.sum()


SENTIMENT_COEF = 0.05  # log-xG nudge per unit of news sentiment [-1..1]


def probability_map(team_a, team_b, elo, form, params, intel=None):
    lam_a, lam_b = expected_goals(team_a, team_b, elo, form, params)
    if intel:
        sa = intel.get("teams", {}).get(team_a, {}).get("sentiment", 0.0)
        sb = intel.get("teams", {}).get(team_b, {}).get("sentiment", 0.0)
        lam_a *= float(np.exp(SENTIMENT_COEF * sa))
        lam_b *= float(np.exp(SENTIMENT_COEF * sb))
    grid = score_grid(lam_a, lam_b, params.get("rho", 0.0))

    p_win = float(np.tril(grid, -1).sum())
    p_draw = float(np.trace(grid))
    p_loss = float(np.triu(grid, 1).sum())

    flat = [((i, j), float(grid[i, j])) for i in range(GRID) for j in range(GRID)]
    flat.sort(key=lambda t: -t[1])

    goals_idx = np.add.outer(np.arange(GRID), np.arange(GRID))
    return {
        "teams": (team_a, team_b),
        "xg": (round(lam_a, 2), round(lam_b, 2)),
        "outcome": {"win_a": p_win, "draw": p_draw, "win_b": p_loss},
        "top_scores": [(f"{i}-{j}", p) for (i, j), p in flat[:6]],
        "over_1_5": float(grid[goals_idx >= 2].sum()),
        "over_2_5": float(grid[goals_idx >= 3].sum()),
        "over_3_5": float(grid[goals_idx >= 4].sum()),
        "btts": float(grid[1:, 1:].sum()),
        "grid": grid,
    }


def render_intel(team, intel):
    """Markdown block: news sentiment, player flags, recent headlines."""
    t = intel.get("teams", {}).get(team, {})
    flags = intel.get("players", {}).get(team, {})
    if not t and not flags:
        return []
    lines = [f"**{team}** — news sentiment {t.get('sentiment', 0.0):+.2f}"]
    for player, f in list(flags.items())[:5]:
        icon = {"out": "OUT", "doubt": "DOUBT", "boost": "BOOST"}[f["status"]]
        lines.append(f"- `{icon}` {player}: {f['evidence']}")
    for h in t.get("headlines", [])[:3]:
        lines.append(f"- {h}")
    return lines + [""]


def render_markdown(pmap, scorers_a, scorers_b, profiles, kickoff="", city="",
                    intel=None):
    a, b = pmap["teams"]
    o = pmap["outcome"]
    lines = [
        f"# {a} vs {b}",
        f"{kickoff} {('— ' + city) if city else ''}",
        "",
        f"**Expected goals:** {a} {pmap['xg'][0]} — {pmap['xg'][1]} {b}",
        "",
        f"| {a} win | Draw | {b} win |",
        "|---------|------|---------|",
        f"| {o['win_a']:.1%} | {o['draw']:.1%} | {o['win_b']:.1%} |",
        "",
        "**Most likely scorelines:** " + ", ".join(f"{s} ({p:.1%})" for s, p in pmap["top_scores"]),
        "",
        f"Over 1.5: {pmap['over_1_5']:.1%} | Over 2.5: {pmap['over_2_5']:.1%} | "
        f"Over 3.5: {pmap['over_3_5']:.1%} | Both score: {pmap['btts']:.1%}",
        "",
        "### Scoreline heatmap (rows = " + a + ", cols = " + b + ", 0-5)",
        "",
        "| | " + " | ".join(str(j) for j in range(6)) + " |",
        "|--" * 7 + "|",
    ]
    for i in range(6):
        cells = " | ".join(f"{pmap['grid'][i, j]:.1%}" for j in range(6))
        lines.append(f"| **{i}** | {cells} |")

    for team, tbl in ((a, scorers_a), (b, scorers_b)):
        lines += ["", f"### Likely scorers — {team}", "",
                  "| Player | Pos | Caps | Intl goals | P(scores) | xG |",
                  "|--------|-----|------|------------|-----------|-----|"]
        for _, r in tbl.head(7).iterrows():
            lines.append(f"| {r['player']} | {r['position']} | {r['caps']} | "
                         f"{r['goals']} | {r['p_score']:.1%} | {r['xg']:.2f} |")

    if intel:
        intel_lines = render_intel(a, intel) + render_intel(b, intel)
        if intel_lines:
            lines += ["", "### Intelligence (last 96h of football media)", ""]
            lines += intel_lines

    lines += ["", "### 10-year radar", ""]
    for t in (a, b):
        p = profiles.get(t, {})
        if p:
            lines.append(f"- **{t}**: {p['matches']} matches, "
                         f"{p['wins']}W-{p['draws']}D-{p['losses']}L, "
                         f"{p['gf_pm']} scored / {p['ga_pm']} conceded per match. "
                         f"Form (last 8 vs Elo expectation): {p['form']:+.3f}. "
                         f"Last 5: {p['last5']}")
    return "\n".join(lines)
