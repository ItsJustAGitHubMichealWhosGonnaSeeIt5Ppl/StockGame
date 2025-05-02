# DISCORD Bot
# SOME AI USED
#TODO add autocompletion for game_id and other parameters
#TODO add error handling

# NEEDS FROM BACKEND:
# - check_user_permissions
# - should we add public vs private games for something like game_info?
# - need games objects to be able to get game info

from stocks import Backend, Frontend
import sys
import os
import logging
import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import Button, View
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

TOKEN = os.getenv('DISCORD_TOKEN')

# Set up intents with all necessary permissions
intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="$", intents=intents) # Set up 

fe = Frontend() # Frontend

# Event: Called when the bot is ready and connected to Discord
@bot.event
async def on_ready():
    """Prints a message to the console when the bot is online and syncs slash commands."""
    print(f'Logged in as {bot.user.name} (ID: {bot.user.id})')
    print('------')
    try:
        # Sync commands globally
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Failed to sync commands: {e}")


# GAME RELATED
@bot.tree.command(name="create-game", description="Create a new stock game")
@app_commands.describe(
    name="Name of the game",
    start_date="Start date (YYYY-MM-DD)",
    end_date="End date (YYYY-MM-DD)",
    starting_money="Starting money amount",
    total_picks="Number of stocks each player can pick",
    exclusive_picks="Whether stocks can only be picked once",
    join_after_start="Whether players can join after game starts",
    sell_during_game="Whether players can sell stocks during game"
)
async def create_game(
    interaction: discord.Interaction,
    name: str,
    start_date: str,
    end_date: str = None,
    starting_money: float = 10000.00,
    total_picks: int = 10,
    exclusive_picks: bool = False,
    join_after_start: bool = False,
    sell_during_game: bool = False
):
    # Create game using frontend and get the result
    result = fe.create_game(
        user_id=interaction.user.id,
        name=name,
        start_date=start_date,
        end_date=end_date,
        starting_money=starting_money,
        total_picks=total_picks,
        exclusive_picks=exclusive_picks,
        join_after_start=join_after_start,
        sell_during_game=sell_during_game
    )
    
    # If result is None or empty, the game was created successfully
    if not result:
        embed = discord.Embed(
            title="Game Created Successfully",
            description=f"Game '{name}' has been created!",
            color=discord.Color.green()
        )
    else:
        # If there's a result, it's an error message
        embed = discord.Embed(
            title="Game Creation Failed",
            description=result,
            color=discord.Color.red()
        )
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="join-game", description="Join an existing stock game")
@app_commands.describe(
    game_id="ID of the game to join"
)
async def join_game(
    interaction: discord.Interaction, 
    game_id: int
):
    # Check if game exists and is joinable
    # Check user permissions
    # Add user to game
    # Return success/error embed
    pass

@bot.tree.command(name="buy-stock", description="Buy a stock in a game")
@app_commands.describe(
    game_id="ID of the game",
    ticker="Stock ticker symbol",
    shares="Number of shares to buy"
)
async def buy_stock(
    interaction: discord.Interaction, 
    game_id: int, 
    ticker: str, 
    shares: int
):
    # Check game status and user permissions
    # Check if user has enough money
    # Process purchase
    # Return transaction embed
    pass

@bot.tree.command(name="sell-stock", description="Sell a stock in a game")
@app_commands.describe(
    game_id="ID of the game",
    ticker="Stock ticker symbol",
    shares="Number of shares to sell"
)
async def sell_stock(
    interaction: discord.Interaction, 
    game_id: int, 
    ticker: str, 
    shares: int
):
    # Check game status and user permissions
    # Check if user owns the stock
    # Process sale
    # Return transaction embed
    pass

# TODO Add join game button to game info embed
@bot.tree.command(name="game-info", description="View information about a game")
@app_commands.describe(
    game_id="ID of the game to view"
)
async def game_info(
    interaction: discord.Interaction, 
    game_id: int
):
        
    game = fe.game_info(game_id)

    if not game:
        embed = discord.Embed(
            title="Game Not Found",
            description=f"Could not find a game with ID {game_id}.",
            color=discord.Color.red()
        )
    else:
        embed = discord.Embed(
            title="Game #{game_id}",
            description=f"Name: {game['name']}\nStart Date: {game['start_date']}\nEnd Date: {game['end_date']}\nStarting Money: ${game['starting_money']}\nTotal Picks: {game['total_picks']}\nExclusive Picks: {game['exclusive_picks']}\nJoin After Start: {game['join_after_start']}\nSell During Game: {game['sell_during_game']}\nStatus: {game['status']}",
            color=discord.Color.blue()
        )

    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="my-games", description="View your games and their status")
async def my_games(
    interaction: discord.Interaction
):
    # Get user's games from frontend
    games = fe.my_games(interaction.user.id)
    
    # Create embed for the response
    embed = discord.Embed(
        title="Your Games",
        color=discord.Color.blue()
    )
    
    if not games:
        embed.description = "No games found"
    else:
        # Add each game to the embed
        for game in games:
            # Create status indicator
            status_emoji = "🟢" if game['status'] == 'open' else "🔴"
            
            # Add game field
            embed.add_field(name=f"{status_emoji} Game #{game['id']}: {game['name']}")
    
    # Add footer with command usage
    embed.set_footer(text=f"Use /game-info <game_id> for more details")
    
    # Send the response
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="leaderboard", description="View game leaderboard")
@app_commands.describe(
    game_id="ID of the game",
    user_id="Optional: View specific user's position"
)
async def leaderboard(
    interaction: discord.Interaction, 
    game_id: int, 
    user_id: discord.User = None
):
    # Get leaderboard data from backend
    # Create autofill for user's games
    # Create paginated embed with leaderboard
    # Add navigation buttons if multiple pages
    pass


# Run the bot using the token
if TOKEN:
    try:
        bot.run(TOKEN)
    except discord.errors.LoginFailure:
        print("Login Failed: Improper token has been passed.")
    except discord.errors.PrivilegedIntentsRequired:
        print("Privileged Intents Required: Make sure Message Content Intent is enabled on the Discord Developer Portal.")
    except Exception as e:
        print(f"An error occurred while running the bot: {e}")
else:
    print("Error: DISCORD_TOKEN environment variable not found.")
    print("Please set the DISCORD_TOKEN environment variable before running the bot.")
    # Instructions for setting environment variables can vary by OS.
    # Example for Linux/macOS: export DISCORD_TOKEN='YOUR_BOT_TOKEN'
    # Example for Windows (Command Prompt): set DISCORD_TOKEN=YOUR_BOT_TOKEN
    # Example for Windows (PowerShell): $env:DISCORD_TOKEN='YOUR_BOT_TOKEN'
    # Consider using a .env file and the python-dotenv library for easier management.
