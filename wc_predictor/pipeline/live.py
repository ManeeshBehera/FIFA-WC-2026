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


def refresh(days_back=None):
    """Pull completed WC matches from ESPN and fold them into the state.

    days_back defaults to the whole tournament so far, so a fresh deploy
    (empty state) rebuilds live Elo/form from every completed match;
    already-processed events are skipped by id, making this idempotent.
    """
    import requests

    state = load_state()
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
            if ev["id"] in state["processed_events"]:
                continue
            if ev.get("status", {}).get("type", {}).get("state") != "post":
                continue
            comp = ev["competitions"][0]
            sides = {c["homeAway"]: c for c in comp["competitors"]}
            home = canonical(sides["home"]["team"]["displayName"])
            away = canonical(sides["away"]["team"]["displayName"])
            if home not in TEAMS or away not in TEAMS:
                continue
            hs, as_ = int(sides["home"]["score"]), int(sides["away"]["score"])
            _apply_result(state, home, away, hs, as_)
            for detail in comp.get("details", []):
                if not detail.get("scoringPlay") or detail.get("ownGoal"):
                    continue
                for ath in detail.get("athletesInvolved", []):
                    name = ath.get("displayName", "")
                    state["player_goals_wc"][name] = \
                        state["player_goals_wc"].get(name, 0) + 1
            state["processed_events"].append(ev["id"])
            applied.append(f"{home} {hs}-{as_} {away}")
    state["last_refresh"] = date.today().isoformat()
    save_state(state)
    return applied


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
