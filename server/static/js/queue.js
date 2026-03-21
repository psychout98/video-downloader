// ── Queue tab: search, stream picker, download queue ────────────────────────


// ── Search ───────────────────────────────────────────────────────────────────

let _searchController = null;   // AbortController for the in-flight search
let _searchGeneration  = 0;     // increments with every new search; lets finally know if it's stale

async function doSearch() {
  const q = document.getElementById('q-input').value.trim();
  if (!q) return;

  // Cancel any previous in-flight search before starting a new one
  if (_searchController) _searchController.abort();
  _searchController = new AbortController();
  const signal = _searchController.signal;
  const myGen  = ++_searchGeneration;   // capture the generation for this request

  showLoading('Searching TMDB &amp; torrent sources…');
  hideStreamPanel();
  try {
    const r = await fetch('/api/search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: q }),
      signal,
    });
    const data = await r.json();
    if (!r.ok) { showToast('Search failed: ' + (data.detail || 'unknown error'), 'error'); return; }
    currentSearchId = data.search_id;
    renderStreamPanel(data.media, data.streams, data.warning);
  } catch (e) {
    if (e.name === 'AbortError') return;   // superseded by a newer search — ignore silently
    showToast('Network error: ' + e.message, 'error');
  } finally {
    // Only tear down the loading state if no newer search has taken over.
    // An aborted request must NOT hide the overlay that belongs to its successor.
    if (myGen === _searchGeneration) {
      hideLoading();
      _searchController = null;
    }
  }
}

document.getElementById('q-input').addEventListener('keydown', e => {
  if (e.key === 'Enter') doSearch();
});


// ── Stream picker panel ───────────────────────────────────────────────────────

function renderStreamPanel(media, streams, warning) {
  document.getElementById('sp-title').textContent = media.title || '—';
  document.getElementById('sp-year').textContent  = media.year ? `(${media.year})` : '';
  document.getElementById('sp-type').textContent  = (media.type || '').toUpperCase();

  const list = document.getElementById('stream-list');
  if (!streams.length) {
    const msg = warning || 'No RD-cached torrents found. Try a different query.';
    list.innerHTML = `<div class="no-streams" style="color:var(--error)">⚠ ${esc(msg)}</div>`;
    document.getElementById('stream-panel').style.display = 'block';
    return;
  }

  // Show a non-blocking warning banner above the stream list if present
  const warnHtml = warning
    ? `<div class="no-streams" style="color:var(--warning,var(--accent));margin-bottom:8px">⚠ ${esc(warning)}</div>`
    : '';

  list.innerHTML = warnHtml + streams.map((s, i) => {
    const badges  = buildBadgeHTML(s);
    const size    = s.size_bytes ? fmtSize(s.size_bytes) : '';
    const seeds   = s.seeders    ? `${s.seeders} seeds`  : '';
    const cached  = s.is_cached_rd
      ? '<span class="pill pill-cached">⚡ Cached</span>'
      : '<span class="pill pill-queue">⏳ Queue</span>';
    const bestTag = i === 0 ? ' best' : '';
    return `
      <div class="stream-card${bestTag}" onclick="confirmDownload(${i})">
        <div style="flex:1;min-width:0">
          <div class="stream-badges">${badges} ${cached}</div>
          <div class="stream-name">${esc(s.name.slice(0, 100))}</div>
        </div>
        <div class="stream-meta">
          ${size ? size + '<br>' : ''}
          ${seeds}
        </div>
      </div>`;
  }).join('');

  document.getElementById('stream-panel').style.display = 'block';
}

/** Build quality/source badge HTML for a stream object. */
function buildBadgeHTML(s) {
  const parts = [];
  if (s.resolution) {
    const cls = (s.resolution.startsWith('4') || s.resolution === '2160P') ? 'pill-4k' : 'pill-hd';
    parts.push(`<span class="pill ${cls}">${s.resolution}</span>`);
  }
  if (s.hdr && (s.hdr.includes('dv') || s.hdr.includes('dolby') || s.hdr.includes('dovi')))
    parts.push('<span class="pill pill-dv">DV</span>');
  else if (s.hdr && s.hdr.includes('hdr'))
    parts.push('<span class="pill pill-dv" style="background:rgba(91,156,246,.15);color:var(--info)">HDR</span>');
  if (s.audio && s.audio.includes('atmos'))
    parts.push('<span class="pill pill-atmos">Atmos</span>');
  else if (s.audio && s.audio.includes('truehd'))
    parts.push('<span class="pill pill-atmos">TrueHD</span>');
  else if (s.audio && s.audio.includes('dts'))
    parts.push('<span class="pill pill-atmos" style="background:rgba(91,156,246,.1);color:var(--info)">DTS-HD</span>');
  if (s.channels === '7.1') parts.push('<span class="pill pill-queue">7.1</span>');
  else if (s.channels === '5.1') parts.push('<span class="pill pill-queue">5.1</span>');
  if (s.source) {
    const src = s.source.includes('remux') ? 'Remux'
      : s.source.includes('blu') || s.source.includes('bd') ? 'BluRay'
      : s.source.includes('web') ? (s.source.includes('dl') ? 'WEB-DL' : 'WEBRip')
      : s.source.toUpperCase();
    parts.push(`<span class="pill" style="background:var(--surface);border:1px solid var(--border);color:var(--muted)">${src}</span>`);
  }
  return parts.join('') || `<span class="pill pill-queue">${esc((s.quality_str || 'Unknown').slice(0, 30))}</span>`;
}

function hideStreamPanel() {
  document.getElementById('stream-panel').style.display = 'none';
  document.getElementById('stream-list').innerHTML = '';
  currentSearchId = null;
}

async function confirmDownload(streamIndex) {
  if (!currentSearchId) return;
  try {
    const r = await fetch('/api/download', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ search_id: currentSearchId, stream_index: streamIndex }),
    });
    const data = await r.json();
    if (r.ok) {
      showToast('✓ ' + (data.message || 'Download queued'), 'success');
      hideStreamPanel();
      document.getElementById('q-input').value = '';
      await refreshJobs();
    } else {
      showToast('Error: ' + (data.detail || JSON.stringify(data)), 'error');
    }
  } catch (e) {
    showToast('Network error: ' + e.message, 'error');
  }
}


// ── Toast notification ────────────────────────────────────────────────────────

function showToast(msg, type) {
  const t = document.getElementById('toast');
  t.textContent  = msg;
  t.className    = type;
  t.style.display = 'block';
  setTimeout(() => t.style.display = 'none', 5000);
}


// ── Job list ──────────────────────────────────────────────────────────────────

function setFilter(f, btn) {
  jobFilter = f;
  document.querySelectorAll('.ftab').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  renderJobs(lastJobs);
}

function renderJobs(jobs) {
  const filtered = jobs.filter(j => {
    if (jobFilter === 'active')   return isActive(j.status);
    if (jobFilter === 'complete') return j.status === 'complete';
    if (jobFilter === 'failed')   return j.status === 'failed' || j.status === 'cancelled';
    return true;
  });
  document.getElementById('job-count').textContent = filtered.length;
  const el = document.getElementById('jobs-container');
  if (!filtered.length) {
    el.innerHTML = `<div class="empty-state">
      <div class="ei">📭</div>
      <h3>No jobs</h3>
      <p style="color:var(--muted);font-size:13px">Search above to queue a download.</p>
    </div>`;
    return;
  }
  el.innerHTML = filtered.map(renderJob).join('');
  filtered.forEach(j => {
    const lb = document.getElementById('lb-' + j.id);
    if (lb) lb.onclick = () => toggleLog(j.id);
  });
}

function renderJob(j) {
  const active  = isActive(j.status);
  const pct     = Math.round((j.progress || 0) * 100);
  const title   = j.title ? (j.year ? `${j.title} (${j.year})` : j.title) : j.query;
  const icon    = TYPE_ICONS[j.type] || '📄';
  const logOpen = expandedLogs.has(j.id);
  const spinner = active && j.status !== 'downloading' ? '<span class="spin"></span>' : '';

  let prog = '';
  if (active || j.status === 'complete') {
    const fc      = j.status === 'complete' ? 'done' : j.status === 'failed' ? 'fail' : '';
    const szLabel = j.size_bytes ? `${fmtSize(j.downloaded_bytes || 0)} / ${fmtSize(j.size_bytes)}` : '';
    prog = `<div class="progress-wrap">
      <div class="progress-bar"><div class="progress-fill ${fc}" style="width:${pct}%"></div></div>
      <div class="progress-row"><span>${pct}%</span><span>${szLabel}</span></div>
    </div>`;
  }

  let actions = '';
  if (active)
    actions = `<button class="btn-ghost btn-sm" onclick="cancelJob('${j.id}')">Cancel</button>`;
  else if (j.status === 'failed' || j.status === 'cancelled')
    actions = `<button class="btn btn-sm" onclick="retryJob('${j.id}')">Retry</button>
               <button class="btn-ghost btn-sm" onclick="deleteJob('${j.id}')">Delete</button>`;
  else if (j.status === 'complete')
    actions = `<button class="btn-ghost btn-sm" onclick="deleteJob('${j.id}')">Remove</button>`;

  const qualPill = j.quality
    ? `<span class="pill" style="background:rgba(229,160,13,.1);color:var(--accent)">${esc(j.quality)}</span>`
    : '';

  return `<div class="job-card ${active ? 'running' : ''}" id="jc-${j.id}">
    <div class="job-top">
      <div class="job-icon">${icon}</div>
      <div class="job-info">
        <div class="job-title">${esc(title)}</div>
        <div class="job-meta">
          <span class="status-badge s-${j.status}">${spinner}${STATUS_LABELS[j.status] || j.status}</span>
          ${j.type ? `<span class="pill pill-type">${j.type.toUpperCase()}</span>` : ''}
          ${qualPill}
          ${j.size_bytes ? `<span class="meta-txt">${fmtSize(j.size_bytes)}</span>` : ''}
          <span class="meta-txt">${timeAgo(j.created_at)}</span>
        </div>
      </div>
      <div class="job-actions">${actions}</div>
    </div>
    ${prog}
    ${j.status === 'complete' && j.file_path ? `<div class="job-path">📁 ${esc(j.file_path)}</div>` : ''}
    ${j.error ? `<div class="job-error">⚠ ${esc(j.error)}</div>` : ''}
    ${j.log ? `<button class="log-toggle" id="lb-${j.id}">${logOpen ? '▲ hide log' : '▼ show log'}</button>
               <pre class="job-log" id="jlog-${j.id}" style="display:${logOpen ? 'block' : 'none'}">${esc(j.log.trim())}</pre>` : ''}
  </div>`;
}

function toggleLog(id) {
  expandedLogs.has(id) ? expandedLogs.delete(id) : expandedLogs.add(id);
  const el = document.getElementById('jlog-' + id);
  const lb = document.getElementById('lb-' + id);
  if (el) el.style.display = expandedLogs.has(id) ? 'block' : 'none';
  if (lb) lb.textContent   = expandedLogs.has(id) ? '▲ hide log' : '▼ show log';
  if (el && expandedLogs.has(id)) el.scrollTop = el.scrollHeight;
}

async function cancelJob(id) { await fetch(`/api/jobs/${id}`, { method: 'DELETE' }); await refreshJobs(); }
async function deleteJob(id)  { await fetch(`/api/jobs/${id}`, { method: 'DELETE' }); await refreshJobs(); }
async function retryJob(id)   { await fetch(`/api/jobs/${id}/retry`, { method: 'POST' }); await refreshJobs(); }

async function refreshJobs() {
  try {
    const r = await fetch('/api/jobs');
    if (!r.ok) return;
    const d = await r.json();
    lastJobs = d.jobs || [];
    if (currentTab === 'queue') renderJobs(lastJobs);
  } catch { /* server not up yet */ }
}
