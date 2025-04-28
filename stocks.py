#TODO [x] DB for storing stock information
#TODO frontend (Jack will create)
#TODO Discord interaction bot of some kind?
#TODO should an invite only/needs approval gametype exist? Needs DB changes if so

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
##TODO [x] Do we need to hash user IDs? - No
##TODO Do we need to track whether a user is allowed to create a game or not? (I think no)


import re
import sqlite3
import yfinance as yf
import logging
from datetime import datetime, date

db_name = "stonks.db"
conn = sqlite3.connect(db_name)
cursor = conn.cursor()


    

# Class to handle game creation and management
class Backend:
    # Most of these expect that the data being sent has been checked or otherwise verified.  End users should not interact directly with this
    def __init__(self): #TODO Set database name here, create database if it doesn't exist already, store the database version somewhere?
        pass
    
    def _sql_get(self, table:str, columns:list=["*"], filters:dict=None, order:dict=None): 
        """INTERNAL USE ONLY! Run SQL get queries
        
        THE COLUMNS ARE NOT INJECTION SAFE! DO NOT LET USERS SEND ANYTHING HERE, AND NEVER SEND UNTRUSTED INPUT TO table OR columns

        Args:
            table (str): Table name
            columns(list, optional): List of columns to be returned, Defaults to ['*'] (all columns)
            filters (dict): Key should be the column name to filter by, values should be the variables
            order (dict): Key should be the column name to order by, values should be ASC or DESC
        """        
        sql_query = """SELECT {columns} FROM {table} {filters} {order}"""
        
        filter_str = "" # Will contain filter string (if any)
        filter_vars = list()
        filter_items = list()
        if filters: # Create filter string (if exists)
            for var, item in filters.items():
                if item == None:
                    continue # Skip blank items
                filter_vars.append(var + "=?")
                filter_items.append(item)
            
            if len(filter_vars) > 0: # Sometimes filters are sent but all the items are none I guess
                filter_str = "WHERE " + " AND ".join(filter_vars) 
            
        order_str = "" # Will contain order string (if any)
        order_items = list()
        if order:
            for var, direction in order.items():
                if direction.lower() not in ['asc', 'desc']: # Skip invalid order/sort
                    continue #TODO make this return an error or something I guess
                
                order_items.append(f"{var} {direction.upper()}") 
            
            order_str = "ORDER BY " + ", ".join(order_items)
            
        sql_query = sql_query.format(columns=",".join(columns), table=table, filters=filter_str, order =order_str)
        cursor.execute(sql_query, filter_items)
        resp = cursor.fetchall()
        return resp
    
    def _iso8601(self, date_type:str='datetime'): # Get an ISO formatted datetime
        
        now = datetime.now()
        date_type = date_type.lower() # Easier to work with
        if date_type == 'datetime':
            now = now.strftime("%Y-%m-%d %H:%M:%S")
            
        elif date_type == 'date':
            now = now.strftime("%Y-%m-%d")
            
        else:
            raise ValueError(f"Date type must be 'datetime' or 'date', not {date_type}!")
        
        return now
    
    def _reformat_sqlite(self, data:list, table:str, custom_table:list=None): # Reformat data from the database into more friendly 
        """Reformat the data from SQLite database to make it easier to work with

        Args:
            data (list): Data from SQLite
            table (str): Table that data came from ('games', 'stocks', 'users', 'prices', 'custom', 'picks')
            custom_table (list, optional): If table is set to 'custom', a custom set of columns/keys must be sent here
        Returns:
            list: List of data converted to dictionary format
        """
        
        formatted_data = [] # Data will be stored here
        
        table_columns = {# Column names will be stored here, must be in the same order as SQLITE DB
        'custom': custom_table, #TODO add error if no custom table is sent
        'games': ['id', 'name', 'owner', 'starting_money','total_picks','exclusive_picks','join_after_start','sell_during_game','start_date','end_date','status','creation_date'],
        'stocks': ['id', 'ticker', 'exchange', 'name'],
        'users': ['id', 'username', 'permissions', 'registration_date'],
        'prices': ['id','stock_id','price','price_data'],
        'picks': ['id', 'participant_id', 'stock_id', 'shares' 'start_value', 'current_value', 'status', 'last_updated']
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
    
    def create_user(self, user_id:int, display_name:str, permissions:int = 210):
        """Create a game user

        Args:
            user_id (int): UNIQUE ID to identify user.
            display_name (str): Username/Displayname for user
            permissions (int, optional): User permissions (see). Defaults to 210.
        """
        #TODO Add user permissions docstring
        now = self._iso8601()
        cursor.execute("""INSERT OR IGNORE INTO users (user_id, display_name, permissions, datetime_registered) VALUES(?,?,?)""",(user_id, display_name, permissions, now,)) #TODO move this to elsewhere
        if cursor.rowcount > 0: # This should verifiy that the item was actually added
            conn.commit()
            return "User created"
        else:
            return "User creation failed" #TODO figure out why it failed and raise an error?
        
    def list_users(self, ids_only:bool=False):
        """List all users

        Args:
            ids_only (bool, optional): Only return user IDs. Defaults to False.

        Returns:
            list: All users (includes details unless ids_only is set)
        """
        if ids_only:
            cursor.execute("""SELECT user_id FROM users""") 
            
        else:
            cursor.execute("""SELECT * FROM users""")
        users = cursor.fetchall()
        
        if ids_only:
            users = [user[0] for user in users]
            return users
        
        else:
            return self._reformat_sqlite(users, 'users')
        
    def remove_user(self, user_id:int): #TODO add remove_user
        pass
    
    def get_user(self, user_id:int): #TODO add get_user
        cursor.execute("""SELECT * FROM users WHERE user_id = ?""", (user_id,))
        user = cursor.fetchall()
        if user:
            return self._reformat_sqlite(user, 'users')[0]
        else:
            raise KeyError(f"No user with ID {user_id} found.")
    
    def update_user(self, user_id:int, display_name:str=None, permissions:str=None): #TODO add update_user (allow usernames to be changed)
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
        
        Returns:
            str: Game creation status
        """
        #TODO add validation for dates (make sure it isn't past today, etc)
        end_date = 0 if end_date == None else end_date # Set end date to 0 #TODO is this needed?
        now = self._iso8601()
        
        cursor.execute("""INSERT OR IGNORE INTO games (game_name,owner_user_id,start_money,pick_count,draft_mode,join_late,allow_selling,start_date,end_date,datetime_created) VALUES(?,?,?,?,?,?,?,?,?,?)""",(name, user_id, starting_money, total_picks, exclusive_picks, join_after_start, sell_during_game, start_date, end_date, now,))
        if cursor.rowcount > 0: # This should verifiy that the item was actually added
            conn.commit()
            return "Game created"
        else:
            return "Game creation failed" #TODO figure out why it failed
    
    def list_games(self): # List all games
        """List all games

        Args:

        Returns:
            list: List of games
        """
        filters = {    #TODO Get date filtering working
        }

        #TODO make the filters actually do something
        #TODO send back less information by default?

        cursor.execute("""SELECT * FROM games""") # Get all games
        games = cursor.fetchall()
        games = self._sql_get(table='games',filters=filters) 
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
            return "Invalid ID" #TODO Raise an error here
        else:
            game = self._reformat_sqlite([game], 'games')[0]
            return game
        
    def update_game(self,): #TODO Should changing the game be allowed?
        pass
    
    def delete_game(self,): #TODO Do we need an option to delete games?
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
    
    def list_stocks(self, tickers_only:bool=False):
        """List all stocks

        Args:
            tickers_only (bool, optional): Only return tickers. Defaults to False.

        Returns:
            list: All stocks (includes details unless tickers_only is set)
        """        
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
    
    def get_stock(self, ticker:str):
        """Get an existing stock from ticker

        Args:
            ticker (str): Stock ticker

        Returns:
            dict: Single stock details
        """        
        filters = {'ticker': ticker}
        stock = self._sql_get(table='stocks',filters=filters) 
        if len(stock) > 0:
            return self._reformat_sqlite(stock, 'stocks')[0]
        else:
            return "Invalid Ticker"
        
    def remove_stock(self, ticker:str): #TODO add remove_stock
        pass
    
    # # STOCK PRICE ACTIONS # # 
    
    def add_stock_price(self, ticker:str, price:float, date:str): #TODO should date be set in the action? #TODO maybe use stock_ids here?
        """Add price data for a stock (should be done at close)

        Args:
            ticker (str): Stock ticker
            price (float): Stock price 
            date (str): ISO8601 (YYYY-MM-DD)
        """        
        #AI IS FUCKING STUPID AND CLAIMS WE ABSOLUTELY NEED THE STOCK_ID TO BE ITS OWN THING, SO HERE IS THE SHIT WORKAROUND. FUCK YOU AI
        stock_id = self.get_stock(ticker)['id'] # Fuck you AI #TODO add some sort of error catching here
        
        cursor.execute("""INSERT OR IGNORE INTO stock_prices (stock_id, price, price_date) VALUES(?,?,?)""",(stock_id, price, date,))
        if cursor.rowcount > 0: # This should verifiy that the item was actually added
            conn.commit()
        else:
            pass #TODO add error if needed?
    
    def list_stock_prices(self, ticker:str=None, start_date:str=None, end_date:str=None): # List stock prices, allow some filtering 
        #TODO add docstring
        order = {'price_date': "DESC"}  # Sort by price date
        if ticker: # Ticker isn't none # Fuck you AI #TODO add some sort of error catching here
            stock_id = self.get_stock(ticker)['id']
            filters = f"WHERE stock_id = {stock_id}" #TODO THIS IS DANGEROUS
        
        filters = {    #TODO Get date filtering working
            'stock_id': stock_id if ticker else None
        }

        prices = self._sql_get(table='stock_prices',filters=filters, order=order) 
        prices = self._reformat_sqlite(prices, 'prices') 
        return prices
    
    def get_stock_price(price_id:int):
        pass
    
    def update_stock_prices(self): # Should be run at the end of each day #TODO add docstring #TODO should this be filterable to allow only specific games prices to be updated?
        # What this should do (in order)
        #TODO verify market is closed "prices.tickers['SNAP'].info['postMarketTime']"
        
        # Update all stock prices 
        tickers = self.list_stocks(tickers_only=True) # Get all stock tickers currently in game
        prices = yf.Tickers(tickers).tickers
        for ticker, price in prices.items(): # update pricing
            price = price.info['regularMarketPrice']
            self.add_stock_price(ticker=ticker, price=price, date=self._iso8601('date')) # Update pricing
    
    # # STOCK PICK ACTIONS # #
    
    def add_stock_pick(self, participant_id:int, stock_id:int,): # This is essentially putting in a buy order. End users should not be interacting with this directly 
        #TODO add docstring
        datetime = self._iso8601() 
        cursor.execute("""INSERT OR IGNORE INTO stock_picks (participation_id, stock_id, datetime_updated) VALUES(?,?,?)""",(stock_id, participant_id, datetime,))
        if cursor.rowcount > 0: # This should verifiy that the item was actually added
            conn.commit()
        else:
            pass #TODO add error if needed?
    
    def list_stock_picks(self, status:str=None, participant_id:int=None): #TODO add docstring #TODO test
        #Statuses =  'pending_buy', 'owned', 'pending_sell', 'sold'
        sql_query = """SELECT * FROM stock_picks {filters} """
        
        filters = {
            'pick_status': status, #TODO validate statuses
            'participation_id': participant_id
        }

        picks = self._sql_get(table='stock_picks', filters=filters)
        return self._reformat_sqlite(picks, 'picks')
    
    def get_stock_pick(self, pick_id:int): #TODO add get_stock_pick
        pass
        
    def update_stock_picks(self): #TODO add update_stock_picks #TODO should this allow only updating for a specific game?
        pending_picks = self.list_stock_picks(status='pending_buy') #TODO handle pending_sell here too
        
        pass
        #TODO check that game is active or about to start
        #TODO apply orders
        #TODO update values
        pass
    
    # # GAME PARTICIPATION ACTIONS # #
    def add_user_to_game(self, user_id:int, game_id:int): # TODO should this use name or ID (I think ID)
        datetime = self._iso8601()
        cursor.execute("""INSERT OR IGNORE INTO game_participants (user_id, game_id, datetime_joined) VALUES(?,?,?)""",(user_id, game_id, datetime,))
        if cursor.rowcount > 0: # This should verifiy that the item was actually added
            conn.commit()
        else:
            pass #TODO add error if needed?
        
    def remove_user_from_game(self, game_id:int, user_id:int): #TODO add remove_user_from_game
        pass
    
    def list_game_members(self, game_id:int): #TODO add list_game_members
        pass
    
    def get_game_member(self, participant_id:int): #TODO add list_game_members
        pass
    
    def update_game_info(self, game_id:int): #TODO add update_game_info
        #TODO update player portfolio values

        pass
        
    # # UPDATE ACTIONS # #

    def update(self,): # Update all positions, games, etc 
        #TODO allow specific game(s) to be updated
        #Update order
        #- Update stock prices
        #- Update stock picks (includes running any pending purchases)
        #- Update game info (Set the new portfolio value, etc)
        pass

# INTERFACE INTERACTIONS.  SHOULD EXPECT CRAP FROM USERS AND VALIDATE DATA
class Frontend: # This will be where a bot (like discord) interacts
    def __init__(self, default_permissions:int=210):
        self.backend = Backend()
        self.default_perms = default_permissions
        pass
    
    # Game actions (Return information that is relevant to overall games)
    
    def create_game(self, user_id:int, name:str, start_date:str, end_date:str=None, starting_money:float=10000.00, total_picks:int=10, exclusive_picks:bool=False, join_after_start:bool=False, sell_during_game:bool=False):
        """Create a new stock game!

        Args:
            user_id (int): Game creators user ID
            name (str): Name for this game
            start_date (str): Start date in ISO8601 (YYYY-MM-DD). Must be on or after current date
            end_date (str, optional): Optional end date ISO8601 (YYYY-MM-DD). Defaults to None.
            starting_money (float, optional): Starting money. Minimum 10. Defaults to 10000.00.
            total_picks (int, optional): Amount of stocks each user picks. Minimum 1. Defaults to 10.
            exclusive_picks (bool, optional): Whether multiple users can pick the same stock. Defaults to False.
            join_after_start (bool, optional): Whether users can join late. Defaults to False.
            sell_during_game (bool, optional): Whether users can sell stocks during the game. Defaults to False.
        
        Returns:
            str: Game creation status
        """
        # Data validation #TODO maye this should be higher?
        if starting_money < 10.0:
            return "Error! Starting money must be atleast 10."
        
        elif total_picks < 1:
            return "Error! Users must be allowed to pick atleast 1 stock."
        
        elif datetime.strfdate(start_date, "%Y-%m-%d") < date.today():
            return "Error! Start date must not be in the past!"
            
        try: # Try to get user
            user = self.backend.get_user(user_id=user_id)
            permissions = user['permissions']
            
        except KeyError: # User doesn't exist, create.
            try: #TODO this will never fail right now, so that should be fixed
                self.backend.create_user(user_id=user_id, display_name=user_id, permissions=self.default_perms) # Try to create a user with no name #TODO log a warning that the user was created with no name
            except Exception as e:
                raise e
        
        if permissions - 200 < 0 or permissions - 200 < 19: # User is inactive, banned, or not allowed to create game #TODO this won't work with custom perms!
            reason = "banned" if permissions < 100 else "not allowed to create games!"
            return f"Error! User is {reason}" 
        
        # User is allowed to create games
        try:
            self.backend.create_game(user_id=user_id, name=name, start_date=start_date, end_date=end_date, starting_money=starting_money, total_picks=total_picks, exclusive_picks=exclusive_picks, join_after_start=join_after_start, sell_during_game=sell_during_game)
        except Exception as e: #TODO find errors
            return e
    
    def list_games(self): #TODO allow filtering
        games = self.backend.list_games()
        return games
    
    def game_info(self, game_id:int): 
        game = self.backend.get_game(game_id=game_id)
        return game
    
    # User actions (Return information that is relevant to a specific user)

    def join_game(self):
        pass
    
    def my_games(self):
        pass
    
    def buy_stock(self):
        pass
    
    def my_stocks(self):
        pass
    
    def change_name(self, user_id:int, name:str):
        pass

        

# TESTING

if __name__ == "__main__":
    game = Frontend()
    game.list_games()
    game.create_game(user_id=11102002233, name="Test", start_date="2025-01-01", end_date="2025-01-02")
    pass
    
    if False: # Backend testing
        game = Backend()

        test_stock_tickers = ['MSFT','GME','SNAP','MMM','AOS','ABT']
        for stock in test_stock_tickers:
            game.add_stock(stock)
        add_user = game.add_user(1110002233,"USER")
        game.create_game(user_id=1110002233, name="Test", start_date="2025-01-01", end_date="2025-01-02")
        prices = game.list_stock_prices()
        game.list_stock_picks(1223)
        game.update_stock_prices()

        users = game.list_users()
        ids_only = game.list_users(ids_only=True)
        pass
        #test = game.list_games()
        single_game = game.get_game(1)
        pass


        conn.commit()
        conn.close()