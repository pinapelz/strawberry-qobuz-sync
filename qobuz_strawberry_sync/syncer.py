"""Atomic SQLite playlist sync execution."""

from __future__ import annotations

from pathlib import Path
import sqlite3

from .db import build_playlist_item_row, inspect_and_validate_schema
from .models import MAX_BACKUPS, QobuzPlaylist, SyncResult
from .safety import create_timestamped_backup, ensure_strawberry_not_running


def apply_sync(
    db_path: Path,
    playlists: list[QobuzPlaylist],
    keep_backups: int = MAX_BACKUPS,
    proc_root: Path = Path("/proc"),
) -> tuple[Path, list[SyncResult]]:
    """Safely back up strawberry.db and atomically upsert playlists and playlist_items."""
    ensure_strawberry_not_running(proc_root=proc_root)

    # Validate schema read-only before creating a backup or writing
    ro_conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        inspect_and_validate_schema(ro_conn)
    finally:
        ro_conn.close()

    backup_path = create_timestamped_backup(db_path, keep=keep_backups)

    conn = sqlite3.connect(db_path)
    try:
        playlists_cols, items_cols = inspect_and_validate_schema(conn)
        ordered_item_cols = [
            col[1]
            for col in conn.execute("PRAGMA table_info(playlist_items)").fetchall()
            if col[1] in items_cols
        ]

        results: list[SyncResult] = []
        with conn:
            cur = conn.cursor()
            max_order_row = cur.execute(
                "SELECT COALESCE(MAX(ui_order), -1) FROM playlists WHERE ui_order >= 0"
            ).fetchone()
            next_ui_order = int(max_order_row[0]) + 1

            for pl in playlists:
                existing = cur.execute(
                    "SELECT ROWID, ui_order, is_favorite FROM playlists WHERE name = ? ORDER BY ROWID ASC LIMIT 1",
                    (pl.name,),
                ).fetchone()

                if existing is not None:
                    action = "UPDATE"
                    playlist_rowid = int(existing[0])
                    current_order = int(existing[1]) if existing[1] is not None else -1
                    ui_order = current_order if current_order >= 0 else next_ui_order
                    if current_order < 0:
                        next_ui_order += 1
                    is_fav = 1 if (existing[2] or 1) else 1

                    update_assignments = {
                        "last_played": -1,
                        "ui_order": ui_order,
                        "is_favorite": is_fav,
                        "dynamic_playlist_type": 0,
                        "dynamic_playlist_backend": None,
                        "dynamic_playlist_data": None,
                    }
                    usable_updates = {
                        k: v for k, v in update_assignments.items() if k in playlists_cols
                    }
                    set_clause = ", ".join(f"{k} = ?" for k in usable_updates)
                    cur.execute(
                        f"UPDATE playlists SET {set_clause} WHERE ROWID = ?",
                        (*usable_updates.values(), playlist_rowid),
                    )
                else:
                    action = "INSERT"
                    ui_order = next_ui_order
                    next_ui_order += 1
                    insert_playlist = {
                        "name": pl.name,
                        "last_played": -1,
                        "ui_order": ui_order,
                        "special_type": None,
                        "ui_path": None,
                        "is_favorite": 1,
                        "dynamic_playlist_type": 0,
                        "dynamic_playlist_backend": None,
                        "dynamic_playlist_data": None,
                    }
                    usable_pcols = [k for k in insert_playlist if k in playlists_cols]
                    placeholders = ", ".join("?" for _ in usable_pcols)
                    col_list = ", ".join(usable_pcols)
                    cur.execute(
                        f"INSERT INTO playlists ({col_list}) VALUES ({placeholders})",
                        tuple(insert_playlist[k] for k in usable_pcols),
                    )
                    assert cur.lastrowid is not None
                    playlist_rowid = int(cur.lastrowid)

                cur.execute(
                    "DELETE FROM playlist_items WHERE playlist = ?",
                    (playlist_rowid,),
                )

                if pl.tracks:
                    sample_row = build_playlist_item_row(playlist_rowid, pl.tracks[0])
                    insert_cols = [c for c in ordered_item_cols if c in sample_row]
                    col_sql = ", ".join(insert_cols)
                    val_sql = ", ".join("?" for _ in insert_cols)
                    rows_to_insert = [
                        tuple(
                            build_playlist_item_row(playlist_rowid, track)[c]
                            for c in insert_cols
                        )
                        for track in pl.tracks
                    ]
                    cur.executemany(
                        f"INSERT INTO playlist_items ({col_sql}) VALUES ({val_sql})",
                        rows_to_insert,
                    )

                results.append(
                    SyncResult(
                        name=pl.name,
                        action=action,
                        rowid=playlist_rowid,
                        track_count=len(pl.tracks),
                    )
                )

        return backup_path, results
    finally:
        conn.close()
