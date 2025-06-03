# BUILT-IN
from datetime import datetime, timedelta
import logging
import os
import re
from typing import Optional, Type
from pydantic import ValidationError

# EXTERNAL
from dotenv import load_dotenv
from pydantic import TypeAdapter
import pytz
from requests import exceptions # Exceptions!
import yfinance as yf #TODO find alternative to yfinance since it seems to have issues https://docs.alpaca.markets/docs/about-market-data-api

# INTERNAL
import helpers.datatype_validation as dtv
import helpers.exceptions as bexc
from helpers.sqlhelper import SqlHelper, _iso8601, Status
from sqlite_creator_real import create as create_db

load_dotenv() 

version = "???" #TODO should frontend and backend have different versions?

class Backend:
    # Raise Exceptions if bad data is passed in
    # Most of these expect that the data being sent has been checked or otherwise verified.  End users should not interact directly with this
    def __init__(self, db_name:str):
        """Methods for interacting directly with the database
        
        Methods in this class will only perform basic validation of what is sent to prevent the database from being damaged.  These methods should never be directly interacted with by users.  The `Frontend()` class should be used instead.
                
        Updating stock prices, picks, etc. are handled in `GameLogic()`
        
        Args:
            db_name (str): Database name.
        """
        create_db(db_name) # Try to create DB
        self.logger = logging.getLogger('StockBackend')
        self.sql = SqlHelper(db_name)
        self.logger.info('Initiated new Backend instance.')

    # # INTERNAL # #
    def _single_get(self, model:Type[dtv.PydanticModelType], resp:Status)-> dtv.PydanticModelType: # Handle single gets
        """Check, validate, and format single get requests

        Args:
            model (Type[dtv.PydanticModelType]): Model to validate item against.
            resp (Status): Status object from sqlhelper.

        Raises:
            LookupError(Item not found.):  Raised if no items are found.
            LookupError('Expected one item, but got x): Raised if more than one item is found.
            Exception(Failed to get item.(more info)): Raised if another issue is encountered.

        Returns:
            dtv.PydanticModelType: Will return the validated and formatted object for item.
        """
        
        if resp.status == 'success':
            assert isinstance(resp.result, tuple) # Do this here because its not a tuple if its not successful
            if len(resp.result) == 1: # Single object (expected)
                return model.model_validate(resp.result[0])
            else:
                raise LookupError(f'Expected one item, but got {len(resp.result)}.')
            
        elif resp.reason == 'NO ROWS RETURNED': # Response is not success so can just check what the error is
            self.logger.error(f'Failed to get item - Not found. {resp}' )
            raise LookupError(f'Item not found.')
        else:
            raise Exception('Failed to get item.', resp)
        
    def _many_get(self, typeadapter:TypeAdapter, resp:Status)-> tuple:
        """Check, validate, and format multi get requests

        Args:
            typeadapter (TypeAdapter): Wrapper for multiple objects that need to be validated
            resp (Status): Status object from sqlhelper.

        Raises:
            LookupError(No items found):  Raised if no items are found.
            Exception(Failed to get items.(more info)): Raised if another issue is encountered.

        Returns:
            tuple: Tuple of formatted objects.
        """
        if resp.status == 'success':
            assert isinstance(resp.result, tuple) #  Real and true
            return tuple(typeadapter.validate_python(resp.result))
        elif resp.reason == 'NO ROWS RETURNED': # Response is not success so can just check what the error is
            raise LookupError('No items found')
        else:
            raise Exception(f'Failed to get items.', resp)
        
    def _validate_date(self, date:str, format:str='%Y-%m-%d')-> bool: # #TODO is this really needed anymore?
        """Attempt to validate a string formatted date

        Args:
            date (str): Unvalidated date.
            format (str, optional): datetime formatting string. Defaults to '%Y-%m-%d'.

        Returns:
            bool: True if valid.
        """
        try:
            validated: datetime = datetime.strptime(date, format)
            return True
        except ValueError:
            return False
        
    def _update_single(self, table:str, id_column:str, item_id:int | str, **update_columns):            
        resp = self.sql.update(table=table, filters={id_column: item_id}, items=update_columns) 
        if resp.status != 'success': #TODO errors
            if resp.reason == 'NO ROWS EFFECTED':
                raise bexc.DoesntExistError(table=table, item=item_id)
            if resp.reason == 'SQLITE_CONSTRAINT_CHECK':
                raise ValueError(resp.result) # Pass on the result
            else:
                raise Exception(f'Failed to update item {item_id} in table {table}.', resp) # Worst case error where nothing was caught
        
    def _delete_single(self, table:str, id_column:str, item_id:int | str):            
        resp = self.sql.delete(table=table, filters={id_column: item_id}) 
        if resp.status != 'success': #TODO errors
            if resp.reason == 'NO ROWS EFFECTED':
                raise bexc.DoesntExistError(table=table, item=item_id)
            else:
                raise Exception(f'Failed to delete item {item_id} in table {table}.', resp) # Worst case error where nothing was caught
    
    def _validation_recovery(self, table:str, error:ValidationError, resp:Status): # Try to recover from errors 
        pass
        
    # # USER ACTIONS # #
    def add_user(self, user_id:int, source:str, display_name:Optional[str]=None, permissions:int = 210):
        """Add a user
        
        Add a single user to the database

        Args:
            user_id (int): UNIQUE ID to identify user.
            source (str): Source of user.  EG: Discord.
            display_name (str): Username/Displayname for user.
            permissions (int, optional): User permissions (see). - UNUSED in V1.0.0
        """
        
        self.logger.debug(f'Adding user {user_id} to database.  source: {source}, display_name: {display_name}.')
        items = {
            'user_id': user_id,
            'display_name':display_name,
            'source': source,
            'permissions': permissions,
            'datetime_created': _iso8601()
            }
        
        resp = self.sql.insert(table='users', items=items)
        if resp.status != 'success': #TODO errors
            self.logger.error(f'Failed to add user: {user_id}. Reason: {resp}')
            if resp.reason == 'SQLITE_CONSTRAINT_PRIMARYKEY': # User already in the database
                raise bexc.UserExistsError(user_id=user_id)
            elif resp.reason == 'SQLITE_MISMATCH': # Invalid data in one of the fields
                raise bexc.WrongTypeError(table='users')
            else: # Can't think of any other issues you could have with this honestly
                raise Exception(f'Failed to add user.', resp)
        else:
            self.logger.debug(f'Added user {user_id}.')
            
        
    def get_user(self, user_id:int) -> dtv.User:
        """Get a single user

        Args:
            user_id (int): User ID.

        Returns:
            dict: User information.
        """
        self.logger.debug(f'Getting user: {user_id}.')
        resp = self.sql.get(table='users', filters={'user_id': user_id})
        return self._single_get(model=dtv.User, resp=resp)
    
    def get_many_users(self, display_name:Optional[str]=None, source:Optional[str]=None, permissions:Optional[int]=None, ids_only:bool=False) -> tuple[dtv.User, ...] | tuple[int, ...]: 
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
        
        filters = {
            'display_name': display_name,
            'source': source,
            'permissions': permissions
            }
        
        resp = self.sql.get(table='users', filters=filters)
        users = self._many_get(typeadapter=dtv.Users, resp=resp)
        if ids_only:
            ids = tuple([user.id for user in users])
            return ids 
        else:
            return users
         
    def update_user(self, user_id: int, source:Optional[str]=None, display_name:Optional[str]=None, overall_wins:Optional[int]=None, change_dollars:Optional[float]=None, change_percent:Optional[float]=None, permissions:Optional[int]=None):
        
        """Update an existing user
        
        Must provide atleast one arg to update in addition to the user_id

        Args:
            user_id (int): User ID.
            display_name (str, optional): Display name.
            permissions (str, optional): Permissions.
            overall_wins (int, optional): Total game wins.
            change_dollars (float, optional): Overall change dollars across all games (completed only).
            change_percent (float, optional): Overall change percent across all games (completed only).
        
        Raises:
            ValueError(Atleast one arg must be changed.): Raised if no args besides user_id are passed.
        """
        
        if not display_name and not permissions and not source: # Must have atleast once of these changed
            raise ValueError('Atleast one arg must be changed.')
        
        self._update_single(
            table="users",
            id_column='user_id',
            item_id=user_id,
            source=source,
            overall_wins=overall_wins,
            change_dollars=change_dollars,
            change_percent=change_percent,
            display_name=display_name,
            permissions=permissions,
            last_updated=_iso8601()
        )
        
    def remove_user(self, user_id:int): 
        """Remove a user

        Args:
            user_id (int): User ID.
        """
        
        self._delete_single(table="users", id_column='user_id', item_id=user_id)
    
    
    # # GAME ACTIONS # #
    def add_game(self, user_id:int, name:str, start_date:str, end_date:Optional[str]=None, starting_money:float=10000.00, pick_date:Optional[str]=None, private_game:bool=False, total_picks:int=10, exclusive_picks:bool=False, sell_during_game:bool=False, update_frequency:dtv.UpdateFrequency='daily'):
        """Add a new game
        
        WARNING: If using realtime, expect issues

        Args:
            user_id (int): Game creators user ID.
            name (str): Name for this game.  Maximum 35 chatacters.
            start_date (str): Start date.  Format: `YYYY-MM-DD`.
            end_date (str, optional): End date.  Format: `YYYY-MM-DD`.  Leave blank for infinite game.
            starting_money (float, optional): Starting money. Defaults to $10000.00.
            pick_date (str, optional): Date stocks must be picked by.  Format: `YYYY-MM-DD`.  If not set, players can join anytime.
            private_game(bool, optional): Whether the game is private (True).  Defaults to public (False).
            total_picks (int, optional): Amount of stocks each user picks. Defaults to 10.
            exclusive_picks (bool, optional): Whether multiple users can pick the same stock.  If enabled, pick date must be on or before start date Defaults to False. - NOT IMPLEMENTED
            sell_during_game (bool, optional): Whether users can sell stocks during the game.  Defaults to False. - NOT IMPLEMENTED
            update_frequency (str, optional): How often prices will update ('daily', 'hourly', 'minute', 'realtime'). Defaults to 'daily'. - NOT IMPLEMENTED
            
        Returns:
            Status: Game creation status.
        """
        #TODO make a Literal for update_frequency
        #TODO accept datetime for date fields
        #TODO maybe this should return the game ID
        # Date formatting validation
        if not self._validate_date(start_date):
            raise bexc.InvalidDateFormatError('Invalid `start_date` format.')
        if end_date: # Enddate stuff
            if not self._validate_date(end_date):
                raise bexc.InvalidDateFormatError('Invalid `end_date` format.')
            if datetime.strptime(start_date, "%Y-%m-%d").date() > datetime.strptime(end_date, "%Y-%m-%d").date():
                raise ValueError('`end_date` must be after `start_date`.')
            
        if pick_date and not self._validate_date(pick_date):
            raise bexc.InvalidDateFormatError('Invalid `pick_date` format.')
        #TODO should we check if pick_date is after end_date?  Doesn't cause an issue, just kinda silly
        
        if exclusive_picks: # Draftmode checks
            if not pick_date:
                raise TypeError('`pick_date` required when `exclusive_picks` is enabled.')
            if datetime.strptime(start_date, "%Y-%m-%d").date() < datetime.strptime(pick_date, "%Y-%m-%d").date(): # Date format is already validated
                raise ValueError('`start_date` must be after `pick_date` when `exclusive_picks` is enabled.')
    
        # Misc
        if update_frequency not in ['daily', 'hourly', 'minute', 'realtime']: #TODO can this use dtv.UpdateFrequency?
            raise ValueError(f'Invalid update frequency {update_frequency}')
        if starting_money < 1.0:
            raise ValueError('`starting_money` must be atleast `1.0`.')
        if total_picks < 1:
            raise ValueError('`total_picks` must be atleast `1`.')
        
        items = {
            'name': name,
            'owner_user_id': user_id,
            'start_money': starting_money,
            'pick_count': total_picks,
            'draft_mode': exclusive_picks,
            'pick_date': pick_date,
            'private_game': private_game,
            'allow_selling': sell_during_game,
            'update_frequency': update_frequency.lower() if update_frequency else None, # Make sure its lowercase
            'start_date': start_date,
            'end_date': end_date,  # is this needed?, no but I like it.
            'datetime_created': _iso8601()
            }

        resp = self.sql.insert(table='games', items=items)
        if resp.status != 'success': #TODO errors
            if resp.reason == 'SQLITE_CONSTRAINT_UNIQUE' and str(resp.result).strip() == 'games.name':
                raise bexc.AlreadyExistsError(table='games', duplicate=name, message='Cannot add multiple games with the same name')

            raise Exception(f'Failed to add game.', resp) 
    
    def get_game(self, game_id:int)-> dtv.Game: # Its always a Games object, but its being a fucking baby
        """Get a single game by ID

        Args:
            game_id (int): Game ID.

        Returns:
            dict: Game information.
        """
        
        self.logger.debug(f'Getting game: {game_id}')
        tobsi_loop = 0 # Issue originally found by @tobsi on discord
        while tobsi_loop < 4: # Should allow it to fix some issues
            tobsi_loop += 1
            resp = self.sql.get(table='games',filters={'game_id': int(game_id)})
            try:
                return self._single_get(model=dtv.Game, resp=resp)
            except ValidationError as exc: # Something has gone terribly wrong
                self.logger.exception(f'Game exists, but validation failed', exc_info=exc)
                # Reset values back to their defaults #TODO add more
                fixes = {} # Empty dictionary
                if 'update_frequency' in str(exc):
                    self.logger.debug(f'Setting update_frequency to \'daily\' for game: {game_id}')
                    fixes['update_frequency'] = 'daily' 
                
                if 'name' in str(exc):
                    self.logger.debug(f'Shortening name to 35 characters for game: {game_id}')
                    name = re.sub(r'[\(\)\[\]/`\\/{}]', '', resp.result[0]['name']) # Clean the name more
                    if tobsi_loop != 0: # We've been here before, add the game ID to the name
                        fixes['name'] = str(str(game_id) + name)[:35] # name string at 35 characters and get rid of shit.  If it fails, remove an extra character
                    else:
                        fixes['name'] = name[:35] # name string at 35 characters and get rid of shit.  If it fails, remove an extra character
                
                if 'status' in str(exc):
                    self.logger.debug(f'Setting status to \'open\' for game: {game_id}')
                    fixes['status'] = 'open' 
                    
                if 'end_date' in str(exc):
                    self.logger.debug(f'Removing end date for game: {game_id}')
                    fixes['end_date'] = 'NULL' 
                
                if len(fixes) == 0:
                    raise ValidationError(str(exc) + 'Unable to fix automatically') # Throw the same error
                else: # Apply fixes
                    apply = self.sql.update(table='games', filters={'game_id': game_id}, items=fixes)
                    if apply.status !='success': 
                        self.logger.error(f'Fix to game: {game_id} failed.  More info: {apply}')

        raise ValidationError('Failed to recover from a validation error loop.')
    
    def get_many_games(self, name:Optional[str]=None, owner_id:Optional[int]=None, include_public:bool=True, include_private:bool=False, include_open:bool=True, include_active:bool=True, include_ended:bool=False)-> tuple[dtv.Game]: # List all games
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
           
        query = """WHERE private_game IN ({privacy})
        AND STATUS IN ({statuses})
        """
        
        values =[]
        if name:
            query += 'AND name LIKE ?'
            values.append(name)
        if owner_id:
            query += 'AND owner_user_id = ?'
            values.append(owner_id)
        
        privacy = [] # privacy

        if include_public:
            privacy.append('0')
        if include_private:
            privacy.append('1')
        
        statuses = [] # status
        if include_open:
            statuses.append('"open"')
        if include_active:
            statuses.append('"active"')
        if include_ended:
            statuses.append('"ended"')
        
        repair= 0
        e = ''
        while repair < 2: # Try this twice
            resp = self.sql.get(table='games', filters=(query.format(statuses='' +','.join(statuses), privacy='' +','.join(privacy)), values))
            repair +=1
            try:
                return self._many_get(typeadapter=dtv.Games, resp=resp)
            except ValidationError as e: # Something bad happened
                self.repair_games() # Repair games and loop again
        
        raise Exception('Failed to repair games', e)
        
    def update_game(self, game_id:int, owner:Optional[int]=None, name:Optional[str]=None, start_date:Optional[str]=None, end_date:Optional[str]=None, status:Optional[str]=None, starting_money:Optional[float]=None, pick_date:Optional[str]=None, private_game:Optional[bool]=None, total_picks:Optional[int]=None, exclusive_picks:Optional[bool]=None, sell_during_game:Optional[bool]=None, update_frequency:Optional[dtv.UpdateFrequency]=None, aggregate_value:Optional[float]=None, change_dollars:Optional[float]=None, change_percent:Optional[float]=None):
        """Update an existing game
        
        Args:
            game_id (int): Game ID.
            owner (Optional[int], optional): New owner ID. 
            name (Optional[str], optional): New game name.  Maximum 35 chatacters.
            start_date (Optional[str], optional): New start date.  Format: `YYYY-MM-DD`.  Cannot be changed once game has started.
            end_date (Optional[str], optional): New end date.  Format: `YYYY-MM-DD`.
            status (Optional[str], optional): Status ('open', 'active', 'ended').  Once start date has passed, game will become 'active'.  Shouldn't be changed manually.
            starting_money (Optional[float], optional): Starting money.  Cannot be changed once game has started.
            pick_date (Optional[str], optional): Pick date.  Format: `YYYY-MM-DD`.  Cannot be changed once game has started.
            private_game (Optional[bool], optional): Game privacy. 
            total_picks (Optional[int], optional): Total picks.  Cannot be changed once game has started.
            exclusive_picks (Optional[bool], optional): Whether multiple users can pick the same stock.  Cannot be changed once game has started.
            sell_during_game (Optional[bool], optional): Whether users can sell stocks during game.
            update_frequency (Optional[str], optional): Price update frequency ('daily', 'hourly', 'minute', 'realtime'. 
            aggregate_value (float, optional): Total value of all game participants stocks.  Shouldn't be changed manually.
            change_dollars (float, optional): aggregate_value - (starting_money * total participants).  Rounded to two decimal points.
            change_percent (float, optional): change_dollars in percent format.  Rounded to two decimal points.
        """

        game = self.get_game(game_id) # Error will be thrown if game can't be found, so anything returned is a game
        if start_date and not self._validate_date(start_date):
            raise bexc.InvalidDateFormatError('Invalid `start_date` format.')
        
        if game.start_date < datetime.today().date():
            if start_date or starting_money or pick_date or exclusive_picks:
                raise ValueError('Cannot update `start_date`, `starting_money`, `pick_date`, or `exclusive_picks` once game has started.')
            
        if end_date: # Enddate stuff
            if not self._validate_date(end_date):
                raise bexc.InvalidDateFormatError('Invalid `end_date` format.')
            if game.start_date > datetime.strptime(end_date, "%Y-%m-%d").date():
                raise ValueError('`end_date` must be after `start_date`.')
            
        if pick_date and not self._validate_date(pick_date):
            raise bexc.InvalidDateFormatError('Invalid `pick_date` format.')
        
        if update_frequency and update_frequency not in ['daily', 'hourly', 'minute', 'realtime']: #TODO can this use dtv.UpdateFrequency?
            raise ValueError(f'Invalid update frequency {update_frequency}')
        if starting_money and starting_money < 1.0:
            raise ValueError('`starting_money` must be atleast `1.0`.')
        if total_picks and total_picks < 1:
            raise ValueError('`total_picks` must be atleast `1`.')
        
        try:
            self._update_single(
                table='games', 
                id_column='game_id', 
                item_id=game_id,
                name=name,
                owner_user_id = owner,
                start_money = starting_money,
                pick_count = total_picks,
                draft_mode = exclusive_picks,
                pick_date = pick_date,
                private_game = private_game,
                allow_selling = sell_during_game,
                status = status,
                update_frequency = update_frequency.lower() if update_frequency else None,
                start_date = start_date,
                end_date = end_date,
                aggregate_value = aggregate_value,
                change_dollars = round(change_dollars, 2) if change_dollars else None,
                change_percent = round(change_percent, 2) if change_percent else None,
                datetime_updated = _iso8601() 
            )
        except ValueError as e: # Raised when Constraint check fails
            if 'CHECK constraint failed:' in str(e):
                raise ValueError(str(e).strip('IntegrityError(\'CHECK constraint failed:').strip(')')) # Pass on just the field that failed #TODO regex
            
    def remove_game(self, game_id:int): 
        """Remove a game

        Args:
            game_id (int): Game ID.
        """
        
        self._delete_single(table='games', id_column='game_id', item_id=game_id)
    
    def repair_games(self):
        # Repair games in database
        resp = self.sql.get(table='games', columns=['game_id']) # Get ALL games
        if resp.status == 'success': # Found games
            assert isinstance(resp.result, tuple)
            for game in resp.result: # Go through games and try to fix them
                self.get_game(game['game_id']) 
    
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
        if resp.status != 'success': 
            if resp.reason == 'SQLITE_CONSTRAINT_UNIQUE' and 'stocks.ticker' in str(resp.result): 
                raise ValueError(f'Stock with ticker {ticker} already exists.')
            else:
                raise Exception(f'Failed to add stock.', resp)
    
    def get_stock(self, ticker_or_id:str | int)-> dtv.Stock:
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
        return self._single_get(model=dtv.Stock, resp=resp)
        
    def get_many_stocks(self, company_name:Optional[str]=None, exchange:Optional[str]=None, tickers_only:bool=False)-> tuple[dtv.Stock]:
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

        resp = self.sql.get(table='stocks', filters=filters)
        stocks = self._many_get(typeadapter=dtv.Stocks, resp=resp)
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
            self._delete_single(table='stocks', id_column='stock_id', item_id=ticker_or_id)
        else: # Ticker
            self._delete_single(table='stocks', id_column='ticker', item_id=ticker_or_id)

    
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
            
        stock_id = self.get_stock(ticker_or_id).id #If stock is invalid, an error will be thrown anyway.
        
        items = {
            'stock_id':int(stock_id), 
            'price': float(price), 
            'datetime': str(datetime)
            }
        
        resp = self.sql.insert(table='stock_prices', items=items)
        if resp.status != 'success': #TODO errors
                raise Exception(f'Failed to add stock price for {ticker_or_id}.', resp)
    
    def get_stock_price(self, price_id:int) -> dtv.StockPrice:
        """Get a single stock price by ID.

        Args:
            price_id (int): Price ID.

        Returns:
            dict: Stock price information.
        """
        resp = self.sql.get(table='stock_prices', filters={'price_id': price_id})
        return self._single_get(model=dtv.StockPrice, resp=resp)
    
    def get_many_stock_prices(self, stock_id:Optional[int]=None, datetime:Optional[str]=None)-> tuple[dtv.StockPrice]: # List stock prices, allow some filtering 
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
            ('LIKE', 'datetime'): datetime + '%' # Match like objects #TODO NOT 100% INJECTION SAFE
            } 

        resp = self.sql.get(table='stock_prices',filters=filters, order=order) 
        return self._many_get(typeadapter=dtv.StockPrices, resp=resp)
    
    
    # # STOCK PICK ACTIONS # #
    def add_stock_pick(self, participant_id:int, stock_id:int,): # This is essentially putting in a buy order. End users should not be interacting with this directly    
        """Add a stock pick

        Args:
            participant_id (int): Participant ID.
            stock_id (int): Stock ID.
        
        Raises:
            bexc.NotAllowedError: reason=Not active.  Player status isn't active, so cannot pick stocks
            get_participant > bexc.DoesntExistError: Player not in game
            bexc.NotAllowedError: reason=Past pick_date.  (only possible if a pick date is set).
            bexc.NotAllowedError: reason=Maximum picks reached.  Player already has the maximum amount of stock picks.
            bexc.AlreadyExistsError: Cannot buy the same stock twice.
            Exception: Some other issues ocurred
        """
        
        player = self.get_participant(participant_id)
        if player.status != 'active':
            raise bexc.NotAllowedError(action='add_stock_pick', reason='Not active', message=f'Player status is {player.status}.  Must be active to pick stocks')

        
        game = self.get_game(game_id=player.game_id) 
        if game.pick_date and game.pick_date < datetime.today().date(): # Check that pick date hasn't passed
            raise bexc.NotAllowedError(action='add_stock_pick', reason='Past pick_date', message='Cannot pick stock once pick date has passed')
        
        try:
            picks = self.get_many_stock_picks(participant_id=participant_id, status=['pending_buy', 'owned', 'pending_sell'])
            if len(picks) >= game.pick_count: 
                raise bexc.NotAllowedError(action='add_stock_pick', reason='Maximum picks reached', message='Player already has maximum amount of picks')
            
        except LookupError as e: # Should only be raised if no stocks are present
            pass
            
        items = {
            'participation_id':participant_id,
            'stock_id':stock_id,
            'datetime_updated': _iso8601()
            }
        
        resp = self.sql.insert(table='stock_picks', items=items)
        if resp.status != 'success': #TODO errors
            if resp.reason =='SQLITE_CONSTRAINT_UNIQUE':
                raise bexc.AlreadyExistsError(table='add_picks', duplicate={'participant_id': participant_id, 'stock_id':stock_id }, message='Cannot buy the same stock twice')
                
            raise Exception(f'Failed to add pick.', resp)
    
    def get_stock_pick(self, pick_id:int)-> dtv.StockPick:
        """Get a single stock pick

        Args:
            pick_id (int): Pick ID.

        Returns:
            dict: Single stock pick
        """
        
        resp = self.sql.get(table='stock_picks', filters={'pick_id': pick_id})
        return self._single_get(model=dtv.StockPick, resp=resp)
    
    def get_many_stock_picks(self, participant_id:Optional[int]=None, status:Optional[str | list]=None, stock_id:Optional[int]=None, include_tickers:bool=False)-> tuple[dtv.StockPick]: 
        """List stock picks.  Optionally, filter by a status or participant ID
        
        Stocks will be ordered from best performance to worst (by percent)

        Args:
            participant_id (int, optional): Filter by a participant ID.
            status (str | list, optional): Filter by a status(es) ('pending_buy', 'owned', 'pending_sell', 'sold').
            stock_id(int, optional): Filter by stock ID.
            include_tickers(bool, optional):  Include the ticker when getting the stocks
            
        Returns:
            list: List of stock picks
        """
        valid_statuses = ['pending_buy', 'owned', 'pending_sell', 'sold']
        left_str = None
        filters = { 
            'participation_id': participant_id,
            'stock_id': stock_id
            }
        if status: # validate statuses
            statuses = []
            if isinstance(status, str):
                status = [status]
            for st in status: # Chec kthat 
                if st not in valid_statuses:
                    raise ValueError(f'invalid `status` {st}.')
                statuses.append(f'"{st}"') # Add valid statues
            filters.update({('IN', 'status'): "" + ",".join(statuses)})
            
        if include_tickers: # Run a left_join
            left_str = 'LEFT JOIN stocks ON stocks.stock_id = stock_picks.stock_id\n'#IDK if the \n is needed
        
        resp = self.sql.get(table='stock_picks', left_join=left_str, filters=filters, order={'change_percent': 'DESC', 'change_dollars': 'DESC'})
        return self._many_get(typeadapter=dtv.StockPicks, resp=resp)

    def update_stock_pick(self, pick_id:int, current_value:float,  shares:Optional[float]=None, start_value:Optional[float]=None,  status:Optional[str]=None, change_dollars:Optional[float]=None, change_percent:Optional[float]=None): #Update a single stock pick
        """Update a stock pick

        Args:
            pick_id (int): Pick ID.
            current_value (float): Current value (shares * current stock price)
            shares (Optional[float], optional): Shares.
            start_value (Optional[float], optional): Starting value of pick.
            status (Optional[str], optional): Status ('pending_buy', 'owned', 'pending_sell', 'sold').
            change_dollars (float, optional): current_value - (games.starting_money).  Rounded to two decimal points.
            change_percent (float, optional): change_dollars in percent format.  Rounded to two decimal points.
        """
        
        self._update_single(
            table='stock_picks',
            id_column='pick_id',
            item_id=pick_id,
            

            shares = shares,
            start_value = start_value,
            current_value = current_value,
            status = status,
            change_dollars = round(change_dollars, 2) if change_dollars else None,
            change_percent = round(change_percent, 2) if change_percent else None,
            datetime_updated = _iso8601()
        )
    
    def remove_stock_pick(self, pick_id:int):
        """Remove a stock pick
        
        Will not prevent owned stocks from being removed.

        Args:
            pick_id (int): Pick ID.
        """
        
        self._delete_single(table="stock_picks", id_column='pick_id', item_id=pick_id)
        

    # # GAME PARTICIPATION ACTIONS # #
    def add_participant(self, user_id:int, game_id:int, team_name:Optional[str]=None):
        """Add a game participant
        
        Cannot add participant to a game that has already started.
                
        Args:
            user_id (int): User ID.
            game_id (int): Game ID.
            team_name (Optional[str], optional): Nickname for this specific game.
        
        Raises:
            ValueError('`pick_date` has passed.'): The pick date for the game has already passed, so the player cannot be added.
            ValueError('Already in game.'): The participant ID is already in the game.
        """
        game = self.get_game(game_id=game_id)
        if game.start_date < datetime.today().date() and (game.pick_date and game.pick_date < datetime.today().date()):
            raise ValueError('`pick_date` has passed.')
        if game.private_game and game.owner_id != user_id: # Otherwise the owner is pending lol
            status = 'pending'
        else:
            status = 'active'
        items = {
            'user_id':user_id, 
            'game_id':game_id,
            'name': team_name,
            'status': status,
            'datetime_joined': _iso8601()
            }
    
        resp = self.sql.insert(table='game_participants', items=items)
        if resp.status != 'success': #TODO errors
            if resp.reason == 'SQLITE_CONSTRAINT_UNIQUE' and 'game_participants.user_id, game_participants.game_id' in str(resp.result):
                raise ValueError('Already in game.')
            
            raise Exception(f'Unexpected error while adding player.', resp)
        
    def get_participant(self, participant_id:int)-> dtv.GameParticipant: # Get game player info
        """Get a game participant's information

        Args:
            participant_id (int): Participant ID.

        Returns:
            dict: Participant information.
        """

        resp = self.sql.get(table='game_participants', filters={'participation_id': participant_id})
        try:
            return self._single_get(model=dtv.GameParticipant, resp=resp)
        except LookupError:
            raise bexc.DoesntExistError(table='game_participants', item=participant_id, message='Player not in game')

    def get_many_participants(self, game_id:Optional[int]=None, user_id:Optional[int]=None, status:Optional[str]=None, sort_by_value:bool=False)-> tuple[dtv.GameParticipant]:
        """Get multiple participants

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
        return self._many_get(typeadapter=dtv.GameParticipants, resp=resp)
    
    def update_participant(self, participant_id:int, team_name:Optional[str]=None, status:Optional[str]=None, current_value:Optional[float]=None, change_dollars:Optional[float]=None, change_percent:Optional[float]=None):
        """Update a game participant

        Args:
            participant_id (int): Participant ID.
            name (Optional[str], optional): Team name.
            status (Optional[str], optional): Status ('pending', 'active', 'inactive').
            current_value (Optional[float], optional): Current portfolio value.
            change_dollars (float, optional): current_value - (starting_money / total_picks).  Rounded to two decimal points.
            change_percent (float, optional): change_dollars in percent format.  Rounded to two decimal points.
        """
        
        self._update_single(
            table='game_participants',
            id_column='participation_id',
            item_id=participant_id,
            name = team_name,
            status = status,
            current_value = current_value,
            change_dollars = round(change_dollars, 2) if change_dollars else None,
            change_percent = round(change_percent, 2) if change_percent else None,
            datetime_updated = _iso8601()
            )
        
    def remove_participant(self, participant_id:int):
        """Remove a game participant

        Args:
            participant_id (int): Participant ID.
        """
        
        self._delete_single(table='game_participants', id_column='participant_id', item_id=participant_id)
        
  
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
        
        try:
            market = yf.Market('US')
            return False if market.status == 'closed' else True
        except: #TODO log
            pass
        
        # ALL OF THIS IS JUST IN CASE WE STOP USING YAHOO FINANCE
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
        
        try:
            games = self.be.get_many_games(include_private=True) # Get all games
        except LookupError:
            return # No games

        for game in games: #TODO add log here
            
            # Start and end games
            if game.status == 'open' and game.start_date <= datetime.strptime(_iso8601('date'), "%Y-%m-%d").date(): # Set games to active
                self.be.update_game(game_id=game.id, status='active')
            if game.status == 'active' and game.end_date and game.end_date < datetime.strptime(_iso8601('date'), "%Y-%m-%d").date(): #Game has ended
                self.be.update_game(game_id=game.id, status='ended')

    def update_stock_prices(self):
        """Find and update stock prices for all stocks currently in games (pending picks are included)
        
        Uses yfinance API.
        """
        #TODO Skip holidays
        #TODO allow after hours data to be added here as long as its tagged?
        #TODO don't run too often
        # Only get active stocks (stocks from games that are running)
        query = """
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
        
        try:
            resp = self.be.sql.get(table='stocks', filters=query)
            active_stocks = self.be._many_get(typeadapter=dtv.Stocks, resp=resp)
        except LookupError:
            return # No stocks

        #tickers = [tkr.ticker for tkr in active_stocks]
        if len(active_stocks) > 0:
            market_open = self._is_market_hours()
            for ticker in active_stocks:
                basic_info = yf.Ticker(ticker.ticker).fast_info # Hopefully speed this up
                if basic_info['quote_type'] != 'EQUITY': #TODO decide what should happen if someone manages this
                    self.logger.error(f'Ticker {ticker} is not tradeable! Skipping')
                    continue
                
                if market_open:
                    price = basic_info['last_price'] 
                else:
                    price = basic_info['regular_market_previous_close'] 
                    
                try:
                    self.be.add_stock_price(ticker_or_id=ticker.ticker, price=price, datetime=_iso8601()) # Update pricing
                except Exception as e:
                    self.logger.exception(e) # Log exception
                    pass #TODO find problems if/when they appear
    
    def update_stock_picks(self, game_id:Optional[int]=None) -> None:
        """Update all owned and pending stock picks with current prices
        
        - Validates game type of daily, but nothing else for now
        - Adds pending_buy stock picks for users (depending on time)
        - Update owned stock pick values

        Args:
            game_id (Optional[int], optional): Game ID.  If blank, all games will be checked/run
        """
        
        try:        
            if game_id:
                self.logger.debug(f'Updating stock picks for single game: {game_id}')
                games = [self.be.get_game(game_id=game_id)] # TODO flag that the checked game specifically did not update
            else:
                self.logger.debug(f'Updating stock picks for games')
                games = self.be.get_many_games(include_open=False, include_active=True, include_private=True) # Only active games
            
        except LookupError as e:
            self.logger.exception(f'Failed to update stock picks', exc_info=e)
            return # No games
        
        for game in games:
            if game.update_frequency == 'daily' and self._is_market_hours():
                self.logger.info(f'Not updating stock picks for game: {game.id} because update_frequency is daily and market is still open')
                continue # daily game, currently in market hours, don't run
            self.logger.debug(f'Updating stock picks for game: {game.id}')
            pending_and_owned_query = """
            WHERE status IN ("pending_buy", "owned")
            AND participation_id IN (SELECT participation_id
                FROM game_participants
                WHERE status = "active"
                AND game_id = ?
                )
            """ #TODO instead of setting games to active, just use start and end date?
            try:
                resp = self.be.sql.get(table='stock_picks', filters=(pending_and_owned_query, [game.id]))
                picks:tuple[dtv.StockPick, ...] = self.be._many_get(typeadapter=dtv.StockPicks, resp=resp)
                pass
            except LookupError:
                self.logger.debug(f'No stock picks to update for game: {game.id}')
                continue # No picks
            
            for pick in picks:
                assert isinstance(pick.id, int)
                assert isinstance(pick.stock_id, int)
                if game.update_frequency == 'daily' and pick.status == 'owned' and datetime.strptime(str(pick.last_updated), "%Y-%m-%d %H:%M:%S") + timedelta(hours=8 ) > datetime.now():
                    self.logger.debug(f'Skipping stock pick: {pick.id} in game: {game_id} because update_frequency is daily, and it was last updated less than 8 hours ago')
                    continue # Skip picks with daily update frequency that have been updated in the last 12 hours
                try:
                    price = self.be.get_many_stock_prices(stock_id=int(pick.stock_id),datetime=_iso8601('date'))[0]
                except LookupError as e:
                    self.logger.exception(e) #TODO any change this causes more problems?
                    continue
                
                #TODO check datetime here and decide if price should be used
                buying_power = None,
                shares = None
                start_value = None
                status = None
                
                if pick.status == 'pending_buy':
                    buying_power = float(game.start_money / game.pick_count) # Amount available to buy this stock (starting money divided by picks)
                    shares = buying_power / price.price# Total shares owned
                    start_value = current_value = round(float(shares * price.price), 2)
                    dollar_change = 0
                    percent_change = 0
                    status = 'owned'
                
                else: # Stock is owned 
                    assert isinstance(pick.shares, float) # Owned stocks would have to have this
                    assert isinstance(pick.start_value, float) # Owned stocks would have to have this
                    current_value = float(pick.shares * price.price)
                    dollar_change = current_value - pick.start_value
                    percent_change = (dollar_change / pick.start_value) * 100
                self.be.update_stock_pick(pick_id=pick.id,shares=shares, start_value=start_value, current_value=current_value, status=status, change_dollars=dollar_change, change_percent=percent_change) # Update

    def update_participants_and_games(self, game_id:Optional[int]=None):
        """Update game participant and game information
        
        - Participant portfolio value
        - Game Aggregate value

        Args:
            game_id (Optional[int], optional): Game ID.  If blank, all active games will be updated.
        """
        try:        
            if game_id:
                games = [self.be.get_game(game_id=game_id)] # TODO flag that the checked game specifically did not update
            else:
                games = self.be.get_many_games(include_open=False, include_active=True) # Only active games
                
        except LookupError:
            return # No games
        for game in games:
            aggr_val = 0
            if game.status != 'active':
                return "Game not active"
            try:
                players = self.be.get_many_participants(game_id=game.id, status='active')
            except LookupError:
                continue # No players
                
            for player in players:
                portfolio_value = 0.0
                try:
                    picks = self.be.get_many_stock_picks(participant_id=player.id, status='owned')
                except LookupError: # Skip games with no picks 
                    continue
                      
                for pick in picks:
                    assert isinstance(pick.current_value, float)
                    portfolio_value += pick.current_value
                dollar_change = portfolio_value - game.start_money
                percent_change = (dollar_change / game.start_money) * 100
                self.be.update_participant(participant_id=player.id, current_value=portfolio_value, change_dollars=dollar_change, change_percent=percent_change)
                aggr_val += portfolio_value
            
            game_dollar_change = aggr_val - (game.start_money * len(players))
            game_percent_change =  (game_dollar_change / (game.start_money * len(players))) * 100 
            self.be.update_game(game_id=game.id, aggregate_value=aggr_val, change_dollars=game_dollar_change, change_percent=game_percent_change)
               
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
        """Find and add a stock to database

        Args:
            ticker (str): Stock ticker.  Eg: 'MSFT'.
            
        Raises:
            ValueError: Stock is not tradeable
            ValueError: Unable to find stock
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
            except exceptions.HTTPError: # Just fully gives up
                raise ValueError('Unable to find stock')
                
            if len(info) > 0: # Try to verify ticker is real and get the relevant infos
                if info['quoteType'] != 'EQUITY': # Stock can no longer be traded
                    raise ValueError('Stock is not tradeable')
                self.be.add_stock(ticker=ticker.upper(),
                    exchange=info['fullExchangeName'], #TODO this fails with CLR stock
                    company_name=info['displayName'] if 'displayName' in info else info['shortName'])
            else:
                raise ValueError(f'Failed to add `ticker` {ticker}.')
        pass

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
        self.logger = logging.getLogger('StockGameLogic')
        self.source = source if source else 'Frontend'
        self.be = Backend(database_name)
        self.gl = GameLogic(database_name) # Handle game logic
        self.default_perms = default_permissions
        self.register(user_id=owner_user_id, source=self.source) # Try to register user
        self.be.update_user(user_id=owner_user_id, permissions=288)
        self.owner_id = int(owner_user_id)
    
    def _user_owns_game(self, user_id:int, game_id:int): # Check if a user owns a specific game
        """Check whether a user owns a specific game

        Args:
            user_id (int): User ID.
            game_id (int): Game ID.

        Returns:
            bool: True if owned, False if not.
        """
        self.logger.debug(f'Checking if user: {user_id} owns game: {game_id}')
        try:
            game = self.be.get_game(game_id=game_id)
        except LookupError as e: # TODO log this in the main bit
            self.logger.error(f'Game: {game_id} does not exist')
            raise LookupError(e)
        
        if game.owner_id != user_id:
            self.logger.debug(f'User: {user_id} does not own game: {game_id}')
            return False
        else:
            self.logger.debug(f'User: {user_id} owns game: {game_id}')
            return True
        
    def _participant_id(self, user_id:int, game_id:int)-> int:
        """Get a game participant ID

        Args:
            user_id (int): User ID.
            game_id (int): Game ID.

        Returns:
           int: Participant ID
        """
        
        self.register(user_id) # Must try to register user
        players = self.be.get_many_participants(user_id=user_id, game_id=game_id)
        if len(players) == 1:
            return players[0].id
        else:
            raise ValueError(f'Expected one participant ID, but got {len(players)}.')
    
    def _get_game_name(self, game_id:int): # Get a game name from ID
        """Get game name from ID

        Args:
            game_id (int): Game ID.

        Raises:
            LookupError: Game not found if ID is invalid

        Returns:
            str: Game name
        """
        
        self.logger.debug(f'Getting game name for game: {game_id}')
        game_info = self.be.get_game(game_id)
        return str(game_info.name)
    
    def clean_text(self, text:str) -> str:
        """
        Helper function to clean text input, to prevent users from injecting formatting that breaks embeds. 
        Only removes formatting that causes line breaks or links.
        """
        text = re.sub(r'[\(\)\[\]/`\\/{}]', '', text) # Remove stupid characters
        return text

    # # GAME RELATED # #
    def new_game(self, user_id:int, name:str, start_date:str, end_date:Optional[str]=None, starting_money:float=10000.00, pick_date:Optional[str]=None, private_game:bool=False, total_picks:int=10, exclusive_picks:bool=False, sell_during_game:bool=False, update_frequency:dtv.UpdateFrequency='daily'):
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
            exclusive_picks (bool, optional): Whether multiple users can pick the same stock.  If enabled, pick date must be on or before start date Defaults to False. - NOT IMPLEMENTED
            sell_during_game (bool, optional): Whether users can sell stocks during the game.  Defaults to False. - NOT IMPLEMENTED
            update_frequency (str, optional): How often prices will update ('daily', 'hourly', 'minute', 'realtime'). Defaults to 'daily'. - NOT IMPLEMENTED
        """
    
        try: # Try create user
            user = self.register(user_id=user_id)  
        except bexc.UserExistsError: # User was already there, my bad
            self.logger.info(f'User with ID {user_id} already exists.')
            pass #TODO log
        

        try:  # Create game
            self.be.add_game(
                user_id=user_id,
                name=self.clean_text(name)[:35], # Limit to 35
                start_date=start_date,
                end_date=end_date,
                starting_money=starting_money,
                pick_date=pick_date,
                total_picks=total_picks,
                private_game=private_game,
                exclusive_picks=exclusive_picks,
                sell_during_game=sell_during_game,
                update_frequency=update_frequency
                )
        except Exception as e: #TODO find errors?
            raise e
        
        try:
            games = self.be.get_many_games(name=name, owner_id=user_id, include_private=True)
            if len(games) == 1:
                self.be.add_participant(user_id=user_id, game_id=games[0].id)
        except LookupError: # Game wasn't found for some reason
            self.logger.warning('Game was created but owner could not be added.')
        except ValueError as exc:
            self.logger.warning(f'Game was created but owner could not be added.  Reason: {exc}')
        
       
    
    def list_games(self, include_public:bool=True, include_private:bool=False, include_open:bool=True, include_active:bool=True, include_ended:bool=False): 
        """List games
        
        Args:
            include_public (bool, optional): Include public games in results. Defaults to True.
            include_private (bool, optional): Include private games in results. Defaults to False.
            include_open (bool, optional): Include open games in results. Defaults to True.
            include_active (bool, optional): Include active games in results. Defaults to True.
            include_ended (bool, optional): Include ended games in results. Defaults to False.
        Returns:
            list: List of games
        """
        games = self.be.get_many_games(include_private=include_private, include_public=include_public, include_active=include_active, include_open=include_open, include_ended=include_ended)
        return games
    
    def game_info(self, game_id:int, show_leaderboard:bool=True) -> dtv.GameInfo: 
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
        
        game.current_value = round(game.current_value, 2) if game.current_value else 0# Round to two decimal places
        info = {
            'game': game,
        }
        if show_leaderboard:
            leaderboard = list()
            try:
                players = self.be.get_many_participants(game_id=game_id, sort_by_value=True)
                for player in players:
                    user = self.be.get_user(player.user_id)
                    leaderboard.append({ 
                        'user_id': int(player.user_id),
                        'current_value': round(player.current_value, 2) if player.current_value else 0, # Round to two decimal places
                        'joined': player.datetime_joined
                    }) # Should keep order
                    
            except LookupError: # No players in game
                self.logger.info(f'No players are currently in game: {game_id}')
                
            info['leaderboard'] = leaderboard  # type: ignore WAA I DONT FUCKING CARE I KNOW THIS WORKS
        return dtv.GameInfo.model_validate(info)
    
    # # USER RELATED
    def register(self, user_id:int, source:Optional[str]=None, username:Optional[str]=None): #TODO should this be an internal function?
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
        except bexc.UserExistsError: # user already exists
            return "User already registered"

    def change_name(self, user_id:int, name:str):
        """Change your display name (nickname).

        Args:
            user_id (int): User ID.
            name (str): New name.
        
        Raises:
            update_user > bexc.DoesntExistError: Attempted to update a user who doesn't exist.
        """
         
        self.register(user_id) # Must try to register user
        self.be.update_user(user_id=int(user_id), display_name=str(name)) 
    
    def join_game(self, user_id:int, game_id:int, name:Optional[str]=None):
        """Join a game.

        Args:
            user_id (int): User ID.
            game_id (int): Game ID.
            name (str, optional): Team name/nickname for game.
        
        Raises:
            add_participant > bexc.DoesntExistError: Attempted to join a game that doesn't exist
        """
        self.register(user_id) # Must try to register user
        try:
            self.be.add_participant(user_id=int(user_id), game_id=int(game_id), team_name=str(name))
        except LookupError:
            raise LookupError('Game not found.')
            
    def my_games(self, user_id:int, include_ended:bool=False)->dtv.MyGames:
        """Get a list of your current games

        Args:
            user_id (int): User ID.
            include_ended (bool, optional): Whether to include past games.  Defaults to False.

        Returns:
            dict: User information along with current games
        """
        #TODO should this alow filtering for inactive games, etc.?
        self.register(user_id) # Must try to register user
        try:
            players = self.be.get_many_participants(user_id=int(user_id))
        except LookupError:
            raise LookupError('Player is not in any games.')
        games = {
            'user': self.be.get_user(user_id=user_id), # User details
            'games': [] # Game details will be stored here
            }
        for player in players: # Provide additional details
            game = self.be.get_game(player.game_id)
            if game.status != 'ended' or include_ended: # Add games that are active or all games if include ended
                games['games'].append(game)

        return dtv.MyGames.model_validate(games)
    
    def my_stocks(self, user_id:int, game_id:int, show_pending:bool=True, show_sold:bool=False):
        """Get your stocks for a specific game
        
        Includes stock tickers!

        Args:
            user_id (int): User ID.
            game_id (int): Game ID.
            show_pending (bool, optional): Whether to show pending purchases. Defaults to False (no).
            show_sold (bool, optional): Whether to sold stocks. Defaults to False (no).

        Returns:
            list: Stocks both owned and pending

        Raises:
        self.register(user_id) # Must try to register user
            _participant_id > bexc.DoesntExistError: Player not in game
            get_many_stock_picks > LookupError: No items found.  Raised when no stocks are found
            
        """
        
        self.register(user_id) # Must try to register user
        player_id = self._participant_id(user_id=user_id, game_id=game_id)
        picks = self.be.get_many_stock_picks(participant_id=player_id,status=['pending_buy', 'owned', 'pending_sell'], include_tickers=True)            
        return picks
    
    # # STOCK RELATED
    def buy_stock(self, user_id:int, game_id:int, ticker:str):
        """Pick/buy a stock
        
        Prevents users from picking too many stocks, or picking stocks if the game has already started and the pick date has passed.

        Args:
            user_id (int): User ID.
            game_id (int): Game ID.
            ticker (str): Ticker.
            
        Raises:
            ValueError: Invalid Ticker, too long!
            _participant_id > bexc.DoesntExistError: Player not in game
            _participant_id > LookupError: Game or player doesn't exist
            find_stock > ValueError: Stock is not tradeable.  Stock existed at some point, but cannot be traded
            find_stock > ValueError: Unable to find stock.  HTTP error when searching for stock, assume it doesn't exist
            find_stock > ValueError: Failed to add stock (usually means the stock doesn't exist)
            add_stock_pick > bexc.NotAllowedError: reason='Not active'.  Player status isn't active, so cannot pick stocks
            add_stock_pick > bexc.NotAllowedError: reason='Past pick_date'.  (only possible if a pick date is set).
            add_stock_pick > bexc.NotAllowedError: reason='Maximum picks reached'.  Player already has the maximum amount of stock picks.
            add_stock_pick > bexc.AlreadyExistsError: Cannot own the same stock twice.
            add_stock_pick > Exception: Some other issues ocurred.
            
        """ #TODO should this return picks remaining? Could also add that as another function
        
        if len(str(ticker)) > 5:
            raise ValueError('Invalid Ticker, too long!')
        
        self.register(user_id) # Must try to register user
        player_id = self._participant_id(user_id=user_id, game_id=game_id) # If user doesn't exist in the game, error will be raised
        self.gl.find_stock(ticker=str(ticker))  # This will add the stock
        stock = self.be.get_stock(ticker_or_id=str(ticker)) # This should only run if the stock was added successfully
        self.be.add_stock_pick(participant_id=player_id, stock_id=stock.id) # Add the pick

    def sell_stock(self, user_id:int, game_id:int, ticker:str): # Will also allow for cancelling an order #TODO add sell_stock
        self.register(user_id) # Must try to register user
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
        self.register(user_id) # Must try to register user
        player_id = self._participant_id(user_id=user_id, game_id=game_id) #TODO check for errors
        stock = self.be.get_stock(ticker_or_id=ticker)
        try:
            picks = self.be.get_many_stock_picks(participant_id=player_id, stock_id=stock.id)
        except LookupError:
            raise LookupError('No picks found')
        if len(picks) > 1: # IDK how you'd even get this to happen.
            raise ValueError(f'Found {len(picks)} matching picks. Cannot remove more than 1 pick at a time.')
        
        if picks[0].status in ['pending_buy']:
            return self.be.remove_stock_pick(pick_id=picks[0].id)
        else:
            raise ValueError(f'Pick status is `{picks[0].status}`.  Only `pending_buy` picks can be removed.')
    
    # # OTHER # #
    def start_draft(self, user_id:int, game_id:int): #TODO add
        pass
    
    def force_update(self, user_id:int, game_id:Optional[int]=None, enforce_permissions:bool=True):
        """Force update game(s)

        Args:
            user_id (int): User ID.
            game_id (Optional[int], optional): Game ID. If blank, all games will be updated.
            enforce_permissions (bool): Disable to bypass permission checking.
        """
        self.register(user_id) # Must try to register user
        if (user_id != self.owner_id) and enforce_permissions:
            raise PermissionError(f'User {user_id} is not allowed to manage game {game_id}')

        
        self.gl.update_all(game_id=game_id, force=True) # 
        
    def manage_game(self, user_id:int, game_id:int, owner:Optional[int]=None, name:Optional[str]=None, start_date:Optional[str]=None, end_date:Optional[str]=None, status:Optional[str]=None, starting_money:Optional[float]=None, pick_date:Optional[str]=None, private_game:Optional[bool]=None, total_picks:Optional[int]=None, exclusive_picks:Optional[bool]=None, sell_during_game:Optional[bool]=None, update_frequency:Optional[str]=None, enforce_permissions:bool=True):
        """Update/Manage an existing game.
        
        start_date, starting_money, pick_date, total_picks, exclusive_picks, sell_during_game cannot be changed once a game has started

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
            exclusive_picks (bool, optional): Whether multiple users can pick the same stock. Pick date must be on or before start date. Cannot be changed once game has started.
            sell_during_game (bool, optional): Whether users can sell stocks during the game. Defaults to False. Cannot be changed once game has started.
            update_frequency (str, optional): How often prices should update ('daily', 'hourly', 'minute', 'realtime').
            enforce_permissions (bool): Disable to bypass permission checking.

        Raises:
            dict: Status/result
        """
        self.register(user_id) # Must try to register user
        self.logger.debug(f'User: {user_id} is updating game: {game_id}.  Settings[Owner: {owner}, name: {name}, tbd]')
        if (self._user_owns_game(user_id=user_id, game_id=game_id) == False and user_id != self.owner_id) and enforce_permissions:
            self.logger.error(f'User {user_id} is not allowed to make changes to game {game_id}')
            raise PermissionError(f'User {user_id} is not allowed to make changes to game {game_id}')
        
        self.be.update_game(game_id=game_id, owner=owner, name=name, start_date=start_date, end_date=end_date, status=status, starting_money=starting_money, pick_date=pick_date, private_game=private_game, total_picks=total_picks, exclusive_picks=exclusive_picks, sell_during_game=sell_during_game, update_frequency=update_frequency)
        
    def remove_game(self, user_id:int, game_id:int, enforce_permissions:bool=True):
        """Remove a game
        
        Only the games creator or the bots owner can remove a game!

        Args:
            user_id (int): User ID. (Must be the game owner OR the bot owner)
            game_id (int): Game ID.
            enforce_permissions (bool): Disable to bypass permission checking.

        Raises:
            PermissionError: Raised if someone who isn't allowed to remove the game tries
        """
        
        self.register(user_id) # Must try to register user
        if (not self._user_owns_game(user_id=user_id, game_id=game_id) or user_id != self.owner_id) and enforce_permissions:
            raise PermissionError(f'User {user_id} is not allowed to make changes to game {game_id}')
        
        self.be.remove_game(game_id)
    
    def pending_game_users(self, user_id:int, game_id:int, enforce_permissions:bool=True):
        """Get a list of pending users for private games

        Args:
            user_id (int): User ID.
            game_id (int): Game ID.
            enforce_permissions (bool): Disable to bypass permission checking.

        Returns:
            list: Pending users (including participant ID)
        """
        self.register(user_id) # Must try to register user
        if (not self._user_owns_game(user_id=user_id, game_id=game_id) or user_id != self.owner_id) and enforce_permissions:
            raise PermissionError(f'User {user_id} is not allowed to manage players for game {game_id}')
        try:
            return self.be.get_many_participants(game_id=game_id, status='pending')
        except ValueError: # no pending users, return empty list 
            return () #TODO problem?
        
    def approve_game_users(self, user_id:int, game_id:int, approved_user_id:int, enforce_permissions:bool=True):
        """Approve/add a user to private game
        
        Only the bot owner or game owner can approve users for a game by default

        Args:
            user_id (int): User ID (command runner).
            game_id (int): Game ID.
            approved_user_id (int): User ID to approve.
            enforce_permissions (bool): Disable to bypass permission checking.

        Returns:
            dict: status
        """
        
        self.register(user_id) # Must try to register user
        player_id = self._participant_id(user_id=approved_user_id, game_id=game_id) #TODO check for errors
        if (not self._user_owns_game(user_id=user_id, game_id=game_id) or user_id != self.owner_id) and enforce_permissions:
            raise PermissionError(f'User {user_id} is not allowed to approve players for game {player_id}')
        
        #TODO errors!
        self.be.update_participant(participant_id=player_id, status='active')

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
    game.gl.find_stock(ticker='COST')
    game.gl.update_all()
    game.be.add_stock(ticker='YM=F',exchange='fake', company_name='fake')
    game.be.update_game(1, update_frequency='hourly')