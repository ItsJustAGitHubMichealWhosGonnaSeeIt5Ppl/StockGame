# Stock Game

VERY VERY EARLY STOCK PICK GAME CODE

## Overall Concept
- Users will get a certain amount of starting money, and a set amount of stock picks.  The money will then be divided evenly between the picks
- Historical data for each ticker will be stored from close price daily
- Price should be saved to the second decimal
- By default, buys will happen at the end of each day (same as tracking)
- Date format: YYYY-MM-DD
- Track the users total gain (and percent)
- Track the users last 7 days of gain
- Monthly recurring games,
- Winner/top places get a role,
- Overall leaderboard,
- Per user leaderboard

### Additional ideas
- Draft style picks - users cannot pick the same stocks
- Rolling 12 month start to allow more people to join
- Multiple games (leagues) allowed
- If mid-game sells are allowed, use a ticker called "CASH" or something?

## First Time Setup

### Prerequisites
- Python 3.x installed
- pip (Python package installer)
- A Discord bot token (get from [Discord Developer Portal](https://discord.com/developers/applications))

### Installation Steps

1. Clone the repository

2. Install required Python packages:
   ```bash
   pip install -r requirements.txt
   ```
   This will install:
   - discord.py (Discord bot library)
   - python-dotenv (Environment variable management)
   - yfinance (Yahoo Finance API for stock data)

3. Create a `.env` file in the root directory with your Discord bot token and your personal database name (ending in .db):
   ```
   DISCORD_TOKEN="your_discord_bot_token_here"
   DB_NAME="test.db"
   OWNER="testowner123"
   ```

4. Set up the database:
   ```bash
   python sqlite_creator_real.py
   ```

### Discord Bot Setup

1. Create a Discord Application:
   - Go to [Discord Developer Portal](https://discord.com/developers/applications)
   - Click "New Application" and give it a name
   - Go to the "Bot" section in the left sidebar
   - Click "Add Bot"
   - Under "Privileged Gateway Intents", enable:
     - MESSAGE CONTENT INTENT
     - SERVER MEMBERS INTENT
     - PRESENCE INTENT
   - Click "Reset Token" to get your bot token
   - Copy the token and add it to your `.env` file as `DISCORD_TOKEN`

2. Add the bot to your server:
   - In the Developer Portal, go to "OAuth2" → "URL Generator"
   - Under "Scopes", select:
     - `bot`
     - `applications.commands`
   - Under "Bot Permissions", select:
     - `Send Messages`
     - `Read Messages`
     - `View Channels`
     - `Use Slash Commands`
     - `Embed Links`
     - `Attach Files`
     - `Read Message History`
     - `Add Reactions`
   - Copy the generated URL and open it in your browser
   - Select your server and authorize the bot

3. Get your Discord User ID:
   - Enable Developer Mode in Discord (User Settings → Advanced → Developer Mode)
   - Right-click your username and select "Copy ID"
   - Add this ID to your `.env` file as `OWNER`

4. Adding the bot to your server:
   - Make sure you have "Manage Server" permissions in your Discord server
   - Use the OAuth2 URL generated in step 2 to add the bot
   - After adding, the bot should appear in your server's member list
   - The bot will be offline until you start it using `python discord_bot.py`
   - Once started, you should see the bot come online with a green status indicator
   - Try using `/` in any channel to see if the bot's commands appear
   - If commands don't appear, wait a few minutes as Discord can take time to register slash commands
   - You can verify the bot is working by using `/game-list` or `/create-game`

### Running the Bot

1. Run the Discord bot:
   ```bash
   python discord_bot.py
   ```

Before running the bot, ensure:
- Your `.env` file has the correct Discord token
- The database has been set up
- You've invited the bot to your test Discord server with the necessary permissions

## Contributors
- [EpicSadFace](https://github.com/ItsJustAGitHubMichealWhosGonnaSeeIt5Ppl)
- [nje331](https://github.com/nje331)
- [TheDrewtopian](https://github.com/TheDrewtopian)
