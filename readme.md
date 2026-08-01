# Stock Game
## Overall Concept
- Users will get a certain amount of starting money, and a set amount of stock picks.  The money will then be divided evenly between the picks
- Historical data for each ticker will be stored from close price daily
- Price should be saved to the second decimal
- By default, buys will happen hourly
- Date format: YYYY-MM-DD
- Track the users total gain (and percent) after game completion
- Track the users last 7 days of gain
- Monthly recurring games
- Winner/top places get a role
- Overall leaderboard
- Per user leaderboard

## First Time Setup

### Prerequisites
- Python 3.13 installed
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
   - pydantic (Data validation)
   - pytz (Timezone support)
   - python-dateutil (Date utilities)
   - Pillow (Image generation / leaderboards)
   - pandas, beautifulsoup4, requests (helpers / seeding scripts)
   - Alpaca market data via HTTP (`helpers/alpaca_client.py`; requires `ALPACA_API_KEY` / `ALPACA_SECRET_KEY`)

   Contributors should install the development dependencies instead:
   ```bash
   pip install -r requirements-dev.txt
   ```

**Before running the bot, ensure:**
- **Your `.env` file has the correct Discord token**
- Your `.env` file includes both `ALPACA_API_KEY` and `ALPACA_SECRET_KEY` Alpaca keys
  - Go to the [Alpaca Setup](#)
- The database has been set up
- You've invited the bot to your test Discord server with the necessary permissions

3. Create a `.env` file in the root directory with your Discord bot token and your personal database name (ending in .db):
   ```
   DISCORD_TOKEN="your_discord_bot_token_here"
   DB_NAME="test.db"
    OWNER="123456789012345678"
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

#### Python (local)

1. Run the Discord bot:
   ```bash
   python discord_bot.py
   ```

#### Docker

1. Build the image:
   ```bash
   docker build -t stockgame .
   ```

2. Run the container (mount your `.env` and database file):
   ```bash
   docker run -d --env-file .env -v $(pwd)/data:/app/data stockgame
   ```
   The bot will look for `DB_NAME` inside `.env`; make sure your database path is relative to `/app` or mounted accordingly.

Run the local quality checks with:
```bash
python -m compileall -q discord_bot.py stocks.py sqlite_creator_real.py helpers scripts tests
python -m pyright
python -m pytest -q
```

## Contributors
- [EpicSadFace](https://github.com/ItsJustAGitHubMichealWhosGonnaSeeIt5Ppl)
- [nje331](https://github.com/nje331)
- [TheDrewtopian](https://github.com/TheDrewtopian)
