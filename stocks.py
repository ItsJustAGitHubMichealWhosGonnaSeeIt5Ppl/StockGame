#TODO [x] DB for storing stock information
#TODO frontend (Jack will create)
#TODO Discord interaction bot of some kind?

# Overall idea - Stock picking game
## Users will get 100, 1000, or 10000 USD and pick (up to) 10 stocks.  Each pick will be 
## Historical data for each ticker will be stored from close price daily
## Price should be saved to the second decimal
## Buys will happen at the end of each day (same as tracking)
## Date format: YYYY-MM-DD
## Track the users total gain (and percent)
## Track the users last 7 days of gain

# OTHER IDEAS
## Draft style picks - users cannot pick the same stocks
## Rolling 12 month start to allow more people to join
## Multiple games (leagues) allowed
## If mid-game sells are allowed, use a ticker called "CASH" or something?


# More questions
##TODO Do we need to hash user IDs?
##TODO Do we need to track whether a user is allowed to create a game or not? (I think no)


import re
import sqlite3
import yfinance as yf
from datetime import datetime

db_name = "stonks.db"
conn = sqlite3.connect(db_name)
cursor = conn.cursor()


    

# Class to handle game creation and management
class StockGame: #TODO does this need to be a class?

    def _iso8601(self, date_type:str='datetime'): # Get an ISO formatted datetime #TODO allow type to be set to date
        now = datetime.now()
        if date_type == 'datetime':
            now = now.strftime("%Y-%m-%d %H:%M:%S")
            
        elif date_type == 'date':
            now = now.strftime("%Y-%m-%d")
            
        else:
            raise ValueError(f"Date type must be 'datetime' or 'date', not {date_type}!")
        
        return now
    
    
    def _reformat_sqlite(self, data:list, table:str): # Reformat data from the database into more friendly 
        """Reformat the data from SQLite database to make it easier to work with

        Args:
            data (list): Data from SQLite
            table (str): Table that data came from ('games', 'stocks', 'users')

        Returns:
            list: List of data converted to dictionary format
        """
        supported_tables = ['games', 'stocks', 'users'] #TODO redundant?

        
        formatted_data = [] # Data will be stored here
        
        table_columns = {# Column names will be stored here, must be in the same order as SQLITE DB
        'games': ['id', 'name', 'creator', 'starting_money','total_picks','total_picks','exclusive_picks','join_after_start','sell_during_game','start_date','end_date','status','creation_date'],
        'stocks': ['id', 'ticker', 'exchange', 'name'],
        'users': ['id', 'username', 'registration_date'],
        'prices': ['id','stock_id','price','price_data']
        }
        if table not in table_columns.keys():
            raise ValueError(f"{table} is not supported!  Please only use supported tables.")
        
        columns = table_columns[table]
            
        
        for raw_data in data: # Reformat data from SQLite #TODO surely there is a way to get column names?
            item = {}
            for count, value in enumerate(raw_data): #TODO validate that the length of values and columns are the same 
                item[columns[count]] = value
            
            formatted_data.append(item)
        
        return formatted_data
    
    # # USER ACTIONS # #
    
    def add_user(self, user_id:int, username:str):
        """Add a game user

        Args:
            user_id (int): UNIQUE ID to identify user.
            username (str): Username/Displayname for user
        """
        #TODO check if the user exists
        now = self._iso8601()
        cursor.execute("""INSERT OR IGNORE INTO users (user_id,display_name,datetime_registered) VALUES(?,?,?)""",(user_id, username, now,))
        pass
        
    def remove_user(self, user_id:int): #TODO add this
        pass
    
    def list_users(self, ids_only:bool=False): #TODO add docstring
        if ids_only:
            cursor.execute("""SELECT user_id FROM users""") #TODO the formatting here is kinda fucked
            
        else:
            cursor.execute("""SELECT * FROM users""")
        users = cursor.fetchall()
        
        if ids_only:
            return users
        else:
            return self._reformat_sqlite(users, 'users')
        
    
    def get_user(self, user_id): #TODO add
        pass
    
    # # GAME MANAGEMENT ACTIONS # #
    
    def create_game(self, user_id:int, name:str, start_date:str, end_date:str=None, starting_money:float=10000.00, total_picks:int=10, exclusive_picks:bool=False, join_after_start:bool=False, sell_during_game:bool=False):
        """Create a new stock game!

        Args:
            user_id (int): Game creators user ID
            name (str): Name for this game
            start_date (str): Start date in ISO8601 (YYYY-MM-DD)
            end_date (str, optional): Optional end date ISO8601 (YYYY-MM-DD). Defaults to None.
            starting_money (float, optional): Starting money. Defaults to $10000.00.
            total_picks (int, optional): Amount of stocks each user picks. Defaults to 10.
            exclusive_picks (bool, optional): Whether multiple users can pick the same stock. Defaults to False.
            join_after_start (bool, optional): Whether users can join late. Defaults to False.
            sell_during_game (bool, optional): Whether users can sell stocks during the game. Defaults to False.
        """
        #TODO check if the user exists
        #TODO add validation for dates (make sure it isn't past today, etc)
        end_date = 0 if end_date == None else end_date # Set end date to 0 #TODO is this needed?
        now = self._iso8601()
        
        cursor.execute("""INSERT OR IGNORE INTO games (game_name,created_by,start_money,pick_count,draft_mode,join_late,allow_selling,start_date,end_date,datetime_created) VALUES(?,?,?,?,?,?,?,?,?,?)""",(name, user_id, starting_money, total_picks, exclusive_picks, join_after_start, sell_during_game, start_date, end_date, now,))
        pass #TODO should this return anything?
    
    
    def delete_game(self,): #TODO Do we need an option to delete games?
        pass
    
    def list_games(self, only_show_joinable:bool=False, show_ended_games:bool=False): # List all games
        """List all games

        Args:
            only_show_joinable (bool, optional): Only show joinable games. Defaults to False.
            show_ended_games (bool, optional): Show games that have ended. Defaults to False.

        Returns:
            list: List of games
        """        
        #TODO make the filters actually do something
        #TODO send back less information by default?

        cursor.execute("""SELECT * FROM games""") # Get all games
        games = cursor.fetchall()
        games_list = self._reformat_sqlite(games, 'games') # Send games data to be reformatted
        return games_list
    
    def get_game(self, game_id:int):
        """Get a single game by ID

        Args:
            game_id (int): Game ID

        Returns:
            dict: Game information OR "Invalid ID"
        """        
        
        cursor.execute("""SELECT * FROM games WHERE game_id=?""", (game_id,))
        game = cursor.fetchone()
        if game == None: # Will return none for invalid game id
            return "Invalid ID" #TODO should this raise an error instead?
        else:
            game = self._reformat_sqlite([game], 'games')
            return game
    
    def join_game(self, game_id:str, user_id:int): # TODO should this use name or ID (I think ID)
        pass
    
    def leave_game(self, game_id:str, user_id:int):
        pass
    
    # # STOCK ACTIONS # # #TODO should these be split into classes for ease of use?
    
    def add_stock(self, ticker:str):
        """Add a stock

        Args:
            ticker (str): Stock ticker. Format should be 'MSFT'

        Returns:
            str: status/error #TODO should this raise an error instead?
        """        
        #TODO regex the subimissions to check for invalid characters and save time.
        #TODO should only USD stocks be allowed/limit exchanges?
        #TODO what happens if multiple stocks are returned (probably something bad)
        existing_tickers = self.list_stocks(tickers_only=True)
        if ticker in existing_tickers:
            return "Ticker already exists"
        
        stock = yf.Ticker(ticker)
    
        try:
            info = stock.info
        except AttributeError: # If stock isn't valid, an attribute error should be raised
            info = []
    
        if len(info) > 0: # Try to verify ticker is real and get the relevant info
            ticker = ticker.upper()
            exchange = info['fullExchangeName']
            company = info['displayName'] if 'displayName' in info else info['shortName'] # I guess not all stocks have a long name?
            
            cursor.execute("""INSERT OR IGNORE INTO stocks (ticker,exchange,company_name) VALUES(?,?,?)""",(ticker, exchange, company,))
            conn.commit()
            return "Ticker added"
        else:
            return "Ticker invalid" #TODO is this a good way to verify
    
    def remove_stock(self, ticker:str): #TODO add remove_stock
        pass
    
    def list_stocks(self, tickers_only:bool=False): #TODO add a docstring
        if tickers_only:
            cursor.execute("""SELECT ticker FROM stocks""") 
            
        else:
            cursor.execute("""SELECT * FROM stocks""")
        stocks = cursor.fetchall()
        
        if tickers_only:
            tickers = [ticker[0] for ticker in stocks]
            return tickers
        
        else:
            return self._reformat_sqlite(stocks, 'stocks')
    
    def get_stock(self, ticker:str): #TODO add get_stock maybe
        cursor.execute("""SELECT * FROM stocks WHERE ticker = ?""", (ticker,))
        stock = cursor.fetchall()
        if len(stock) > 0:
            return self._reformat_sqlite(stock, 'stocks')[0]
        else:
            return "Invalid Ticker"
    # # STOCK PRICE ACTIONS # # 
    
    
    def add_stock_price(self, ticker:str, price:int, date:str): #TODO add a docstring #TODO should date be set in the action?
        #AI IS FUCKING STUPID AND CLAIMS WE ABSOLUTELY NEED THE STOCK_ID TO BE ITS OWN THING, SO HERE IS THE SHIT WORKAROUND. FUCK YOU AI
        stock_id = self.get_stock(ticker)['id'] # Fuck you AI #TODO add some sort of error catching here
        
        cursor.execute("""INSERT OR IGNORE INTO stock_prices (stock_id, price, price_date) VALUES(?,?,?)""",(stock_id, price, date,))
        if cursor.rowcount > 0: # This should verifiy that the item was actually added
            conn.commit()
        else:
            pass #TODO add error if needed?
        
        
    
    def list_stock_prices(self, ticker:str=None, start_date:str=None, end_date:str=None): # List stock prices, allow some filtering
        sql_query = """SELECT * FROM stock_prices {filters} {order}"""
        filters = ""
        order = "ORDER BY price_date DESC" # Set the order
        if ticker: # Ticker isn't none
            stock_id = self.get_stock(ticker)['id']
            filters = f"WHERE stock_id = {stock_id}" #TODO THIS IS DANGEROUS
            
        #TODO Get date filtering working!
        sql_query = sql_query.format(filters=filters, order=order)
         # Fuck you AI #TODO add some sort of error catching here
        cursor.execute(sql_query)
        prices = cursor.fetchall() #TODO verify data exists here
        prices = self._reformat_sqlite(prices, 'prices')
        return prices 
    
    # # STOCK PICK ACTIONS # #
    
    def add_stock_pick(self, participation_id:int, stock_id:int, shares:float,): # This is essentially putting in a buy order. End users should not be interacting with this directly
        #TODO confirm user can even pick a stock
        pass
    
    def ez_stock_pick(self, user_id:int, game_id:int, ticker:str): #Allow buying a stock without knowing backend info #TODO maybe this should be in a class that handles users/players?
        
        pass
        
    # # GAMEPLAY ACTIONS # #
    
    # # UPDATE ACTIONS # #
    
    def update_stock_prices(self): # Should be run at the end of each day
        # What this should do (in order)
        #TODO verify market is closed "prices.tickers['SNAP'].info['postMarketTime']"
        #TODO apply all stock pick orders
        #TODO update all stock picks values
        #TODO update player portfolio values
        
        # Update all stock prices
        tickers = self.list_stocks(tickers_only=True) # Get all stock tickers currently in game
        prices = yf.Tickers(tickers).tickers
        for ticker, price in prices.items(): # update pricing
            price = price.info['regularMarketPrice']
            self.add_stock_price(ticker=ticker, price=price, date=self._iso8601('date')) # Update pricing 
        
    def update(self,): # Update all positions, games, etc 
        #TODO allow specific game(s) to updated 
        #TODO allow updating only stocks
        #TODO allow more choice
        pass
    # # REQUESTED FEATURES/DATA DISPLAY # #
    
    # # USER FACING STUFF # # (this is where stock picking will be handled maybe?)


# TESTING

game = StockGame()

test_stock_tickers = ['MSFT','GME','SNAP','MMM','AOS','ABT']
for stock in test_stock_tickers:
    game.add_stock(stock)
add_user = game.add_user(1110002233,"USER")
game.create_game(user_id=1110002233, name="Test", start_date="2025-01-01", end_date="2025-01-02")
game.list_stock_prices()
game.update_stock_prices()

users = game.list_users()
ids_only = game.list_users(ids_only=True)
pass
#test = game.list_games()
single_game = game.get_game(1)
pass


conn.commit()
conn.close()  