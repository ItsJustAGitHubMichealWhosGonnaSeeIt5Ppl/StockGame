import sqlite3
import os 
from helpers.sqlhelper import SqlHelper
from dotenv import load_dotenv

load_dotenv()

#NOTE ISO8601 applies to both (YYYY-MM-DD HH:MM:SS) and (YYYY-MM-DD)! keys should be named according to below
# # (YYYY-MM-DD HH:MM:SS) objects should include 'datetime' in the key name
# # (YYYY-MM-DD) objects should include 'date' in the key name

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
    if send['status'] == 'error':
        print(send) # Sometimes gives error but does what its asked anyway...
    pass
def create(db_name:str):
    """Create database
    
    Version: 0.0.2a

    Args:
        db_name (str): Database name
        
    # Changelog
    
    ## [0.0.2b] - Unreleased
    
    ### Added
    - sources column to users table

    ### Fixed

    ### Changed

    ### Removed
    """    
    version = "0.0.2" #TODO will require a migration tool
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
    
    
    # Users table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,  -- Unique ID (EG: Discord user ID)
        display_name TEXT,                          -- User display name
        source TEXT NOT NULL,                       -- User source
        permissions INT NOT NULL DEFAULT 210,       -- Store users permissions
        datetime_created TEXT NOT NULL           -- ISO8601 (YYYY-MM-DD HH:MM:SS)
    );""")

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_registered_user_ids ON users(user_id);") # All user IDs

    # Games table #TODO write different game statuses and explainers
    cursor.execute("""CREATE TABLE IF NOT EXISTS games (
        game_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
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
        datetime_created TEXT NOT NULL,                       -- ISO8601 (YYYY-MM-DD HH:MM:SS)
        
        FOREIGN KEY (owner_user_id) REFERENCES users (user_id)
    );""")
    # GAME STATUS OPTIONS
    # - 'open' # Game has not yet started, can be joined
    # - 'active' # Game started, can be joined if join_late is enabled
    # - 'ended' # Game has ended, nothing can be done


    # Stocks table 
    cursor.execute("""CREATE TABLE IF NOT EXISTS stocks (
        stock_id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker TEXT NOT NULL,           -- Stock ticker
        exchange TEXT NOT NULL,         -- Stock exchange that it is listed on
        company_name TEXT,              -- Optional?
        
        UNIQUE (ticker, exchange)
    );""")

    # Stock price (current and historical) table
    cursor.execute("""CREATE TABLE IF NOT EXISTS stock_prices (
        price_id INTEGER PRIMARY KEY AUTOINCREMENT,
        stock_id INTEGER NOT NULL,
        price REAL NOT NULL,           -- Closing price of stock
        datetime TEXT NOT NULL,      -- ISO8601 (YYYY-MM-DD HH:MM:SS)
        
    FOREIGN KEY (stock_id) REFERENCES stocks (stock_id) ON DELETE CASCADE,  -- When a ticker is deleted from the main table, all references to it will also be deleted?
        
    UNIQUE (stock_id, datetime)                                           -- Ensure only one price per stock per day
    );""")
    #cursor.execute("CREATE INDEX IF NOT EXISTS idx_stock_prices ON stock_prices(stock_id, price, price_date);") # I think this will be more useful to have?

    # Game participants table (track who is in which leagues/games)
    cursor.execute("""CREATE TABLE IF NOT EXISTS game_participants (
        participation_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        game_id INTEGER NOT NULL,
        name TEXT,                              -- Optional 'team' name
        status TEXT DEFAULT 'active',           -- A participant (player) status.  Can be 'pending', 'active', 'inactive'.  Pending will be used if a player tries to join a private game
        datetime_joined TEXT NOT NULL,          -- ISO8601 (YYYY-MM-DD HH:MM:SS)
        current_value REAL DEFAULT NULL,        -- Current portfolio value
        datetime_updated TEXT DEFAULT NULL,     -- ISO8601 (YYYY-MM-DD HH:MM:SS)
        
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
        status TEXT DEFAULT 'pending_buy',            -- Status of pick. Options: 'pending_buy', 'owned', 'pending_sell', 'sold'
        datetime_updated TEXT NOT NULL,                    -- ISO8601 (YYYY-MM-DD HH:MM:SS)
        
        FOREIGN KEY (participation_id) REFERENCES game_participants (participation_id) ON DELETE CASCADE,
        FOREIGN KEY (stock_id) REFERENCES stocks (stock_id) ON DELETE RESTRICT, -- Don't delete a stock if picks exist? Or CASCADE? Depends on desired behavior. RESTRICT is safer.
        
    UNIQUE (participation_id, stock_id) -- User picks a specific stock only once per game participation
    );""")

    conn.commit()
    conn.close()
    
if __name__ == "__main__":
    DB_NAME = str(os.getenv('DB_NAME'))
    create(DB_NAME)
    
    