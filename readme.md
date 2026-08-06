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

You need [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Windows/macOS) or Docker Engine + Compose plugin (Linux).

### 1. Clone and configure

```bash
git clone https://github.com/ItsJustAGitHubMichealWhosGonnaSeeIt5Ppl/StockGame.git
cd StockGame
```

Create a `.env` in the project root. Easiest: copy the example and edit values.

**Linux / macOS / Git Bash**

```bash
cp .env.example .env
```

**Windows PowerShell**

```powershell
Copy-Item .env.example .env
```

Edit `.env` and set at least:

```env
DISCORD_TOKEN=your_discord_bot_token
DB_NAME=data/stockgame.db
OWNER=123456789012345678
ALPACA_API_KEY=your_alpaca_key
ALPACA_SECRET_KEY=your_alpaca_secret
```

Use `DB_NAME=data/stockgame.db` with Docker so the database is stored on the host under `./data` (persists across rebuilds). See [Environment variables](#environment-variables) and the [wiki](https://github.com/ItsJustAGitHubMichealWhosGonnaSeeIt5Ppl/StockGame/wiki).

### 2. Build and run with Compose

**Linux / macOS / Git Bash**

```bash
mkdir -p data logs
docker compose up -d --build
docker compose logs -f
```

**Windows PowerShell**

```powershell
New-Item -ItemType Directory -Force -Path data, logs | Out-Null
docker compose up -d --build
docker compose logs -f
```

The container:

- Creates or migrates `data/stockgame.db` on bot startup if needed
- Writes logs under `./logs` on the host
- Restarts automatically unless you stop it

Useful commands:

```bash
docker compose ps
docker compose logs -f bot
docker compose restart
docker compose down          # stop (keeps ./data)
docker compose up -d --build # rebuild after code changes
```



### 3. Plain `docker` commands (Optional; no Compose)

If you prefer not to use Compose:

**Linux / macOS / Git Bash**

```bash
mkdir -p data logs
docker build -t stockgame .
docker run -d --name stockgame --env-file .env \
  -v "$(pwd)/data:/app/data" \
  -v "$(pwd)/logs:/app/logs" \
  --restart unless-stopped \
  stockgame
```

**Windows PowerShell**

```powershell
New-Item -ItemType Directory -Force -Path data, logs | Out-Null
docker build -t stockgame .
docker run -d --name stockgame --env-file .env `
  -v "${PWD}/data:/app/data" `
  -v "${PWD}/logs:/app/logs" `
  --restart unless-stopped `
  stockgame
```



### Docker notes

- Do **not** bake secrets into the image; `.env` is excluded from the build and passed at runtime.
- After changing code, rebuild: `docker compose up -d --build`.
- If the bot cannot write the database on Linux, ensure `./data` is writable (the entrypoint tries to fix ownership on start).
- Local Python is not required for Docker; the bot creates or migrates the SQLite schema on startup.

### Database version, migrate/remake, and backups

SQLite schema version is tracked in `database_info`. When `discord_bot.py` starts it calls `db_schema.ensure_database()`:

1. **Missing DB** → create current schema  
2. **Matching version** → leave data in place (ensure tables exist)  
3. **Version mismatch with a registered migration** → backup, run migration, stamp new version  
4. **Version mismatch with no migration** → backup under `data/backups/`, then remake an **empty** schema  

Expect to lose live game data on an unmigrated version bump unless you restore from backup.

Automatic backups (also under `data/backups/`):

| Kind | When | Retention |
|------|------|-----------|
| `remake` | Before a migrate or remake on version mismatch | last 10 |
| `daily` | Once per calendar day (on `update_all`) | last 7 |
| `hourly` | Once per clock hour (on `update_all`) | last 24 |

**Restore:** stop the bot → copy a `.db` backup over `DB_NAME` → start the bot.

### Recurring leaderboard push

On `/create-recurring-game`, set `push_leaderboard` and pick a text channel (bot needs View Channel, Send Messages, Embed Links, Attach Files). Manage later with `/manage-recurring-games` (Enable/Disable Push, Set Channel). After each scheduled `/update` cycle, the bot edits the stored leaderboard message in place (or re-sends if that message was deleted).



## Quick start (local Python)

Requires **Python 3.13**.

```bash
git clone https://github.com/ItsJustAGitHubMichealWhosGonnaSeeIt5Ppl/StockGame.git
cd StockGame
pip install -r requirements.txt
cp .env.example .env   # Windows: Copy-Item .env.example .env
# edit .env — for local runs DB_NAME=stockgame.db is fine
python discord_bot.py
```

Contributors should use `pip install -r requirements-dev.txt` instead.

## Environment variables

‼️‼️**For more assistance with** `.env` **keys [visit the wiki.](https://github.com/ItsJustAGitHubMichealWhosGonnaSeeIt5Ppl/StockGame/wiki)**


| Variable            | Required | Purpose                                                                                  |
| ------------------- | -------- | ---------------------------------------------------------------------------------------- |
| `DISCORD_TOKEN`     | Yes      | Discord bot token                                                                        |
| `DB_NAME`           | Yes      | SQLite database path. Use `data/stockgame.db` for Docker; `stockgame.db` is fine locally |
| `OWNER`             | Yes      | Your numeric Discord user ID                                                             |
| `ALPACA_API_KEY`    | Yes*     | Alpaca API key                                                                           |
| `ALPACA_SECRET_KEY` | Yes*     | Alpaca secret key                                                                        |


The bot starts without Alpaca keys, but price updates will not work until they are set.

`.env` example (Docker-friendly):

```env
DISCORD_TOKEN=your_discord_bot_token
DB_NAME=data/stockgame.db
OWNER=123456789012345678
ALPACA_API_KEY=your_alpaca_key
ALPACA_SECRET_KEY=your_alpaca_secret
```



## Discord Integrations (important)

After the bot is invited, **configure command permissions in Discord** so only the right roles and channels can use sensitive commands (`/create-recurring-game`, `/manage-recurring-games`, `/update`, `/logs`, etc.).

Do this in **Server Settings → Integrations → your bot → Command Permissions**. That is the main way to control access. The bot still double-checks Discord **Administrator** (and the configured `OWNER`) if someone can invoke a privileged command.

Step-by-step with screenshots: [Discord Integrations wiki](https://github.com/ItsJustAGitHubMichealWhosGonnaSeeIt5Ppl/StockGame/wiki/Discord-Integrations)

Other setup guides: [Wiki home](https://github.com/ItsJustAGitHubMichealWhosGonnaSeeIt5Ppl/StockGame/wiki)

## Development

```bash
pip install -r requirements-dev.txt
python -m compileall -q discord_bot.py stocks.py db_schema.py helpers scripts tests
python -m pyright
python -m pytest -q
```

