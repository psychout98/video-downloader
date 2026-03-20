// ── Shared utilities and constants ──────────────────────────────────────────

/** HTML-escape a value so it is safe to inject into innerHTML. */
function esc(s) {
  return String(s || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/** Format a byte count as a human-readable string (KB / MB / GB / TB). */
function fmtSize(b) {
  if (!b) return '';
  if (b >= 1e12) return (b / 1e12).toFixed(1) + ' TB';
  if (b >= 1e9)  return (b / 1e9).toFixed(1)  + ' GB';
  if (b >= 1e6)  return (b / 1e6).toFixed(1)  + ' MB';
  return (b / 1e3 | 0) + ' KB';
}

/** Format milliseconds as m:ss or h:mm:ss. */
function fmtMs(ms) {
  if (!ms) return '0:00';
  const s   = ms / 1000 | 0;
  const h   = s / 3600  | 0;
  const m   = (s % 3600) / 60 | 0;
  const sec = s % 60;
  return h
    ? `${h}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`
    : `${m}:${String(sec).padStart(2, '0')}`;
}

/** Return a human-readable "X ago" string for an ISO timestamp. */
function timeAgo(iso) {
  if (!iso) return '';
  const s = (Date.now() - new Date(iso)) / 1000;
  if (s < 60)   return `${s | 0}s ago`;
  if (s < 3600) return `${s / 60 | 0}m ago`;
  return `${s / 3600 | 0}h ago`;
}

/** Return true if a job status represents an in-progress state. */
function isActive(status) {
  return ['pending', 'searching', 'found', 'adding_to_rd',
          'waiting_for_rd', 'downloading', 'organizing'].includes(status);
}

/** Deterministic hue from a string — used for placeholder card colours. */
function hashColor(str) {
  let h = 0;
  for (const c of str) h = (h * 31 + c.charCodeAt(0)) & 0xffffffff;
  const hue = (h >>> 0) % 360;
  return `hsl(${hue},40%,22%)`;
}

// ── Shared display maps ──────────────────────────────────────────────────────

const STATUS_LABELS = {
  pending:        'Pending',
  searching:      'Searching…',
  found:          'Found',
  adding_to_rd:   'Adding to RD…',
  waiting_for_rd: 'Waiting for RD…',
  downloading:    'Downloading',
  organizing:     'Organising…',
  complete:       'Complete',
  failed:         'Failed',
  cancelled:      'Cancelled',
};

const TYPE_ICONS = { movie: '🎬', tv: '📺', anime: '🎌' };
