# World Cup 2026 Scan & Prediction System

Live Monte Carlo prediction engine for the 2026 FIFA World Cup (USA / Mexico /
Canada, June 11 – July 19, 2026) using the **real final draw**, the
**official 48-team format**, a **10-year calibrated match model**, and
**player-level goalscorer predictions**.

## Live engine (v2)

```bash
.venv/bin/python live_engine.py setup        # one-time: 10y archive, model fit, squads
.venv/bin/python live_engine.py refresh      # ingest completed results from ESPN
.venv/bin/python live_engine.py matchday 2026-06-11   # probability maps for a day
.venv/bin/python live_engine.py odds 50000   # live tournament odds (current ratings)
.venv/bin/python live_engine.py scan         # 10-year radar for all 48 teams
.venv/bin/python live_engine.py watch 5      # live loop: refresh + maps every 5 min
```

### What the live layer adds

- **10-year knowledge radar** ([pipeline/history.py](wc_predictor/pipeline/history.py)):
  downloads the full international results archive, reconstructs Elo
  history over ~49k matches, and fits a Dixon-Coles Poisson model
  (`lambda = exp(a + b·elo_diff/400 + h·home)`) by maximum likelihood on
  the last decade (~9.7k matches). Team profiles: 10-year record, scoring
  rates, and form measured as Elo over/under-performance in the last 8.
- **Player database** ([pipeline/squads.py](wc_predictor/pipeline/squads.py)):
  all 48 final squads (~1,250 players) with position, age, caps,
  international goals, club.
- **Goalscorer model** ([scorer_model.py](wc_predictor/scorer_model.py)):
  Poisson thinning of team xG into per-player P(scores), blending career
  international rate, decayed 3-year scoring form, position priors,
  caps-based participation, and live World Cup goals.
- **Live ingestion** ([pipeline/live.py](wc_predictor/pipeline/live.py)):
  ESPN's public scoreboard feeds completed results into live Elo + form
  updates and tracks tournament scorers; in-progress scores shown in
  `watch` mode. State persists in `data/live_state.json`.
- **News gatherer** ([pipeline/news.py](wc_predictor/pipeline/news.py)):
  polite single-request feeds from goal.com (Google News sitemap, robots
  allows), OneFootball (daily news sitemap), ESPN news API, and RSS from
  BBC, Guardian, Sky Sports, talkSPORT, CBS Sports, Marca, 90min,
  FourFourTwo, The Sun and Mirror — ~750+ fresh articles per sweep,
  deduped, 30-min cache. Add your own feeds in data/news_sources.json
  ([{"source": ..., "url": ...}]); dead sources are skipped gracefully.
  Run with `python live_engine.py news`.
- **Intelligence layer** ([intelligence.py](wc_predictor/intelligence.py)):
  tags every article with WC teams and squad players, then classifies
  proximity-scoped signals (text window around the player mention):
  `OUT` (ruled out/suspended), `DOUBT` (injury/fitness), `BOOST`
  (returns/passed fit/replacement call-up), plus team news sentiment.
  Flags feed the scorer model as participation multipliers (out 0.05,
  doubt 0.55, boost 1.15); sentiment nudges team xG (±5% max); match maps
  get an Intelligence section with evidence headlines.
  Keyword extraction has residual noise — every flag prints with its
  evidence headline, and `data/availability_overrides.json`
  (`{"Player Name": "out|doubt|boost|ok"}`) is human truth that always
  wins ("ok" clears a wrong flag).
- **Match probability maps** ([match_map.py](wc_predictor/match_map.py)):
  per-fixture markdown in `outputs/match_maps/` with W/D/L, xG, the full
  scoreline heatmap, most likely scores, over/unders, BTTS, top scorer
  candidates per side, and the 10-year radar of both teams.

## Deploying to Render

The repo is deploy-ready via Docker (one container runs Node + the Python
engine, with the knowledge base baked in at image build):

1. Push to GitHub/GitLab.
2. On Render: **New → Web Service → connect the repo**. Render detects the
   `Dockerfile` automatically (or use the included `render.yaml` blueprint).
3. Done — health check is `/api/status`, the port is taken from `$PORT`.

Notes for hosted operation:

- Render's disk is ephemeral: state resets on redeploy. That's handled —
  `refresh` rebuilds live Elo/form from every completed tournament match
  (ESPN, idempotent by event id), and stale artifacts regenerate on demand.
- Big Monte Carlo runs (500k/1M sims) take 10-45 minutes of CPU; on a
  small instance prefer 20k-100k, which converge to within ~0.3pp anyway.
- The Real Madrid crest watermark is a personal design homage — replace
  `webapp/public/assets/crest.svg` before hosting anything public.

## Web app (Node.js)

```bash
cd webapp && npm install && npm start   # http://localhost:3000
```

Express server ([webapp/server.js](webapp/server.js)) + dependency-free
accessible frontend ([webapp/public](webapp/public)). The Python engine
stays the brain: it exports JSON artifacts (`live_engine.py export` /
`exportday`), and the server regenerates them automatically when stale
(core 15 min, matchday 10 min) by spawning the venv Python — one engine
job at a time.

- **Tabs**: Matches (per-day probability maps with outcome bars, scoreline
  heatmaps, scorer probabilities, intelligence), Title odds, Groups,
  Team radar, Intelligence feed.
- **Action buttons** run the engine from the browser: ingest latest
  results, news sweep, re-simulate odds (selectable 10k–100k sims) — with
  a polite live status line.
- **Match lab**: pick ANY two teams (scheduled fixture or hypothetical
  knockout pairing) and the engine computes the full probability map live
  on submit — optionally forcing a fresh media sweep first. Nothing is
  pre-baked; the result shows its computation timestamp.
- **Triggered news search**: from the Intelligence tab, force-fetch all
  five media feeds *now* for a chosen team and get its updated sentiment,
  flags, and headlines.
- **Engine log** in the footer shows recent engine jobs with output tails,
  so every number is traceable to a real run.
- **API**: `GET /api/core`, `GET /api/day/:date`, `GET /api/status`,
  `POST /api/run/{refresh|news|odds}?n=`, `POST /api/analyze`
  (`{home, away, freshNews}`), `POST /api/news-team` (`{team}`).
- **Accessibility**: WAI-ARIA tab pattern with arrow-key navigation, skip
  link, captioned data tables with header scopes, `aria-live` job status,
  outcome bars with text alternatives, visible focus rings,
  light/dark via `prefers-color-scheme`, semantic landmarks throughout.

### Daily rhythm during the tournament

```bash
python live_engine.py refresh    # morning: fold in yesterday's results
python live_engine.py news       # sweep media, refresh injury/form intel
python live_engine.py matchday   # generate today's match maps (uses intel)
python live_engine.py odds       # updated title probabilities
```

`watch` runs the news sweep automatically every ~6 cycles.

---

## v1 core (static pre-tournament simulation)

## What it models

- **Real data**: the 12 confirmed groups from the December 2025 draw (with
  March 2026 playoff winners resolved) and eloratings.net Elo ratings as of
  June 2026 ([wc_predictor/data.py](wc_predictor/data.py)).
- **Match engine**: independent Poisson goals with scoring rates derived
  from the Elo difference, calibrated to World Cup scoring levels. Hosts
  (USA, Mexico, Canada) get a +50 Elo home bonus
  ([wc_predictor/match_model.py](wc_predictor/match_model.py)).
- **Exact 2026 format** ([wc_predictor/tournament.py](wc_predictor/tournament.py)):
  - 12 round-robin groups, tiebreakers points → GD → goals → lots
  - best 8 of 12 third-placed teams advance
  - third-place qualifiers matched to their Round-of-32 slots by bipartite
    matching against FIFA's allowed-group lists (matches 73–88)
  - full knockout bracket through the July 19 final, with extra time
    (1/3 scoring rate) and Elo-weighted penalty shootouts
- **Monte Carlo**: N independent tournaments (default 50k), aggregated into
  per-team probabilities of winning the group, reaching each knockout
  round, and lifting the trophy.

## Usage

```bash
.venv/bin/python run_prediction.py           # 50,000 simulations
.venv/bin/python run_prediction.py 100000    # more precision
```

Outputs:

- `outputs/REPORT.md` — full tournament scan: title odds, most likely
  finals, group-of-death ranking, group-by-group fixture probabilities
  (with xG), dark horses
- `outputs/predictions.csv` — every team's stage-by-stage probabilities

## Tuning

Model knobs live in `wc_predictor/match_model.py`:

| Parameter | Default | Meaning |
|-----------|---------|---------|
| `BASE_GOALS` | 1.30 | per-team xG between equals |
| `ELO_GOAL_SLOPE` | 0.0021 | how fast xG shifts with Elo gap |
| `HOST_ELO_BONUS` | 50 | home advantage for the three hosts |

To inject fresher ratings (injuries, form), edit the Elo numbers in
`wc_predictor/data.py` and re-run.

## Caveats

- Elo is a team-level signal; it knows nothing about squad news, injuries,
  or tactical matchups.
- Goals are modeled as independent Poissons (no Dixon-Coles low-score
  correlation), which slightly underrates draws.
- Elo-based simulations concentrate probability on top-rated sides more
  than betting markets do; treat the gap between #1 and #5 as wider than
  reality.
