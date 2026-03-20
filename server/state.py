"""
App-level mutable singletons.

All values start as ``None`` and are populated by ``main.lifespan()``
before the first request is ever served.  Routers import this module and
read from it at request time — never at import time.
"""
from __future__ import annotations

import time
from pathlib import Path

# ── Paths (set once at startup from main.py) ─────────────────────────────────
ROOT_DIR: Path = Path(__file__).parent.parent   # project root
ENV_FILE: Path = ROOT_DIR / ".env"
PID_FILE: Path = ROOT_DIR / "server.pid"
LOG_FILE: Path = ROOT_DIR / "logs" / "server.log"

# ── Service singletons ────────────────────────────────────────────────────────
processor    = None   # JobProcessor
tmdb         = None   # TMDBClient
torrentio    = None   # TorrentioClient
nyaa         = None   # NyaaClient
scorer       = None   # QualityScorer
library      = None   # LibraryScanner
mpc          = None   # MPCClient
watch_tracker  = None # WatchTracker
progress_store = None # ProgressStore

# ── In-memory search cache ────────────────────────────────────────────────────
# { search_id: {"media": dict, "streams": list, "expires": float} }
searches: dict = {}
SEARCH_TTL = 300  # seconds until a search result expires


def prune_searches() -> None:
    """Remove expired entries from the search cache."""
    now = time.time()
    stale = [k for k, v in searches.items() if v["expires"] < now]
    for k in stale:
        del searches[k]
