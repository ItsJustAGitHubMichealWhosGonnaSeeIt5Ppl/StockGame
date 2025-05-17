#TODO Do we need to track whether a user is allowed to create a game or not? (I think no)

import re
import yfinance as yf
import logging
import os
from datetime import datetime, date
from helpers.sqlhelper import SqlHelper, _iso8601



version = "0.0.2" #TODO should frontend and backend have different versions?

class Backend:
    # Most of these expect that the data being sent has been checked or otherwise verified.  End users should not interact directly with this
    def __init__(self, db_name:str): #TODO create database if it doesn't exist already, store the database version somewhere?
        """Backend
        """
        self.sql = SqlHelper(db_name)
        self.version = "0.0.2"
    
    def _reformat_sqlite(self, data:list, custom_keys:dict=None): # Reformat data from the database into more friendly 
        """Reformat the data from SQLite database to make it easier to work with

        Args:
            data (list): Data from SQLite
            custom_keys (dict, optional): Custom key names
        
        Returns:
            list: List of reformatted data
        """
        formatted_data = [] # Data will be stored here
        if custom_keys: # Allow custom key mapping
            keys = custom_keys
        
        else:
            keys = { # Friendly names for SQL items
            # Multiple/Generic
            'datetime_created': 'creation_date', # Games, Users, 
            'datetime_updated': 'last_updated', # Participants, Picks
            # Games
            'game_id': 'id',
            'owner_user_id': 'owner',
            'start_money': 'starting_money',
            'pick_count':'total_picks',
            'draft_mode':'exclusive_picks',
            'allow_selling':'sell_during_game',
            'update_frequency':'update_frequency',
            # Participants
            'participation_id': 'id',
            'datetime_joined': 'joined',
            # Picks
            'pick_id': 'id',
            'participation_id': 'participant_id',
            
            # Prices
            'price_id': 'id',
            # Stocks
            'stock_id': 'id',
            'company_name': 'name',
            # Users
            'user_id': 'id',
            'display_name': 'username',
            }
        for raw_data in data: # Reformat data from SQLite #TODO surely there is a way to get column names?
            item = {}
            for key, val in raw_data.items(): #TODO validate that the length of values and columns are the same
                try:
                    item[keys[key]] = val
                except KeyError: # If not in the list, just use the SQL NAME
                    item[key] = val
                    
            formatted_data.append(item)
        return formatted_data
    
    # # USER ACTIONS # #
    
    def add_user(self, user_id:int, display_name:str=None, permissions:int = 210):
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
                 'datetime_created': _iso8601()}
        
        user = self.sql.insert(table='users', items=items)
        #TODO move errors here
        return user
        
    def remove_user(self, user_id:int): #TODO add remove_user
        pass
    
    def list_users(self, ids_only:bool=False): #TODO allow some filtering#
        """List all users

        Args:
            ids_only (bool, optional): Only return user IDs. Defaults to False.

        Returns:
            list: All users (includes details unless ids_only is set)
        """
        
        if ids_only:
            columns = ['user_id']
            
        else:
            columns = ['*']
        
        users = self.sql.get(table='users', columns=columns)
        if ids_only:
            users = [user['user_id'] for user in users]
            return users
        
        else:
            return self._reformat_sqlite(users)
        
    def get_user(self, user_id:int):
        """Get a single user by ID

        Args:
            user_id (int): User ID.

        Returns:
            dict: User information
        """
        filters = {'user_id': user_id}
        user = self.sql.get(table='users', filters=filters)
        return self._reformat_sqlite(user)[0] #TODO add error handling #TODO test
    
    def update_user(self, user_id:int, display_name:str=None, permissions:str=None): 
        items = {'display_name': display_name,
                 'permissions': permissions}
        
        filters = {'user_id': user_id}
        self.sql.update(table="users", filters=filters, items=items)
    
    # # GAME MANAGEMENT ACTIONS # #
    
    def add_game(self, user_id:int, name:str, start_date:str, end_date:str=None, starting_money:float=10000.00, pick_date:str=None, private_game:bool=False, total_picks:int=10, draft_mode:bool=False, sell_during_game:bool=False, update_frequency:str='daily'):
        """Create a new stock game!
        
        WARNING: If using realtime, expect issues

        Args:
            user_id (int): Game creators user ID
            name (str): Name for this game
            start_date (str): Start date in ISO8601 (YYYY-MM-DD)
            end_date (str, optional): End date ISO8601 (YYYY-MM-DD). Defaults to None.
            starting_money (float, optional): Starting money. Defaults to $10000.00.
            pick_date (str, optional): Date stocks must be picked by in ISO8601 (YYYY-MM-DD). Defaults to None (allow players to join anytime)
            private_game(bool, optional): Whether the game is private or not
            total_picks (int, optional): Amount of stocks each user picks. Defaults to 10.
            draft_mode (bool, optional): Whether multiple users can pick the same stock.  If enabled (players cannot pick the same stocks), pick date must be on or before start date Defaults to False.
            sell_during_game (bool, optional): Whether users can sell stocks during the game. Defaults to False.
            update_frequency (str, optional): How often prices should update ('daily', 'hourly', 'minute', 'realtime'). Defaults to 'daily'.
            
        Returns:
            str: Game creation status
        """
        #TODO should these be exceptions
        #TODO move more validation here
        if draft_mode and datetime.strptime(start_date, "%Y-%m-%d").date() < datetime.strptime(pick_date, "%Y-%m-%d").date():
            return "Error! Pick date must be before start date when draft mode is enabled!"
            
        elif starting_money < 1.0:
            return "Error! Starting money must be atleast 1."
        
        elif total_picks < 1:
            return "Error! Users must be allowed to pick atleast 1 stock."
        
        items = {'name': name,
                 'owner_user_id': user_id,
                 'start_money': starting_money,
                 'pick_count': total_picks,
                 'draft_mode': draft_mode,
                 'pick_date': pick_date,
                 'private_game': private_game,
                 'allow_selling': sell_during_game,
                 'update_frequency': update_frequency,
                 'start_date': start_date,
                 'end_date': "None" if end_date == None else end_date,  # is this needed?, no but I like it.
                 'datetime_created': _iso8601()}

        game = self.sql.insert(table='games', items=items)
        return game #TODO error catching and checking
    
    def list_games(self): # List all games
        """List all games

        Args:

        Returns:
            list: List of games
        """
        filters = {}    #TODO Get date filtering working #TODO send back less information by default?
        
        games = self.sql.get(table='games',filters=filters) 
        return self._reformat_sqlite(games) # Send games data to be reformatted #TODO test
    
    def get_game(self, game_id:int):
        """Get a single game by ID

        Args:
            game_id (int): Game ID

        Returns:
            dict: Game information OR "Invalid ID"
        """        
        filters = {'game_id': int(game_id)}
        game = self.sql.get(table='games',filters=filters)
        if game == None: # Will return none for invalid game id
            return "Invalid ID" #TODO Raise an error here
        else:
            game = self._reformat_sqlite(game)[0] #TODO test
            return game
        
    def update_game(self,): #TODO Should changing the game be allowed?
        pass
    
    # # STOCK ACTIONS # #
    
    def add_stock(self, ticker:str):
        """Add a stock

        Args:
            ticker (str): Stock ticker. Format should be 'MSFT'

        Returns:
            str: status/error #TODO should this raise an error instead? Yes
        """        
        #TODO regex the subimissions to check for invalid characters and save time.
        #TODO should only USD stocks be allowed/limit exchanges?
        #TODO what happens if multiple stocks are returned (probably something bad)
        #TODO maybe the stock details should be gathered elsewhere.
        existing_tickers = self.list_stocks(tickers_only=True)
        if ticker in existing_tickers:
            return "Ticker already exists"
        
        stock = yf.Ticker(ticker)
        try:
            info = stock.info
        except AttributeError: # If stock isn't valid, an attribute error should be raised
            info = []
    
        if len(info) > 0: # Try to verify ticker is real and get the relevant info
            items = {'ticker': ticker.upper(),
                       'exchange': info['fullExchangeName'],
                       'company_name': info['displayName'] if 'displayName' in info else info['shortName']} # I guess not all stocks have a long name?

            stock = self.sql.insert(table='stocks', items=items)
            return "Ticker added" #TODO This is literally not validating at all
        else:
            return "Ticker invalid" #TODO is this a good way to verify? No
    
    def update_stock(self): #TODO add update_stock
        pass
    
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
            
        stocks = self.sql.get(table='stocks', columns=columns)
        
        if tickers_only:
            tickers = [ticker[0] for ticker in stocks]
            return tickers
    
        else:
            return self.self._reformat_sqlite(stocks) #TODO test
    
    def get_stock(self, ticker:str):
        """Get an existing stock from ticker

        Args:
            ticker (str): Stock ticker

        Returns:
            dict: Single stock details
        """        
        filters = {'ticker': ticker}
        stock = self.sql.get(table='stocks',filters=filters) 
        if len(stock) > 0:
            return self._reformat_sqlite(stock)[0] #TODO test
        else:
            return "No stocks found"
        
    def remove_stock(self, ticker:str): #TODO add remove_stock
        pass
    
    # # STOCK PRICE ACTIONS # # 
    
    def add_stock_price(self, ticker:str, price:float, date:str=None): #TODO IF date is none use today #TODO maybe use stock_ids here? #TODO this won't handle the different game types 
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
        
        stock = self.sql.insert(table='stock_prices', items=items)
        return stock 
    
    def list_stock_prices(self, stock_id:str=None, date:str=None,): # List stock prices, allow some filtering 
        """List stock prices.

        Args:
            stock_id (str, optional): Filter by a stock ID. Defaults to None.
            date (str, optional): Filter by a date. Defaults to None.

        Returns:
            list: Stock price info
        """
        order = {'price_date': "DESC"}  # Sort by price date
        filters = {'stock_id': stock_id, 
                   'price_date': date}

        prices = self.sql.get(table='stock_prices',filters=filters, order=order) 
        prices = self._reformat_sqlite(prices) #TODO test
        return prices
    
    def get_stock_price(price_id:int): #TODO add get_stock_price
        pass
    
    def update_stock_prices(self): #TODO add docstring
        # THIS WILL NOT VALIDATE WHETHER IT IS THE END OF THE DAY OR NOT, THAT IS UP TO YOU TO DO!
        
        tickers = self.list_stocks(tickers_only=True) # Get all stock tickers currently in game
        prices = yf.Tickers(tickers).tickers
        for ticker, price in prices.items(): # update pricing
            price = price.info['regularMarketPrice']
            self.add_stock_price(ticker=ticker, price=price, date=_iso8601('date')) # Update pricing
    
    # # STOCK PICK ACTIONS # #
    
    def add_stock_pick(self, participant_id:int, stock_id:int,): # This is essentially putting in a buy order. End users should not be interacting with this directly 
        """Create stock pick

        Args:
            participant_id (int): Participant ID. Use get_participant_id() with user ID and game ID if you don't have it
            stock_id (int): Stock ID.

        Returns:
            unk: No idea
        """#TODO what does this return
        items = {'participation_id':participant_id,
                 'stock_id':stock_id,
                 'datetime_updated': _iso8601()}
        
        pick = self.sql.insert(table='stock_picks', items=items)
        return pick
    
    def list_stock_picks(self, status:str=None, participant_id:int=None): 
        """List stock picks.  Optionally, filter by a status or participant ID

        Args:
            status (str, optional): Filter by a status ( 'pending_buy', 'owned', 'pending_sell', 'sold'). Defaults to None.
            participant_id (int, optional): Filter by a participant ID. Defaults to None.

        Returns:
            list: List of stock picks
        """
        filters = {'pick_status': status, #TODO validate statuses
                   'participation_id': participant_id}

        picks = self.sql.get(table='stock_picks', filters=filters)
        return self._reformat_sqlite(picks)
    
    def get_stock_pick(self, pick_id:int):
        filters = {'pick_id': pick_id}
        pick = self.sql.get(table='stock_picks', filters=filters)
        return self._reformat_sqlite(pick)[0] #TODO test
    
    def update_stock_pick(self, pick_id:int, current_value:float,  shares:int=None, start_value:float=None,  status:str=None): #Update a single stock pick
        items = {'shares': shares,
                 'start_value': start_value,
                 'current_value': current_value,
                 'pick_status': status,
                 'datetime_updated': _iso8601()}
        
        filters = {'pick_id': pick_id}
        
        pick = self.sql.update(table="stock_picks", filters=filters, items=items)
        return pick # TODO add error handling
    
    def update_stock_picks(self, date:str, game_id:int=None): #TODO allow blank date to use latest
        #TODO implement game_id filtering
        pending_picks = self.list_stock_picks(status='pending_buy') #TODO handle pending_sell here too
        for pick in pending_picks: #TODO make sure a user doesn't have more than 10 stocks
            price = self.list_stock_prices(stock_id=pick['stock_id'],date=date)[0] #TODO handle no data
            game_participant = self.get_game_member(participant_id=pick['participant_id']) #This is also annoying
            game = self.get_game(game_id=game_participant['game_id']) #This is annoying #TODO validate stuff here since I have to get it anyway?
            buying_power = float(game['starting_money'] / game['total_picks']) # Amount available to buy this stock (starting money divided by picks)
            shares = buying_power / price['price'] # Total shares owned
            value = shares * price['price']
            self.update_stock_pick(pick_id=pick['id'],shares=shares, start_value=value, current_value=value, status='owned')
        
        all_picks = self.list_stock_picks(status='owned')
        for pick in all_picks:
            price = self.list_stock_prices(stock_id=pick['stock_id'],date=date)[0] #TODO handle no data
            value = pick['shares'] * price['price']
            self.update_stock_pick(pick_id=pick['id'], current_value=value)
        #TODO return something
            
    # # GAME PARTICIPATION ACTIONS # #
    def add_user_to_game(self, user_id:int, game_id:int):
        items = {'user_id':user_id, 
                 'game_id':game_id, 
                 'datetime_joined': _iso8601()}
        game = self.sql.insert(table='game_participants', items=items)
        if game['status'] == 'success':
            return game 
        
        else: #TODO Should this raise an error instead?
            reason = game['reason']
            if reason == 'SQLITE_CONSTRAINT_FOREIGNKEY':
                game['reason'] = 'Game ID or User ID is invalid'
            
            elif reason == 'SQLITE_CONSTRAINT_UNIQUE':
                game['reason'] = 'User has already been added to this game'

            return game # Return game with updated errors
    
        
    def remove_user_from_game(self, game_id:int, user_id:int): #TODO add remove_user_from_game
        pass
    
    def get_participant_id(self, user_id:int, game_id:int): # Will save time
        """Get a participant ID from user and game ID.

        Args:
            user_id (int): User ID.
            game_id (int): Game ID.

        Returns:
            int: Participant ID.
        """
        filters = {'user_id': user_id,
                   'game_id': game_id}
        participant = self.sql.get(table='game_participants', columns=['participation_id'], filters=filters) 
        return participant # Drill down 

    def list_game_members(self, game_id:int=None, user_id:int=None, status:str=None):
        
        if status and status not in ['pending', 'active', 'inactive']:
            raise ValueError('Invalid status!')
        
        filters = {'user_id': user_id,
                   'game_id': game_id,
                   'status':status}
        
        participants = self.sql.get(table='game_participants', columns=['*'], order={'game_id':'DESC'}, filters=filters) 
        return self._reformat_sqlite(participants)

    def get_game_member(self, participant_id:int): # Get game member info
        """Get participant information from ID

        Args:
            participant_id (int): Participant ID.

        Returns:
            dict: Game participant information
        """
        filters = {'participation_id': participant_id}
        participant = self.sql.get(table='game_participants', filters=filters) 
        return self._reformat_sqlite(participant)[0] #TODO test
    
    def update_game_info(self, game_id:int): #TODO add update_game_info #TODO update player portfolio values
        pass

    def get_all_game_members(self, game_id: int):
        """Get all participants with a game ID

        Args:
            game_id (int): The ID of the game to filter by
        
        Returns:
            list: List of game participants
        """
        filters = {'game_id': game_id}
        participants = self.sql.get(table="game_participants", filters=filters)
        return self._reformat_sqlite(participants)




# INTERFACE INTERACTIONS.  SHOULD EXPECT CRAP FROM USERS AND VALIDATE DATA
class Frontend: # This will be where a bot (like discord) interacts
    def __init__(self, database_name:str, owner_user_id:int, default_permissions:int=210):
        """For use with a discord bot or other frontend. 
        
        Provides  basic error handling, data validation, more user friendly commands, and more.

        Args:
            owner_user_id (int): User ID of the owner.  This user will be able to control everything.
            default_permissions (int, optional): Default permissions for new users. Defaults to 210. (Users can view and join games, but not create their own)
        """
        self.version = "0.0.1"
        self.backend = Backend(database_name)
        self.default_perms = default_permissions
        self.register(owner_user_id,owner_user_id) # Try to register user
        self.backend.update_user(user_id=owner_user_id, permissions=288)
        self.owner_id = owner_user_id
        pass
    
    # Game actions (Return information that is relevant to overall games)
    def new_game(self, user_id:int, name:str, start_date:str, end_date:str=None, starting_money:float=10000.00, pick_date:str=None, private_game:bool=False, total_picks:int=10, draft_mode:bool=False, sell_during_game:bool=False, update_frequency:str='daily'):
        """Create a new stock game!
        
        WARNING: If using realtime, expect issues

        Args:
            user_id (int): Game creators user ID
            name (str): Name for this game
            start_date (str): Start date in ISO8601 (YYYY-MM-DD)
            end_date (str, optional): End date ISO8601 (YYYY-MM-DD). Defaults to None.
            starting_money (float, optional): Starting money. Defaults to $10000.00.
            pick_date (str, optional): Date stocks must be picked by in ISO8601 (YYYY-MM-DD). Defaults to None (allow players to join anytime)
            private_game(bool, optional): Whether the game is private or not
            total_picks (int, optional): Amount of stocks each user picks. Defaults to 10.
            draft_mode (bool, optional): Whether multiple users can pick the same stock.  If enabled (players cannot pick the same stocks), pick date must be on or before start date Defaults to False.
            sell_during_game (bool, optional): Whether users can sell stocks during the game. Defaults to False.
            update_frequency (str, optional): How often prices should update ('daily', 'hourly', 'minute', 'realtime'). Defaults to 'daily'.
            
        Returns:
            str: Game creation status
        """
        #TODO Should the user be automatically added to their own game? Probably?
        # Data validation
        #TODO add validation for update_frequency
        try: # Validate dates are correct format
            startdate = datetime.strptime(start_date, "%Y-%m-%d").date()
            enddate = datetime.strptime(end_date, "%Y-%m-%d").date()
            #pickdate = datetime.strptime(pick_date, "%Y-%m-%d").date() #TODO add me!
        except: #TODO find specific exceptions
            return "Error! Start or end date format is invalid!"
            
        # Date checks
        if datetime.strptime(start_date, "%Y-%m-%d").date() < date.today():
            return "Error! Start date must not be in the past!"
        
        elif end_date != None and datetime.strptime(start_date, "%Y-%m-%d").date() > datetime.strptime(end_date, "%Y-%m-%d").date():
            return "Error! End date cannot be before start date!"
        
        try: # Try to get user
            user = self.backend.get_user(user_id=user_id)
            
        except KeyError: # User doesn't exist, create.
            try:
                self.backend.add_user(user_id=user_id, display_name=user_id, permissions=self.default_perms) # Try to create a user with no name #TODO log a warning that the user was created with no name
                user = self.backend.get_user(user_id=user_id)
            
            except Exception as e:
                raise e
        
        permissions = user['permissions']
        if permissions - 200 < 0 or permissions - 200 < 19: # User is inactive, banned, or not allowed to create game #TODO this won't work with custom perms!
            reason = "banned" if permissions < 100 else "not allowed to create games!"
            return f"Error! User is {reason}" 
    
        try:  # User is allowed to create games
            self.backend.add_game(
                user_id=int(user_id), 
                name=str(name), 
                start_date=str(start_date), 
                end_date=str(end_date), 
                starting_money=float(starting_money), 
                total_picks=int(total_picks), 
                pick_date=str(pick_date), 
                draft_mode=bool(draft_mode), 
                sell_during_game=bool(sell_during_game), 
                update_frequency=str(update_frequency)
                )
            
        except Exception as e: #TODO find errors
            return e
    
    def list_games(self): #TODO allow filtering
        """List all games.

        Returns:
            list: List of games
        """
        games = self.backend.list_games()
        return games
    
    
    def game_info(self, game_id:int): 
        """Get information about a specific game.

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
        user = self.backend.add_user(user_id=user_id ,display_name=username, permissions=self.default_perms)
        if user['status'] == 'success':
            return "Registered"
        
        elif user['reason'] == 'SQLITE_CONSTRAINT_PRIMARYKEY':
            return "User already registered"
        
        else: #TODO add logging here
            return "Unknown error occurred while registering user"

    def change_name(self, user_id:int, name:str):
        """Change your display name (nickname).

        Args:
            user_id (int): User ID.
            name (str): New name.

        Returns:
            unk: NO idea
        """#TODO what does this reurn
        user = self.backend.update_user(user_id=int(user_id), display_name=str(name))
        return user #TODO return an error instead
    
    def join_game(self, user_id:int, game_id:int):
        """Join a game.

        Args:
            user_id (int): User ID.
            game_id (int): Game ID.

        Returns:
            unk: I have no idea
        """# TODO what does this return?
        #TODO check permissions before running
        game = self.backend.add_user_to_game(user_id=int(user_id), game_id=int(game_id))
        return game
    
    def my_games(self, user_id:int): 
        games = self.backend.list_game_members(user_id=user_id)
        return games #TODO get a friendly name and game name?
    
    def buy_stock(self, user_id:int, game_id:int, ticker:str):
        part_id = self.backend.get_participant_id(user_id=user_id, game_id=game_id)
        stock = self.backend.get_stock(ticker=str(ticker)) # Try to get the stock 
        if stock == "No stocks found": # Stock not yet added:
            self.backend.add_stock(ticker=str(ticker)) #TODO handle invalid tickers!
            stock = self.backend.get_stock(ticker=str(ticker)) #TODO clean this up
        
        pick = self.backend.add_stock_pick(participant_id=part_id, stock_id=stock['id']) # Add the pick
        return pick 
    
    def sell_stock(self, user_id:int, game_id:int, ticker:str): # Will also allow for cancelling an order #TODO add sell_stock
        pass
    
    def my_stocks(self, user_id:int, game_id:int):
        """Get your stocks for a specific game.

        Args:
            user_id (int): User ID.
            game_id (int): Game ID.

        Returns:
            list: Stocks both owned and pending
        """
        #TODO hide sold stocks
        part_id = self.backend.get_participant_id(user_id=user_id, game_id=game_id) # TODO error validation
        picks = self.backend.list_stock_picks(participant_id=part_id)
        return picks
    
    def start_draft(user_id:int, game_id:int): #TODO add
        pass
    
    def update(self, user_id:int, game_id:int=None, force:bool=False): # Update games or a specific game #TODO add docstring
        #TODO VALIDATION!!!!!!!!!
        if user_id != self.owner_id:
            return "You do not have permission to do this"
        
        self.backend.update_stock_prices() # Update stock prices
        self.backend.update_stock_picks(date=self.backend._iso8601('date')) # Update picks
        #TODO update account values!
        #TODO update the rest!
        
    def manage_game(self, user_id:int,): #TODO allow game management here, including approving pending users
        pass
    
    def approve_game_users(self, user_id:int):
        pass

    def get_all_participants(self, game_id: int):
        return self.backend.get_all_game_members(game_id=game_id)

# TESTING
if __name__ == "__main__":
    DB_NAME = os.getenv('DB_NAME')
    OWNER = os.getenv("OWNER") # Set owner ID from env
    game = Frontend(database_name=DB_NAME, owner_user_id=OWNER) # Create frontend 
    # Misc tests
    print(game.backend.list_users(ids_only=True)) # List users from the backend
    #create = game.new_game(user_id=OWNER, name="TestGame", start_date="2025-05-06", end_date="2025-05-30") # Try to create game
    print(game.join_game(user_id=OWNER,game_id=1)) # Try to join a game
    print(game.my_games(user_id=OWNER)) # Try to list games you are joined to
    
    
    print(game.list_games()) # Print list of games
    print(game.buy_stock(OWNER, 1, 'MSFT')) # Try to purchase stock
    print(game.update(OWNER)) # Try to update
    pass