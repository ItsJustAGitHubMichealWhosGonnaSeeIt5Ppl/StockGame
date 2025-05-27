# DISCORD Bot
# SOME AI USED
# TODO add an invite user command? would be sent to DMs
# TODO set up some sort of draft system for stocks
# TODO should i add a command to show game info to all with join button?
# TODO add error handling via discord
# TODO add help command

# should i rename the commands? my-games and my-stocks are a bit annoying to type

# BUILT-IN
import sys
import os
import logging
from typing import Optional # 3.13 +
from datetime import datetime, timedelta

# LOCAL
from helpers.views import Pagination
from stocks import Frontend
from helpers.exceptions import NotAllowedError, DoesntExistError

# DISCORD 
import discord
from discord import app_commands
from discord.ui import Button, View
from discord.ext import commands

#OTHER
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
    

# Set up intents with all necessary permissions
intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
intents.guilds = True
intents.members = True
# intents.dm_messages = True # for invite user command


# Logger thing
def setup_logging(level): 
    global console, logger
    frmt = logging.Formatter(fmt='%(asctime)s %(name)s %(levelname)s %(message)s', datefmt='%Y-%m-%d %H:%M:%S') #Format that I like
    logger = logging.getLogger('DiscordBot') # Logger name
    console = logging.StreamHandler(stream=sys.stderr)
    console.setLevel(logging.DEBUG) 
    console.setFormatter(frmt)
    logger.addHandler(console)
    logger.setLevel(level)
setup_logging(level=logging.DEBUG) # debug for now

def has_permission(user:discord.member.Member):
    """Check if a user has permission to create/manage games
    
    Currently only checks for admin

    Args:
        user (discord.member.Member): Member (user) object.
        
    Returns:
        bool: True if allowed
    """
    
    return user.guild_permissions.administrator

def simple_embed(status:str, title:str, desc:Optional[str]=None):
    """Create a simple discord embed object
    
    Objects with a status of 'failed' will be set to red

    Args:
        status (str): Status/result of action ('success', 'failed')
        title (str): Title.
        desc (Optional[str], optional): Description. Defaults to None.

    Returns:
        discord.Embed: Embed object
    """
        
    return discord.Embed(
        title = title,
        description = desc,
        color= discord.Color.green() if status == 'success' else discord.Color.red()
    )

bot = commands.Bot(command_prefix="$", intents=intents)
logger.info(f'Connecting with DB: {DB_NAME}')
fe = Frontend(database_name=DB_NAME, owner_user_id=int(OWNER), source='discord') # Frontend

# Event: Called when the bot is ready and connected to Discord
@bot.event
async def on_ready():
    """Prints a message to the console when the bot is online and syncs slash commands."""
    logger.info(f'Logged in as {bot.user.name} (ID: {bot.user.id})')
    try:
        # Sync commands globally
        synced = await bot.tree.sync()
        logger.info(f"Synced {len(synced)} command(s)")
        for command in synced:
            logger.info(f"   - {command.name}: {command.description}")
    except Exception as e:
        logger.error(f"Failed to sync commands: {e}") #TODO should this be higher severity?

# GAME INTERACTION RELATED

# TODO can i make parameters required? if not, add (optional) to the description
@bot.tree.command(name="create-game-advanced", description="Create a new stock game without a wizard")
@app_commands.describe(
    name="Name of the game",
    start_date="Start date (YYYY-MM-DD)",
    end_date="End date (YYYY-MM-DD)",
    pick_date="Date stocks must be picked by (YYYY-MM-DD)",
    starting_money="Starting money amount",
    total_picks="Number of stocks each player can pick",
    exclusive_picks="Whether stocks can only be picked once",
    private_game="Whether the game is private (requires owner approval for new users)",
    update_frequency="How often prices should update ('daily', 'hourly', 'minute', 'realtime')"
    # sell_during_game="Whether players can sell stocks during game"
)
async def create_game_advanced(
    interaction: discord.Interaction,
    name: str,
    start_date: str,
    end_date: str | None = None,
    starting_money: float = 10000.00,
    total_picks: int = 10,
    exclusive_picks: bool = False,
    private_game: bool = False,
    pick_date: str | None = None,
    update_frequency: str = 'daily',
    # sell_during_game: bool = False
):
    # Create game using frontend and return
    try:
        fe.new_game(
            user_id=interaction.user.id,
            name=name,
            start_date=start_date,
            end_date=end_date,
            starting_money=starting_money,
            total_picks=total_picks,
            exclusive_picks=exclusive_picks,
            private_game= private_game,
            pick_date=pick_date,
            update_frequency=update_frequency
            #sell_during_game=False, - NOT IMPLEMENTED
        )
        
        embed = discord.Embed(
            title="Game Created Successfully",
            description=f"Game '{name}' has been created!",
            color=discord.Color.green()
        )
    except Exception as e: #TODO find specific errors!
        embed = discord.Embed(
        title="Game Creation Failed",
        description=e,
        color=discord.Color.red()
        )
     
    await interaction.response.send_message(embed=embed, ephemeral=True)

# this code is a complete mess at the moment, trying to get it to work my way but it is taking more time than it's worth
# THIS ITERATION IS WORKING IN THE CURRENT STATE
# TODO edit for new parameters
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
            placeholder=(datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d"), # Default to 7 days from now
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
                    game_exclusive_picks = True
                else:
                    game_exclusive_picks = False

                pick_date_modal = discord.ui.Modal(title="Pick Date", timeout=60)

                pick_date_input = discord.ui.TextInput(
                    label=f"Pick Date{' *leave blank for no pick date' if not game_exclusive_picks else ''}",
                    placeholder="YYYY-MM-DD",
                    required=game_exclusive_picks,
                    max_length=10,
                    min_length=10,
                    style=discord.TextStyle.short
                )

                pick_date_modal.add_item(pick_date_input)
                
                await interaction.response.send_modal(pick_date_modal)
                
                async def pick_date_callback(interaction: discord.Interaction):

                    # Create a response embed for join after start
                    private_embed = discord.Embed(
                        title="Do you want your game to be private?",
                        description="If you select 'Yes', the game ID will be hidden in the game-list command. If you select 'No', it will be visible.",
                        color=discord.Color.blue()
                    )

                    # Create buttons for join after start
                    private_yes = discord.ui.Button(
                        label="Yes",
                        style=discord.ButtonStyle.success,
                        custom_id="private_yes"
                    )

                    private_no = discord.ui.Button(
                        label="No",
                        style=discord.ButtonStyle.danger,
                        custom_id="private_no"
                    )

                    private_game_view = discord.ui.View()
                    private_game_view.add_item(private_yes)
                    private_game_view.add_item(private_no)
                    
                    # Send the response
                    await interaction.response.edit_message(embed=private_embed, view=private_game_view)

                    # Define what happens when the join after start button is clicked
                    async def private_game_callback(interaction: discord.Interaction):                            
                        # Check which button was clicked
                        if interaction.data["custom_id"] == "private_yes":
                            private_game = True
                        else:
                            private_game = False

                        # Create a response embed for update frequency
                        update_frequency_embed = discord.Embed(
                            title="Update Frequency",
                            description="How often should the stock prices update?\nDefaults to daily.",
                            color=discord.Color.blue()
                        )

                        # Create buttons for update frequency
                        update_frequency_daily = discord.ui.Button(
                            label="Daily",
                            style=discord.ButtonStyle.success,
                            custom_id="update_frequency_daily"
                        )

                        update_frequency_hourly = discord.ui.Button(
                            label="Hourly",
                            style=discord.ButtonStyle.success,
                            custom_id="update_frequency_hourly"
                        )

                        update_frequency_minute = discord.ui.Button(
                            label="Minute",
                            style=discord.ButtonStyle.success,
                            custom_id="update_frequency_minute"
                        )

                        update_frequency_realtime = discord.ui.Button(
                            label="Realtime",
                            style=discord.ButtonStyle.success,
                            custom_id="update_frequency_realtime"
                        )

                        update_frequency_view = discord.ui.View()
                        update_frequency_view.add_item(update_frequency_daily)
                        update_frequency_view.add_item(update_frequency_hourly)
                        update_frequency_view.add_item(update_frequency_minute)
                        update_frequency_view.add_item(update_frequency_realtime)

                        await interaction.response.edit_message(embed=update_frequency_embed, view=update_frequency_view)

                        async def update_frequency_callback(interaction: discord.Interaction):
                            # Check which button was clicked
                            if interaction.data["custom_id"] == "update_frequency_daily":
                                game_update_frequency = "daily"
                            elif interaction.data["custom_id"] == "update_frequency_hourly":
                                game_update_frequency = "hourly"
                            elif interaction.data["custom_id"] == "update_frequency_minute":
                                game_update_frequency = "minute"
                            else:
                                game_update_frequency = "realtime"
                    
                            game_name=name_input.value
                            game_start_date=start_date_input.value
                            game_end_date=end_date_input.value if end_date_input.value else None
                            game_pick_date=pick_date_input.value if pick_date_input.value else None
                            game_starting_money=int(starting_money_input.value if starting_money_input.value else 10000.00)
                            game_total_picks=int(total_picks_input.value if total_picks_input.value else 10)
                            
                            # Confirm the game creation with the provided inputs
                            confirmation_embed = discord.Embed(
                                title="Game Creation Confirmation",
                                description=f"Name: {game_name}\nStart Date: {game_start_date}\nEnd Date: {game_end_date}\nStarting Money: {game_starting_money}\nTotal Picks: {game_total_picks}\nExclusive Picks: {game_exclusive_picks}\nPrivate Game: {private_game}\nUpdate Frequency: {game_update_frequency}",
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
                                try:
                                    fe.new_game(
                                        user_id=interaction.user.id,
                                        name=game_name,
                                        start_date=game_start_date,
                                        end_date=game_end_date,
                                        pick_date=game_pick_date,
                                        starting_money=game_starting_money,
                                        total_picks=game_total_picks,
                                        exclusive_picks=game_exclusive_picks,
                                        private_game=private_game,
                                        update_frequency=game_update_frequency,
                                        sell_during_game=False # Placeholder for sell_during_game
                                        # sell_during_game=sell_during_game
                                    )

                                    creation_status_embed = discord.Embed(
                                        title="Game Created Successfully",
                                        description=f"Game '{name_input.value}' has been created!",
                                        color=discord.Color.green()
                                    )

                                except ValueError as e:
                                    creation_status_embed = discord.Embed(
                                        title="Game Creation Failed",
                                        description=e,
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

                        # Set the update frequency button callbacks
                        update_frequency_daily.callback = update_frequency_callback
                        update_frequency_hourly.callback = update_frequency_callback
                        update_frequency_minute.callback = update_frequency_callback
                        update_frequency_realtime.callback = update_frequency_callback
                
                    # Set the join after button callback
                    private_yes.callback = private_game_callback
                    private_no.callback = private_game_callback

                # Set the pick date modal callback
                pick_date_modal.on_submit = pick_date_callback

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

# TODO Handle more specific errors when implemented (private game, invalid game id, etc)
@bot.tree.command(name="join-game", description="Join an existing stock game")
@app_commands.describe(
    game_id="ID of the game to join",
    name="Name to display for your picks (optional)"
)
async def join_game(
    interaction: discord.Interaction, 
    game_id: int,
    name: str | None = None
):
    
    if not name:
        name = interaction.user.display_name
    
    status = 'failed'
    try:
        fe.join_game(
            user_id=interaction.user.id, 
            game_id=game_id, 
            name=name
        )

        title= "Game Joined Successfully"
        description = f"You have joined game: {game_id}."
        status = 'success'
    except LookupError as e:
        failed_desc = f'No game with the ID {game_id}.'
        
    except ValueError as e:
        if 'already in game.' in str(e):
            description = f'You are already in this game ID {game_id}.'
            
        elif '`pick_date` has passed.' in str(e):
            description = f'The pick date for this game has passed.'
            
    except Exception as e:
        logger.exception(f'User: {interaction.user.id} failed to join game {game_id}.  Error: {e}')
        description = f'An unexpected error ocurred. Please report this! {game_id}.\n{e}'

    if status == 'failed':
        title = "Game Join Failed"

    await interaction.response.send_message(embed=simple_embed(status = status, title = title, desc = description), ephemeral=True)

@bot.tree.command(name="manage-game", description="Manage an existing stock game")
@app_commands.describe(
    game_id="ID of the game to update",
    name="New name of the game",
    owner="Game owner user ID",
    start_date="New start date (YYYY-MM-DD)",
    end_date="New end date (YYYY-MM-DD); Cannot be changed once game has started",
    pick_date="Date stocks must be picked by (YYYY-MM-DD); Cannot be changed once game has started",
    private_game="Whether the game is private or not",
    starting_money="New starting money amount; Cannot be changed once game has started",
    total_picks="New number of stocks each player can pick; Cannot be changed once game has started",
    draft_mode="Whether multiple users can pick the same stock; Pick date must be on or before start date; Cannot be changed once game has started",
    sell_during_game="Whether users can sell stocks during the game; Cannot be changed once game has started",
    update_frequency="How often prices should update ('daily', 'hourly', 'minute', 'realtime')"
)
async def manage_game(
    interaction: discord.Interaction, 
    game_id: int,
    name: str | None = None,
    owner: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    starting_money: float | None = None,
    pick_date: str | None = None,
    private_game: bool | None = None,
    total_picks: int | None = None,
    draft_mode: bool | None = None,
    sell_during_game: bool | None = None,
    update_frequency: str | None = None
):
    game_info = fe.game_info(game_id, False)

    if not game_info:
        embed = discord.Embed(
            title="Game Not Found",
            description=f"Could not find a game with ID {game_id}.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    try:
        fe.manage_game(
            user_id=interaction.user.id,
            game_id=game_id,
            name=name,
            owner=owner,
            start_date=start_date,
            end_date=end_date,
            starting_money=starting_money,
            pick_date=pick_date,
            private_game=private_game,
            total_picks=total_picks,
            exclusive_picks=draft_mode,
            update_frequency=update_frequency,
            sell_during_game=sell_during_game
        )

        embed = discord.Embed(
            title="Game Updated Successfully",
            description=f"Game #{game_id} has been updated!",
            color=discord.Color.green()
        )
    except Exception as e:
        embed = discord.Embed(
            title="Game Update Failed",
            description=e,
            color=discord.Color.red()
        )

    await interaction.response.send_message(embed=embed, ephemeral=True)

# TODO fix response to command
@bot.tree.command(name="invite", description="Invite a user to a game")
@app_commands.describe(
    game_id="ID of the game to invite them to",
    user="User to invite"
)
async def invite_user(
    interaction: discord.Interaction, 
    game_id: int,
    user: discord.User
):
    invite_embed = discord.Embed(
        title="Game Invite",
        description=f"You have been invited to game #{game_id} by {interaction.user.display_name}.",
        color=discord.Color.green()
    )

    accept_button = discord.ui.Button(
        label="Accept Invite",
        style=discord.ButtonStyle.success,
        custom_id="accept_invite",
        emoji="✅"
    )

    decline_button = discord.ui.Button(
        label="Decline Invite",
        style=discord.ButtonStyle.danger,
        custom_id="decline_invite",
        emoji="❌"
    )

    view = discord.ui.View()
    view.add_item(accept_button)    
    view.add_item(decline_button)

    async def accept_invite_callback(interaction: discord.Interaction):
        # Add user to the game
        
        try:
            fe.join_game(
                user_id=user.id,
                game_id=game_id
            )

            accept_embed = discord.Embed(
                title="Game Joined",
                description=f"You have joined game #{game_id}.",
                color=discord.Color.green()
            )
        except Exception as e:
            accept_embed = discord.Embed(
                title="Game Join Failed",
                description=f"Could not join game #{game_id}.\n{e}",
                color=discord.Color.red()
            )

        await interaction.response.edit_message(embed=accept_embed, view=None)

    async def decline_invite_callback(interaction: discord.Interaction):
        decline_embed = discord.Embed(
            title="Invite Declined",
            description=f"You have declined the invite to game #{game_id}.",
            color=discord.Color.red()
        )
        await interaction.response.edit_message(embed=decline_embed, view=None)

    accept_button.callback = accept_invite_callback
    decline_button.callback = decline_invite_callback

    try:
        invite_response_embed = discord.Embed(
            title="Invite Sent",
            description=f"Invite sent to {user.mention}.",
            color=discord.Color.blue()
        )
    
        await interaction.response.send_message(
            content=f"Invite sent to {user.mention}.",
            embed=invite_response_embed,
            ephemeral=True
        )

        await user.send(embed=invite_embed, view=view)
    except discord.Forbidden:
        # If the user has DMs disabled, send a message in the channel instead
        invite_response_embed = discord.Embed(
            title="Invite Not Sent",
            description=f"Could not send invite to {user.mention}. They have DMs disabled.",
            color=discord.Color.blue()
        )
        
        await interaction.response.send_message(
            embed=invite_response_embed,
            ephemeral=True
        )

# STOCK RELATED

@bot.tree.command(name="buy-stock", description="Buy a stock in a game")
@app_commands.describe(
    game_id="ID of the game",
    ticker="Stock ticker symbol"
)
async def buy_stock(
    interaction: discord.Interaction, 
    game_id: int, 
    ticker: str
):
    
    status = 'failed' # Start with failed status
    title = 'Stock Purchase Failed'
    try:
        fe.buy_stock(
            user_id=interaction.user.id,
            game_id=game_id,
            ticker=ticker
        )
        title = 'Stock Purchased'
        description = f'You have successfully bought {ticker} in game: {game_id}.'
        status = 'success'
        
    except NotAllowedError as exc: # REASONS ARE NOW IN THE DOCSTRING OF buy_stock!!
        if exc.reason == 'Not active': # Player isn't an active member of the game - IDK HOW YOU WANT TO TELL THE USER THIS.  This could happen if they got banned, or if the game is private and they haven't been approved
            description = f'You are not allowed to buy stocks in the game: {game_id}.'
        
        elif exc.reason == 'Maximum picks reached':
            title="Game Pick Limit Reached"
            description = f'You have reached the maximum number of picks for this game.\nTo add another stock, you need to remove one of your current picks.'
        
        elif exc.reason == 'Past pick_date':
            description = f'The pick date for this game has passed, so you can no longer pick stocks.'
            
    except DoesntExistError as exc: # Player isnt in the game at all
        if exc.table == 'game_participants':
            description = f'You are not in the game: {game_id}.'
            
    except Exception as e: # Other unexpeted errors
        logger.exception(f'User: {interaction.user.id} tried to buy the stock: {ticker} in game: {game_id}. Error: {e}')
        description=f'An unexpected error ocurred while trying to buy a stock\nReport this! Ticker: {ticker}, Game: {game_id}'
            
    await interaction.response.send_message(
        embed=simple_embed( # This just creates the status message
            status = status,
            title = title,
            desc = description
            ), 
        ephemeral=True
        )

# TODO add autofill for user's stocks and games
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
   
    status = 'failed'
    try:
        fe.remove_pick(
            user_id=interaction.user.id,
            game_id=game_id,
            ticker=ticker
        )
        status = 'success'
        title="Stock Removal Successful"
        description=f"You have successfully removed {ticker} from your picks in game: {game_id}."

        
    except Exception as e:
        status = 'failed'
        title="Stock Removal Failed"
        description=f"Could not remove {ticker} from your picks in game: {game_id}.\n{e}"

    await interaction.response.send_message(embed=simple_embed(status = status, title = title, desc = description), ephemeral=True)

# TODO Get user's stocks from frontend
# TODO Add autofill for user's games
# TODO Display stocks in an embed with stock info
# TODO Add buttons for buying/selling stocks?
# TODO Add pagination if there are many stocks (10+)
# TODO Add last updated date/time in footer
@bot.tree.command(name="my-stocks", description="View your stocks in a game")
@app_commands.describe(
    game_id="ID of the game"
)
async def my_stocks(
    interaction: discord.Interaction,
    game_id: int
):
    user_id = interaction.user.id
    
    picks_table = ['| Stock |  Price  | Shares |  Value  |  $Gain  | %Gain |'] # Max codeblock line length: 56, This should be EXACTLY 56 charaters
    # EXAMPLE LINE:            | AAPLE | $10,000 | 10,000 | $10,000 | $10,000 | 1000% |
    status = 'failed' # Default to failed
    title = 'Fetching Stocks Failed'
    try:
        picks = fe.my_stocks(user_id, game_id)
        
        row_template = '| {stock} | {price} | {shares} | {value} | {d_gain} | {p_gain} |'
        for pick in picks: #TODO Do we want to limit how many stocks show here?
            #TODO this could be simplified if we only wanted to show the active stocks!
            if pick.status == 'owned': # Prevent null values
                assert pick.current_value != None
                assert pick.shares != None
                share_price = str('$'+ format(float(pick.current_value / pick.shares), ','))[:7] # Cut it off at 7, although this is a very bad solution long term...

            else:
                share_price = 'NA'
                
            picks_table.append(row_template.format(
                stock = str(pick.stock_ticker).center(5),
                price = share_price.center(7),
                shares = (str(round(pick.shares, 2)) if pick.shares else 'NA').center(6),
                value = (str('$'+ format(round(pick.current_value, 2), ','))[:6] if pick.current_value else 'NA').center(6),
                d_gain = (str('$'+ format(round(pick.change_dollars, 2), ','))[:6] if pick.change_dollars else 'NA').center(6),
                p_gain = (str(format(round(pick.change_percent, 2))+ '%')[:5] if pick.change_percent else 'NA').center(5),
            ))
        status = 'success'
        
    except DoesntExistError as e: # Raised when player is not in the game
        description=f'You are not currently participating in this game. You can try to join it using the join-game command.'
    
    except LookupError as e: # No stocks were even returned
        description = f'You don\'t currently have any stocks in game: {game_id}' 
        
    except Exception as e: # Other errors
        description=f"There was an error while fetching your stocks.\n{e}",
        logger.exception(f'User: {interaction.user.id} tried to list their stocks in game: {game_id}. Error: {e}')
        description=f'An unexpected error ocurred while trying to load your stocks\nReport this! Game: {game_id}'

    embed = simple_embed(status=status, title=f'<@{user_id}>\'s stock picks')
    embed.add_field(name='Your Picks', value='```{stocks}```'.format(stocks='\n'.join(picks_table)))
    await interaction.response.send_message(embed=embed, ephemeral=True)

# GAME INFO RELATED

# TODO Add join game button to game info embed
# TODO frontend: change to show only public games
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
    game_info = fe.game_info(game_id, show_leaderboard=True) #Leaderboard is required to set the members participating
    game = game_info.game
    assert isinstance(game_info.leaderboard, list)
    description_str = '> **Owner:** <@{owner_id}>{pick_info}\n{start_cash}\n{date_range}\n{participants}'.format(owner_id=game.owner_id,
        pick_info=f'\n> **Pick date:** {game.pick_date}' if game.pick_date else '',
        start_cash=f'> **Starting Cash:** ${int(game.start_money)}',
        date_range= '> ' + str('Started' if game.status != 'open' else 'Starting') + f' `{game.start_date}`' + str(str(', ends' if  game.status != 'ended' else ', ended') + f' `{game.end_date}`') if game.end_date else '',
        participants=f'> **Participants:** `{len(game_info.leaderboard)}`' #members ' + str('participating' if  game['status'] != 'ended' else 'participated')
        )
    embed = discord.Embed(title=f'{game.name} ({game.id})', 
        description=description_str)
    embed.set_footer(text="Dates are formatted as (YYYY-MM-DD)")

    if not show_leaderboard:
        await interaction.response.send_message(embed=embed)
        return
    
    lb_limit = 10 # Amount of users to show '🏆'
    leaderboard_info = game_info.leaderboard[:lb_limit] # Only include top 10
    pos = ['🥇', '🥈', '🥉', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣', '🔟']  #+ [x+4 for x in range(lb_limit-3)] if emojis cause problems
    
    ldrbrd_lines = ['| 🏆 |     Investor     |    Portfolio    |   Joined   |'] # Max codeblock line length: 56, This should be EXACTLY 56 charaters
    leaderboard_block = '```\n{ldrbrd_linees}\n```'
    row_template = '| {pos} | {user} | {value} | {date} |'
    for rank, info in enumerate(leaderboard_info):
        try: # Try to get username
            member = await interaction.guild.fetch_member(info.user_id) # Set display name
            if len(member.display_name) <= 16: # Server displayname
                user= str(member.display_name)
            elif len(member.global_name) <= 16: # Globbal display
                user= str(member.global_name)
            elif len(member.name) <= 16: # Username
                user= str(member.global_name)
            else:
                user = str(member.global_name)[:15] + '~' # Name is just too long, give up
            
        except discord.errors.NotFound: # User doesn't exist
            user = f'ID({info.user_id})'
        ldrbrd_lines.append(row_template.format( # Create rows
            pos=pos[rank],
            user=user.center(16),
            value= str('$'+ format(float(info.current_value), ',')).center(15),
            date= f'{datetime.strftime(info.joined, "%Y-%m-%d")[:10]}' # Manually centering I guess
        ))
    embed.add_field(name="Leaderboard", value=leaderboard_block.format(ldrbrd_linees='\n'.join(ldrbrd_lines)))
    await interaction.response.send_message(embed=embed)

# TODO get list of public games
#   - list the user count
#   - list the game status
#   - list the game name
# TODO add pagination if there are many games (10+)
# TODO add buttons for joining games?
# TODO add a joinable parameter?
@bot.tree.command(name="game-list", description="View a list of all games") # TODO rename to list-games, all-games, or games-list?
@app_commands.describe(
    page_length="The length of the list per page. Defaults to 10"
)
async def game_list(
    interaction: discord.Interaction,
    page_length: int = 10
):
    games = fe.list_games(include_open=False, include_active=True) # Only get currently running games
    
    async def get_page(page: int):
        embed = discord.Embed(title="Currently running games", description="")
        offset = (page - 1) * page_length
        for game in games:
            game_members = fe.get_all_participants(game.id)
            embed.add_field(
                name=f"{game.name}: [{game.id}]", #TODO switch this to use the simpler formatting
                value=f"""
                    **Owned by:** <@{game.owner_id}>
                    **Pick date:** {game.pick_date or "Not set"}
                    **Starting Cash:** ${int(game.start_money)}
                    Starting on `{game.start_date}` and ending on `{game.end_date}`
                    There are currently **{len(game_members)}** members participating
                    """
                )
        n = Pagination.compute_total_pages(len(games), page_length)
        embed.set_footer(text=f"Page {page} of {n} | Dates are formatted as (YYYY/MM/DD)")
        return embed, n
    await Pagination(interaction, get_page).navigate()
    

@bot.tree.command(name="my-games", description="View your games and their status") #TODO could be renamed to simply games
async def my_games(
    interaction: discord.Interaction
):
    embed = discord.Embed(
        title="Your Games",
        color=discord.Color.blue()
    )
    try:
        games = fe.my_games(interaction.user.id)
        if len(games.games) == 0:
            raise LookupError("No games found")
        game_description: str = ""
        # Add each game to the embed
        for game in games.games: #TODO provide more info here
            # Create status indicator
            status_emoji = "🟢" if game.status != 'ended' else "🔴"
                        
            # Add game field
            game_description= game_description + f"{status_emoji} {game.name}   ID: {game.id}\n"

        embed.description = game_description
        embed.set_footer(text=f"Use /game-info <game_id> for more details")

    except Exception as e:
        embed.description = "No games found"
        embed.color = discord.Color.red()
    
    # Send the response
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="delete-game", description="For admins to delete games if needed")
@app_commands.describe(
    game_id="The game ID to delete"
)
async def delete_game(
    interaction: discord.Interaction,
    game_id: int,
):
    embed = discord.Embed()
    try:
        fe.remove_game(user_id=interaction.user.id, game_id=game_id) # Permission check is done in frontend
        embed.title = "Success"
        embed.description = f"Game with the id {game_id} has been successfully deleted"
        embed.color = discord.Color.green()
    except PermissionError:
        if isinstance(interaction.user, discord.member.Member) and has_permission(user=interaction.user):
            fe.remove_game(user_id=interaction.user.id, game_id=game_id, enforce_permissions=False)
            embed.title = "Success"
            embed.description = f"Game with the id {game_id} has been successfully deleted"
            embed.color = discord.Color.green()
        else:
            embed.title = "Failed"
            embed.description = "You do not have permission to delete this game"
            embed.color = discord.Color.red()
    except Exception as e:
        embed.title = "Failed"
        embed.description = f"There was an error while executing this command:\n{e}"
        embed.color = discord.Color.red()
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

# Run the bot using the token
if TOKEN:
    try:
        bot.run(TOKEN)
    except discord.errors.LoginFailure:
        logger.exception("Login Failed: Improper token has been passed.")
    except discord.errors.PrivilegedIntentsRequired:
        logger.exception("Privileged Intents Required: Make sure Message Content Intent is enabled on the Discord Developer Portal.")
    except Exception as e:
        logger.exception(f"An error occurred while running the bot: {e}")
else:
    logger.error("DISCORD_TOKEN environment variable not found.  Set DISCORD_TOKEN environment variable before running.")
