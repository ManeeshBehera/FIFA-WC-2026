"""Ten-year knowledge radar built from the full international match archive.

- Downloads martj42/international_results (every international since 1872,
  plus the complete 2026 World Cup fixture list) and goalscorers.csv.
- Reconstructs a historical Elo series over the whole archive (eloratings.net
  formula: tournament K, goal-margin multiplier, +100 home advantage).
- Fits a Dixon-Coles Poisson goal model on the last 10 years by maximum
  likelihood: lambda = exp(a + b*elo_diff/400 + h*home).
- Builds per-team profiles: 10-year record, scoring rates, and current form
  (Elo over/under-performance across the last 8 matches).

Everything is cached under data/ and refreshed on demand.
"""

import json
import time

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import poisson

from . import DATA_DIR, canonical
from ..data import TEAMS

RESULTS_URL = "https://raw.githubusercontent.com/martj42/international_results/master/results.csv"
SCORERS_URL = "https://raw.githubusercontent.com/martj42/international_results/master/goalscorers.csv"
CACHE_HOURS = 6


def _cached_download(url, dest, force=False):
    dest = DATA_DIR / dest
    if not force and dest.exists() and (time.time() - dest.stat().st_mtime) < CACHE_HOURS * 3600:
        return dest
    import requests
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    dest.write_bytes(r.content)
    return dest


def load_results(force=False):
    path = _cached_download(RESULTS_URL, "results.csv", force)
    df = pd.read_csv(path, parse_dates=["date"])
    df["home_team"] = df["home_team"].map(canonical)
    df["away_team"] = df["away_team"].map(canonical)
    return df


def load_goalscorers(force=False):
    path = _cached_download(SCORERS_URL, "goalscorers.csv", force)
    df = pd.read_csv(path, parse_dates=["date"])
    df["team"] = df["team"].map(canonical)
    return df


def _k_factor(tournament: str) -> float:
    t = tournament.lower()
    if "fifa world cup" in t and "qualification" not in t:
        return 60.0
    majors = ("uefa euro", "copa américa", "copa america", "african cup",
              "africa cup", "afc asian cup", "gold cup", "confederations")
    if any(m in t for m in majors) and "qualification" not in t:
        return 50.0
    if "qualification" in t or "nations league" in t:
        return 40.0
    if "friendly" in t:
        return 20.0
    return 30.0


def compute_historical_elo(df):
    """Run Elo across the archive. Returns (df with pre-match Elo, ratings)."""
    played = df["home_score"].notna()
    ratings = {}
    eh, ea = np.full(len(df), 1500.0), np.full(len(df), 1500.0)
    rows = zip(df["home_team"].to_numpy(), df["away_team"].to_numpy(),
               df["home_score"].to_numpy(), df["away_score"].to_numpy(),
               df["neutral"].to_numpy(), df["tournament"].to_numpy())
    for i, (h, a, hs, as_, neutral, tourn) in enumerate(rows):
        rh, ra = ratings.get(h, 1500.0), ratings.get(a, 1500.0)
        eh[i], ea[i] = rh, ra
        if not played.iloc[i]:
            continue
        d = rh - ra + (0.0 if neutral else 100.0)
        we = 1.0 / (1.0 + 10.0 ** (-d / 400.0))
        diff = abs(hs - as_)
        g = 1.0 if diff <= 1 else (1.5 if diff == 2 else (11.0 + diff) / 8.0)
        w = 1.0 if hs > as_ else (0.0 if hs < as_ else 0.5)
        delta = _k_factor(tourn) * g * (w - we)
        ratings[h] = rh + delta
        ratings[a] = ra - delta
    out = df.copy()
    out["elo_home"], out["elo_away"] = eh, ea
    return out, ratings


def fit_goal_model(df_elo, since="2016-06-01"):
    """Dixon-Coles MLE on the last decade. Returns dict(a, b, h, rho)."""
    m = df_elo[(df_elo["date"] >= since) & df_elo["home_score"].notna()].copy()
    m = m[(m["home_score"] <= 12) & (m["away_score"] <= 12)]
    d = ((m["elo_home"] - m["elo_away"]) / 400.0).to_numpy()
    home = (~m["neutral"].astype(bool)).astype(float).to_numpy()
    x = m["home_score"].to_numpy(float)
    y = m["away_score"].to_numpy(float)

    def nll(p):
        a, b, h, rho = p
        lam = np.exp(a + b * d + h * home)
        mu = np.exp(a - b * d)
        ll = poisson.logpmf(x, lam) + poisson.logpmf(y, mu)
        tau = np.ones_like(ll)
        m00 = (x == 0) & (y == 0)
        m01 = (x == 0) & (y == 1)
        m10 = (x == 1) & (y == 0)
        m11 = (x == 1) & (y == 1)
        tau[m00] = 1.0 - lam[m00] * mu[m00] * rho
        tau[m01] = 1.0 + lam[m01] * rho
        tau[m10] = 1.0 + mu[m10] * rho
        tau[m11] = 1.0 - rho
        return -(ll + np.log(np.clip(tau, 1e-10, None))).sum()

    res = minimize(nll, x0=[0.25, 0.6, 0.25, 0.05], method="L-BFGS-B",
                   bounds=[(-1, 1), (0.1, 2.0), (0.0, 0.8), (-0.2, 0.2)])
    a, b, h, rho = res.x
    return {"a": a, "b": b, "h": h, "rho": rho,
            "n_matches": int(len(m)), "converged": bool(res.success)}


def team_profiles(df_elo, years=10):
    """Per-WC-team 10-year scan + current form vs Elo expectation."""
    cutoff = df_elo["date"].max() - pd.DateOffset(years=years)
    profiles = {}
    for name in TEAMS:
        m = df_elo[(df_elo["date"] >= cutoff) & df_elo["home_score"].notna() &
                   ((df_elo["home_team"] == name) | (df_elo["away_team"] == name))]
        is_home = m["home_team"] == name
        gf = np.where(is_home, m["home_score"], m["away_score"])
        ga = np.where(is_home, m["away_score"], m["home_score"])
        elo_self = np.where(is_home, m["elo_home"], m["elo_away"])
        elo_opp = np.where(is_home, m["elo_away"], m["elo_home"])
        we = 1.0 / (1.0 + 10.0 ** (-(elo_self - elo_opp) / 400.0))
        actual = np.where(gf > ga, 1.0, np.where(gf < ga, 0.0, 0.5))
        # form: mean Elo over/under-performance, last 8 matches
        form = float(np.mean((actual - we)[-8:])) if len(m) >= 4 else 0.0
        last5 = ["WDL"[int(2 - (a_ * 2))] for a_ in actual[-5:]]
        profiles[name] = {
            "matches": int(len(m)),
            "wins": int((gf > ga).sum()), "draws": int((gf == ga).sum()),
            "losses": int((gf < ga).sum()),
            "gf_pm": round(float(gf.mean()), 2) if len(m) else 0.0,
            "ga_pm": round(float(ga.mean()), 2) if len(m) else 0.0,
            "form": round(form, 3),
            "last5": "".join(last5),
        }
    return profiles


def build(force=False):
    """Run the whole radar. Writes model_params.json + team_profiles.json."""
    df = load_results(force)
    df_elo, ratings = compute_historical_elo(df)
    params = fit_goal_model(df_elo)
    profiles = team_profiles(df_elo)
    (DATA_DIR / "model_params.json").write_text(json.dumps(params, indent=2))
    (DATA_DIR / "team_profiles.json").write_text(json.dumps(profiles, indent=2))
    # sanity: our computed Elo vs eloratings.net anchors
    drift = {n: round(ratings.get(n, 1500) - t.elo, 0) for n, t in TEAMS.items()}
    (DATA_DIR / "elo_drift_check.json").write_text(json.dumps(drift, indent=2))
    return params, profiles


def fixtures_2026():
    """The official remaining 2026 WC fixtures from the archive."""
    df = load_results()
    fx = df[(df["tournament"] == "FIFA World Cup") & (df["date"].dt.year == 2026)]
    return fx[["date", "home_team", "away_team", "city", "home_score", "away_score"]]
