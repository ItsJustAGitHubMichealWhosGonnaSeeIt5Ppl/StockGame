# DISCORD Bot
# SOME AI USED
# TODO set up some sort of draft system for stocks
# TODO add help command

# BUILT-IN
from datetime import datetime, timedelta
import logging
import os
import sys
from typing import Literal, Optional # 3.13 +

# EXTERNAL
import discord
from discord import app_commands
from discord.ui import Button, View
from discord.ext import commands
from dotenv import load_dotenv

# LOCAL
from helpers.datatype_validation import GameLeaderboard
from helpers.views import Pagination, LeaderboardImageGenerator, StockPortfolioImageGenerator
import helpers.autocomplete as ac
from stocks import Frontend
from helpers.exceptions import NotAllowedError, DoesntExistError, AlreadyExistsError, InvalidDateFormatError


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

# Testing variables
ephemeral_test = True # Set to False for testing, True for production
name_cutoff = 25 # Cut names off at 25 characters
dev_role_id = 1412173045350666271

# Logger thing
now = datetime.now().strftime('%Y.%m.%d.%H.%M.%S')
def setup_logging(level): 
    global console, logger
    frmt = logging.Formatter(fmt='%(asctime)s %(name)s %(levelname)s %(message)s', datefmt='%Y-%m-%d %H:%M:%S') #Format that I like
    logger = logging.getLogger('DiscordBot') # Logger name
    console = logging.StreamHandler(stream=sys.stderr)
    console.setLevel(logging.DEBUG) 
    console.setFormatter(frmt)
    logger.addHandler(console)
    
    try:
        os.mkdir('logs')
    except FileExistsError:
        pass # Folder already exists
    
    logging.basicConfig(filename=f'logs/stock_game{now}.log',filemode='w',
        format='%(asctime)s %(name)s %(levelname)s %(message)s', datefmt='%Y-%m-%d %H:%M:%S',
        level=logging.DEBUG)
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
    
    return user.guild_permissions.administrator or dev_role_id in [role.id for role in user.roles]

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

# Process pending users helper
async def process_pending_user(interaction: discord.Interaction, game_id: str, pending_users: list, current_index: int):
    """Process a single pending user with approve/deny buttons"""
    
    if current_index >= len(pending_users):
        # All users processed
        embed = discord.Embed(
            title="All Pending Users Processed",
            description=f"You have processed all pending users for game #{game_id}.",
            color=discord.Color.green()
        )
        await interaction.edit_original_response(embed=embed, view=None)
        return
    
    current_user = pending_users[current_index]
    user_id = current_user.user_id
    
    # Try to get user display name
    try:
        user = await interaction.client.fetch_user(user_id)
        user_display = f"{user.display_name} ({user.name})" if user.display_name != user.name else user.name
        user_mention = user.mention
    except:
        user_display = f"User ID: {user_id}"
        user_mention = f"<@{user_id}>"
    
    # Create embed for current pending user
    embed = discord.Embed(
        title=f"Pending User Approval ({current_index + 1}/{len(pending_users)})",
        description=f"**User:** {user_display}\n**User ID:** {user_id}\n**Game:** #{game_id}",
        color=discord.Color.orange()
    )
    embed.set_footer(text=f"Processing user {current_index + 1} of {len(pending_users)}")
    
    # Create approve/deny buttons
    approve_button = discord.ui.Button(
        label="Approve",
        style=discord.ButtonStyle.success,
        emoji="✅"
    )
    
    deny_button = discord.ui.Button(
        label="Deny",
        style=discord.ButtonStyle.danger,
        emoji="❌"
    )
    
    skip_button = discord.ui.Button(
        label="Skip",
        style=discord.ButtonStyle.secondary,
        emoji="⏭️"
    )
    
    cancel_button = discord.ui.Button(
        label="Cancel",
        style=discord.ButtonStyle.secondary,
        emoji="🚫",
        custom_id="cancel"
    )
    
    view = discord.ui.View()
    view.add_item(approve_button)
    view.add_item(deny_button)
    view.add_item(skip_button)
    view.add_item(cancel_button)
    
    # Button callbacks
    async def approve_callback(button_interaction: discord.Interaction):
        try:
            # Approve the user
            fe.approve_game_users(
                user_id=interaction.user.id,
                game_id=game_id,
                approved_user_id=user_id
            )
            
            # Try to notify the approved user
            try:
                game_name = fe._get_game_name(game_id=game_id)
                approval_embed = discord.Embed(
                    title="Game Approval",
                    description=f"You have been approved to join the game '{game_name}' (#{game_id})!",
                    color=discord.Color.green()
                )
                await user.send(embed=approval_embed)
                notification_status = "✉️ User notified"
            except:
                notification_status = "⚠️ Could not notify user (DMs disabled)"
            
            # Show confirmation and move to next user
            success_embed = discord.Embed(
                title="User Approved",
                description=f"✅ {user_display} has been approved for game #{game_id}.\n{notification_status}",
                color=discord.Color.green()
            )
            await button_interaction.response.edit_message(embed=success_embed, view=None)
            
            # Wait a moment then process next user
            import asyncio
            await asyncio.sleep(1.5)
            await process_pending_user(interaction, game_id, pending_users, current_index + 1)
            
        except Exception as e:
            logger.exception(f'Failed to approve user {user_id} for game {game_id}. Error: {e}')
            error_embed = discord.Embed(
                title="Approval Failed",
                description=f"❌ Failed to approve {user_display}.\nError: {e}",
                color=discord.Color.red()
            )
            await button_interaction.response.edit_message(embed=error_embed, view=None)
    
    async def deny_callback(button_interaction: discord.Interaction):
        try:
            # Remove the user from pending (deny them)
            participant_id = fe._participant_id(user_id=user_id, game_id=game_id)
            fe.be.remove_participant(participant_id=participant_id)
            
            # Show confirmation and move to next user
            deny_embed = discord.Embed(
                title="User Denied",
                description=f"❌ {user_display} has been denied access to game #{game_id}.",
                color=discord.Color.red()
            )
            await button_interaction.response.edit_message(embed=deny_embed, view=None)
            
            # Wait a moment then process next user
            import asyncio
            await asyncio.sleep(1.5)
            await process_pending_user(interaction, game_id, pending_users, current_index + 1)
            
        except Exception as e:
            logger.exception(f'Failed to deny user {user_id} for game {game_id}. Error: {e}')
            error_embed = discord.Embed(
                title="Denial Failed",
                description=f"❌ Failed to deny {user_display}.\nError: {e}",
                color=discord.Color.red()
            )
            await button_interaction.response.edit_message(embed=error_embed, view=None)
    
    async def skip_callback(button_interaction: discord.Interaction):
        skip_embed = discord.Embed(
            title="User Skipped",
            description=f"⏭️ Skipped {user_display}. They will remain pending.",
            color=discord.Color.blue()
        )
        await button_interaction.response.edit_message(embed=skip_embed, view=None)
        
        # Wait a moment then process next user
        import asyncio
        await asyncio.sleep(1.5)
        await process_pending_user(interaction, game_id, pending_users, current_index + 1)
    
    async def cancel_callback(button_interaction: discord.Interaction):
        cancel_embed = discord.Embed(
            title="Process Cancelled",
            description=f"Pending user management cancelled. Remaining users are still pending.",
            color=discord.Color.orange()
        )
        await button_interaction.response.edit_message(embed=cancel_embed, view=None)
    
    # Set callbacks
    approve_button.callback = approve_callback
    deny_button.callback = deny_callback
    skip_button.callback = skip_callback
    cancel_button.callback = cancel_callback
    
    # Send or edit the message
    if current_index == 0:
        await interaction.edit_original_response(embed=embed, view=view)
    else:
        await interaction.edit_original_response(embed=embed, view=view)

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
    update_frequency="How often prices should update ('daily', 'hourly')" #, 'minute', 'realtime')"
    # sell_during_game="Whether players can sell stocks during game"
)
async def create_game_advanced(
    interaction: discord.Interaction,
    name: app_commands.Range[str, 1, name_cutoff],
    start_date: str,
    end_date: str | None = None,
    starting_money: app_commands.Range[int, 1, 1000000000000] = 10000,
    total_picks: app_commands.Range[int, 1, 1000] = 10,
    exclusive_picks: bool = False,
    private_game: bool = False,
    pick_date: str | None = None,
    update_frequency: Literal['daily', 'hourly'] = "daily", #Literal['daily', 'hourly', 'minute', 'realtime'] = "daily",
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
     
    await interaction.response.send_message(embed=embed, ephemeral=ephemeral_test)

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
    await interaction.response.send_message(embed=embed, view=game_creation_button_view, ephemeral=ephemeral_test)
    
    # Define what happens when the button is clicked
    async def game_creation_wizard_start_callback(interaction: discord.Interaction):
        # Create a modal (popup) for text input
        initial_wizard_modal = discord.ui.Modal(title="Create Game Wizard", timeout=60)

        # Add a text input field for each text and number input
        name_input = discord.ui.TextInput(
            label="Name of your Stock Game",
            placeholder=f"{interaction.user.display_name}'s Stock Game",
            required=True,
            max_length=name_cutoff,
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
                        description="If you select 'Yes', the game ID will be hidden in the game-list command. If you select 'No', it will be visible. All private games require owner approval for new users to join. **Owners will have to run the /manage-pending command to approve or deny new users.**",
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

                        # update_frequency_minute = discord.ui.Button(
                        #     label="Minute",
                        #     style=discord.ButtonStyle.success,
                        #     custom_id="update_frequency_minute"
                        # )

                        # update_frequency_realtime = discord.ui.Button(
                        #     label="Realtime",
                        #     style=discord.ButtonStyle.success,
                        #     custom_id="update_frequency_realtime"
                        # )

                        update_frequency_view = discord.ui.View()
                        update_frequency_view.add_item(update_frequency_daily)
                        update_frequency_view.add_item(update_frequency_hourly)
                        # update_frequency_view.add_item(update_frequency_minute)
                        # update_frequency_view.add_item(update_frequency_realtime)

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
                                
                                except InvalidDateFormatError as e: # This handles invalid dates
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
                        # update_frequency_minute.callback = update_frequency_callback
                        # update_frequency_realtime.callback = update_frequency_callback
                
                    # Set the join after button callback
                    private_yes.callback = private_game_callback
                    private_no.callback = private_game_callback

                # Set the pick date modal callback
                pick_date_modal.on_submit = pick_date_callback

            # Set the exclusive button callback
            exclusive_picks_yes.callback = exclusive_picks_callback
            exclusive_picks_no.callback = exclusive_picks_callback

        # Set the modal callback
        initial_wizard_modal.on_submit = initial_wizard_callback

    # Set the button callback
    game_creation_wizard_start.callback = game_creation_wizard_start_callback    

@bot.tree.command(name="create-recurring-game", description="Create a recurring game template (Moderator Only)")
@app_commands.describe(
    name="Name of the game template",
    start_date="Start date (YYYY-MM-DD)",
    recurring_period="Months between recurring games (optional, default: 1)",
    game_length="How many months should the game last. 0 = infinite game (optional, default: 1)", 
    create_days_in_advance="How many days before start_date to create the game (optional, default: 7)",
    starting_money="Starting money for players (optional, default: 10000)",
    pick_date="Pick deadline in days before start of month. Negative numbers are after start of month. Empty for no pick date (optional)",
    private_game="Make the game private (optional, default: False)",
    total_picks="Maximum number of picks per player (optional, default: 10)",
    exclusive_picks="Enable draft mode - each stock can only be picked once (optional, default: False)",
    # sell_during_game="Allow selling stocks during the game (optional, default: False)",
    update_frequency="How often to update game data ('daily', 'hourly') (optional, default: daily)"
)
async def create_recurring_game(
    interaction: discord.Interaction,
    name: app_commands.Range[str, 1, name_cutoff],
    start_date: str,
    recurring_period: app_commands.Range[int, 1, 12] = 1,
    game_length: int = 1,
    create_days_in_advance: app_commands.Range[int, 0, 30] = 7,
    starting_money: app_commands.Range[int, 1, 1000000000000] = 10000,
    pick_date: int | None = None,
    private_game: bool = False,
    total_picks: app_commands.Range[int, 1, 1000] = 10,
    exclusive_picks: bool = False,
    # sell_during_game: bool = False,
    update_frequency: Literal['daily', 'hourly'] = "daily"
):
        """Create a recurring game template"""
        
        # Defer the response since backend operations might take time
        await interaction.response.defer(ephemeral=ephemeral_test)
        
        sell_during_game: bool = False

        try:            
            # Validate update frequency
            valid_frequencies = ['daily', 'hourly', 'weekly']
            if update_frequency.lower() not in valid_frequencies:
                await interaction.followup.send(
                    f"❌ Invalid update frequency. Must be one of: {', '.join(valid_frequencies)}", 
                    ephemeral=ephemeral_test
                )
                return


            # Validate pick date number
            if pick_date is not None:
                if pick_date < -30 or pick_date > 30:
                    await interaction.followup.send(
                        "❌ Pick date must be between -30 and 30 days relative to the start of the month.",
                        ephemeral=ephemeral_test
                    )
                    return


            # Get user ID
            user_id = interaction.user.id
            
            # Create the game template using backend
            fe.be.add_game_template(
                user_id=user_id,
                name=name,
                start_date=start_date,
                create_days_in_advance=create_days_in_advance,
                recurring_period=recurring_period,
                game_length=game_length,
                starting_money=starting_money,
                pick_date=pick_date,
                private_game=private_game,
                total_picks=total_picks,
                exclusive_picks=exclusive_picks,
                sell_during_game=sell_during_game,
                update_frequency=update_frequency
            )
            
            # Create success embed
            embed = discord.Embed(
                title="✅ Recurring Game Template Created!",
                description=f"Successfully created recurring game template: **{name}**",
                color=discord.Color.green(),
                timestamp=datetime.now()
            )
            
            # Add game details to embed
            embed.add_field(name="📅 Start Date", value=start_date, inline=True)
            embed.add_field(name="🔄 Recurring Every", value=f"{recurring_period} months", inline=True)
            embed.add_field(name="⏱️ Game Length", value=(f"{game_length} months" if game_length != 0 else "infinite"), inline=True)
            embed.add_field(name="💰 Starting Money", value=f"${starting_money:,.2f}", inline=True)
            embed.add_field(name="📊 Total Picks", value=str(total_picks), inline=True)
            embed.add_field(name="🔒 Private", value="Yes" if private_game else "No", inline=True)
            
            if pick_date:
                pick_date_text: str = f"{pick_date} days before the 1st" if pick_date >= 1 else f"{pick_date * -1} days after the 1st"
                embed.add_field(name="📝 Pick Deadline", value=pick_date_text, inline=True)
            
            embed.add_field(name="🎯 Exclusive Picks", value="Yes" if exclusive_picks else "No", inline=True)
            # embed.add_field(name="💸 Selling Allowed", value="Yes" if sell_during_game else "No", inline=True)
            embed.add_field(name="🔄 Update Frequency", value=update_frequency.title(), inline=True)
            embed.add_field(name="⏰ Create in Advance", value=f"{create_days_in_advance} days", inline=True)
            
            embed.set_footer(text=f"Created by {interaction.user.display_name}")
            
            await interaction.followup.send(embed=embed, ephemeral=ephemeral_test)
            
        except Exception as e:
            # Handle specific backend errors
            error_message = "❌ Failed to create recurring game template."
            
            if "InvalidDateFormatError" in str(type(e)):
                error_message = "❌ Invalid date format. Please use YYYY-MM-DD format."
            else:
                error_message += f" Error: {str(e)}"
            
            await interaction.followup.send(error_message, ephemeral=ephemeral_test)

# TODO Handle more specific errors when implemented (private game, invalid game id, etc)
@bot.tree.command(name="join-game", description="Join an existing stock game")
@app_commands.describe(
    game_id="ID of the game to join",
    name="Name to display for your picks (optional)"
)
async def join_game(
    interaction: discord.Interaction, 
    game_id: str,
    name: str | None = None
):
    
    if not name:
        name = interaction.user.display_name
    
    status = 'failed'
    description = "failed"
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
        description = f'No game with the ID {game_id}.'
        
    except ValueError as e:
        if 'already in game.' in str(e).lower():
            description = f'You are already in this game ID {game_id}.'
            
        elif '`pick_date` has passed.' in str(e).lower():
            description = f'The pick date for this game has passed.'
            
    except Exception as e:
        logger.exception(f'User: {interaction.user.id} failed to join game {game_id}.  Error: {e}')
        description = f'An unexpected error ocurred. Please report this! {game_id}.\n{e}'

    if status == 'failed':
        title = "Game Join Failed"

    await interaction.response.send_message(embed=simple_embed(status = status, title = title, desc = description), ephemeral=ephemeral_test)

@bot.tree.command(name="delete-game", description="For admins to delete games if needed")
@app_commands.autocomplete(game_id=ac.owner_games_autocomplete)
@app_commands.describe(
    game_id="The game ID to delete"
)
async def delete_game(
    interaction: discord.Interaction,
    game_id: str,
):
    embed = discord.Embed()
    try:
        fe.remove_game(user_id=interaction.user.id, game_id=game_id) # Permission check is done in frontend
        embed.title = "Success"
        embed.description = f"Game with the id {game_id} has been successfully deleted"
        embed.color = discord.Color.green()
    except PermissionError:
        if isinstance(interaction.user, discord.member.Member) and has_permission(user=interaction.user):
            fe.remove_game(user_id=interaction.user.id, game_id=game_id, enforce_permissions=True)
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
    
    await interaction.response.send_message(embed=embed, ephemeral=ephemeral_test)

@bot.tree.command(name="manage-game", description="Manage an existing stock game")
@app_commands.autocomplete(game_id=ac.owner_games_autocomplete)
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
    update_frequency="How often prices should update ('daily', 'hourly')", #, 'minute', 'realtime')"
)
async def manage_game(
    interaction: discord.Interaction, 
    game_id: str,
    name: app_commands.Range[str, 1, name_cutoff] | None = None,
    owner: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    starting_money: app_commands.Range[int, 1, 1000000000000] | None = None,
    total_picks: app_commands.Range[int, 1, 1000] | None = None,
    pick_date: str | None = None,
    private_game: bool | None = None,
    draft_mode: bool | None = None,
    sell_during_game: bool | None = None,
    update_frequency: Literal['daily', 'hourly'] | None = None
):
    
    try:
        game_info = fe.game_info(game_id, False)
    except LookupError:
        embed = discord.Embed(
            title="Game Not Found",
            description=f"Could not find a game with ID {game_id}.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=ephemeral_test)
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
        
    except ValueError as e: # Should catch issues
        embed = discord.Embed(
            title="Game Update Failed",
            description=e,
            color=discord.Color.red()
        )
    except Exception as e:
        embed = discord.Embed(
            title="Game Update Failed",
            description=e,
            color=discord.Color.red()
        )

    await interaction.response.send_message(embed=embed, ephemeral=ephemeral_test)

#TODO fix response to command
@bot.tree.command(name="invite", description="Invite a user to a game")
@app_commands.autocomplete(game_id=ac.all_games_autocomplete)
@app_commands.describe(
    game_id="ID of the game to invite them to",
    user="User to invite"
)
async def invite_user(
    interaction: discord.Interaction, 
    game_id: str,
    user: discord.User
):
    await interaction.response.defer(ephemeral=ephemeral_test) # Defer the response to allow time for the update

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
    
        await interaction.followup.send(
            content=f"Invite sent to {user.mention}.",
            embed=invite_response_embed,
            ephemeral=ephemeral_test
        )

        await user.send(embed=invite_embed, view=view)
    except discord.Forbidden:
        # If the user has DMs disabled, send a message in the channel instead
        invite_response_embed = discord.Embed(
            title="Invite Not Sent",
            description=f"Could not send invite to {user.mention}. They have DMs disabled.",
            color=discord.Color.blue()
        )
        
        await interaction.followup.send(
            embed=invite_response_embed,
            ephemeral=ephemeral_test
        )

    except Exception as e:
        logger.exception(f'User: {interaction.user.id} tried to invite user: {user.id} to game: {game_id}. Error: {e}')
        error_embed = discord.Embed(
            title="Invite Failed",
            description=f"An unexpected error occurred while trying to invite {user.mention} to game #{game_id}.",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=error_embed, ephemeral=ephemeral_test)

@bot.tree.command(name="manage-pending", description="Approve or deny pending users for your private game")
@app_commands.autocomplete(game_id=ac.owner_games_autocomplete)
@app_commands.describe(
    game_id="ID of the game to manage pending users for"
)
async def manage_pending(
    interaction: discord.Interaction,
    game_id: str
):
    await interaction.response.defer(ephemeral=ephemeral_test)
    
    try:
        # Get pending users for the game
        pending_users = fe.pending_game_users(
            user_id=interaction.user.id,
            game_id=game_id
        )
        
        if not pending_users:
            embed = discord.Embed(
                title="No Pending Users",
                description=f"There are no pending users for game #{game_id}.",
                color=discord.Color.blue()
            )
            await interaction.followup.send(embed=embed, ephemeral=ephemeral_test)
            return
        
        # Start the approval process with the first pending user
        await process_pending_user(interaction, game_id, list(pending_users), 0)
        
    except PermissionError:
        embed = discord.Embed(
            title="Permission Denied",
            description="You don't have permission to manage pending users for this game.",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed, ephemeral=ephemeral_test)
    except Exception as e:
        logger.exception(f'User: {interaction.user.id} failed to get pending users for game {game_id}. Error: {e}')
        embed = discord.Embed(
            title="Error",
            description=f"An unexpected error occurred while getting pending users.\n{e}",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed, ephemeral=ephemeral_test)
  
@bot.tree.command(name="list-game-templates", description="List your game templates (Moderator Only)")
@app_commands.describe(
    show_all="Show all templates (default: False, only shows first 10)"
)
async def list_game_templates(
    interaction: discord.Interaction,
    show_all: bool = False
):
    """List game templates for the user"""
    try:
        # Get templates from backend - assuming it has a method to get by user
        templates = fe.be.get_many_game_templates(status=None)  # Adjust this based on your backend
        
        # Filter by user if needed (depends on your backend implementation)
        user_templates = [t for t in templates if t.owner_id == interaction.user.id]
        
        if not user_templates:
            embed = discord.Embed(
                title="No Game Templates Found",
                description="You haven't created any recurring game templates yet.",
                color=discord.Color.orange()
            )
        else:
            embed = discord.Embed(
                title="Your Game Templates",
                description=f"Found {len(user_templates)} template(s)",
                color=discord.Color.blue()
            )
            
            # Add templates to embed
            if not show_all:
                user_templates = user_templates[:10]
            for template in user_templates:
                # Format pick date display
                pick_date_text = "No deadline"
                if template.pick_date is not None:
                    if template.pick_date >= 1:
                        pick_date_text = f"{template.pick_date} days before 1st"
                    else:
                        pick_date_text = f"{abs(template.pick_date)} days after 1st"
                
                # Format game length
                game_length_text = "Infinite" if template.game_length == 0 else f"{template.game_length} months"
                
                embed.add_field(
                    name=f"📋 {template.name}",
                    value=(
                        f"🔄 Every {template.recurring_period} months\n"
                        f"📅 Start: {template.start_date}\n"
                        f"⏱️ Length: {game_length_text}\n"
                        f"⏰ Create: {template.create_days_in_advance} days early\n"
                        f"💰 Starting: ${template.start_money:,}\n"
                        f"📝 Pick deadline: {pick_date_text}\n"
                        f"🔒 Private: {'Yes' if template.private_game else 'No'}\n"
                        f"📊 Total picks: {template.pick_count}\n"
                        f"🎯 Exclusive: {'Yes' if template.draft_mode else 'No'}\n"
                        f"💸 Selling: {'Yes' if template.allow_selling else 'No'}\n"
                        f"🔄 Updates: {template.update_frequency.title()}"
                    ),
                    inline=True
                )
           
            if len(user_templates) > 10 or show_all:
                embed.set_footer(text=f"Showing first 10 of {len(user_templates)} templates")
        
    except Exception as e:
        embed = discord.Embed(
            title="Failed to List Game Templates",
            description=str(e),
            color=discord.Color.red()
        )
        logger.exception(f'User: {interaction.user.id} failed to list game templates. Error: {e}')
    
    await interaction.response.send_message(embed=embed, ephemeral=ephemeral_test)

@bot.tree.command(name="update", description="Update the all game stock prices (Moderator Only)")
@app_commands.describe(
    # game_id="ID of the game to update", - NOT IMPLEMENTED IN force_update
)
async def update(
    interaction: discord.Interaction, 
    # game_id: str, - NOT IMPLEMENTED IN force_update
):
    await interaction.response.defer(ephemeral=ephemeral_test) # Defer the response to allow time for the update
    embed = discord.Embed()
    try:
        fe.force_update(
            user_id=interaction.user.id,
            enforce_permissions=True
        )
        embed.title = "Success"
        embed.description = f"All games have been successfully updated"
        embed.color = discord.Color.green()
    except PermissionError:
        embed.title = "Failed"
        embed.description = "You do not have permission to update this game"
        embed.color = discord.Color.red()
    except Exception as e:
        embed.title = "Failed"
        embed.description = f"There was an error while executing this command:\n{e}"
        embed.color = discord.Color.red()

    await interaction.followup.send(embed=embed, ephemeral=ephemeral_test)


# STOCK RELATED

@bot.tree.command(name="buy-stock", description="Buy a stock in a game")
@app_commands.autocomplete(game_id=ac.all_games_autocomplete)
@app_commands.describe(
    game_id="ID of the game",
    ticker="Stock ticker symbol"
)
async def buy_stock(
    interaction: discord.Interaction, 
    game_id: str, 
    ticker: str
):
    await interaction.response.defer(ephemeral=ephemeral_test) # Defer the response to allow time for the update
    status = 'failed' # Start with failed status
    title = 'Stock Purchase Failed'
    try:
        ticker = ticker.upper()
        fe.buy_stock(
            user_id=interaction.user.id,
            game_id=game_id,
            ticker=ticker
        )
        title = 'Stock Purchased'
        description = f'You have successfully bought {ticker} in game: {game_id}.'
        status = 'success'

    except ValueError as exc:
        if 'Invalid Ticker, too long!' in str(exc):
            description = f'The ticker {ticker} is not valid!'
        
        elif 'Stock is not tradeable' in str(exc):
            description = f'The ticker {ticker} is not tradeable.  This can occur when a stock is private or has been delisted.'
            
        elif 'Unable to find stock' in str(exc) or 'Failed to add `ticker`' in str(exc):
            description = f'The ticker {ticker} was not found.  Double check your spelling and try again!'
        
        else:
            logger.exception(f'Uncaught value error user: {interaction.user.id} tried to buy stock with ticker: {ticker}', exc_info=exc)
            'An error ocurred while finding your stock.'
    
    except LookupError:
        description = f'No game with ID {game_id} found.'
    
    except NotAllowedError as exc: # REASONS ARE NOW IN THE DOCSTRING OF buy_stock!!
        if exc.reason == 'Not active': # Player isn't an active member of the game - IDK HOW YOU WANT TO TELL THE USER THIS.  This could happen if they got banned, or if the game is private and they haven't been approved
            description = f'You are not allowed to buy stocks in the game: {game_id}.'
        
        elif exc.reason == 'Maximum picks reached':
            title="Game Pick Limit Reached"
            description = f'You have reached the maximum number of picks for this game.\nTo add another stock, you need to remove one of your current picks.'
        
        elif exc.reason == 'Past pick_date':
            description = f'The pick date for this game has passed, so you can no longer pick stocks.'
    
    except AlreadyExistsError as exc:
        description = f'You already own {ticker} in this game!'
        
    except DoesntExistError as exc: # Player isnt in the game at all
        if exc.table == 'game_participants':
            description = f'You are not in the game: {game_id}.'

    except Exception as e: # Other unexpeted errors
        logger.exception(f'User: {interaction.user.id} tried to buy the stock: {ticker} in game: {game_id}. Error: {e}')
        description=f'An unexpected error ocurred while trying to buy a stock\nReport this! Ticker: {ticker}, Game: {game_id}'
            
    await interaction.followup.send(
        embed=simple_embed( # This just creates the status message
            status = status,
            title = title,
            desc = description
            ), 
        ephemeral=ephemeral_test
        )

@bot.tree.command(name="remove-stock", description="Remove a stock from your picks")
@app_commands.autocomplete(game_id=ac.all_games_autocomplete, ticker=ac.sell_ticker_autocomplete)
@app_commands.describe(
    game_id="ID of the game",
    ticker="Stock ticker symbol"
)
async def remove_stock(
    interaction: discord.Interaction, 
    game_id: str, 
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

    await interaction.response.send_message(embed=simple_embed(status = status, title = title, desc = description), ephemeral=ephemeral_test)

# TODO Add buttons for buying/selling stocks?
# TODO Add last updated date/time in footer
@bot.tree.command(name="my-stocks", description="View your stocks in a game as a visual portfolio")
@app_commands.autocomplete(game_id=ac.all_games_autocomplete)
@app_commands.describe(
    game_id="ID of the game"
)
async def my_stocks(
    interaction: discord.Interaction,
    game_id: str
):
    user_id = interaction.user.id
    await interaction.response.defer(ephemeral=ephemeral_test)
    
    try:
        picks = fe.my_stocks(user_id, game_id)
        info = fe.game_info(game_id)
        
        # Prepare data for image generator
        user_data = {
            'display_name': interaction.user.display_name,
            'user_id': user_id
        }
        
        game_data = {
            'name': fe._get_game_name(game_id=game_id),
            'id': game_id
        }
        
        # Convert pick objects to dictionaries
        stock_picks = []
        for pick in picks:
            stock_dict = {
                'stock_ticker': pick.stock_ticker,
                'status': pick.status,
                'shares': pick.shares,
                'current_value': pick.current_value,
                'change_dollars': pick.change_dollars,
                'change_percent': pick.change_percent,
                'last_updated': pick.last_updated
            }
            stock_picks.append(stock_dict)
        
        # Generate image
        generator = StockPortfolioImageGenerator(theme='discord_dark')
        image_buffer = generator.create_portfolio_image(user_data, game_data, stock_picks, info)
        
        # Create Discord file
        file = discord.File(image_buffer, filename=f"portfolio_{user_id}_{game_id}.png")
        
        # Send image with a simple message
        await interaction.followup.send(
            file=file,
            ephemeral=ephemeral_test
        )
        
    except DoesntExistError:
        embed = simple_embed(
            status='failed', 
            title='Not in Game',
            desc='You are not currently participating in this game. You can try to join it using the join-game command.'
        )
        await interaction.followup.send(embed=embed, ephemeral=ephemeral_test)
        
    except LookupError:
        embed = simple_embed(
            status='failed',
            title='No Stocks Found', 
            desc=f'You don\'t currently have any stocks in game: {game_id}'
        )
        await interaction.followup.send(embed=embed, ephemeral=ephemeral_test)
        
    except Exception as e:
        logger.exception(f'User: {interaction.user.id} tried to generate portfolio image for game: {game_id}. Error: {e}')
        embed = simple_embed(
            status='failed',
            title='Error Generating Portfolio',
            desc='An unexpected error occurred while generating your portfolio image'
        )
        await interaction.followup.send(embed=embed, ephemeral=ephemeral_test)


# GAME INFO RELATED-

@bot.tree.command(name="game-info", description="View information about a game")
@app_commands.autocomplete(game_id=ac.all_games_autocomplete)
@app_commands.describe(
    game_id="ID of the game to view",
    show_leaderboard="Whether to display the leaderboard or not, will by default"
)
async def game_info(
    interaction: discord.Interaction,
    game_id: str,
    show_leaderboard: bool = True
):
    await interaction.response.defer(ephemeral=ephemeral_test)
    
    try:
        game_info_obj = fe.game_info(game_id, show_leaderboard=True)
        game = game_info_obj.game
        assert isinstance(game_info_obj.leaderboard, list)
        
        # Basic embed for game info
        description_str = '> **Owner:** <@{owner_id}>{pick_info}\n{start_cash}\n{pick_count}\n{date_range}\n{participants}'.format(
            owner_id=game.owner_id,
            pick_info=f'\n> **Pick date:** {game.pick_date}' if game.pick_date else '',
            start_cash=f'> **Starting Cash:** ${int(game.start_money)}',
            pick_count=f'> **Pick Count:** `{game.pick_count}`',
            date_range='> ' + str('Started' if game.status != 'open' else 'Starting') + f' `{game.start_date}`' + str(str(', ends' if game.status != 'ended' else ', ended') + f' `{game.end_date}`') if game.end_date else '',
            participants=f'> **Participants:** `{len(game_info_obj.leaderboard)}`',
        )
        
        embed = discord.Embed(
            title=f'{game.name} ({game.id})',
            description=description_str
        )
        embed.set_footer(text="Dates are formatted as (YYYY-MM-DD)")
        
        if not show_leaderboard:
            await interaction.response.send_message(embed=embed, ephemeral=ephemeral_test)
            return
        
        # Limit leaderboard to top 10
        # lb_limit = 10
        leaderboard_info: list[GameLeaderboard] = game_info_obj.leaderboard#[:lb_limit]
        
        # Fetch user display names and prepare data for image
        processed_leaderboard = []
        for info in leaderboard_info:
            player_data = {
                'user_id': info.user_id,
                'current_value': info.current_value,
                'joined': info.joined,
                'change_dollars': info.change_dollars,
                'change_percent': info.change_percent,
                'last_updated': info.last_updated
            }
            
            try:
                member = await interaction.guild.fetch_member(info.user_id)
                if len(member.display_name) <= 16:
                    display_name = member.display_name
                elif len(member.global_name or "") <= 16:
                    display_name = member.global_name
                elif len(member.name) <= 16:
                    display_name = member.name
                else:
                    display_name = (member.global_name or member.name)[:15] + "~"
                player_data['display_name'] = display_name
            except discord.errors.NotFound:
                player_data['display_name'] = f'ID({info.user_id})'
            
            processed_leaderboard.append(player_data)
        
        # Create the leaderboard image using the new class
        try:
            # Prepare game data for image generation
            game_data = {
                'name': game.name,
                'id': game.id,
                'owner': game.owner_id,
                'starting_money': game.start_money,
                'start_date': str(game.start_date),
                'end_date': str(game.end_date) if game.end_date else None,
                'status': game.status
            }
            
            # Add owner name to game data for the image
            try:
                owner_member = await interaction.guild.fetch_member(game.owner_id)
                game_data['owner_name'] = owner_member.display_name or owner_member.global_name or owner_member.name
            except:
                game_data['owner_name'] = f'ID({game.owner_id})'
            
            generator = LeaderboardImageGenerator(theme='discord_dark')
            image_buffer = generator.create_leaderboard_image(game_data, processed_leaderboard)
            
            # Create Discord file from buffer
            file = discord.File(image_buffer, filename="leaderboard.png")
            
            # Send embed with image
            embed.set_image(url="attachment://leaderboard.png")
            await interaction.followup.send(embed=embed, file=file, ephemeral=ephemeral_test)
            
        except Exception as e:
            # Fallback to text-based leaderboard if image generation fails
            print(f"Image generation failed: {e}")
            
            # Your original markdown table code as fallback
            pos = ['🥇', '🥈', '🥉', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣', '🔟']
            ldrbrd_lines = ['| 🏆 |     Investor     |    Portfolio    |   Joined   |']
            row_template = '| {pos} | {user} | {value} | {date} |'
            
            for rank, player_data in enumerate(processed_leaderboard):
                ldrbrd_lines.append(row_template.format(
                    pos=pos[rank] if rank < len(pos) else f'{rank+1}️⃣',
                    user=player_data['display_name'].center(16),
                    value=str('$' + format(float(player_data["current_value"]), ',')).center(15),
                    date=f'{datetime.strftime(player_data["joined"], "%Y-%m-%d")[:10]}'
                ))
            
            leaderboard_block = '```\n{}\n```'.format('\n'.join(ldrbrd_lines))
            embed.add_field(name="Leaderboard", value=leaderboard_block, inline=False)
            await interaction.response.send_message(embed=embed, ephemeral=ephemeral_test)
            
    except Exception as e:
        # Handle case where game doesn't exist
        embed = discord.Embed(
            title='Failed to get info',
            description=f'Game with ID {game_id} does not exist or an error occurred.',
            color=0xff0000
        )
        await interaction.response.send_message(embed=embed, ephemeral=ephemeral_test)

# TODO add buttons for joining games?
# TODO add a joinable parameter?
# TODO max page length cant be more than 25
@bot.tree.command(name="game-list", description="View a list of all games") # TODO rename to list-games, all-games, or games-list?
@app_commands.describe(
    page_length="The length of the list per page. Defaults to 9"
)
async def game_list(
    interaction: discord.Interaction,
    page_length: int = 9 # 9 looks nicer than 10
):
    embed = discord.Embed()
    error = False
    try:
        games = fe.list_games(include_open=True, include_active=True) # Only get currently running games. Does not include private games
        
        embed = discord.Embed(title="Currently running games", description="")
        formatted_games = [] # 
        for game in games: # Make a field for each game
            formatted_games.append(( 
                f"{game.name[:name_cutoff]}: [{game.id}]", #TODO switch this to use the simpler formatting
                '> **Owner:** <@{owner_id}>{pick_info}\n{start_cash}\n{date_range}'.format(owner_id=game.owner_id,
                pick_info=f'\n> **Pick date:** {game.pick_date}' if game.pick_date else '',
                start_cash=f'> **Starting Cash:** ${int(game.start_money)}',
                date_range= '> ' + str('Started' if game.status != 'open' else 'Starting') + f' `{game.start_date}`' + str(str(', ends' if  game.status != 'ended' else ', ended') + f' `{game.end_date}`') if game.end_date else ''
                    )
                ) # Tuple of game info
                ) # Formatted games
        await Pagination(interaction, page_len=page_length, embed=embed, games=formatted_games, ephemeral=ephemeral_test).navigate()

    except LookupError as e:
        error = True
        embed.title = 'No games found'
        embed.description = 'There are no public open or active games'
        embed.color = discord.Color.red()
        
    except Exception as e:
        error = True
        logger.exception(f'Error when loading game list. Page length: {page_length}', exc_info=e)
        embed.title = 'Error'
        embed.description = f'An unexpected error ocurred while trying to load games\nReport this!'
    
    if error:
        await interaction.response.send_message(embed=embed, ephemeral=ephemeral_test)

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
        game_description: str = ""
        # Add each game to the embed
        for game in games.games: #TODO provide more info here
            # Create status indicator
            status_emoji = "🟢" if game.status != 'ended' else "🔴"
                        
            # Add game field
            game_description= game_description + f"{status_emoji} {game.name[:name_cutoff]}   ID: {game.id}\n"

        embed.description = game_description
        embed.set_footer(text=f"Use /game-info <game_id> for more details")

    except Exception as e:
        logger.exception(f'User: {interaction.user.id} tried to get their games. Error: {e}')
        embed.description = "No games found"
        embed.color = discord.Color.red()
    
    # Send the response
    await interaction.response.send_message(embed=embed, ephemeral=ephemeral_test)

@bot.tree.command(name="user-stats", description="Shows global statistics of a user. Shows yours by default.")
@app_commands.describe(
    user="The ID of the user you want to see stats for"
)
async def user_stats(
    interaction: discord.Interaction,
    user: discord.User | None
):
    await interaction.response.defer(ephemeral=ephemeral_test) # Defer the response to allow time for the update
    try:
        discord_user: discord.User | discord.Member = user if user else interaction.user
        user_title = f"{discord_user.display_name}{f' ({discord_user.name})' if discord_user.display_name != discord_user.name else ''}"
        
        user_stats = fe.get_user(discord_user.id)

        embed = discord.Embed(title=user_title, description="Global Statistics")
        embed.set_thumbnail(url=discord_user.display_avatar)
        embed.add_field(name="Total wins:", value=user_stats.overall_wins)
        embed.add_field(name="Change Dollars/Change %", value=f"{user_stats.change_dollars}/{user_stats.change_percent}")
        embed.color = discord.Color.blue()

        await interaction.followup.send(embed=embed, ephemeral=ephemeral_test)
    except LookupError:
        embed = discord.Embed(title="User not found", description="User does not exist in our system!")
        embed.color = discord.Color.red()
        await interaction.followup.send(embed=embed, ephemeral=ephemeral_test)

# ABOUT, LOGS AND HELP COMMANDS
@bot.tree.command(name="about", description="About the bot and its creators")
async def about(
    interaction: discord.Interaction,
):
    creators = "<@163784331804934144>: Project Leader, Coordinated Strategic Management Lead, Frontend Dev, Backend Dev, gave the idea for the about command" \
    "\n<@329374393715392520>: Frontend Dev, Bot Dev, made really big bot commits" \
    "\n<@1240817181692792934>: Bot Dev, made the about command, strategy consultant"

    embed = discord.Embed(title="About the bot", description="[StockBot](https://github.com/ItsJustAGitHubMichealWhosGonnaSeeIt5Ppl/StockGame) is a discord bot that simulates the purchase of stocks and runs them in a gamified format. Originally built for the Lemonade Stand community.")
    embed.add_field(name="Creators", value=creators)
    embed.add_field(name="Special Thanks", value="<@394012218729168907>: Gave the idea\n<@204414583203430400>: Chaotic Project Tester")
    await interaction.response.send_message(embed=embed, ephemeral=ephemeral_test)

@bot.tree.command(name="logs", description="(Moderator Only) For admins to get logs") # For debugging, get logs
async def logs(
    interaction: discord.Interaction,
):
    
    if has_permission(interaction.user): # Check if user is an admin
        title = "Logs"
        status = 'success'
        logfile = discord.File(fp=f'logs/stock_game{now}.log', filename='log-latest.log')
        await interaction.response.send_message(embed=simple_embed(status=status, title=title, desc=''), file=logfile, ephemeral=ephemeral_test)

    else:
        title = "Not Allowed"
        status = 'failed'
        logs = 'Must be admin to get logs'
        await interaction.response.send_message(embed=simple_embed(status=status, title=title, desc=logs), ephemeral=True)

@bot.tree.command(name="help", description="Get help with StockBot")
async def help(interaction: discord.Interaction):
    title = "Stock Game Bot - Help"
    help_text = """
## Available Commands
All commands include built-in hints and help when you run them!

### Game Management
- `/create-game` - Guided setup for stock game creation
- `/create-game-advanced` - Create a new stock game without a wizard
- `/manage-game` - Manage an existing stock game
- `/delete-game` - For owners and admins to delete games
- `/invite` - Invite a user to a game
- `/manage-pending` - Approve or deny pending users for your private game

### Playing Games
- `/join-game` - Join an existing stock game
- `/buy-stock` - Buy a stock in a game
- `/remove-stock` - Remove a pending stock from your picks
- `/my-stocks` - View your stocks in a game as a visual portfolio

### Information & Stats
- `/game-info` - View information about a game
- `/game-list` - View a list of all games
- `/my-games` - View your games and their status
- `/user-stats` - Shows global statistics of a user. Shows yours by default
- `/about` - About the bot and its creators

### Moderator Commands
- `/create-recurring-game` - Create a recurring game template (Moderator only)
- `/list-recurring-games` - List your recurring game templates (Moderator only)
- `/update` - Update the all game stock prices (Moderator only)
- `/logs` - For admins to get logs (Moderator only)

## How to Play
1. **Join a game** using `/join-game` or create your own with `/create-game`
2. **Buy stocks** using `/buy-stock` 
3. **Watch the leaderboard** and see how your picks perform!

## Need Help?
Use `/help` to see this message again, or contact a moderator if you encounter any issues!"""
    await interaction.response.send_message(embed=simple_embed(status='success', title=title, desc=help_text), ephemeral=ephemeral_test)

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
