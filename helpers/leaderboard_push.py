"""Build and post/edit recurring leaderboard push messages in Discord."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from io import BytesIO
from typing import Any, Optional

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
        title=f"📈 {game.name}",
        description=(
            f"Game pot moved **${d_chg:+,.2f}** (**{p_chg:+.2f}%**).\n"
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
    embed.set_image(url="attachment://recurring_leaderboard.png")
    return embed


def collect_push_payload(fe, game) -> tuple[discord.Embed, BytesIO, list[dict]]:
    """Load leaderboard + pick chips and return embed, image buffer, player dicts."""
    info = fe.game_info(game.id, show_leaderboard=True)
    leaderboard = info.leaderboard or []
    players: list[dict] = []
    owned_pcts: list[dict] = []

    for entry in leaderboard:
        try:
            participants = fe.be.get_many_participants(game_id=game.id, user_id=entry.user_id)
            participant = participants[0]
        except LookupError:
            continue
        picks_data: list[dict] = []
        try:
            picks = fe.be.get_many_stock_picks(
                participant_id=participant.id,
                status=["owned", "pending_buy", "pending_sell"],
                include_tickers=True,
            )
        except LookupError:
            picks = []
        for pick in picks:
            ticker = pick.stock_ticker or "?"
            company = getattr(pick, "company_name", None) or ticker
            pct = float(pick.change_percent or 0)
            picks_data.append(
                {
                    "ticker": ticker,
                    "company": company,
                    "company_name": company,
                    "change_percent": pct,
                }
            )
            if pick.status == "owned":
                owned_pcts.append({"ticker": ticker, "pct": pct})
        players.append(
            {
                "user_id": entry.user_id,
                "display_name": entry.display_name or f"ID({entry.user_id})",
                "current_value": entry.current_value,
                "change_dollars": entry.change_dollars,
                "change_percent": entry.change_percent,
                "days_in_first": getattr(entry, "days_in_first", 0) or 0,
                "joined": entry.joined,
                "picks": picks_data,
            }
        )

    best = max(owned_pcts, key=lambda x: x["pct"]) if owned_pcts else None
    worst = min(owned_pcts, key=lambda x: x["pct"]) if owned_pcts else None
    embed = build_push_embed(game, best_pick=best, worst_pick=worst)
    game_data = {"name": game.name, "id": game.id}
    buffer = RecurringLeaderboardImageGenerator().create_image(game_data, players, target_n=10)
    return embed, buffer, players


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


async def push_or_edit_leaderboard_message(
    *,
    channel: discord.TextChannel,
    game,
    fe,
    embed: discord.Embed,
    image: BytesIO,
) -> Optional[str]:
    """
    Edit stored message in-place; on unknown message, delete (ignore fail) then send new.

    Returns new/kept message id string, or None on failure.
    """
    filename = "recurring_leaderboard.png"
    file = discord.File(image, filename=filename)
    message_id = getattr(game, "leaderboard_message_id", None)

    if message_id:
        try:
            msg = await channel.fetch_message(int(message_id))
            # Re-seek in case prior attempt consumed the buffer
            image.seek(0)
            file = discord.File(image, filename=filename)
            await msg.edit(embed=embed, attachments=[file])
            return str(msg.id)
        except Exception as exc:
            if not is_unknown_message_error(exc):
                logger.warning(
                    "Leaderboard edit failed (will retry next cycle) game=%s: %s",
                    game.id,
                    exc,
                )
                return message_id
            try:
                msg = channel.get_partial_message(int(message_id))
                await msg.delete()
            except Exception:
                logger.debug("Could not delete stale leaderboard message %s", message_id, exc_info=True)

    image.seek(0)
    file = discord.File(image, filename=filename)
    try:
        sent = await channel.send(embed=embed, file=file)
    except Exception as exc:
        logger.warning("Leaderboard send failed for game %s: %s", game.id, exc)
        return None
    try:
        fe.be.update_game(game_id=game.id, leaderboard_message_id=str(sent.id))
    except Exception:
        logger.exception("Failed to persist leaderboard_message_id for game %s", game.id)
    return str(sent.id)


async def push_all_recurring_leaderboards(bot: discord.Client, fe) -> None:
    """Push/edit leaderboards for active games whose templates have push enabled."""
    try:
        games = fe.be.get_many_games(include_open=False, include_active=True, include_private=True)
    except LookupError:
        return

    for game in games:
        if not game.template_id:
            continue
        try:
            template = fe.be.get_game_template(game.template_id)
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
            embed, image, _ = collect_push_payload(fe, game)
            # Refresh game row for message id
            game = fe.be.get_game(game.id)
            await push_or_edit_leaderboard_message(
                channel=channel,
                game=game,
                fe=fe,
                embed=embed,
                image=image,
            )
        except Exception:
            logger.exception("Recurring leaderboard push failed for game %s", game.id)
