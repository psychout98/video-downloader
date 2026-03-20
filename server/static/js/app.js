// ── Global application state ─────────────────────────────────────────────────

let currentTab    = 'queue';
let jobFilter     = 'all';
let libTypeFilter = 'all';
let expandedLogs  = new Set();
let lastJobs      = [];
let libItems      = [];
let currentSearchId = null;
let selectedMedia   = null;   // item open in the media detail modal
let _episodeList    = [];     // flat episode array for current modal (indexed by onclick)
let npStatus        = null;   // latest MPC-BE status object
let npPollTimer     = null;   // fast 2-second poll when NP tab is active
let npBgTimer       = null;   // slow 5-second background poll on other tabs
let _mpcLaunching   = false;  // true while MPC-BE is starting up (suppress error flash)
let volDragging     = false;


// ── Tab switching ────────────────────────────────────────────────────────────

function switchTab(tab, btn) {
  document.querySelectorAll('.pane').forEach(p    => p.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('pane-' + tab).classList.add('active');
  btn.classList.add('active');
  currentTab = tab;

  if (tab === 'library')    loadLibrary();
  if (tab === 'settings')   { loadSettingsForm(); loadLogs(); }

  if (tab === 'nowplaying') {
    // Switch to fast poll; stop the slow background poll to avoid double-firing
    clearInterval(npBgTimer); npBgTimer = null;
    startNPPoll();
    refreshNP();
  } else {
    stopNPPoll();
    if (!npBgTimer) npBgTimer = setInterval(refreshNP, 5000);
  }
}


// ── Server status indicator (nav-bar dot) ────────────────────────────────────

async function checkServer() {
  try {
    const r   = await fetch('/api/status');
    const dot = document.getElementById('server-dot');
    dot.className = r.ok ? 'server-dot online' : 'server-dot error';
  } catch {
    document.getElementById('server-dot').className = 'server-dot error';
  }
}


// ── Loading overlay helpers ──────────────────────────────────────────────────

function showLoading(msg) {
  document.getElementById('loading-label').innerHTML = msg;
  document.getElementById('search-loading').classList.add('show');
}
function hideLoading() {
  document.getElementById('search-loading').classList.remove('show');
}


// ── Initialisation ───────────────────────────────────────────────────────────

checkServer();
refreshJobs();

// Start background MPC-BE poll so the NP tab has cached state before the user
// switches to it (avoids a "Nothing playing" flash on first open).
npBgTimer = setInterval(refreshNP, 5000);
refreshNP();

setInterval(refreshJobs,  3000);
setInterval(checkServer, 30000);
