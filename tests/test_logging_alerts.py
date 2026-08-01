"""Logging setup, dual files, and CRITICAL Discord DM routing."""

from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from helpers.logging_setup import (
    CRITICAL_ALERT_USER_IDS,
    attach_critical_dm_bot,
    flush_critical_dm_queue,
    get_critical_handler,
    latest_log_path,
    log_intentional,
    log_unexpected,
    prepare_log_for_upload,
    reset_logging_for_tests,
    setup_app_logging,
)


ALLOWED_CRITICAL_USER = 329374393715392520


@pytest.fixture(autouse=True)
def _clean_logging(tmp_path, monkeypatch):
    """Isolate logging config and files per test."""
    reset_logging_for_tests()
    monkeypatch.chdir(tmp_path)
    yield
    reset_logging_for_tests()


def _ready_bot(*, users: dict[int, MagicMock] | None = None):
    """Minimal bot stand-in for CriticalDmHandler."""
    users = users or {}
    bot = MagicMock()
    bot.is_ready.return_value = True
    bot.loop = asyncio.new_event_loop()
    bot.get_user.side_effect = lambda uid: users.get(uid)

    async def _fetch(uid: int):
        if uid in users:
            return users[uid]
        raise LookupError(f"unknown user {uid}")

    bot.fetch_user = AsyncMock(side_effect=_fetch)
    return bot


def test_critical_alert_recipients_are_hardcoded_allowlist_only():
    assert CRITICAL_ALERT_USER_IDS == [ALLOWED_CRITICAL_USER]
    assert ALLOWED_CRITICAL_USER not in (0, None)
    assert len(CRITICAL_ALERT_USER_IDS) == 1


def test_dual_log_files_split_levels(tmp_path):
    setup_app_logging(log_dir=str(tmp_path / "logs"), force=True, console_level=logging.CRITICAL)
    logger = logging.getLogger("TestDualLogs")

    logger.debug("dbg-line")
    logger.info("info-line")
    logger.warning("warn-line")
    logger.error("err-line")
    logger.critical("crit-line")

    for handler in logging.getLogger().handlers:
        handler.flush()

    debug_path = latest_log_path("debug", log_dir=str(tmp_path / "logs"))
    error_path = latest_log_path("error", log_dir=str(tmp_path / "logs"))
    assert debug_path is not None and error_path is not None

    debug_text = debug_path.read_text(encoding="utf-8")
    error_text = error_path.read_text(encoding="utf-8")

    assert "dbg-line" in debug_text
    assert "info-line" in debug_text
    assert "err-line" in debug_text
    assert "crit-line" in debug_text

    assert "dbg-line" not in error_text
    assert "info-line" not in error_text
    assert "err-line" in error_text
    assert "crit-line" in error_text


def test_log_intentional_and_unexpected_helpers(tmp_path):
    log_dir = tmp_path / "logs"
    setup_app_logging(log_dir=str(log_dir), force=True, console_level=logging.CRITICAL)
    logger = logging.getLogger("HelperLogs")

    log_intentional(logger, "user joined game", user_id=42, command="join", game="G1")
    log_unexpected(
        logger,
        "unexpected failure",
        user_id=42,
        command="buy",
        exc=RuntimeError("boom"),
    )
    for handler in logging.getLogger().handlers:
        handler.flush()

    debug_text = latest_log_path("debug", log_dir=str(log_dir)).read_text(encoding="utf-8")
    error_text = latest_log_path("error", log_dir=str(log_dir)).read_text(encoding="utf-8")
    assert "user joined game" in debug_text
    assert "command=join" in debug_text
    assert "unexpected failure" in error_text
    assert "command=buy" in error_text


def test_info_and_error_do_not_dm(tmp_path):
    setup_app_logging(log_dir=str(tmp_path / "logs"), force=True, console_level=logging.CRITICAL)
    allowed = MagicMock()
    allowed.send = AsyncMock()
    bot = _ready_bot(users={ALLOWED_CRITICAL_USER: allowed})
    # Force queue path so INFO/ERROR never even schedule deliveries
    bot.is_ready.return_value = False
    attach_critical_dm_bot(bot)

    logging.getLogger("NoDm").info("info should not DM")
    logging.getLogger("NoDm").error("error should not DM")

    handler = get_critical_handler()
    assert handler is not None
    assert handler._pending == []
    allowed.send.assert_not_called()
    bot.loop.close()


def test_critical_dm_only_to_allowlisted_user(tmp_path):
    setup_app_logging(log_dir=str(tmp_path / "logs"), force=True, console_level=logging.CRITICAL)

    allowed = MagicMock()
    allowed.send = AsyncMock()
    stranger = MagicMock()
    stranger.send = AsyncMock()

    bot = _ready_bot(
        users={
            ALLOWED_CRITICAL_USER: allowed,
            111111111111111111: stranger,
        }
    )
    # Queue then flush — avoids same-thread run_coroutine_threadsafe races
    bot.is_ready.return_value = False
    attach_critical_dm_bot(bot)
    handler = get_critical_handler()
    assert handler is not None
    assert handler.user_ids == [ALLOWED_CRITICAL_USER]

    logging.getLogger("CritPath").critical("simulated CRITICAL operational failure")
    assert len(handler._pending) == 1

    bot.is_ready.return_value = True
    bot.loop.run_until_complete(flush_critical_dm_queue())

    allowed.send.assert_awaited()
    stranger.send.assert_not_called()
    fetch_ids = [c.args[0] for c in bot.fetch_user.await_args_list]
    get_ids = [c.args[0] for c in bot.get_user.call_args_list]
    assert all(uid == ALLOWED_CRITICAL_USER for uid in fetch_ids + get_ids)

    content = allowed.send.await_args.args[0]
    assert "CRITICAL alert" in content
    assert "simulated CRITICAL operational failure" in content

    bot.loop.close()


def test_critical_queued_before_ready_then_flushed_only_to_allowlist(tmp_path):
    setup_app_logging(log_dir=str(tmp_path / "logs"), force=True, console_level=logging.CRITICAL)

    allowed = MagicMock()
    allowed.send = AsyncMock()
    bot = MagicMock()
    bot.is_ready.return_value = False
    bot.loop = None
    bot.get_user.side_effect = lambda uid: allowed if uid == ALLOWED_CRITICAL_USER else None
    bot.fetch_user = AsyncMock(return_value=allowed)

    attach_critical_dm_bot(bot)
    logging.getLogger("EarlyCrit").critical("queued before bot ready")

    handler = get_critical_handler()
    assert handler is not None
    assert len(handler._pending) == 1
    allowed.send.assert_not_called()

    bot.is_ready.return_value = True
    bot.loop = asyncio.new_event_loop()
    bot.loop.run_until_complete(flush_critical_dm_queue())

    allowed.send.assert_awaited_once()
    assert handler._pending == []
    content = allowed.send.await_args.args[0]
    assert "queued before bot ready" in content
    bot.loop.close()


def test_critical_dm_failure_is_logged_not_raised(tmp_path):
    log_dir = tmp_path / "logs"
    setup_app_logging(log_dir=str(log_dir), force=True, console_level=logging.CRITICAL)

    flaky = MagicMock()
    flaky.send = AsyncMock(side_effect=RuntimeError("DM blocked"))
    bot = _ready_bot(users={ALLOWED_CRITICAL_USER: flaky})
    attach_critical_dm_bot(bot)

    bot.loop.run_until_complete(
        get_critical_handler()._deliver("delivery-failure-test")  # type: ignore[union-attr]
    )
    for handler in logging.getLogger().handlers:
        handler.flush()

    error_text = latest_log_path("error", log_dir=str(log_dir)).read_text(encoding="utf-8")
    assert "Failed to DM CRITICAL alert" in error_text
    assert str(ALLOWED_CRITICAL_USER) in error_text
    bot.loop.close()


def test_discord_bot_critical_paths_use_allowlisted_logging(tmp_path, monkeypatch):
    """Exercise discord_bot CRITICAL login/token messages without connecting to Discord."""
    monkeypatch.setenv("DISCORD_TOKEN", "fake-token-for-tests")
    monkeypatch.setenv("DB_NAME", str(tmp_path / "bot_test.sqlite"))
    monkeypatch.setenv("OWNER", str(ALLOWED_CRITICAL_USER))

    from sqlite_creator_real import create

    create(str(tmp_path / "bot_test.sqlite"))

    import importlib
    import sys

    sys.modules.pop("discord_bot", None)
    import discord_bot as db

    importlib.reload(db)

    allowed = MagicMock()
    allowed.send = AsyncMock()
    bot = _ready_bot(users={ALLOWED_CRITICAL_USER: allowed})
    bot.is_ready.return_value = False
    reset_logging_for_tests()
    setup_app_logging(log_dir=str(tmp_path / "logs"), force=True, console_level=logging.CRITICAL)
    attach_critical_dm_bot(bot)

    db.logger.critical(
        "Discord login failed: invalid DISCORD_TOKEN. Check .env / secrets.",
    )
    db.logger.critical("DISCORD_TOKEN environment variable not found. Bot cannot start.")

    bot.is_ready.return_value = True
    bot.loop.run_until_complete(flush_critical_dm_queue())
    assert allowed.send.await_count == 2
    for call in allowed.send.await_args_list:
        assert "CRITICAL alert" in call.args[0]
    bot.loop.close()


def test_prepare_log_for_upload_truncates(tmp_path):
    path = tmp_path / "big.log"
    path.write_bytes(b"x" * 5000 + b"\nKEEP_TAIL\n")
    buf, name, truncated, original, uploaded = prepare_log_for_upload(path, max_bytes=200)
    assert truncated is True
    assert original == path.stat().st_size
    assert uploaded <= 200
    assert b"KEEP_TAIL" in buf.getvalue()
    assert name.endswith("_tail.log")


def test_latest_log_path_none_when_missing(tmp_path):
    assert latest_log_path("debug", log_dir=str(tmp_path / "empty")) is None
