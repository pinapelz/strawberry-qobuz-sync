"""Strawberry SQLite schema validation and playlist_items row mapping."""

from __future__ import annotations

import sqlite3
from typing import Any
import uuid

from .models import (
    SONG_FILETYPE_STREAM,
    SONG_SOURCE_QOBUZ,
    QobuzTrack,
    SchemaCompatibilityError,
)


def inspect_and_validate_schema(conn: sqlite3.Connection) -> tuple[set[str], set[str]]:
    """Verify playlists and playlist_items tables and required NOT NULL columns exist."""
    cur = conn.cursor()
    playlists_info = cur.execute("PRAGMA table_info(playlists)").fetchall()
    if not playlists_info:
        raise SchemaCompatibilityError("Table 'playlists' does not exist in strawberry.db.")

    items_info = cur.execute("PRAGMA table_info(playlist_items)").fetchall()
    if not items_info:
        raise SchemaCompatibilityError("Table 'playlist_items' does not exist in strawberry.db.")

    playlists_cols = {row[1] for row in playlists_info}
    items_cols = {row[1] for row in items_info}

    required_playlists_cols = {"name", "last_played", "ui_order", "is_favorite"}
    missing_p = required_playlists_cols - playlists_cols
    if missing_p:
        raise SchemaCompatibilityError(
            f"Table 'playlists' is missing expected columns: {sorted(missing_p)}"
        )

    required_items_cols = {
        "playlist",
        "type",
        "title",
        "artist",
        "album",
        "track",
        "length",
        "source",
        "url",
        "filetype",
        "song_id",
    }
    missing_i = required_items_cols - items_cols
    if missing_i:
        raise SchemaCompatibilityError(
            f"Table 'playlist_items' is missing expected columns: {sorted(missing_i)}"
        )

    supported_playlist_values = {
        "name",
        "last_played",
        "ui_order",
        "special_type",
        "ui_path",
        "is_favorite",
        "dynamic_playlist_type",
        "dynamic_playlist_backend",
        "dynamic_playlist_data",
    }
    for _, col_name, _, notnull, dflt_value, pk in playlists_info:
        if notnull and dflt_value is None and not pk and col_name not in supported_playlist_values:
            raise SchemaCompatibilityError(
                f"Unsupported NOT NULL column without default in 'playlists': {col_name}"
            )

    for _, col_name, _, notnull, dflt_value, pk in items_info:
        if notnull and dflt_value is None and not pk and col_name not in {"playlist", "type"}:
            raise SchemaCompatibilityError(
                f"Unsupported NOT NULL column without default in 'playlist_items': {col_name}"
            )

    return playlists_cols, items_cols


def build_playlist_item_row(
    playlist_rowid: int,
    track: QobuzTrack,
) -> dict[str, Any]:
    """Build a complete row dictionary matching Strawberry 1.2.x Song::BindToQuery."""
    effective_albumartist = track.album_artist or track.artist
    effective_originalyear = track.year if track.year > 0 else -1

    return {
        "playlist": playlist_rowid,
        "type": SONG_SOURCE_QOBUZ,
        "uuid": str(uuid.uuid4()),
        "collection_id": None,
        "playlist_url": None,
        "title": track.title,
        "titlesort": "",
        "album": track.album,
        "albumsort": "",
        "artist": track.artist,
        "artistsort": "",
        "albumartist": track.album_artist,
        "albumartistsort": "",
        "track": track.track_number,
        "disc": track.disc_number,
        "year": track.year,
        "originalyear": -1,
        "genre": track.genre,
        "compilation": track.compilation,
        "composer": track.composer,
        "composersort": "",
        "performer": track.performer,
        "performersort": "",
        "grouping": "",
        "comment": track.comment,
        "lyrics": "",
        "artist_id": track.artist_id,
        "album_id": track.album_id,
        "song_id": track.track_id,
        "beginning": 0,
        "length": track.duration_nanosec,
        "bitrate": -1,
        "samplerate": track.samplerate_hz,
        "bitdepth": track.bitdepth,
        "source": SONG_SOURCE_QOBUZ,
        "directory_id": 0,
        "url": track.url,
        "filetype": SONG_FILETYPE_STREAM,
        "filesize": 0,
        "mtime": 0,
        "ctime": 0,
        "unavailable": 0,
        "fingerprint": "",
        "playcount": 0,
        "skipcount": 0,
        "lastplayed": -1,
        "lastseen": -1,
        "compilation_detected": track.compilation,
        "compilation_on": 0,
        "compilation_off": 0,
        "compilation_effective": track.compilation,
        "art_embedded": 0,
        "art_automatic": track.cover_url,
        "art_manual": "",
        "art_unset": 0,
        "effective_albumartist": effective_albumartist,
        "effective_originalyear": effective_originalyear,
        "cue_path": "",
        "rating": -1,
        "acoustid_id": "",
        "acoustid_fingerprint": "",
        "musicbrainz_album_artist_id": "",
        "musicbrainz_artist_id": "",
        "musicbrainz_original_artist_id": "",
        "musicbrainz_album_id": "",
        "musicbrainz_original_album_id": "",
        "musicbrainz_recording_id": "",
        "musicbrainz_track_id": "",
        "musicbrainz_disc_id": "",
        "musicbrainz_release_group_id": "",
        "musicbrainz_work_id": "",
        "ebur128_integrated_loudness_lufs": None,
        "ebur128_loudness_range_lu": None,
        "bpm": -1.0,
        "mood": "",
        "initial_key": "",
    }
