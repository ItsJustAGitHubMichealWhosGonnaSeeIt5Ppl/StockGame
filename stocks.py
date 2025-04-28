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
import os
from datetime import datetime, date

db_name = "stonks.db"
conn = sqlite3.connect(db_name)
cursor = conn.cursor()

class Backend:
    # Most of these expect that the data being sent has been checked or otherwise verified.  End users should not interact directly with this
    def __init__(self): #TODO Set database name here, create database if it doesn't exist already, store the database version somewhere?
        pass
    
    def _sql_filters(self, filters:dict):
        filter_str = "" # Will contain filter string (if any)
        filter_vars = list()
        filter_items = list()
        if filters: # Create filter string (if exists)
            for var, item in filters.items():
                if item != None: # Skip blank items
                    filter_vars.append(var + "=?")
                    filter_items.append(item)
    
            if len(filter_vars) > 0: # Sometimes filters are sent but all the items are none I guess
                filter_str = "WHERE " + " AND ".join(filter_vars)
        
        return filter_str, filter_items
    
    def _sql_items(self, items:dict):
        keys = list()
        values = list()
        questionmarks = list()
        for key, val in items.items(): #TODO better way?
            if val != None:  # Skip blank items
                keys.append(key)
                values.append(val)
                questionmarks.append("?") #TODO this is dogshit
        
        return keys, values, questionmarks
    
    def _sql_insert(self, table:str, items:dict):
        sql_query = "INSERT INTO {table} ({keys}) VALUES({keyvars})"
        keys, values, questionmarks = self._sql_items(items)
        
        sql_query = sql_query.format(table=table, keys=",".join(keys), keyvars=",".join(questionmarks))
        try:
            cursor.execute(sql_query, values)
            conn.commit()
            
        except sqlite3.IntegrityError as e:
            return 'OTHER_ERROR', e
            #return e['sqlite_errorname'], e['args']
            
        except Exception as e:
            return 'OTHER_ERROR', e
    
        return "success", "Added" #TODO more info?
        
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
        
        filter_str, filter_items = self._sql_filters(filters)
            
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
        return resp #TODO add errors
    
    def _sql_update(self, table:str, filters:dict, items:dict):
        sql_query = """UPDATE {table} SET {keys} {filters}"""
        
        filter_str, filter_items = self._sql_filters(filters)
        keys, value_items, questionmarks = self._sql_items(items)
            
        all_items = value_items + filter_items
            
        sql_query = sql_query.format(table=table, keys=",".join(keys), filters=filter_str)
        cursor.execute(sql_query, all_items)
        conn.commit()
        return "something happened" #TODO add errors
    
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
        'games': ['id', 'name', 'owner', 'starting_money','total_picks','exclusive_picks','join_after_start','sell_during_game','update_frequency','start_date','end_date','status','creation_date'],
        'stocks': ['id', 'ticker', 'exchange', 'name'],
        'users': ['id', 'username', 'permissions', 'registration_date'],
        'prices': ['id','stock_id','price','price_data'],
        'picks': ['id', 'participant_id', 'stock_id', 'shares', 'start_value', 'current_value', 'status', 'last_updated']
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
    
    def create_user(self, user_id:int, display_name:str=None, permissions:int = 210):
        """Create a game user

        Args:
            user_id (int): UNIQUE ID to identify user.
            display_name (str): Username/Displayname for user
            permissions (int, optional): User permissions (see). Defaults to 210.
        """
        #TODO Add user permissions docstring
        items = {'user_id': user_id, 
                 'display_name':display_name if display_name else user_id, # Set display name to user ID if there isnt one supplied
                 'permissions': permissions,
                 'datetime_registered': self._iso8601()}
        
        user = self._sql_insert(table='users', items=items)
        #TODO move errors here
        return user
        
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
    
    def get_user(self, user_id:int):
        filters = {'user_id': user_id}
        user = self._sql_get(table='users', filters=filters)
        return self._reformat_sqlite(user, 'users')[0] #TODO add error handling
    
    def update_user(self, user_id:int, display_name:str=None, permissions:str=None): 
        items = {'display_name': display_name,
                 'permissions': permissions}
        
        filters = {'user_id': user_id}
        self._sql_update(table="users", filters=filters, items=items)
    
    # # GAME MANAGEMENT ACTIONS # #
    
    def create_game(self, user_id:int, name:str, start_date:str, end_date:str=None, starting_money:float=10000.00, total_picks:int=10, exclusive_picks:bool=False, join_after_start:bool=False, sell_during_game:bool=False, update_frequency:str='daily'):
        """Create a new stock game!
        
        WARNING: If using realtime, expect issues

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
            update_frequency (str, optional): How often prices should update ('daily', 'hourly', 'minute', 'realtime'). Defaults to 'daily'.
            
        
        Returns:
            str: Game creation status
        """
        #TODO add validation for dates (make sure it isn't past today, etc)
        items = {'game_name': name,
                 'owner_user_id': user_id,
                 'start_money': starting_money,
                 'pick_count': total_picks,
                 'draft_mode': exclusive_picks,
                 'join_late': join_after_start,
                 'allow_selling': sell_during_game,
                 'update_frequency': update_frequency,
                 'start_date': start_date,
                 'end_date': "None" if end_date == None else end_date, #TODO is this needed?
                 'datetime_created': self._iso8601()}

        game = self._sql_insert(table='games', items=items)
        return game #TODO error catching and checking
    
    def list_games(self): # List all games
        """List all games

        Args:

        Returns:
            list: List of games
        """
        filters = {}    #TODO Get date filtering working #TODO send back less information by default?
        
        games = self._sql_get(table='games',filters=filters) 
        return self._reformat_sqlite(games, 'games') # Send games data to be reformatted
    
    def get_game(self, game_id:int):
        """Get a single game by ID

        Args:
            game_id (int): Game ID

        Returns:
            dict: Game information OR "Invalid ID"
        """        
        filters = {'game_id': int(game_id)}
        game = self._sql_get(table='games',filters=filters)
        if game == None: # Will return none for invalid game id
            return "Invalid ID" #TODO Raise an error here
        else:
            game = self._reformat_sqlite(game, 'games')[0]
            return game
        
    def update_game(self,): #TODO Should changing the game be allowed?
        pass
    
    def delete_game(self,): #TODO Do we need an option to delete games?
        pass
    
    # # STOCK ACTIONS # # #TODO should these be split into classes for ease of use?
    
    def create_stock(self, ticker:str):
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
            #TODO use new insert system
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
        columns = []    
        if tickers_only:
            columns = ['ticker']
            
        stocks = self._sql_get(table='stocks', columns=columns)
        
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
            return "No stocks found"
        
    def remove_stock(self, ticker:str): #TODO add remove_stock
        pass
    
    # # STOCK PRICE ACTIONS # # 
    
    def add_stock_price(self, ticker:str, price:float, date:str): #TODO should date be set in the action? #TODO maybe use stock_ids here? #TODO this won't handle the different game types 
        """Add price data for a stock (should be done at close)

        Args:
            ticker (str): Stock ticker
            price (float): Stock price 
            date (str): ISO8601 (YYYY-MM-DD)
        """
        #AI IS FUCKING STUPID AND CLAIMS WE ABSOLUTELY NEED THE STOCK_ID TO BE ITS OWN THING, SO HERE IS THE SHIT WORKAROUND. FUCK YOU AA
        stock_id = self.get_stock(ticker)['id'] #TODO add some sort of error catching here
        
        items = {'stock_id':int(stock_id), 
                 'price': float(price), 
                 'price_date': str(date)}
        
        stock = self._sql_insert(table='stock_prices', items=items)
        return stock 
    
    def list_stock_prices(self, stock_id:str=None, date:str=None,): # List stock prices, allow some filtering 
        #TODO add docstring
        order = {'price_date': "DESC"}  # Sort by price date
        filters = {    #TODO Get date filtering working
            'stock_id': stock_id,
            'price_date': date
        }

        prices = self._sql_get(table='stock_prices',filters=filters, order=order) 
        prices = self._reformat_sqlite(prices, 'prices') 
        return prices
    
    def get_stock_price(price_id:int):
        pass
    
    def update_stock_prices(self): #TODO add docstring
        # THIS WILL NOT VALIDATE WHETHER IT IS THE END OF THE DAY OR NOT, THAT IS UP TO YOU TO DO!
        
        tickers = self.list_stocks(tickers_only=True) # Get all stock tickers currently in game
        prices = yf.Tickers(tickers).tickers
        for ticker, price in prices.items(): # update pricing
            price = price.info['regularMarketPrice']
            self.add_stock_price(ticker=ticker, price=price, date=self._iso8601('date')) # Update pricing
    
    # # STOCK PICK ACTIONS # #
    
    def add_stock_pick(self, participant_id:int, stock_id:int,): # This is essentially putting in a buy order. End users should not be interacting with this directly 
        #TODO add docstring
        items = {'participation_id':participant_id,
                 'stock_id':stock_id,
                 'datetime_updated': self._iso8601()}
        pick = self._sql_insert(table='stock_picks', items=items)
        return pick
    
    def list_stock_picks(self, status:str=None, participant_id:int=None): #TODO add docstring
        #Statuses =  'pending_buy', 'owned', 'pending_sell', 'sold'
        
        filters = {'pick_status': status, #TODO validate statuses
                   'participation_id': participant_id}

        picks = self._sql_get(table='stock_picks', filters=filters)
        return self._reformat_sqlite(picks, 'picks')
    
    def get_stock_pick(self, pick_id:int):
        filters = {'pick_id': pick_id}
        pick = self._sql_get(table='stock_picks', filters=filters)
        return self._reformat_sqlite(pick, 'picks')[0]
    
    def update_stock_pick(self, pick_id:int, current_value:float,  shares:int=None, start_value:float=None,  status:str=None): #Update a single stock pick
        items = {'shares': shares,
                 'start_value': start_value,
                 'current_value': current_value,
                 'pick_status': status,
                 'datetime_updated': self._iso8601()}
        
        filters = {'pick_id': pick_id}
        
        pick = self._sql_update(table="stock_picks", filters=filters, items=items)
        return pick # TODO add error handling
    
    def update_stock_picks(self, date:str, game_id:int=None): #TODO add update_stock_picks #TODO allow blank date to use latest
        #TODO implement game_id filtering
        pending_picks = self.list_stock_picks(status='pending_buy') #TODO handle pending_sell here too
        for pick in pending_picks:
            price = self.list_stock_prices(stock_id=pick['stock_id'],date=date)[0] #TODO handle no data
            
            self.update_stock_pick(pick_id=pick['id'],)
            
            
        
        #TODO check that game is active or about to start
        #TODO apply orders
        #TODO update values
        pass
    
    # # GAME PARTICIPATION ACTIONS # #
    def add_user_to_game(self, user_id:int, game_id:int):
        items = {'user_id':user_id, 
                 'game_id':game_id, 
                 'datetime_joined': self._iso8601()
        }
        game = self._sql_insert(table='game_participants', items=items)
        return game #TODO add errors here
        
    def remove_user_from_game(self, game_id:int, user_id:int): #TODO add remove_user_from_game
        pass
    
    def get_participant_id(self, user_id:int, game_id:int): # Will save time
        filters = {'user_id': user_id,
                   'game_id': game_id}
        participant = self._sql_get(table='game_participants', columns=['participation_id'], filters=filters) 
        return participant[0][0] # Drill down 
        pass
    
    
    def list_game_members(self, game_id:int): #TODO add list_game_members
        pass
    
    def get_game_member(self, participant_id:int): #TODO add game_game_members
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
    
    # # HELPERS # #
    
        

# INTERFACE INTERACTIONS.  SHOULD EXPECT CRAP FROM USERS AND VALIDATE DATA
class Frontend: # This will be where a bot (like discord) interacts
    def __init__(self, owner_user_id:int, default_permissions:int=210):
        """For use with a discord bot or other frontend. 
        
        Provides  basic error handling, data validation, more user friendly commands, and more.

        Args:
            owner_user_id (int): User ID of the owner.  This user will be able to control everything.
            default_permissions (int, optional): Default permissions for new users. Defaults to 210. (Users can view and join games, but not create their own)
        """
        self.backend = Backend()
        self.default_perms = default_permissions
        self.register(owner_user_id,owner_user_id) # Try to register user
        self.backend.update_user(user_id=owner_user_id, permissions=288)
        self.owner_id = owner_user_id
        #TODO implement owner user
        pass
    
    # Game actions (Return information that is relevant to overall games)
    
    def create_game(self, user_id:int, name:str, start_date:str, end_date:str=None, starting_money:float=10000.00, total_picks:int=10, exclusive_picks:bool=False, join_after_start:bool=False, sell_during_game:bool=False, update_frequency:str='daily'):
        """Create a new game.

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
            update_frequency (str, optional): How often prices should update ('daily', 'hourly', 'minute', 'realtime'). Defaults to 'daily'.
        
        Returns:
            str: Game creation status
        """
        #TODO Should the user be automatically added to their own game? Probably?
        # Data validation #TODO maybe this should be higher?
        if starting_money < 10.0:
            return "Error! Starting money must be atleast 10."
        
        elif total_picks < 1:
            return "Error! Users must be allowed to pick atleast 1 stock."
        
        # Date checks
        elif datetime.strptime(start_date, "%Y-%m-%d").date() < date.today():
            return "Error! Start date must not be in the past!"
        
        elif end_date != None and datetime.strptime(start_date, "%Y-%m-%d").date() > datetime.strptime(end_date, "%Y-%m-%d").date():
            return "Error! End date cannot be before start date!"
        try: # Try to get user
            user = self.backend.get_user(user_id=user_id)
            
            
        except KeyError: # User doesn't exist, create.
            try: #TODO this will never fail right now, so that should be fixed
                self.backend.create_user(user_id=user_id, display_name=user_id, permissions=self.default_perms) # Try to create a user with no name #TODO log a warning that the user was created with no name
                user = self.backend.get_user(user_id=user_id)
            except Exception as e:
                raise e
        
        permissions = user['permissions']
        
        if permissions - 200 < 0 or permissions - 200 < 19: # User is inactive, banned, or not allowed to create game #TODO this won't work with custom perms!
            reason = "banned" if permissions < 100 else "not allowed to create games!"
            return f"Error! User is {reason}" 
        
        # User is allowed to create games
        try:
            self.backend.create_game(user_id=int(user_id), name=name, start_date=start_date, end_date=end_date, starting_money=starting_money, total_picks=total_picks, exclusive_picks=exclusive_picks, join_after_start=join_after_start, sell_during_game=sell_during_game, update_frequency=update_frequency)
        except Exception as e: #TODO find errors
            return e
    
    def list_games(self): #TODO allow filtering
        games = self.backend.list_games()
        return games
    
    def game_info(self, game_id:int):
        """Get information about a specific game

        Args:
            game_id (int): Game ID

        Returns:
            dict: Game information
        """
        #TODO validate game ID?
        game = self.backend.get_game(game_id=int(game_id))
        return game
    
    # User actions (Return information that is relevant to a specific user)
    
    def register(self, user_id:int, username:str):
        user = self.backend.create_user(user_id=user_id ,display_name=username, permissions=self.default_perms)
        if user[0] == 'success':
            return "Registered"
        
        elif user[0] == 'SQLITE_CONSTRAINT_PRIMARYKEY':
            return "User already registered"
        
        else: #TODO add logging here
            return "Unknown error occurred while registering user"

    def change_name(self, user_id:int, name:str):
        user = self.backend.update_user(user_id=int(user_id), display_name=str(name))
        return user #TODO return an error instead
    
    def join_game(self, user_id:int, game_id:int): 
        #TODO check permissions before running
        game = self.backend.add_user_to_game(user_id=user_id, game_id=game_id)
        return game
    
    def my_games(self, user_id:int): #TODO add
        pass
    
    def buy_stock(self, user_id:int, game_id:int, ticker:str):
        part_id = self.backend.get_participant_id(user_id=user_id, game_id=game_id)
        stock = self.backend.get_stock(ticker=str(ticker)) # Try to get the stock 
        if stock == "No stocks found": # Stock not yet added:
            self.backend.create_stock(ticker=str(ticker)) #TODO handle invalid tickers!
            stock = self.backend.get_stock(ticker=str(ticker)) #TODO clean this up
        
        pick = self.backend.add_stock_pick(participant_id=part_id, stock_id=stock['id']) # Add the pick
        return pick 
    
    def sell_stock(self, user_id:int, game_id:int, ticker:str): # Will also allow for cancelling an order
        pass
    
    def my_stocks(self, user_id:int, game_id:int):
        part_id = self.backend.get_participant_id(user_id=user_id, game_id=game_id) # TODO error validation
        picks = self.backend.list_stock_picks(participant_id=part_id)
        return picks
    
    def update(self, user_id:int, game_id:int=None, force:bool=False): # Update games or a specific game
        if user_id != self.owner_user_id:
            return "You do not have permission to do this"
        
        self.backend.update_stock_prices()
        #TODO update the rest!
        

        

# TESTING

if __name__ == "__main__":
    owner = os.getenv("OWNER")
    game = Frontend(owner_user_id=owner)
    print(game.list_games())
    create = game.create_game(user_id=owner, name="TestGame", start_date="2025-05-01", end_date="2025-05-10")
    print(game.buy_stock(owner, 1, 'MSFT'))
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