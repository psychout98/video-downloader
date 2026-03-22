"""
Test infrastructure for Media Downloader.

Provides:
- FastAPI TestClient with mocked dependencies
- Temporary database for each test
- Mock singletons injected into server.state (via monkeypatch, not module replacement)
- Temporary .env file
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest

# Ensure the project root is in the path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Set required env vars BEFORE any server module is imported, so that
# server.config.Settings() doesn't blow up on missing TMDB_API_KEY / RD key.
os.environ.setdefault("TMDB_API_KEY", "test_tmdb_key_12345")
os.environ.setdefault("REAL_DEBRID_API_KEY", "test_rd_key_67890")


# ── Mock Classes ───────────────────────────────────────────────────────────


@dataclass
class MockMediaInfo:
    """Mock TMDB search result."""

    title: str = "Test Title"
    year: int = 2024
    imdb_id: str = "tt1234567"
    tmdb_id: int = 12345
    type: str = "movie"
    season: int | None = None
    episode: int | None = None
    is_anime: bool = False
    episode_titles: list[str] | None = None
    overview: str = "Test overview"
    poster_path: str | None = "/path/to/poster.jpg"
    poster_url: str | None = "https://example.com/poster.jpg"
    display_name: str = "Test Title (2024)"


@dataclass
class MockStreamResult:
    """Mock Torrentio stream result."""

    name: str = "Test.Torrent.1080p"
    info_hash: str = "abc123"
    download_url: str = "https://example.com/download"
    size_bytes: int = 5000000000
    seeders: int = 100
    is_cached_rd: bool = True
    magnet: str = "magnet:?xt=urn:btih:abc123"
    file_idx: int | None = None


class MockTMDBClient:
    """Mock TMDB client."""

    async def search(self, query: str) -> MockMediaInfo:
        return MockMediaInfo(title=query.title())

    async def fuzzy_resolve(
        self, title: str, media_type: str = "movie", year: int | None = None
    ):
        return title, year or 2024, "/path/to/poster.jpg"

    async def close(self):
        pass


class MockTorrentioClient:
    """Mock Torrentio client."""

    async def get_streams(self, media, cached_only: bool = False) -> list[MockStreamResult]:
        if cached_only:
            return [MockStreamResult(is_cached_rd=True)]
        return [
            MockStreamResult(name="Test.1080p", is_cached_rd=True),
            MockStreamResult(name="Test.720p", is_cached_rd=False),
        ]

    async def close(self):
        pass


class MockRealDebridClient:
    """Mock Real-Debrid client."""

    async def add_magnet(self, magnet_link: str):
        return {"id": "rd-torrent-123"}

    async def get_torrent_info(self, torrent_id: str):
        return {"status": "downloaded", "progress": 100}

    async def close(self):
        pass


class MockMPCClient:
    """Mock MPC-BE client."""

    async def get_status(self):
        status = MagicMock()
        status.to_dict.return_value = {"file": "test.mkv", "state": "playing"}
        return status

    async def command(self, command_id: int, **kwargs):
        return True

    async def ping(self):
        return True


class MockLibraryManager:
    """Mock library manager."""

    def scan(self, force: bool = False) -> list[dict]:
        return []

    async def refresh(self, tmdb_client):
        return {
            "renamed": 0,
            "posters_fetched": 0,
            "errors": [],
            "total_items": 0,
        }


class MockJobProcessor:
    """Mock job processor."""

    def start(self):
        pass

    def stop(self):
        pass

    def cancel_job(self, job_id: str):
        pass


class MockWatchTracker:
    """Mock watch tracker."""

    def __init__(self, mpc_client, progress_store):
        self.mpc = mpc_client
        self.progress = progress_store

    def start(self):
        pass

    def stop(self):
        pass


class MockProgressStore:
    """Mock progress store."""

    def __init__(self, file_path: str):
        self.file_path = file_path

    def get(self, path: str) -> dict | None:
        return None

    def save(self, path: str, position_ms: int, duration_ms: int):
        pass


# ── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture
def tmp_env_file(tmp_path):
    """Create a temporary .env file with test values."""
    env_file = tmp_path / ".env"
    env_content = (
        "TMDB_API_KEY=test_tmdb_key_12345\n"
        "REAL_DEBRID_API_KEY=test_rd_key_67890\n"
        "MOVIES_DIR=/tmp/movies\n"
        "TV_DIR=/tmp/tv\n"
        "ANIME_DIR=/tmp/anime\n"
        "DOWNLOADS_DIR=/tmp/downloads\n"
        "MPC_BE_URL=http://127.0.0.1:13579\n"
    )
    env_file.write_text(env_content)
    return env_file


@pytest.fixture
def mock_state(tmp_path, tmp_env_file, monkeypatch):
    """
    Inject mock singletons directly into the real server.state module.

    Routers do ``from .. import state`` which gives them a reference to the
    *actual* module object.  We must set attributes on that same object —
    replacing it in sys.modules (via ``patch("server.state")``) does NOT
    propagate to modules that have already imported it.
    """
    import server.state as state_mod

    # Back up originals so we can restore after the test
    originals = {}
    attrs_to_set = {
        "LOG_FILE": tmp_path / "test.log",
        "PID_FILE": tmp_path / "server.pid",
        "DATA_DIR": tmp_path / "data",
        "ROOT_DIR": tmp_path,
        "ENV_FILE": tmp_env_file,
        "searches": {},
        "SEARCH_TTL": 300,
        "tmdb": MockTMDBClient(),
        "torrentio": MockTorrentioClient(),
        "rd": MockRealDebridClient(),
        "mpc": MockMPCClient(),
        "library": MockLibraryManager(),
        "processor": MockJobProcessor(),
        "progress_store": MockProgressStore(str(tmp_path / "progress.json")),
    }
    # watch_tracker needs mpc + progress_store refs
    attrs_to_set["watch_tracker"] = MockWatchTracker(
        attrs_to_set["mpc"], attrs_to_set["progress_store"]
    )

    for attr, value in attrs_to_set.items():
        originals[attr] = getattr(state_mod, attr, None)
        monkeypatch.setattr(state_mod, attr, value)

    # Also make prune_searches a no-op
    monkeypatch.setattr(state_mod, "prune_searches", lambda: None)

    # Create the data dir so lifespan-like code doesn't fail
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)

    yield state_mod


@pytest.fixture
async def mock_database(tmp_path, monkeypatch):
    """Set up temporary database with schema."""
    db_path = tmp_path / "test.db"

    import server.database as db_mod

    monkeypatch.setattr(db_mod, "DB_PATH", db_path)
    await db_mod.init_db()
    yield db_mod


@pytest.fixture
def test_client(mock_state, mock_database):
    """
    Create FastAPI TestClient with mocked state and a temp database.

    Because ``mock_state`` has already injected mocks into the real
    ``server.state`` module, and ``mock_database`` has redirected
    ``server.database.DB_PATH`` to a temp file, we can safely import
    the app — all routers will pick up the mocked singletons.
    """
    from fastapi.testclient import TestClient
    from server.main import app

    client = TestClient(app, raise_server_exceptions=False)
    yield client


# ── Async Test Support ────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def anyio_backend():
    """Use asyncio as the async backend for pytest-asyncio."""
    return "asyncio"
