// ── Library tab: grid, cards, media modal, episodes, playback ────────────────


// ── Library load / filter ─────────────────────────────────────────────────────

async function loadLibrary(force = false) {
  document.getElementById('lib-sections').innerHTML =
    '<div style="text-align:center;padding:40px;color:var(--muted)">Loading library…</div>';
  try {
    // On force-refresh clear the poster cache first so stale images are
    // re-fetched from TMDB when cards render.
    if (force) {
      await fetch('/api/library/posters/clear', { method: 'POST' }).catch(() => {});
    }
    const r = await fetch('/api/library' + (force ? '?force=true' : ''));
    if (!r.ok) { renderLibEmpty('Could not load library.'); return; }
    const d = await r.json();
    libItems = d.items || [];
    renderLibGrid();
  } catch {
    renderLibEmpty('Server unreachable.');
  }
}

let libTypeFilter2 = 'all';

function setLibType(t, btn) {
  libTypeFilter2 = t;
  document.querySelectorAll('.lib-type-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  renderLibGrid();
}

function filterLib() { renderLibGrid(); }

const LIB_SECTIONS = [
  { type: 'movie', label: 'Movies',   icon: '🎬' },
  { type: 'tv',    label: 'TV Shows', icon: '📺' },
  { type: 'anime', label: 'Anime',    icon: '⛩️' },
];

function renderLibGrid() {
  const query     = document.getElementById('lib-search').value.toLowerCase();
  const showAll   = libTypeFilter2 === 'all';
  const container = document.getElementById('lib-sections');

  const allFiltered = libItems.filter(item => {
    if (!showAll && item.type !== libTypeFilter2) return false;
    if (query && !item.title.toLowerCase().includes(query)) return false;
    return true;
  });
  document.getElementById('lib-count').textContent =
    `${allFiltered.length} item${allFiltered.length !== 1 ? 's' : ''}`;

  if (!allFiltered.length) {
    container.innerHTML = '<div style="text-align:center;padding:40px;color:var(--muted)">No items found.</div>';
    return;
  }

  if (showAll) {
    let html = '';
    for (const sec of LIB_SECTIONS) {
      const items = allFiltered.filter(i => i.type === sec.type);
      if (!items.length) continue;
      html += `<div class="lib-section">
        <div class="lib-section-header">
          <span class="lib-section-title">${sec.icon}&nbsp; ${sec.label}</span>
          <span class="lib-section-count">${items.length}</span>
        </div>
        <div class="lib-grid">${items.map(renderLibCard).join('')}</div>
      </div>`;
    }
    container.innerHTML = html;
  } else {
    container.innerHTML = `<div class="lib-grid">${allFiltered.map(renderLibCard).join('')}</div>`;
  }
}

function renderLibEmpty(msg) {
  document.getElementById('lib-sections').innerHTML =
    `<div style="text-align:center;padding:40px;color:var(--muted)">${msg}</div>`;
}


// ── Poster URL helper ─────────────────────────────────────────────────────────

/** Return the best poster URL for a library item.
 *
 *  Uses ``tmdb_title`` / ``tmdb_year`` when present — these come from
 *  data/title_overrides.json and override the parsed filename title so TMDB
 *  finds the right result for tricky titles (colons, apostrophes, etc.).
 */
function libPosterSrc(item) {
  // Serve a locally-cached poster file if the scanner found one
  if (item.poster)
    return `/api/library/poster?path=${encodeURIComponent(item.poster)}`;
  // Otherwise ask the server to fetch it from TMDB (and cache it).
  // Prefer override fields when available.
  if (item.folder) {
    const lookupTitle = item.tmdb_title || item.title;
    const lookupYear  = item.tmdb_year  || item.year;
    let u = `/api/library/poster/tmdb`
          + `?title=${encodeURIComponent(lookupTitle)}`
          + `&folder=${encodeURIComponent(item.folder)}`
          + `&type=${encodeURIComponent(item.type || 'movie')}`;
    if (lookupYear) u += `&year=${lookupYear}`;
    return u;
  }
  return null;
}


// ── Library card renderer ─────────────────────────────────────────────────────

function renderLibCard(item) {
  const color      = hashColor(item.title);
  const icon       = TYPE_ICONS[item.type] || '📄';
  const titleWords = item.title.split(' ').slice(0, 4).join(' ');

  const posterSrc = libPosterSrc(item);
  let posterHTML;
  if (posterSrc) {
    // onerror falls back to a coloured placeholder; uses a closure-safe
    // color value encoded into the attribute string.
    const escColor = color.replace(/'/g, "\\'");
    posterHTML = `<img class="lib-poster" src="${posterSrc}" alt="" loading="lazy"
      onerror="this.parentNode.innerHTML='<div class=\\'lib-poster-placeholder\\' style=\\'background:${escColor}\\'>'
        +'<span>${icon}</span><span class=\\'pt\\'>${esc(titleWords)}</span></div>'">`;
  } else {
    posterHTML = `<div class="lib-poster-placeholder" style="background:${color}">
      <span>${icon}</span><span class="pt">${esc(titleWords)}</span></div>`;
  }

  const storageBadge = {
    new:     `<span class="storage-badge storage-new">NEW</span>`,
    archive: `<span class="storage-badge storage-archive">WATCHED</span>`,
    mixed:   `<span class="storage-badge storage-mixed">MIXED</span>`,
  }[item.storage] || '';

  // Pass item data via a global index rather than inline JSON to avoid
  // HTML attribute escaping issues with titles containing quotes/colons.
  const idx = _libCardItems.push(item) - 1;

  return `<div class="lib-card" onclick="openMediaModal(${idx})">
    <div class="lib-poster-wrap">
      ${posterHTML}
      ${storageBadge}
    </div>
    <div class="lib-card-info">
      <div class="lib-card-title">${esc(item.title)}</div>
      <div class="lib-card-year">${item.year || ''}</div>
    </div>
  </div>`;
}

// Index-based item store so onclick handlers don't embed JSON in HTML.
let _libCardItems = [];

// Reset the store each time the grid is fully re-rendered.
const _origRenderLibGrid = renderLibGrid;
window.renderLibGrid = function () {
  _libCardItems = [];
  _origRenderLibGrid();
};


// ── Media detail modal ────────────────────────────────────────────────────────

let _modalEpisodeData = null;

function openMediaModal(itemIdx) {
  const item = _libCardItems[itemIdx];
  if (!item) return;
  selectedMedia     = item;
  _modalEpisodeData = null;

  const color = hashColor(item.title);
  const icon  = TYPE_ICONS[item.type] || '📄';

  // Poster
  const pw        = document.getElementById('modal-poster-wrap');
  const mPosterSrc = libPosterSrc(item);
  if (mPosterSrc) {
    pw.innerHTML = `<img src="${mPosterSrc}" alt=""
      style="width:100%;height:210px;object-fit:cover;display:block"
      onerror="this.parentNode.innerHTML='<div class=\\'modal-poster-ph\\' style=\\'background:${color}\\'>${icon}</div>'">`;
  } else {
    pw.innerHTML = `<div class="modal-poster-ph" style="background:${color}">${icon}</div>`;
  }

  document.getElementById('modal-title').textContent = item.title;
  const storageLabel = {
    new:     'On NVMe (new)',
    archive: 'On SATA (watched)',
    mixed:   'Split across drives',
  }[item.storage] || '';
  document.getElementById('modal-meta').textContent = [
    item.year,
    item.file_count > 1 ? item.file_count + ' files' : '',
    fmtSize(item.size_bytes),
    storageLabel,
  ].filter(Boolean).join(' · ');
  document.getElementById('modal-tags').innerHTML =
    `<span class="pill pill-type">${(item.type || '').toUpperCase()}</span>`;
  document.getElementById('modal-path').textContent = item.path;

  const epEl = document.getElementById('modal-episodes');
  if (item.type === 'tv' || item.type === 'anime') {
    epEl.style.display = 'block';
    epEl.innerHTML = '<div style="padding:16px;color:var(--muted);font-size:13px">Loading episodes…</div>';
    document.getElementById('modal-play-btn').textContent = '▶ Play Next';
    loadEpisodes(item);
  } else {
    epEl.style.display = 'none';
    document.getElementById('modal-play-btn').textContent = '▶ Play in MPC-BE';
  }

  document.getElementById('media-modal').classList.add('show');
}

function closeModal(event) {
  if (event.target === event.currentTarget) closeModalDirect();
}
function closeModalDirect() {
  document.getElementById('media-modal').classList.remove('show');
}


// ── Episode list ──────────────────────────────────────────────────────────────

async function loadEpisodes(item) {
  const epEl = document.getElementById('modal-episodes');
  try {
    let url = `/api/library/episodes?folder=${encodeURIComponent(item.folder)}`;
    if (item.folder_archive)
      url += `&folder_archive=${encodeURIComponent(item.folder_archive)}`;
    const r = await fetch(url);
    if (!r.ok) throw new Error('API error');
    const d       = await r.json();
    _modalEpisodeData = d.seasons;
    renderEpisodes(d.seasons);
  } catch {
    epEl.innerHTML =
      '<div style="padding:16px;color:var(--muted);font-size:13px">Could not load episodes.</div>';
  }
}

function renderEpisodes(seasons) {
  _episodeList = [];   // reset flat list
  const epEl   = document.getElementById('modal-episodes');
  if (!seasons || !seasons.length) {
    epEl.innerHTML =
      '<div style="padding:16px;color:var(--muted);font-size:13px">No episodes found.</div>';
    return;
  }
  let html = '';
  for (const { season, episodes } of seasons) {
    html += `<div class="ep-season-header">Season ${season} <span style="font-weight:400;opacity:.6">(${episodes.length} ep)</span></div>`;
    for (const ep of episodes) {
      const idx    = _episodeList.length;
      _episodeList.push(ep);
      const epLabel = ep.episode
        ? `S${String(season).padStart(2, '0')}E${String(ep.episode).padStart(2, '0')}`
        : `S${String(season).padStart(2, '0')}`;
      const pct    = ep.progress_pct || 0;
      const done   = pct >= 85;
      const progHTML = done
        ? `<span class="ep-done" title="Watched">✓</span>`
        : pct > 0
          ? `<div class="ep-bar"><div class="ep-bar-fill" style="width:${pct}%"></div></div>
             <div class="ep-pct">${pct}%</div>`
          : '';
      html += `<div class="ep-row">
        <button class="ep-play" onclick="playEpisode(${idx})">▶</button>
        <div class="ep-info">
          <div class="ep-label">${epLabel}</div>
          <div class="ep-title">${esc(ep.title || '')}</div>
        </div>
        <div class="ep-progress-wrap">${progHTML}</div>
      </div>`;
    }
  }
  epEl.innerHTML = html;
}


// ── Playback ──────────────────────────────────────────────────────────────────

/** Play all episodes from *idx* onwards as a playlist. */
async function playEpisode(idx) {
  const ep = _episodeList[idx];
  if (!ep) return;
  const playlist = _episodeList.slice(idx).map(e => e.path);
  await _openInMPC(ep.path, playlist);
}

/** Play the selected item — either a movie or the next unwatched episode. */
async function playInMPC() {
  if (!selectedMedia) return;
  const item = selectedMedia;

  let path     = item.path;
  let playlist = null;

  if ((item.type === 'tv' || item.type === 'anime') && _modalEpisodeData) {
    // Flatten all seasons into one list and find the first unwatched episode
    const allEps = _modalEpisodeData.flatMap(s => s.episodes);
    const startIdx = allEps.findIndex(e => (e.progress_pct || 0) < 85);
    if (startIdx >= 0) {
      path     = allEps[startIdx].path;
      playlist = allEps.slice(startIdx).map(e => e.path);
    }
  }

  await _openInMPC(path, playlist);
}

/** Send an open request to the server, then switch to the Now Playing tab. */
async function _openInMPC(path, playlist = null) {
  let resp;
  try {
    resp = await fetch('/api/mpc/open', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ path, playlist }),
    });
  } catch {
    alert('Could not reach the server.');
    return;
  }

  if (!resp.ok) {
    const d = await resp.json().catch(() => ({}));
    alert(d.detail || 'Failed to open file in MPC-BE.');
    return;
  }

  const d = await resp.json();
  if (!d.ok) {
    alert('MPC-BE could not open the file. Check that its web interface is enabled on port 13579.');
    return;
  }

  closeModalDirect();
  const switchToNP = () =>
    document.querySelectorAll('.tab-btn').forEach(b => {
      if (b.textContent.includes('Now Playing')) b.click();
    });

  if (d.launched) {
    // MPC-BE was just started — suppress the "unreachable" flash while it loads
    _mpcLaunching = true;
    switchToNP();
    // Clear the flag and do a real status poll after ~6 seconds
    setTimeout(() => { _mpcLaunching = false; refreshNP(); }, 6000);
  } else {
    switchToNP();
    // Already running — give it a moment to load the new file
    setTimeout(refreshNP, 1200);
  }
}
