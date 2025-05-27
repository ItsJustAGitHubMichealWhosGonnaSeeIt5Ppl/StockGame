# WRITTEN MOSTLY BY CLAUDE

import discord
import os
from discord import app_commands
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

# Autocomplete function for game_id parameter
async def game_id_autocomplete(
    interaction: discord.Interaction,
    current: str,
    owner_only: bool = False
) -> list[app_commands.Choice[int]]:
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
                choices.append(app_commands.Choice(
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
    interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[int]]:
    return await game_id_autocomplete(interaction, current, owner_only=False)

async def owner_games_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[int]]:
    return await game_id_autocomplete(interaction, current, owner_only=True)