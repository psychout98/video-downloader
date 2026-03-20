// ── Now Playing tab: MPC-BE status polling and playback controls ─────────────


// ── Polling ───────────────────────────────────────────────────────────────────

function startNPPoll() {
  if (!npPollTimer) npPollTimer = setInterval(refreshNP, 2000);
}
function stopNPPoll() {
  clearInterval(npPollTimer);
  npPollTimer = null;
}

async function refreshNP() {
  try {
    const r = await fetch('/api/mpc/status');
    if (!r.ok) {
      if (_mpcLaunching) { showNPStarting(); return; }
      showNPError('Could not reach MPC-BE.');
      return;
    }
    npStatus      = await r.json();
    _mpcLaunching = false;   // successfully connected — clear launching flag
    renderNP(npStatus);
  } catch {
    if (_mpcLaunching) { showNPStarting(); return; }
    showNPError('MPC-BE unreachable — make sure it is running with web interface enabled.');
  }
}


// ── Rendering ────────────────────────────────────────────────────────────────

const _NP_IDLE_HTML =
  '<div class="ni">🎬</div>' +
  '<h3>Nothing playing</h3>' +
  '<p>Start something in MPC-BE or pick a file from the Library tab.</p>';

function renderNP(s) {
  document.getElementById('np-error').style.display = 'none';
  if (!s || !s.file) {
    const idle       = document.getElementById('np-idle');
    idle.innerHTML   = _NP_IDLE_HTML;   // restore if it was showing "Starting…"
    idle.style.display  = 'block';
    document.getElementById('np-player').style.display = 'none';
    return;
  }
  document.getElementById('np-idle').style.display   = 'none';
  document.getElementById('np-player').style.display = 'block';

  document.getElementById('np-title').textContent =
    s.filename || s.file.split('\\').pop().split('/').pop();
  document.getElementById('np-file').textContent = s.file;
  document.getElementById('np-playpause').textContent = s.is_playing ? '⏸' : '▶';

  const pct = s.duration_ms > 0 ? (s.position_ms / s.duration_ms * 100).toFixed(2) : 0;
  document.getElementById('np-fill').style.width  = pct + '%';
  document.getElementById('np-pos').textContent   = s.position_str || fmtMs(s.position_ms);
  document.getElementById('np-dur').textContent   = s.duration_str || fmtMs(s.duration_ms);

  if (!volDragging) {
    document.getElementById('vol-slider').value        = s.volume;
    document.getElementById('vol-pct').textContent     = s.volume + '%';
  }
  document.getElementById('mute-icon').textContent =
    s.muted ? '🔇' : s.volume < 30 ? '🔈' : '🔊';
}

function showNPError(msg) {
  const el       = document.getElementById('np-error');
  el.textContent = msg;
  el.style.display = 'block';
}

function showNPStarting() {
  document.getElementById('np-error').style.display  = 'none';
  document.getElementById('np-player').style.display = 'none';
  const idle     = document.getElementById('np-idle');
  idle.innerHTML = '<div class="ni">⏳</div><h3>Starting MPC-BE…</h3><p>The player is loading, please wait.</p>';
  idle.style.display = 'block';
}


// ── Playback commands ─────────────────────────────────────────────────────────

async function mpcCmd(cmd, extra) {
  const body = { command: cmd };
  if (extra) Object.assign(body, extra);
  try {
    await fetch('/api/mpc/command', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(body),
    });
    setTimeout(refreshNP, 400);
  } catch {}
}

async function mpcPlayPause() { await mpcCmd(887); }

async function mpcSeekRel(deltaMs) {
  if (!npStatus || !npStatus.duration_ms) return;
  const newPos = Math.max(0, Math.min(npStatus.duration_ms, npStatus.position_ms + deltaMs));
  await fetch('/api/mpc/command', {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ command: 889, position_ms: newPos }),
  });
  setTimeout(refreshNP, 400);
}

// Seek on progress-bar click
document.getElementById('np-seek').addEventListener('click', async e => {
  if (!npStatus || !npStatus.duration_ms) return;
  const rect = e.currentTarget.getBoundingClientRect();
  const frac = (e.clientX - rect.left) / rect.width;
  const pos  = Math.round(frac * npStatus.duration_ms);
  await fetch('/api/mpc/command', {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ command: 889, position_ms: pos }),
  });
  setTimeout(refreshNP, 400);
});


// ── Volume ────────────────────────────────────────────────────────────────────

function onVolSlider(val) {
  volDragging = true;
  document.getElementById('vol-pct').textContent = val + '%';
}

async function setVolume(val) {
  // MPC-BE has no direct "set volume to N%" API command, so we approximate
  // by sending volume-up / volume-down commands in 5% steps.
  const current = npStatus ? npStatus.volume : 100;
  const target  = parseInt(val);
  const diff    = target - current;
  const steps   = Math.round(Math.abs(diff) / 5);
  const cmd     = diff > 0 ? 907 : 908;
  for (let i = 0; i < steps; i++) await mpcCmd(cmd);
  volDragging = false;
  setTimeout(refreshNP, 600);
}
