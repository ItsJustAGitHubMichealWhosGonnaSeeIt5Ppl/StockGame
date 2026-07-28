from helpers.sqlhelper import SqlHelper


def test_insert_many_inserts_all_rows(db_path):
    sql = SqlHelper(db_path)
    sql.send_query("CREATE TABLE samples (id INTEGER PRIMARY KEY, name TEXT NOT NULL)", mode="insert")

    result = sql._insert_many(
        "samples",
        columns=["id", "name"],
        rows=[{"id": 1, "name": "one"}, {"id": 2, "name": "two"}],
    )

    assert result.status == "success"
    rows = sql.get("samples")
    assert rows.status == "success"
    assert rows.result == ({"id": 1, "name": "one"}, {"id": 2, "name": "two"})


def test_update_requires_force_without_filters(db_path):
    sql = SqlHelper(db_path)
    sql.send_query("CREATE TABLE samples (id INTEGER PRIMARY KEY, name TEXT NOT NULL)", mode="insert")
    sql.insert("samples", {"id": 1, "name": "one"})

    blocked = sql.update("samples", {"name": "changed"})
    assert blocked.status == "error"
    assert blocked.reason == "FORCE REQUIRED"

    applied = sql.update("samples", {"name": "changed"}, force=True)
    assert applied.status == "success"


def test_delete_table_uses_current_schema_allowlist(db_path):
    sql = SqlHelper(db_path)
    sql.send_query("CREATE TABLE users (id INTEGER PRIMARY KEY)", mode="insert")

    result = sql.delete_table("users", force=True)

    assert result.status == "success"
    missing = sql.get("users")
    assert missing.status == "error"
