"""SQLite backup helpers for StockGame (online-safe via sqlite3.backup)."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional

from helpers.sqlhelper import SqlHelper

logger = logging.getLogger("DbBackup")

BackupKind = Literal["remake", "daily", "hourly"]

_RETENTION = {"remake": 10, "daily": 7, "hourly": 24}


def backups_dir_for(db_name: str) -> Path:
    """Return ``<db_parent>/backups`` (e.g. ``data/backups``)."""
    parent = Path(db_name).resolve().parent
    path = parent / "backups"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S-%f")


def create_db_backup(
    db_name: str,
    *,
    kind: BackupKind,
    label: Optional[str] = None,
) -> Optional[Path]:
    """
    Create an online backup of ``db_name`` under ``data/backups/``.

    Returns the backup path, or None if the source file does not exist.
    """
    source = Path(db_name)
    if not source.is_file() or source.stat().st_size <= 0:
        return None

    dest_dir = backups_dir_for(db_name)
    stem = source.stem
    extra = f"-{label}" if label else ""
    dest = dest_dir / f"{stem}-{kind}{extra}-{_stamp()}.db"

    helper = SqlHelper(str(source))
    helper.create_backup(str(dest), display_progress=False)
    logger.info("Created %s backup: %s", kind, dest)
    prune_backups(db_name, kind=kind)
    return dest


def prune_backups(
    db_name: str,
    *,
    kind: BackupKind,
    keep: Optional[int] = None,
) -> int:
    """Delete older backups of ``kind`` beyond retention. Returns files removed."""
    retention = keep if keep is not None else _RETENTION[kind]
    dest_dir = backups_dir_for(db_name)
    stem = Path(db_name).stem
    matches = sorted(
        (
            p
            for p in dest_dir.iterdir()
            if p.is_file()
            and p.name.startswith(f"{stem}-{kind}-")
            and p.suffix == ".db"
        ),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    removed = 0
    for path in matches[retention:]:
        try:
            path.unlink()
            removed += 1
        except OSError as exc:
            logger.warning("Failed to prune backup %s: %s", path, exc)
    return removed


def maybe_daily_backup(db_name: str) -> Optional[Path]:
    """Create a daily backup if none exists for today's calendar date."""
    dest_dir = backups_dir_for(db_name)
    stem = Path(db_name).stem
    today = datetime.now().strftime("%Y%m%d")
    for path in dest_dir.iterdir():
        if path.is_file() and path.name.startswith(f"{stem}-daily-") and today in path.name:
            return None
    return create_db_backup(db_name, kind="daily")


def maybe_hourly_backup(db_name: str) -> Optional[Path]:
    """Create an hourly backup if none exists for the current hour."""
    dest_dir = backups_dir_for(db_name)
    stem = Path(db_name).stem
    hour_key = datetime.now().strftime("%Y%m%d-%H")
    for path in dest_dir.iterdir():
        if path.is_file() and path.name.startswith(f"{stem}-hourly-") and hour_key in path.name:
            return None
    return create_db_backup(db_name, kind="hourly")
