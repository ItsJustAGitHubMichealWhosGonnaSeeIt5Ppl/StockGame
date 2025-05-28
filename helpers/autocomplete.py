# WRITTEN MOSTLY BY CLAUDE

import discord
import os
from discord.app_commands import Choice # Explicitly import Choice for clarity
from discord.interactions import Interaction # Explicitly import Interaction for clarity
from helpers.datatype_validation import StockPick
from stocks import Frontend
from dotenv import load_dotenv


load_dotenv()

try:
    TOKEN = os.getenv('DISCORD_TOKEN')
    assert isinstance(TOKEN, str)
    DB_NAME = os.getenv('DB_NAME')
    assert isinstance(DB_NAME, str)
    OWNER = os.getenv("OWNER") # Set owner ID from env
    assert isinstance(OWNER, str)
except AssertionError as e:
    raise AssertionError('Missing one or more enviroment variables.')

fe = Frontend(database_name=DB_NAME, owner_user_id=int(OWNER), source='discord')

# Autocomplete function for stock symbols based on user's stocks in a specific game
async def sell_ticker_autocomplete(
    interaction: Interaction,
    current: str,
) -> list[Choice[str]]:
    """Autocomplete function to show user's stocks for the selected game"""
    try:
        # Get the current game_id value from the interaction
        # This accesses the partially filled command parameters
        game_id = 0
        if interaction.data and 'options' in interaction.data:
            for option in interaction.data.get('options', []):
                if option['name'] == 'game_id':
                    game_id = option.get('value')
                    break
        
        # If no game_id is entered yet, return empty list
        if game_id == 0 or not isinstance(game_id, int):
            return []
        
        # Get user's stocks for the specific game
        user_stocks: tuple[StockPick] = fe.my_stocks(
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
            search_text = f"{ticker} {getattr(stock.stock_ticker, 'name', '')}".lower()
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
    except Exception as e:
        # Handle any other errors gracefully
        print(f"Error in stock autocomplete: {e}")
        return []

# Autocomplete function for game_id parameter
async def game_id_autocomplete(
    interaction: Interaction,
    current: str,
    owner_only: bool = False
) -> list[Choice[int]]:
    """Autocomplete function to show user's games
    
    Args:
        interaction: Discord interaction
        current: Current user input
        owner_only: If True, only show games where user is the owner
    """
    try:
        # Get user's games using the frontend command
        user_games = fe.my_games(interaction.user.id, include_ended=False)
        
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
                    value=game.id
                ))
        
        # Return up to 25 choices (Discord's limit)
        return choices[:25]
        
    except LookupError:
        # User has no games, return empty list
        return []
    except Exception as e:
        # Handle any other errors gracefully
        print(f"Error in autocomplete: {e}")
        return []
    
async def all_games_autocomplete(
    interaction: Interaction,
    current: str,
) -> list[Choice[int]]:
    return await game_id_autocomplete(interaction, current, owner_only=False)

async def owner_games_autocomplete(
    interaction: Interaction,
    current: str,
) -> list[Choice[int]]:
    return await game_id_autocomplete(interaction, current, owner_only=True)