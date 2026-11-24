"""Command-line interface for Qobuz -> Strawberry playlist sync."""

from __future__ import annotations

import argparse
import sys

from .config import load_strawberry_credentials, resolve_config_path, resolve_db_path
from .models import MAX_BACKUPS, StrawberryRunningError, SyncError
from .qobuz import QobuzClient
from .safety import ensure_strawberry_not_running
from .syncer import apply_sync


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sync Qobuz playlists into Strawberry Music Player using Strawberry's Qobuz credentials."
    )
    parser.add_argument(
        "--db-path",
        help="Path to strawberry.db (overrides auto-detection).",
    )
    parser.add_argument(
        "--config-path",
        help="Path to strawberry.conf (overrides auto-detection).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)

    try:
        ensure_strawberry_not_running()

        config_path = resolve_config_path(args.config_path)
        db_path = resolve_db_path(args.db_path)
        creds = load_strawberry_credentials(config_path)

        client = QobuzClient(app_id=creds.app_id, user_auth_token=creds.user_auth_token)
        summaries = client.list_user_playlists()
        if not summaries:
            print("No Qobuz playlists found to sync.")
            return 0

        playlists = [client.get_playlist_with_tracks(p.playlist_id) for p in summaries]
        backup_path, results = apply_sync(db_path=db_path, playlists=playlists)

        total_tracks = sum(r.track_count for r in results)
        print(f"Backup created: {backup_path} (retaining last {MAX_BACKUPS} sync backups)")
        for r in results:
            print(f"[{r.action}] {r.name!r} (ROWID={r.rowid}): synced {r.track_count} track(s)")
        print(f"Successfully synced {len(results)} playlist(s) ({total_tracks} tracks) to {db_path}.")
        return 0

    except StrawberryRunningError as exc:
        print(f"WARNING: {exc}", file=sys.stderr)
        return 2
    except SyncError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
