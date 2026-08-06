#!/bin/sh
# Docker entrypoint: ensure data dirs exist and are writable, then run CMD.
# Database create / migrate / remake is handled by discord_bot.py (db_schema.ensure_database).
set -e

mkdir -p /app/data /app/data/backups /app/logs

prepare_dirs() {
  if [ -z "${DB_NAME:-}" ]; then
    echo "DB_NAME is not set; refusing to start." >&2
    exit 1
  fi
  db_dir=$(dirname "$DB_NAME")
  if [ "$db_dir" != "." ]; then
    mkdir -p "$db_dir" "$db_dir/backups"
  else
    mkdir -p /app/data/backups
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
  '
  exec gosu appuser "$@"
fi

prepare_dirs
exec "$@"
