# Stock Game

A Discord bot for fantasy stock-picking games inspired by [DougDoug](https://dougdoug.com/stocks). Players get starting cash and a fixed number of picks; cash is split evenly across picks. Prices come from [Alpaca](https://alpaca.markets/) market data. Games can be one-off or recurring.

## Features

- Create and join public or private games
- Buy stocks (optional pick deadline; otherwise buy anytime)
- Per-game leaderboards and portfolio views
- Recurring game templates (moderators)
- Live price updates via Alpaca (stocks only; no crypto)

Dates use `YYYY-MM-DD`. Prices are stored to two decimal places.

## Quick start (Docker — recommended)

1. Clone the repo and create a `.env` in the project root (see [Environment variables](#environment-variables)).
2. Create the SQLite database (once):

   ```bash
   pip install -r requirements.txt   # or use any Python 3.13 env
   python sqlite_creator_real.py
   ```

3. Build and run (persist the DB under `./data`):

   ```bash
   mkdir -p data
   docker build -t stockgame .
   docker run -d --env-file .env -v "$(pwd)/data:/app/data" stockgame
   ```

   Use `DB_NAME=data/stockgame.db` in `.env` so the file lands on the mounted volume.

## Quick start (local Python)

Requires **Python 3.13**.

```bash
git clone https://github.com/ItsJustAGitHubMichealWhosGonnaSeeIt5Ppl/StockGame.git
cd StockGame
pip install -r requirements.txt
# create .env (see below)
python sqlite_creator_real.py
python discord_bot.py
```

Contributors should use `pip install -r requirements-dev.txt` instead.

## Environment variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `DISCORD_TOKEN` | Yes | Discord bot token |
| `DB_NAME` | Yes | SQLite database path (e.g. `stockgame.db`) |
| `OWNER` | Yes | Your numeric Discord user ID |
| `ALPACA_API_KEY` | Yes* | Alpaca API key |
| `ALPACA_SECRET_KEY` | Yes* | Alpaca secret key |

\*The bot starts without Alpaca keys, but price updates will not work until they are set.

`.env` example:

```env
DISCORD_TOKEN=your_discord_bot_token
DB_NAME=stockgame.db
OWNER=123456789012345678
ALPACA_API_KEY=your_alpaca_key
ALPACA_SECRET_KEY=your_alpaca_secret
```

## Setup guides (Wiki)

Long-form setup and troubleshooting live on the [GitHub Wiki](https://github.com/ItsJustAGitHubMichealWhosGonnaSeeIt5Ppl/StockGame/wiki). Drafts you can copy into the wiki are also in [`docs/wiki/`](docs/wiki/):

| Topic | Draft |
|-------|--------|
| Discord app, intents, invite, command sync | [Discord Bot Setup](docs/wiki/Discord-Bot-Setup.md) |
| Who can use commands / which channels | [Discord Integrations](docs/wiki/Discord-Integrations.md) |
| Alpaca keys and price-data troubleshooting | [Alpaca Setup](docs/wiki/Alpaca-Setup.md) |
| Full `.env` notes | [Environment Variables](docs/wiki/Environment-Variables.md) |

## Development

```bash
pip install -r requirements-dev.txt
python -m compileall -q discord_bot.py stocks.py sqlite_creator_real.py helpers scripts tests
python -m pyright
python -m pytest -q
```
