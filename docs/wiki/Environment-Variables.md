# Environment Variables

All runtime config is loaded from a `.env` file in the project root (`python-dotenv`).

## Required for Discord bot

| Name | Example | Notes |
|------|---------|--------|
| `DISCORD_TOKEN` | `MTIz...` | From the Discord Developer Portal bot page |
| `DB_NAME` | `stockgame.db` | SQLite file path. Created/initialized with `python sqlite_creator_real.py` |
| `OWNER` | `329374393715392520` | Numeric Discord snowflake (your user ID). Must parse as an integer |

If any of these are missing, `discord_bot.py` exits at startup.

## Required

| Name | Example | Notes |
|------|---------|--------|
| `ALPACA_API_KEY` | `PK...` | Alpaca key ID |
| `ALPACA_SECRET_KEY` | `...` | Alpaca secret |

See [Alpaca Setup](Alpaca-Setup).

## Example

```env
DISCORD_TOKEN=your_discord_bot_token
DB_NAME=stockgame.db
OWNER=123456789012345678
ALPACA_API_KEY=your_alpaca_key
ALPACA_SECRET_KEY=your_alpaca_secret
```

## Docker

Pass the same file with `--env-file .env`. Make sure `DB_NAME` points at a path that exists **inside** the container (mount a host directory if you want the database to persist).

## Related setup

- [Discord Bot Setup](Discord-Bot-Setup)
- [Alpaca Setup](Alpaca-Setup)
