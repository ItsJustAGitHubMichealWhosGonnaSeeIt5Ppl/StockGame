import sqlite3
import os 



#NOTE ISO8601 applies to both (YYYY-MM-DD HH:MM:SS) and (YYYY-MM-DD)! keys should be named according to below
# # (YYYY-MM-DD HH:MM:SS) objects should include 'datetime' in the key name
# # (YYYY-MM-DD) objects should include 'date' in the key name


DB_NAME = str(os.getenv('DB_NAME'))
conn = sqlite3.connect(DB_NAME)
cursor = conn.cursor()
cursor.execute("PRAGMA foreign_keys = ON;") # Enable foreign key constraint enforcement (important for data integrity (According to Gemini))


# Users table
#TODO add source field.  Text string
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,  -- Unique ID (EG: Discord user ID)
    display_name TEXT,                          -- User display name
    permissions INT NOT NULL DEFAULT 210,       -- Store users permissions.
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
    status TEXT NOT NULL DEFAULT 'open',             -- Game status ('open', 'active', 'ended')
    datetime_created TEXT NOT NULL,                       -- ISO8601 (YYYY-MM-DD HH:MM:SS)
    
    FOREIGN KEY (owner_user_id) REFERENCES users (user_id)
);""")
# GAME STATUS OPTIONS #TODO move these
# - 'open' # Game has not yet started, can be joined
# - 'active' # Game started, can be joined if join_late is enabled
# - 'ended' # Game has ended, nothing can be done
#cursor.execute("CREATE INDEX IF NOT EXISTS idx_games ON games(game_name, game_id, game_status);")


# Stocks table 
cursor.execute("""CREATE TABLE IF NOT EXISTS stocks (
    stock_id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL UNIQUE,    -- Stock ticker
    exchange TEXT NOT NULL,         -- Stock exchange that it is listed on
    company_name TEXT               -- Optional?
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