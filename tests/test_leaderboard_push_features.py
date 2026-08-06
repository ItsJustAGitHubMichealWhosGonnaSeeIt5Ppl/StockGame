from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from helpers.leaderboard_push import (
    bot_can_push_to_channel,
    build_push_embed,
    is_unknown_message_error,
    push_or_edit_leaderboard_message,
)
from helpers.recurring_leaderboard_image import (
    LEADERBOARD_N_CANDIDATES,
    estimate_recurring_leaderboard_height,
    select_leaderboard_n,
    sort_picks_by_performance,
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


def test_picks_sorted_best_first():
    picks = [
        {"ticker": "AAA", "change_percent": -4.0},
        {"ticker": "BBB", "change_percent": 12.5},
        {"ticker": "CCC", "change_percent": None},
        {"ticker": "DDD", "change_percent": 3.0},
    ]
    assert [p["ticker"] for p in sort_picks_by_performance(picks)] == ["BBB", "DDD", "CCC", "AAA"]


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


def test_push_payload_renders_top_five(mocker):
    from io import BytesIO

    import helpers.leaderboard_push as lp

    generator = mocker.patch.object(lp, "RecurringLeaderboardImageGenerator")
    generator.return_value.create_image.return_value = BytesIO(b"png")
    game = SimpleNamespace(
        name="Recurring",
        id="REC01",
        change_dollars=100,
        change_percent=1,
        start_date=date.today(),
        end_date=None,
    )
    players = [{"user_id": user_id} for user_id in range(10)]

    _embed, image = lp.render_push_payload(game, players, [])

    assert image.getvalue() == b"png"
    assert generator.return_value.create_image.call_args.kwargs["target_n"] == 5


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


def test_push_embed_does_not_embed_leaderboard_attachment():
    game = MagicMock()
    game.name = "Example"
    game.change_dollars = 100
    game.change_percent = 1
    game.start_date = date.today()
    game.end_date = None

    embed = build_push_embed(game)

    assert embed.image.url is None


def test_push_edits_standalone_attachment_in_place():
    import asyncio
    from io import BytesIO

    message = AsyncMock()
    message.id = 111
    channel = AsyncMock()
    channel.fetch_message = AsyncMock(return_value=message)
    game = MagicMock(id="g1", leaderboard_message_id="111")

    new_id = asyncio.run(
        push_or_edit_leaderboard_message(
            channel=channel,
            game=game,
            fe=MagicMock(),
            embed=discord.Embed(title="stats"),
            image=BytesIO(b"fakepng"),
        )
    )

    assert new_id == "111"
    message.edit.assert_awaited_once()
    kwargs = message.edit.await_args.kwargs
    assert kwargs["embed"].image.url is None
    assert len(kwargs["attachments"]) == 1
    assert kwargs["attachments"][0].filename == "recurring_leaderboard.png"


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


def test_push_uses_live_name_resolver():
    import asyncio
    from io import BytesIO

    import helpers.leaderboard_push as lp

    game = MagicMock()
    game.id = "g1"
    game.template_id = 7
    template = MagicMock()
    template.push_leaderboard = 1
    template.leaderboard_channel_id = "42"

    fe = MagicMock()
    fe.be.get_many_games.return_value = [game]
    fe.be.get_game_template.return_value = template
    fe.be.get_game.return_value = game

    channel = MagicMock(spec=discord.TextChannel)
    channel.guild = MagicMock()
    bot = MagicMock()
    bot.get_channel.return_value = channel

    rendered: dict = {}

    def fake_render(_game, players, _owned):
        rendered["players"] = [dict(p) for p in players]
        return discord.Embed(title="t"), BytesIO(b"png")

    async def resolver(_user_id, _guild):
        return "LiveName"

    with patch.object(lp, "collect_push_players", return_value=([{"user_id": 5, "display_name": "ID(5)"}], [])), \
         patch.object(lp, "render_push_payload", side_effect=fake_render), \
         patch.object(lp, "bot_can_push_to_channel", return_value=True), \
         patch.object(lp, "push_or_edit_leaderboard_message", new=AsyncMock(return_value="1")):
        asyncio.run(lp.push_all_recurring_leaderboards(bot, fe, name_resolver=resolver))

    assert rendered["players"][0]["display_name"] == "LiveName"


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
