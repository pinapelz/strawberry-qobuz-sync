from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
import shutil
import sqlite3

from .models import MAX_BACKUPS, StrawberryRunningError


def find_running_strawberry_pids(proc_root: Path = Path("/proc")) -> list[int]:
    ignored_pids = {os.getpid(), os.getppid()}
    found_pids: list[int] = []

    if not proc_root.is_dir():
        return []

    for entry in proc_root.iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        if pid in ignored_pids:
            continue
        try:
            comm = (entry / "comm").read_text(encoding="utf-8", errors="replace").strip()
            raw_cmd = (entry / "cmdline").read_bytes()
        except OSError:
            continue

        argv = [part.decode("utf-8", errors="replace") for part in raw_cmd.split(b"\x00") if part]
        exe_name = Path(argv[0]).name if argv else ""

        if comm == "strawberry" or exe_name == "strawberry":
            found_pids.append(pid)
        elif exe_name == "bwrap" and "org.strawberrymusicplayer.strawberry" in argv:
            found_pids.append(pid)

    return sorted(set(found_pids))


def ensure_strawberry_not_running(proc_root: Path = Path("/proc")) -> None:
    pids = find_running_strawberry_pids(proc_root=proc_root)
    if pids:
        pid_list = ", ".join(str(p) for p in pids)
        raise StrawberryRunningError(
            f"Strawberry Music Player is currently running (PID: {pid_list}). "
            "Please close Strawberry before syncing so SQLite locks or overwrites are avoided."
        )


def create_timestamped_backup(db_path: Path, keep: int = MAX_BACKUPS) -> Path:
    now = datetime.now()
    stamp = now.strftime("%Y%m%d_%H%M%S")
    backup_path = db_path.with_name(f"{db_path.name}.qobuz-sync-{stamp}.bak")
    if backup_path.exists():
        stamp_precise = now.strftime("%Y%m%d_%H%M%S_%f")
        backup_path = db_path.with_name(f"{db_path.name}.qobuz-sync-{stamp_precise}.bak")

    src_conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        dst_conn = sqlite3.connect(backup_path)
        try:
            src_conn.backup(dst_conn)
        finally:
            dst_conn.close()
    finally:
        src_conn.close()

    shutil.copymode(db_path, backup_path)

    pattern = f"{db_path.name}.qobuz-sync-*.bak"
    existing_backups = sorted(
        db_path.parent.glob(pattern),
        key=lambda p: (p.stat().st_mtime_ns, p.name),
        reverse=True,
    )
    for stale in existing_backups[keep:]:
        stale.unlink(missing_ok=True)

    return backup_path
