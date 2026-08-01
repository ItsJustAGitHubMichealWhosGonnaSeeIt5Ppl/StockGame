# Environment Variables

All runtime config is loaded from a `.env` file in the project root (`python-dotenv`).

Copy `.env.example` to `.env` and fill in real values. Never commit `.env`.

## Required for Discord bot

| Name | Example | Notes |
|------|---------|--------|
| `DISCORD_TOKEN` | `MTIz...` | From the Discord Developer Portal bot page |
| `DB_NAME` | `data/stockgame.db` | SQLite file path. With Docker, keep this under `data/` so the bind mount persists it. Created automatically on first container start, or with `python sqlite_creator_real.py` locally |
| `OWNER` | `329374393715392520` | Numeric Discord snowflake (your user ID). Must parse as an integer |

If any of these are missing, `discord_bot.py` exits at startup.

## Alpaca (needed for prices / buys)

| Name | Example | Notes |
|------|---------|--------|
| `ALPACA_API_KEY` | `PK...` | Alpaca key ID |
| `ALPACA_SECRET_KEY` | `...` | Alpaca secret |

See [Alpaca Setup](Alpaca-Setup).

## Example (Docker)

```env
DISCORD_TOKEN=your_discord_bot_token
DB_NAME=data/stockgame.db
OWNER=123456789012345678
ALPACA_API_KEY=your_alpaca_key
ALPACA_SECRET_KEY=your_alpaca_secret
```

For a local (non-Docker) run you can use `DB_NAME=stockgame.db` in the project root instead.

## Docker

- Prefer `docker compose up -d --build` (see the repo README).
- `.env` is **not** copied into the image; Compose / `docker run --env-file .env` injects it at runtime.
- Mount `./data` → `/app/data` and set `DB_NAME=data/stockgame.db` so the database survives rebuilds.
- Mount `./logs` → `/app/logs` if you want log files on the host.

## Related setup

- [Discord Bot Setup](Discord-Bot-Setup)
- [Alpaca Setup](Alpaca-Setup)
