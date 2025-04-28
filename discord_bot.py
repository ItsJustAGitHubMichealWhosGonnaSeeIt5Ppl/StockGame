# DISCORD Bot
# SOME AI USED
#TODO add autocompletion 

from stocks import Backend, Frontend
import sys
import os
import logging
import discord
from discord.ext import commands

TOKEN = os.getenv('DISCORD_TOKEN')

intents = discord.Intents(messages=True, message_content=True) # Set intent

bot = commands.Bot(command_prefix="$", intents=intents) # Set up 

fe = Frontend() # Frontend


# CTX data that might be relevant when a user runs a command
## ctx.author = (Message.Author object)
## ctx.author.nick = Users nickname in the server(?)
## ctx.author.name = Users Discord name
## ctx.author.id = User ID

# Event: Called when the bot is ready and connected to Discord
@bot.event #TODO who needs this
async def on_ready():
    """Prints a message to the console when the bot is online."""
    print(f'Logged in as {bot.user.name} (ID: {bot.user.id})')
    print('------')
    # Optional: Set bot's presence (e.g., "Playing $help")
    # await bot.change_presence(activity=discord.Game(name="$help"))

# ping #TODO remove this once the bot is ready
@bot.command(name='ping', help='Responds with Pong! and the bot latency.')
async def ping(ctx):
    """Simple command to check if the bot is responsive."""
    latency = bot.latency * 1000 # Convert latency to milliseconds
    
    

    await ctx.reply(f'Pong! Latency: {latency:.2f}ms', ephemeral=True ) # ephemeral=True does not work # Reply replies to the user who sent it, which is a good start.

# echo #TODO remove this once bot is ready
@bot.command(name='echo', help='Repeats the message provided by the user.')
async def echo(ctx, *, message: str):
    """Takes a string as input and sends it back."""
    # `*` makes it take all following text as one argument
    # `message: str` type hints that the argument should be a string
    await ctx.send(f"{message} Author:[{ctx.author}] ")


# END AI SLOP
# GAME RELATED
@bot.command(name='list-games', help='List games.')
async def echo(ctx): #TODO create autocompletes
    games = fe.list_games()
    await ctx.reply(games)

@bot.command(name='my-games', help='Show your games.')
async def echo(ctx, ended:bool=True): #TODO create (ended will toggle whether to show ended games or not)

    await ctx.send(str(ended))
    
@bot.command(name='game-info', help='Get information about a single game')
async def echo(ctx, game_id:int):
    game = fe.game_info(int(game_id)) #TODO ERROR HANDLING
    embed = discord.Embed(title=game['name'])
    embed.add_field(name='Status', value=game['status'], inline=False)
    embed.add_field(name='Start Date', value=game['start_date'], inline=True)
    embed.add_field(name='End Date', value=game['end_date'], inline=True)
    await ctx.reply(embed=embed)



# MORE AI SLOP
# Command: template_command (with arguments)
@bot.command(name='template', help='Example command that accepts arguments.')
async def template_command(ctx, arg1: str, arg2: int, *optional_args):
    """
    A template command to demonstrate argument handling.

    Args:
        ctx: The command context.
        arg1 (str): A required string argument.
        arg2 (int): A required integer argument.
        *optional_args: Any additional arguments passed to the command.
                         These will be captured as a tuple.
    """
    # Send a message confirming the received arguments
    response = f"Received template command!\n"
    response += f"Required argument 1 (string): {arg1}\n"
    response += f"Required argument 2 (integer): {arg2}\n"

    # Check if any optional arguments were provided
    if optional_args:
        response += f"Optional arguments: {', '.join(optional_args)}"
    else:
        response += "No optional arguments provided."

    # --- Your Custom Logic Here ---
    # Add the specific actions you want this command to perform.
    # For example, you could use the arguments to query a database,
    # perform a calculation, interact with an API, etc.
    #
    # Example: Check if arg2 is positive
    if arg2 > 0:
        response += f"\nArgument 2 ({arg2}) is positive!"
    else:
        response += f"\nArgument 2 ({arg2}) is not positive."
    # --- End Custom Logic ---

    await ctx.send(response)


# Error Handling for the template command (optional but recommended)
@template_command.error
async def template_command_error(ctx, error):
    """Handles errors specifically for the template_command."""
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"Missing required argument: `{error.param.name}`. Use `$help template` for usage.")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("Invalid argument type provided. Please check argument types (e.g., the second argument must be a number). Use `$help template` for usage.")
    else:
        # Handle other potential errors or re-raise if needed
        print(f"An error occurred in template_command: {error}")
        await ctx.send("An unexpected error occurred while running the command.")



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
