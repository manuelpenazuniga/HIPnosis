const PHASES = ['QUEUED', 'CLONING', 'SCANNING', 'PORTING', 'BUILD_LOOP', 'RUNNING', 'PARITY', 'REPORTING', 'DONE'];
const PHASE_COLORS = {
  QUEUED: 'bg-gray-600', CLONING: 'bg-blue-600', SCANNING: 'bg-cyan-600',
  PORTING: 'bg-purple-600', BUILD_LOOP: 'bg-yellow-600', RUNNING: 'bg-orange-600',
  PARITY: 'bg-green-600', REPORTING: 'bg-indigo-600', DONE: 'bg-red-600',
  DONE_PARTIAL: 'bg-red-500', FAILED: 'bg-red-800'
};

const state = {
  runId: '',
  events: [],
  lastIdx: -1,
  currentPhase: null,
  builds: [],
  wave64: [],
  fixes: [],
  classifies: {},
  verify: null,
  report: null,
  scan: null,
  polling: true,
  demoMode: false
};

function getRunId() {
  const params = new URLSearchParams(window.location.search);
  return params.get('run') || 'run_bsw01a2';
}

function setStatus(msg, isError = false) {
  const el = document.getElementById('status');
  el.textContent = msg;
  el.className = `mb-6 p-4 rounded-lg text-center ${isError ? 'bg-red-900 text-red-200' : 'bg-gray-800 text-gray-400'}`;
}

function showDashboard() {
  document.getElementById('status').style.display = 'none';
  document.getElementById('dashboard').style.display = 'block';
}

function renderTimeline() {
  const container = document.getElementById('timeline');
  container.innerHTML = '';
  const allPhases = [...PHASES, 'DONE_PARTIAL', 'FAILED'];
  const displayPhases = state.currentPhase === 'FAILED' ? [...PHASES, 'FAILED'] :
                        state.currentPhase === 'DONE_PARTIAL' ? [...PHASES, 'DONE_PARTIAL'] : PHASES;

  displayPhases.forEach(phase => {
    const el = document.createElement('div');
    const isActive = phase === state.currentPhase;
    const isPast = PHASES.indexOf(phase) < PHASES.indexOf(state.currentPhase) ||
                   (state.currentPhase === 'DONE' && phase !== 'FAILED' && phase !== 'DONE_PARTIAL');
    const color = PHASE_COLORS[phase] || 'bg-gray-600';

    el.className = `px-4 py-2 rounded-lg text-sm font-semibold transition-all ${
      isActive ? `${color} phase-active text-white ring-2 ring-white` :
      isPast ? `${color} text-white opacity-70` :
      'bg-gray-700 text-gray-500'
    }`;
    el.textContent = phase;
    container.appendChild(el);
  });
}

function renderErrors() {
  const container = document.getElementById('errors-chart');
  container.innerHTML = '';
  if (state.builds.length === 0) return;

  const maxErrors = Math.max(...state.builds.map(b => b.errors), 1);

  state.builds.forEach(build => {
    const row = document.createElement('div');
    row.className = 'flex items-center gap-4';

    const label = document.createElement('div');
    label.className = 'w-24 text-sm text-gray-400 font-mono';
    label.textContent = `Iter ${build.iteration}`;

    const barContainer = document.createElement('div');
    barContainer.className = 'flex-1 bg-gray-700 rounded-full h-8 relative';

    const bar = document.createElement('div');
    const pct = (build.errors / maxErrors) * 100;
    bar.className = `h-full rounded-full transition-all duration-500 ${
      build.errors === 0 ? 'bg-green-500' : 'bg-red-500'
    }`;
    bar.style.width = `${pct}%`;

    const count = document.createElement('span');
    count.className = 'absolute right-3 top-1/2 -translate-y-1/2 text-sm font-bold text-white';
    count.textContent = build.errors;

    barContainer.appendChild(bar);
    barContainer.appendChild(count);
    row.appendChild(label);
    row.appendChild(barContainer);
    container.appendChild(row);
  });
}

function renderEfficiency() {
  const container = document.getElementById('efficiency-stats');
  container.innerHTML = '';
  if (!state.report) return;

  const totalFixes = state.report.fixes_deterministic + state.report.fixes_local + state.report.fixes_remote;
  const localFixes = state.report.fixes_deterministic + state.report.fixes_local;
  const pctLocal = totalFixes > 0 ? Math.round((localFixes / totalFixes) * 100) : 0;

  const cards = [
    { label: '% Resolved Locally', value: `${pctLocal}%`, color: 'text-green-400' },
    { label: 'Tokens (Local)', value: state.report.tokens_local.toLocaleString(), color: 'text-cyan-400' },
    { label: 'Tokens (Remote)', value: state.report.tokens_remote.toLocaleString(), color: 'text-purple-400' }
  ];

  cards.forEach(card => {
    const el = document.createElement('div');
    el.className = 'bg-gray-700 rounded-lg p-6 text-center';
    el.innerHTML = `
      <div class="text-sm text-gray-400 mb-2">${card.label}</div>
      <div class="text-4xl font-bold ${card.color}">${card.value}</div>
    `;
    container.appendChild(el);
  });
}

function renderWave64() {
  const container = document.getElementById('wave64-table');
  container.innerHTML = '';
  if (state.wave64.length === 0) return;

  const table = document.createElement('table');
  table.className = 'w-full text-left';
  table.innerHTML = `
    <thead class="border-b border-gray-600">
      <tr>
        <th class="py-2 px-4 text-gray-400">File</th>
        <th class="py-2 px-4 text-gray-400">Line</th>
        <th class="py-2 px-4 text-gray-400">Pattern</th>
      </tr>
    </thead>
  `;

  const tbody = document.createElement('tbody');
  state.wave64.forEach(w => {
    const row = document.createElement('tr');
    row.className = 'border-b border-gray-700';
    row.innerHTML = `
      <td class="py-2 px-4 font-mono text-sm">${w.file}</td>
      <td class="py-2 px-4 font-mono text-sm">${w.line}</td>
      <td class="py-2 px-4"><span class="bg-yellow-600 text-white px-2 py-1 rounded text-xs font-bold">${w.pattern}</span></td>
    `;
    tbody.appendChild(row);
  });

  table.appendChild(tbody);
  container.appendChild(table);
}

function renderFixes() {
  const summaryEl = document.getElementById('fixes-summary');
  const tableEl = document.getElementById('fixes-table');
  summaryEl.innerHTML = '';
  tableEl.innerHTML = '';

  if (state.fixes.length === 0) return;

  const counts = { deterministic: 0, local: 0, remote: 0 };
  state.fixes.forEach(f => { counts[f.tier] = (counts[f.tier] || 0) + 1; });

  summaryEl.innerHTML = `
    <div class="flex gap-4 text-sm">
      <span class="bg-green-700 px-3 py-1 rounded">Deterministic: ${counts.deterministic}</span>
      <span class="bg-cyan-700 px-3 py-1 rounded">Local: ${counts.local}</span>
      <span class="bg-purple-700 px-3 py-1 rounded">Remote: ${counts.remote}</span>
    </div>
  `;

  const table = document.createElement('table');
  table.className = 'w-full text-left';
  table.innerHTML = `
    <thead class="border-b border-gray-600">
      <tr>
        <th class="py-2 px-4 text-gray-400">Class</th>
        <th class="py-2 px-4 text-gray-400">Tier</th>
        <th class="py-2 px-4 text-gray-400">Commit</th>
        <th class="py-2 px-4 text-gray-400">Delta</th>
      </tr>
    </thead>
  `;

  const tbody = document.createElement('tbody');
  state.fixes.forEach(f => {
    const klass = state.classifies[f.sig]?.klass || '?';
    const tierColor = f.tier === 'deterministic' ? 'bg-green-700' :
                      f.tier === 'local' ? 'bg-cyan-700' : 'bg-purple-700';
    const row = document.createElement('tr');
    row.className = 'border-b border-gray-700';
    row.innerHTML = `
      <td class="py-2 px-4 font-mono text-sm">${klass}</td>
      <td class="py-2 px-4"><span class="${tierColor} text-white px-2 py-1 rounded text-xs">${f.tier}</span></td>
      <td class="py-2 px-4 font-mono text-xs text-gray-400">${f.commit || '-'}</td>
      <td class="py-2 px-4 font-mono text-sm ${f.delta < 0 ? 'text-green-400' : 'text-red-400'}">${f.delta}</td>
    `;
    tbody.appendChild(row);
  });

  table.appendChild(tbody);
  tableEl.appendChild(table);
}

function renderVerdict() {
  const verdictEl = document.getElementById('verdict');
  const detailEl = document.getElementById('verdict-detail');

  if (!state.verify) {
    verdictEl.textContent = '...';
    verdictEl.className = 'text-center text-6xl font-bold py-8 text-gray-600';
    detailEl.textContent = '';
    return;
  }

  const colors = { PASS: 'text-green-400', FAIL: 'text-red-400', NO_ORACLE: 'text-yellow-400' };
  verdictEl.textContent = state.verify.verdict;
  verdictEl.className = `text-center text-6xl font-bold py-8 ${colors[state.verify.verdict] || 'text-gray-400'}`;
  detailEl.textContent = state.verify.detail || '';
}

function processEvent(ev) {
  switch (ev.ev) {
    case 'phase':
      state.currentPhase = ev.phase;
      renderTimeline();
      break;
    case 'scan':
      state.scan = ev;
      break;
    case 'wave64':
      state.wave64.push({ file: ev.file, line: ev.line, pattern: ev.pattern });
      renderWave64();
      break;
    case 'build':
      state.builds.push({ iteration: ev.iteration, errors: ev.errors, delta: ev.delta });
      renderErrors();
      break;
    case 'classify':
      state.classifies[ev.sig] = { klass: ev.klass, tier: ev.tier, confidence: ev.confidence };
      break;
    case 'fix':
      state.fixes.push({ sig: ev.sig, tier: ev.tier, applied: ev.applied, delta: ev.delta, commit: ev.commit, tokens: ev.tokens });
      renderFixes();
      break;
    case 'verify':
      state.verify = { verdict: ev.verdict, detail: ev.detail };
      renderVerdict();
      break;
    case 'report':
      state.report = ev;
      renderEfficiency();
      break;
    default:
      break;
  }
}

function processEvents(events) {
  events.forEach(ev => {
    if (ev._i > state.lastIdx) {
      state.lastIdx = ev._i;
      state.events.push(ev);
      processEvent(ev);
    }
  });
}

async function pollEvents() {
  if (!state.polling) return;

  try {
    const url = `/runs/${state.runId}/events?after=${state.lastIdx}`;
    const resp = await fetch(url);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const events = await resp.json();

    if (events.length > 0) {
      processEvents(events);
      showDashboard();
      setStatus('');
    }

    if (state.currentPhase === 'DONE' || state.currentPhase === 'FAILED' || state.currentPhase === 'DONE_PARTIAL') {
      state.polling = false;
    }
  } catch (err) {
    if (!state.demoMode) {
      console.warn('API unavailable, loading demo data:', err.message);
      await loadDemoData();
    }
    return;
  }

  if (state.polling) {
    setTimeout(pollEvents, 1000);
  }
}

async function loadDemoData() {
  state.demoMode = true;
  state.polling = false;

  try {
    const resp = await fetch('../fixtures/demo-run.jsonl');
    const text = await resp.text();
    const lines = text.trim().split('\n');
    const events = lines.map((line, i) => {
      const ev = JSON.parse(line);
      ev._i = i;
      return ev;
    });

    processEvents(events);
    showDashboard();
    setStatus('Demo mode (no API connection)');
  } catch (err) {
    console.error('Failed to load demo data:', err);
    setStatus('Failed to load demo data', true);
  }
}

function init() {
  state.runId = getRunId();
  document.getElementById('run-id').textContent = state.runId;

  renderTimeline();
  renderErrors();
  renderEfficiency();
  renderWave64();
  renderFixes();
  renderVerdict();

  pollEvents();
}

document.addEventListener('DOMContentLoaded', init);
