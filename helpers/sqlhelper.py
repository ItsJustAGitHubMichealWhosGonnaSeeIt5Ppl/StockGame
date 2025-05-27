# # DO NOT MAKE ANY CHANGES TO THIS VERSION PLEASE.  IT IS GOING TO BE MOVED INTO ITS OWN MODULE # #

# Misc helpers
import sqlite3
from datetime import datetime
import functools
import logging
from typing import Optional, Literal
from datetime import datetime
from pydantic import BaseModel, ConfigDict

MainStatus = Literal['success', 'error']

class Status(BaseModel): # Status item
    model_config = ConfigDict(arbitrary_types_allowed=True)
    status: str
    reason: str
    result: Optional[str | int | dict | tuple | Exception] = None
    more_info: Optional[str | int | dict | tuple | Exception] = None

def _unix_timestamp(): # Get a unix timestamp
    """Creates a unix timestamp from the current time

    Returns:
        int: Unix timestamp for NOW
    """
    return int(datetime.now().timestamp())

def _iso8601(date_type:str='datetime'): # 
    """Get an ISO formatted date or datetime

    Args:
        date_type (str, optional): Toggle between 'date' or 'datetime'. Defaults to 'datetime'.

    Raises:
        ValueError: _description_

    Returns:
        str: Date/datetime
    """
    now = datetime.now()
    date_type = date_type.lower() # Easier to work with
    if date_type == 'datetime':
        now = now.strftime("%Y-%m-%d %H:%M:%S")
        
    elif date_type == 'date':
        now = now.strftime("%Y-%m-%d")
        
    else:
        raise ValueError(f"Date type must be 'datetime' or 'date', not {date_type}!")
    
    return now

def open_and_close(func): #TODO MAKE THIS NOT AI
    """
    Decorator to open and close an SQLite connection around a method call.
    Assumes the class instance (self) has _open_connection and _close_connection methods.
    """
    @functools.wraps(func)  # Preserves the name, docstring, etc., of the decorated function
    def wrapper(self, *args, **kwargs):
        """
        Wrapper function that manages the connection.
        'self' is the instance of the class where the decorated method is defined.
        """
        self._open_connection()  # Call the instance's open connection method
        try:
            # Call the original method (e.g., _sql_items)
            result = func(self, *args, **kwargs)
            return result
        except sqlite3.Error as e:
            # Handle potential SQLite errors during the execution of 'func'
            print(f"SQLite error during {func.__name__}: {e}")
            # Depending on the desired behavior, you might want to re-raise the exception
            # or return a specific value indicating failure.
            raise # Re-raise the exception after logging
        finally:
            # This block will always execute, ensuring the connection is closed
            self._close_connection() # Call the instance's close connection method
    return wrapper

class SqlHelper: # Simple helper for SQL
    """Helps with entering and retreiving data from an SQL database.  Runs kind of like an API, where responses come back with either a success or error message
    """
    def __init__(self, db_name:str):
        """SQLlite helper tool

        Args:
            db_name (str): Database name
        """
        self.logger = logging.getLogger('SqlHelper')
        self.logger.info('Logging for SqlHelper started')
        self.db = db_name
        try: #TODO can we check if the DB is locked?
            self._open_connection()
            self._close_connection()
        except Exception as e: #TODO find errors 
            print(e)
            pass
    
    def _open_connection(self): # Start/open connection:
            self.conn = sqlite3.connect(self.db)
            self.cur = self.conn.cursor()
            self.cur.execute("PRAGMA foreign_keys = ON;")
            
    def _close_connection(self): # Stop/close connection
            self.conn.close()
    
    def _simple_status(self, status:MainStatus='success', reason:str='NA', result: str | int | dict | tuple | Exception | None=None, more_info:str | int | dict | tuple | Exception | None='NA')-> Status:
        """Simple status and results object

        Args:
            status (str, optional): Status. Defaults to 'success'.
            reason (str, optional): Reason. Defaults to 'NA'.
            result (str | int | dict | list | Exception | None, optional): Result item (if any).  
            more_info (str | int | dict | list | Exception | None, optional): Extra info. Defaults to 'NA'.

        Returns:
            Status: Status/result
        """
        return Status(status=status, reason=reason, result=result, more_info=more_info)
        
    def _run_query(self, query:str, values:Optional[list]=None, mode: str ='get')-> Status:
        if mode not in ['insert', 'update', 'delete', 'get', 'raw-get']:
            raise ValueError(f'Invalid mode {mode}.')
        status = 'error' # Assume the request was no good to start
        more_info = None
        result = None
        try:
            if values:
                resp = self.cur.execute(query, values)
            else: # Run without values, prevents error
                resp = self.cur.execute(query)
            self.conn.commit() # Commit changes, should only run if something happened
            reason = 'VALID QUERY' # Assume query is valid (I love assuming)
            
            if mode in ['insert', 'update', 'delete']: # Modify/change modes
                if self.cur.rowcount > 0:
                    result = self.cur.lastrowid # Get the last updated row ID
                    more_info = f'{self.cur.rowcount} row effected' # Shows how many rows were effected by the last command
                else:
                    reason = 'NO ROWS EFFECTED'
                    more_info = 'Query valid, but no rows were returned'
            elif mode in ['get', 'raw-get']: # Get modes
                resp = self.cur.fetchall()
                if len(resp) > 0:
                    result = self._format(resp, self.cur.description) if mode == 'get' else (resp, self.cur.description)
                    more_info = f'{len(resp)} rows found'
                else: # The SQL query was valid, but no rows were returned
                    reason = 'NO ROWS RETURNED'
                    more_info = 'Query valid, but no rows were returned'
                    
            status = 'success' if reason == 'VALID QUERY' else 'error'
            
        except sqlite3.IntegrityError as e:   
            if e.sqlite_errorcode in [2067, 1555]: # (Unique, primary key) constraint failed # type: ignore is custom exception
                reason = str(e.sqlite_errorname)  # type: ignore is custom exception
                result = e.args[0].split(':')[1].strip() 
            
            elif e.sqlite_errorcode == 787: # Foreign Key Constraint Failed # type: ignore is custom exception
                reason = 'SQLITE_CONSTRAINT_FOREIGNKEY'
                result = e.args[0]
                
            else:
                reason = str(e.sqlite_errorname)  # type: ignore is custom exception
                result = e
            
        except Exception as e:
            reason = 'OTHER ERROR'
            result = e
            
        finally:
            return self._simple_status( # Return the result
                status = status, 
                reason = reason,
                result = result,
                more_info = more_info
                )

    def _format(self, items:list | tuple, keys:list | tuple)-> tuple[dict]:
        item_keys = [key[0] for key in keys] # Extract keys
        formatted_items = []
        
        for item in items: # Extract the individual values
            formatted_item = {}
            for count, value in enumerate(item):
                if item_keys[count] in formatted_item: # Prevent Key overwriting
                    formatted_item[str(f'{count}-{item_keys[count]}')] = value
                else:
                    formatted_item[item_keys[count]] = value
                
            formatted_items.append(formatted_item)
            
        return tuple(formatted_items)
    
    def _sql_filters(self, filters:dict | str | tuple)-> tuple[str, list[str | int | float | bool]| None]:
        """Handle different filtering formats and items for other internal methods

        Args:
            filters (dict | str): String (not injection safe) or dict (hopefully injection safe)

        Returns:
            tuple[str, list[str | int | float | bool]| None]:
        """
        
        if isinstance(filters, str):
            filter_str = filters
            filter_items = None
        elif isinstance(filters, tuple):
            filter_str = filters[0] 
            filter_items = filters[1]
        elif not isinstance(filters, dict): # something unexpected provided in filters field
            raise TypeError(f'`filters` must be str or dict, not{type(filters)}.') 
        else:
            filter_str = "" # Will contain filter string (if any)
            filter_vars = list()
            filter_items = list()
            if filters: # Create filter string (if exists)
                for var, item in filters.items():
                    if item != None: # Skip blank items
                        if isinstance(var, tuple): # Support LIKE and NOT by sending a line like this var = ('LIKE', '<query>')
                            filter_vars.append(f'{var[1]} {var[0].upper()} ' + str(f'({item})' if var[0].lower() == 'in' else '?'))
                            if not var[0].lower() == 'in':
                                filter_items.append(item)
                        else:
                            filter_vars.append(var + " = ?")
                            filter_items.append(item)
        
                if len(filter_vars) > 0: # Sometimes filters are sent but all the items are none I guess
                    filter_str = "WHERE " + " AND ".join(filter_vars)
            
        return filter_str, filter_items
    
    def _sql_items(self, items:dict, mode:str='insert'):
        keys = list()
        values = list()
        questionmarks = list()
        for key, val in items.items():
            if val == None:  # Skip blank items
                continue
            elif val == 'NULL': # Allows a field be set back to none/null
                values.append(None)
            else:
                values.append(val)
                
            if mode == 'insert':
                keys.append(key)
            elif mode == 'set':
                keys.append(key +'=?')

            questionmarks.append("?")
        
        return keys, values, questionmarks
    
    @open_and_close
    def insert(self, table:str, items:dict): # Insert into table
        sql_query = "INSERT INTO {table} ({keys}) VALUES({keyvars})"
        keys, values, questionmarks = self._sql_items(items)
        
        sql_query = sql_query.format(table=table, keys=",".join(keys), keyvars=",".join(questionmarks))
        
        return self._run_query(sql_query, values, mode='insert')
        
        
    @open_and_close    
    def get(self, table:str, columns:list=["*"], filters:dict | str | tuple={}, left_join:Optional[str]=None, order:Optional[dict[str,str]]=None) -> Status: 
        """Run SQL get queries
        
        THE COLUMNS ARE NOT INJECTION SAFE! DO NOT LET USERS SEND ANYTHING HERE, AND NEVER SEND UNTRUSTED INPUT TO table OR columns

        Args:
            table (str): Table name
            columns (list, optional): List of columns to be returned, Defaults to ['*'] (all columns)
            filters (dict | str, optional): Run simple filters by sending them as a dict {'column': 'val'}.  These will be added as `WHERE column = `val` using injection safe input.  Alternatively, a str can be used to send pre-formatted filters, eg: `WHERE column IS NOT 1`.  These AREN'T currently injection safe!
            left_join (str, optional): Include a LEFT JOIN SQL query in your request
            order (dict): Key should be the column name to order by, values should be ASC or DESC
            
        Returns:
            tuple of items and their keys
        """
        if len(columns) == 0:
            columns = ['*']        
        sql_query = """SELECT {columns} FROM {table} {left_join} {filters} {order}"""

        filter_str, filter_items = self._sql_filters(filters)
        
        order_str = "" # Will contain order string (if any)
        order_items = list()
        if order:
            for var, direction in order.items():
                if direction.lower() not in ['asc', 'desc']: # Skip invalid order/sort
                    return self._simple_status( # Return the result
                        status='error', 
                        reason='INVALID ORDER DIRECTION',
                        more_info=f'Order direction must be ASC or DESC, not \'{direction}\'.'
                        )
                
                order_items.append(f"{var} {direction.upper()}") 
            
            order_str = "ORDER BY " + ", ".join(order_items)
            
        sql_query = sql_query.format(columns=",".join(columns), table=table, left_join=str(left_join), filters=filter_str, order =order_str)
        return self._run_query(sql_query, values=filter_items, mode='get')  # type: ignore its a list or status, idk why it has a hard time understanding that but im sick of trying to fix it
    
    @open_and_close
    def update(self, table:str, items:dict, filters:dict | str | tuple={}):
        sql_query = """UPDATE {table} SET {keys} {filters}"""
        
        filter_str, filter_items = self._sql_filters(filters)

        keys, value_items, questionmarks = self._sql_items(items, mode='set')
        if len(value_items) == 0:
            return self._simple_status( # Return the result
                status='error', 
                reason='NO COLUMNS CHANGED',
                more_info='Atleast one column must be changed'
                )
        all_items = value_items + (filter_items if isinstance(filter_items, list) else [])
            
        sql_query = sql_query.format(table=table, keys=",".join(keys), filters=filter_str)
        return self._run_query(sql_query, all_items, mode='update')
    
    @open_and_close
    def delete(self, table:str, filters:dict | str | tuple={}):
        sql_query = """DELETE FROM {table} {filters}"""
        
        filter_str, filter_items = self._sql_filters(filters)
        
        sql_query = sql_query.format(table=table, filters=filter_str)
        return self._run_query(sql_query, filter_items, mode='delete')
    
    @open_and_close
    def send_query(self, query, values: Optional[list]=None , mode:str='get'): # Send an SQL query directly
        return self._run_query(query=query, values=values, mode=mode)
    
    @open_and_close
    def delete_table(self, table:str): # Drop that shit
        query = """DROP TABLE IF EXISTS ?
        VALUES(?,)"""
        values = [table]
        return self._run_query(query=query, values=values, mode='delete')
    