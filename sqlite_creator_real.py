import logging
import sqlite3
import os 
from pathlib import Path
from helpers.sqlhelper import SqlHelper, _iso8601
from helpers.db_backup import create_db_backup
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("SqliteCreator")
#TODO change datetime_updated to last_updated, and use a unix timestamp
#TODO change aggregate_value to total value for consistency
#TODO check the add a guild field to verify that the server is the same 
#NOTE ISO8601 applies to both (YYYY-MM-DD HH:MM:SS) and (YYYY-MM-DD)! keys should be named according to below
# # (YYYY-MM-DD HH:MM:SS) objects should include 'datetime' in the key name
# # (YYYY-MM-DD) objects should include 'date' in the key name

db_ver = "0.2.0"  # Current schema version


def _read_db_version(db_name: str) -> str | None:
    """Return ``database_info.current_version``, or None if unreadable/missing."""
    path = Path(db_name)
    if not path.is_file() or path.stat().st_size <= 0:
        return None
    conn = sqlite3.connect(path)
    try:
        has_info = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='database_info'"
        ).fetchone()
        if not has_info:
            return None
        row = conn.execute(
            "SELECT current_version FROM database_info LIMIT 1"
        ).fetchone()
        return row[0] if row else None
    except sqlite3.Error:
        return None
    finally:
        conn.close()


def remake_db_on_mismatch(
    db_name: str,
    db_current_ver: str = db_ver,
    *,
    force: bool = False,
) -> str | None:
    """Keep the DB only when versions match; otherwise backup then remake empty schema.

    Returns the remake backup path when a remake ran, else None.

    TODO: Real row-preserving migrations can return here later (formerly ``upgrade_db``).
    """
    path = Path(db_name)
    if not path.is_file() or path.stat().st_size <= 0:
        create(db_name, upgrade=False)
        return None

    current = _read_db_version(db_name)
    if current == db_current_ver and not force:
        return None

    old_label = (current or "unknown").replace("/", "_")
    new_label = db_current_ver.replace("/", "_")
    label = f"{old_label}-to-{new_label}"
    backup = create_db_backup(db_name, kind="remake", label=label)
    logger.warning(
        "DB version mismatch (found=%s, expected=%s); remaking empty schema. Backup: %s",
        current,
        db_current_ver,
        backup,
    )
    path.unlink(missing_ok=True)
    for suffix in ("-wal", "-shm", "-journal"):
        Path(str(path) + suffix).unlink(missing_ok=True)
    create(db_name, upgrade=False)
    return str(backup) if backup else None


def upgrade_db(db_name: str, db_current_ver: str = db_ver, force_upgrade: bool = False):
    """Deprecated alias for remake-on-mismatch (no row copy). Prefer ``remake_db_on_mismatch``."""
    return remake_db_on_mismatch(db_name, db_current_ver, force=force_upgrade)


def create(db_name:str, upgrade:bool=True):
    """Create database schema; on version mismatch, backup then remake empty DB.

    Version: 0.2.0

    Args:
        db_name (str): Database name
        upgrade (bool, optional): When True, remake if ``database_info`` version
            does not match ``db_ver``. Defaults to True.

    # Changelog

    ## [0.2.0] - 2026-08-05
    ### Added
    - ``push_leaderboard``, ``leaderboard_channel_id`` on game_templates
    - ``leaderboard_message_id`` on games
    - ``days_in_first`` on game_participants
    - ``leaderboard_day_snapshots`` table
    ### Changed
    - Version mismatch remakes empty schema (backup first); no row migration

    ## [0.1.1] / [0.1.0] - 2025-06-27
    See git history for older changelog entries.
    """
    db_path = Path(db_name)
    if db_path.parent != Path('.'):
        db_path.parent.mkdir(parents=True, exist_ok=True)

    # Remake-on-mismatch before CREATE IF NOT EXISTS (avoids mixed old/new schemas).
    if upgrade and db_path.is_file() and db_path.stat().st_size > 0:
        current = _read_db_version(db_name)
        if current != db_ver:
            remake_db_on_mismatch(db_name, db_ver)
            return

    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON;") # Enable foreign key constraint enforcement (important for data integrity (According to Gemini))
    
    # Permissions/roles
    # Will allow for discord role permissions instead of what we have now.
    if False:
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_roles (
            role_id INTEGER PRIMARY KEY,  -- Unique ID (EG: Discord role ID)
            role_name TEXT DEFAULT NULL,                -- User display name
            source TEXT NOT NULL,                       -- role source
            datetime_created TEXT NOT NULL,             -- ISO8601 (YYYY-MM-DD HH:MM:SS)
        );""")
    
    # Meta table (store things like the database version)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS database_info (
        database_name TEXT PRIMARY KEY,             -- Database 
        original_version TEXT NOT NULL,             -- Orginal database version
        current_version TEXT NOT NULL,              
        datetime_created TEXT NOT NULL,             -- ISO8601 (YYYY-MM-DD HH:MM:SS)
        last_updated TEXT DEFAULT NULL              -- ISO8601 (YYYY-MM-DD HH:MM:SS)
        );""")

    # Users table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,                -- Unique ID (EG: Discord user ID)
        display_name TEXT,                          -- User display name
        source TEXT NOT NULL,                       -- User source
        overall_wins INT DEFAULT 0,                 -- First place finishes
        change_dollars REAL DEFAULT NULL,           -- Overall gain/loss in dollars
        change_percent REAL DEFAULT NULL,           -- Overall gain/loss percent
        permissions INT NOT NULL DEFAULT 210,       -- Store users permissions
        datetime_created TEXT NOT NULL,             -- ISO8601 (YYYY-MM-DD HH:MM:SS)
        last_updated TEXT DEFAULT NULL              -- ISO8601 (YYYY-MM-DD HH:MM:SS)
        );""")

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_registered_user_ids ON users(user_id);") # All user IDs
    
    
    # TEMPLATES
    cursor.execute("""CREATE TABLE IF NOT EXISTS game_templates (
        template_id INTEGER PRIMARY KEY AUTOINCREMENT,
        template_name TEXT NOT NULL,
        template_description TEXT DEFAULT NULL,
        game_name TEXT NOT NULL UNIQUE,
        game_description TEXT DEFAULT NULL,
        status TEXT NOT NULL DEFAULT 'enabled',               -- Whether to create the game or not
        owner_user_id INTEGER NOT NULL,                       -- User_ID who created the game 
        start_money REAL NOT NULL CHECK(start_money > 0),     -- Set starting money, value is in USD (Ensure positive starting amount)
        pick_count INTEGER NOT NULL CHECK(pick_count > 0),    -- Set amount of stocks each user will pick (Ensure positive number of stocks)
        pick_date INTEGER DEFAULT NULL,                       -- Days before or after start of month that picks must be in by. Negative values for after start of month. If NULL, players can join at anytime
        draft_mode BOOLEAN DEFAULT 0,                         -- When enabled, each stock can only be picked once per game.  Pick date must be on or before start date to allow this
        private_game BOOLEAN DEFAULT 0,                       -- When enabled, players must be approved to join.
        allow_selling BOOLEAN DEFAULT 0,                      -- When enabled, users can sell mid-game
        update_frequency TEXT NOT NULL DEFAULT 'alpaca',      -- Price update tag: 'alpaca', 'daily', 'hourly', 'minute', 'realtime'
        start_date TEXT NOT NULL,                             -- Game start date ISO8601 (YYYY-MM-DD). Everything else will be calculated off of this first creation date
        create_days_in_advance INTEGER NOT NULL DEFAULT 0,    -- How many days before the start should it be created
        recurring_period INTEGER NOT NULL DEFAULT 1,          -- How often should the game be created (in months)
        game_length INTEGER DEFAULT 1,                        -- How many months should the game last. 0 = infinite game
        push_leaderboard INTEGER NOT NULL DEFAULT 0,          -- Auto-push leaderboard image to a channel
        leaderboard_channel_id TEXT DEFAULT NULL,             -- Discord channel snowflake as text
        datetime_created TEXT NOT NULL,                       -- ISO8601 (YYYY-MM-DD HH:MM:SS)
        last_updated TEXT DEFAULT NULL,                       -- ISO8601 (YYYY-MM-DD HH:MM:SS)
        
        FOREIGN KEY (owner_user_id) REFERENCES users (user_id)
        );""")
    
    # Games table 
    cursor.execute("""CREATE TABLE IF NOT EXISTS games (
        game_id TEXT PRIMARY KEY,
        template_id DEFAULT NULL,                             -- Track games created from template
        name TEXT NOT NULL UNIQUE,
        description TEXT DEFAULT NULL,
        owner_user_id INTEGER NOT NULL,                       -- User_ID who created the game 
        start_money REAL NOT NULL CHECK(start_money > 0),     -- Set starting money, value is in USD (Ensure positive starting amount)
        pick_count INTEGER NOT NULL CHECK(pick_count > 0),    -- Set amount of stocks each user will pick (Ensure positive number of stocks)
        pick_date TEXT DEFAULT NULL,                          -- Buy/pick deadline YYYY-MM-DD. If NULL, players can buy anytime
        draft_mode BOOLEAN DEFAULT 0,                         -- When enabled, each stock can only be picked once per game.  Pick date must be on or before start date to allow this
        private_game BOOLEAN DEFAULT 0,                       -- When enabled, players must be approved to join.
        allow_selling BOOLEAN DEFAULT 0,                      -- When enabled, users can sell mid-game
        update_frequency TEXT NOT NULL DEFAULT 'alpaca',      -- Price update tag: 'alpaca', 'daily', 'hourly', 'minute', 'realtime'
        start_date TEXT NOT NULL,                             -- Game start date ISO8601 (YYYY-MM-DD)
        end_date TEXT,                                        -- OPTIONAL Game end date ISO8601 (YYYY-MM-DD)
        status TEXT NOT NULL DEFAULT 'open',                  -- Game status ('open', 'active', 'ended')
        aggregate_value REAL,                                 -- Combined value of all users
        change_dollars REAL DEFAULT NULL,
        change_percent REAL DEFAULT NULL,
        leaderboard_message_id TEXT DEFAULT NULL,             -- Discord message snowflake for push edits
        datetime_created TEXT NOT NULL,                       -- ISO8601 (YYYY-MM-DD HH:MM:SS)
        last_updated TEXT DEFAULT NULL,                       -- ISO8601 (YYYY-MM-DD HH:MM:SS)
        
        FOREIGN KEY (template_id) REFERENCES game_templates (template_id)
        FOREIGN KEY (owner_user_id) REFERENCES users (user_id)
        );""")
    # GAME STATUS OPTIONS
    # - 'open' # Game has not yet started, can be joined
    # - 'active' # Game started, can be joined if join_late is enabled
    # - 'ended' # Game has ended, nothing can be done


    # Stocks table 
    #TODO mark stocks as active/inactive
    cursor.execute("""CREATE TABLE IF NOT EXISTS stocks (
        stock_id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker TEXT NOT NULL,           -- Stock ticker
        exchange TEXT NOT NULL,         -- Stock exchange that it is listed on should alwaws be lowercase
        company_name TEXT,              -- Optional?
        
        UNIQUE (ticker)
        );""")

    # Stock price (current and historical) table
    #TODO add price type (daily, hourly, etc)
    cursor.execute("""CREATE TABLE IF NOT EXISTS stock_prices (
        price_id INTEGER PRIMARY KEY AUTOINCREMENT,
        stock_id INTEGER NOT NULL,
        price REAL NOT NULL,           -- Closing price of stock
        datetime TEXT NOT NULL,      -- ISO8601 (YYYY-MM-DD HH:MM:SS)
        
        FOREIGN KEY (stock_id) REFERENCES stocks (stock_id) ON DELETE CASCADE,  -- When a ticker is deleted from the main table, all references to it will also be deleted?
        
        UNIQUE (stock_id, datetime)                                           -- Ensure only one price per stock per day
        );""")

    # Game participants table (track who is in which leagues/games)
    #TODO name should be nickname
    cursor.execute("""CREATE TABLE IF NOT EXISTS game_participants (
        participation_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        game_id TEXT NOT NULL,
        name TEXT,                              -- Optional 'team' name
        status TEXT DEFAULT 'active',           -- A participant (player) status.  Can be 'pending', 'active', 'inactive'.  Pending will be used if a player tries to join a private game
        datetime_joined TEXT NOT NULL,          -- ISO8601 (YYYY-MM-DD HH:MM:SS)
        current_value REAL DEFAULT NULL,        -- Current portfolio value
        change_dollars REAL DEFAULT NULL,
        change_percent REAL DEFAULT NULL,
        days_in_first INTEGER NOT NULL DEFAULT 0, -- Days ended as #1 (NYSE close snapshots)
        last_updated TEXT DEFAULT NULL,         -- ISO8601 (YYYY-MM-DD HH:MM:SS)
        
        FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE,
        FOREIGN KEY (game_id) REFERENCES games (game_id) ON DELETE CASCADE,
        
        UNIQUE (user_id, game_id) -- A user can only join a specific game once
        );""")

    # Stock picks table.  Store a users stock picks for their game(s).  Buy date not needed since game_participants join date can be used
    cursor.execute("""CREATE TABLE IF NOT EXISTS stock_picks (
        pick_id INTEGER PRIMARY KEY AUTOINCREMENT,
        participation_id INTEGER NOT NULL,                 -- Reference the game 
        stock_id INTEGER NOT NULL,
        shares REAL DEFAULT NULL,                          -- Amount of shares held
        start_value REAL DEFAULT NULL,                     -- Start value of shares
        current_value REAL DEFAULT NULL,                   -- Current value of shares
        change_dollars REAL DEFAULT NULL,
        change_percent REAL DEFAULT NULL,
        status TEXT DEFAULT 'pending_buy',            -- Status of pick. Options: 'pending_buy', 'owned', 'pending_sell', 'sold'
        datetime_created TEXT NOT NULL,                       -- ISO8601 (YYYY-MM-DD HH:MM:SS)
        last_updated TEXT DEFAULT NULL,                    -- ISO8601 (YYYY-MM-DD HH:MM:SS)
        
        FOREIGN KEY (participation_id) REFERENCES game_participants (participation_id) ON DELETE CASCADE,
        FOREIGN KEY (stock_id) REFERENCES stocks (stock_id) ON DELETE RESTRICT, -- Don't delete a stock if picks exist? Or CASCADE? Depends on desired behavior. RESTRICT is safer.
        
        UNIQUE (participation_id, stock_id) -- User picks a specific stock only once per game participation
        );""")

    # Idempotent "days in first" awards per NYSE trade date
    cursor.execute("""CREATE TABLE IF NOT EXISTS leaderboard_day_snapshots (
        game_id TEXT NOT NULL,
        trade_date TEXT NOT NULL,               -- ISO8601 (YYYY-MM-DD) ET trade date
        first_user_id INTEGER NOT NULL,
        datetime_created TEXT NOT NULL,         -- ISO8601 (YYYY-MM-DD HH:MM:SS)
        PRIMARY KEY (game_id, trade_date),
        FOREIGN KEY (game_id) REFERENCES games (game_id) ON DELETE CASCADE,
        FOREIGN KEY (first_user_id) REFERENCES users (user_id)
        );""")

    conn.commit()
    conn.close()

    sql = SqlHelper(db_name)
    info = sql.get(table="database_info")
    if info.status == 'error' and info.reason == "NO ROWS RETURNED":
        sql.insert(
            table='database_info',
            items={
                'database_name': db_name,
                'original_version': db_ver,
                'current_version': db_ver,
                'datetime_created': _iso8601(),
            },
        )


if __name__ == "__main__":
    
    DB_NAME = str(os.getenv('DB_NAME'))
    print(f'DB Name is: {DB_NAME}')
    # upgrade_db(DB_NAME, force_upgrade=True) # Force upgrade to latest version
    create(DB_NAME)
