"""
Quality scoring for torrent/stream names.

Scoring philosophy
------------------
Higher = better.  Weights are tuned for a home-theatre setup that prioritises:
  resolution  → 4K > 1080p > 720p
  source      → Remux > BluRay > WEB-DL > WEBRip > HDRip
  HDR         → DV > HDR10+ > HDR10 > SDR
  audio       → Atmos > TrueHD 7.1 > DTS:X > DTS-HD > DD+ (EAC3) > DD
  codec       → HEVC/x265 preferred (smaller file for same quality)
  channels    → 7.1 > 5.1 > stereo
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# Compiled patterns
# ---------------------------------------------------------------------------
_RES = {
    "4k": 2000, "2160p": 2000, "uhd": 1900,
    "1080p": 800, "1080i": 700,
    "720p": 400,
    "576p": 100, "480p": 50,
}

_SOURCE = {
    "remux": 500,
    "bluray": 350, "blu-ray": 350, "blu_ray": 350, "bdrip": 300, "bdremux": 500,
    "web-dl": 250, "webdl": 250,
    "webrip": 180, "web": 150,
    "hdrip": 80, "hdtv": 60,
    "dvdrip": 30, "dvd": 20,
    "cam": -500, "ts": -400, "hdcam": -300,
}

_HDR = {
    "dv": 400, "dolby vision": 400, "dovi": 400,
    "hdr10+": 350,
    "hdr10": 300,
    "hdr": 200,
}

_AUDIO = {
    "atmos": 300, "truehd 7.1": 280, "truehd": 250,
    "dtsx": 240, "dts-x": 240, "dts:x": 240,
    "dts-hd": 200, "dtshd": 200,
    "ddplus": 150, "dd+": 150, "eac3": 150, "eac-3": 150,
    "dts": 120,
    "dd 5.1": 100, "dd5.1": 100, "ac3": 80, "dd": 80,
    "aac": 50,
}

_CHANNELS = {
    "7.1": 60, "5.1": 40, "2.0": 0, "stereo": 0, "mono": -20,
}

_CODEC = {
    "hevc": 50, "x265": 50, "h.265": 50, "h265": 50,
    "av1": 40,
    "avc": 0, "x264": 0, "h.264": 0, "h264": 0,
    "xvid": -50, "divx": -50,
}

# Negative boosts for things we don't want
_NEGATIVE = {
    "cam": -1000, "camrip": -1000,
    "ts ": -800,  # telesync (note space to avoid matching "atmos")
    "r5": -600, "r6": -600,
    "sample": -200,
}


@dataclass
class ScoredStream:
    """A torrent / stream with its computed quality score."""
    name: str                         # raw torrent / stream title
    info_hash: Optional[str] = None   # hex info hash (for building magnets)
    download_url: Optional[str] = None  # pre-resolved RD URL (if available)
    size_bytes: Optional[int] = None
    seeders: Optional[int] = 0

    # Parsed quality flags
    resolution: str = ""
    source: str = ""
    hdr: str = ""
    audio: str = ""
    channels: str = ""
    codec: str = ""
    is_cached_rd: bool = False

    score: int = 0
    quality_str: str = ""    # human-readable quality label e.g. "4K DV Atmos"

    # Seeder bonus (applied after main score)
    _seeder_bonus: int = field(default=0, repr=False)


class QualityScorer:
    """Score and rank a list of ScoredStream objects."""

    def score(self, stream: ScoredStream) -> ScoredStream:
        """Populate *stream.score* and *stream.quality_str* in-place."""
        name_lower = stream.name.lower()
        total = 0
        tags: list[str] = []

        # Prefer cached RD items (available immediately)
        if stream.is_cached_rd:
            total += 1000
            stream.download_url = stream.download_url  # already set

        # --- Resolution ---
        for key, pts in _RES.items():
            if key in name_lower:
                total += pts
                stream.resolution = key.upper().replace("P", "p")
                if key in ("4k", "2160p", "uhd"):
                    tags.append("4K")
                elif "1080" in key:
                    tags.append("1080p")
                elif "720" in key:
                    tags.append("720p")
                break

        # --- Source ---
        for key, pts in _SOURCE.items():
            if key in name_lower:
                total += pts
                stream.source = key
                if "remux" in key:
                    tags.append("Remux")
                elif "blu" in key or "bd" in key:
                    tags.append("BluRay")
                elif "web" in key:
                    tags.append("WEB-DL" if "dl" in key else "WEBRip")
                break

        # --- HDR ---
        for key, pts in _HDR.items():
            if key in name_lower:
                total += pts
                stream.hdr = key
                if "dv" in key or "dolby" in key or "dovi" in key:
                    tags.append("DV")
                elif "hdr10+" in key:
                    tags.append("HDR10+")
                elif "hdr" in key:
                    tags.append("HDR")
                break

        # --- Audio ---
        for key, pts in _AUDIO.items():
            if key in name_lower:
                total += pts
                stream.audio = key
                if "atmos" in key:
                    tags.append("Atmos")
                elif "truehd" in key:
                    tags.append("TrueHD")
                elif "dts" in key:
                    tags.append("DTS-HD" if "hd" in key else "DTS")
                elif "eac3" in key or "dd+" in key or "ddplus" in key:
                    tags.append("DD+")
                break

        # --- Channels ---
        for key, pts in _CHANNELS.items():
            if key in name_lower:
                total += pts
                stream.channels = key
                if key == "7.1":
                    tags.append("7.1")
                elif key == "5.1":
                    tags.append("5.1")
                break

        # --- Codec ---
        for key, pts in _CODEC.items():
            if key in name_lower:
                total += pts
                stream.codec = key
                break

        # --- Negative boosts ---
        for key, pts in _NEGATIVE.items():
            if key in name_lower:
                total += pts

        # --- Seeder bonus (log scale, capped) ---
        if stream.seeders and stream.seeders > 0:
            import math
            bonus = min(int(math.log(stream.seeders + 1) * 10), 100)
            total += bonus

        stream.score = total
        stream.quality_str = " ".join(tags) if tags else "SD"
        return stream

    def rank(self, streams: list[ScoredStream]) -> list[ScoredStream]:
        """Return streams sorted best-first."""
        for s in streams:
            self.score(s)
        return sorted(streams, key=lambda s: s.score, reverse=True)
