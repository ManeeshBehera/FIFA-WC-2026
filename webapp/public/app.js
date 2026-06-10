/* World Cup 2026 predictor UI — vanilla JS, no build step. */

const $ = (sel) => document.querySelector(sel);
const pct = (x) => (100 * x).toFixed(1) + '%';
const esc = (s) =>
  String(s).replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

let CORE = null;

// ---------------- tabs (WAI-ARIA tab pattern with roving tabindex) ----------
const tabs = [...document.querySelectorAll('[role="tab"]')];
function selectTab(tab) {
  tabs.forEach((t) => {
    const selected = t === tab;
    t.setAttribute('aria-selected', selected);
    t.tabIndex = selected ? 0 : -1;
    document.getElementById(t.getAttribute('aria-controls')).hidden = !selected;
  });
  tab.focus();
}
tabs.forEach((tab, i) => {
  tab.addEventListener('click', () => selectTab(tab));
  tab.addEventListener('keydown', (e) => {
    const move = { ArrowRight: 1, ArrowLeft: -1, Home: -i, End: tabs.length - 1 - i }[e.key];
    if (move === undefined) return;
    e.preventDefault();
    selectTab(tabs[(i + move + tabs.length) % tabs.length]);
  });
});

// ---------------- engine actions -------------------------------------------
async function runEngineAction(action, btn, sims) {
  btn.disabled = true;
  $('#job-status').textContent = `Running ${action}…`;
  try {
    const qs = action === 'odds' && sims ? `?n=${sims}` : '';
    const r = await fetch(`/api/run/${action}${qs}`, { method: 'POST' });
    if (r.status === 409) {
      $('#job-status').textContent = 'Engine busy — try again shortly.';
      return;
    }
    await pollUntilIdle(action);
    await loadCore(true);
    await loadDay($('#day-picker').value, true);
  } finally {
    btn.disabled = false;
  }
}

document.querySelectorAll('[data-action]').forEach((btn) => {
  btn.addEventListener('click', () => runEngineAction(btn.dataset.action, btn));
});

// re-simulate dropdown: opens on hover (CSS) and click; menu items run odds
const dropdown = $('#sim-dropdown');
const resimBtn = $('#resim-btn');
resimBtn.addEventListener('click', () => {
  const open = dropdown.classList.toggle('open');
  resimBtn.setAttribute('aria-expanded', String(open));
});
document.addEventListener('click', (e) => {
  if (!dropdown.contains(e.target)) {
    dropdown.classList.remove('open');
    resimBtn.setAttribute('aria-expanded', 'false');
  }
});
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && dropdown.classList.contains('open')) {
    dropdown.classList.remove('open');
    resimBtn.setAttribute('aria-expanded', 'false');
    resimBtn.focus();
  }
});
dropdown.querySelectorAll('[data-sims]').forEach((item) => {
  item.addEventListener('click', () => {
    dropdown.classList.remove('open');
    resimBtn.setAttribute('aria-expanded', 'false');
    runEngineAction('odds', resimBtn, item.dataset.sims);
  });
});

async function pollUntilIdle(action) {
  // up to ~70 min: 500k/1M-sim Monte Carlo runs are slow by design
  for (let i = 0; i < 1680; i++) {
    await new Promise((r) => setTimeout(r, 2500));
    const s = await (await fetch('/api/status')).json();
    if (!s.running) {
      const last = s.recentJobs[0];
      $('#job-status').textContent = last
        ? `${action} finished (${last.tail.slice(-1)[0] || 'ok'})`
        : `${action} finished`;
      return;
    }
    $('#job-status').textContent = `Running ${s.running.label}…`;
  }
}

// ---------------- matches panel ---------------------------------------------
function outcomeBar(o, home, away) {
  const a = Math.round(o.win_a * 100);
  const d = Math.round(o.draw * 100);
  const b = 100 - a - d;
  return `<div class="outcome-bar" role="img"
    aria-label="${esc(home)} win ${a} percent, draw ${d} percent, ${esc(away)} win ${b} percent">
    <span class="seg-a" style="width:${a}%">${a}%</span>
    <span class="seg-d" style="width:${d}%">${d}%</span>
    <span class="seg-b" style="width:${b}%">${b}%</span>
  </div>`;
}

function heatmap(grid, home, away) {
  const head = grid[0].map((_, j) => `<th scope="col">${j}</th>`).join('');
  const rows = grid
    .map(
      (row, i) =>
        `<tr><th scope="row">${i}</th>` +
        row.map((p) => `<td>${(100 * p).toFixed(1)}</td>`).join('') +
        '</tr>'
    )
    .join('');
  return `<table class="heatmap">
    <caption>Scoreline probabilities (%). Rows: ${esc(home)} goals. Columns: ${esc(away)} goals.</caption>
    <thead><tr><td></td>${head}</tr></thead><tbody>${rows}</tbody></table>`;
}

function scorerTable(team, rows) {
  if (!rows.length) return '';
  const body = rows
    .map(
      (r) => `<tr><td>${esc(r.player)}</td><td>${esc(r.position)}</td>
      <td class="num">${r.caps}</td><td class="num">${r.goals}</td>
      <td class="num">${pct(r.p_score)}</td></tr>`
    )
    .join('');
  return `<table>
    <caption>Likely scorers — ${esc(team)}</caption>
    <thead><tr><th scope="col">Player</th><th scope="col">Pos</th>
    <th scope="col">Caps</th><th scope="col">Intl goals</th>
    <th scope="col">P(scores)</th></tr></thead><tbody>${body}</tbody></table>`;
}

function intelBlock(team, intel) {
  const flags = Object.entries(intel.flags || {});
  const sent = intel.sentiment || 0;
  if (!flags.length && !(intel.headlines || []).length) return '';
  const cls = sent > 0 ? 'sent-pos' : sent < 0 ? 'sent-neg' : '';
  const items = flags
    .map(
      ([p, f]) => `<li><span class="flag-${f.status}">${f.status.toUpperCase()}</span>
      ${esc(p)} — <cite>${esc(f.evidence)}</cite></li>`
    )
    .concat((intel.headlines || []).map((h) => `<li>${esc(h)}</li>`))
    .join('');
  return `<div class="intel-team">
    <strong>${esc(team)}</strong> — news sentiment
    <span class="${cls}">${sent >= 0 ? '+' : ''}${sent.toFixed(2)}</span>
    <ul>${items}</ul></div>`;
}

function matchCard(m) {
  const score = m.score ? ` — final score ${m.score}` : '';
  const tops = m.top_scores
    .map(([s, p]) => `${s} (${(100 * p).toFixed(0)}%)`)
    .join(', ');
  return `<article class="match-card">
    <h3>${esc(m.home)} vs ${esc(m.away)}${score}</h3>
    <p class="match-meta">${esc(m.city)} — expected goals ${m.xg[0]} : ${m.xg[1]}</p>
    ${outcomeBar(m.outcome, m.home, m.away)}
    <p class="stat-row">
      <span>Most likely: ${tops}</span>
      <span>Over 2.5: ${pct(m.over_2_5)}</span>
      <span>Both score: ${pct(m.btts)}</span>
    </p>
    <details><summary>Scoreline heatmap</summary>${heatmap(m.grid, m.home, m.away)}</details>
    <details><summary>Goalscorer probabilities</summary>
      ${scorerTable(m.home, m.scorers_home)}${scorerTable(m.away, m.scorers_away)}
    </details>
    <details><summary>Intelligence</summary>
      ${intelBlock(m.home, m.intel_home)}${intelBlock(m.away, m.intel_away)}
      <p>No coverage shown means no recent flagged articles.</p>
    </details>
  </article>`;
}

async function loadDay(date, bust) {
  const el = $('#matches');
  el.innerHTML = '<p>Loading match maps…</p>';
  const r = await fetch(`/api/day/${date}${bust ? '?t=' + Date.now() : ''}`);
  if (!r.ok) {
    el.innerHTML = '<p>Could not load this day.</p>';
    return;
  }
  const data = await r.json();
  el.innerHTML = data.matches.length
    ? data.matches.map(matchCard).join('')
    : '<p>No World Cup fixtures on this day (knockout pairings appear once groups finish).</p>';
}

// ---------------- odds / groups / radar / intel panels ----------------------
function renderOdds() {
  const rows = [...CORE.odds]
    .sort((a, b) => b.Champion - a.Champion)
    .map(
      (r, i) => `<tr><td class="num">${i + 1}</td><td>${esc(r.team)}</td>
      <td>${esc(r.group)}</td><td class="num">${Math.round(r.elo)}</td>
      <td class="num">${pct(r['Win group'])}</td><td class="num">${pct(r['Reach R16'])}</td>
      <td class="num">${pct(r['Reach QF'])}</td><td class="num">${pct(r['Reach SF'])}</td>
      <td class="num">${pct(r['Reach Final'])}</td><td class="num">${pct(r.Champion)}</td></tr>`
    )
    .join('');
  $('#odds').innerHTML = `<table>
    <caption>All 48 teams, Monte Carlo stage probabilities</caption>
    <thead><tr><th scope="col">#</th><th scope="col">Team</th><th scope="col">Group</th>
    <th scope="col">Elo</th><th scope="col">Win group</th><th scope="col">R16</th>
    <th scope="col">QF</th><th scope="col">SF</th><th scope="col">Final</th>
    <th scope="col">Champion</th></tr></thead><tbody>${rows}</tbody></table>`;
}

function renderGroups() {
  $('#groups').innerHTML = Object.entries(CORE.groups)
    .map(([letter, teams]) => {
      const items = teams
        .map((t) => `<li>${esc(t)} <small>(${Math.round(CORE.elo[t])})</small></li>`)
        .join('');
      return `<div class="group-card"><h3>Group ${letter}</h3><ol>${items}</ol></div>`;
    })
    .join('');
}

function renderRadar() {
  const teams = Object.keys(CORE.profiles).sort(
    (a, b) => CORE.elo[b] - CORE.elo[a]
  );
  const rows = teams
    .map((t) => {
      const p = CORE.profiles[t];
      const scorers = (CORE.top_scorers[t] || [])
        .map((s) => `${esc(s.player)} (${s.goals})`)
        .join(', ');
      return `<tr><td>${esc(t)}</td><td class="num">${Math.round(CORE.elo[t])}</td>
      <td class="num">${p.wins}-${p.draws}-${p.losses}</td>
      <td class="num">${p.gf_pm} / ${p.ga_pm}</td>
      <td class="num">${p.form >= 0 ? '+' : ''}${p.form}</td>
      <td>${esc(p.last5)}</td><td>${scorers}</td></tr>`;
    })
    .join('');
  $('#radar').innerHTML = `<table>
    <caption>Last 10 years of internationals per team; form is Elo over/under-performance across the last 8 matches</caption>
    <thead><tr><th scope="col">Team</th><th scope="col">Elo</th><th scope="col">W-D-L</th>
    <th scope="col">Goals for/against per match</th><th scope="col">Form</th>
    <th scope="col">Last 5</th><th scope="col">Top intl scorers in squad</th></tr></thead>
    <tbody>${rows}</tbody></table>`;
}

function renderIntel() {
  const teams = Object.entries(CORE.intel.teams || {}).sort(
    (a, b) => Math.abs(b[1].sentiment) - Math.abs(a[1].sentiment)
  );
  $('#intel').innerHTML =
    `<p>${CORE.intel.n_articles || 0} articles analyzed (goal.com, OneFootball, ESPN, BBC, Guardian).
     Generated ${esc(CORE.intel.generated || 'n/a')}.</p>` +
    teams
      .map(([t, v]) =>
        intelBlock(t, {
          sentiment: v.sentiment,
          headlines: v.headlines,
          flags: (CORE.intel.players || {})[t] || {},
        })
      )
      .join('');
}

// ---------------- match lab + team news search -------------------------------
function fillTeamSelects() {
  const teams = Object.values(CORE.groups).flat().sort();
  const opts = teams.map((t) => `<option>${esc(t)}</option>`).join('');
  $('#lab-home').innerHTML = opts;
  $('#lab-away').innerHTML = opts;
  $('#lab-away').selectedIndex = 1;
  $('#team-search').innerHTML = opts;
}

$('#lab-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const home = $('#lab-home').value;
  const away = $('#lab-away').value;
  const freshNews = $('#lab-fresh').checked;
  if (home === away) {
    $('#lab-status').textContent = 'Pick two different teams.';
    return;
  }
  const btn = e.target.querySelector('button');
  btn.disabled = true;
  $('#lab-status').textContent =
    `Engine running: ${home} vs ${away}${freshNews ? ' (with fresh news sweep)' : ''}…`;
  $('#lab-result').innerHTML = '';
  try {
    const r = await fetch('/api/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ home, away, freshNews }),
    });
    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      $('#lab-status').textContent = `Analysis failed: ${err.error || r.status}`;
      return;
    }
    const m = await r.json();
    $('#lab-status').textContent =
      `Computed ${new Date().toLocaleTimeString()} — ` +
      (m.date ? `scheduled fixture (${m.date}, ${m.city}).` : `${m.city}.`) +
      (m.fresh_news ? ' Used a fresh media sweep.' : '');
    $('#lab-result').innerHTML = matchCard(m);
  } finally {
    btn.disabled = false;
  }
});

$('#team-search-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const team = $('#team-search').value;
  const btn = e.target.querySelector('button');
  btn.disabled = true;
  $('#team-search-status').textContent =
    `Fetching goal.com, OneFootball, ESPN, BBC, Guardian for ${team}…`;
  try {
    const r = await fetch('/api/news-team', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ team }),
    });
    if (!r.ok) {
      $('#team-search-status').textContent = 'Search failed.';
      return;
    }
    const d = await r.json();
    $('#team-search-status').textContent =
      `Swept ${d.n_articles_swept} articles at ${new Date().toLocaleTimeString()}.`;
    $('#team-news').innerHTML = intelBlock(d.team, d);
    await loadCore(true); // global intel changed too
  } finally {
    btn.disabled = false;
  }
});

async function renderEngineLog() {
  const s = await (await fetch('/api/status')).json();
  const jobs = (s.recentJobs || [])
    .map(
      (j) => `<li><strong>${esc(j.label)}</strong> — exit ${j.code} at ${esc(j.finished)}
      <pre>${esc(j.tail.join('\n'))}</pre></li>`
    )
    .join('');
  $('#engine-log').innerHTML = jobs
    ? `<ul>${jobs}</ul>`
    : '<p>No engine jobs run from this server yet.</p>';
}
setInterval(renderEngineLog, 15000);
renderEngineLog();

// ---------------- match archive & model scorecard ---------------------------
function renderHistory() {
  const hist = CORE.history || [];
  const acc = CORE.model_accuracy;
  if (!hist.length) {
    $('#history').innerHTML =
      '<p>No completed matches yet — the archive fills automatically every time ' +
      'results are ingested, storing each final score, the goalscorers, Elo ' +
      'movement, and what the model predicted before kickoff.</p>';
    return;
  }
  const scorecard = acc
    ? `<div class="card-grid" style="margin-bottom:1rem">
        <div class="group-card"><h3>Matches archived</h3><p>${acc.matches}</p></div>
        <div class="group-card"><h3>Favorite hit rate</h3><p>${pct(acc.favorite_hit_rate)}</p></div>
        <div class="group-card"><h3>Brier score</h3>
          <p>${acc.brier_score} <small>(uniform guess = 0.667, lower is better)</small></p></div>
        <div class="group-card"><h3>Avg P(actual scoreline)</h3><p>${pct(acc.avg_p_actual_score)}</p></div>
      </div>`
    : '';
  const rows = [...hist]
    .reverse()
    .map((r) => {
      const p = r.prediction;
      const favLabel = { win_a: r.home, draw: 'Draw', win_b: r.away }[p.favorite];
      const favProb = p.outcome[p.favorite];
      const hit = p.favorite_hit
        ? '<span class="flag-boost">HIT</span>'
        : '<span class="flag-out">MISS</span>';
      const scorers = r.scorers
        .map((s) => `${s.player}${s.minute ? ' ' + s.minute : ''}`)
        .join(', ');
      const dElta = (t) => (r.elo_after[t] - r.elo_before[t]).toFixed(0);
      return `<tr>
        <td>${esc((r.date || '').slice(0, 10))}</td>
        <td>${esc(r.home)} <strong>${r.score[0]}-${r.score[1]}</strong> ${esc(r.away)}
          <br><small>${esc(scorers) || 'no scorers recorded'}</small></td>
        <td>${esc(r.stage)}</td>
        <td>${esc(favLabel)} (${pct(favProb)}) ${hit}
          <br><small>xG ${p.xg[0]}-${p.xg[1]}, called ${p.top_score[0]},
          P(actual score) ${pct(p.p_actual_score)}</small></td>
        <td class="num">${esc(r.home)} ${dElta(r.home) >= 0 ? '+' : ''}${dElta(r.home)}
          <br>${esc(r.away)} ${dElta(r.away) >= 0 ? '+' : ''}${dElta(r.away)}</td>
      </tr>`;
    })
    .join('');
  $('#history').innerHTML =
    scorecard +
    `<table>
      <caption>Every completed match with the model's pre-kickoff prediction</caption>
      <thead><tr><th scope="col">Date</th><th scope="col">Result &amp; scorers</th>
      <th scope="col">Stage</th><th scope="col">Model said</th>
      <th scope="col">Elo shift</th></tr></thead>
      <tbody>${rows}</tbody></table>`;
}

// ---------------- boot -------------------------------------------------------
async function loadCore(bust) {
  CORE = await (await fetch('/api/core' + (bust ? '?t=' + Date.now() : ''))).json();
  fillTeamSelects();
  renderOdds();
  renderGroups();
  renderRadar();
  renderIntel();
  renderHistory();
  $('#meta').textContent =
    `Engine artifacts generated ${CORE.generated}. ` +
    `Last live result ingest: ${CORE.last_refresh || 'pre-tournament'}.`;
}

const picker = $('#day-picker');
const today = new Date().toISOString().slice(0, 10);
if (today >= picker.min && today <= picker.max) picker.value = today;
picker.addEventListener('change', () => loadDay(picker.value));
$('#prev-day').addEventListener('click', () => stepDay(-1));
$('#next-day').addEventListener('click', () => stepDay(1));
function stepDay(delta) {
  const d = new Date(picker.value + 'T12:00:00Z');
  d.setUTCDate(d.getUTCDate() + delta);
  const v = d.toISOString().slice(0, 10);
  if (v >= picker.min && v <= picker.max) {
    picker.value = v;
    loadDay(v);
  }
}

loadCore().then(() => loadDay(picker.value));
