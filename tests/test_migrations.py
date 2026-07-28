from pathlib import Path
import sqlite3

from helpers.sqlhelper import SqlHelper
from sqlite_creator_real import create, db_ver, upgrade_db


def test_upgrade_preserves_data_for_non_db_filename(db_path):
    create(db_path, upgrade=False)
    sql = SqlHelper(db_path)
    sql.insert("users", {
        "user_id": 9001,
        "source": "testing",
        "datetime_created": "2025-01-01 00:00:00",
    })
    sql.update(
        "database_info",
        {"current_version": "0.0.5"},
        filters={"database_name": db_path},
    )

    backup = upgrade_db(db_path)

    upgraded = SqlHelper(db_path)
    user = upgraded.get("users", filters={"user_id": 9001})
    info = upgraded.get("database_info", filters={"database_name": db_path})
    assert user.status == "success"
    assert info.result[0]["current_version"] == db_ver
    assert Path(backup).is_file()


def test_create_detects_and_upgrades_legacy_database_without_metadata(db_path):
    connection = sqlite3.connect(db_path)
    connection.execute("CREATE TABLE users (user_id INTEGER PRIMARY KEY)")
    connection.execute("INSERT INTO users (user_id) VALUES (77)")
    connection.commit()
    connection.close()

    create(db_path)

    upgraded = SqlHelper(db_path)
    user = upgraded.get("users", filters={"user_id": 77})
    info = upgraded.get("database_info", filters={"database_name": db_path})
    assert user.result[0]["source"] == "Unknown"
    assert info.result[0]["current_version"] == db_ver
