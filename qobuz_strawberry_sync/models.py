"""Shared constants, exceptions, and data models."""

from __future__ import annotations

from dataclasses import dataclass, field

QOBUZ_API_BASE = "https://www.qobuz.com/api.json/0.2"
DEFAULT_TRACK_PAGE_LIMIT = 500
DEFAULT_PLAYLIST_PAGE_LIMIT = 50
MAX_BACKUPS = 3

# Strawberry 1.2.x (schema_version 25) enum constants from src/core/song.h:
#   Song::Source::Qobuz = 8
#   Song::FileType::Stream = 91
SONG_SOURCE_QOBUZ = 8
SONG_FILETYPE_STREAM = 91
NSEC_PER_SEC = 1_000_000_000


class SyncError(Exception):
    """Base error for Qobuz-to-Strawberry sync failures."""


class ConfigError(SyncError):
    """Raised when required Strawberry config, DB, or credentials cannot be resolved."""


class QobuzAPIError(SyncError):
    """Raised when the Qobuz v0.2 API returns an error or unexpected payload."""


class StrawberryRunningError(SyncError):
    """Raised when Strawberry Music Player is currently running."""


class SchemaCompatibilityError(SyncError):
    """Raised when strawberry.db is missing expected tables or columns."""


@dataclass(frozen=True)
class Credentials:
    app_id: str
    user_auth_token: str


@dataclass(frozen=True)
class QobuzTrack:
    track_id: str
    title: str
    artist: str
    artist_id: str
    album: str
    album_id: str
    album_artist: str
    track_number: int
    disc_number: int
    duration_seconds: int
    year: int
    genre: str
    composer: str
    performer: str
    comment: str
    cover_url: str
    samplerate_hz: int
    bitdepth: int
    compilation: int = 0

    @property
    def duration_nanosec(self) -> int:
        return max(0, self.duration_seconds) * NSEC_PER_SEC

    @property
    def url(self) -> str:
        # Strawberry's QobuzRequest::ParseSong produces "qobuz:<track_id>"
        return f"qobuz:{self.track_id}"


@dataclass
class QobuzPlaylist:
    playlist_id: int
    name: str
    tracks_count: int
    owner_id: int | None
    owner_name: str
    is_public: bool = False
    description: str = ""
    tracks: list[QobuzTrack] = field(default_factory=list)


@dataclass(frozen=True)
class SyncResult:
    name: str
    action: str  # "INSERT" or "UPDATE"
    rowid: int
    track_count: int
