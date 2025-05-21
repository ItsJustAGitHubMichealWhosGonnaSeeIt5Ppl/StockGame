import re
import yfinance as yf #TODO find alternative to yfinance since it seems to have issues https://docs.alpaca.markets/docs/about-market-data-api
import logging
import os
from datetime import datetime, timedelta
import pytz
from helpers.sqlhelper import SqlHelper, _iso8601
from typing import Optional
from stock_datatypes import Status, Games

### Methods (in order)
## add (create)
# Return nothing if successful

## get
# Raise error if the response is not 1 user

## get_many (list)
# Return 0+ items
# Raise error if search fails

## update
# Return nothing if successful

## delete
# Return nothing if successful

#TODO implement custom types
from sqlite_creator_real import create as create_db

version = "???" #TODO should frontend and backend have different versions?

class Backend:
    # Raise Exceptions if bad data is passed in
    # Most of these expect that the data being sent has been checked or otherwise verified.  End users should not interact directly with this
    def __init__(self, db_name:str):
        """Backend class
        
        The backend only performs basic validation to confirm that invalid information is not being sent to the database.  Things like prevening a user from joining a game that has already started, etc. are handled in `Frontend()`
        
        Updating stock prices, picks, etc. are handled in `GameLogic()`
        
        Args:
            db_name (str): Database name.
        """
        create_db(db_name) # Try to create DB
        self.logger = logging.getLogger('StockBackend')
        self.sql = SqlHelper(db_name)
        
    # # INTERNAL # #
    def _single_get(self, table:str, resp:Status)-> dict: # Handle single gets
        #TODO add Literal for table
        if table == 'users':
            ubj_str = 'user'
        elif table == 'games':
            ubj_str = 'game'
        elif table == 'stocks':
            ubj_str = 'stock'
        elif table == 'stock_prices':
            ubj_str = 'stock price'
        elif table == 'stock_picks':
            ubj_str = 'stock pick'
        elif table == 'game_participants':
            ubj_str = 'game participant'
        else:
            raise ValueError(f'Invalid `table` {table}.')
        
        if resp['status'] == 'success':
            assert isinstance(resp['result'], tuple)
            if len(resp['result']) == 1: # Single object (expected)
                return self._reformat_sqlite(resp['result'], table=table)[0]
            elif len(resp['result']) == 0: # No results
                raise LookupError(f'{ubj_str.capitalize()} not found.')
            else:
                raise LookupError(f'Expected one {ubj_str}, but got {len(resp["result"])}.', resp['result'])
        else:
            raise Exception('Failed to get {ubj_str}.', resp)
        
    def _many_get(self, table:str, resp:Status)-> tuple:
        if resp['status'] == 'success':
            assert isinstance(resp['result'], tuple)
            return self._reformat_sqlite(resp['result'], table=table) 
        else:
            raise Exception(f'Failed to get {table}.', resp)
        
    def _validate_date(self, date:str, format:str='%Y-%m-%d')-> bool: # Will return a datetime object
        """Attempt to validate a string formatted date

        Args:
            date (str): Unvalidated date.
            format (str, optional): datetime formatting string. Defaults to '%Y-%m-%d'.

        Returns:
            bool:  True if valid.
        """
        try:
            validated: datetime = datetime.strptime(date, format)
        except ValueError:
            return False
        
        return True
    
    def _reformat_sqlite(self, data:tuple, table:str, custom_keys:Optional[dict]=None) -> tuple[dict[str, str | int | float | bool]]: # Reformat data from the database into more friendly 
        """Reformat the data from SQLite database to make it easier to work with

        Args:
            data (list): Data from SQLite
            table (str): The table that data is being extracted from
            custom_keys (dict, optional): Custom key names
        
        Returns:
            tuple: List of reformatted data
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
            'aggregate_value': 'combined_value',
            # Participants
            'datetime_joined': 'joined',
            # Stocks
            'company_name': 'name',
            # Users
            'display_name': 'username',
            }
        for raw_data in data: # Reformat data from SQLite
            
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
        return tuple(formatted_data)
    
    
    # # USER ACTIONS # #
    def add_user(self, user_id:int, source:str, display_name:Optional[str]=None, permissions:int = 210):
        """Add a user

        Args:
            user_id (int): UNIQUE ID to identify user.
            source (str): Source of user.  EG: Discord.
            display_name (str): Username/Displayname for user.
            permissions (int, optional): User permissions (see). - UNUSED in V1.0.0
        """
        items = {
            'user_id': user_id,
            'display_name':display_name,
            'source': source,
            'permissions': permissions,
            'datetime_created': _iso8601()
            }
        
        resp = self.sql.insert(table='users', items=items)
        if resp['status'] != 'success': #TODO errors
            if resp['reason'] == 'SQLITE_CONSTRAINT_PRIMARYKEY':
                raise ValueError(f'User with ID {user_id} already exists.')
            else:
                raise Exception(f'Failed to add user.', resp)
        
    def get_user(self, user_id:int):
        """Get a single user

        Args:
            user_id (int): User ID.

        Returns:
            dict: User information.
        """
        resp = self.sql.get(table='users', filters={'user_id': user_id})
        return self._single_get(table='users', resp=resp)
    
    def get_many_users(self, display_name:Optional[str]=None, source:Optional[str]=None, permissions:Optional[int]=None, ids_only:bool=False) -> tuple: 
        """Get multiple users

        Args:
            display_name (Optional[str], optional): Filter by display name.
            source (Optional[str], optional): Filter by source.
            permissions (Optional[int], optional): Filter by permission.
            ids_only (bool, optional): Return only user IDs. Defaults to False.

        Returns:
            tuple: Matching users.
        """
        #TODO implement source and permission filtering
        columns = []
        if ids_only:
            columns = ['user_id']    
        
        filters = {
            'display_name': display_name,
            'source': source,
            'permissions': permissions
            }
        
        
        resp = self.sql.get(table='users', columns=columns, filters=filters)
        users = self._many_get(table='users', resp=resp)
        if ids_only:
            ids = tuple([user['id'] for user in users])
            return ids 
        else:
            return users
         
    def update_user(self, user_id:int, display_name:Optional[str]=None, permissions:Optional[int]=None):
        """Update an existing user

        Args:
            user_id (int): User ID.
            display_name (Optional[str], optional): Display name.
            permissions (Optional[str], optional): Permissions.
        """
        items = {
            'display_name': display_name,
            'permissions': permissions
            }
        
        resp = self.sql.update(table="users", filters={'user_id': user_id}, items=items) 
        if resp['status'] != 'success': #TODO errors
            raise Exception(f'Failed to update user {user_id}.', resp) 
        
    def remove_user(self, user_id:int): 
        """Remove a user

        Args:
            user_id (int): User ID.
        """
        
        resp = self.sql.delete(table="users", filters={'user_id': user_id}) 
        if resp['status'] != 'success': #TODO errors
            raise Exception(f'Failed to remove user {user_id}.', resp) 
    
    
    # # GAME ACTIONS # #
    def add_game(self, user_id:int, name:str, start_date:str, end_date:Optional[str]=None, starting_money:float=10000.00, pick_date:Optional[str]=None, private_game:bool=False, total_picks:int=10, draft_mode:bool=False, sell_during_game:bool=False, update_frequency:str='daily'):
        """Add a new game
        
        WARNING: If using realtime, expect issues

        Args:
            user_id (int): Game creators user ID.
            name (str): Name for this game.
            start_date (str): Start date.  Format: `YYYY-MM-DD`.
            end_date (str, optional): End date.  Format: `YYYY-MM-DD`.  Leave blank for infinite game.
            starting_money (float, optional): Starting money. Defaults to $10000.00.
            pick_date (str, optional): Date stocks must be picked by.  Format: `YYYY-MM-DD`.  If not set, players can join anytime.
            private_game(bool, optional): Whether the game is private (True).  Defaults to public (False).
            total_picks (int, optional): Amount of stocks each user picks. Defaults to 10.
            draft_mode (bool, optional): Whether multiple users can pick the same stock.  If enabled, pick date must be on or before start date Defaults to False. - NOT IMPLEMENTED
            sell_during_game (bool, optional): Whether users can sell stocks during the game.  Defaults to False. - NOT IMPLEMENTED
            update_frequency (str, optional): How often prices will update ('daily', 'hourly', 'minute', 'realtime'). Defaults to 'daily'. - NOT IMPLEMENTED
            
        Returns:
            Status: Game creation status.
        """
        #TODO make a Literal for update_frequency
 
        # Date formatting validation
        if not self._validate_date(start_date):
            raise ValueError('Invalid `start_date` format.')
        if end_date: # Enddate stuff
            if not self._validate_date(end_date):
                raise ValueError('Invalid `end_date` format.')
            if datetime.strptime(start_date, "%Y-%m-%d").date() > datetime.strptime(end_date, "%Y-%m-%d").date():
                raise ValueError('`end_date` must be after `start_date`.')
            
        if pick_date and not self._validate_date(pick_date):
            raise ValueError('Invalid `pick_date` format.')
        #TODO should we check if pick_date is after end_date?  Doesn't cause an issue, just kinda silly
        
        if draft_mode: # Draftmode checks
            if not pick_date:
                raise TypeError('`pick_date` required when `draft_mode` is enabled.')
            if datetime.strptime(start_date, "%Y-%m-%d").date() < datetime.strptime(pick_date, "%Y-%m-%d").date(): # Date format is already validated
                raise ValueError('`start_date` must be after `pick_date` when `draft_mode` is enabled.')
    
        # Misc
        if starting_money < 1.0:
            raise ValueError('`starting_money` must be atleast `1.0`.')
        if total_picks < 1:
            raise ValueError('`total_picks` must be atleast `1`.')
        
        items = {
            'name': name,
            'owner_user_id': user_id,
            'start_money': starting_money,
            'pick_count': total_picks,
            'draft_mode': draft_mode,
            'pick_date': pick_date,
            'private_game': private_game,
            'allow_selling': sell_during_game,
            'update_frequency': update_frequency.lower() if update_frequency else None, # Make sure its lowercase
            'start_date': start_date,
            'end_date': "None" if end_date == None else end_date,  # is this needed?, no but I like it.
            'datetime_created': _iso8601()
            }

        resp = self.sql.insert(table='games', items=items)
        if resp['status'] != 'success': #TODO errors
            raise Exception(f'Failed to add game.', resp) 
    
    def get_game(self, game_id:int)-> Games | dict: # Its always a Games object, but its being a fucking baby
        """Get a single game by ID

        Args:
            game_id (int): Game ID.

        Returns:
            dict: Game information.
        """        
        filters = {'game_id': int(game_id)}
        resp = self.sql.get(table='games',filters=filters)
        return self._single_get(table='games', resp=resp)
    
    def get_many_games(self, name:Optional[str]=None, owner_id:Optional[int]=None, include_public:bool=True, include_private:bool=False, include_open:bool=True, include_active:bool=True, include_ended:bool=False)-> tuple[Games]: # List all games
        """Get multiple games

        Args:
            name (Optional[str], optional): Filter by name.
            owner_id (Optional[int], optional): Filter by owner ID.
            include_public (bool, optional): Include public games in results. Defaults to True.
            include_private (bool, optional): Include private games in results. Defaults to False.
            include_open (bool, optional): Include open games in results. Defaults to True.
            include_active (bool, optional): Include active games in results. Defaults to True.
            include_ended (bool, optional): Include ended games in results. Defaults to False.

        Returns:
            tuple: Matching games.
        """        
        query = """SELECT *
        FROM games
        WHERE private_game IN ({privacy})
        AND STATUS IN ({statuses})
        """
        values =[]
        
        if name:
            query += 'AND name LIKE ?'
            values.append(name)
        if owner_id:
            query += 'AND owner_user_id = ?'
            values.append(owner_id)
        
        # privacy
        privacy = []
        if include_public:
            privacy.append('0')
        if include_private:
            privacy.append('1')
        
        # status
        statuses = []
        if include_open:
            statuses.append('"open"')
        if include_active:
            statuses.append('"active"')
        if include_ended:
            statuses.append('"ended"')
        
        resp = self.sql.send_query(query=query.format(statuses='' +','.join(statuses), privacy='' +','.join(privacy)), values=values)
        return self._many_get(table='games', resp=resp)
        
    def update_game(self, game_id:int, owner:Optional[int]=None, name:Optional[str]=None, start_date:Optional[str]=None, end_date:Optional[str]=None, status:Optional[str]=None, starting_money:Optional[float]=None, pick_date:Optional[str]=None, private_game:Optional[bool]=None, total_picks:Optional[int]=None, draft_mode:Optional[bool]=None, sell_during_game:Optional[bool]=None, update_frequency:Optional[str]=None, aggregate_value:Optional[float]=None):
        """Update an existing game
        
        Args:
            game_id (int): Game ID.
            owner (Optional[int], optional): New owner ID. 
            name (Optional[str], optional): New game name. 
            start_date (Optional[str], optional): New start date.  Format: `YYYY-MM-DD`.  Cannot be changed once game has started.
            end_date (Optional[str], optional): New end date.  Format: `YYYY-MM-DD`.
            status (Optional[str], optional): Status ('open', 'active', 'ended').  Once start date has passed, game will become 'active'.  Shouldn't be changed manually.
            starting_money (Optional[float], optional): Starting money.  Cannot be changed once game has started.
            pick_date (Optional[str], optional): Pick date.  Format: `YYYY-MM-DD`.  Cannot be changed once game has started.
            private_game (Optional[bool], optional): Game privacy. 
            total_picks (Optional[int], optional): Total picks.  Cannot be changed once game has started.
            draft_mode (Optional[bool], optional): Whether multiple users can pick the same stock.  Cannot be changed once game has started.
            sell_during_game (Optional[bool], optional): Whether users can sell stocks during game.
            update_frequency (Optional[str], optional): Price update frequency ('daily', 'hourly', 'minute', 'realtime'. 
            aggregate_value (Optional[float], optional): Total value of all game participants stocks.  Shouldn't be changed manually.
        """

        game = self.get_game(game_id) # Error will be thrown if game can't be found, so anything returned is a game
        if datetime.strptime(game['start_date'], "%Y-%m-%d").date() < datetime.today().date():
            if start_date or starting_money or pick_date or draft_mode:
                raise ValueError('Cannot update `start_date`, `starting_money`, `pick_date`, or `draft_mode` once game has started.')
        
        items = {'name': name,
            'owner_user_id': owner,
            'start_money': starting_money,
            'pick_count': total_picks,
            'draft_mode': draft_mode,
            'pick_date': pick_date,
            'private_game': private_game,
            'allow_selling': sell_during_game,
            'status': status,
            'update_frequency': update_frequency.lower() if update_frequency else None,
            'start_date': start_date,
            'end_date': end_date,
            'aggregate_value': aggregate_value
            }
        
        resp = self.sql.update(table='games', filters={'game_id': game_id}, items=items)
        if resp['status'] != 'success': #TODO errors
            raise Exception(f'Failed to update game {game_id}.', resp) 
    
    
    # # STOCK ACTIONS # #
    def add_stock(self, ticker:str, exchange:str, company_name:str):
        """Add a stock

        Args:
            ticker (str): Stock ticker.  Eg: 'MSFT'.
            exchange (str): Exchange stock is listed on.
            company_name (str): Company name.
        """        
        items = {
            'ticker': ticker.upper(),
            'exchange': exchange,
            'company_name': company_name
            } # I guess not all stocks have a long name?

        resp = self.sql.insert(table='stocks', items=items)
        if resp['status'] != 'success': 
            if resp['reason'] == 'SQLITE_CONSTRAINT_UNIQUE' and 'stocks.ticker' in str(resp['result']): 
                raise ValueError(f'Stock with ticker {ticker} already exists.')
            else:
                raise Exception(f'Failed to add stock.', resp)
    
    def get_stock(self, ticker_or_id:str | int)-> dict:
        """Get a stock

        Args:
            ticker_or_id (str | int): Stock ID (int) or ticker (str).

        Returns:
            dict: Stock information.
        """
        if isinstance(ticker_or_id, str): # ID
            filters={'ticker': str(ticker_or_id)}
        else: # Ticker
            filters = {'stock_id': int(ticker_or_id)}
        resp = self.sql.get(table='stocks', filters=filters)
        return self._single_get(table='stocks', resp=resp)
        
    def get_many_stocks(self, company_name:Optional[str]=None, exchange:Optional[str]=None, tickers_only:bool=False)-> tuple:
        """Get multiple stocks

        Args:
            company_name (Optional[str], optional): Filter by company name.
            exchange (Optional[str], optional): Filter by exchange.
            tickers_only (bool, optional): Only return tickers. Defaults to False.

        Returns:
            tuple: Matching stocks.
        """
        filters = {
            'company_name': company_name,
            'exchange': exchange
            }
        columns = []
        if tickers_only:
            columns = ['ticker']

        resp = self.sql.get(table='stocks', columns=columns, filters=filters)
        stocks = self._many_get(table='stocks', resp=resp)
        if tickers_only:
            tickers = tuple([ticker['ticker'] for ticker in stocks])
            return tickers
        else:
            return stocks
    
    def remove_stock(self, ticker_or_id:str | int): 
        """Remove a stock

        Args:
            ticker_or_id (str | int): Stock ID (int) or ticker (str).
        """
        if isinstance(ticker_or_id, int): # ID
            filters={'ticker': str(ticker_or_id)}
        else: # Ticker
            filters = {'stock_id': int(ticker_or_id)}
            
        resp = self.sql.delete(table="stocks", filters=filters) 
        if resp['status'] != 'success': #TODO errors
            raise Exception(f'Failed to delete stock {ticker_or_id}.', resp) 
    
    
    # # STOCK PRICE ACTIONS # #
    def add_stock_price(self, ticker_or_id:str | int, price:float, datetime:Optional[str]=None):
        """Add price data for a stock (should be done at close)

        Args:
            ticker_or_id (str | int): Stock ID (int) or ticker (str).
            price (float): Stock price.
            datetime (str, optional): Price datetime Format:`YYYY-MM-DD HH:MM:SS`.  If not provided, current datetime will be used.
        
        Raises:
            LookupError: Invalid Stock ID/Ticker.
        """
        if datetime and not self._validate_date(datetime, '%Y-%m-%d %H:%M:%S'): #Try to validate date
            raise ValueError('Invalid `datetime` format.')
        elif not datetime:
            datetime = _iso8601() # Current datetime as string if date was not provided
            
        stock_id = self.get_stock(ticker_or_id)['id'] #If stock is invalid, an error will be thrown anyway.
        
        items = {
            'stock_id':int(stock_id), 
            'price': float(price), 
            'datetime': str(datetime)
            }
        
        resp = self.sql.insert(table='stock_prices', items=items)
        if resp['status'] != 'success': #TODO errors
                raise Exception(f'Failed to add stock price for {ticker_or_id}.', resp)
    
    def get_stock_price(self, price_id:int) -> dict:
        """Get a single stock price by ID.

        Args:
            price_id (int): Price ID.

        Returns:
            dict: Stock price information.
        """
        resp = self.sql.get(table='stock_prices', filters={'price_id': price_id})
        return self._single_get(table='stock_prices', resp=resp)
    
    def get_many_stock_prices(self, stock_id:Optional[int]=None, datetime:Optional[str]=None): # List stock prices, allow some filtering 
        """List stock prices.

        Args:
            stock_id (str, optional): Filter by a stock ID. Defaults to None.
            date (str, optional): Filter by a date.  Formats:  `YYYY-MM-DD HH:MM:SS`, `YYYY-MM-DD`, `YYYY-MM-DD HH:`, etc..  Will use todays DATE if blank.

        Returns:
            list: Stock price info
        """
        if not datetime:
            datetime = _iso8601('date')
        order = {'datetime': 'DESC'}  # Sort by price date (recent first)
        filters = {
            'stock_id': stock_id, 
            ('LIKE', 'datetime'): datetime + '%' # Match like objects
            } 

        resp = self.sql.get(table='stock_prices',filters=filters, order=order) 
        return self._many_get(table='stock_prices', resp=resp)
    
    
    # # STOCK PICK ACTIONS # #
    def add_stock_pick(self, participant_id:int, stock_id:int,): # This is essentially putting in a buy order. End users should not be interacting with this directly 
        """Create stock pick.

        Args:
            participant_id (int): Participant ID. Use get_participant_id() with user ID and game ID if you don't have it
            stock_id (int): Stock ID.
        """
        player = self.get_participant(participant_id)
        if player['status'] != 'active':
            raise ValueError("User is not active in game.")
        
        game = self.get_game(game_id=player['game_id']) 
        if game['pick_date'] and datetime.strptime(game['pick_date'], "%Y-%m-%d").date() < datetime.today().date(): # Check that pick date hasn't passed
            raise ValueError('Unable to add pick, past `pick_date`')
        
        picks = self.get_many_stock_picks(participant_id=participant_id, status=['pending_buy', 'owned', 'pending_sell'])
        if len(picks) >= game['total_picks']: #
            raise ValueError("Already at maximum picks.")
        
        items = {
            'participation_id':participant_id,
            'stock_id':stock_id,
            'datetime_updated': _iso8601()
            }
        
        resp = self.sql.insert(table='stock_picks', items=items)
        if resp['status'] != 'success': #TODO errors
            raise Exception(f'Failed to add pick.', resp)
    
    def get_stock_pick(self, pick_id:int)-> dict:
        """Get a single stock pick

        Args:
            pick_id (int): Pick ID.

        Returns:
            dict: Single stock pick
        """
        
        resp = self.sql.get(table='stock_picks', filters={'pick_id': pick_id})
        return self._single_get(table='stock_picks', resp=resp)
    
    def get_many_stock_picks(self, participant_id:Optional[int]=None, status:Optional[str | list]=None, stock_id:Optional[int]=None): 
        """List stock picks.  Optionally, filter by a status or participant ID

        Args:
            participant_id (int, optional): Filter by a participant ID.
            status (str | list, optional): Filter by a status(es) ('pending_buy', 'owned', 'pending_sell', 'sold').
            stock_id(int, optional): Filter by stock ID.
            
        Returns:
            list: List of stock picks
        """
        valid_statuses = ['pending_buy', 'owned', 'pending_sell', 'sold']
        statuses = []
        if status: # validate statuses
            if isinstance(status, str):
                status = [status]
            for st in status: # Chec kthat 
                if st not in valid_statuses:
                    raise ValueError(f'invalid `status` {st}.')
                statuses.append(f'"{st}"') # Add valid statues
        
            filters = { 
            ('IN', 'status'): "" + ",".join(statuses),
            'participation_id': participant_id,
            'stock_id': stock_id
            }

        resp = self.sql.get(table='stock_picks', filters=filters)
        return self._many_get(table='stock_picks', resp=resp)

    def update_stock_pick(self, pick_id:int, current_value:float,  shares:Optional[float]=None, start_value:Optional[float]=None,  status:Optional[str]=None): #Update a single stock pick
        """Update a stock pick

        Args:
            pick_id (int): Pick ID.
            current_value (float): Current value (shares * current stock price)
            shares (Optional[float], optional): Shares.
            start_value (Optional[float], optional): Starting value of pick.
            status (Optional[str], optional): Status ('pending_buy', 'owned', 'pending_sell', 'sold').
        """
        items = {
            'shares': shares,
            'start_value': start_value,
            'current_value': current_value,
            'status': status,
            'datetime_updated': _iso8601()
            }
        
        resp = self.sql.update(table='stock_picks', items=items, filters={'pick_id': pick_id})
        if resp['status'] != 'success': #TODO errors
            raise Exception(f'Failed to update pick.', resp)
    
    def remove_stock_pick(self, pick_id:int):
        """Remove a stock pick

        Args:
            pick_id (int): Pick ID.
        """
        
        resp = self.sql.delete(table='stock_picks', filters={'pick_id': pick_id})
        if resp['status'] != 'success': #TODO errors
            raise Exception(f'Failed to remove pick.', resp)
    

    # # GAME PARTICIPATION ACTIONS # #
    def add_participant(self, user_id:int, game_id:int, team_name:Optional[str]=None):
        """Add a game participant
        
        No checks are done here, any game can be joined.  Frontend will handle validation for this

        Args:
            user_id (int): User ID.
            game_id (int): Game ID.
            team_name (Optional[str], optional): Nickname for this specific game.
        """
        items = {
            'user_id':user_id, 
            'game_id':game_id,
            'name': team_name,
            'datetime_joined': _iso8601()
            }
    
        resp = self.sql.insert(table='game_participants', items=items)
        if resp['status'] != 'success': #TODO errors
            raise Exception(f'Failed to add participant.', resp)
        
    def get_participant(self, participant_id:int): # Get game member info
        """Get a game participant's information

        Args:
            participant_id (int): Participant ID.

        Returns:
            dict: Participant information.
        """

        resp = self.sql.get(table='game_participants', filters={'participation_id': participant_id}) 
        return self._single_get(table='game_participants', resp=resp)
        
    def get_many_participants(self, game_id:Optional[int]=None, user_id:Optional[int]=None, status:Optional[str]=None, sort_by_value:bool=False):
        """Get multiple

        Args:
            game_id (Optional[int], optional): Filter by game ID. 
            user_id (Optional[int], optional): Filter by user ID.
            status (Optional[str], optional): Filter by status ('pending', 'active', 'inactive').
            sort_by_value (bool, optional): Whether results should be sorted by value.

        Returns:
            tuple: Matching participants.
        """
        if status and status not in ['pending', 'active', 'inactive']: # TODO support multiple statuses
            raise ValueError('Invalid status!')
        
        filters = {
            'user_id': user_id,
            'game_id': game_id,
            'status':status
            }
        
        order={'game_id': 'DESC'}
        if sort_by_value:
            order['current_value'] = 'DESC'
        
        resp = self.sql.get(table='game_participants', order=order, filters=filters, ) 
        return self._many_get(table='game_participants', resp=resp)
    
    def update_participant(self, participant_id:int, team_name:Optional[str]=None, status:Optional[str]=None, current_value:Optional[float]=None):
        """Update a game participant

        Args:
            participant_id (int): Participant ID.
            name (Optional[str], optional): Team name.
            status (Optional[str], optional): Status ('pending', 'active', 'inactive').
            current_value (Optional[float], optional): Current portfolio value.
        """
        items = {'name': team_name,
                 'status': status,
                 'current_value': current_value,
                 'datetime_updated': _iso8601()}
        
        resp = self.sql.update(table='game_participants', filters={'participation_id': participant_id}, items=items)
        if resp['status'] != 'success': #TODO errors
            raise Exception(f'Failed to update participant {participant_id}.', resp)
        
    def remove_participant(self, participant_id:int):
        """Remove a game participant

        Args:
            participant_id (int): Participant ID.
        """
        resp = self.sql.delete(table="game_participants", filters={'participant_id': participant_id}) 
        if resp['status'] != 'success': #TODO errors
            raise Exception(f'Failed to remove participant {participant_id}.', resp) 
        
  
class GameLogic: # Might move some of the control/running actions here
    def __init__(self, db_name:str, market_open_est:str='09:30', market_close_est:str='16:00'):
        """GameLogic class
        
        Handles game logic like updating stock prices, etc.
        
        Args:
            db_name (str): Database name.
        """
        create_db(db_name) # Try to create DB
        self.logger = logging.getLogger('StockGameLogic')
        self.be = Backend(db_name)
        self.market_open_est = datetime.strptime(market_open_est,"%H:%M")
        self.market_close_est = datetime.strptime(market_close_est,"%H:%M")
        self.est_offset = self._market_time_offset()
    
    def _is_market_hours(self): # Only considers hours
        """Check whether the time is inside our outside of market hours.  Does not consider weekends, etc.

        Returns:
            bool: True when within market hours.
        """
        the_time = datetime.strftime(datetime.now() + timedelta(hours=self.est_offset), "%H:%M")
        if datetime.strptime(the_time,"%H:%M") > self.market_open_est and self.market_close_est > datetime.strptime(the_time,"%H:%M"):
            return True
        else:
            return False

    def _market_time_offset(self): # If your timezone is EST then none of this is needed and I'll feel real dumb #TODO this is so awful oh my god
        """Get the market offset hours from current timezone.  Add or subtract this from times in DB

        Returns:
            float: Offset in hours.
        """
        local_time = datetime.now() # Naive time (except then it isnt fucking naive like 30 seconds later so why call it that)
        local_utc_offset = datetime.now().astimezone().utcoffset() 
        local_offset_hours = (local_utc_offset.days * 24) + (local_utc_offset.seconds / 3600) # This is the UTC offset in hours
        if local_offset_hours > 0: # Ahead of UTC
            local_offset = 'ahead'
        else:
             local_offset = 'behind'
            
        nyc = pytz.timezone('America/New_York') # NYC timezone
        market_utc_offset = nyc.localize(local_time).utcoffset()
        market_offset_hours = (market_utc_offset.days * 24) + (market_utc_offset.seconds / 3600) # So is this
        if market_offset_hours > 0: # Ahead of UTC
            market_offset = 'ahead' # Market offset should never be ahead of UTC, but idk maybe one day it will be :)
        else:
             market_offset = 'behind' 
        
        total_offset = (0 -local_offset_hours if local_offset == 'ahead'  else +local_offset_hours) + (0 -market_offset_hours if market_offset == 'ahead'  else +market_offset_hours)
        return total_offset
    
    def update_game_statuses(self):
        """Update game statuses
        
        Sets games that have started to 'active' and games that have ended to 'ended'
        """
        games = self.be.get_many_games(include_private=True) # Get all games
        if len(games) > 0:
            for game in games: #TODO add log here
                
                # Start and end games
                if game['status'] == 'open' and datetime.strptime(game['start_date'], "%Y-%m-%d").date() <= datetime.strptime(_iso8601('date'), "%Y-%m-%d").date(): # Set games to active
                    self.be.update_game(game_id=game['id'], status='active')
                if game['status'] == 'active' and game['end_date'] and datetime.strptime(game['end_date'], "%Y-%m-%d").date() < datetime.strptime(_iso8601('date'), "%Y-%m-%d").date(): #Game has ended
                    self.be.update_game(game_id=game['id'], status='ended')
        else:
            raise Exception('Failed to update game statuses.', games)
        
    def update_stock_prices(self):
        """Find and update stock prices for all stocks currently in games (pending picks are included)
        
        Uses yfinance API.
        """
        #TODO Skip holidays
        #TODO allow after hours data to be added here as long as its tagged?
        #TODO don't run too often
        # Only get active stocks (stocks from games that are running)
        query = """ SELECT *
        FROM stocks
        WHERE stock_id IN (SELECT stock_id
            FROM stock_picks
            WHERE status IS NOT "sold"
            AND participation_id IN (SELECT participation_id
                FROM game_participants
                WHERE game_id IN (SELECT game_id
                    FROM games
                    WHERE status IS NOT "ended"
                    )
                )
            )
        """
        active_stocks = self.be.sql.send_query(query)
        if active_stocks['status'] == 'success':
            assert isinstance(active_stocks['result'], tuple)
            tickers = [tkr['ticker'] for tkr in active_stocks['result']]
            if len(tickers) > 0:
                prices = yf.Tickers(tickers).tickers
                for ticker, price in prices.items(): # update pricing
                    price = price.info['regularMarketPrice'] 
                    try:
                        self.be.add_stock_price(ticker_or_id=ticker, price=price, datetime=_iso8601()) # Update pricing
                    except Exception as e:
                        self.logger.exception(e) # Log exception
                        pass #TODO find problems if/when they appear
        else:
            raise ValueError('Failed to update stock prices.', active_stocks)
    
    def update_stock_picks(self, game_id:Optional[int]=None) -> None:
        """Update all owned and pending stock picks with current prices
        
        - Validates game type of daily, but nothing else for now
        - Adds pending_buy stock picks for users (depending on time)
        - Update owned stock pick values

        Args:
            game_id (Optional[int], optional): Game ID.  If blank, all games will be checked/run

        """        
        if game_id:
            games = [self.be.get_game(game_id=game_id)]
        else:
            games = self.be.get_many_games(include_open=False, include_active=True) # Only active games
        
        for game in games: 
            if game['update_frequency'] == 'daily' and self._is_market_hours(): 
                continue # daily game, currently in market hours, don't run
            pending_and_owned_query = """SELECT *
            FROM stock_picks
            WHERE status IN ("pending_buy", "owned")
            AND participation_id IN (SELECT participation_id
                FROM game_participants
                WHERE status = "active"
                AND game_id = ?
                )
            """ #TODO instead of setting games to active, just use start and end date?
            pending_unformatted = self.be.sql.send_query(query=pending_and_owned_query, values=[game['id']])
            if pending_unformatted['status'] != 'success':
                raise Exception(pending_unformatted) # catch error
            else:
                assert isinstance(pending_unformatted['result'], tuple)
                picks = self.be._reformat_sqlite(pending_unformatted['result'], table='stock_picks')
            
                for pick in picks:
                    assert isinstance(pick['id'], int)
                    assert isinstance(pick['stock_id'], int)
                    if game['update_frequency'] == 'daily' and pick['status'] == 'owned' and datetime.strptime(str(pick['last_updated']), "%Y-%m-%d %H:%M:%S") + timedelta(hours=8 ) > datetime.now():
                        continue # Skip picks with daily update frequency that have been updated in the last 12 hours
                    price = self.be.get_many_stock_prices(stock_id=int(pick['stock_id']),datetime=_iso8601('date'))[0]
                    #TODO check datetime here and decide if price should be used
                    buying_power = None,
                    shares = None
                    start_value = None
                    status = None
                    
                    if pick['status'] == 'pending_buy':
                        buying_power = float(game['starting_money'] / game['total_picks']) # Amount available to buy this stock (starting money divided by picks)
                        shares = buying_power / price['price']# Total shares owned
                        start_value = current_value = float(shares * price['price'])
                        status = 'owned'
                    else: # Stock is owned
                        current_value = float(pick['shares'] * price['price'])
                    self.be.update_stock_pick(pick_id=pick['id'],shares=shares, start_value=start_value, current_value=current_value, status=status) # Update

    def update_participants_and_games(self, game_id:Optional[int]=None):
        """Update game participant and game information
        
        - Participant portfolio value
        - Game Aggregate value

        Args:
            game_id (Optional[int], optional): Game ID.  If blank, all active games will be updated.
        """
        if game_id:
            games = [self.be.get_game(game_id=game_id)]
        else:
            games = self.be.get_many_games(include_open=False, include_active=True) # Only active games
        for game in games:
            aggr_val = 0
            if game['status'] != 'active':
                return "Game not active"
            members = self.be.get_many_participants(game_id=game['id'])
            for member in members:
                portfolio_value = 0.0
                picks = self.be.get_many_stock_picks(participant_id=member['id'], status='owned')
                for pick in picks:
                    portfolio_value += pick['current_value']
                self.be.update_participant(participant_id=member['id'], current_value=portfolio_value)
                aggr_val += portfolio_value
            
            self.be.update_game(game_id=game['id'], aggregate_value=aggr_val)
               
    def update_all(self, game_id:Optional[int]=None, force:bool=False): #TODO allow game_id #TODO allow force
        """Run all update commands/logic for games

        Args:
            game_id (Optional[int], optional): Game ID.  If blank, all active games will be updated.
            force (bool, optional): Force update games that may not be updated due to frequency. Defaults to False.
        """
        self.update_game_statuses() # Update games statuses (start and stop)
        self.update_stock_prices() # Update stock prices
        self.update_stock_picks() # Handle pending stock picks 
        self.update_participants_and_games() # Update participants (set their total value, etc.)
            
    def find_stock(self, ticker:str): 
        """Find and add a stock

        Args:
            ticker (str): Stock ticker.  Eg: 'MSFT'.
        """        
        #TODO regex the subimissions to check for invalid characters and save time.
        #TODO should only USD stocks be allowed/limit exchanges?
        try: # Check if the stock exists
            self.be.get_stock(ticker_or_id=ticker)
            
        except LookupError: # Stock doesnt exist, add
            stock = yf.Ticker(ticker)
            try:
                info = stock.info
            except AttributeError: # If stock isn't valid, an attribute error should be raised
                info = [] # Set list to 0 length so error is thrown
        
            if len(info) > 0: # Try to verify ticker is real and get the relevant infos
                self.be.add_stock(ticker=ticker.upper(),
                    exchange=info['fullExchangeName'],
                    company_name=info['displayName'] if 'displayName' in info else info['shortName'])
            else:
                raise ValueError(f'Failed to add `ticker` {ticker}.')

# # FRONTEND INTERACTIONS. # #
# This is where things like preventing users from joining a game too late, etc. will take place.
class Frontend: # This will be where a bot (like discord) interacts
    def __init__(self, database_name:str, owner_user_id:int, default_permissions:int=210, source:Optional[str]=None):
        """For use with a discord bot or other frontend
        
        Provides  basic error handling, data validation, more user friendly commands, and more.

        Args:
            database_name (str): Name of database.
            owner_user_id (int): User ID of the owner.  This user will be able to control everything.
            source (str, optional): Source.  EG: Discord. Used when creating users.
            default_permissions (int, optional): Default permissions for new users. Defaults to 210. (Users can view and join games, but not create their own). - UNUSED
        """
        self.source = source if source else 'Frontend'
        self.be = Backend(database_name)
        self.gl = GameLogic(database_name) # Handle game logic
        self.default_perms = default_permissions
        self.register(user_id=owner_user_id, source=self.source) # Try to register user
        self.be.update_user(user_id=owner_user_id, permissions=288)
        self.owner_id = owner_user_id
    
    def _user_owns_game(self, user_id:int, game_id:int): # Check if a user owns a specific game
        """Check whether a user owns a specific game

        Args:
            user_id (int): User ID.
            game_id (int): Game ID.

        Returns:
            bool: True if owned, False if not.
        """
        game = self.be.get_game(game_id=game_id)
        if game['owner'] != user_id:
            return False
        else:
            return True
        
    def _participant_id(self, user_id:int, game_id:int)-> dict:
        """Get a game participant ID

        Args:
            user_id (int): User ID.
            game_id (int): Game ID.

        Returns:
            dict: Participant information.
        """
        user = self.be.get_many_participants(user_id=user_id, game_id=game_id)
        if len(user) == 1:
            return user[0]
        else:
            raise ValueError(f'Expected one participant ID, but got {len(user)}.', user)
        
    # # GAME RELATED # #
    def new_game(self, user_id:int, name:str, start_date:str, end_date:Optional[str]=None, starting_money:float=10000.00, pick_date:Optional[str]=None, private_game:bool=False, total_picks:int=10, draft_mode:bool=False, sell_during_game:bool=False, update_frequency:str='daily'):
        """Create a new stock game!
        
        WARNING: If using realtime, expect issues
        
        ower will be automatically added

        Args:
            user_id (int): Game creators user ID.
            name (str): Name for this game.
            start_date (str): Start date.  Format: `YYYY-MM-DD`.
            end_date (str, optional): End date.  Format: `YYYY-MM-DD`.  Leave blank for infinite game.
            starting_money (float, optional): Starting money. Defaults to $10000.00.
            pick_date (str, optional): Date stocks must be picked by.  Format: `YYYY-MM-DD`.  If not set, players can join anytime.
            private_game(bool, optional): Whether the game is private (True).  Defaults to public (False).
            total_picks (int, optional): Amount of stocks each user picks. Defaults to 10.
            draft_mode (bool, optional): Whether multiple users can pick the same stock.  If enabled, pick date must be on or before start date Defaults to False. - NOT IMPLEMENTED
            sell_during_game (bool, optional): Whether users can sell stocks during the game.  Defaults to False. - NOT IMPLEMENTED
            update_frequency (str, optional): How often prices will update ('daily', 'hourly', 'minute', 'realtime'). Defaults to 'daily'. - NOT IMPLEMENTED
        """
    
        try: # Try create user
            user = self.register(user_id=user_id)  
        except ValueError: # User was already there, my bad
            pass
    
        try:  # Create game
            self.be.add_game(
                user_id=int(user_id),
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
        game = self.be.get_many_games(name=name, owner_id=user_id)
        if len(game) == 1:
            self.be.add_participant(user_id=user_id, game_id=game[0]['id'])
        else:
            pass #TODO log that user could not be added to their game, but that it was created
    
    def list_games(self, include_private:bool=False): 
        """List games.
        
        Args:
            include_private (bool, optional): Whether to include private games. Defaults to False.
        
        Returns:
            list: List of games
        """
        games = self.be.get_many_games(include_private=include_private)
        return games
    
    def game_info(self, game_id:int, show_leaderboard:bool=True): 
        """Get information and leaderboard for a game.
        
        If user has set a nickname for a game that will be returned, otherwise their username will be used

        Args:
            game_id (int): Game ID
            show_leaderboard (bool, optional): Whether to include the leaderboard in the response

        Returns:
            dict: Game information
        """
        # Return Tuples
        
        game = self.be.get_game(game_id) # Will raise an error for invalid games
        game_obj = dict(game) # Make a copy so it quits acting like a child
        game_obj['combined_value'] = "%.2f" % game['combined_value'] # Round to two decimal places
        info = {
            'game': game,
        }
        if show_leaderboard:
            leaderboard = list()
            members = self.be.get_many_participants(game_id=game_id, sort_by_value=True)
            for member in members:
                user = self.be.get_user(member['user_id'])
                leaderboard.append({
                    'username': member['team_name'] if member['team_name'] not in [None, 'None'] else user['username'],
                    'current_value': "%.2f" % member['current_value'] # Round to two decimal places
                }) # Should keep order
                
            info['leaderboard'] = leaderboard  # type: ignore WAA I DONT FUCKING CARE I KNOW THIS WORKS
        return info
    
    # # USER RELATED
    def register(self, user_id:int, source:Optional[str]=None, username:Optional[str]=None):
        """Register user to allow gameplay

        Args:
            user_id (int): User ID.
            source (str, optional): Source of user.  EG: Discord.  If blank, will use default source set in frontend.
            username (str, optional): Display name/username.

        Returns:
            str: Status/result
        """
        try:
            self.be.add_user(user_id=user_id, source=source if source else self.source, display_name=username, permissions=self.default_perms)
            return "Registered"
        except ValueError: # user already exists
            return "User already registered"

    def change_name(self, user_id:int, name:str):
        """Change your display name (nickname).

        Args:
            user_id (int): User ID.
            name (str): New name.
        """
        self.be.update_user(user_id=int(user_id), display_name=str(name)) 
    
    def join_game(self, user_id:int, game_id:int, name:Optional[str]=None):
        """Join a game.

        Args:
            user_id (int): User ID.
            game_id (int): Game ID.
            name (str, optional): Team name/nickname for game.
        """
        #TODO check permissions before running
        self.be.add_participant(user_id=int(user_id), game_id=int(game_id), team_name=str(name))

    def my_games(self, user_id:int):
        """Get a list of your current games

        Args:
            user_id (int): User ID.

        Returns:
            list: Your current games 
        """
        #TODO should this alow filtering for inactive games, etc.?
        games = self.be.get_many_participants(user_id=int(user_id))
        games_info = {
            'user': self.be.get_user(user_id=user_id), # User details
            'games': [] # Game details will be stored here
            }
        for game in games: # Provide additional details
            games_info['games'].append(self.be.get_game(game['game_id']))

        return games_info
    
    # # STOCK RELATED
    def buy_stock(self, user_id:int, game_id:int, ticker:str):
        """Pick/buy a stock

        Args:
            user_id (int): User ID.
            game_id (int): Game ID.
            ticker (str): Ticker.
        """
        member = self._participant_id(user_id=user_id, game_id=game_id)
        try: # Try to add stock
            self.gl.find_stock(ticker=str(ticker))
        except ValueError as e: # Stock exists #TODO breakout specific errors
            pass
        stock = self.be.get_stock(ticker_or_id=str(ticker))

        self.be.add_stock_pick(participant_id=member['id'], stock_id=stock['id']) # Add the pick

    
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
        participant = self._participant_id(user_id=user_id, game_id=game_id) #TODO check for errors
        stock_id = self.be.get_stock(ticker_or_id=ticker)
        picks = self.be.get_many_stock_picks(participant_id=participant['id'], status='pending_buy', stock_id=stock_id['id'])
        if len(picks) == 1:
            return self.be.remove_stock_pick(pick_id=picks[0]['id'])
        else:
            raise ValueError(f'Expected one pick, but got {len(picks)}.', user)
    
    def my_stocks(self, user_id:int, game_id:int, show_pending:bool=True, show_sold:bool=False):
        """Get your stocks for a specific game.

        Args:
            user_id (int): User ID.
            game_id (int): Game ID.
            show_pending (bool, optional): Whether to show pending purchases. Defaults to False (no).
            show_sold (bool, optional): Whether to sold stocks. Defaults to False (no).

        Returns:
            list: Stocks both owned and pending
        """
        part_id = self._participant_id(user_id=user_id, game_id=game_id) 
        if 'status' in part_id:
            part_id['reason'] = 'User not found'
            return part_id
        picks = self.be.get_many_stock_picks(participant_id=part_id['id'],status=['pending_buy, owned, pending_sell'])
        return picks
    
    def start_draft(self, user_id:int, game_id:int): #TODO add
        pass
    
    def force_update(self, user_id:int, game_id:Optional[int]=None):
        """Force update game(s)

        Args:
            user_id (int): User ID.
            game_id (Optional[int], optional): Game ID. If blank, all games will be updated.
        """
        if user_id != self.owner_id:
            raise ValueError(f'User {user_id} does not have permission to update games')
        
        self.gl.update_all(game_id=game_id, force=True) # 
        
        
    def manage_game(self, user_id:int, game_id:int, owner:Optional[int]=None, name:Optional[str]=None, start_date:Optional[str]=None, end_date:Optional[str]=None, status:Optional[str]=None, starting_money:Optional[float]=None, pick_date:Optional[str]=None, private_game:Optional[bool]=None, total_picks:Optional[int]=None, draft_mode:Optional[bool]=None, sell_during_game:Optional[bool]=None, update_frequency:Optional[str]=None):
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
            return "You do not have permission to update this game" #TODO this should be an error
            
        self.be.update_game(game_id=game_id, owner=owner, name=name, start_date=start_date, end_date=end_date, status=status, starting_money=starting_money, pick_date=pick_date, private_game=private_game, total_picks=total_picks, draft_mode=draft_mode, sell_during_game=sell_during_game, update_frequency=update_frequency)

    
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
        
        users = self.be.get_many_participants(game_id=game_id, status='pending')
        return users
        
    def approve_game_users(self, user_id:int, participant_id:int):
        """Approve/add a user to private game

        Args:
            user_id (int): User ID (command runner).
            participant_id (int): Participant ID (get with pending_game_users).

        Returns:
            dict: status
        """
        user = self.be.get_participant(participant_id=participant_id)
        if not self._user_owns_game(user_id=user_id, game_id=user['game_id']):
            return "You do not have permission to manage this game"
        
        user = self.be.update_participant(participant_id=participant_id, status='active')
        return user

    def get_all_participants(self, game_id: int):
        return self.be.get_many_participants(game_id=game_id, sort_by_value=True)
    
# TESTING
if __name__ == "__main__":
    DB_NAME = str(os.getenv('DB_NAME')) # Only added so itll shut the fuck up about types
    OWNER = int(os.getenv("OWNER")) # type: ignore # Set owner ID from env 
    test_users = [111, 222, 333, 444, 555, 666]
    test_stocks = ['MSFT', 'SNAP', 'GME', 'COST', 'NVDA', 'MSTR', 'CSCO', 'IBM', 'GE', 'BKNG']
    test_stocks2 = ['MSFT', 'SNAP', 'UBER', 'COST', 'AMD', 'ADBE', 'CSCO', 'IBM', 'GE', 'PEP']
    game = Frontend(database_name=DB_NAME, owner_user_id=OWNER) # Create frontend 
    #create = game.new_game(user_id=OWNER, name="TestGame", start_date="2025-05-06", end_date="2025-05-30") # Try to create game
    many_games = game.be.get_many_games(include_private=True)
    game.be.update_game(game_id=1, name='TestGameUpd')
    picks = game.be.get_many_stock_picks(status=['owned', 'pending_sell'])
    game.gl.update_all()
    #game.gl.update_stock_prices()
    print(game.be.get_many_users(ids_only=True)) # List users from the backend
    print(game.list_games()) # Print list of games
    print(game.my_games(user_id=OWNER)) # Try to list games you are joined to
    for user in test_users: # Add some random users
        print(game.register(user_id=user, username=str(user)))
        try:
            game.join_game(user_id=user,game_id=1)
        except:
            pass
        for stock in test_stocks2: # Buy some stocks
            game.buy_stock(user, 1, stock)
    print(game.join_game(user_id=OWNER,game_id=1)) # Try to join a game
    
    for stock in test_stocks: # Buy stocks
        print(f'BUY {stock}! {game.buy_stock(OWNER, 1, stock)}') # Try to purchase stock
    
    print(f'my stocks: {game.my_stocks(user_id=OWNER, game_id=1)}')
    #print(game.update(OWNER)) # Try to update
    leaders = game.game_info(game_id=1)
    print([info for info in leaders])
    pass