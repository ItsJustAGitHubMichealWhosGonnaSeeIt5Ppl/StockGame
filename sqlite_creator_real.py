import sqlite3
import os 
from helpers.sqlhelper import SqlHelper, _iso8601
from dotenv import load_dotenv

load_dotenv()
#TODO change datetime_updated to last_updated, and use a unix timestamp
#TODO change aggregate_value to total value for consistency
#TODO check the add a guild field to verify that the server is the same 
#NOTE ISO8601 applies to both (YYYY-MM-DD HH:MM:SS) and (YYYY-MM-DD)! keys should be named according to below
# # (YYYY-MM-DD HH:MM:SS) objects should include 'datetime' in the key name
# # (YYYY-MM-DD) objects should include 'date' in the key name

db_ver = "0.1.0" # This is the current DB version.  Using b to indicate a beta, might not use this in producton, idk  
def upgrade_db(db_name:str, db_current_ver:str=db_ver, force_upgrade:bool=False):
    """Upgrade your database to the latest version

    Args:
        db_current_ver (str): The current database version. Defaults to current version set by script.
        db_name (str): Database name.
        force_upgrade (bool, optional): If True, will try to run all upgrades regardless of what version your database is. Defaults to False.

    ILL DO THESE LATER
    Raises:
        Exception: _description_
        Exception: _description_
        ValueError: _description_
        Exception: _description_
        Exception: _description_
    """
    # Force upgrade will try to run EVERY migration except v001_to_v002 because I don't feel like fixing that one and you can't make me
    current_ver = db_current_ver
    sql = SqlHelper(db_name)
    
    def v001_to_v002(db_name:str, user_source:str): # Help migrate to new DB version without losing data
        """Migrate v0.0.1 DB to v0.0.2
        

        Args:
            db_name (str): Existing database name.
            user_source (str): Default source to set for existing users.
        """
        sql = SqlHelper(db_name)
        
        # Create new column in user table
        query = """ALTER TABLE users
        ADD source TEXT"""
        send = sql.send_query(query)
        if send.status == 'error':
            print(send) # Sometimes gives error but does what its asked anyway...
        pass

    def v002_to_v003(db_name:str,): # OLD SYSTEM #TODO move this
        """Migrate v0.0.2 DB to v0.0.3 (see changelog)

        Args:
            db_name (str): Existing database name.
        """
        sql = SqlHelper(db_name)
        # Create new column in user table
        tables = ['games', 'game_participants', 'stock_picks']
        default_queries = ["ALTER TABLE {table} ADD change_dollars TEXT DEFAULT NULL", "ALTER TABLE {table} ADD change_percent TEXT DEFAULT NULL"]
        game_queries = ["ALTER TABLE {table} ADD datetime_updated TEXT DEFAULT NULL"] # Add this to games
        for table in tables:
            if table == 'games':
                queries = default_queries.copy() + game_queries
            else:
                queries = default_queries
            for query in queries:
                send = sql.send_query(query.format(table=table),mode='insert')
                if send.status == 'error':
                    if send.reason == 'DUPLICATE COLUMN NAME': # The column is already there, not a big deal so keep moving
                        continue
                    else:
                        raise Exception(f'An unknown error occurred while trying to upgrade from v0.0.2 to v0.0.3\n{e}', send) # Sometimes gives error but does what its asked anyway...

    
    try:
        info = sql.get(table='database_info', filters={'database_name': db_name})
    except Exception as e: # TODO find errors
        raise Exception(e)
    
    def make_changes(changes:dict):
        """Simple function to apply changes for a version

        Args:
            changes (dict): Changes.  Format: {'<table>': {'<add/rename>': ['<column>']}}

        """
        
        for table, change_type in changes.items():
            pass
        #TODO IDFK what im doing man :(
        
    
    if info.status == 'success':
        db_ver = info.result[0]['current_version']

    elif info.reason == 'NO ROWS RETURNED' or force_upgrade: # The table exists, but there isn't a row OR force migrate is set
        v002_to_v003(db_name=db_name) # Try to migrate from v 0.0.2 just in case
        sql.insert(table='database_info', items={'database_name': db_name, 'original_version': '0.0.2', 'current_version': '0.0.3', 'datetime_created': _iso8601()})
        db_ver = '0.0.3' if info.reason == 'NO ROWS RETURNED' else db_ver # DB ver should exist unless the database was forcefully migrated
    
    else: # IDFK how we'd even even up here
        raise ValueError(f'Failed to get information for database: {db_name}')
    
    if db_ver == current_ver and not force_upgrade: # No changes needed
        return 
    
    # Consolidated all of the changes to here since itll be easier that way
    if db_ver in ['0.0.3', '0.0.4b1', '0.0.4b2', '0.0.4b3', '0.0.5'] or force_upgrade: # Upgrade to version 0.1.0 (MAJOR CHANGE) 
        os.rename(db_name, f'pre_005_{db_name}') # Rename the current database
        old_db = SqlHelper(f'pre_005_{db_name}') # Attach to old DB
        create(db_name=db_name, upgrade=False) # Recreate
        old_tables = { # This will hold all the old DBs, probably not a great way to do it but fuck it
            'database_info': old_db.get(table='database_info'),
            'users': old_db.get(table='users'),
            'game_templates': old_db.get(table='game_templates'),
            'games': old_db.get(table='games'),
            'stocks': old_db.get(table='stocks'),
            'stock_prices': old_db.get(table='stock_prices'),
            'game_participants': old_db.get(table='game_participants'),
            'stock_picks': old_db.get('stock_picks')
        }
        def revert(): # Revert changes
            os.remove(db_name) # Remove failed db
            os.rename(f'pre_005_{db_name}', db_name) # Revert db
        
        for table, status in old_tables.items():
            if status.status != 'success' and status.reason != 'NO ROWS RETURNED': # Confirm we actually got a response
                revert()
                raise ValueError(f'Failed to retreive {table}. Reason: {status.reason}. reverting changes')
            if status.result == None: # No items skip it
                continue
            assert isinstance(status.result, tuple)
            rows:tuple = status.result
            rows_to_add = list()
            for row in rows:                
                if 'datetime_updated' in row: 
                    row['last_updated'] = row.pop('datetime_updated') # Rename
                    
                if 'datetime_created' in row: # IDK when I did this lol
                    row['datetime_created'] = row.pop('datetime_created') # Rename
                
                if table == 'users' and row['source'] == None: # Some users don't have a source
                    row['source'] = 'Unknown'
                
                if table == 'stock_picks' and 'datetime_created' not in row: # Was added in v0.0.4b3
                    row['datetime_created'] = row['datetime_updated'] if 'datetime_updated' in row else row['last_updated']# This is probably right
                
                ins = sql.insert(table=table, items=row)
                if ins.status !='success':
                    revert()
                    raise ValueError(f'Failed to add row to {table}. Reason: {ins.reason}. Row: {row}. Reverting changes')
         
    # Set the current version
    upd = sql.update(table='database_info', filters={'database_name': db_name}, items={'current_version': current_ver, 'last_updated': _iso8601()})
    if upd.status !='success':
        raise Exception(f'An unexpected error occurred while trying to set the database version to {current_ver}', upd)


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
        game_name TEXT NOT NULL,
        game_description TEXT DEFAULT NULL,
        status TEXT NOT NULL DEFAULT 'enabled',               -- Whether to create the game or not
        owner_user_id INTEGER NOT NULL,                       -- User_ID who created the game 
        start_money REAL NOT NULL CHECK(start_money > 0),     -- Set starting money, value is in USD (Ensure positive starting amount)
        pick_count INTEGER NOT NULL CHECK(pick_count > 0),    -- Set amount of stocks each user will pick (Ensure positive number of stocks)
        pick_date INTEGER DEFAULT NULL,                       -- Days before or after start of month that picks must be in by. Negative values for after start of month. If NULL, players can join at anytime
        draft_mode BOOLEAN DEFAULT 0,                         -- When enabled, each stock can only be picked once per game.  Pick date must be on or before start date to allow this
        private_game BOOLEAN DEFAULT 0,                       -- When enabled, players must be approved to join.
        allow_selling BOOLEAN DEFAULT 0,                      -- When enabled, users can sell mid-game
        update_frequency TEXT NOT NULL DEFAULT 'daily',       -- How often a game should be updated 'daily', 'hourly', 'minute', 'realtime' REALTIME WILL BE BUGGY
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
        name TEXT NOT NULL,
        description TEXT DEFAULT NULL,
        owner_user_id INTEGER NOT NULL,                       -- User_ID who created the game 
        start_money REAL NOT NULL CHECK(start_money > 0),     -- Set starting money, value is in USD (Ensure positive starting amount)
        pick_count INTEGER NOT NULL CHECK(pick_count > 0),    -- Set amount of stocks each user will pick (Ensure positive number of stocks)
        pick_date TEXT DEFAULT NULL,                          -- Date that picks must be in by.  If NULL, players can join at anytime
        draft_mode BOOLEAN DEFAULT 0,                         -- When enabled, each stock can only be picked once per game.  Pick date must be on or before start date to allow this
        private_game BOOLEAN DEFAULT 0,                       -- When enabled, players must be approved to join.
        allow_selling BOOLEAN DEFAULT 0,                      -- When enabled, users can sell mid-game
        update_frequency TEXT NOT NULL DEFAULT 'daily',       -- How often a game should be updated 'daily', 'hourly', 'minute', 'realtime' REALTIME WILL BE BUGGY
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
        
        UNIQUE (ticker, exchange)
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
        game_id INTEGER NOT NULL,
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
    
    # Run database upgrade
    if upgrade:
        upgrade_db(db_current_ver=db_ver, db_name=db_name)
    
if __name__ == "__main__":
    
    DB_NAME = str(os.getenv('DB_NAME'))
    print(f'DB Name is: {DB_NAME}')
    # upgrade_db(DB_NAME, force_upgrade=True) # Force upgrade to latest version
    create(DB_NAME)
    
    
    