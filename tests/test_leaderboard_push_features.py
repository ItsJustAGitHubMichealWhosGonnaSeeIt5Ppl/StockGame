from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from helpers.leaderboard_push import (
    bot_can_push_to_channel,
    is_unknown_message_error,
    push_or_edit_leaderboard_message,
)
from helpers.recurring_leaderboard_image import (
    LEADERBOARD_N_CANDIDATES,
    estimate_recurring_leaderboard_height,
    select_leaderboard_n,
    RecurringLeaderboardImageGenerator,
)
from helpers.sqlhelper import _iso8601
from stocks import Backend, GameLogic


def test_height_estimate_scales_with_players_and_picks():
    h5 = estimate_recurring_leaderboard_height(5, 10)
    h10 = estimate_recurring_leaderboard_height(10, 10)
    assert h10 > h5
    with_chips = estimate_recurring_leaderboard_height(1, 20)
    without = estimate_recurring_leaderboard_height(1, 0)
    assert with_chips > without


@pytest.mark.parametrize("n", list(LEADERBOARD_N_CANDIDATES))
def test_select_n_candidates(n):
    picks = [3] * 40
    chosen = select_leaderboard_n(picks, max_height=10_000, target=n)
    assert chosen == n


def test_select_n_respects_height_budget():
    picks = [12] * 30
    chosen = select_leaderboard_n(picks, max_height=1200, target=30)
    assert chosen in LEADERBOARD_N_CANDIDATES
    assert chosen < 30
    assert estimate_recurring_leaderboard_height(chosen, picks[:chosen]) <= 1200


def test_recurring_image_smoke():
    players = [
        {
            "user_id": 1,
            "display_name": "Alice",
            "current_value": 10500,
            "change_dollars": 500,
            "change_percent": 5.0,
            "days_in_first": 2,
            "joined": "2026-01-01",
            "picks": [
                {"ticker": "AAPL", "company": "Apple", "change_percent": 1.2},
                {"ticker": "MSFT", "company": "Microsoft", "change_percent": -0.5},
            ],
        }
    ]
    buf = RecurringLeaderboardImageGenerator().create_image({"name": "Test", "id": "abc"}, players)
    assert buf.getvalue()[:8] == b"\x89PNG\r\n\x1a\n"


def test_days_in_first_idempotent(db_path, mocker):
    be = Backend(db_path)
    be.add_user(1, "discord", "One")
    be.add_user(2, "discord", "Two")
    game_id = be.add_game(
        user_id=1,
        name="Days First Game",
        start_date="2020-01-01",
        starting_money=10000,
        total_picks=2,
    )
    be.update_game(game_id=game_id, status="active")
    be.add_participant(1, game_id)
    be.add_participant(2, game_id)
    p1 = be.get_many_participants(game_id=game_id, user_id=1)[0]
    p2 = be.get_many_participants(game_id=game_id, user_id=2)[0]
    be.update_participant(p1.id, current_value=12000, change_dollars=2000, change_percent=20)
    be.update_participant(p2.id, current_value=9000, change_dollars=-1000, change_percent=-10)

    logic = GameLogic(db_path)
    mocker.patch.object(logic, "_is_market_hours", return_value=False)
    mocker.patch.object(logic, "_today_et", return_value=date(2026, 7, 30))  # Thursday

    logic.record_days_in_first(game_id=game_id)
    logic.record_days_in_first(game_id=game_id)

    leader = be.get_many_participants(game_id=game_id, user_id=1)[0]
    assert leader.days_in_first == 1
    snaps = be.sql.get(
        "leaderboard_day_snapshots",
        filters={"game_id": str(game_id), "trade_date": "2026-07-30"},
    )
    assert snaps.status == "success"
    assert len(snaps.result) == 1


def test_is_unknown_message_error():
    assert is_unknown_message_error(discord.NotFound(MagicMock(), "missing"))
    http = discord.HTTPException(MagicMock(), "Unknown Message")
    http.code = 10008
    assert is_unknown_message_error(http)
    assert not is_unknown_message_error(RuntimeError("boom"))


def test_push_edit_then_resend_on_unknown():
    import asyncio
    from io import BytesIO

    channel = AsyncMock()
    channel.fetch_message = AsyncMock(
        side_effect=discord.NotFound(MagicMock(), {"message": "Unknown Message"})
    )
    partial = AsyncMock()
    channel.get_partial_message = MagicMock(return_value=partial)
    sent = MagicMock()
    sent.id = 555
    channel.send = AsyncMock(return_value=sent)

    game = MagicMock()
    game.id = "g1"
    game.leaderboard_message_id = "111"
    fe = MagicMock()
    fe.be.update_game = MagicMock()

    embed = discord.Embed(title="t")

    async def _run():
        return await push_or_edit_leaderboard_message(
            channel=channel,
            game=game,
            fe=fe,
            embed=embed,
            image=BytesIO(b"fakepng"),
        )

    new_id = asyncio.run(_run())
    assert new_id == "555"
    partial.delete.assert_awaited()
    channel.send.assert_awaited()
    fe.be.update_game.assert_called()


def test_bot_can_push_permissions():
    channel = MagicMock()
    me = MagicMock()
    perms = MagicMock()
    perms.view_channel = True
    perms.send_messages = True
    perms.embed_links = True
    perms.attach_files = True
    channel.permissions_for.return_value = perms
    assert bot_can_push_to_channel(channel, me) is True
    perms.attach_files = False
    assert bot_can_push_to_channel(channel, me) is False
