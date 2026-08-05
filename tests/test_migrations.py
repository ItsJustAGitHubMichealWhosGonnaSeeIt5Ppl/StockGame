from pathlib import Path
import sqlite3

from helpers.db_backup import create_db_backup, prune_backups, maybe_daily_backup
from helpers.sqlhelper import SqlHelper
from sqlite_creator_real import create, db_ver, remake_db_on_mismatch


def test_create_fresh_database_has_current_version(db_path):
    create(db_path, upgrade=False)
    info = SqlHelper(db_path).get("database_info", filters={"database_name": db_path})
    assert info.status == "success"
    assert info.result[0]["current_version"] == db_ver
    conn = sqlite3.connect(db_path)
    try:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(game_templates)")}
    finally:
        conn.close()
    assert "push_leaderboard" in cols
    assert "leaderboard_channel_id" in cols


def test_remake_on_version_mismatch_backs_up_and_wipes(db_path):
    create(db_path, upgrade=False)
    sql = SqlHelper(db_path)
    sql.insert(
        "users",
        {
            "user_id": 9001,
            "source": "testing",
            "datetime_created": "2025-01-01 00:00:00",
        },
    )
    sql.update(
        "database_info",
        {"current_version": "0.0.5"},
        filters={"database_name": db_path},
    )

    backup = remake_db_on_mismatch(db_path)

    assert backup is not None
    assert Path(backup).is_file()
    rebuilt = SqlHelper(db_path)
    user = rebuilt.get("users", filters={"user_id": 9001})
    assert user.status == "error"
    info = rebuilt.get("database_info", filters={"database_name": db_path})
    assert info.result[0]["current_version"] == db_ver


def test_create_remakes_legacy_database_without_metadata(db_path):
    connection = sqlite3.connect(db_path)
    connection.execute("CREATE TABLE users (user_id INTEGER PRIMARY KEY)")
    connection.execute("INSERT INTO users (user_id) VALUES (77)")
    connection.commit()
    connection.close()

    create(db_path)

    rebuilt = SqlHelper(db_path)
    user = rebuilt.get("users", filters={"user_id": 77})
    assert user.status == "error"  # wiped
    info = rebuilt.get("database_info", filters={"database_name": db_path})
    assert info.result[0]["current_version"] == db_ver


def test_backup_prune_retention(db_path, tmp_path):
    create(db_path, upgrade=False)
    stem = Path(db_path).stem
    for _ in range(5):
        path = create_db_backup(db_path, kind="hourly")
        assert path is not None
    removed = prune_backups(db_path, kind="hourly", keep=2)
    assert removed >= 3
    remaining = [
        p
        for p in Path(db_path).resolve().parent.joinpath("backups").glob(f"{stem}-hourly-*.db")
    ]
    assert len(remaining) == 2


def test_maybe_daily_backup_once_per_day(db_path):
    create(db_path, upgrade=False)
    first = maybe_daily_backup(db_path)
    second = maybe_daily_backup(db_path)
    assert first is not None
    assert second is None
