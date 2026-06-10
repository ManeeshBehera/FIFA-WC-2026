"""Intelligence layer: turn the gathered news stream into model inputs.

For every article we tag World Cup teams (name/alias match) and squad
players (full-name or contextual surname match), then run keyword rules
over title+summary to classify signals:

  availability-  player injured / ruled out / suspended / doubtful
  availability+  player returns / fit / cleared / back in training
  form+ / form-  narrative momentum for a team

Output (data/news_intel.json):
  teams:   {team: {"sentiment": float[-1..1], "headlines": [..]}}
  players: {team: {player: {"status": "out"|"doubt"|"boost",
                            "evidence": headline}}}

Application downstream:
  - scorer model: participation multiplier out=0.05, doubt=0.55, boost=1.15
  - match map: xG nudged by exp(0.05 * sentiment), intel shown per match
"""

import json
import re
import unicodedata
from datetime import datetime, timezone

import pandas as pd

from .data import TEAMS
from .pipeline import DATA_DIR

INTEL_PATH = DATA_DIR / "news_intel.json"

# extra ways the press refers to teams
TEAM_ALIASES = {
    "United States": ["usmnt", "usa"],
    "South Korea": ["korea republic"],
    "Netherlands": ["dutch"],
    "Turkey": ["turkiye", "türkiye"],
    "Ivory Coast": ["cote d'ivoire"],
    "Cape Verde": ["cabo verde"],
    "DR Congo": ["congo dr"],
}

OUT_PAT = re.compile(
    r"ruled out|out of the world cup|misses? the world cup|out for the tournament|"
    r"suspended|banned|surgery|torn (acl|hamstring)|out injured|sidelined|"
    r"withdraw[ns]?|replaced in .*squad|out of the squad", re.I)
DOUBT_PAT = re.compile(
    r"injur|doubt|knock|fitness (concern|worry|test)|limp|strain|scan|"
    r"hamstring|race against time|sweat|question mark", re.I)
BOOST_PAT = re.compile(
    r"returns? to training|back in training|passed fit|declared fit|cleared to play|"
    r"boost|recovered|back in the squad|in contention", re.I)
REPLACEMENT_PAT = re.compile(
    r"replac(es?|ed|ement)|called up|call-up|drafted in|joins the squad", re.I)
WINDOW = 110  # chars around a player mention that a signal must fall within
FORM_POS_PAT = re.compile(
    r"in[- ]form|brace|hat[- ]?trick|masterclass|brilliant|stunning|cruise|"
    r"thrash|dominant|unbeaten", re.I)
FORM_NEG_PAT = re.compile(
    r"crisis|slump|woeful|turmoil|under pressure|row|dispute|chaos|"
    r"poor form|out of form|struggling", re.I)


def _norm(s):
    s = unicodedata.normalize("NFKD", str(s))
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def _team_patterns():
    pats = {}
    for name in TEAMS:
        variants = [name.lower()] + TEAM_ALIASES.get(name, [])
        pats[name] = re.compile(
            r"\b(" + "|".join(re.escape(v) for v in variants) + r")\b", re.I)
    return pats


def analyze(articles, squads: pd.DataFrame):
    team_pats = _team_patterns()
    # player index: normalized full name -> (team, player); surnames kept
    # only when >= 5 chars and unique across all squads to limit collisions
    full_idx, sur_count = {}, {}
    for _, r in squads.iterrows():
        full = _norm(r["player"])
        full_idx[full] = (r["team"], r["player"])
        sur = full.split()[-1] if full.split() else ""
        if len(sur) >= 5:
            sur_count.setdefault(sur, []).append((r["team"], r["player"]))
    sur_idx = {s: v[0] for s, v in sur_count.items() if len(v) == 1}

    team_sent = {t: 0.0 for t in TEAMS}
    team_heads = {t: [] for t in TEAMS}
    player_flags = {t: {} for t in TEAMS}

    def classify_window(seg):
        """Signal for one player-centered text window."""
        if REPLACEMENT_PAT.search(seg) and not OUT_PAT.search(seg):
            return "boost"
        if OUT_PAT.search(seg):
            return "out"
        if BOOST_PAT.search(seg) and not DOUBT_PAT.search(seg):
            return "boost"
        if DOUBT_PAT.search(seg):
            return "doubt"
        return None

    for a in articles:
        text = f"{a['title']} {a.get('summary', '')}"
        ntext = _norm(text)
        teams_hit = [t for t, p in team_pats.items() if p.search(text)]

        # player mentions with positions, so signals stay local to the name
        players_hit = []  # (team, player, position_in_ntext)
        for full, (team, player) in full_idx.items():
            pos = ntext.find(full)
            if pos >= 0:
                players_hit.append((team, player, pos))
        if not players_hit:
            for sur, (team, player) in sur_idx.items():
                # surname alone only counts when the team is also mentioned
                m = re.search(rf"\b{re.escape(sur)}\b", ntext)
                if m and team in teams_hit:
                    players_hit.append((team, player, m.start()))

        is_out = bool(OUT_PAT.search(text))
        is_doubt = bool(DOUBT_PAT.search(text))
        is_boost = bool(BOOST_PAT.search(text))

        for team, player, pos in set(players_hit):
            window = ntext[max(0, pos - WINDOW):pos + WINDOW]
            status = classify_window(window)
            if status is None:
                continue
            cur = player_flags[team].get(player, {}).get("status")
            rank = {"out": 3, "doubt": 2, "boost": 1}
            if cur is None or rank[status] > rank.get(cur, 0):
                player_flags[team][player] = {
                    "status": status, "evidence": a["title"][:140]}

        for t in set(teams_hit):
            delta = 0.0
            if FORM_POS_PAT.search(text):
                delta += 0.5
            if FORM_NEG_PAT.search(text):
                delta -= 0.5
            if is_out or (is_doubt and not is_boost):
                delta -= 0.3
            if is_boost:
                delta += 0.2
            if delta:
                team_sent[t] += delta
            if len(team_heads[t]) < 6:
                team_heads[t].append(f"[{a['source']}] {a['title'][:120]}")

    import numpy as np
    intel = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "n_articles": len(articles),
        "teams": {t: {"sentiment": round(float(np.tanh(team_sent[t] / 3.0)), 3),
                      "headlines": team_heads[t]}
                  for t in TEAMS if team_heads[t] or team_sent[t]},
        "players": {t: f for t, f in player_flags.items() if f},
    }
    INTEL_PATH.write_text(json.dumps(intel, indent=1))
    return intel


def load_intel():
    if INTEL_PATH.exists():
        return json.loads(INTEL_PATH.read_text())
    return {"teams": {}, "players": {}}


AVAILABILITY_MULT = {"out": 0.05, "doubt": 0.55, "boost": 1.15, "ok": 1.0}
OVERRIDES_PATH = DATA_DIR / "availability_overrides.json"


def availability_for(intel, team):
    """{normalized player name: participation multiplier} for one team.

    data/availability_overrides.json ({"Player Name": "out|doubt|boost|ok"})
    is human-edited truth and wins over auto-extracted flags; "ok" clears
    a wrong flag.
    """
    out = {_norm(p): AVAILABILITY_MULT[f["status"]]
           for p, f in intel.get("players", {}).get(team, {}).items()}
    if OVERRIDES_PATH.exists():
        overrides = json.loads(OVERRIDES_PATH.read_text())
        for p, status in overrides.items():
            if status in AVAILABILITY_MULT:
                out[_norm(p)] = AVAILABILITY_MULT[status]
    return out
