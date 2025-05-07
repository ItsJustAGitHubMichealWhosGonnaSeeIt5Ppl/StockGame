import re
import yfinance as yf
import logging
import os
from datetime import datetime, date
from helpers.sqlhelper import SqlHelper, _iso8601
from sqlite_creator_real import create as create_db

logging.basicConfig(filename='stock_game.log', 
                    level=logging.WARNING, 
                    format='%(asctime)s %(levelname)-8s %(message)s', 
                    datefmt='%Y-%m-%d %H:%M:%S')

version = "0.0.2" #TODO should frontend and backend have different versions?

class Backend:
    # Raise Exceptions if bad data is passed in
    # Return a status/error if the database returns an error
    # Most of these expect that the data being sent has been checked or otherwise verified.  End users should not interact directly with this
    def __init__(self, db_name:str):
        """Backend
        """
        create_db(db_name) # Try to create DB
        self.sql = SqlHelper(db_name)
        # Try to create DB
        self.version = "0.0.2"
    
    def _reformat_sqlite(self, data:list, table:str, custom_keys:dict=None): # Reformat data from the database into more friendly 
        """Reformat the data from SQLite database to make it easier to work with

        Args:
            data (list): Data from SQLite
            table (str): The table that data is being extracted from
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
            'owner_user_id': 'owner',
            'start_money': 'starting_money',
            'pick_count':'total_picks',
            'draft_mode':'exclusive_picks',
            'allow_selling':'sell_during_game',
            'update_frequency':'update_frequency',
            # Participants
            'datetime_joined': 'joined',
            # Stocks
            'company_name': 'name',
            # Users
            'display_name': 'username',
            }
            
            if table == 'users': # Handle specific items that need to be added 
                keys['user_id'] = 'id'
                
            elif table == 'games':
                keys['game_id'] = 'id'
                
            elif table == 'stock_picks':
                keys['pick_id'] = 'id'
                keys['participation_id'] = 'participant_id'
                
            elif table == 'game_participants':
                keys['participation_id'] = 'id'
                
            elif table == 'stock_prices':
                keys['price_id'] = 'id'

            elif table == 'stocks':
                keys['stock_id'] = 'id'
                
        for raw_data in data: # Reformat data from SQLite
            item = {}
            for key, val in raw_data.items(): 
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
        
        Returns:
            dict: Result/status
        """#TODO Add user permissions docstring
        items = {'user_id': user_id, 
                 'display_name':display_name if display_name else user_id, # Set display name to user ID if there isnt one supplied
                 'permissions': permissions,
                 'datetime_created': _iso8601()}
        
        user = self.sql.insert(table='users', items=items)
        return user
        
    def remove_user(self, user_id:int):
        delete = self.sql.delete(table='users', filters={'user_id': user_id})
        return delete
    
    def list_users(self, ids_only:bool=False):
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
            return self._reformat_sqlite(users, table='users')
        
    def get_user(self, user_id:int):
        """Get a single user by ID

        Args:
            user_id (int): User ID.

        Returns:
            dict: User information
        """
        filters = {'user_id': user_id}
        user = self.sql.get(table='users', filters=filters)
        return self._reformat_sqlite(user, table='users')[0] #TODO add error handling
    
    def update_user(self, user_id:int, display_name:str=None, permissions:str=None): 
        items = {'display_name': display_name,
                 'permissions': permissions}
        
        filters = {'user_id': user_id}
        self.sql.update(table="users", filters=filters, items=items)
    
    # # GAME MANAGEMENT ACTIONS # #
    
    def add_game(self, owner:int, name:str, start_date:str, end_date:str=None, starting_money:float=10000.00, pick_date:str=None, private_game:bool=False, total_picks:int=10, draft_mode:bool=False, sell_during_game:bool=False, update_frequency:str='daily'):
        """Create a new stock game!
        
        WARNING: If using realtime, expect issues

        Args:
            owner (int): ID of game creator/owner
            name (str): Name for this game
            start_date (str): Start date in ISO8601 (YYYY-MM-DD)
            end_date (str, optional): End date ISO8601 (YYYY-MM-DD). Defaults to None.
            starting_money (float, optional): Starting money. Defaults to $10000.00.
            pick_date (str, optional): Date stocks must be picked by in ISO8601 (YYYY-MM-DD). Defaults to None (allow players to join anytime)
            private_game(bool, optional): Whether the game is private or not
            total_picks (int, optional): Amount of stocks each user picks. Defaults to 10.
            draft_mode (bool, optional): Whether multiple users can pick the same stock. Pick date must be on or before start date. Defaults to False.
            sell_during_game (bool, optional): Whether users can sell stocks during the game. Defaults to False.
            update_frequency (str, optional): How often prices should update ('daily', 'hourly', 'minute', 'realtime'). Defaults to 'daily'.
            
        Returns:
            str: Game creation status
        """
        #TODO should all errors be checked at once?
        if update_frequency not in ['daily', 'hourly', 'minute', 'realtime']:
            raise ValueError(f'{update_frequency} is not a valid updated frequency.')
        
        if draft_mode and datetime.strptime(start_date, "%Y-%m-%d").date() < datetime.strptime(pick_date, "%Y-%m-%d").date():
            raise ValueError("Pick date must be before start date when draft mode is enabled.")
            
        elif starting_money < 1.0:
            raise ValueError("Starting money must be atleast 1.")
        
        elif total_picks < 1:
            raise ValueError("Stock picks must be atleast 1.")
        
        elif end_date != None and datetime.strptime(start_date, "%Y-%m-%d").date() > datetime.strptime(end_date, "%Y-%m-%d").date():
            raise ValueError("End date cannot be before start date.")
        
        items = {'name': name,
                 'owner_user_id': owner,
                 'start_money': starting_money,
                 'pick_count': total_picks,
                 'draft_mode': draft_mode,
                 'pick_date': pick_date,
                 'private_game': private_game,
                 'allow_selling': sell_during_game,
                 'update_frequency': update_frequency,
                 'start_date': start_date,
                 'end_date': end_date,
                 'datetime_created': _iso8601()}

        game = self.sql.insert(table='games', items=items)
        return game #TODO error catching and checking
    
    def list_games(self, show_private:bool=False): # List all games
        """List all games

        Args:
            show_private (bool, optional): Whether to show private games. Defaults to False (no).

        Returns:
            list: List of games
        """
        filters = {'private_game': show_private if show_private == False else None} #TODO This is a bad solution
        games = self.sql.get(table='games',filters=filters) 
        return self._reformat_sqlite(games, table='games') # Send games data to be reformatted
    
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
            game = self._reformat_sqlite(game, table='games')[0]
            return game
        
    def update_game(self, game_id:int, owner:int=None, name:str=None, start_date:str=None, end_date:str=None, status:str=None, starting_money:float=None, pick_date:str=None, private_game:bool=None, total_picks:int=None, draft_mode:bool=None, sell_during_game:bool=None, update_frequency:str=None):
        #TODO only allow starting money, picks to be edited before game has started
        game = self.get_game(game_id=game_id)
        if len(game) == 0:
            raise ValueError("Invalid Game ID")
        
        items = {'name': name,
            'owner_user_id': owner,
            'start_money': starting_money,
            'pick_count': total_picks,
            'draft_mode': draft_mode,
            'pick_date': pick_date,
            'private_game': private_game,
            'allow_selling': sell_during_game,
            'status': status,
            'update_frequency': update_frequency,
            'start_date': start_date,
            'end_date': end_date,  # is this needed?, no but I like it.
            }
        
        update = self.sql.update(table='games', filters={'game_id': game_id}, items=items)
        return update
    
    def update_games(self): # Update existing games
        games = self.list_games(show_private=True)
        for game in games: #TODO add log here
            if game['status'] == 'open' and datetime.strptime(game['start_date'], "%Y-%m-%d").date() <= datetime.strptime(_iso8601('date'), "%Y-%m-%d").date(): # Set games to active
                self.update_game(game_id=game['id'], status='active')
            
            if game['status'] == 'active' and game['end_date'] and datetime.strptime(game['end_date'], "%Y-%m-%d").date() < datetime.strptime(_iso8601('date'), "%Y-%m-%d").date(): #Game has ended
                self.update_game(game_id=game['id'], status='ended')
            
            
    
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
            return stock
        else:
            return "Ticker invalid" #TODO is this a good way to verify? No
    
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
            tickers = [ticker['ticker'] for ticker in stocks]
            return tickers
    
        else:
            return self._reformat_sqlite(stocks, table='stocks')
    
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
            return self._reformat_sqlite(stock, table='stocks')[0]
        else:
            return stock
        
    def remove_stock(self, ticker:str): #TODO add remove_stock
        pass
    
    # # STOCK PRICE ACTIONS # # 
    
    def add_stock_price(self, ticker:str, price:float, datetime:str): #TODO maybe use stock_ids here?
        """Add price data for a stock (should be done at close)

        Args:
            ticker (str): Stock ticker
            price (float): Stock price 
            datetime (str): ISO8601 (YYYY-MM-DD)
        """
        #AI IS FUCKING STUPID AND CLAIMS WE ABSOLUTELY NEED THE STOCK_ID TO BE ITS OWN THING, SO HERE IS THE SHIT WORKAROUND. FUCK YOU AI
        stock_id = self.get_stock(ticker)['id'] #TODO add some sort of error catching here
        
        items = {'stock_id':int(stock_id), 
                 'price': float(price), 
                 'datetime': str(datetime)}
        
        stock = self.sql.insert(table='stock_prices', items=items)
        return stock 
    
    def list_stock_prices(self, stock_id:str=None, date:str=None): # List stock prices, allow some filtering 
        """List stock prices.

        Args:
            stock_id (str, optional): Filter by a stock ID. Defaults to None.
            date (str, optional): Filter by a date. Defaults to None.

        Returns:
            list: Stock price info
        """
        order = {'datetime': "DESC"}  # Sort by price date
        filters = {'stock_id': stock_id, 
                   'datetime': date}

        prices = self.sql.get(table='stock_prices',filters=filters, order=order) 
        prices = self._reformat_sqlite(prices, table='stock_prices')
        return prices
    
    def get_stock_price(price_id:int): #TODO add get_stock_price
        pass
    
    def update_stock_prices(self):
        """Update stock prices
        
        Will skip stocks that have already been updated today
        """
        # THIS WILL NOT VALIDATE WHETHER IT IS THE END OF THE DAY OR NOT, THAT IS UP TO YOU TO DO!
        today = _iso8601('date')
        
        updated = [s_id['stock_id'] for s_id in self.list_stock_prices(date=today)] # Skip stocks that have already been updated
        tickers = self.list_stocks() # Get all stock tickers currently in game
        tickers = [ticker for ticker in tickers if ticker['id'] not in updated]
        if len(tickers) > 0:
            
            prices = yf.Tickers(tickers).tickers
            for ticker, price in prices.items(): # update pricing
                price = price.info['regularMarketPrice']
                self.add_stock_price(ticker=ticker, price=price, datetime=today) # Update pricing
    
    # # STOCK PICK ACTIONS # #
    
    def add_stock_pick(self, participant_id:int, stock_id:int,): # This is essentially putting in a buy order. End users should not be interacting with this directly 
        """Create stock pick.

        Args:
            participant_id (int): Participant ID. Use get_participant_id() with user ID and game ID if you don't have it
            stock_id (int): Stock ID.

        Returns:
            unk: No idea
        """#TODO what does this return
        player = self.get_game_member(participant_id)
        if player['status'] != 'active':
            raise ValueError("User is not active in game.")
        
        game = self.get_game(game_id=player['game_id']) #TODO validate that game hasn't already started?
        
        stocks = self.list_stock_picks(participant_id=participant_id)
        
        if len(stocks) >= game['total_picks']: #TODO this does not account for stocks that have been sold
            raise ValueError("Maximum stocks selected.")
        
        items = {'participation_id':participant_id,
                 'stock_id':stock_id,
                 'datetime_updated': _iso8601()}
        
        pick = self.sql.insert(table='stock_picks', items=items)
        return pick
    
    def list_stock_picks(self, participant_id:int=None, status:str=None, stock_id:int=None): 
        """List stock picks.  Optionally, filter by a status or participant ID

        Args:
            participant_id (int, optional): Filter by a participant ID. Defaults to None.
            status (str, optional): Filter by a status ('pending_buy', 'owned', 'pending_sell', 'sold'). Defaults to None.

        Returns:
            list: List of stock picks
        """
        if status and status not in ['pending_buy', 'owned', 'pending_sell', 'sold']:
            raise ValueError(f'Status {status} is not valid!')
        
        filters = {'status': status,
                   'participation_id': participant_id,
                   'stock_id': stock_id}

        picks = self.sql.get(table='stock_picks', filters=filters)
        return self._reformat_sqlite(picks, table='stock_picks')
    
    def get_stock_pick(self, pick_id:int):
        filters = {'pick_id': pick_id}
        pick = self.sql.get(table='stock_picks', filters=filters)
        return self._reformat_sqlite(pick, table='stock_picks')[0]
    
    def update_stock_pick(self, pick_id:int, current_value:float,  shares:int=None, start_value:float=None,  status:str=None): #Update a single stock pick
        items = {'shares': shares,
                 'start_value': start_value,
                 'current_value': current_value,
                 'status': status,
                 'datetime_updated': _iso8601()}
        
        filters = {'pick_id': pick_id}
        
        pick = self.sql.update(table="stock_picks", filters=filters, items=items)
        return pick # TODO add error handling
    
    def remove_stock_pick(self, pick_id:int):
        #TODO more validation?
        delete = self.sql.delete(table='stock_picks', filters={'pick_id': pick_id, 'status': 'pending_buy'})
        return delete
    
    def update_stock_picks(self, date:str, game_id:int=None): #TODO allow blank date to use latest
        #TODO implement game_id filtering
        pending_picks = self.list_stock_picks(status='pending_buy') #TODO handle pending_sell here too
        for pick in pending_picks:
            game_participant = self.get_game_member(participant_id=pick['participant_id']) #This is also annoying
            game = self.get_game(game_id=game_participant['game_id']) #This is annoying
            if game['status'] != 'active': # Won't buy stocks for games that have not started
                continue #TODO log skipped games
            
            price = self.list_stock_prices(stock_id=pick['stock_id'],date=date)[0] #TODO handle no data #TODO Set to date or datetime depending on what the update frequency is. 
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
    def add_user_to_game(self, user_id:int, game_id:int, name:str=None):
        items = {'user_id':user_id, 
                 'game_id':game_id,
                 'name': name,
                 'datetime_joined': _iso8601()}
        
        game = self.sql.insert(table='game_participants', items=items)
        if game['status'] == 'success':
            return game 
        
        else:
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
        if len(participant) > 0: 
            return participant[0]['participation_id']
        else:
            return 'Not found' #TODO should this be more clear?

    def list_game_members(self, game_id:int=None, user_id:int=None, status:str=None, sort_by_value:bool=False): 
        
        if status and status not in ['pending', 'active', 'inactive']:
            raise ValueError('Invalid status!')
        
        filters = {'user_id': user_id,
                   'game_id': game_id,
                   'status':status}
        
        order={'game_id':'DESC'}
        if sort_by_value:
            order['current_value'] = 'DESC'
        
        participants = self.sql.get(table='game_participants', columns=['*'], order=order, filters=filters, ) 
        return self._reformat_sqlite(participants, table='game_participants')

    def get_game_member(self, participant_id:int): # Get game member info
        """Get participant information from ID

        Args:
            participant_id (int): Participant ID.

        Returns:
            dict: Game participant information
        """
        filters = {'participation_id': participant_id}
        participant = self.sql.get(table='game_participants', filters=filters) 
        return self._reformat_sqlite(participant, table='game_participants')[0]
    
    def update_game_member(self, participant_id:int, name:str=None, status:str=None, current_value:float=None):  
        items = {'name': name,
                 'status': status,
                 'current_value': current_value,
                 'datetime_updated': _iso8601()}
        
        game = self.sql.update(table='game_participants', filters={'participation_id': participant_id}, items=items)
        return game

    def update_game_members(self, game_id:int):
        game = self.get_game(game_id=game_id)
        if game['status'] != 'active':
            return "Game not active"
        members = self.list_game_members(game_id=game['id'])
        for member in members:
            portfolio_value = 0.0
            picks = self.list_stock_picks(participant_id=member['id'], status='owned')
            for pick in picks:
                portfolio_value += pick['current_value']
            update = self.update_game_member(participant_id=member['id'], current_value=portfolio_value)
            pass
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
    
    def _user_owns_game(self, user_id:int, game_id:int): # Check if a user owns a specific game
        """Check whether a user owns a specific game

        Args:
            user_id (int): User ID.
            game_id (int): Game ID.

        Returns:
            bool: True if owned, False if not.
        """
        game = self.backend.get_game(game_id=game_id)
        if game['owner'] != user_id:
            return False
        else:
            return True
    
    # Game actions (Return information that is relevant to overall games)
    def new_game(self, owner:int, name:str, start_date:str, end_date:str=None, starting_money:float=10000.00, pick_date:str=None, private_game:bool=False, total_picks:int=10, draft_mode:bool=False, sell_during_game:bool=False, update_frequency:str='daily'):
        """Create a new stock game!
        
        WARNING: If using realtime, expect issues

        Args:
            owner (int): Game creators user ID
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
        permissions = user['permissions'] # Check that user is even allowed to create a game
        if permissions - 200 < 0 or permissions - 200 < 19: # User is inactive, banned, or not allowed to create game #TODO this won't work with custom perms!
            reason = "banned" if permissions < 100 else "not allowed to create games!"
            return f"User is {reason}" 
        #TODO Should the user be automatically added to their own game? Probably?
        # Data validation
        try: # Validate dates are correct format
            startdate = datetime.strptime(start_date, "%Y-%m-%d").date()
            enddate = datetime.strptime(end_date, "%Y-%m-%d").date()
            if pick_date:
                pickdate = datetime.strptime(pick_date, "%Y-%m-%d").date()
        except: #TODO find specific exceptions
            return "Date format is invalid!"
            
        # Date checks
        if datetime.strptime(start_date, "%Y-%m-%d").date() < date.today(): # This is done in the frontend because technically a game could be started in the past
            return "Start date must not be in the past!"
    
        try: # Try to get user
            user = self.backend.get_user(user_id=owner)
            
        except KeyError: # User doesn't exist, create.
            try:
                self.backend.add_user(user_id=owner, display_name=owner, permissions=self.default_perms) # Try to create a user with no name #TODO log a warning that the user was created with no name
                user = self.backend.get_user(user_id=owner)
            
            except Exception as e:
                return e
    
        try:  # Create game
            self.backend.add_game(
                owner=int(owner),
                name=str(name), 
                start_date=str(start_date), 
                end_date=str(end_date), 
                starting_money=float(starting_money), 
                total_picks=int(total_picks), 
                pick_date=str(pick_date), 
                draft_mode=bool(draft_mode),
                private_game=bool(private_game),
                sell_during_game=bool(sell_during_game), 
                update_frequency=str(update_frequency)
                )
            
        except Exception as e: #TODO find errors
            return e
    
    def list_games(self, show_private:bool=False): 
        """List games.
        
        Args:
            show_private (bool, optional): Whether to show private games. Defaults to False.
        
        Returns:
            list: List of games
        """
        games = self.backend.list_games(show_private=show_private)
        return games
    
    def game_info(self, game_id:int): 
        """Get information about a specific game.

        Args:
            game_id (int): Game ID

        Returns:
            dict: Game information
        """
        game = self.backend.get_game(game_id=int(game_id))
        return game
    
    # User actions (Return information that is relevant to a specific user)
    
    def register(self, user_id:int, username:str):
        """Register user to allow gameplay

        Args:
            user_id (int): User ID.
            username (str): Display name/username

        Returns:
            dict: Status/result
        """
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
            dict: Status/result
        """
        user = self.backend.update_user(user_id=int(user_id), display_name=str(name))
        return user
    
    def join_game(self, user_id:int, game_id:int, name:str=None):
        """Join a game.

        Args:
            user_id (int): User ID.
            game_id (int): Game ID.
            name (str, optional): Team name/nickname for game.

        Returns:
            dict: Status/result
        """
        #TODO check permissions before running
        game = self.backend.add_user_to_game(user_id=int(user_id), game_id=int(game_id), name=str(name))
        return game
    
    def my_games(self, user_id:int):
        """Get a list of your current games

        Args:
            user_id (int): User ID.

        Returns:
            list: Your current games
        """
        games = self.backend.list_game_members(user_id=int(user_id))
        return games #TODO get a friendly name and game name?
    
    def buy_stock(self, user_id:int, game_id:int, ticker:str):
        """Add a stock pick (buy a stock).

        Args:
            user_id (int): User ID.
            game_id (int): Game ID.
            ticker (str): Ticker.

        Returns:
            dict: Status/result
        """
        part_id = self.backend.get_participant_id(user_id=user_id, game_id=game_id)
        stock = self.backend.get_stock(ticker=str(ticker)) # Try to get the stock 
        if len(stock) ==  0: # Stock not yet added:
            add = self.backend.add_stock(ticker=str(ticker)) 
            if add == 'Ticker invalid':
                return add
            stock = self.backend.get_stock(ticker=str(ticker))
        try:
            pick = self.backend.add_stock_pick(participant_id=part_id, stock_id=stock['id']) # Add the pick
        except ValueError as e:
            pick = e
            
        return pick 
    
    def sell_stock(self, user_id:int, game_id:int, ticker:str): # Will also allow for cancelling an order #TODO add sell_stock
        pass
    
    def remove_pick(self, user_id:int, game_id:int, ticker:str): # Remove a stock pick
        """Remove a stock pick. Status must be pending, cannot remove already owned stocks.

        Args:
            user_id (int): User ID.
            game_id (int): Game ID.
            ticker (str): Ticker.

        Returns:
            dict: Status/result
        """
        participant = self.backend.get_participant_id(user_id=user_id, game_id=game_id) #TODO check for errors
        stock_id = self.backend.get_stock(ticker=ticker)
        picks = self.backend.list_stock_picks(participant_id=participant['id'], status='pending_buy', stock_id=stock_id['id'])
        if len(picks) > 0:
            return self.backend.remove_stock_pick(pick_id=picks['id'])
        else:
            return "Unable to remove stock" #TODO add a more detailed reason here
    
    def my_stocks(self, user_id:int, game_id:int, show_pending:bool=True, show_sold:bool=False):
        """Get your stocks for a specific game.

        Args:
            user_id (int): User ID.
            game_id (int): Game ID.
            show_pending (bool, optional): Whether to show pending purchases. Defaults to False (no).
            show_sold (bool, optional): Whether to sold stocks. Defaults to False (no).

        Returns:
            list: Stocks both owned and pending
        """#TODO implement pending and sold
        part_id = self.backend.get_participant_id(user_id=user_id, game_id=game_id)
        if part_id == 'Not found':
            return part_id
        picks = self.backend.list_stock_picks(participant_id=part_id)
        return picks
    
    def start_draft(user_id:int, game_id:int): #TODO add
        pass
    
    def update(self, user_id:int, game_id:int=None, force:bool=False): # Update games or a specific game #TODO make game_id actually do something #TODO add docstring
        #TODO VALIDATION!!!!!!!!!
        if user_id != self.owner_id:
            return "You do not have permission to do this"
        self.backend.update_games() # Sets game statuses
        self.backend.update_stock_prices() # Update stock prices #TODO only works with daily update for now
        self.backend.update_stock_picks(date=_iso8601('date')) # Update picks 
        
        if game_id: #Update account values
            games = [self.backend.get_game(game_id)]
        else:
            games = self.backend.list_games(show_private=True)
        
        for game in games: 
            self.backend.update_game_members(game_id=game['id'])
        
        
    def manage_game(self, user_id:int, game_id:int, owner:int=None, name:str=None, start_date:str=None, end_date:str=None, status:str=None, starting_money:float=None, pick_date:str=None, private_game:bool=None, total_picks:int=None, draft_mode:bool=None, sell_during_game:bool=None, update_frequency:str=None):
        """Update/Manage an existing game.
        
        start_date, starting_money, pick_date, total_picks, draft_mode, sell_during_game cannot be changed once a game has started

        Args:
            user_id (int): User ID.
            game_id (int): Game ID.
            owner (int): Game owner user ID (allows changing).
            name (str): Name for this game. 
            start_date (str): Start date in ISO8601 (YYYY-MM-DD). Cannot be changed once game has started.
            end_date (str, optional): End date ISO8601 (YYYY-MM-DD). 
            status (str, optional): Game Status. 
            starting_money (float, optional): Starting money. Cannot be changed once game has started.
            pick_date (str, optional): Date stocks must be picked by in ISO8601 (YYYY-MM-DD). Cannot be changed once game has started.
            private_game(bool, optional): Whether the game is private or not. 
            total_picks (int, optional): Amount of stocks each user picks. Cannot be changed once game has started.
            draft_mode (bool, optional): Whether multiple users can pick the same stock. Pick date must be on or before start date. Cannot be changed once game has started.
            sell_during_game (bool, optional): Whether users can sell stocks during the game. Defaults to False. Cannot be changed once game has started.
            update_frequency (str, optional): How often prices should update ('daily', 'hourly', 'minute', 'realtime').

        Returns:
            dict: Status/result
        """
        if not self._user_owns_game(user_id=user_id, game_id=game_id):
            return "You do not have permission to update this game"
        
        if (start_date or starting_money or pick_date or total_picks or draft_mode or sell_during_game) and datetime.strptime(game['start_date'], "%Y-%m-%d").date() < datetime.strptime(_iso8601(), "%Y-%m-%d").date(): # Start date has passed
            return "Cannot make changes to start_date, starting_money, pick_date, total_picks, draft_mode, sell_during_game once game has started"
            
        update = self.backend.update_game(game_id=game_id, owner=owner, name=name, start_date=start_date, end_date=end_date, status=status, starting_money=starting_money, pick_date=pick_date, private_game=private_game, total_picks=total_picks, draft_mode=draft_mode, sell_during_game=sell_during_game, update_frequency=update_frequency)
        return update
    
    def pending_game_users(self, user_id:int, game_id:int):
        """Get a list of pending users for private games

        Args:
            user_id (int): User ID.
            game_id (int): Game ID.

        Returns:
            list: Pending users (including participant ID)
        """
        if not self._user_owns_game(user_id=user_id, game_id=game_id):
            return "You do not have permission to manage this game"
        
        users = self.backend.list_game_members(game_id=game_id, status='pending')
        return users
        
    def approve_game_users(self, user_id:int, participant_id:int):
        """Approve/add a user to private game

        Args:
            user_id (int): User ID (command runner).
            participant_id (int): Participant ID (get with pending_game_users).

        Returns:
            dict: status
        """
        user = self.backend.get_game_member(participant_id=participant_id)
        if not self._user_owns_game(user_id=user_id, game_id=user['game_id']):
            return "You do not have permission to manage this game"
        
        user = self.backend.update_game_member(participant_id=participant_id, status='active')
        return user
    
    def leaderboard(self, game_id:int):
        game = self.backend.list_game_members(game_id=game_id, sort_by_value=True)
        return game
    
    
# TESTING
if __name__ == "__main__":
    test_users = [111, 222, 333, 444, 555, 666]
    test_stocks = ['MSFT', 'SNAP', 'GME', 'COST', 'NVDA', 'MSTR', 'CSCO', 'IBM', 'GE', 'BKNG']
    test_stocks2 = ['MSFT', 'SNAP', 'UBER', 'COST', 'AMD', 'ADBE', 'CSCO', 'IBM', 'GE', 'PEP']
    DB_NAME = os.getenv('DB_NAME')
    OWNER = os.getenv("OWNER") # Set owner ID from env
    game = Frontend(database_name=DB_NAME, owner_user_id=OWNER) # Create frontend 
    #create = game.new_game(user_id=OWNER, name="TestGame", start_date="2025-05-06", end_date="2025-05-30") # Try to create game
    for user in test_users: # Add some random users
        print(game.register(user_id=user, username=str(user)))
        game.join_game(user_id=user,game_id=1)
        for stock in test_stocks2: # Buy some stocks
            game.buy_stock(user, 1, stock)
    print(game.backend.list_users(ids_only=True)) # List users from the backend
    print(game.list_games()) # Print list of games
    print(game.join_game(user_id=OWNER,game_id=1)) # Try to join a game
    print(game.my_games(user_id=OWNER)) # Try to list games you are joined to
    
    for stock in test_stocks: # Buy stocks
        print(f'BUY {stock}! {game.buy_stock(OWNER, 1, stock)}') # Try to purchase stock
    
    print(f'my stocks: {game.my_stocks(user_id=OWNER, game_id=1)}')
    print(game.update(OWNER)) # Try to update
    leaders = game.leaderboard(game_id=1)
    print([info for info in leaders])
    pass