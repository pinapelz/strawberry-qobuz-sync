from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import requests

from .models import (
    DEFAULT_PLAYLIST_PAGE_LIMIT,
    DEFAULT_TRACK_PAGE_LIMIT,
    QOBUZ_API_BASE,
    QobuzAPIError,
    QobuzPlaylist,
    QobuzTrack,
)


class QobuzClient:
    def __init__(
        self,
        app_id: str,
        user_auth_token: str,
        base_url: str = QOBUZ_API_BASE,
        session: requests.Session | None = None,
        timeout: float = 20.0,
    ) -> None:
        self.app_id = app_id
        self.user_auth_token = user_auth_token
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = session or requests.Session()

    def _headers(self) -> dict[str, str]:
        return {
            "X-App-Id": self.app_id,
            "X-User-Auth-Token": self.user_auth_token,
            "Accept": "application/json",
            "User-Agent": "qobuz-strawberry-sync/0.1",
        }

    def _request(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        try:
            resp = self.session.get(
                url=url,
                headers=self._headers(),
                params=params,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise QobuzAPIError(f"Network error calling Qobuz {endpoint}: {exc}") from exc

        if resp.status_code >= 400:
            detail = ""
            try:
                err_json = resp.json()
                detail = err_json.get("message") or err_json.get("status") or str(err_json)
            except ValueError:
                detail = resp.text[:200].strip()
            raise QobuzAPIError(
                f"Qobuz API {endpoint} failed with HTTP {resp.status_code}: {detail}"
            )

        try:
            payload = resp.json()
        except ValueError as exc:
            raise QobuzAPIError(f"Invalid JSON response from Qobuz {endpoint}") from exc

        if not isinstance(payload, dict):
            raise QobuzAPIError(f"Unexpected non-object JSON payload from Qobuz {endpoint}")
        return payload

    def list_user_playlists(
        self,
        page_limit: int = DEFAULT_PLAYLIST_PAGE_LIMIT,
    ) -> list[QobuzPlaylist]:
        playlists: list[QobuzPlaylist] = []
        offset = 0
        authenticated_user_id: int | None = None

        while True:
            payload = self._request(
                "playlist/getUserPlaylists",
                params={"limit": page_limit, "offset": offset},
            )
            user_obj = payload.get("user")
            if isinstance(user_obj, dict) and user_obj.get("id") is not None:
                try:
                    authenticated_user_id = int(user_obj["id"])
                except (TypeError, ValueError):
                    pass

            container = payload.get("playlists")
            if not isinstance(container, dict):
                raise QobuzAPIError("Qobuz playlist/getUserPlaylists response missing 'playlists'.")

            items = container.get("items") or []
            total = int(container.get("total") or 0)
            if not items:
                break

            for raw in items:
                owner = raw.get("owner") or {}
                owner_id = int(owner["id"]) if owner.get("id") is not None else None
                if authenticated_user_id is not None and owner_id != authenticated_user_id:
                    continue
                playlists.append(
                    QobuzPlaylist(
                        playlist_id=int(raw["id"]),
                        name=str(raw.get("name") or f"Playlist {raw['id']}"),
                        tracks_count=int(raw.get("tracks_count") or 0),
                        owner_id=owner_id,
                        owner_name=str(owner.get("name") or ""),
                        is_public=bool(raw.get("is_public", False)),
                        description=str(raw.get("description") or ""),
                    )
                )

            offset += len(items)
            if offset >= total:
                break

        return playlists

    def get_playlist_with_tracks(
        self,
        playlist_id: int,
        page_limit: int = DEFAULT_TRACK_PAGE_LIMIT,
    ) -> QobuzPlaylist:
        tracks: list[QobuzTrack] = []
        offset = 0
        playlist_meta: QobuzPlaylist | None = None

        while True:
            payload = self._request(
                "playlist/get",
                params={
                    "playlist_id": playlist_id,
                    "extra": "tracks",
                    "limit": page_limit,
                    "offset": offset,
                },
            )
            if playlist_meta is None:
                owner = payload.get("owner") or {}
                owner_id = int(owner["id"]) if owner.get("id") is not None else None
                playlist_meta = QobuzPlaylist(
                    playlist_id=int(payload.get("id", playlist_id)),
                    name=str(payload.get("name") or f"Playlist {playlist_id}"),
                    tracks_count=int(payload.get("tracks_count") or 0),
                    owner_id=owner_id,
                    owner_name=str(owner.get("name") or ""),
                    is_public=bool(payload.get("is_public", False)),
                    description=str(payload.get("description") or ""),
                )

            tracks_container = payload.get("tracks")
            if not isinstance(tracks_container, dict):
                break

            items = tracks_container.get("items") or []
            total = int(tracks_container.get("total") or 0)
            if not items:
                break

            for raw_track in items:
                parsed = parse_qobuz_track(raw_track)
                if parsed is not None:
                    tracks.append(parsed)

            offset += len(items)
            if offset >= total:
                break

        assert playlist_meta is not None
        playlist_meta.tracks = tracks
        playlist_meta.tracks_count = len(tracks)
        return playlist_meta


def _parse_release_year(album_obj: dict[str, Any], track_obj: dict[str, Any]) -> int:
    released_at = album_obj.get("released_at")
    if released_at is not None:
        try:
            return datetime.fromtimestamp(int(released_at), tz=timezone.utc).year
        except (TypeError, ValueError, OSError, OverflowError):
            pass

    for key in ("release_date_original", "release_date_stream"):
        date_str = track_obj.get(key) or album_obj.get(key)
        if isinstance(date_str, str) and len(date_str) >= 4 and date_str[:4].isdigit():
            return int(date_str[:4])

    return -1


def parse_qobuz_track(raw: dict[str, Any]) -> QobuzTrack | None:
    if not isinstance(raw, dict) or raw.get("id") is None:
        return None

    track_id = str(raw["id"])
    title = str(raw.get("title") or "").strip() or f"Track {track_id}"

    album_obj = raw.get("album") if isinstance(raw.get("album"), dict) else {}
    album_id = str(album_obj["id"]) if album_obj.get("id") is not None else ""
    album_title = str(album_obj.get("title") or "").strip()

    album_artist_obj = (
        album_obj.get("artist") if isinstance(album_obj.get("artist"), dict) else {}
    )
    album_artist_name = str(album_artist_obj.get("name") or "").strip()
    album_artist_id = (
        str(album_artist_obj["id"]) if album_artist_obj.get("id") is not None else ""
    )

    performer_obj = raw.get("performer") if isinstance(raw.get("performer"), dict) else {}
    performer_name = str(performer_obj.get("name") or "").strip()
    performer_id = str(performer_obj["id"]) if performer_obj.get("id") is not None else ""

    composer_obj = raw.get("composer") if isinstance(raw.get("composer"), dict) else {}
    composer_name = str(composer_obj.get("name") or "").strip()

    artist_name = performer_name or album_artist_name
    artist_id = performer_id or album_artist_id

    genre_obj = album_obj.get("genre") if isinstance(album_obj.get("genre"), dict) else {}
    genre_name = str(genre_obj.get("name") or "").strip()

    image_obj = album_obj.get("image") if isinstance(album_obj.get("image"), dict) else {}
    cover_url = str(
        image_obj.get("large") or image_obj.get("small") or image_obj.get("thumbnail") or ""
    ).strip()

    track_number = int(raw.get("track_number") or -1)
    disc_number = int(raw.get("media_number") or 0)
    duration_seconds = int(raw.get("duration") or 0)
    year = _parse_release_year(album_obj, raw)
    comment = str(raw.get("copyright") or "").strip()

    raw_sr = raw.get("maximum_sampling_rate") or album_obj.get("maximum_sampling_rate")
    samplerate_hz = int(float(raw_sr) * 1000) if raw_sr else -1

    raw_bd = raw.get("maximum_bit_depth") or album_obj.get("maximum_bit_depth")
    bitdepth = int(raw_bd) if raw_bd else -1

    compilation = 1 if album_artist_name.lower() == "various artists" else 0

    return QobuzTrack(
        track_id=track_id,
        title=title,
        artist=artist_name,
        artist_id=artist_id,
        album=album_title,
        album_id=album_id,
        album_artist=album_artist_name if album_artist_name != artist_name else "",
        track_number=track_number,
        disc_number=disc_number,
        duration_seconds=duration_seconds,
        year=year,
        genre=genre_name,
        composer=composer_name,
        performer=performer_name,
        comment=comment,
        cover_url=cover_url,
        samplerate_hz=samplerate_hz,
        bitdepth=bitdepth,
        compilation=compilation,
    )
