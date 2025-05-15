# DISCORD Bot
# SOME AI USED
# TODO add an invite user command? would be sent to DMs
# TODO set up some sort of draft system for stocks
# TODO should i add a command to show game info to all with join button?
# TODO add error handling via discord

# NEEDS FROM BACKEND:

# can you buy after start date?
# should i rename the commands? my-games and my-stocks are a bit annoying to type
# is my_games necessary?

from stocks import Backend, Frontend
import sys
import os
import logging
import discord
import datetime
from dateutil import parser
from discord.ext import commands
from discord import app_commands
from discord.ui import Button, View
from dotenv import load_dotenv, dotenv_values
from .helpers.views import Pagination

load_dotenv()

TOKEN = os.getenv('DISCORD_TOKEN')
DB_NAME = os.getenv('DB_NAME')
OWNER = os.getenv("OWNER") # Set owner ID from env

# Set up intents with all necessary permissions
intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
intents.guilds = True
intents.members = True
# intents.dm_messages = True # for invite user command

bot = commands.Bot(command_prefix="$", intents=intents)
print(DB_NAME)
fe = Frontend(database_name=DB_NAME, owner_user_id=OWNER) # Frontend

# Event: Called when the bot is ready and connected to Discord
@bot.event
async def on_ready():
    """Prints a message to the console when the bot is online and syncs slash commands."""
    print(fe.backend.get_game(1))
    print(f'Logged in as {bot.user.name} (ID: {bot.user.id})')
    print('------')
    try:
        # Sync commands globally
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
        for command in synced:
            print(f"   - {command.name}: {command.description}")
    except Exception as e:
        print(f"Failed to sync commands: {e}")


# GAME RELATED
# TODO can i make parameters required? if not, add (optional) to the description
# TODO should i add autofill to anything? 
@bot.tree.command(name="create-game-advanced", description="Create a new stock game without a wizard")
@app_commands.describe(
    name="Name of the game",
    start_date="Start date (YYYY-MM-DD)",
    end_date="End date (YYYY-MM-DD)",
    starting_money="Starting money amount",
    total_picks="Number of stocks each player can pick",
    exclusive_picks="Whether stocks can only be picked once",
    join_after_start="Whether players can join after game starts",
    private_game="Whether the game is private (requires owner approval for new users)"
    # sell_during_game="Whether players can sell stocks during game"
)
async def create_game_advanced(
    interaction: discord.Interaction,
    name: str,
    start_date: str,
    end_date: str = None,
    starting_money: float = 10000.00,
    total_picks: int = 10,
    exclusive_picks: bool = False,
    join_after_start: bool = False,
    private_game: bool = False
    # sell_during_game: bool = False
):
    # Create game using frontend and get the result
    result = fe.new_game(
        owner=interaction.user.id,
        name=name,
        start_date=start_date,
        end_date=end_date,
        starting_money=starting_money,
        total_picks=total_picks,
        exclusive_picks=exclusive_picks,
        join_after_start=join_after_start,
        sell_during_game=False,
        private_game= False
        # sell_during_game=sell_during_game
    )
    
    # If result is None or empty, the game was created successfully
    if not result:
        embed = discord.Embed(
            title="Game Created Successfully",
            description=f"Game '{name}' has been created!",
            color=discord.Color.green()
        )
    else:
        # If create game failed, show the error message
        embed = discord.Embed(
            title="Game Creation Failed",
            description=result,
            color=discord.Color.red()
        )
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

# TODO ask how start date works and remove "can users join after start" if not needed
# this code is a complete mess at the moment, trying to get it to work my way but it is taking more time than it's worth
# THIS ITERATION IS WORKING IN THE CURRENT STATE
@bot.tree.command(name="create-game", description="Guided setup for stock game creation")
async def create_game(interaction: discord.Interaction):
    # Create the initial embed
    embed = discord.Embed(
        title="Welcome to the Game Creation Wizard!",
        description="Click the button below to start creating your game.",
        color=discord.Color.blue()
    )
    
    # Create a button
    game_creation_wizard_start = discord.ui.Button(
        label="Create Stock Game",
        emoji="🛠️",
        style=discord.ButtonStyle.primary
    )
    
    # Create a view to hold the button
    game_creation_button_view = discord.ui.View()
    game_creation_button_view.add_item(game_creation_wizard_start)
    
    # Send the initial message with the embed and button
    await interaction.response.send_message(embed=embed, view=game_creation_button_view, ephemeral=True)
    
    # Define what happens when the button is clicked
    async def game_creation_wizard_start_callback(interaction: discord.Interaction):
        # Create a modal (popup) for text input
        initial_wizard_modal = discord.ui.Modal(title="Create Game Wizard", timeout=60)

        # Add a text input field for each text and number input
        name_input = discord.ui.TextInput(
            label="Name of your Stock Game",
            placeholder=f"{interaction.user.display_name}'s Stock Game",
            required=True,
            max_length=100,
            min_length=3,
        )

        start_date_input = discord.ui.TextInput(
            label="Start Date *No buying after this date",
            placeholder=(datetime.datetime.now() + datetime.timedelta(days=7)).strftime("%Y-%m-%d"), # Default to 7 days from now
            required=True,
            max_length=10,
            min_length=10,
            style=discord.TextStyle.short
        )

        end_date_input = discord.ui.TextInput(
            label="End Date *leave blank for no end date",
            placeholder="YYYY-MM-DD",
            required=False,
            max_length=10,
            min_length=10,
            style=discord.TextStyle.short
        )

        starting_money_input = discord.ui.TextInput(
            label="Starting Money Amount",
            placeholder="10000",
            required=False
        )

        total_picks_input = discord.ui.TextInput(
            label="Total Picks",
            placeholder="10",
            required=False
        )

        initial_wizard_modal.add_item(name_input)
        initial_wizard_modal.add_item(start_date_input)
        initial_wizard_modal.add_item(end_date_input)
        initial_wizard_modal.add_item(starting_money_input)
        initial_wizard_modal.add_item(total_picks_input)

        # Show the modal
        await interaction.response.send_modal(initial_wizard_modal)
        
        # Define what happens when the modal is submitted
        async def initial_wizard_callback(interaction: discord.Interaction):
            # # Ask if wanted end date - couldn't get the no button to work
            # # Create an end date embed
            # end_date_embed = discord.Embed(
            #     title="End Date",
            #     description="Do you want to set an end date for the game?",
            #     color=discord.Color.blue()
            # )

            # end_date_yes = discord.ui.Button(
            #     label="Yes",
            #     style=discord.ButtonStyle.success,
            #     custom_id="end_date_yes"
            # )

            # end_date_no = discord.ui.Button(
            #     label="No",
            #     style=discord.ButtonStyle.danger,
            #     custom_id="end_date_no"
            # )

            # end_date_view = discord.ui.View()

            # end_date_view.add_item(end_date_yes)
            # end_date_view.add_item(end_date_no)

            # await interaction.response.edit_message(embed=end_date_embed, view=end_date_view)
            
            # # Define what happens when the end date button is clicked
            # async def end_date_callback(interaction: discord.Interaction):                
            #     # Check which button was clicked
            #     if interaction.data["custom_id"] == "end_date_yes":
            #         end_date_input = discord.ui.TextInput(
            #             label="End Date (YYYY-MM-DD)",
            #             placeholder="YYYY-MM-DD",
            #             required=True,
            #             max_length=10,
            #             min_length=10,
            #             style=discord.TextStyle.short
            #         )
                    
            #         end_date_modal = discord.ui.Modal(title="Create Game Wizard", timeout=60)

            #         end_date_modal.add_item(end_date_input)

            #         await interaction.response.send_modal(end_date_modal)
                
            #     else:
            #         end_date_input = None
                
            #     async def end_date_modal_callback(interaction: discord.Interaction):
            # Create a exclusive picks embed
            exclusive_picks_embed = discord.Embed(
                title="Do you want exclusive picks?",
                description="If you select 'Yes', a stock can only be picked by one player. If you select 'No', a stock can be picked by multiple players.",
                color=discord.Color.blue()
            )

            # Create buttons for exclusive picks
            exclusive_picks_yes = discord.ui.Button(
                label="Yes",
                style=discord.ButtonStyle.success,
                custom_id="exclusive_picks_yes"
            )

            exclusive_picks_no = discord.ui.Button(
                label="No",
                style=discord.ButtonStyle.danger,
                custom_id="exclusive_picks_no"
            )

            exclusive_picks_view = discord.ui.View()
            exclusive_picks_view.add_item(exclusive_picks_yes)
            exclusive_picks_view.add_item(exclusive_picks_no)
            
            # Send the response
            await interaction.response.edit_message(embed=exclusive_picks_embed, view=exclusive_picks_view)

            # Define what happens when the exclusive picks button is clicked
            async def exclusive_picks_callback(interaction: discord.Interaction):
                # Check which button was clicked
                if interaction.data["custom_id"] == "exclusive_picks_yes":
                    exclusive_picks = True
                else:
                    exclusive_picks = False
                
                # Create a response embed for join after start
                join_after_start_embed = discord.Embed(
                    title="Do you want players to join after the game starts?",
                    description="If you select 'Yes', players can join after the game starts. If you select 'No', players cannot join after the game starts.",
                    color=discord.Color.blue()
                )

                # Create buttons for join after start
                join_after_start_yes = discord.ui.Button(
                    label="Yes",
                    style=discord.ButtonStyle.success,
                    custom_id="join_after_start_yes"
                )

                join_after_start_no = discord.ui.Button(
                    label="No",
                    style=discord.ButtonStyle.danger,
                    custom_id="join_after_start_no"
                )

                join_after_start_view = discord.ui.View()
                join_after_start_view.add_item(join_after_start_yes)
                join_after_start_view.add_item(join_after_start_no)
                
                # Send the response
                await interaction.response.edit_message(embed=join_after_start_embed, view=join_after_start_view)

                # Define what happens when the join after start button is clicked
                async def join_after_start_callback(interaction: discord.Interaction):                            
                    # Check which button was clicked
                    if interaction.data["custom_id"] == "join_after_start_yes":
                        join_after_start = True
                    else:
                        join_after_start = False

                    game_name=name_input.value
                    game_start_date=start_date_input.value
                    game_end_date=end_date_input.value if end_date_input.value else None
                    game_starting_money=int(starting_money_input.value if starting_money_input.value else 10000.00)
                    game_total_picks=int(total_picks_input.value if total_picks_input.value else 10)
                    
                    # Confirm the game creation with the provided inputs
                    confirmation_embed = discord.Embed(
                        title="Game Creation Confirmation",
                        description=f"Name: {game_name}\nStart Date: {game_start_date}\nEnd Date: {game_end_date}\nStarting Money: {game_starting_money}\nTotal Picks: {game_total_picks}\nExclusive Picks: {exclusive_picks}\nJoin After Start: {join_after_start}",
                        color=discord.Color.blue()
                    )
                    confirmation_embed.set_footer(text="Click 'Confirm' to create the game.")
                
                    confirmation_view = discord.ui.View()

                    confirm_button = discord.ui.Button(
                        label="Confirm",
                        style=discord.ButtonStyle.success,
                        custom_id="confirm_game_creation"
                    )

                    cancel_button = discord.ui.Button(
                        label="Cancel",
                        style=discord.ButtonStyle.danger,
                        custom_id="cancel_game_creation"
                    )

                    confirmation_view.add_item(confirm_button)
                    confirmation_view.add_item(cancel_button)
                    await interaction.response.edit_message(embed=confirmation_embed, view=confirmation_view)

                    # Define what happens when the confirm button is clicked
                    async def confirm_callback(interaction: discord.Interaction):
                        # Create the game using the provided inputs
                        result = fe.create_game(
                            user_id=interaction.user.id,
                            name=game_name,
                            start_date=game_start_date,
                            end_date=game_end_date,
                            starting_money=game_starting_money,
                            total_picks=game_total_picks,
                            exclusive_picks=exclusive_picks,
                            join_after_start=join_after_start,
                            sell_during_game=False # Placeholder for sell_during_game
                            # sell_during_game=sell_during_game
                        )
                        
                        # Check the result and create the response embed
                        if not result:
                            creation_status_embed = discord.Embed(
                                title="Game Created Successfully",
                                description=f"Game '{name_input.value}' has been created!",
                                color=discord.Color.green()
                            )
                        else:
                            creation_status_embed = discord.Embed(
                                title="Game Creation Failed",
                                description=result,
                                color=discord.Color.red()
                            )
                        
                        await interaction.response.edit_message(embed=creation_status_embed, view=None)
                    
                    # Define what happens when the cancel button is clicked
                    async def cancel_callback(interaction: discord.Interaction):
                        cancel_embed = discord.Embed(
                            title="Game Creation Cancelled",
                            description="The game creation process has been cancelled.",
                            color=discord.Color.red()
                        )
                        await interaction.response.edit_message(embed=cancel_embed, view=None)                    
        
                    # Set the confirm button callbacks
                    confirm_button.callback = confirm_callback
                    cancel_button.callback = cancel_callback
            
                # Set the join after button callback
                join_after_start_yes.callback = join_after_start_callback
                join_after_start_no.callback = join_after_start_callback

            # Set the exclusive button callback
            exclusive_picks_yes.callback = exclusive_picks_callback
            exclusive_picks_no.callback = exclusive_picks_callback

                # Set the end date modal callback
                # end_date_modal.on_submit = end_date_modal_callback

            # Set the end date yes button callback
            # end_date_yes.callback = end_date_callback
            # Set end date no button callback, skipping the modal
            # end_date_no.callback = end_date_callback

        # Set the modal callback
        initial_wizard_modal.on_submit = initial_wizard_callback

    # Set the button callback
    game_creation_wizard_start.callback = game_creation_wizard_start_callback    

# TODO Add user to game
# TODO Return success/error embed
@bot.tree.command(name="join-game", description="Join an existing stock game")
@app_commands.describe(
    game_id="ID of the game to join"
)
async def join_game(
    interaction: discord.Interaction, 
    game_id: int,
    name: str = None
):
    pass

# TODO Process purchase
# TODO Return transaction embed
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
    pass

# TODO Add remove stock pick
# TODO Return transaction embed
@bot.tree.command(name="remove-stock", description="Remove a stock from your picks")
@app_commands.describe(
    game_id="ID of the game",
    ticker="Stock ticker symbol"
)
async def remove_stock(
    interaction: discord.Interaction, 
    game_id: int, 
    ticker: str
):
    pass

# TODO Get user's stocks from frontend
# TODO Add autofill for user's games
# TODO Display stocks in an embed with stock info
# TODO Add buttons for buying/selling stocks?
# TODO Add pagination if there are many stocks (10+)
# TODO Add last updated date/time
@bot.tree.command(name="my-stocks", description="View your stocks in a game")
@app_commands.describe(
    game_id="ID of the game"
)
async def my_stocks(
    interaction: discord.Interaction,
    game_id: int
):
    pass

# TODO Add join game button to game info embed
# TODO change to show only public games
# TODO add buttons for joining games?
# TODO add autofill for user's games?
@bot.tree.command(name="game-info", description="View information about a game")
@app_commands.describe(
    game_id="ID of the game to view",
    show_leaderboard="Whether to display the leaderboard or not, will by default"
)
async def game_info(
    interaction: discord.Interaction, 
    game_id: int,
    show_leaderboard: bool = True
):
    info = fe.game_info(game_id, show_leaderboard)
    print(info)


    # await interaction.response.send_message(embed=embed, ephemeral=True)

# TODO get list of public games
#   - list the user count
#   - list the game status
#   - list the game name
# TODO add pagination if there are many games (10+)
# TODO add buttons for joining games?
# TODO add a joinable parameter?
@bot.tree.command(name="game-list", description="View a list of all games")
@app_commands.describe(
    page_length="The length of the list per page. Defaults to 10"
)
async def game_list(
    interaction: discord.Interaction,
    page_length: int = 10
):
    original = fe.list_games()
    games = filter(lambda x: (x["pick_date"] == 'None' or parser.parse(x["pick_date"]) > datetime.datetime.now()) and x["status"] == "active", original)
    async def get_page(page: int):
        embed = discord.Embed(title="Currently running games", description="")
        offset = (page - 1) * page_length
        for game in games:
            embed.add_field(
                name=f"{game["name"]}: [{game["id"]}]",
                value=f"""
                    Owned by: <@{game["owner"]}>\n
                    Pick date: {game["pick_date"] or "Not set"}\n
                    Starting Cash: {int(game["starting_money"])}\n
                    Starting on ${game["start_date"]} and ending on {game[""]}\n
                    """
                )
        n = Pagination.compute_total_pages(len(games), page_length)
        embed.set_footer(text=f"Page {page} of {n}")
        return embed, n
    await Pagination(interaction, get_page).navigate()
    

@bot.tree.command(name="my-games", description="View your games and their status") #TODO could be renamed to simply games
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
            status_emoji = "🟢" if game['status'] != 'ended' else "🔴"
            
            # Add game field
            embed.add_field(name=f"{status_emoji} {game['name']}", value=f"ID:{game['id']}")
    
    # Add footer with command usage
    embed.set_footer(text=f"Use /game-info <game_id> for more details")
    
    # Send the response
    await interaction.response.send_message(embed=embed, ephemeral=True)

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
