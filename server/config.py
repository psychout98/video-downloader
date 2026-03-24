import os
from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field, model_validator
from pydantic_settings import SettingsConfigDict

# Absolute path to the project .env — two levels up from this file (server/config.py)
_ENV_FILE = Path(__file__).parent.parent / ".env"
_DATA_DIR = Path(__file__).parent.parent / "data"


def _userprofile(subdir: str) -> str:
    r"""Primary media dir: resolves %USERPROFILE%\Media\<subdir> at runtime."""
    return str(Path(os.path.expandvars("%USERPROFILE%")) / "Media" / subdir)


def _default_media_dir() -> str:
    return str(Path(os.path.expandvars("%USERPROFILE%")) / "Media")


class Settings(BaseSettings):
    # --- Required API keys ---
    TMDB_API_KEY: str = Field(..., description="TMDB v3 API key")
    REAL_DEBRID_API_KEY: str = Field(..., description="Real-Debrid API key")

    # --- New unified directory settings ---
    MEDIA_DIR: str = Field(default_factory=_default_media_dir,
                           description="Primary media directory (flat, with [tmdb_id] folders)")
    ARCHIVE_DIR: str = Field("D:\\Media",
                             description="Archive directory (watched content moved here)")

    # --- Legacy directory settings (kept for migration) ---
    MOVIES_DIR: str = Field(default_factory=lambda: _userprofile("Movies"))
    TV_DIR: str = Field(default_factory=lambda: _userprofile("TV Shows"))
    ANIME_DIR: str = Field(default_factory=lambda: _userprofile("Anime"))
    MOVIES_DIR_ARCHIVE: str = Field("D:\\Media\\Movies")
    TV_DIR_ARCHIVE: str = Field("D:\\Media\\TV Shows")
    ANIME_DIR_ARCHIVE: str = Field("D:\\Media\\Anime")

    # Temporary download staging area
    DOWNLOADS_DIR: str = Field(default_factory=lambda: _userprofile(r"Downloads\.staging"))

    # Central poster cache — inside the data/ folder
    POSTERS_DIR: str = Field(default_factory=lambda: str(_DATA_DIR / "posters"))

    # Per-file watch-progress database (JSON) — inside the data/ folder
    # (legacy, kept for migration — progress now lives in SQLite)
    PROGRESS_FILE: str = Field(default_factory=lambda: str(_DATA_DIR / "playback.json"))

    # How much of a file must be watched before it's archived (0.0 – 1.0)
    WATCH_THRESHOLD: float = Field(0.85, description="Fraction of runtime considered 'watched'")

    # --- Server ---
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # --- Download behaviour ---
    MAX_CONCURRENT_DOWNLOADS: int = 2
    CHUNK_SIZE: int = 8 * 1024 * 1024  # 8 MB chunks

    # How many seconds to poll Real-Debrid while waiting for a non-cached torrent
    RD_POLL_INTERVAL: int = 30

    # --- MPC-BE web interface (local on HTPC) ---
    MPC_BE_URL: str = Field("http://127.0.0.1:13579", description="MPC-BE web interface base URL")
    MPC_BE_EXE: str = Field(
        r"C:\Program Files\MPC-BE x64\mpc-be64.exe",
        description="Full path to the MPC-BE executable (used to launch it when closed)",
    )

    # --- Migration flag ---
    MIGRATED: bool = Field(False, description="Set to true after migration to new layout")

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",  # ignore unknown keys in .env (e.g. leftover SECRET_KEY)
    )


settings = Settings()


def reload_settings() -> None:
    """Re-read the .env file and update the module-level settings object in-place."""
    import logging
    new = Settings()
    settings.__dict__.update(new.__dict__)
    logging.getLogger(__name__).info(
        "Settings reloaded — REAL_DEBRID_API_KEY ends with …%s",
        settings.REAL_DEBRID_API_KEY[-6:] if settings.REAL_DEBRID_API_KEY else "(empty)"
    )
