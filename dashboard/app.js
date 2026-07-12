const PHASES = ['QUEUED','CLONING','SCANNING','PORTING','BUILD_LOOP','RUNNING','PARITY','REPORTING','DONE'];
const PHASE_META = {
  QUEUED:       { label: 'Queued',      icon: '◎' },
  CLONING:      { label: 'Cloning',     icon: '⬇' },
  SCANNING:     { label: 'Scanning',    icon: '⊙' },
  PORTING:      { label: 'Porting',     icon: '⇄' },
  BUILD_LOOP:   { label: 'Build Loop',  icon: '⟳' },
  RUNNING:      { label: 'Running',     icon: '▶' },
  PARITY:       { label: 'Parity',      icon: '≡' },
  REPORTING:    { label: 'Reporting',   icon: '◉' },
  DONE:         { label: 'Done',        icon: '✓' },
  DONE_PARTIAL: { label: 'Partial',     icon: '◐' },
  FAILED:       { label: 'Failed',      icon: '✕' },
};

const WAVE64_SEV = {
  W01: { label: 'Correctness', color: 'red' },
  W02: { label: 'Correctness', color: 'red' },
  W03: { label: 'Correctness', color: 'red' },
  W04: { label: 'Suspicious',  color: 'amber' },
  W05: { label: 'Suspicious',  color: 'amber' },
  W06: { label: 'Suspicious',  color: 'amber' },
  W07: { label: 'Suspicious',  color: 'amber' },
};

// Decoder de jerga (audit H8): etiquetas fijas para tooltips, espejo de
// core/rules.yaml y core/wave64.py. Solo TEXTO descriptivo — los números
// siguen saliendo únicamente del backend (F-17).
const CLASS_NAMES = {
  E01: 'Leftover CUDA include (<cuda_runtime.h> not translated)',
  E02: 'Unconverted CUDA API call',
  E03: 'Unconverted CUDA type or handle',
  E04: 'Inline PTX assembly (NVIDIA-only)',
  E05: 'Warp intrinsic mismatch (32 vs 64 lanes)',
  E06: 'Texture / surface API',
  E07: 'Kernel launch syntax (<<<...>>>)',
  E08: 'Undefined symbol at link time',
  E09: 'HIP include not found',
  E10: 'Symbol / memcpy issue',
  E11: 'External library mismatch (cuBLAS, cuFFT, …)',
  E12: 'Wave64 runtime issue',
  E13: 'Build system (Makefile flags, nvcc remnants)',
  E99: 'Unknown — unclassified error',
};
const WAVE64_EXPL = {
  W01: '32-bit mask — on wave64 the mask/result are 64-bit',
  W02: 'Ballot result truncated to 32 bits on wave64',
  W03: 'Needs __popcll over a 64-bit mask',
  W04: 'Hardcoded width 32 — AMD wavefront is 64',
  W05: 'Lane arithmetic assumes a 32-wide warp (&31, >>5)',
  W06: 'Cooperative-groups partition of NVIDIA warp size',
  W07: 'warpSize must be queried at runtime in HIP, not fixed at 32',
};
const TIER_EXPL = {
  deterministic: 'Fixed by the rule table — no LLM involved',
  local: 'Fixed by Gemma 3 27B running locally on the MI300X ($0 API)',
  remote: 'Fixed by the cloud LLM (Fireworks) — hard cases only',
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
  failed: null,
  loopDone: null,
  firstTs: null,
  lastTs: null,
  certOpen: false,
  scan: null,
  runMeta: null,
  polling: true,
  demoMode: false,
  apiAlive: false,
  retryDelay: 1000,
  mode: '',
  diffFetched: false,
  certFetched: false,
  certRaw: '',
  attestation: null,
  attestFetched: false,
  diffText: '',
};

function getRunId() {
  return new URLSearchParams(window.location.search).get('run') || 'run_bsw01a2';
}

function $(id) { return document.getElementById(id); }

function showApp() {
  $('loading-screen').classList.add('hidden');
  $('app').classList.remove('hidden');
}

function revealSection(id) {
  const el = $(id);
  if (el && !el.classList.contains('visible')) {
    el.classList.add('visible');
  }
}

function updateStatusBadge(phase) {
  const badge = $('status-badge');
  if (!phase) return;
  const map = {
    DONE:         { cls: 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30', label: 'DONE' },
    DONE_PARTIAL: { cls: 'bg-amber-500/15 text-amber-400 border border-amber-500/30', label: 'DONE (PARTIAL)' },
    FAILED:       { cls: 'bg-red-500/15 text-red-400 border border-red-500/30', label: 'FAILED' },
    REPORTING:    { cls: 'bg-indigo-500/15 text-indigo-400 border border-indigo-500/30', label: 'REPORTING' },
    PARITY:       { cls: 'bg-cyan-500/15 text-cyan-400 border border-cyan-500/30', label: 'PARITY' },
    RUNNING:      { cls: 'bg-orange-500/15 text-orange-400 border border-orange-500/30', label: 'RUNNING' },
    BUILD_LOOP:   { cls: 'bg-yellow-500/15 text-yellow-400 border border-yellow-500/30 pulse-active', label: 'BUILD LOOP' },
    PORTING:      { cls: 'bg-purple-500/15 text-purple-400 border border-purple-500/30 pulse-active', label: 'PORTING' },
    SCANNING:     { cls: 'bg-cyan-500/15 text-cyan-400 border border-cyan-500/30 pulse-active', label: 'SCANNING' },
    CLONING:      { cls: 'bg-blue-500/15 text-blue-400 border border-blue-500/30 pulse-active', label: 'CLONING' },
    QUEUED:       { cls: 'bg-gray-500/15 text-gray-400 border border-gray-500/30', label: 'QUEUED' },
  };
  const m = map[phase] || map.QUEUED;
  badge.className = `px-4 py-2 rounded-full text-sm font-bold ${m.cls}`;
  badge.textContent = m.label;
  document.title = `HIPnosis · ${m.label}`;
}

function renderScanStrip() {
  // H9: el contexto del repo (evento scan + run_meta) — antes se descartaba.
  const el = $('scan-strip');
  const s = state.scan;
  if (!s) return;
  const apiCalls = s.api_calls ? Object.values(s.api_calls).reduce((a, b) => a + b, 0) : null;
  const diffCls = { easy: 'text-emerald-400', medium: 'text-amber-400', hard: 'text-red-400' }[s.difficulty] || 'text-gray-300';
  const item = (label, value, valueCls = 'text-gray-200') =>
    `<span class="flex items-baseline gap-1.5"><span class="text-[10px] uppercase tracking-wider text-gray-500">${label}</span><span class="font-mono text-sm font-semibold ${valueCls}">${escapeHtml(String(value))}</span></span>`;
  let html = '';
  if (s.files_cuda != null) html += item('CUDA files', s.files_cuda);
  if (s.loc_kernels != null) html += item('Kernel LOC', s.loc_kernels);
  if (apiCalls != null) html += item('CUDA API calls', apiCalls);
  if (s.build_system) html += item('Build', s.build_system);
  if (s.difficulty) html += item('Difficulty', s.difficulty, diffCls);
  if (state.runMeta && state.runMeta.gpu_arch) html += item('Target GPU', state.runMeta.gpu_arch, 'text-amd');
  el.innerHTML = html;
  el.classList.remove('hidden');
}

function renderElapsed() {
  // H11: duración del run según los timestamps del trace (honesto en replay:
  // muestra la duración GRABADA, no la del playback).
  if (!state.firstTs || !state.lastTs) return;
  const secs = Math.max(0, Math.round((state.lastTs - state.firstTs) / 1000));
  const text = secs >= 60 ? `${Math.floor(secs / 60)}m ${secs % 60}s` : `${secs}s`;
  $('elapsed').textContent = `run time ${text}`;
}

function renderTimeline() {
  const container = $('timeline');
  container.innerHTML = '';
  const displayPhases = (state.currentPhase === 'FAILED' || state.currentPhase === 'DONE_PARTIAL')
    ? [...PHASES, state.currentPhase] : PHASES;

  displayPhases.forEach((phase, i) => {
    const meta = PHASE_META[phase] || { label: phase, icon: '·' };
    const isActive = phase === state.currentPhase;
    const isPast = PHASES.indexOf(phase) < PHASES.indexOf(state.currentPhase) ||
                   (state.currentPhase === 'DONE' && phase !== 'FAILED' && phase !== 'DONE_PARTIAL');
    const isTerminalFail = phase === 'FAILED';
    const isTerminalPartial = phase === 'DONE_PARTIAL';

    const el = document.createElement('div');
    let cls = 'px-3 py-2 rounded-xl text-xs font-semibold transition-[background-color,color,box-shadow] duration-300 flex items-center gap-1.5 ';
    if (isActive) {
      if (isTerminalFail) cls += 'bg-red-500/20 text-red-400 border border-red-500/40 pulse-active';
      else if (isTerminalPartial) cls += 'bg-amber-500/20 text-amber-400 border border-amber-500/40 pulse-active';
      else cls += 'bg-blue-500/20 text-blue-400 border border-blue-500/40 pulse-active';
    } else if (isPast) {
      cls += 'bg-emerald-500/10 text-emerald-500/70 border border-emerald-500/10';
    } else {
      cls += 'bg-surface-700 text-gray-600 border border-transparent';
    }
    el.className = cls;
    el.innerHTML = `<span class="text-sm">${meta.icon}</span><span>${meta.label}</span>`;
    container.appendChild(el);
  });
  revealSection('timeline-section');
}

// Count-up interrumpible (Emil std 6): anima del valor MOSTRADO al nuevo, y
// retargetea si llega otro valor a mitad (drip-feed). Respeta reduced-motion
// (salta al valor). Solo dígitos GPU-free: cambia textContent, no layout.
const _count = new WeakMap();
function animateNumber(el, to, prefix = '') {
  const prev = _count.get(el);
  if (prev) cancelAnimationFrame(prev);
  const from = (() => { const n = parseFloat(String(el.textContent).replace(/[^0-9.\-]/g, '')); return Number.isFinite(n) ? n : 0; })();
  const set = v => { el.textContent = prefix + Math.round(v); };
  if (from === to || window.matchMedia('(prefers-reduced-motion: reduce)').matches) { set(to); return; }
  const t0 = performance.now(), dur = 650, easeOut = t => 1 - Math.pow(1 - t, 3);
  const step = now => {
    const p = Math.min(1, (now - t0) / dur);
    set(from + (to - from) * easeOut(p));
    if (p < 1) _count.set(el, requestAnimationFrame(step)); else { set(to); _count.delete(el); }
  };
  _count.set(el, requestAnimationFrame(step));
}

function renderHeroMetrics() {
  const r = state.report;
  const initialErrors = r ? r.errors_initial : (state.builds.length ? state.builds[0].errors : null);
  const currentErrors = state.builds.length ? state.builds[state.builds.length - 1].errors : null;

  if (initialErrors !== null && currentErrors !== null) {
    // "Errors Resolved" = resueltos (inicial - actuales), no el conteo inicial (audit H6).
    animateNumber($('metric-errors'), initialErrors - currentErrors);
    $('metric-errors-sub').textContent = `${initialErrors} → ${currentErrors}`;
    renderSparkline();
  }

  if (r) {
    const totalFixes = r.fixes_deterministic + r.fixes_local + r.fixes_remote;
    const localFixes = r.fixes_deterministic + r.fixes_local;
    const pct = totalFixes > 0 ? Math.round((localFixes / totalFixes) * 100) : 0;
    animateNumber($('metric-local'), pct);

    // H7/F-17: el costo viene CALCULADO del backend (evento report). El front
    // no conoce precios; sin el campo, solo el caso trivial 0 tokens = $0.
    const cost = (typeof r.cost_remote_usd === 'number') ? r.cost_remote_usd
               : (r.tokens_remote === 0 ? 0 : null);
    $('metric-cost').textContent = cost === null ? '—' : `$${cost.toFixed(2)}`;

    animateNumber($('metric-wave64'), r.wave64_findings || state.wave64.length);
  } else {
    animateNumber($('metric-wave64'), state.wave64.length);
  }
}

function renderSparkline() {
  if (state.builds.length < 2) return;
  const svg = $('sparkline-errors');
  const errors = state.builds.map(b => b.errors);
  const max = Math.max(...errors, 1);
  const w = 64, h = 32, pad = 2;
  const step = (w - pad * 2) / Math.max(errors.length - 1, 1);
  const points = errors.map((e, i) => {
    const x = pad + i * step;
    const y = h - pad - (e / max) * (h - pad * 2);
    return `${x},${y}`;
  });
  svg.innerHTML = `
    <polyline points="${points.join(' ')}" fill="none" stroke="#ef4444" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="sparkline-path" opacity="0.8"/>
    <circle cx="${points[points.length-1].split(',')[0]}" cy="${points[points.length-1].split(',')[1]}" r="2.5" fill="#22c55e"/>
  `;
}

function renderWave64() {
  const container = $('wave64-table');
  if (state.wave64.length === 0) {
    container.innerHTML = '<p class="text-gray-600 text-sm py-4">No wave64 findings.</p>';
    return;
  }
  let html = `<table class="w-full text-left text-sm">
    <thead><tr class="border-b border-white/5">
      <th class="py-2 px-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">File</th>
      <th class="py-2 px-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Line</th>
      <th class="py-2 px-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Pattern</th>
      <th class="py-2 px-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Severity</th>
    </tr></thead><tbody>`;
  state.wave64.forEach(w => {
    const sev = WAVE64_SEV[w.pattern] || { label: 'Info', color: 'gray' };
    const sevCls = sev.color === 'red' ? 'bg-red-500/10 text-red-400 border-red-500/20' :
                   sev.color === 'amber' ? 'bg-amber-500/10 text-amber-400 border-amber-500/20' :
                   'bg-gray-500/10 text-gray-400 border-gray-500/20';
    const patCls = 'bg-amber-500/10 text-amber-300 border border-amber-500/20';
    const expl = WAVE64_EXPL[w.pattern] || '';
    html += `<tr class="border-b border-white/[0.03] hover:bg-white/[0.02] transition-colors">
      <td class="py-2.5 px-3 font-mono text-gray-300">${escapeHtml(String(w.file))}</td>
      <td class="py-2.5 px-3 font-mono text-gray-400">${escapeHtml(String(w.line))}</td>
      <td class="py-2.5 px-3"><span class="px-2 py-0.5 rounded-md text-xs font-bold border cursor-help ${patCls}" title="${escapeHtml(expl)}">${escapeHtml(String(w.pattern))}</span></td>
      <td class="py-2.5 px-3"><span class="px-2 py-0.5 rounded-md text-xs font-semibold border ${sevCls}">${sev.label}</span></td>
    </tr>`;
  });
  html += '</tbody></table>';
  container.innerHTML = html;
  revealSection('wave64-section');
}

function renderDiff(text) {
  const container = $('diff-container');
  if (!text) {
    container.innerHTML = '<p class="text-gray-600 text-center py-8">No diff available.</p>';
    return;
  }
  const lines = text.split('\n');
  let html = '';
  lines.forEach(line => {
    let cls = 'diff-line';
    if (line.startsWith('+++') || line.startsWith('---') || line.startsWith('diff ') || line.startsWith('index ')) {
      cls += ' diff-meta';
    } else if (line.startsWith('@@')) {
      cls += ' diff-hunk';
    } else if (line.startsWith('+')) {
      cls += ' diff-add';
    } else if (line.startsWith('-')) {
      cls += ' diff-del';
    } else {
      cls += ' text-gray-500';
    }
    html += `<div class="${cls}">${escapeHtml(line)}</div>`;
  });
  container.innerHTML = html;
  revealSection('diff-section');
}

function renderBurndown() {
  const container = $('burndown-chart');
  if (state.builds.length === 0) return;
  const maxErrors = Math.max(...state.builds.map(b => b.errors), 1);
  let html = '';
  state.builds.forEach((b, i) => {
    const pct = (b.errors / maxErrors) * 100;
    const isZero = b.errors === 0;
    const barColor = isZero ? 'bg-emerald-500' : 'bg-gradient-to-r from-amd to-red-400';
    const delay = i * 100;
    html += `<div class="flex items-center gap-4 group">
      <div class="w-16 text-xs font-mono text-gray-500 text-right flex-shrink-0">iter ${b.iteration}</div>
      <div class="flex-1 h-8 bg-surface-600 rounded-lg relative overflow-hidden">
        <div class="${barColor} h-full rounded-lg bar-animate transition-[width] duration-500" style="width:${Math.max(pct, 2)}%; animation-delay:${delay}ms"></div>
        <span class="absolute right-3 top-1/2 -translate-y-1/2 text-xs font-bold ${isZero ? 'text-emerald-400' : 'text-white'}">${b.errors}</span>
      </div>
      <div class="w-12 text-xs font-mono text-gray-600 flex-shrink-0">${b.delta > 0 ? '+' : ''}${b.delta}</div>
    </div>`;
  });
  container.innerHTML = html;
  revealSection('burndown-section');
}

function renderFixes() {
  const tableEl = $('fixes-table');
  const countersEl = $('fixes-counters');
  const tokensBar = $('fixes-tokens-bar');

  if (state.fixes.length === 0) return;

  const counts = { deterministic: 0, local: 0, remote: 0 };
  state.fixes.forEach(f => { counts[f.tier] = (counts[f.tier] || 0) + 1; });

  const tierBadge = (tier) => {
    const map = {
      deterministic: 'bg-gray-500/10 text-gray-400 border-gray-500/20',
      local:         'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
      remote:        'bg-blue-500/10 text-blue-400 border-blue-500/20',
    };
    const expl = TIER_EXPL[tier] || '';
    return `<span class="px-2 py-0.5 rounded-md text-xs font-semibold border cursor-help ${map[tier] || map.deterministic}" title="${escapeHtml(expl)}">${escapeHtml(String(tier))}</span>`;
  };

  countersEl.innerHTML = `
    <span class="px-2.5 py-1 rounded-lg text-xs font-bold bg-gray-500/10 text-gray-400 border border-gray-500/20">Deterministic: ${counts.deterministic}</span>
    <span class="px-2.5 py-1 rounded-lg text-xs font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">Local: ${counts.local}</span>
    <span class="px-2.5 py-1 rounded-lg text-xs font-bold bg-blue-500/10 text-blue-400 border border-blue-500/20">Remote: ${counts.remote}</span>
  `;

  if (state.report) {
    tokensBar.classList.remove('hidden');
    const total = state.report.tokens_local + state.report.tokens_remote || 1;
    const localPct = (state.report.tokens_local / total) * 100;
    const remotePct = (state.report.tokens_remote / total) * 100;
    $('tokens-local-bar').style.width = `${localPct}%`;
    $('tokens-remote-bar').style.width = `${remotePct}%`;
  }

  let html = `<table class="w-full text-left text-sm">
    <thead><tr class="border-b border-white/5">
      <th class="py-2 px-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Class</th>
      <th class="py-2 px-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Tier</th>
      <th class="py-2 px-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Commit</th>
      <th class="py-2 px-3 text-xs font-semibold text-gray-500 uppercase tracking-wider text-right cursor-help" title="Change in compiler error count after this fix (negative = errors removed)">Δ errors</th>
    </tr></thead><tbody>`;
  state.fixes.forEach(f => {
    const klass = f.klass || state.classifies[f.sig]?.klass || '?';
    const klassExpl = CLASS_NAMES[klass] || '';
    const commitShort = f.commit ? f.commit.substring(0, 7) : '—';
    const deltaColor = f.delta <= 0 ? 'text-emerald-400' : 'text-red-400';
    html += `<tr class="border-b border-white/[0.03] hover:bg-white/[0.02] transition-colors">
      <td class="py-2.5 px-3 font-mono text-gray-300 cursor-help" title="${escapeHtml(klassExpl)}">${escapeHtml(String(klass))}</td>
      <td class="py-2.5 px-3">${tierBadge(f.tier)}</td>
      <td class="py-2.5 px-3 font-mono text-xs text-gray-500">${escapeHtml(String(commitShort))}</td>
      <td class="py-2.5 px-3 font-mono text-xs text-right ${deltaColor}">${f.delta > 0 ? '+' : ''}${escapeHtml(String(f.delta))}</td>
    </tr>`;
  });
  html += '</tbody></table>';
  tableEl.innerHTML = html;
  revealSection('fixes-section');
}

function renderResultBanner() {
  // QW1: el "so what" arriba. Se puebla cuando el run llega a un estado final,
  // con el veredicto + los números que importan (todo desde state, F-17).
  const done = ['DONE', 'DONE_PARTIAL', 'FAILED'].includes(state.currentPhase);
  if (!done && !state.verify) return;
  const card = $('result-card');

  const r = state.report;
  const initial = r ? r.errors_initial : (state.builds[0]?.errors ?? null);
  const current = state.builds.length ? state.builds[state.builds.length - 1].errors : null;
  const wave = r ? (r.wave64_findings || state.wave64.length) : state.wave64.length;
  const totalFixes = r ? r.fixes_deterministic + r.fixes_local + r.fixes_remote : 0;
  const localPct = r && totalFixes > 0
    ? Math.round(((r.fixes_deterministic + r.fixes_local) / totalFixes) * 100) : null;

  let verdict, vcls, border, bg;
  if (state.failed) {
    verdict = 'FAILED'; vcls = 'text-red-400'; border = 'border-red-500/40'; bg = 'bg-red-500/5';
  } else if (state.loopDone && state.loopDone.success === false) {
    verdict = 'DONE · PARTIAL'; vcls = 'text-amber-400'; border = 'border-amber-500/40'; bg = 'bg-amber-500/5';
  } else if (state.verify && state.verify.verdict === 'PASS') {
    verdict = 'PASS'; vcls = 'text-emerald-400'; border = 'border-emerald-500/40'; bg = 'bg-emerald-500/5';
  } else if (state.verify && state.verify.verdict === 'FAIL') {
    verdict = 'FAIL'; vcls = 'text-red-400'; border = 'border-red-500/40'; bg = 'bg-red-500/5';
  } else {
    verdict = state.verify ? state.verify.verdict : 'DONE'; vcls = 'text-gray-300'; border = 'border-white/10'; bg = 'bg-white/5';
  }

  const stat = (label, value, cls = 'text-white') =>
    `<div class="flex flex-col"><span class="text-[10px] uppercase tracking-wider text-gray-500">${label}</span><span class="text-lg font-bold ${cls} font-mono">${value}</span></div>`;
  let stats = '';
  if (initial !== null && current !== null) stats += stat('Build errors', `${initial} → ${current}`, current === 0 ? 'text-emerald-400' : 'text-white');
  if (wave) stats += stat('Wave64 caught', wave, 'text-amber-400');
  if (localPct !== null) stats += stat('Resolved locally', `${localPct}%`, 'text-emerald-400');
  if (state.attestation) stats += stat('Passport', 'verifiable', 'text-emerald-400');

  card.className = `rounded-2xl p-5 sm:p-6 border ${border} ${bg} flex flex-col sm:flex-row sm:items-center gap-x-8 gap-y-4`;
  card.innerHTML = `
    <div class="flex items-center gap-4 sm:pr-8 sm:border-r border-white/10">
      <span class="text-4xl sm:text-5xl font-black ${vcls}">${escapeHtml(verdict)}</span>
    </div>
    <div class="flex flex-wrap items-center gap-x-8 gap-y-3">${stats}</div>`;
  $('result-banner').classList.remove('hidden');
  revealSection('result-banner');
}

function renderVerdict() {
  const el = $('verdict');
  const detail = $('verdict-detail');
  if (!state.verify) return;

  const map = {
    PASS:       { cls: 'text-emerald-400', glow: 'drop-shadow(0 0 30px rgba(34,197,94,0.3))' },
    FAIL:       { cls: 'text-red-400', glow: 'drop-shadow(0 0 30px rgba(239,68,68,0.3))' },
    NO_ORACLE:  { cls: 'text-amber-400', glow: 'drop-shadow(0 0 30px rgba(245,158,11,0.3))' },
  };
  const m = map[state.verify.verdict] || map.NO_ORACLE;
  el.className = `text-7xl sm:text-8xl font-black py-4 ${m.cls}`;
  el.style.filter = m.glow;
  el.textContent = state.verify.verdict;
  let detailText = state.verify.detail || '';
  if (state.verify.verdict === 'NO_ORACLE') {
    // H8: NO_ORACLE es jerga interna — explicarla siempre.
    const expl = 'No test oracle available for this repo — the build was verified, numerical parity could not be checked.';
    detailText = detailText ? `${expl} (${detailText})` : expl;
  }
  detail.textContent = detailText;
  revealSection('verdict-section');
  renderResultBanner();
}

function renderOutcome() {
  // H9: la causa de un final no-verde, visible — no enterrada en el trace.
  const card = $('outcome-card');
  const needsHuman = state.loopDone && Array.isArray(state.loopDone.needs_human)
    ? state.loopDone.needs_human : [];

  if (state.failed) {
    $('outcome-section').classList.remove('hidden');
    card.className = 'glass rounded-2xl p-6 border-l-4 border-l-red-500';
    card.innerHTML = `
      <h2 class="text-lg font-bold text-red-400 mb-2">Why this run failed</h2>
      <p class="text-sm text-gray-300 leading-relaxed font-mono">${escapeHtml(state.failed.reason || 'unknown error')}</p>
      <p class="text-xs text-gray-500 mt-2">${escapeHtml(state.failed.exc_type || '')} — full detail in the run trace.</p>`;
    revealSection('outcome-section');
    return;
  }
  if (needsHuman.length > 0) {
    $('outcome-section').classList.remove('hidden');
    const items = needsHuman.map(s =>
      `<li class="font-mono text-xs text-gray-300 py-1 px-2 bg-white/5 rounded-md">${escapeHtml(String(s))}</li>`).join('');
    card.className = 'glass rounded-2xl p-6 border-l-4 border-l-amber-500';
    card.innerHTML = `
      <h2 class="text-lg font-bold text-amber-300 mb-1">Needs human attention</h2>
      <p class="text-sm text-gray-400 mb-3">HIPnosis could not resolve ${needsHuman.length === 1 ? 'this error group' : `these ${needsHuman.length} error groups`} automatically — they are listed honestly in the certificate instead of being hidden.</p>
      <ul class="space-y-1">${items}</ul>`;
    revealSection('outcome-section');
  }
}

function renderCertificate(md) {
  if (!md) return;
  state.certRaw = md;
  const content = $('cert-content');
  const toggle = $('cert-toggle');
  const downloadBtn = $('cert-download-btn');

  try {
    content.innerHTML = marked.parse(md);
  } catch (e) {
    content.innerHTML = `<pre class="text-sm text-gray-400 whitespace-pre-wrap">${escapeHtml(md)}</pre>`;
  }

  toggle.classList.remove('hidden');
  downloadBtn.classList.remove('hidden');
  // H14: el certificado es "the deliverable" — llega expandido, no escondido.
  state.certOpen = true;
  applyCertToggle();
  revealSection('certificate-section');
}

function escapeHtml(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// Deploy estático (Vercel/Pages, sin backend): cuando los endpoints /runs/*
// no existen, caemos a los fixtures bundleados. Es EL MISMO artefacto que el
// backend real serviría en modo replay — el badge sigue diciendo "synthetic
// demo" y el passport igual verifica (hash del demo-diff commiteado).
async function fetchStaticFallback(file) {
  try {
    const resp = await fetch(`../fixtures/${file}`);
    return resp.ok ? resp : null;
  } catch (e) { return null; }
}

async function fetchDiff() {
  if (state.diffFetched) return;
  state.diffFetched = true;
  try {
    let resp = await fetch(`/runs/${state.runId}/diff`);
    if (resp.ok) {
      state.diffText = (await resp.json()).diff || '';
      renderDiff(state.diffText);
      return;
    }
  } catch (e) { /* cae al fixture */ }
  const fb = await fetchStaticFallback('demo-diff.txt');
  if (fb) { state.diffText = await fb.text(); renderDiff(state.diffText); }
}

// --- Port Passport (wow #2): verificación de hashes client-side --------------
async function sha256Hex(text) {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2, '0')).join('');
}

function setPassportBadge(kind) {
  const el = $('passport-badge');
  const map = {
    verified: { cls: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/40', label: '● PASSPORT VERIFIED' },
    tampered: { cls: 'bg-red-500/15 text-red-400 border-red-500/40', label: '✕ TAMPERED' },
    pending:  { cls: 'bg-gray-500/15 text-gray-400 border-gray-500/30', label: '… verifying' },
    nodiff:   { cls: 'bg-amber-500/15 text-amber-400 border-amber-500/30', label: 'diff unavailable' },
  };
  const m = map[kind] || map.pending;
  el.className = `px-3 py-1.5 rounded-lg text-xs font-bold border ${m.cls}`;
  el.textContent = m.label;
}

async function verifyPassport(diffOverride) {
  const att = state.attestation;
  if (!att) return;
  const declared = att.predicate?.materials?.diff?.digest;
  const msg = $('passport-verify-msg');
  if (!declared) { setPassportBadge('nodiff'); return; }
  setPassportBadge('pending');
  // La verificación obtiene el diff DIRECTO del endpoint (la fuente que se
  // atesta) para no depender del orden de carga; el tamper demo pasa override.
  let diff = diffOverride;
  if (typeof diff !== 'string') {
    diff = null;
    try {
      const resp = await fetch(`/runs/${state.runId}/diff`);
      if (resp.ok) diff = (await resp.json()).diff || '';
    } catch (e) { /* cae al fixture */ }
    if (diff === null) {
      const fb = await fetchStaticFallback('demo-diff.txt');
      diff = fb ? await fb.text() : state.diffText;
    }
    state.diffText = diff;
  }
  const actual = await sha256Hex(diff);
  if (actual === declared) {
    setPassportBadge('verified');
    msg.textContent = 'recomputed sha256(diff) matches the attestation';
    msg.className = 'text-xs text-emerald-500';
  } else {
    setPassportBadge('tampered');
    msg.textContent = `hash mismatch — declared …${declared.slice(-12)}, got …${actual.slice(-12)}`;
    msg.className = 'text-xs text-red-400';
  }
}

function renderPassport() {
  const att = state.attestation;
  if (!att) return;
  const p = att.predicate || {};
  const short = (s) => (s && s.length > 20 ? s.slice(0, 10) + '…' + s.slice(-6) : (s || '—'));
  const row = (label, value, mono = true) =>
    `<div class="flex items-baseline gap-2 min-w-0">
       <span class="text-[10px] uppercase tracking-wider text-gray-500 flex-shrink-0">${label}</span>
       <span class="${mono ? 'font-mono' : ''} text-gray-300 truncate" title="${escapeHtml(String(value))}">${escapeHtml(String(value))}</span>
     </div>`;
  const r = p.result || {};
  const fields = [
    row('Source commit', short(p.source?.commit)),
    row('Final commit', short(p.port?.final_commit)),
    row('Diff digest', 'sha256:' + short(p.materials?.diff?.digest)),
    row('Cert digest', 'sha256:' + short(p.materials?.certificate?.digest)),
    row('Builder', p.builder?.id),
    row('GPU / mode', `${p.environment?.gpu_arch || '—'} · ${p.environment?.oracle_mode || '—'}`),
    row('Verdict', `${r.verdict || '—'} (${r.errors_initial ?? '?'} → ${r.errors_final ?? '?'} errors)`),
    row('Provenance', p.provenance_level || 'SLSA-L1', false),
  ].join('');
  $('passport-fields').innerHTML = fields;
  $('passport-section').classList.remove('hidden');
  revealSection('passport-section');
  verifyPassport();
  renderResultBanner();   // suma el stat "Passport verifiable" al banner superior
}

async function fetchAttestation() {
  if (state.attestFetched) return;
  state.attestFetched = true;
  let att = null;
  try {
    const resp = await fetch(`/runs/${state.runId}/attestation`);
    if (resp.ok) att = (await resp.json()).attestation;
  } catch (e) { /* cae al fixture */ }
  if (!att) {
    const fb = await fetchStaticFallback('demo-attestation.jsonl');
    if (fb) { try { att = JSON.parse((await fb.text()).trim().split('\n')[0]); } catch (e) { /* */ } }
  }
  if (att) {
    state.attestation = att;
    await fetchDiff();   // el diff debe estar cargado para verificar
    renderPassport();
  }
}

async function fetchCertificate() {
  if (state.certFetched) return;
  state.certFetched = true;
  try {
    const resp = await fetch(`/runs/${state.runId}/certificate`);
    if (resp.ok) { renderCertificate((await resp.json()).markdown || ''); return; }
  } catch (e) { /* cae al fixture */ }
  const fb = await fetchStaticFallback('demo-certificate.md');
  if (fb) renderCertificate(await fb.text());
}

function processEvent(ev) {
  switch (ev.ev) {
    case 'phase':
      state.currentPhase = ev.phase;
      updateStatusBadge(ev.phase);
      renderTimeline();
      if (ev.phase === 'REPORTING' || ev.phase === 'DONE' || ev.phase === 'DONE_PARTIAL') {
        fetchDiff();
        fetchCertificate();
      }
      break;
    case 'run_meta':
      state.runMeta = ev;
      renderScanStrip();
      renderModeBadge();   // la procedencia (recorded vs synthetic) vive en el trace
      break;
    case 'scan':
      state.scan = ev;
      renderScanStrip();
      break;
    case 'wave64':
      state.wave64.push({ file: ev.file, line: ev.line, pattern: ev.pattern });
      renderWave64();
      renderHeroMetrics();
      break;
    case 'build':
      state.builds.push({ iteration: ev.iteration, errors: ev.errors, delta: ev.delta });
      renderBurndown();
      renderHeroMetrics();
      break;
    case 'classify':
      state.classifies[ev.sig] = { klass: ev.klass, tier: ev.tier, confidence: ev.confidence };
      break;
    case 'fix':
      state.fixes.push({ sig: ev.sig, klass: ev.klass, tier: ev.tier, applied: ev.applied, delta: ev.delta, commit: ev.commit, tokens: ev.tokens });
      renderFixes();
      break;
    case 'failed':
      state.failed = { reason: ev.reason, exc_type: ev.exc_type };
      renderOutcome();
      renderResultBanner();
      break;
    case 'build_loop.done':
      state.loopDone = ev;
      renderOutcome();
      break;
    case 'verify':
      state.verify = { verdict: ev.verdict, detail: ev.detail };
      renderVerdict();
      break;
    case 'report':
      state.report = ev;
      renderHeroMetrics();
      renderFixes();
      renderResultBanner();
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
      if (ev.ts) {
        const t = Date.parse(ev.ts);
        if (!Number.isNaN(t)) {
          if (!state.firstTs) state.firstTs = t;
          state.lastTs = t;
        }
      }
      processEvent(ev);
    }
  });
  renderElapsed();
}

function setConn(kind, text) {
  const el = $('conn');
  const colors = {
    live: 'text-emerald-500',
    reconnecting: 'text-amber-400',
    done: 'text-gray-500',
    error: 'text-red-400',
  };
  el.className = `text-[10px] mt-1 text-right ${colors[kind] || 'text-gray-600'}`;
  el.innerHTML = kind === 'live'
    ? '<span class="inline-block w-1.5 h-1.5 rounded-full bg-emerald-500 pulse-dot mr-1 align-middle"></span>live'
    : escapeHtml(text || '');
}

async function pollEvents() {
  if (!state.polling) return;
  try {
    const url = `/runs/${state.runId}/events?after=${state.lastIdx}`;
    const resp = await fetch(url);
    if (resp.status === 404) {
      // 404 con API viva = run desconocido: decirlo y parar. 404 sin API
      // (dashboard servido estático, p.ej. http.server) = caso demo.
      if (!state.apiAlive && !state.demoMode && state.events.length === 0) {
        await loadDemoData();
        return;
      }
      state.polling = false;
      setConn('error', 'run not found');
      const msg = $('newrun-msg');
      msg.textContent = `Run "${state.runId}" not found — start a new port above.`;
      msg.className = 'text-xs mt-2 px-2 text-amber-400';
      return;
    }
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const events = await resp.json();
    state.retryDelay = 1000;
    setConn('live');
    if (events.length > 0) {
      processEvents(events);
    }
    if (['DONE','FAILED','DONE_PARTIAL'].includes(state.currentPhase)) {
      state.polling = false;
      setConn('done', 'run finished');
      fetchDiff();
      fetchCertificate();
      fetchAttestation().then(scrollToHash);
      return;
    }
  } catch (err) {
    // Audit H1: JAMÁS degradar a datos demo un run cuya API ya vimos viva.
    // Fixtures solo como landing si la API NUNCA respondió y no hay eventos;
    // en cualquier otro caso, reintentar con backoff y decirlo.
    if (!state.demoMode && !state.apiAlive && state.events.length === 0) {
      await loadDemoData();
      return;
    }
    setConn('reconnecting', 'connection lost — retrying…');
    state.retryDelay = Math.min((state.retryDelay || 1000) * 2, 5000);
  }
  setTimeout(pollEvents, state.retryDelay || 1000);
}

async function loadDemoData() {
  state.demoMode = true;
  state.polling = false;
  // Dos casos honestos (audit H1):
  //  - apiAlive: había un backend vivo y se cayó → "offline fixtures" (degradado).
  //  - sin backend (deploy estático Vercel/Pages, por diseño) → replay
  //    intencional del run grabado; el badge lo deriva del trace (synthetic).
  if (state.apiAlive) {
    renderModeBadge('demo');
    setConn('done', 'demo playback — orchestrator unreachable');
  } else {
    state.mode = 'replay';   // el trace (oracle_mode=mock) → "REPLAY · synthetic demo"
    setConn('done', 'replay — recorded run');
    // Sitio estático: el "New port" no puede correr repos (no hay backend).
    // Ajustamos la nota para que quede claro de entrada.
    const note = $('newrun-note');
    if (note) note.innerHTML = 'Hosted demo — this replays a recorded run of <b class="text-gray-400">bsw-cuda</b>. To port your own repository, run HIPnosis locally with a GPU (see the README).';
  }
  try {
    const resp = await fetch('../fixtures/demo-run.jsonl');
    if (!resp.ok) throw new Error('demo not found');
    const text = await resp.text();
    const lines = text.trim().split('\n');
    const events = lines.map((line, i) => {
      const ev = JSON.parse(line);
      ev._i = i;
      return ev;
    });
    showApp();
    // Deep-link (#wave64-section, #passport-section desde el onboarding): el
    // usuario quiere VER esa sección, no esperar el replay — renderizamos todo
    // al instante y scrolleamos. Sin hash, la reproducción respira como un run
    // real (compilar tarda; clasificar es instantáneo).
    const deepLink = !!window.location.hash;
    const pacing = deepLink ? {} : { phase: 350, build: 500, verify: 400 };
    for (let i = 0; i < events.length; i++) {
      processEvents([events[i]]);
      if (!deepLink) await new Promise(r => setTimeout(r, pacing[events[i].ev] || 100));
    }
    await fetchDiff();
    fetchCertificate();
    await fetchAttestation();
    scrollToHash();
  } catch (err) {
    const msg = $('newrun-msg');
    msg.textContent = 'Could not connect to the API or load demo data.';
    msg.className = 'text-xs mt-2 px-2 text-red-400';
  }
}

function applyCertToggle() {
  const open = state.certOpen;
  $('cert-content').classList.toggle('hidden', !open);
  $('cert-chevron').style.transform = open ? 'rotate(180deg)' : 'rotate(0deg)';
  $('cert-toggle').querySelector('span').textContent = open ? 'Collapse certificate' : 'Expand certificate';
}

function initCertToggle() {
  $('cert-toggle').addEventListener('click', () => {
    state.certOpen = !state.certOpen;
    applyCertToggle();
  });
}

function initIntro() {
  // Onboarding: se muestra una vez por navegador. Si el usuario llega con un
  // deep-link a una sección concreta (#wave64-section, etc.), no interrumpimos.
  const intro = $('intro');
  if (!intro) return;
  const dismiss = () => {
    intro.classList.add('hidden');
    try { localStorage.setItem('hipnosis_intro_seen', '1'); } catch (e) { /* */ }
  };
  const seen = (() => { try { return localStorage.getItem('hipnosis_intro_seen'); } catch (e) { return null; } })();
  if (!seen && !window.location.hash) intro.classList.remove('hidden');
  $('intro-close').addEventListener('click', dismiss);
  $('intro-go').addEventListener('click', dismiss);
  intro.addEventListener('click', (e) => { if (e.target === intro) dismiss(); });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') dismiss(); });
}

function scrollToHash() {
  // Deep-links del onboarding de la landing (#wave64-section, #passport-section).
  // Las secciones aparecen recién cuando el run las revela, así que scrolleamos
  // al final del replay, no al cargar.
  const hash = window.location.hash;
  if (!hash) return;
  const el = document.querySelector(hash);
  if (el && !el.classList.contains('hidden')) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function initPassport() {
  $('passport-verify-btn').addEventListener('click', () => verifyPassport());
  $('passport-tamper-btn').addEventListener('click', () => {
    // Demo de manipulación: verificar contra un diff con un byte cambiado.
    // NO altera state.diffText — es una prueba efímera de que el hash detecta
    // la más mínima modificación. Re-verify vuelve a VERIFIED.
    const tampered = state.diffText
      ? state.diffText.replace(/./, c => (c === 'x' ? 'y' : 'x'))
      : 'x';
    verifyPassport(tampered);
  });
  $('passport-download-btn').addEventListener('click', () => {
    if (!state.attestation) return;
    const blob = new Blob([JSON.stringify(state.attestation) + '\n'], { type: 'application/jsonl' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `HIPNOSIS_ATTESTATION-${state.runId}.jsonl`;
    a.click();
    URL.revokeObjectURL(url);
  });
}

function initNewRun() {
  const form = $('newrun-form');
  const input = $('newrun-url');
  const btn = $('newrun-btn');
  const msg = $('newrun-msg');
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const repoUrl = input.value.trim();
    if (!repoUrl) return;
    // Demo estático (Vercel/Pages, sin orquestador): no hay backend que reciba
    // el POST — sería un 404 confuso. Explicamos honestamente en vez de fingir.
    if (!state.apiAlive) {
      msg.innerHTML = 'This is the <b class="text-gray-200">hosted demo</b> — it replays a recorded run and has no live orchestrator, so it can\'t port an arbitrary repo. To port your own, run HIPnosis locally with an AMD GPU: <a href="https://github.com/manuelpenazuniga/HIPnosis#-quickstart-no-gpu-required" class="text-amd underline hover:text-red-400">see the quickstart</a>.';
      msg.className = 'text-xs mt-2 px-2 text-amber-400 leading-relaxed';
      msg.classList.remove('hidden');
      return;
    }
    btn.disabled = true;
    btn.textContent = 'Starting…';
    msg.classList.add('hidden');
    try {
      const resp = await fetch('/runs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ repo_url: repoUrl }),
      });
      if (resp.status === 403) {
        msg.textContent = 'This deployment only ports the curated demo repositories (bsw-cuda, softmax-cuda, scan-cuda).';
        msg.className = 'text-xs mt-2 px-2 text-amber-400';
        msg.classList.remove('hidden');
        btn.disabled = false; btn.textContent = 'Port it →';
        return;
      }
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const run = await resp.json();
      window.location.search = `?run=${encodeURIComponent(run.id)}`;
    } catch (err) {
      msg.textContent = `Could not start the run (${err.message}). Is the orchestrator up?`;
      msg.className = 'text-xs mt-2 px-2 text-red-400';
      btn.disabled = false;
      btn.textContent = 'Port it →';
    }
  });
}

function initDownload() {
  $('cert-download-btn').addEventListener('click', () => {
    if (!state.certRaw) return;
    const blob = new Blob([state.certRaw], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `HIPnosis-certificate-${state.runId}.md`;
    a.click();
    URL.revokeObjectURL(url);
  });
}

function renderModeBadge(mode) {
  if (mode) state.mode = mode;
  const el = $('mode-badge');
  // Procedencia honesta (audit codex P0.2): "recorded run" SOLO si el trace
  // mismo declara oracle_mode=real en run_meta. Un fixture sintético jamás
  // debe presentarse como corrida grabada.
  const recorded = state.runMeta && state.runMeta.oracle_mode === 'real';
  const map = {
    replay: { cls: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
              label: recorded ? 'REPLAY · recorded run' : 'REPLAY · synthetic demo' },
    real:   { cls: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20', label: 'LIVE · MI300X' },
    mock:   { cls: 'bg-gray-500/10 text-gray-400 border-gray-500/20', label: 'MOCK' },
    demo:   { cls: 'bg-amber-500/10 text-amber-400 border-amber-500/20', label: 'DEMO · offline fixtures' },
  };
  const m = map[state.mode];
  if (!m) { el.classList.add('hidden'); return; }
  el.className = `px-2 py-0.5 rounded-md text-[10px] font-bold border ${m.cls}`;
  el.textContent = m.label;
}

async function fetchRunList() {
  // H4: navegación entre runs — GET /runs existía y la UI no lo usaba.
  try {
    const resp = await fetch('/runs');
    if (!resp.ok) return;
    const runs = await resp.json();
    if (!Array.isArray(runs) || runs.length === 0) return;
    const sel = $('run-select');
    let html = runs.map(r =>
      `<option value="${escapeHtml(r.id)}"${r.id === state.runId ? ' selected' : ''}>${escapeHtml(r.id)} · ${escapeHtml(r.state)}</option>`
    ).join('');
    if (!runs.some(r => r.id === state.runId)) {
      html = `<option value="${escapeHtml(state.runId)}" selected>${escapeHtml(state.runId)}</option>` + html;
    }
    sel.innerHTML = html;
    sel.classList.remove('hidden');
    $('run-id').classList.add('hidden');
  } catch (e) { /* silent — sin lista, queda el run-id plano */ }
}

async function fetchRunMeta() {
  // Contexto del header: modo del orquestador (badge REPLAY/LIVE/MOCK) y QUÉ
  // repo se está porteando. Fallos silenciosos: la conexión la reporta el polling.
  try {
    const resp = await fetch('/healthz');
    if (resp.ok) {
      state.apiAlive = true;
      renderModeBadge((await resp.json()).mode);
    }
  } catch (e) { /* silent */ }
  try {
    const resp = await fetch(`/runs/${state.runId}`);
    if (resp.ok) {
      const run = await resp.json();
      const el = $('run-repo');
      el.textContent = run.repo_url || '';
      el.title = run.repo_url || '';
    }
  } catch (e) { /* silent */ }
}

async function init() {
  state.runId = getRunId();
  $('run-id').textContent = state.runId;
  initCertToggle();
  initDownload();
  initNewRun();
  initPassport();
  initIntro();
  $('run-select').addEventListener('change', (e) => {
    if (e.target.value && e.target.value !== state.runId) {
      window.location.search = `?run=${encodeURIComponent(e.target.value)}`;
    }
  });
  // Show the shell right away (input + phases pending) instead of blocking
  // everything behind the spinner until the first event arrives.
  showApp();
  renderTimeline();
  // Antes del primer poll: fija state.apiAlive (decide 404→not-found vs demo).
  await fetchRunMeta();
  fetchRunList();
  pollEvents();
}

document.addEventListener('DOMContentLoaded', init);
