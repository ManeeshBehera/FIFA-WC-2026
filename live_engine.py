#!/usr/bin/env python3
"""Live World Cup 2026 prediction engine.

Commands:
  setup                 download 10-year history, fit model, scrape squads
  refresh               ingest completed matches from ESPN (Elo/form/scorers)
  matchday [YYYY-MM-DD] probability maps for that day's fixtures (default today)
  odds [n_sims]         live tournament Monte Carlo with current ratings
  scan                  10-year team profiles report
  watch [minutes]       loop: refresh + live scores + regenerate today's maps
"""

import sys
import time
from datetime import date
from pathlib import Path

import dataclasses
import pandas as pd

from wc_predictor.data import TEAMS
from wc_predictor.pipeline import history, live, news, squads
from wc_predictor import intelligence, match_map, scorer_model, match_model

OUT = Path(__file__).parent / "outputs"


def cmd_setup():
    print("Downloading 10-year match archive + reconstructing Elo + fitting model...")
    params, profiles = history.build(force=True)
    print(f"  Dixon-Coles fit on {params['n_matches']:,} matches since 2016: "
          f"a={params['a']:.3f} b={params['b']:.3f} h={params['h']:.3f} "
          f"rho={params['rho']:.3f} (converged={params['converged']})")
    print("Scraping 48 final squads from Wikipedia...")
    sq = squads.scrape(force=True)
    print(f"  {len(sq)} players across {sq['team'].nunique()} squads")
    print("Priming live state from current Elo ratings...")
    live.save_state(live.load_state())
    print("Setup complete.")


def cmd_refresh():
    applied = live.refresh()
    print(f"Applied {len(applied)} new results:" if applied else "No new completed matches.")
    for line in applied:
        print(f"  {line}")


def _context():
    state = live.load_state()
    params = match_map.load_params()
    profiles = pd.read_json(history.DATA_DIR / "team_profiles.json").to_dict()
    sq = squads.scrape()
    gs = history.load_goalscorers()
    return state, params, profiles, sq, gs


def cmd_news():
    print("Gathering football media (goal.com, OneFootball, ESPN, BBC, Guardian)...")
    articles = news.gather(force=True)
    sq = squads.scrape()
    intel = intelligence.analyze(articles, sq)
    n_flags = sum(len(v) for v in intel["players"].values())
    print(f"\nAnalyzed {intel['n_articles']} articles -> "
          f"{len(intel['teams'])} teams with coverage, {n_flags} player flags.")
    for team, flags in sorted(intel["players"].items()):
        for player, f in flags.items():
            print(f"  {f['status'].upper():<5} {player} ({team}) — {f['evidence'][:90]}")
    hot = sorted(intel["teams"].items(), key=lambda kv: -abs(kv[1]["sentiment"]))[:8]
    print("\nStrongest news sentiment:")
    for t, v in hot:
        if v["sentiment"]:
            print(f"  {t:<15} {v['sentiment']:+.2f}")
    print("\nSaved to data/news_intel.json (matchday maps will use it).")


def cmd_matchday(day=None):
    day = day or date.today().isoformat()
    state, params, profiles, sq, gs = _context()
    intel = intelligence.load_intel()
    fx = history.fixtures_2026()
    todays = fx[fx["date"].dt.date.astype(str) == day]
    if todays.empty:
        print(f"No World Cup fixtures on {day}.")
        return
    (OUT / "match_maps").mkdir(parents=True, exist_ok=True)
    for _, m in todays.iterrows():
        a, b = m["home_team"], m["away_team"]
        if a not in TEAMS or b not in TEAMS:
            continue
        pmap = match_map.probability_map(a, b, state["elo"], state["form_events"],
                                         params, intel=intel)
        sca = scorer_model.team_scorer_table(
            sq, a, pmap["xg"][0], gs, state["player_goals_wc"],
            availability=intelligence.availability_for(intel, a))
        scb = scorer_model.team_scorer_table(
            sq, b, pmap["xg"][1], gs, state["player_goals_wc"],
            availability=intelligence.availability_for(intel, b))
        md = match_map.render_markdown(pmap, sca, scb, profiles,
                                       kickoff=str(m["date"].date()), city=m["city"],
                                       intel=intel)
        fname = f"{day}_{a.replace(' ', '')}_vs_{b.replace(' ', '')}.md"
        (OUT / "match_maps" / fname).write_text(md)
        o = pmap["outcome"]
        top = pmap["top_scores"][0]
        best_a = sca.iloc[0]["player"] if len(sca) else "?"
        best_b = scb.iloc[0]["player"] if len(scb) else "?"
        print(f"{a} vs {b}  [{o['win_a']:.0%}/{o['draw']:.0%}/{o['win_b']:.0%}]  "
              f"xG {pmap['xg'][0]}-{pmap['xg'][1]}  likely {top[0]} ({top[1]:.0%})  "
              f"top scorers: {best_a} / {best_b}")
    print(f"\nFull maps written to outputs/match_maps/")


def cmd_odds(n_sims=50_000):
    from wc_predictor.simulate import run
    state = live.load_state()
    params = match_map.load_params()
    match_model.configure(params)
    teams = {n: dataclasses.replace(t, elo=state["elo"][n]) for n, t in TEAMS.items()}
    df, top_finals = run(n_sims=n_sims, teams=teams)
    df.to_csv(OUT / "predictions_live.csv", index=False)
    print(f"Live title odds ({n_sims:,} sims, ratings as of "
          f"{state.get('last_refresh') or 'pre-tournament'}):")
    for i, r in df.head(12).iterrows():
        print(f"{i + 1:>2}. {r['team']:<15} {r['Champion']:>6.1%}  "
              f"(final {r['Reach Final']:.1%})")
    print(f"\nSaved to outputs/predictions_live.csv")


def cmd_scan():
    state, params, profiles, sq, gs = _context()
    lines = ["# 10-Year Team Radar — World Cup 2026", ""]
    order = sorted(TEAMS, key=lambda t: -state["elo"][t])
    for t in order:
        p = profiles[t]
        top = sq[sq["team"] == t].nlargest(3, "goals")
        tops = ", ".join(f"{r['player']} ({r['goals']})" for _, r in top.iterrows())
        lines.append(
            f"- **{t}** (Elo {state['elo'][t]:.0f}) — last 10y: {p['matches']} matches "
            f"{p['wins']}W-{p['draws']}D-{p['losses']}L, {p['gf_pm']}/{p['ga_pm']} "
            f"goals pm, form {p['form']:+.3f}, last5 {p['last5']}. Top intl scorers: {tops}")
    (OUT / "TEAM_RADAR.md").write_text("\n".join(lines))
    print(f"Wrote outputs/TEAM_RADAR.md ({len(order)} teams)")


def _api_dir():
    d = OUT / "api"
    d.mkdir(parents=True, exist_ok=True)
    return d


def cmd_export():
    """Write core JSON artifacts for the web app (outputs/api/core.json)."""
    import json
    state, params, profiles, sq, gs = _context()
    intel = intelligence.load_intel()

    odds_csv = OUT / "predictions_live.csv"
    if not odds_csv.exists():
        odds_csv = OUT / "predictions.csv"
    odds = pd.read_csv(odds_csv).to_dict(orient="records") if odds_csv.exists() else []

    fx = history.fixtures_2026()
    schedule = [{
        "date": str(m["date"].date()), "home": m["home_team"], "away": m["away_team"],
        "city": m["city"],
        "score": None if pd.isna(m["home_score"])
                 else f"{int(m['home_score'])}-{int(m['away_score'])}",
    } for _, m in fx.iterrows()]

    top_scorers = {
        t: sq[sq["team"] == t].nlargest(3, "goals")[["player", "goals"]]
            .to_dict(orient="records")
        for t in TEAMS
    }
    from wc_predictor.data import GROUPS
    core = {
        "generated": pd.Timestamp.utcnow().isoformat(),
        "last_refresh": state.get("last_refresh"),
        "odds": odds,
        "groups": GROUPS,
        "elo": state["elo"],
        "profiles": profiles,
        "top_scorers": top_scorers,
        "intel": intel,
        "schedule": schedule,
        "history": live.load_history(),
        "model_accuracy": live.accuracy_summary(live.load_history()),
    }
    (_api_dir() / "core.json").write_text(json.dumps(core))
    print(f"Exported outputs/api/core.json ({len(schedule)} fixtures, "
          f"{len(odds)} odds rows, {len(core['history'])} archived matches)")


def _match_payload(a, b, ctx, intel, city="", day="", score=None):
    """Full per-match analysis payload (shared by exportday and analyze)."""
    state, params, profiles, sq, gs = ctx
    pmap = match_map.probability_map(a, b, state["elo"], state["form_events"],
                                     params, intel=intel)
    sca = scorer_model.team_scorer_table(
        sq, a, pmap["xg"][0], gs, state["player_goals_wc"],
        availability=intelligence.availability_for(intel, a))
    scb = scorer_model.team_scorer_table(
        sq, b, pmap["xg"][1], gs, state["player_goals_wc"],
        availability=intelligence.availability_for(intel, b))

    def team_intel(t):
        return {
            "sentiment": intel.get("teams", {}).get(t, {}).get("sentiment", 0),
            "headlines": intel.get("teams", {}).get(t, {}).get("headlines", [])[:3],
            "flags": intel.get("players", {}).get(t, {}),
        }

    return {
        "home": a, "away": b, "city": city, "date": day, "score": score,
        "xg": pmap["xg"],
        "outcome": pmap["outcome"],
        "top_scores": pmap["top_scores"],
        "over_1_5": pmap["over_1_5"], "over_2_5": pmap["over_2_5"],
        "over_3_5": pmap["over_3_5"], "btts": pmap["btts"],
        "grid": [[round(float(x), 4) for x in row[:7]] for row in pmap["grid"][:7]],
        "scorers_home": sca.head(8).round(4).to_dict(orient="records"),
        "scorers_away": scb.head(8).round(4).to_dict(orient="records"),
        "intel_home": team_intel(a), "intel_away": team_intel(b),
    }


def cmd_exportday(day=None):
    """Write one matchday's probability maps as JSON for the web app."""
    import json
    day = day or date.today().isoformat()
    ctx = _context()
    intel = intelligence.load_intel()
    fx = history.fixtures_2026()
    todays = fx[fx["date"].dt.date.astype(str) == day]
    matches = []
    for _, m in todays.iterrows():
        a, b = m["home_team"], m["away_team"]
        if a not in TEAMS or b not in TEAMS:
            continue
        score = None if pd.isna(m["home_score"]) \
            else f"{int(m['home_score'])}-{int(m['away_score'])}"
        matches.append(_match_payload(a, b, ctx, intel,
                                      city=m["city"], day=day, score=score))
    path = _api_dir() / f"day_{day}.json"
    path.write_text(json.dumps({"date": day, "matches": matches}))
    print(f"Exported {path.relative_to(Path(__file__).parent)} ({len(matches)} matches)")


def cmd_analyze(team_a, team_b, fresh=False):
    """On-demand analysis of ANY pairing; optionally force a news sweep first.

    Writes outputs/api/analysis_latest.json for the web app.
    """
    import json
    if team_a not in TEAMS or team_b not in TEAMS:
        raise SystemExit(f"Unknown team(s): {team_a!r}, {team_b!r}")
    if fresh:
        print("Fresh news sweep before analysis...")
        intelligence.analyze(news.gather(force=True), squads.scrape())
    ctx = _context()
    intel = intelligence.load_intel()
    # attach venue/date when this pairing is actually scheduled
    fx = history.fixtures_2026()
    sched = fx[((fx["home_team"] == team_a) & (fx["away_team"] == team_b)) |
               ((fx["home_team"] == team_b) & (fx["away_team"] == team_a))]
    city = sched.iloc[0]["city"] if len(sched) else "hypothetical pairing"
    day = str(sched.iloc[0]["date"].date()) if len(sched) else ""
    payload = _match_payload(team_a, team_b, ctx, intel, city=city, day=day)
    payload["fresh_news"] = bool(fresh)
    payload["generated"] = pd.Timestamp.utcnow().isoformat()
    (_api_dir() / "analysis_latest.json").write_text(json.dumps(payload))
    o = payload["outcome"]
    print(f"{team_a} vs {team_b}: {o['win_a']:.0%}/{o['draw']:.0%}/{o['win_b']:.0%} "
          f"xG {payload['xg'][0]}-{payload['xg'][1]}")


def cmd_newsteam(team):
    """Triggered search: force-fetch all media feeds now, return one team's intel."""
    import json
    if team not in TEAMS:
        raise SystemExit(f"Unknown team: {team!r}")
    articles = news.gather(force=True)
    intel = intelligence.analyze(articles, squads.scrape())
    out = {
        "team": team,
        "generated": intel["generated"],
        "n_articles_swept": intel["n_articles"],
        "sentiment": intel.get("teams", {}).get(team, {}).get("sentiment", 0),
        "headlines": intel.get("teams", {}).get(team, {}).get("headlines", []),
        "flags": intel.get("players", {}).get(team, {}),
    }
    (_api_dir() / "team_news_latest.json").write_text(json.dumps(out))
    print(f"Swept {intel['n_articles']} articles; {team}: "
          f"sentiment {out['sentiment']:+.2f}, {len(out['flags'])} player flags")


def cmd_watch(minutes=5):
    cycle = 0
    while True:
        print(f"\n=== refresh @ {time.strftime('%H:%M:%S')} ===")
        cmd_refresh()
        if cycle % 6 == 0:  # news sweep every ~6 cycles (sources are cached 30 min)
            try:
                intelligence.analyze(news.gather(), squads.scrape())
                print("  [news] intelligence refreshed")
            except Exception as e:
                print(f"  [news] sweep failed: {e}")
        for m in live.live_matches():
            print(f"  LIVE {m['home']} {m['score']} {m['away']} ({m['clock']})")
        cmd_matchday()
        cycle += 1
        time.sleep(minutes * 60)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "matchday"
    arg = sys.argv[2] if len(sys.argv) > 2 else None
    if cmd == "analyze":
        cmd_analyze(sys.argv[2], sys.argv[3],
                    fresh=(len(sys.argv) > 4 and sys.argv[4] == "fresh"))
        sys.exit(0)
    if cmd == "newsteam":
        cmd_newsteam(sys.argv[2])
        sys.exit(0)
    {
        "setup": lambda: cmd_setup(),
        "refresh": lambda: cmd_refresh(),
        "news": lambda: cmd_news(),
        "matchday": lambda: cmd_matchday(arg),
        "odds": lambda: cmd_odds(int(arg) if arg else 50_000),
        "scan": lambda: cmd_scan(),
        "watch": lambda: cmd_watch(int(arg) if arg else 5),
        "export": lambda: cmd_export(),
        "exportday": lambda: cmd_exportday(arg),
    }[cmd]()
