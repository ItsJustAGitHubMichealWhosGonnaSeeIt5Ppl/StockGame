#!/bin/sh
# Docker entrypoint: ensure data dirs exist, create SQLite DB if missing, then run CMD.
set -e

mkdir -p /app/data /app/data/backups /app/logs

prepare_database() {
  if [ -z "${DB_NAME:-}" ]; then
    echo "DB_NAME is not set; refusing to start." >&2
    exit 1
  fi
  db_dir=$(dirname "$DB_NAME")
  if [ "$db_dir" != "." ]; then
    mkdir -p "$db_dir"
  fi
  mkdir -p "$(dirname "$DB_NAME")/backups" 2>/dev/null || mkdir -p /app/data/backups
  if [ ! -f "$DB_NAME" ]; then
    echo "No database at ${DB_NAME}; creating schema..."
    python3 sqlite_creator_real.py
  fi
}

if [ "$(id -u)" = "0" ]; then
  # Bind-mounted ./data is often owned by the host user; make it writable for appuser.
  chown -R appuser:appuser /app/data /app/logs 2>/dev/null || true
  if [ -n "${DB_NAME:-}" ]; then
    db_dir=$(dirname "$DB_NAME")
    if [ "$db_dir" != "." ]; then
      mkdir -p "$db_dir"
      chown appuser:appuser "$db_dir" 2>/dev/null || true
    fi
  fi
  gosu appuser sh -ec '
    mkdir -p /app/data /app/data/backups /app/logs
    if [ -z "${DB_NAME:-}" ]; then
      echo "DB_NAME is not set; refusing to start." >&2
      exit 1
    fi
    db_dir=$(dirname "$DB_NAME")
    if [ "$db_dir" != "." ]; then
      mkdir -p "$db_dir" "$db_dir/backups"
    fi
    if [ ! -f "$DB_NAME" ]; then
      echo "No database at ${DB_NAME}; creating schema..."
      python3 sqlite_creator_real.py
    fi
  '
  exec gosu appuser "$@"
fi

prepare_database
exec "$@"
