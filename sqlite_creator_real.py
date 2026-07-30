import sqlite3
import os 
from pathlib import Path
import shutil
from helpers.sqlhelper import SqlHelper, _iso8601
from dotenv import load_dotenv

load_dotenv()
#TODO change datetime_updated to last_updated, and use a unix timestamp
#TODO change aggregate_value to total value for consistency
#TODO check the add a guild field to verify that the server is the same 
#NOTE ISO8601 applies to both (YYYY-MM-DD HH:MM:SS) and (YYYY-MM-DD)! keys should be named according to below
# # (YYYY-MM-DD HH:MM:SS) objects should include 'datetime' in the key name
# # (YYYY-MM-DD) objects should include 'date' in the key name

db_ver = "0.1.1" # This is the current DB version.  Using b to indicate a beta, might not use this in producton, idk  
def upgrade_db(db_name:str, db_current_ver:str=db_ver, force_upgrade:bool=False):
    """Rebuild an older schema into the current schema and keep a backup.

    The source database is never moved or deleted until the rebuilt temporary
    database has copied all rows and passed SQLite's foreign-key check.
    """
    target_version = db_current_ver
    source_path = Path(db_name)
    source = sqlite3.connect(source_path)
    source.row_factory = sqlite3.Row
    try:
        has_info = source.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='database_info'"
        ).fetchone()
        info_row = None
        if has_info:
            info_row = source.execute(
                "SELECT original_version, current_version FROM database_info LIMIT 1"
            ).fetchone()
        current_version = info_row['current_version'] if info_row else '0.0.2'
        original_version = info_row['original_version'] if info_row else current_version
        if current_version == target_version and not force_upgrade:
            return None

        temp_path = source_path.with_name(source_path.name + '.upgrade.tmp')
        if temp_path.exists():
            temp_path.unlink()
        create(str(temp_path), upgrade=False)
        destination = sqlite3.connect(temp_path)
        destination.execute('PRAGMA foreign_keys = OFF')
        table_order = (
            'users', 'game_templates', 'games', 'stocks', 'stock_prices',
            'game_participants', 'stock_picks',
        )
        now = _iso8601()
        seen_template_names: set[str] = set()
        for table in table_order:
            exists = source.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone()
            if not exists:
                continue
            destination_columns = {
                row[1] for row in destination.execute(f'PRAGMA table_info("{table}")')
            }
            for source_row in source.execute(f'SELECT * FROM "{table}"'):
                row = dict(source_row)
                if 'datetime_updated' in row and 'last_updated' not in row:
                    row['last_updated'] = row.pop('datetime_updated')
                if table == 'users' and not row.get('source'):
                    row['source'] = 'Unknown'
                if table == 'game_templates':
                    row.setdefault('template_name', row.get('game_name') or 'Recurring game')
                    row.setdefault('game_name', row.get('template_name') or 'Recurring game')
                    base_name = str(row['game_name'])
                    unique_name = base_name
                    suffix = 2
                    while unique_name in seen_template_names:
                        trimmed = base_name[: max(1, 35 - len(f' {suffix}'))]
                        unique_name = f'{trimmed} {suffix}'
                        suffix += 1
                    seen_template_names.add(unique_name)
                    row['game_name'] = unique_name
                    row['template_name'] = unique_name
                if table == 'stock_picks' and not row.get('datetime_created'):
                    row['datetime_created'] = row.get('last_updated') or now
                row.setdefault('datetime_created', now)
                filtered = {key: value for key, value in row.items() if key in destination_columns}
                columns = list(filtered)
                placeholders = ','.join('?' for _ in columns)
                quoted_columns = ','.join(f'"{column}"' for column in columns)
                destination.execute(
                    f'INSERT INTO "{table}" ({quoted_columns}) VALUES ({placeholders})',
                    [filtered[column] for column in columns],
                )

        destination.execute('DELETE FROM database_info')
        destination.execute(
            """INSERT INTO database_info
               (database_name, original_version, current_version, datetime_created, last_updated)
               VALUES (?, ?, ?, ?, ?)""",
            (str(source_path), original_version, target_version, now, now),
        )
        destination.commit()
        destination.execute('PRAGMA foreign_keys = ON')
        violations = destination.execute('PRAGMA foreign_key_check').fetchall()
        if violations:
            raise ValueError(f'Foreign-key violations after database upgrade: {violations}')
        destination.close()
    except Exception:
        if 'destination' in locals():
            destination.close()
        if 'temp_path' in locals() and temp_path.exists():
            temp_path.unlink()
        raise
    finally:
        source.close()

    backup_path = source_path.with_name(source_path.name + '.pre-010.bak')
    counter = 1
    while backup_path.exists():
        backup_path = source_path.with_name(source_path.name + f'.pre-010.{counter}.bak')
        counter += 1
    shutil.copy2(source_path, backup_path)
    os.replace(temp_path, source_path)
    return str(backup_path)


def create(db_name:str, upgrade:bool=True):
    """Create database and upgrade older databases to the current version
    
    Version: 0.1.0

    Args:
        db_name (str): Database name
        upgrade (bool, optional): Whether to try to upgrade older databases to the newest version.  Defaults to True.
    

    # Changelog
    This tries to comply with Semantic versioning with varying success...
    
    ## [0.1.0] - 2025-06-27
    This version requires the database to be recreated. A copy of the original DB will be made.
    
    ### Added
    - `template_name`, `template_description`, `game_description` to game_templates table

    ### Fixed
    - Upgrade tool

    ### Changed
    - `game_id` type from INT to TEXT in games table
    - `datetime_updated` to `last_updated` in games, game participants, and stock_picks table

    ### Removed
    
    ## [0.0.5] - 2025-06-23
    
    ### Added
    - Game templates table

    ### Fixed

    ### Changed
    - Added `template_id` column to games table for tracking recurring games

    ### Removed
    
    ## [0.0.4b3] - 2025-06-10
    
    ### Added
    - `datetime_created` to stock picks

    ### Fixed

    ### Changed

    ### Removed
    
    ## [0.0.4b1] - 2025-06-01
    
    ### Added
    - database information table to make version changes easier
    - `last_updated`, `overall_wins`, `change_dollars`, and `change_percent` to users table
    - Database upgrade/migration system
    
    ### Fixed

    ### Changed

    ### Removed
    
    ## [0.0.3] - 2025-05-22
    
    ### Added
    - `change_dollars` and `change_percent` to tables stock_picks, game_participants, and games
    
    ### Fixed

    ### Changed

    ### Removed
    
    
    ## [0.0.2] - 2025-05-19
    
    ### Added
    - sources column to users table

    ### Fixed

    ### Changed

    ### Removed
    """    
    
    preexisting_tables: set[str] = set()
    if os.path.exists(db_name) and os.path.getsize(db_name) > 0:
        inspection = sqlite3.connect(db_name)
        preexisting_tables = {
            row[0]
            for row in inspection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        inspection.close()

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

    conn.commit()
    conn.close()
    
    
    sql = SqlHelper(db_name)
    info = sql.get(table="database_info")
    if info.status == 'error' and info.reason == "NO ROWS RETURNED": # likely brand new
        initial_version = '0.0.2' if preexisting_tables else db_ver
        sql.insert(table='database_info', items={'database_name': db_name, 'original_version': initial_version, 'current_version': initial_version, 'datetime_created': _iso8601()})
        
    if upgrade: # Run database upgrade
        upgrade_db(db_current_ver=db_ver, db_name=db_name)

        
    
if __name__ == "__main__":
    
    DB_NAME = str(os.getenv('DB_NAME'))
    print(f'DB Name is: {DB_NAME}')
    # upgrade_db(DB_NAME, force_upgrade=True) # Force upgrade to latest version
    create(DB_NAME)
