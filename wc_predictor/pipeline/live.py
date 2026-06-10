"""Live layer: ESPN public scoreboard -> rating/form/scorer updates.

State (data/live_state.json):
  elo               current live Elo per team (seeded from eloratings.net)
  form_events       per team, list of (actual - expected) results, most recent last
  player_goals_wc   goals scored at this World Cup per player
  processed_events  ESPN event ids already applied
"""

import json
from datetime import date, timedelta

from . import DATA_DIR, canonical
from ..data import TEAMS

SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard"
STATE_PATH = DATA_DIR / "live_state.json"
K_WC = 60.0


def load_state():
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return {
        "elo": {name: t.elo for name, t in TEAMS.items()},
        "form_events": {name: [] for name in TEAMS},
        "player_goals_wc": {},
        "processed_events": [],
        "last_refresh": None,
    }


def save_state(state):
    STATE_PATH.write_text(json.dumps(state, indent=2))


def _apply_result(state, home, away, hs, as_):
    """Standard Elo update (WC K=60, margin multiplier) + form tracking."""
    rh, ra = state["elo"][home], state["elo"][away]
    d = rh - ra  # WC host advantage is in the match model, not the ratings
    we = 1.0 / (1.0 + 10.0 ** (-d / 400.0))
    diff = abs(hs - as_)
    g = 1.0 if diff <= 1 else (1.5 if diff == 2 else (11.0 + diff) / 8.0)
    w = 1.0 if hs > as_ else (0.0 if hs < as_ else 0.5)
    delta = K_WC * g * (w - we)
    state["elo"][home] = rh + delta
    state["elo"][away] = ra - delta
    state["form_events"][home].append(round(w - we, 3))
    state["form_events"][away].append(round((1 - w) - (1 - we), 3))


HISTORY_PATH = DATA_DIR / "wc2026_history.json"


def load_history():
    """Permanent archive of completed WC 2026 matches (with predictions)."""
    if HISTORY_PATH.exists():
        return json.loads(HISTORY_PATH.read_text())
    return []


def _prediction_snapshot(state, home, away, hs, as_):
    """The model's pre-match view, captured BEFORE the result updates Elo.

    Includes how much probability the model gave the actual outcome and
    the actual scoreline, so accuracy can be scored later. Model-only
    (no news-sentiment nudge), so the archive is reproducible.
    """
    from .. import match_map
    params = match_map.load_params()
    pmap = match_map.probability_map(home, away, state["elo"],
                                     state["form_events"], params)
    o = pmap["outcome"]
    actual = "win_a" if hs > as_ else ("win_b" if hs < as_ else "draw")
    fav = max(o, key=o.get)
    g = pmap["grid"]
    p_score = float(g[hs][as_]) if hs < len(g) and as_ < len(g) else 0.0
    return {
        "xg": pmap["xg"],
        "outcome": {k: round(v, 4) for k, v in o.items()},
        "top_score": pmap["top_scores"][0],
        "favorite": fav,
        "favorite_hit": fav == actual,
        "p_actual_outcome": round(o[actual], 4),
        "p_actual_score": round(p_score, 4),
        "over_2_5": round(pmap["over_2_5"], 4),
    }


def _process_event(state, ev, history, known_ids):
    """Apply one completed ESPN event. Returns a summary line or None."""
    if ev["id"] in state["processed_events"]:
        return None
    if ev.get("status", {}).get("type", {}).get("state") != "post":
        return None
    comp = ev["competitions"][0]
    sides = {c["homeAway"]: c for c in comp["competitors"]}
    home = canonical(sides["home"]["team"]["displayName"])
    away = canonical(sides["away"]["team"]["displayName"])
    if home not in TEAMS or away not in TEAMS:
        return None
    hs, as_ = int(sides["home"]["score"]), int(sides["away"]["score"])

    # snapshot the prediction while Elo is still pre-match
    prediction = _prediction_snapshot(state, home, away, hs, as_)
    elo_before = {home: round(state["elo"][home], 1),
                  away: round(state["elo"][away], 1)}

    team_by_id = {sides[s]["team"].get("id"): canonical(sides[s]["team"]["displayName"])
                  for s in sides}
    scorers = []
    for detail in comp.get("details", []):
        if not detail.get("scoringPlay") or detail.get("ownGoal"):
            continue
        for ath in detail.get("athletesInvolved", []):
            name = ath.get("displayName", "")
            state["player_goals_wc"][name] = \
                state["player_goals_wc"].get(name, 0) + 1
            scorers.append({
                "player": name,
                "team": team_by_id.get(detail.get("team", {}).get("id"), ""),
                "minute": detail.get("clock", {}).get("displayValue", ""),
            })

    _apply_result(state, home, away, hs, as_)
    state["processed_events"].append(ev["id"])

    if ev["id"] not in known_ids:
        history.append({
            "event_id": ev["id"],
            "date": ev.get("date", ""),
            "stage": ev.get("season", {}).get("slug", ""),
            "venue": comp.get("venue", {}).get("fullName", ""),
            "home": home, "away": away, "score": [hs, as_],
            "scorers": scorers,
            "elo_before": elo_before,
            "elo_after": {home: round(state["elo"][home], 1),
                          away: round(state["elo"][away], 1)},
            "prediction": prediction,
        })
        known_ids.add(ev["id"])
    return f"{home} {hs}-{as_} {away}"


def refresh(days_back=None):
    """Pull completed WC matches from ESPN and fold them into the state.

    days_back defaults to the whole tournament so far, so a fresh deploy
    (empty state) rebuilds live Elo/form AND the match archive from every
    completed match; already-processed events are skipped by id, making
    this idempotent.
    """
    import requests

    state = load_state()
    history = load_history()
    known_ids = {r["event_id"] for r in history}
    if days_back is None:
        since_start = (date.today() - date(2026, 6, 10)).days
        days_back = max(3, min(since_start, 45))
    applied = []
    for offset in range(days_back, -1, -1):
        day = (date.today() - timedelta(days=offset)).strftime("%Y%m%d")
        try:
            data = requests.get(SCOREBOARD, params={"dates": day}, timeout=30).json()
        except Exception as e:  # network hiccup: skip day, try next refresh
            print(f"  fetch failed for {day}: {e}")
            continue
        for ev in data.get("events", []):
            line = _process_event(state, ev, history, known_ids)
            if line:
                applied.append(line)
    state["last_refresh"] = date.today().isoformat()
    save_state(state)
    history.sort(key=lambda r: r["date"])
    HISTORY_PATH.write_text(json.dumps(history, indent=1))
    return applied


def accuracy_summary(history):
    """Honest model scorecard over the archive. Brier: lower is better
    (0.667 = uniform guessing; good football models land ~0.55-0.60)."""
    if not history:
        return None
    n = len(history)
    fav_hits = sum(1 for r in history if r["prediction"]["favorite_hit"])
    briers, p_outcomes = [], []
    for r in history:
        o = r["prediction"]["outcome"]
        hs, as_ = r["score"]
        actual = "win_a" if hs > as_ else ("win_b" if hs < as_ else "draw")
        briers.append(sum((o[k] - (1.0 if k == actual else 0.0)) ** 2 for k in o))
        p_outcomes.append(r["prediction"]["p_actual_outcome"])
    return {
        "matches": n,
        "favorite_hit_rate": round(fav_hits / n, 3),
        "brier_score": round(sum(briers) / n, 3),
        "avg_p_actual_outcome": round(sum(p_outcomes) / n, 3),
        "avg_p_actual_score": round(
            sum(r["prediction"]["p_actual_score"] for r in history) / n, 3),
    }


def live_matches():
    """Currently in-progress matches with scores (for the watch loop)."""
    import requests
    data = requests.get(SCOREBOARD, timeout=30).json()
    out = []
    for ev in data.get("events", []):
        st = ev.get("status", {})
        if st.get("type", {}).get("state") != "in":
            continue
        comp = ev["competitions"][0]
        sides = {c["homeAway"]: c for c in comp["competitors"]}
        out.append({
            "home": canonical(sides["home"]["team"]["displayName"]),
            "away": canonical(sides["away"]["team"]["displayName"]),
            "score": f"{sides['home']['score']}-{sides['away']['score']}",
            "clock": st.get("displayClock", ""),
        })
    return out
