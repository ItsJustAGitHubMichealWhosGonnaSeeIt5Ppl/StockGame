"""Build and post/edit recurring leaderboard push messages in Discord.

Top 20 players are split across up to four messages (5 players each). The game
title appears only on the first image; the stats embed always sits on the last
message. Extra messages are deleted when the player count shrinks.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from io import BytesIO
from typing import Any, Awaitable, Callable, Optional

import discord
import pytz

from helpers.recurring_leaderboard_image import RecurringLeaderboardImageGenerator

logger = logging.getLogger("LeaderboardPush")

PUSH_PERMS = (
    discord.Permissions.view_channel,
    discord.Permissions.send_messages,
    discord.Permissions.embed_links,
    discord.Permissions.attach_files,
)

PUSH_PAGE_SIZE = 5
PUSH_MAX_PLAYERS = 20


def bot_can_push_to_channel(channel: discord.abc.GuildChannel, me: discord.Member) -> bool:
    """Return True if the bot can view, send, embed, and attach in ``channel``."""
    perms = channel.permissions_for(me)
    return bool(
        perms.view_channel
        and perms.send_messages
        and perms.embed_links
        and perms.attach_files
    )


def _et_now() -> datetime:
    return datetime.now(pytz.timezone("America/New_York"))


def _format_hours_line(game) -> str:
    now = _et_now().replace(tzinfo=None)
    start = datetime.combine(game.start_date, datetime.min.time())
    elapsed = max(0, int((now - start).total_seconds() // 3600))
    if game.end_date is None:
        return f"{elapsed}h elapsed · ongoing"
    end = datetime.combine(game.end_date, datetime.max.time().replace(microsecond=0))
    remaining = int((end - now).total_seconds() // 3600)
    if remaining < 0:
        return f"{elapsed}h elapsed · ended"
    return f"{elapsed}h elapsed · {remaining}h remaining"


def build_push_embed(game, *, best_pick: Optional[dict] = None, worst_pick: Optional[dict] = None) -> discord.Embed:
    """Short playful stats embed for a recurring leaderboard push."""
    d_chg = float(game.change_dollars or 0)
    p_chg = float(game.change_percent or 0)
    embed = discord.Embed(
        title=f"{'📈' if d_chg >= 0 else '📉'} {game.name} (ID: {game.id})",
        description=(
            f"The fund is {('up' if d_chg >= 0 else 'down')} **${d_chg:+,.2f}** (**{p_chg:+.2f}%**) this month.\n"
            f"{_format_hours_line(game)}"
        ),
        color=discord.Color.green() if d_chg >= 0 else discord.Color.red(),
    )
    if best_pick:
        embed.add_field(
            name="Best owned pick",
            value=f"`{best_pick['ticker']}` {best_pick['pct']:+.2f}%",
            inline=True,
        )
    if worst_pick:
        embed.add_field(
            name="Worst owned pick",
            value=f"`{worst_pick['ticker']}` {worst_pick['pct']:+.2f}%",
            inline=True,
        )
    embed.set_footer(text=f"Last updated · {_et_now().strftime('%Y-%m-%d %H:%M')} ET")
    return embed


def collect_player_picks(fe, game_id, user_id: int) -> Optional[list[dict]]:
    """Chip data for one player's holdings, or None when they are not a participant."""
    try:
        participant = fe.be.get_many_participants(game_id=game_id, user_id=user_id)[0]
    except LookupError:
        return None
    try:
        picks = fe.be.get_many_stock_picks(
            participant_id=participant.id,
            status=["owned", "pending_buy", "pending_sell"],
            include_tickers=True,
        )
    except LookupError:
        return []
    picks_data: list[dict] = []
    for pick in picks:
        ticker = pick.stock_ticker or "?"
        company = getattr(pick, "company_name", None) or ticker
        picks_data.append(
            {
                "ticker": ticker,
                "company": company,
                "company_name": company,
                "change_percent": float(pick.change_percent or 0),
                "status": pick.status,
            }
        )
    return picks_data


def collect_push_players(fe, game) -> tuple[list[dict], list[dict]]:
    """Load the leaderboard plus each player's pick chips.

    Returns the player rows and every owned pick's percent change, so the caller
    can resolve live Discord names before the image is rendered.
    """
    info = fe.game_info(game.id, show_leaderboard=True)
    leaderboard = info.leaderboard or []
    players: list[dict] = []
    owned_pcts: list[dict] = []

    for entry in leaderboard:
        picks_data = collect_player_picks(fe, game.id, entry.user_id)
        if picks_data is None:
            continue
        for pick in picks_data:
            if pick["status"] == "owned":
                owned_pcts.append({"ticker": pick["ticker"], "pct": pick["change_percent"]})
        players.append(
            {
                "user_id": entry.user_id,
                "display_name": f"ID({entry.user_id})",
                "current_value": entry.current_value,
                "change_dollars": entry.change_dollars,
                "change_percent": entry.change_percent,
                "days_in_first": getattr(entry, "days_in_first", 0) or 0,
                "joined": entry.joined,
                "picks": picks_data,
            }
        )

    return players, owned_pcts


def parse_leaderboard_message_ids(raw: Optional[str]) -> list[str]:
    """Split a stored comma-separated message-id list into individual snowflakes."""
    if not raw:
        return []
    return [part.strip() for part in str(raw).split(",") if part.strip()]


def serialize_leaderboard_message_ids(message_ids: list[str]) -> Optional[str]:
    """Join message ids for storage, or None when the list is empty."""
    cleaned = [str(message_id).strip() for message_id in message_ids if str(message_id).strip()]
    return ",".join(cleaned) if cleaned else None


def chunk_push_players(
    players: list[dict],
    *,
    page_size: int = PUSH_PAGE_SIZE,
    max_players: int = PUSH_MAX_PLAYERS,
) -> list[list[dict]]:
    """Split the top N players into ordered pages of ``page_size``.

    Always returns at least one page so an empty game still gets the stats embed.
    """
    trimmed = list(players[:max_players])
    if not trimmed:
        return [[]]
    return [trimmed[i : i + page_size] for i in range(0, len(trimmed), page_size)]


def render_push_pages(
    game,
    players: list[dict],
    owned_pcts: list[dict],
    *,
    created_at: Optional[datetime] = None,
) -> tuple[discord.Embed, list[BytesIO]]:
    """Build the stats embed plus one PNG buffer per leaderboard page."""
    best = max(owned_pcts, key=lambda x: x["pct"]) if owned_pcts else None
    worst = min(owned_pcts, key=lambda x: x["pct"]) if owned_pcts else None
    embed = build_push_embed(game, best_pick=best, worst_pick=worst)
    stamp = created_at or _et_now()
    game_data = {"name": game.name, "id": game.id}
    generator = RecurringLeaderboardImageGenerator()
    images: list[BytesIO] = []

    for page_index, page in enumerate(chunk_push_players(players)):
        ranked_page: list[dict] = []
        for offset, player in enumerate(page):
            row = dict(player)
            row["rank"] = page_index * PUSH_PAGE_SIZE + offset + 1
            ranked_page.append(row)
        images.append(
            generator.create_image(
                game_data,
                ranked_page,
                target_n=max(len(ranked_page), 1),
                show_title=False,
                created_at=stamp,
            )
        )
    return embed, images


def render_push_payload(game, players: list[dict], owned_pcts: list[dict]) -> tuple[discord.Embed, BytesIO]:
    """Compatibility wrapper: embed plus the first page image."""
    embed, images = render_push_pages(game, players, owned_pcts)
    return embed, images[0]


def is_unknown_message_error(exc: BaseException) -> bool:
    """True when Discord says the message is gone / not editable."""
    if isinstance(exc, discord.NotFound):
        return True
    if isinstance(exc, discord.HTTPException):
        # 10008 Unknown Message
        code = getattr(exc, "code", None)
        if code == 10008:
            return True
        text = str(exc).lower()
        if "unknown message" in text:
            return True
    return False


async def _delete_message_quiet(channel: discord.TextChannel, message_id: str) -> None:
    try:
        await channel.get_partial_message(int(message_id)).delete()
    except Exception:
        logger.debug("Could not delete leaderboard message %s", message_id, exc_info=True)


async def _upsert_leaderboard_page(
    *,
    channel: discord.TextChannel,
    message_id: Optional[str],
    embed: Optional[discord.Embed],
    image: BytesIO,
    filename: str,
    game_id: Any,
) -> Optional[str]:
    """Edit one page in place, or send a new message when missing/unknown."""
    image.seek(0)
    file = discord.File(image, filename=filename)
    edit_kwargs: dict[str, Any] = {"attachments": [file]}
    if embed is None:
        edit_kwargs["embeds"] = []
    else:
        edit_kwargs["embed"] = embed

    if message_id:
        try:
            msg = await channel.fetch_message(int(message_id))
            image.seek(0)
            edit_kwargs["attachments"] = [discord.File(image, filename=filename)]
            await msg.edit(**edit_kwargs)
            return str(msg.id)
        except Exception as exc:
            if not is_unknown_message_error(exc):
                logger.warning(
                    "Leaderboard page edit failed (will retry next cycle) game=%s msg=%s: %s",
                    game_id,
                    message_id,
                    exc,
                )
                return message_id
            await _delete_message_quiet(channel, message_id)

    image.seek(0)
    file = discord.File(image, filename=filename)
    try:
        if embed is None:
            sent = await channel.send(file=file)
        else:
            sent = await channel.send(embed=embed, file=file)
    except Exception as exc:
        logger.warning("Leaderboard page send failed for game %s: %s", game_id, exc)
        return None
    return str(sent.id)


async def push_or_edit_leaderboard_message(
    *,
    channel: discord.TextChannel,
    game,
    fe,
    embed: discord.Embed,
    image: BytesIO,
) -> Optional[str]:
    """Compatibility wrapper for a single-image push."""
    return await push_or_edit_leaderboard_messages(
        channel=channel,
        game=game,
        fe=fe,
        embed=embed,
        images=[image],
    )


async def push_or_edit_leaderboard_messages(
    *,
    channel: discord.TextChannel,
    game,
    fe,
    embed: discord.Embed,
    images: list[BytesIO],
) -> Optional[str]:
    """
    Sync one Discord message per image page.

    The embed is attached only to the last page. Existing messages are edited in
    place; missing pages are sent; leftover messages from a smaller roster are
    deleted. Stored ids are a comma-separated list in ``leaderboard_message_id``.
    """
    if not images:
        images = [BytesIO()]

    existing = parse_leaderboard_message_ids(getattr(game, "leaderboard_message_id", None))
    new_ids: list[str] = []

    for index, image in enumerate(images):
        is_last = index == len(images) - 1
        filename = (
            "recurring_leaderboard.png"
            if len(images) == 1
            else f"recurring_leaderboard_{index + 1}.png"
        )
        page_id = await _upsert_leaderboard_page(
            channel=channel,
            message_id=existing[index] if index < len(existing) else None,
            embed=embed if is_last else None,
            image=image,
            filename=filename,
            game_id=game.id,
        )
        if page_id is None:
            # Keep whatever we already synced; leave extras for the next cycle.
            if new_ids:
                try:
                    fe.be.update_game(
                        game_id=game.id,
                        leaderboard_message_id=serialize_leaderboard_message_ids(new_ids),
                    )
                except Exception:
                    logger.exception(
                        "Failed to persist partial leaderboard_message_id for game %s",
                        game.id,
                    )
            return serialize_leaderboard_message_ids(new_ids)
        new_ids.append(page_id)

    for stale_id in existing[len(new_ids) :]:
        await _delete_message_quiet(channel, stale_id)

    serialized = serialize_leaderboard_message_ids(new_ids)
    try:
        if serialized is None:
            fe.be.update_game(game_id=game.id, clear_leaderboard_message=True)
        else:
            fe.be.update_game(game_id=game.id, leaderboard_message_id=serialized)
    except Exception:
        logger.exception("Failed to persist leaderboard_message_id for game %s", game.id)
    return serialized


async def push_all_recurring_leaderboards(
    bot: discord.Client,
    fe,
    name_resolver: Optional[Callable[[int, Optional[discord.Guild]], Awaitable[str]]] = None,
) -> None:
    """Push/edit leaderboards for active games whose templates have push enabled.

    ``name_resolver`` maps a user id + guild to the name shown on the image; when
    omitted, rows fall back to ``ID(...)``.
    """
    try:
        games = await asyncio.to_thread(
            fe.be.get_many_games,
            include_open=False,
            include_active=True,
            include_private=True,
        )
    except LookupError:
        return

    for game in games:
        if not game.template_id:
            continue
        try:
            template = await asyncio.to_thread(fe.be.get_game_template, game.template_id)
        except LookupError:
            continue
        if not template.push_leaderboard or not template.leaderboard_channel_id:
            continue
        channel_id = int(template.leaderboard_channel_id)
        channel = bot.get_channel(channel_id)
        if channel is None:
            try:
                channel = await bot.fetch_channel(channel_id)
            except Exception as exc:
                logger.warning("Cannot fetch push channel %s: %s", channel_id, exc)
                continue
        if not isinstance(channel, discord.TextChannel):
            logger.warning("Push channel %s is not a text channel", channel_id)
            continue
        guild = channel.guild
        me = guild.me if guild else None
        if me is None:
            continue
        if not bot_can_push_to_channel(channel, me):
            logger.warning(
                "Missing push permissions in channel %s for game %s; skipping",
                channel_id,
                game.id,
            )
            continue
        try:
            players, owned_pcts = await asyncio.to_thread(collect_push_players, fe, game)
            if name_resolver is not None:
                for player in players:
                    try:
                        player["display_name"] = await name_resolver(int(player["user_id"]), guild)
                    except Exception:
                        logger.debug("Name lookup failed for user %s", player["user_id"])
            embed, images = await asyncio.to_thread(
                render_push_pages, game, players, owned_pcts
            )
            # Refresh game row for message ids
            game = await asyncio.to_thread(fe.be.get_game, game.id)
            await push_or_edit_leaderboard_messages(
                channel=channel,
                game=game,
                fe=fe,
                embed=embed,
                images=images,
            )
        except Exception:
            logger.exception("Recurring leaderboard push failed for game %s", game.id)
