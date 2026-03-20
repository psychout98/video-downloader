// ── Settings tab: configuration form, server logs, server control ────────────

const SETTINGS_KEYS = [
  'TMDB_API_KEY', 'REAL_DEBRID_API_KEY', 'SECRET_KEY',
  'MOVIES_DIR', 'TV_DIR', 'ANIME_DIR',
  'MOVIES_DIR_ARCHIVE', 'TV_DIR_ARCHIVE', 'ANIME_DIR_ARCHIVE',
  'DOWNLOADS_DIR', 'POSTERS_DIR',
  'MPC_BE_EXE', 'WATCH_THRESHOLD', 'PORT',
];


// ── Settings form ─────────────────────────────────────────────────────────────

async function loadSettingsForm() {
  try {
    const r = await fetch('/api/settings');
    if (!r.ok) return;
    const d = await r.json();
    for (const key of SETTINGS_KEYS) {
      const el = document.getElementById('cfg-' + key);
      if (el && d[key] !== undefined) el.value = d[key];
    }
  } catch {}
}

async function saveSettings() {
  const updates = {};
  for (const key of SETTINGS_KEYS) {
    const el = document.getElementById('cfg-' + key);
    if (el) updates[key] = el.value;
  }
  const toast = document.getElementById('settings-save-toast');
  try {
    const r = await fetch('/api/settings', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ updates }),
    });
    const d = await r.json();
    if (r.ok) {
      toast.textContent    = '✓ Saved — settings applied';
      toast.style.display  = 'inline';
      setTimeout(() => toast.style.display = 'none', 4000);
    } else {
      _showSettingsError(toast, '✗ Error: ' + (d.detail || JSON.stringify(d)));
    }
  } catch (e) {
    _showSettingsError(toast, '✗ Network error: ' + e.message);
  }
}

function _showSettingsError(toast, msg) {
  toast.textContent   = msg;
  toast.style.color   = 'var(--error)';
  toast.style.display = 'inline';
  setTimeout(() => {
    toast.style.display = 'none';
    toast.style.color   = 'var(--success)';
  }, 6000);
}


// ── Server log viewer ─────────────────────────────────────────────────────────

async function loadLogs() {
  const viewer     = document.getElementById('log-viewer');
  const autoscroll = document.getElementById('log-autoscroll').checked;
  try {
    const r = await fetch('/api/logs?lines=300');
    if (!r.ok) { viewer.textContent = 'Could not load logs.'; return; }
    const d = await r.json();
    viewer.textContent = (d.lines || []).join('\n') || '(No log entries yet)';
    if (autoscroll) viewer.scrollTop = viewer.scrollHeight;
  } catch {
    viewer.textContent = 'Server unreachable.';
  }
}


// ── Server control ────────────────────────────────────────────────────────────

async function confirmRestartServer() {
  if (!confirm('Restart the server? The UI will be unavailable for a few seconds.')) return;
  const toast = document.getElementById('restart-toast');
  toast.textContent  = '↺ Restarting…';
  toast.style.color  = 'var(--muted)';
  toast.style.display = 'inline';
  try {
    await fetch('/api/restart', { method: 'POST' });
  } catch { /* connection drop is expected */ }

  // Poll until the server comes back
  const start = Date.now();
  const poll = setInterval(async () => {
    if (Date.now() - start > 30000) {
      clearInterval(poll);
      toast.textContent = '✗ Server did not come back in 30 s — check logs';
      toast.style.color = 'var(--error)';
      return;
    }
    try {
      const r = await fetch('/api/status');
      if (r.ok) {
        clearInterval(poll);
        toast.textContent = '✓ Server restarted';
        toast.style.color = 'var(--success)';
        setTimeout(() => toast.style.display = 'none', 4000);
      }
    } catch { /* still coming up */ }
  }, 1000);
}

async function confirmStopServer() {
  if (!confirm('Stop the server? The UI will stop working until the server is restarted.')) return;
  try {
    const r = await fetch('/api/shutdown', { method: 'POST' });
    const d = await r.json();
    alert(d.message || 'Server stopping…');
  } catch {
    // Server may have already closed the connection — that's expected
    alert('Server stopping…');
  }
}

function showUninstallHelp() {
  const el           = document.getElementById('uninstall-help');
  el.style.display   = el.style.display === 'none' ? 'block' : 'none';
}
