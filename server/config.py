import os
from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field


def _userprofile(subdir: str) -> str:
    """Primary media dir: resolves %USERPROFILE%\Media\<subdir> at runtime."""
    return str(Path(os.path.expandvars("%USERPROFILE%")) / "Media" / subdir)


class Settings(BaseSettings):
    # --- Required API keys ---
    TMDB_API_KEY: str = Field(..., description="TMDB v3 API key")
    REAL_DEBRID_API_KEY: str = Field(..., description="Real-Debrid API key")

    # --- Optional webhook auth (set to secure your Siri shortcut endpoint) ---
    SECRET_KEY: str = Field("change-me", description="Bearer token for webhook auth")

    # --- Primary media dirs (fast NVMe — new downloads land here) ---
    MOVIES_DIR: str = Field(default_factory=lambda: _userprofile("Movies"))
    TV_DIR: str = Field(default_factory=lambda: _userprofile("TV Shows"))
    ANIME_DIR: str = Field(default_factory=lambda: _userprofile("Anime"))

    # Temporary download staging area
    DOWNLOADS_DIR: str = Field(default_factory=lambda: _userprofile(r"Downloads\.staging"))

    # Central poster cache — all poster.jpg files live here, named after their title folder
    # e.g. %USERPROFILE%\Media\Posters\Inception (2010).jpg
    POSTERS_DIR: str = Field(default_factory=lambda: _userprofile("Posters"))

    # Per-file watch-progress database (JSON)
    PROGRESS_FILE: str = Field(default_factory=lambda: _userprofile("progress.json"))

    # --- Archive media dirs (SATA — watched content is moved here) ---
    MOVIES_DIR_ARCHIVE: str = Field("D:\\Media\\Movies")
    TV_DIR_ARCHIVE: str = Field("D:\\Media\\TV Shows")
    ANIME_DIR_ARCHIVE: str = Field("D:\\Media\\Anime")

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

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
