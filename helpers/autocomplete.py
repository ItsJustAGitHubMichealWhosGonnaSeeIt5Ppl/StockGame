# WRITTEN MOSTLY BY CLAUDE

import logging
import re

import discord
from discord.app_commands import Choice # Explicitly import Choice for clarity
from discord.interactions import Interaction # Explicitly import Interaction for clarity
from helpers.alpaca_client import to_db_ticker
from helpers.datatype_validation import StockPick
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from stocks import Frontend

_fe: 'Frontend | None' = None
logger = logging.getLogger(__name__)

# Matches buy_stock's effective ticker length (DB form uses '-' for class shares).
_TICKER_RE = re.compile(r"^[A-Z]{1,5}(?:[.\-][A-Z]{1,2})?$")


def init_autocomplete(fe_instance: 'Frontend') -> None:
    """Inject the Frontend instance shared with the main bot module."""
    global _fe
    _fe = fe_instance


def _normalize_typed_ticker(current: str) -> str | None:
    """Return a DB-form ticker if ``current`` looks like a symbol the user can buy."""
    raw = current.strip().upper().replace(" ", "")
    if not raw or not _TICKER_RE.match(raw):
        return None
    ticker = to_db_ticker(raw)
    if len(ticker) > 5:
        return None
    return ticker

# Autocomplete function for stock symbols based on user's stocks in a specific game
async def sell_ticker_autocomplete(
    interaction: Interaction,
    current: str,
) -> list[Choice[str]]:
    """Autocomplete function to show user's stocks for the selected game"""
    try:
        # Get the current game_id value from the interaction
        # This accesses the partially filled command parameters
        game_id: str | None = None
        if interaction.data and 'options' in interaction.data:
            for option in interaction.data.get('options', []):
                if option['name'] == 'game_id':
                    value = option.get('value')
                    game_id = value if isinstance(value, str) else None
                    break

        # If no game_id is entered yet, return empty list
        if not isinstance(game_id, str) or not game_id:
            return []

        if _fe is None:
            return []

        # Get user's stocks for the specific game
        user_stocks: tuple[StockPick] = _fe.my_stocks(
            user_id=interaction.user.id,
            game_id=game_id,
            show_pending=True,
            show_sold=False
        )

        # Filter stocks based on current input and convert to choices
        choices = []
        seen_tickers = set()  # Avoid duplicate tickers

        for stock in user_stocks:
            ticker: str | None = stock.stock_ticker

            if not isinstance(ticker, str):
                continue

            # Skip if we've already added this ticker
            if ticker in seen_tickers:
                continue
            seen_tickers.add(ticker)

            # Add status indicator
            status_indicator = ""
            if hasattr(stock, 'status'):
                if stock.status == 'pending_buy':
                    status_indicator = " [PENDING BUY]"

            display_name: str = ticker + status_indicator

            # Filter based on current input (search in ticker and company name)
            search_text = ticker.lower()
            if current.lower() in search_text:
                choices.append(Choice(
                    name=display_name[:100],  # Discord limits choice names to 100 chars
                    value=ticker
                ))

        # Return up to 25 choices (Discord's limit)
        return choices[:25]

    except (LookupError, AttributeError) as e:
        # User has no stocks in this game or game doesn't exist
        return []
    except Exception:
        # Handle any other errors gracefully
        logger.debug('Stock-pick autocomplete failed.', exc_info=True)
        return []


async def buy_ticker_autocomplete(
    interaction: Interaction,
    current: str,
) -> list[Choice[str]]:
    """Suggest local tickers, and always offer the typed symbol if valid.

    Discord clients generally require selecting an autocomplete choice. Without
    including the typed ticker, symbols not already in the DB cannot be bought.
    """
    try:
        if _fe is None:
            return []

        choices: list[Choice[str]] = []
        seen: set[str] = set()

        typed = _normalize_typed_ticker(current)
        if typed:
            # First choice = exactly what the user typed (may not be in DB yet).
            choices.append(Choice(name=f"{typed} (verify on buy)", value=typed))
            seen.add(typed)

        needle = current.strip().lower()
        try:
            stocks = _fe.be.get_many_stocks()
        except LookupError:
            stocks = ()

        for stock in stocks:
            ticker = str(stock.ticker)
            company_name = str(getattr(stock, "company", "") or "")
            if needle and needle not in ticker.lower() and needle not in company_name.lower():
                continue
            if ticker in seen:
                # Prefer the richer DB label over the generic typed entry.
                choices = [
                    Choice(
                        name=(f"{ticker} — {company_name}" if company_name else ticker)[:100],
                        value=ticker,
                    )
                    if c.value == ticker
                    else c
                    for c in choices
                ]
                continue
            seen.add(ticker)
            label = f"{ticker} — {company_name}" if company_name else ticker
            choices.append(Choice(name=label[:100], value=ticker))
            if len(choices) >= 25:
                break

        return choices[:25]
    except Exception:
        logger.debug('Buy-ticker autocomplete failed.', exc_info=True)
        # Last resort: still allow the typed ticker through.
        typed = _normalize_typed_ticker(current)
        if typed:
            return [Choice(name=typed, value=typed)]
        return []

# Autocomplete function for game_id parameter
async def game_id_autocomplete(
    interaction: Interaction,
    current: str,
    owner_only: bool = False
) -> list[Choice[str]]:
    """Autocomplete function to show user's games

    Args:
        interaction: Discord interaction
        current: Current user input
        owner_only: If True, only show games where user is the owner
    """
    try:
        if _fe is None:
            return []

        # Get user's games using the frontend command
        user_games = _fe.my_games(interaction.user.id, include_ended=False)

        # Filter games based on current input and convert to choices
        choices = []
        for game in user_games.games:
            # Skip non-owned games if owner_only is True
            if owner_only and game.owner_id != interaction.user.id:
                continue

            # Create display text with game name and ID
            display_name = f"{game.name} (ID: {game.id})"

            # Add owner indicator if showing all games
            if not owner_only and game.owner_id == interaction.user.id:
                display_name += " [OWNER]"

            # Filter based on current input (search in both name and ID)
            if (current.lower() in game.name.lower() or
                current in str(game.id)):
                choices.append(Choice(
                    name=display_name[:100],  # Discord limits choice names to 100 chars
                    value=str(game.id)        # Return string to match command param type
                ))

        # Return up to 25 choices (Discord's limit)
        return choices[:25]

    except LookupError:
        # User has no games, return empty list
        return []
    except Exception:
        # Handle any other errors gracefully
        logger.debug('Game autocomplete failed.', exc_info=True)
        return []

async def all_games_autocomplete(
    interaction: Interaction,
    current: str,
) -> list[Choice[str]]:
    return await game_id_autocomplete(interaction, current, owner_only=False)

async def owner_games_autocomplete(
    interaction: Interaction,
    current: str,
) -> list[Choice[str]]:
    return await game_id_autocomplete(interaction, current, owner_only=True)
