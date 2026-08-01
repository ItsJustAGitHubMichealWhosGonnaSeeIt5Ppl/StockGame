# DISCORD Bot
# SOME AI USED
# Draft exclusivity is enforced by the backend; Discord exposes it during game creation.
# TODO set up some sort of draft system for stocks

# BUILT-IN
from datetime import datetime, timedelta
import asyncio
import io
import logging
import os
import sys
from typing import Any, Literal, Mapping, Optional, cast # 3.13 +

# EXTERNAL
import discord
from discord import app_commands
from discord.ui import Button, View
from discord.ext import commands, tasks
from dotenv import load_dotenv

# LOCAL
from helpers.datatype_validation import GameLeaderboard
from helpers.views import Pagination, LeaderboardImageGenerator, StockPortfolioImageGenerator
import helpers.autocomplete as ac
from helpers.logging_setup import (
    attach_critical_dm_bot,
    flush_critical_dm_queue,
    latest_log_path,
    setup_app_logging,
)
from stocks import Frontend
from helpers.exceptions import NotAllowedError, DoesntExistError, AlreadyExistsError, InvalidDateFormatError


load_dotenv()

TOKEN = os.getenv('DISCORD_TOKEN')
DB_NAME = os.getenv('DB_NAME')
OWNER = os.getenv('OWNER')
if not TOKEN or not DB_NAME or not OWNER:
    raise RuntimeError('Missing one or more required environment variables: DISCORD_TOKEN, DB_NAME, OWNER.')
try:
    OWNER_ID = int(OWNER)
except ValueError as exc:
    raise RuntimeError('OWNER must be a numeric Discord user ID.') from exc
    

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

logger = setup_app_logging(console_level=logging.INFO, root_level=logging.DEBUG)

def has_permission(user:discord.member.Member):
    """Check if a user has permission to create/manage games
    
    Currently only checks for admin

    Args:
        user (discord.member.Member): Member (user) object.
        
    Returns:
        bool: True if allowed
    """
    
    return user.guild_permissions.administrator or dev_role_id in [role.id for role in user.roles]

def is_moderator(interaction: discord.Interaction) -> bool:
    """Return whether the interaction author may run moderator commands."""
    if interaction.user.id == OWNER_ID:
        return True
    return isinstance(interaction.user, discord.Member) and has_permission(interaction.user)

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

def interaction_custom_id(interaction: discord.Interaction) -> str:
    data = cast(Mapping[str, Any], interaction.data or {})
    value = data.get('custom_id')
    return value if isinstance(value, str) else ''


class InitiatorOnlyView(discord.ui.View):
    """A short-lived component view restricted to the command initiator."""

    def __init__(self, initiator_id: int, *, timeout: float = 120):
        super().__init__(timeout=timeout)
        self.initiator_id = initiator_id
        self.message: discord.InteractionMessage | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.initiator_id:
            return True
        await interaction.response.send_message(
            "Only the person who started this command can use these controls.",
            ephemeral=True,
        )
        return False

    async def on_timeout(self):
        if self.message is None:
            return
        try:
            embed = self.message.embeds[0].copy() if self.message.embeds else discord.Embed()
            embed.set_footer(text="This confirmation expired. Run the command again to continue.")
            await self.message.edit(embed=embed, view=None)
        except discord.HTTPException:
            logger.debug('Could not remove controls from an expired view.', exc_info=True)

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
    async def reject_other_clicker(button_interaction: discord.Interaction) -> bool:
        if button_interaction.user.id == interaction.user.id:
            return False
        await button_interaction.response.send_message(
            "Only the moderator who started this review can use these controls.",
            ephemeral=True,
        )
        return True

    async def approve_callback(button_interaction: discord.Interaction):
        if await reject_other_clicker(button_interaction):
            return
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
                description=f"❌ Failed to approve {user_display}. Please try again or contact a moderator.",
                color=discord.Color.red()
            )
            await button_interaction.response.edit_message(embed=error_embed, view=None)
    
    async def deny_callback(button_interaction: discord.Interaction):
        if await reject_other_clicker(button_interaction):
            return
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
                description=f"❌ Failed to deny {user_display}. Please try again or contact a moderator.",
                color=discord.Color.red()
            )
            await button_interaction.response.edit_message(embed=error_embed, view=None)
    
    async def skip_callback(button_interaction: discord.Interaction):
        if await reject_other_clicker(button_interaction):
            return
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
        if await reject_other_clicker(button_interaction):
            return
        cancel_embed = discord.Embed(
            title="Process Cancelled",
            description=f"Pending user management cancelled. Remaining users are still pending.",
            color=discord.Color.orange()
        )
        await button_interaction.response.edit_message(embed=cancel_embed, view=None)
    
    # Set callbacks
    approve_button.callback = approve_callback  # type: ignore[assignment]
    deny_button.callback = deny_callback  # type: ignore[assignment]
    skip_button.callback = skip_callback  # type: ignore[assignment]
    cancel_button.callback = cancel_callback  # type: ignore[assignment]
    
    # Send or edit the message
    if current_index == 0:
        await interaction.edit_original_response(embed=embed, view=view)
    else:
        await interaction.edit_original_response(embed=embed, view=view)

bot = commands.Bot(command_prefix="$", intents=intents)
logger.info(f'Connecting with DB: {DB_NAME}')
fe = Frontend(database_name=DB_NAME, owner_user_id=OWNER_ID, source='discord') # Frontend
ac.init_autocomplete(fe)  # Inject the shared Frontend instance into autocomplete module

# Prevent overlapping update_all runs if a cycle takes longer than the loop interval.
_game_update_lock = asyncio.Lock()

@tasks.loop(minutes=1)
async def scheduled_game_update():
    """Refresh prices (Alpaca) and game portfolios without blocking Discord commands."""
    if _game_update_lock.locked():
        logger.debug('Skipping scheduled update; previous cycle still running.')
        return
    async with _game_update_lock:
        try:
            # Blocking HTTP + SQLite work stays off the event loop.
            await asyncio.to_thread(fe.gl.update_all)
        except Exception:
            logger.exception('Scheduled game update failed.')

@scheduled_game_update.before_loop
async def wait_for_scheduled_update():
    await bot.wait_until_ready()

# Event: Called when the bot is ready and connected to Discord
@bot.event
async def on_ready():
    """Prints a message to the console when the bot is online and syncs slash commands."""
    attach_critical_dm_bot(bot)
    await flush_critical_dm_queue()
    if bot.user is None:
        logger.error('Ready event fired without an authenticated bot user.')
        return
    logger.info(f'Logged in as {bot.user.name} (ID: {bot.user.id})')
    if not scheduled_game_update.is_running():
        scheduled_game_update.start()
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
    start_date="Game start date (YYYY-MM-DD). Does not by itself stop buying.",
    end_date="End date (YYYY-MM-DD)",
    pick_date="Last day players can buy stocks (YYYY-MM-DD). Leave empty = buy anytime.",
    starting_money="Starting money amount",
    total_picks="Number of stocks each player can pick",
    exclusive_picks="Draft mode: each stock can only be picked by one player (requires a deadline on or before the start date)",
    private_game="Whether the game is private (requires owner approval for new users)",
    sell_during_game="Whether players may sell owned stocks during the game",
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
    sell_during_game: bool = False,
):
    # Create game using frontend and return
    try:
        game_id = fe.new_game(
            user_id=interaction.user.id,
            name=name,
            start_date=start_date,
            end_date=end_date,
            starting_money=starting_money,
            total_picks=total_picks,
            exclusive_picks=exclusive_picks,
            private_game= private_game,
            pick_date=pick_date,
            update_frequency='alpaca',
            sell_during_game=sell_during_game,
        )
        
        pick_note = (
            f"Pick deadline: `{pick_date}`"
            if pick_date
            else "Pick deadline: none — players can buy anytime"
        )
        embed = discord.Embed(
            title="Game Created Successfully",
            description=f"Game '{name}' has been created. Game ID: #{game_id}\n{pick_note}",
            color=discord.Color.green()
        )
    except (InvalidDateFormatError, ValueError, TypeError) as exc:
        embed = discord.Embed(
            title="Game Creation Failed",
            description=str(exc),
            color=discord.Color.red(),
        )
    except Exception as exc:
        logger.exception("Advanced game creation failed", exc_info=exc)
        embed = simple_embed(
            status='failed',
            title='Game Creation Failed',
            desc='Unable to create the game. Please check the supplied values and try again.',
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
    game_creation_button_view = InitiatorOnlyView(interaction.user.id, timeout=120)
    game_creation_button_view.add_item(game_creation_wizard_start)
    
    # Send the initial message with the embed and button
    await interaction.response.send_message(embed=embed, view=game_creation_button_view, ephemeral=ephemeral_test)
    game_creation_button_view.message = await interaction.original_response()
    
    # Define what happens when the button is clicked
    async def game_creation_wizard_start_callback(interaction: discord.Interaction):
        original_user = interaction.user.id
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
            label="Start Date (when the game becomes active)",
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

        async def initial_wizard_timeout():
            try:
                await interaction.edit_original_response(
                    embed=simple_embed(
                        status='failed',
                        title='Game Creation Timed Out',
                        desc='The form was not submitted in time. Run /create-game to start again.',
                    ),
                    view=None,
                )
            except discord.HTTPException:
                logger.debug('Could not mark game creation modal as timed out.', exc_info=True)

        initial_wizard_modal.on_timeout = initial_wizard_timeout
        
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
                if interaction.user.id != original_user:
                    await interaction.response.send_message(
                        "Only the person who started this wizard can make selections.",
                        ephemeral=True,
                    )
                    return
                # Check which button was clicked
                if interaction_custom_id(interaction) == "exclusive_picks_yes":
                    game_exclusive_picks = True
                else:
                    game_exclusive_picks = False

                pick_date_modal = discord.ui.Modal(title="Buy / Pick Deadline", timeout=60)

                pick_date_input = discord.ui.TextInput(
                    label=(
                        "Pick deadline (required for exclusive picks)"
                        if game_exclusive_picks
                        else "Pick deadline (blank = buy anytime)"
                    ),
                    placeholder="YYYY-MM-DD — leave blank to allow buying anytime",
                    required=game_exclusive_picks,
                    max_length=10,
                    min_length=10 if game_exclusive_picks else 0,
                    style=discord.TextStyle.short
                )

                pick_date_modal.add_item(pick_date_input)
                
                await interaction.response.send_modal(pick_date_modal)
                
                async def pick_date_callback(interaction: discord.Interaction):
                    if interaction.user.id != original_user:
                        await interaction.response.send_message(
                            "Only the person who started this wizard can make selections.",
                            ephemeral=True,
                        )
                        return

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
                    async def private_game_callback(button_interaction: discord.Interaction):
                        if button_interaction.user.id != original_user:
                            await button_interaction.response.send_message(
                                "Only the person who started this wizard can make selections.",
                                ephemeral=True,
                            )
                            return

                        private_game = interaction_custom_id(button_interaction) == "private_yes"
                        sell_embed = discord.Embed(
                            title="Allow selling during the game?",
                            description="If enabled, players can sell owned stocks. Otherwise, owned picks are permanent.",
                            color=discord.Color.blue(),
                        )
                        sell_yes = discord.ui.Button(label="Allow selling", style=discord.ButtonStyle.success, custom_id="sell_yes")
                        sell_no = discord.ui.Button(label="Keep picks permanent", style=discord.ButtonStyle.secondary, custom_id="sell_no")
                        sell_view = discord.ui.View(timeout=120)
                        sell_view.add_item(sell_yes)
                        sell_view.add_item(sell_no)
                        await button_interaction.response.edit_message(embed=sell_embed, view=sell_view)

                        async def sell_callback(sell_interaction: discord.Interaction):
                            if sell_interaction.user.id != original_user:
                                await sell_interaction.response.send_message(
                                    "Only the person who started this wizard can make selections.",
                                    ephemeral=True,
                                )
                                return

                            try:
                                game_starting_money = int(float(starting_money_input.value.replace(',', ''))) if starting_money_input.value else 10000
                                game_total_picks = int(total_picks_input.value.replace(',', '')) if total_picks_input.value else 10
                                if game_starting_money < 1 or game_total_picks < 1:
                                    raise ValueError
                            except ValueError:
                                await sell_interaction.response.edit_message(
                                    embed=simple_embed(
                                        status='failed',
                                        title='Invalid Game Settings',
                                        desc='Starting money and total picks must be whole numbers greater than zero. Run /create-game to try again.',
                                    ),
                                    view=None,
                                )
                                return

                            sell_during_game = interaction_custom_id(sell_interaction) == "sell_yes"
                            game_name = name_input.value
                            game_start_date = start_date_input.value
                            game_end_date = end_date_input.value or None
                            game_pick_date = pick_date_input.value or None
                            pick_deadline_text = game_pick_date or "None — players can buy anytime"
                            confirmation_embed = discord.Embed(
                                title="Game Creation Confirmation",
                                description=(
                                    f"**Name:** {game_name}\n"
                                    f"**Start date:** {game_start_date}\n"
                                    f"**End date:** {game_end_date or 'None'}\n"
                                    f"**Starting money:** ${game_starting_money:,}\n"
                                    f"**Total picks:** {game_total_picks}\n"
                                    f"**Exclusive picks:** {'Yes' if game_exclusive_picks else 'No'}\n"
                                    f"**Private game:** {'Yes' if private_game else 'No'}\n"
                                    f"**Selling enabled:** {'Yes' if sell_during_game else 'No'}\n"
                                    f"**Pick deadline:** {pick_deadline_text}"
                                ),
                                color=discord.Color.blue(),
                            )
                            confirmation_embed.set_footer(text="Confirm to create the game, or cancel to discard these settings.")
                            confirmation_view = discord.ui.View(timeout=120)
                            confirm_button = discord.ui.Button(label="Confirm", style=discord.ButtonStyle.success)
                            cancel_button = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.danger)
                            confirmation_view.add_item(confirm_button)
                            confirmation_view.add_item(cancel_button)

                            async def confirm_callback(confirm_interaction: discord.Interaction):
                                if confirm_interaction.user.id != original_user:
                                    await confirm_interaction.response.send_message(
                                        "Only the person who started this wizard can confirm it.",
                                        ephemeral=True,
                                    )
                                    return
                                try:
                                    game_id = fe.new_game(
                                        user_id=confirm_interaction.user.id,
                                        name=game_name,
                                        start_date=game_start_date,
                                        end_date=game_end_date,
                                        pick_date=game_pick_date,
                                        starting_money=game_starting_money,
                                        total_picks=game_total_picks,
                                        exclusive_picks=game_exclusive_picks,
                                        private_game=private_game,
                                        update_frequency='alpaca',
                                        sell_during_game=sell_during_game,
                                    )
                                    creation_status_embed = simple_embed(
                                        status='success',
                                        title='Game Created Successfully',
                                        desc=f"Game '{game_name}' has been created. Game ID: #{game_id}",
                                    )
                                except (InvalidDateFormatError, ValueError, TypeError) as exc:
                                    creation_status_embed = simple_embed(
                                        status='failed',
                                        title='Game Creation Failed',
                                        desc=str(exc),
                                    )
                                except Exception as exc:
                                    logger.exception('Guided game creation failed', exc_info=exc)
                                    creation_status_embed = simple_embed(
                                        status='failed',
                                        title='Game Creation Failed',
                                        desc='Unable to create the game. Please check the settings and try again.',
                                    )
                                await confirm_interaction.response.edit_message(embed=creation_status_embed, view=None)

                            async def cancel_callback(cancel_interaction: discord.Interaction):
                                if cancel_interaction.user.id != original_user:
                                    await cancel_interaction.response.send_message(
                                        "Only the person who started this wizard can cancel it.",
                                        ephemeral=True,
                                    )
                                    return
                                await cancel_interaction.response.edit_message(
                                    embed=simple_embed(status='success', title='Game Creation Cancelled', desc='No game was created.'),
                                    view=None,
                                )

                            confirm_button.callback = confirm_callback  # type: ignore[assignment]
                            cancel_button.callback = cancel_callback  # type: ignore[assignment]
                            await sell_interaction.response.edit_message(embed=confirmation_embed, view=confirmation_view)

                        sell_yes.callback = sell_callback  # type: ignore[assignment]
                        sell_no.callback = sell_callback  # type: ignore[assignment]

                    private_yes.callback = private_game_callback  # type: ignore[assignment]
                    private_no.callback = private_game_callback  # type: ignore[assignment]

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
    start_date="First game start date (YYYY-MM-DD). Later games repeat monthly from this day",
    recurring_period="Months between recurring games (optional, default: 1)",
    game_length="How many months each game lasts. 0 = infinite. Cannot exceed recurring period",
    create_days_in_advance="How many days before each game's start to create it (optional, default: 7)",
    starting_money="Starting money for players (optional, default: 10000)",
    pick_date="Buy deadline in days before each game start. Negative = after start. Empty = anytime",
    private_game="Make the game private (optional, default: False)",
    total_picks="Maximum number of picks per player (optional, default: 10)",
    exclusive_picks="Enable exclusive picks: each stock can only be picked once (optional, default: False)",
    sell_during_game="Allow selling owned stocks during the game (optional, default: False)",
    # update_frequency="How often to update game data ('daily', 'hourly') (optional, default: daily)"
)
async def create_recurring_game(
    interaction: discord.Interaction,
    name: app_commands.Range[str, 1, name_cutoff],
    start_date: str,
    recurring_period: app_commands.Range[int, 1, 12] = 1,
    game_length: app_commands.Range[int, 0, 12] = 1,
    create_days_in_advance: app_commands.Range[int, 0, 30] = 7,
    starting_money: app_commands.Range[int, 1, 1000000000000] = 10000,
    pick_date: int | None = None,
    private_game: bool = False,
    total_picks: app_commands.Range[int, 1, 1000] = 10,
    exclusive_picks: bool = False,
    sell_during_game: bool = False,
    # update_frequency: Literal['daily', 'hourly'] = "daily"
):
        """Create a recurring game template"""

        await interaction.response.defer(ephemeral=ephemeral_test)

        if not is_moderator(interaction):
            await interaction.followup.send("You do not have permission to create recurring games.", ephemeral=True)
            return


        try:
            if exclusive_picks and pick_date is None:
                await interaction.followup.send(
                    "❌ Exclusive picks requires a pick deadline on or before each game start. "
                    "Press the **↑ up arrow** to edit your previous command.",
                    ephemeral=ephemeral_test,
                )
                return
            if exclusive_picks and pick_date is not None and pick_date < 0:
                await interaction.followup.send(
                    "❌ Exclusive picks cannot use a pick deadline after the game start. "
                    "Press the **↑ up arrow** to edit your previous command.",
                    ephemeral=ephemeral_test,
                )
                return
            if pick_date is not None and (pick_date < -30 or pick_date > 30):
                await interaction.followup.send(
                    "❌ Pick date must be between -30 and 30 days relative to each game's start date. "
                    "Press the **↑ up arrow** to edit your previous command.",
                    ephemeral=ephemeral_test,
                )
                return
            if game_length > 0 and game_length > recurring_period:
                await interaction.followup.send(
                    "❌ Game length cannot be longer than the recurring period "
                    "(that would overlap active games). "
                    "Press the **↑ up arrow** to edit your previous command.",
                    ephemeral=ephemeral_test,
                )
                return

            user_id = interaction.user.id
            fe.register(user_id=user_id, username=interaction.user.display_name)

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
            )

            embed = discord.Embed(
                title="✅ Recurring Game Template Created!",
                description=f"Successfully created recurring game template: **{name}**",
                color=discord.Color.green(),
                timestamp=datetime.now()
            )

            embed.add_field(name="📅 Start Date", value=start_date, inline=True)
            embed.add_field(name="🔄 Recurring Every", value=f"{recurring_period} months", inline=True)
            embed.add_field(name="⏱️ Game Length", value=(f"{game_length} months" if game_length != 0 else "infinite"), inline=True)
            embed.add_field(name="💰 Starting Money", value=f"${starting_money:,.2f}", inline=True)
            embed.add_field(name="📊 Total Picks", value=str(total_picks), inline=True)
            embed.add_field(name="🔒 Private", value="Yes" if private_game else "No", inline=True)

            if pick_date is not None:
                if pick_date > 0:
                    pick_date_text = f"{pick_date} days before each game start"
                elif pick_date < 0:
                    pick_date_text = f"{abs(pick_date)} days after each game start"
                else:
                    pick_date_text = "On each game start date"
                embed.add_field(name="📝 Pick Deadline", value=pick_date_text, inline=True)
            else:
                embed.add_field(name="📝 Pick Deadline", value="None — buy anytime", inline=True)

            embed.add_field(name="🎯 Exclusive Picks", value="Yes" if exclusive_picks else "No", inline=True)
            embed.add_field(name="💸 Selling Allowed", value="Yes" if sell_during_game else "No", inline=True)
            # embed.add_field(name="🔄 Update Frequency", value=update_frequency.title(), inline=True)
            embed.add_field(name="🏷️ Updates", value="alpaca", inline=True)
            embed.add_field(name="⏰ Create in Advance", value=f"{create_days_in_advance} days", inline=True)

            embed.set_footer(text=f"Created by {interaction.user.display_name}")

            await interaction.followup.send(embed=embed, ephemeral=ephemeral_test)

        except AlreadyExistsError:
            await interaction.followup.send(
                f"❌ A recurring template named **{name}** already exists. "
                "Choose a different name — press the **↑ up arrow** to bring back your previous command and edit it.",
                ephemeral=ephemeral_test,
            )
        except InvalidDateFormatError:
            await interaction.followup.send(
                "❌ Invalid start date. Use `YYYY-MM-DD` (example: `2026-08-01`). "
                "Press the **↑ up arrow** to edit your previous command.",
                ephemeral=ephemeral_test,
            )
        except ValueError as e:
            await interaction.followup.send(
                f"❌ {e} Press the **↑ up arrow** to edit your previous command.",
                ephemeral=ephemeral_test,
            )
        except Exception as e:
            logger.exception(f'User {interaction.user.id} failed to create recurring template', exc_info=e)
            error_message = "❌ Failed to create recurring game template. Please try again or contact a moderator."
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

        game_name = fe._get_game_name(game_id)
        title = "Game Joined Successfully"
        description = f"You have joined **{game_name}** (#{game_id})."
        status = 'success'
        # Private games create a pending participant until the owner approves it.
        try:
            participants = fe.be.get_many_participants(user_id=interaction.user.id, game_id=game_id)
            if participants and participants[0].status == 'pending':
                title = "Join Request Submitted"
                description = f"Your request to join **{game_name}** (#{game_id}) is pending. The owner must approve it before you can play."
        except LookupError:
            logger.warning('Could not verify join status for user %s in game %s.', interaction.user.id, game_id)
    except LookupError:
        description = f'No game with the ID {game_id}.'
        
    except ValueError as e:
        if 'already in game.' in str(e).lower():
            description = f'You are already in this game ID {game_id}.'
            
        elif '`pick_date` has passed.' in str(e).lower():
            description = f'The pick date for this game has passed.'
        else:
            description = 'Unable to join this game. Please check its settings and try again.'
            
    except Exception as e:
        logger.exception(f'User: {interaction.user.id} failed to join game {game_id}.  Error: {e}')
        description = f'An unexpected error ocurred when joining game {game_id}. Please try again or contact a moderator.'

    if status == 'failed':
        title = "Game Join Failed"

    await interaction.response.send_message(embed=simple_embed(status = status, title = title, desc = description), ephemeral=ephemeral_test)

@bot.tree.command(name="delete-game", description="Delete a game (Owner/Admin) - with confirmation")
@app_commands.autocomplete(game_id=ac.owner_games_autocomplete)
@app_commands.describe(
    game_id="The game ID to delete"
)
async def delete_game(
    interaction: discord.Interaction,
    game_id: str,
):
    try:
        game_info = fe.game_info(game_id, False)
    except LookupError:
        await interaction.response.send_message(
            embed=simple_embed(status='failed', title='Game Not Found', desc=f'No game exists with ID #{game_id}.'),
            ephemeral=ephemeral_test,
        )
        return

    game = game_info.game
    if interaction.user.id != game.owner_id and not is_moderator(interaction):
        await interaction.response.send_message(
            embed=simple_embed(status='failed', title='Not Allowed', desc='Only the game owner or a moderator can delete this game.'),
            ephemeral=ephemeral_test,
        )
        return

    confirm_view = InitiatorOnlyView(interaction.user.id, timeout=30)
    confirm_btn = discord.ui.Button(label="Yes, delete it", style=discord.ButtonStyle.danger, emoji="⚠️")
    cancel_btn = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.secondary)

    confirm_embed = discord.Embed(
        title="Confirm Deletion",
        description=f"Are you sure you want to delete game **{game.name}** (#{game_id})?\nThis action cannot be undone.",
        color=discord.Color.orange()
    )

    async def do_delete(btn_interaction: discord.Interaction):
        try:
            if is_moderator(btn_interaction):
                fe.remove_game(user_id=interaction.user.id, game_id=game_id, enforce_permissions=False)
            else:
                fe.remove_game(user_id=interaction.user.id, game_id=game_id)
            await btn_interaction.response.edit_message(
                embed=simple_embed(status='success', title='Deleted', desc=f'Game #{game_id} has been deleted.'),
                view=None
            )
        except PermissionError:
            await btn_interaction.response.edit_message(
                embed=simple_embed(status='failed', title='Failed', desc='You do not have permission to delete this game.'),
                view=None
            )
        except Exception as exc:
            logger.exception(f'Failed to delete game {game_id}', exc_info=exc)
            await btn_interaction.response.edit_message(
                embed=simple_embed(status='failed', title='Failed', desc='An error occurred while deleting the game.'),
                view=None
            )

    async def cancel_delete(btn_interaction: discord.Interaction):
        await btn_interaction.response.edit_message(
            embed=simple_embed(status='success', title='Cancelled', desc='Deletion cancelled.'),
            view=None
        )

    confirm_btn.callback = do_delete  # type: ignore[assignment]
    cancel_btn.callback = cancel_delete  # type: ignore[assignment]
    confirm_view.add_item(confirm_btn)
    confirm_view.add_item(cancel_btn)
    await interaction.response.send_message(embed=confirm_embed, view=confirm_view, ephemeral=ephemeral_test)
    confirm_view.message = await interaction.original_response()

@bot.tree.command(name="manage-game", description="Manage an existing stock game")
@app_commands.autocomplete(game_id=ac.owner_games_autocomplete)
@app_commands.describe(
    game_id="ID of the game to update",
    name="New name of the game",
    owner="New game owner",
    start_date="New start date (YYYY-MM-DD). Cannot be changed once game has started",
    end_date="New end date (YYYY-MM-DD)",
    clear_end_date="Remove the end date",
    pick_date="New pick deadline (YYYY-MM-DD). Cannot be changed once game has started",
    clear_pick_date="Remove the pick deadline before the game starts",
    private_game="Whether the game is private or not",
    starting_money="New starting money amount. Cannot be changed once game has started",
    total_picks="New number of stocks each player can pick. Cannot be changed once game has started",
    exclusive_picks="Only allow each stock to be picked by one player. Requires a deadline on or before the start date",
    sell_during_game="Whether users can sell stocks during the game. Cannot be changed once game has started",
    # update_frequency="How often prices should update ('daily', 'hourly')", #, 'minute', 'realtime')"
)
async def manage_game(
    interaction: discord.Interaction, 
    game_id: str,
    name: app_commands.Range[str, 1, name_cutoff] | None = None,
    owner: discord.User | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    clear_end_date: bool = False,
    starting_money: app_commands.Range[int, 1, 1000000000000] | None = None,
    total_picks: app_commands.Range[int, 1, 1000] | None = None,
    pick_date: str | None = None,
    clear_pick_date: bool = False,
    private_game: bool | None = None,
    exclusive_picks: bool | None = None,
    sell_during_game: bool | None = None,
    # update_frequency: Literal['daily', 'hourly'] | None = None
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
        if end_date and clear_end_date:
            raise ValueError('Choose either a new end date or remove the existing one, not both.')
        if pick_date and clear_pick_date:
            raise ValueError('Choose either a new pick deadline or remove the existing one, not both.')
        if owner is not None:
            fe.register(owner.id, username=owner.display_name)

        fe.manage_game(
            user_id=interaction.user.id,
            game_id=game_id,
            name=name,
            owner=owner.id if owner else None,
            start_date=start_date,
            end_date=end_date,
            starting_money=starting_money,
            pick_date=pick_date,
            private_game=private_game,
            total_picks=total_picks,
            exclusive_picks=exclusive_picks,
            # update_frequency=update_frequency,
            sell_during_game=sell_during_game,
            clear_end_date=clear_end_date,
            clear_pick_date=clear_pick_date,
        )

        embed = discord.Embed(
            title="Game Updated Successfully",
            description=f"Game #{game_id} has been updated!",
            color=discord.Color.green()
        )
        
    except ValueError as e: # Should catch issues
        embed = discord.Embed(
            title="Game Update Failed",
            description=str(e),
            color=discord.Color.red()
        )
    except Exception as e:
        logger.exception("Game update failed", exc_info=e)
        embed = discord.Embed(
            title="Game Update Failed",
            description="Unable to update the game. Please try again or contact a moderator.",
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

    try:
        invited_game = fe.be.get_game(game_id)
    except LookupError:
        await interaction.followup.send(
            embed=simple_embed(status='failed', title='Game Not Found', desc=f'No game exists with ID #{game_id}.'),
            ephemeral=ephemeral_test,
        )
        return

    invite_embed = discord.Embed(
        title="Game Invite",
        description=f"You have been invited to **{invited_game.name}** (#{game_id}) by {interaction.user.display_name}.",
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

    async def accept_invite_callback(button_interaction: discord.Interaction):
        # Validate that the clicker is the invited user
        if button_interaction.user.id != user.id:
            await button_interaction.response.send_message(
                "This invite was not meant for you.", ephemeral=True
            )
            return

        try:
            fe.join_game(
                user_id=user.id,
                game_id=game_id,
                name=user.display_name,
            )
            participant = fe.be.get_many_participants(user_id=user.id, game_id=game_id)[0]
            if participant.status == 'pending':
                title = 'Join Request Submitted'
                description = 'Your request is pending owner approval before you can play.'
            else:
                title = 'Game Joined'
                description = f'You joined **{invited_game.name}** (#{game_id}).'
            accept_embed = discord.Embed(
                title=title,
                description=description,
                color=discord.Color.green(),
            )
        except ValueError as exc:
            message = str(exc)
            if 'already in game' in message.lower():
                message = 'You are already participating in this game.'
            elif 'pick_date' in message.lower():
                message = 'The pick deadline for this game has passed.'
            accept_embed = simple_embed(status='failed', title='Game Join Failed', desc=message)
        except LookupError:
            accept_embed = simple_embed(status='failed', title='Game Join Failed', desc='This game is no longer available.')
        except Exception as exc:
            logger.exception('Invite acceptance failed for user %s and game %s.', user.id, game_id, exc_info=exc)
            accept_embed = discord.Embed(
                title="Game Join Failed",
                description='Unable to join the game. Please try again or contact a moderator.',
                color=discord.Color.red(),
            )

        await button_interaction.response.edit_message(embed=accept_embed, view=None)

    async def decline_invite_callback(interaction: discord.Interaction):
        if interaction.user.id != user.id:
            await interaction.response.send_message("This invite was not meant for you.", ephemeral=True)
            return
        decline_embed = discord.Embed(
            title="Invite Declined",
            description=f"You have declined the invite to game #{game_id}.",
            color=discord.Color.red()
        )
        await interaction.response.edit_message(embed=decline_embed, view=None)

    accept_button.callback = accept_invite_callback  # type: ignore[assignment]
    decline_button.callback = decline_invite_callback

    try:
        await user.send(embed=invite_embed, view=view)
        await interaction.followup.send(
            embed=discord.Embed(
                title='Invite Sent',
                description=f'Invite sent to {user.mention}.',
                color=discord.Color.blue(),
            ),
            ephemeral=ephemeral_test,
        )
    except discord.Forbidden:
        if invited_game.private_game:
            description = f"{user.mention} has DMs disabled. Private-game details were not posted publicly; ask them to enable DMs or send them the game ID privately."
            await interaction.followup.send(
                embed=simple_embed(status='failed', title='Invite Not Delivered', desc=description),
                ephemeral=ephemeral_test,
            )
            return
        if interaction.channel is None:
            await interaction.followup.send(
                embed=simple_embed(status='failed', title='Invite Not Delivered', desc=f"{user.mention} has DMs disabled and no channel is available for a public invite."),
                ephemeral=ephemeral_test,
            )
            return
        try:
            channel = cast(discord.abc.Messageable, interaction.channel)
            await channel.send(
                f"{user.mention}, {interaction.user.display_name} invited you to **{invited_game.name}** (#{game_id}). Use `/join-game {game_id}` to join."
            )
        except (discord.Forbidden, discord.HTTPException):
            await interaction.followup.send(
                embed=simple_embed(status='failed', title='Invite Not Delivered', desc=f"{user.mention} has DMs disabled and I could not post an in-channel invite."),
                ephemeral=ephemeral_test,
            )
        else:
            await interaction.followup.send(
                embed=discord.Embed(
                    title='Invite Posted in Channel',
                    description=f'{user.mention} has DMs disabled, so the public-game invite was posted here.',
                    color=discord.Color.blue(),
                ),
                ephemeral=ephemeral_test,
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
            description=f"An unexpected error occurred while getting pending users. Please try again or contact a moderator.",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed, ephemeral=ephemeral_test)
  
class RecurringTemplateManager(discord.ui.View):
    """Paginate through recurring templates one at a time with stop/delete."""

    def __init__(self, interaction: discord.Interaction, templates: list):
        super().__init__(timeout=180)
        self.interaction = interaction
        self.templates = list(templates)
        self.index = 0
        self.confirming_delete = False
        self._sync_buttons()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.interaction.user.id:
            return True
        await interaction.response.send_message(
            "Only the moderator who ran this command can use these controls.",
            ephemeral=True,
        )
        return False

    def _sync_buttons(self) -> None:
        self.clear_items()
        if self.confirming_delete:
            confirm = discord.ui.Button(label="Confirm Delete", style=discord.ButtonStyle.danger)
            cancel = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.secondary)
            confirm.callback = self._confirm_delete  # type: ignore[method-assign]
            cancel.callback = self._cancel_delete  # type: ignore[method-assign]
            self.add_item(confirm)
            self.add_item(cancel)
            return

        prev_btn = discord.ui.Button(emoji="◀️", style=discord.ButtonStyle.blurple, disabled=self.index <= 0)
        next_btn = discord.ui.Button(
            emoji="▶️",
            style=discord.ButtonStyle.blurple,
            disabled=self.index >= len(self.templates) - 1,
        )
        delete_btn = discord.ui.Button(label="Delete", style=discord.ButtonStyle.danger)

        stopped = bool(self.templates and self.templates[self.index].status == "disabled")
        if stopped:
            toggle_btn = discord.ui.Button(label="Resume", style=discord.ButtonStyle.success)
            toggle_btn.callback = self._resume  # type: ignore[method-assign]
        else:
            toggle_btn = discord.ui.Button(label="Stop", style=discord.ButtonStyle.secondary)
            toggle_btn.callback = self._stop  # type: ignore[method-assign]

        prev_btn.callback = self._previous  # type: ignore[method-assign]
        next_btn.callback = self._next  # type: ignore[method-assign]
        delete_btn.callback = self._ask_delete  # type: ignore[method-assign]
        self.add_item(prev_btn)
        self.add_item(next_btn)
        self.add_item(toggle_btn)
        self.add_item(delete_btn)

    def _pick_deadline_text(self, template) -> str:
        if template.pick_date is None:
            return "None — buy anytime"
        if template.pick_date > 0:
            return f"{template.pick_date} days before each game start"
        if template.pick_date < 0:
            return f"{abs(template.pick_date)} days after each game start"
        return "On each game start date"

    def build_embed(self) -> discord.Embed:
        if not self.templates:
            return discord.Embed(
                title="Manage Recurring Games",
                description="No recurring templates left.",
                color=discord.Color.orange(),
            )

        template = self.templates[self.index]
        status_label = "Enabled" if template.status == "enabled" else "Stopped"
        length = "Infinite" if template.game_length == 0 else f"{template.game_length} months"
        embed = discord.Embed(
            title=f"📋 {template.name}",
            description=(
                f"Template **{self.index + 1}** of **{len(self.templates)}**\n"
                f"**Status:** {status_label}\n\n"
                "**Stop** — do not create future games; games already created keep running until they end.\n"
                "**Resume** — start creating future games again on the normal schedule.\n"
                "**Delete** — remove this template from the database (existing games stay)."
            ),
            color=discord.Color.blue() if template.status == "enabled" else discord.Color.dark_grey(),
        )
        embed.add_field(name="🔄 Recurring Every", value=f"{template.recurring_period} months", inline=True)
        embed.add_field(name="📅 First Start", value=str(template.start_date), inline=True)
        embed.add_field(name="⏱️ Game Length", value=length, inline=True)
        embed.add_field(name="⏰ Create Early", value=f"{template.create_days_in_advance} days", inline=True)
        embed.add_field(name="💰 Starting", value=f"${template.start_money:,.0f}", inline=True)
        embed.add_field(name="📊 Picks", value=str(template.pick_count), inline=True)
        embed.add_field(name="📝 Pick Deadline", value=self._pick_deadline_text(template), inline=True)
        embed.add_field(name="🔒 Private", value="Yes" if template.private_game else "No", inline=True)
        embed.add_field(name="🎯 Exclusive", value="Yes" if template.draft_mode else "No", inline=True)
        embed.set_footer(text=f"Template ID: {template.id}")
        return embed

    def build_delete_confirm_embed(self) -> discord.Embed:
        template = self.templates[self.index]
        return discord.Embed(
            title="Delete template?",
            description=(
                f"Permanently delete recurring template **{template.name}**?\n\n"
                "Existing games created from it will keep running, but no new games will be created.\n"
                "Confirm or Cancel — either way you will move to the next template."
            ),
            color=discord.Color.red(),
        )

    async def _refresh(self, interaction: discord.Interaction) -> None:
        self.confirming_delete = False
        self._sync_buttons()
        if not self.templates:
            await interaction.response.edit_message(embed=self.build_embed(), view=None)
            self.stop()
            return
        if self.index >= len(self.templates):
            self.index = len(self.templates) - 1
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def _advance_after_delete_prompt(
        self,
        interaction: discord.Interaction,
        *,
        deleted: bool,
    ) -> None:
        self.confirming_delete = False
        if deleted:
            # Index now points at what used to be the next template.
            if self.index >= len(self.templates):
                self.index = max(0, len(self.templates) - 1)
        # A cancellation advances when possible so moderators can quickly
        # review the next template without reopening the command.
        elif self.index < len(self.templates) - 1:
            self.index += 1
        self._sync_buttons()
        if not self.templates:
            await interaction.response.edit_message(embed=self.build_embed(), view=None)
            self.stop()
            return
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def _previous(self, interaction: discord.Interaction) -> None:
        self.index = max(0, self.index - 1)
        await self._refresh(interaction)

    async def _next(self, interaction: discord.Interaction) -> None:
        self.index = min(len(self.templates) - 1, self.index + 1)
        await self._refresh(interaction)

    async def _stop(self, interaction: discord.Interaction) -> None:
        template = self.templates[self.index]
        try:
            fe.be.update_game_template(template_id=template.id, status="disabled")
            self.templates[self.index] = fe.be.get_game_template(template.id)
            self.confirming_delete = False
            self._sync_buttons()
            await interaction.response.edit_message(embed=self.build_embed(), view=self)
            await interaction.followup.send(
                f"🛑 **{template.name}** stopped. No new games will be created; "
                "games already in progress will finish normally.",
                ephemeral=True,
            )
        except Exception as exc:
            logger.exception(
                "manage-recurring-games stop failed | user=%s template_id=%s",
                interaction.user.id,
                template.id,
                exc_info=exc,
            )
            if interaction.response.is_done():
                await interaction.followup.send(
                    "❌ Failed to stop this template. Please try again or contact a moderator.",
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    "❌ Failed to stop this template. Please try again or contact a moderator.",
                    ephemeral=True,
                )

    async def _resume(self, interaction: discord.Interaction) -> None:
        template = self.templates[self.index]
        try:
            fe.be.update_game_template(template_id=template.id, status="enabled")
            self.templates[self.index] = fe.be.get_game_template(template.id)
            self.confirming_delete = False
            self._sync_buttons()
            await interaction.response.edit_message(embed=self.build_embed(), view=self)
            await interaction.followup.send(
                f"▶️ **{template.name}** resumed. New games will be created again on schedule.",
                ephemeral=True,
            )
        except Exception as exc:
            logger.exception(
                "manage-recurring-games resume failed | user=%s template_id=%s",
                interaction.user.id,
                template.id,
                exc_info=exc,
            )
            if interaction.response.is_done():
                await interaction.followup.send(
                    "❌ Failed to resume this template. Please try again or contact a moderator.",
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    "❌ Failed to resume this template. Please try again or contact a moderator.",
                    ephemeral=True,
                )

    async def _ask_delete(self, interaction: discord.Interaction) -> None:
        self.confirming_delete = True
        self._sync_buttons()
        await interaction.response.edit_message(embed=self.build_delete_confirm_embed(), view=self)

    async def _confirm_delete(self, interaction: discord.Interaction) -> None:
        template = self.templates[self.index]
        try:
            fe.be.remove_game_template(template_id=template.id)
            del self.templates[self.index]
            await self._advance_after_delete_prompt(interaction, deleted=True)
            await interaction.followup.send(f"🗑️ Deleted template **{template.name}**.", ephemeral=True)
        except Exception as exc:
            logger.exception(
                "manage-recurring-games delete failed | user=%s template_id=%s",
                interaction.user.id,
                template.id,
                exc_info=exc,
            )
            self.confirming_delete = False
            self._sync_buttons()
            await interaction.response.edit_message(embed=self.build_embed(), view=self)
            await interaction.followup.send(
                "❌ Failed to delete this template. Please try again or contact a moderator.",
                ephemeral=True,
            )

    async def _cancel_delete(self, interaction: discord.Interaction) -> None:
        await self._advance_after_delete_prompt(interaction, deleted=False)

    async def on_timeout(self) -> None:
        try:
            message = await self.interaction.original_response()
            await message.edit(view=None)
        except discord.HTTPException:
            logger.debug('Could not remove controls from an expired recurring-template view.', exc_info=True)


@bot.tree.command(name="leave-game", description="Leave a game you are participating in")
@app_commands.autocomplete(game_id=ac.all_games_autocomplete)
@app_commands.describe(
    game_id="ID of the game to leave"
)
async def leave_game(
    interaction: discord.Interaction,
    game_id: str,
):
    await interaction.response.defer(ephemeral=ephemeral_test)
    try:
        await asyncio.to_thread(fe.leave_game, interaction.user.id, game_id)
        await interaction.followup.send(
            embed=simple_embed(
                status='success',
                title='Left Game',
                desc=f'You have left game #{game_id}. Your associated picks were removed.',
            ),
            ephemeral=ephemeral_test,
        )
    except PermissionError:
        await interaction.followup.send(
            embed=simple_embed(
                status='failed',
                title='Cannot Leave Game',
                desc='Game owners must transfer ownership or delete the game instead.',
            ),
            ephemeral=ephemeral_test,
        )
    except DoesntExistError:
        await interaction.followup.send(
            embed=simple_embed(status='failed', title='Not in Game', desc=f'You are not participating in game #{game_id}.'),
            ephemeral=ephemeral_test,
        )
    except LookupError:
        await interaction.followup.send(
            embed=simple_embed(status='failed', title='Not in Game', desc=f"You are not in game #{game_id}."),
            ephemeral=ephemeral_test,
        )
    except Exception as e:
        logger.exception(f'User {interaction.user.id} failed to leave game {game_id}', exc_info=e)
        await interaction.followup.send(
            embed=simple_embed(status='failed', title='Error', desc='An unexpected error occurred while leaving the game.'),
            ephemeral=ephemeral_test,
        )

@bot.tree.command(name="manage-recurring-games", description="Browse, stop, or delete recurring game templates (Moderator Only)")
async def manage_recurring_games(interaction: discord.Interaction):
    """Paginate through your recurring templates with stop/delete controls."""
    if not is_moderator(interaction):
        await interaction.response.send_message(
            "You do not have permission to manage recurring games.",
            ephemeral=True,
        )
        return

    try:
        try:
            templates = fe.be.get_many_game_templates(status=None)
        except LookupError:
            templates = ()
        user_templates = [t for t in templates if t.owner_id == interaction.user.id]
        if not user_templates:
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="Manage Recurring Games",
                    description="You haven't created any recurring game templates yet.",
                    color=discord.Color.orange(),
                ),
                ephemeral=ephemeral_test,
            )
            return

        view = RecurringTemplateManager(interaction, user_templates)
        await interaction.response.send_message(
            embed=view.build_embed(),
            view=view,
            ephemeral=ephemeral_test,
        )
    except Exception as e:
        logger.exception(
            "manage-recurring-games failed | user=%s",
            interaction.user.id,
            exc_info=e,
        )
        await interaction.response.send_message(
            "❌ Unable to load recurring templates. Please try again or contact a moderator.",
            ephemeral=ephemeral_test,
        )


@bot.tree.command(name="update", description="Force-update all stock prices and game portfolios (Moderator Only)")
@app_commands.describe(
    # A future command option may expose targeted updates; the backend supports it.
)
async def update(
    interaction: discord.Interaction, 
    # game_id: str,
):
    await interaction.response.defer(ephemeral=ephemeral_test) # Defer the response to allow time for the update
    embed = discord.Embed()
    if not is_moderator(interaction):
        embed.title = "Failed"
        embed.description = "You do not have permission to update games"
        embed.color = discord.Color.red()
        await interaction.followup.send(embed=embed, ephemeral=ephemeral_test)
        return
    try:
        async with _game_update_lock:
            await asyncio.to_thread(
                fe.force_update,
                user_id=interaction.user.id,
                enforce_permissions=False,
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
        embed.description = f"There was an error while executing this command. Please try again or contact a moderator."
        embed.color = discord.Color.red()

    await interaction.followup.send(embed=embed, ephemeral=ephemeral_test)


# STOCK RELATED

@bot.tree.command(name="buy-stock", description="Buy a stock in a game")
@app_commands.autocomplete(game_id=ac.all_games_autocomplete, ticker=ac.buy_ticker_autocomplete)
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
        await asyncio.to_thread(
            fe.buy_stock,
            user_id=interaction.user.id,
            game_id=game_id,
            ticker=ticker,
        )
        remaining, total = fe.pick_capacity(interaction.user.id, game_id)
        title = 'Stock Purchased'
        description = f'Added {ticker} to game #{game_id}. {remaining} of {total} picks remaining.'
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
            description = 'An error ocurred while finding your stock.'
    
    except LookupError:
        description = f'No game with ID {game_id} found.'
    
    except NotAllowedError as exc: # REASONS ARE NOW IN THE DOCSTRING OF buy_stock!!
        if exc.reason == 'Not active':
            try:
                participant = fe.be.get_many_participants(user_id=interaction.user.id, game_id=game_id)[0]
                if participant.status == 'pending':
                    description = 'Your request to join this private game is still awaiting owner approval.'
                else:
                    description = f'You are not currently allowed to buy stocks in game #{game_id}.'
            except (LookupError, IndexError):
                description = f'You are not currently allowed to buy stocks in game #{game_id}.'
        
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
        description='An unexpected error occurred while trying to buy the stock. Please try again or contact a moderator.'
            
    await interaction.followup.send(
        embed=simple_embed( # This just creates the status message
            status = status,
            title = title,
            desc = description
            ), 
        ephemeral=ephemeral_test
        )


@bot.tree.command(name="sell-stock", description="Sell an owned stock or cancel a pending buy")
@app_commands.autocomplete(game_id=ac.all_games_autocomplete, ticker=ac.sell_ticker_autocomplete)
@app_commands.describe(game_id="ID of the game", ticker="Stock ticker symbol")
async def sell_stock(interaction: discord.Interaction, game_id: str, ticker: str):
    await interaction.response.defer(ephemeral=ephemeral_test)
    ticker = ticker.upper().strip()
    try:
        result = await asyncio.to_thread(
            fe.sell_stock,
            user_id=interaction.user.id,
            game_id=game_id,
            ticker=ticker,
        )
        if result == 'cancelled':
            title = 'Purchase Cancelled'
            description = f'Cancelled your pending purchase of {ticker} in game #{game_id}.'
        elif result == 'sell_requested':
            title = 'Sale Requested'
            description = f'Sale of {ticker} was requested. It will complete on the next portfolio update.'
        else:
            title = 'Sale Already Requested'
            description = f'A sale of {ticker} is already waiting for the next portfolio update.'
        embed = simple_embed(status='success', title=title, desc=description)
    except NotAllowedError as exc:
        description = 'Selling is not enabled for this game.' if exc.reason == 'Selling disabled' else 'You are not allowed to sell this stock.'
        embed = simple_embed(status='failed', title='Stock Sale Failed', desc=description)
    except DoesntExistError:
        embed = simple_embed(status='failed', title='Not in Game', desc=f'You are not participating in game #{game_id}.')
    except LookupError:
        embed = simple_embed(status='failed', title='Stock Sale Failed', desc=f'You do not have a matching {ticker} pick in game #{game_id}.')
    except ValueError as exc:
        embed = simple_embed(status='failed', title='Stock Sale Failed', desc=str(exc) or 'The sale could not be processed.')
    except Exception as exc:
        logger.exception('Stock sale failed for user %s in game %s.', interaction.user.id, game_id, exc_info=exc)
        embed = simple_embed(status='failed', title='Stock Sale Failed', desc='Unable to process the sale. Please try again or contact a moderator.')
    await interaction.followup.send(embed=embed, ephemeral=ephemeral_test)


@bot.tree.command(name="remove-stock", description="Cancel a pending stock purchase")
@app_commands.autocomplete(game_id=ac.all_games_autocomplete, ticker=ac.sell_ticker_autocomplete)
@app_commands.describe(game_id="ID of the game", ticker="Pending stock ticker to cancel")
async def remove_stock(interaction: discord.Interaction, game_id: str, ticker: str):
    await interaction.response.defer(ephemeral=ephemeral_test)
    ticker = ticker.upper().strip()
    try:
        await asyncio.to_thread(
            fe.remove_pick,
            user_id=interaction.user.id,
            game_id=game_id,
            ticker=ticker,
        )
        remaining, total = fe.pick_capacity(interaction.user.id, game_id)
        embed = simple_embed(
            status='success',
            title='Pending Purchase Cancelled',
            desc=f'Cancelled {ticker} in game #{game_id}. {remaining} of {total} picks remaining.',
        )
    except DoesntExistError:
        embed = simple_embed(status='failed', title='Not in Game', desc=f'You are not participating in game #{game_id}.')
    except LookupError:
        embed = simple_embed(status='failed', title='No Pending Purchase', desc=f'No pending purchase of {ticker} was found in game #{game_id}.')
    except ValueError as exc:
        embed = simple_embed(
            status='failed',
            title='Cannot Cancel Purchase',
            desc=f'{exc} Use /sell-stock only when selling is enabled for an owned stock.',
        )
    except Exception as exc:
        logger.exception('Pending-purchase cancellation failed for user %s in game %s.', interaction.user.id, game_id, exc_info=exc)
        embed = simple_embed(status='failed', title='Purchase Cancellation Failed', desc='Unable to cancel that pending purchase. Please try again.')
    await interaction.followup.send(embed=embed, ephemeral=ephemeral_test)

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
            content=(
                f'{fe.pick_capacity(user_id, game_id)[0]} of {info.game.pick_count} picks remaining '
                f'(${float(info.game.start_money) / int(info.game.pick_count):,.2f} allocated per pick).'
            ),
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
        try:
            remaining, total = fe.pick_capacity(user_id, game_id)
            game = fe.game_info(game_id, show_leaderboard=False).game
            embed = discord.Embed(
                title='No Stocks Yet',
                description=(
                    f'You have not bought any stocks in game #{game_id}. '
                    f'Use `/buy-stock` to make your first pick.\n'
                    f'**Picks remaining:** {remaining} of {total}\n'
                    f'**Allocated per pick:** ${float(game.start_money) / total:,.2f}'
                ),
                color=discord.Color.blue(),
            )
        except (DoesntExistError, LookupError):
            embed = simple_embed(status='failed', title='Not in Game', desc=f'You are not participating in game #{game_id}.')
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
        game_info_obj = fe.game_info(game_id, show_leaderboard=show_leaderboard)
        game = game_info_obj.game
        leaderboard = game_info_obj.leaderboard or []
        
        # Basic embed for game info
        description_str = '> **Owner:** <@{owner_id}>{pick_info}\n{start_cash}\n{pick_count}\n{updates}\n{date_range}\n{participants}'.format(
            owner_id=game.owner_id,
            pick_info=(
                f'\n> **Pick date:** {game.pick_date}'
                if game.pick_date
                else '\n> **Pick date:** none — buy anytime'
            ),
            start_cash=f'> **Starting Cash:** ${int(game.start_money)}',
            pick_count=f'> **Pick Count:** `{game.pick_count}`',
            updates=f'> **Updates:** `{game.update_frequency}`',
            date_range='> ' + str('Started' if game.status != 'open' else 'Starting') + f' `{game.start_date}`' + str(str(', ends' if game.status != 'ended' else ', ended') + f' `{game.end_date}`') if game.end_date else '',
            participants=f'> **Participants:** `{len(leaderboard)}`' if show_leaderboard else '> **Participants:** hidden',
        )
        
        embed = discord.Embed(
            title=f'{game.name} ({game.id})',
            description=description_str
        )
        embed.set_footer(text="Dates are formatted as (YYYY-MM-DD)")
        
        if not show_leaderboard:
            await interaction.followup.send(embed=embed, ephemeral=ephemeral_test)
            return
        
        # Limit leaderboard to top 10
        # lb_limit = 10
        leaderboard_info: list[GameLeaderboard] = leaderboard
        
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
                member = await interaction.guild.fetch_member(info.user_id) if interaction.guild else None
                if member is None:
                    raise LookupError('Member unavailable outside a guild')
                if len(member.display_name) <= 16:
                    display_name = member.display_name
                elif len(member.global_name or "") <= 16:
                    display_name = member.global_name
                elif len(member.name) <= 16:
                    display_name = member.name
                else:
                    display_name = (member.global_name or member.name)[:15] + "~"
                player_data['display_name'] = display_name
            except (discord.HTTPException, LookupError):
                try:
                    db_user = fe.be.get_user(info.user_id)
                    if db_user.display_name:
                        player_data['display_name'] = db_user.display_name[:16]
                    else:
                        player_data['display_name'] = f'ID({info.user_id})'
                except LookupError:
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
                if interaction.guild is None:
                    raise LookupError('Command used outside a guild')
                owner_member = await interaction.guild.fetch_member(game.owner_id)
                game_data['owner_name'] = owner_member.display_name or owner_member.global_name or owner_member.name
            except (discord.HTTPException, LookupError):
                try:
                    db_owner = fe.be.get_user(game.owner_id)
                    if db_owner.display_name:
                        game_data['owner_name'] = db_owner.display_name[:16]
                    else:
                        game_data['owner_name'] = f'ID({game.owner_id})'
                except LookupError:
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
            logger.warning(f"Image generation failed, falling back to text: {e}")
            
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
            await interaction.followup.send(embed=embed, ephemeral=ephemeral_test)
            
    except Exception as e:
        # Handle case where game doesn't exist
        embed = discord.Embed(
            title='Failed to get info',
            description=f'Game with ID {game_id} does not exist or an error occurred.',
            color=0xff0000
        )
        await interaction.followup.send(embed=embed, ephemeral=ephemeral_test)

# TODO add buttons for joining games?
# TODO add a joinable parameter?
# TODO max page length cant be more than 25
@bot.tree.command(name="game-list", description="View a list of all games") # TODO rename to list-games, all-games, or games-list?
@app_commands.describe(
    page_length="The length of the list per page. Defaults to 9"
)
async def game_list(
    interaction: discord.Interaction,
    page_length: app_commands.Range[int, 1, 25] = 9 # 9 looks nicer than 10
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
                '> **Owner:** <@{owner_id}>{pick_info}\n{start_cash}\n{updates}\n{date_range}'.format(owner_id=game.owner_id,
                pick_info=(
                    f'\n> **Pick date:** {game.pick_date}'
                    if game.pick_date
                    else '\n> **Pick date:** none — buy anytime'
                ),
                start_cash=f'> **Starting Cash:** ${int(game.start_money)}',
                updates=f'> **Updates:** `{game.update_frequency}`',
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
            participant_status = 'active'
            try:
                participant_status = fe.be.get_participant(fe._participant_id(user_id=interaction.user.id, game_id=game.id)).status
            except (DoesntExistError, LookupError):
                logger.warning('Could not resolve participation status for user %s in game %s.', interaction.user.id, game.id)
            if participant_status == 'pending':
                status_emoji = '🟡'
                status_text = 'approval pending'
            elif game.status == 'ended':
                status_emoji = '🔴'
                status_text = 'ended'
            else:
                status_emoji = '🟢'
                status_text = game.status

            game_description += f"{status_emoji} **{game.name[:name_cutoff]}** — #{game.id} ({status_text})\n"

        embed.description = game_description
        embed.set_footer(text=f"Use /game-info <game_id> for more details")

    except LookupError:
        embed.description = "You are not currently in any games."
        embed.color = discord.Color.orange()
    except Exception as e:
        logger.exception(f'User: {interaction.user.id} tried to get their games. Error: {e}')
        embed.description = "Unable to retrieve your games. Please try again."
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

@bot.tree.command(name="change-name", description="Change your display name used in leaderboards and game info")
@app_commands.describe(
    name="Your new display name"
)
async def change_name(
    interaction: discord.Interaction,
    name: app_commands.Range[str, 1, 32],
):
    try:
        fe.change_name(user_id=interaction.user.id, name=name)
        await interaction.response.send_message(
            embed=simple_embed(status='success', title='Name Changed', desc=f'Your display name is now: {name}'),
            ephemeral=ephemeral_test,
        )
    except Exception as e:
        logger.exception(f'User {interaction.user.id} failed to change name', exc_info=e)
        await interaction.response.send_message(
            embed=simple_embed(status='failed', title='Failed', desc='Could not change your display name.'),
            ephemeral=ephemeral_test,
        )

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
  kind: Literal['debug', 'error'] = 'debug',
):
    
    if is_moderator(interaction): # Check if user is an admin
        title = "Logs"
        status = 'success'
        path = latest_log_path(kind)
        if path is None or not os.path.isfile(path):
            await interaction.response.send_message(
                embed=simple_embed(status='failed', title='No Logs', desc=f'No {kind} log file found yet.'),
                ephemeral=True,
            )
            return
        # Discord attachment limit ~25MB; truncate from end if needed for safety
        max_bytes = 8 * 1024 * 1024
        size = os.path.getsize(path)
        if size > max_bytes:
            with open(path, 'rb') as f:
                f.seek(size - max_bytes)
                data = f.read()
            logfile = discord.File(fp=io.BytesIO(data), filename=f'log-{kind}-latest.log')
        else:
            logfile = discord.File(fp=path, filename=f'log-{kind}-latest.log')
        await interaction.response.send_message(
            embed=simple_embed(status=status, title=title, desc=f'Sending latest {kind} log.'),
            file=logfile,
            ephemeral=ephemeral_test,
        )

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

## How to Play
1. **Find a game** using `/game-list` or **create your own** with `/create-game`
2. **Join a game** using `/join-game`
3. **Buy stocks** using `/buy-stock`
4. **Watch the leaderboard** and see how your picks perform!

### Game Management
- `/create-game` - Guided setup for stock game creation
- `/create-game-advanced` - Create a new stock game without a wizard
- `/manage-game` - Manage an existing stock game
- `/delete-game` - For owners and admins to delete games (with confirmation)
- `/invite` - Invite a user to a game
- `/manage-pending` - Approve or deny pending users for your private game
- `/leave-game` - Leave a game you've joined

### Playing Games
- `/join-game` - Join an existing stock game
- `/buy-stock` - Buy a stock in a game
- `/sell-stock` - Sell an owned stock or cancel a pending buy
- `/remove-stock` - Cancel a pending stock purchase (not yet owned)
- `/my-stocks` - View your stocks in a game as a visual portfolio
- `/change-name` - Change your display name

### Information & Stats
- `/game-info` - View information about a game
- `/game-list` - View a list of all public games
- `/my-games` - View your games and their status
- `/user-stats` - Shows global statistics of a user. Shows yours by default
- `/about` - About the bot and its creators
"""
    if is_moderator(interaction):
        help_text += """
### Moderator Commands
- `/create-recurring-game` - Create a recurring game template (Moderator only)
- `/manage-recurring-games` - Browse, stop, or delete recurring templates (Moderator only)
- `/update` - Force-update stock prices and game portfolios (Moderator only)
- `/logs` - For admins to get logs (Moderator only)

## Need Help?
Use `/help` to see this message again, or contact a moderator if you encounter any issues!"""
    await interaction.response.send_message(embed=simple_embed(status='success', title=title, desc=help_text), ephemeral=ephemeral_test)

# Run the bot using the token
if __name__ == '__main__':
    if TOKEN:
        try:
            attach_critical_dm_bot(bot)
            bot.run(TOKEN, log_handler=None)
        except discord.errors.LoginFailure:
            logger.critical(
                "Discord login failed: invalid DISCORD_TOKEN. Check .env / secrets.",
                exc_info=True,
            )
        except discord.errors.PrivilegedIntentsRequired:
            logger.critical(
                "Discord privileged intents required. Enable Message Content / Members "
                "in the Discord Developer Portal.",
                exc_info=True,
            )
        except Exception as e:
            logger.critical("Bot crashed while starting/running: %s", e, exc_info=True)
    else:
        logger.critical("DISCORD_TOKEN environment variable not found. Bot cannot start.")
