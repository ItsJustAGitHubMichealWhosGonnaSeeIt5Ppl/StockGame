# Misc helpers
import sqlite3
from datetime import datetime
import functools

def _unix_timestamp(): # Get a unix timestamp #TODO add docstring
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
    def __init__(self, db_name:str): #TODO add logging
        """SQLlite helper tool

        Args:
            db_name (str): Database name
        """
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
    
    def _simple_status(self, status:str='success', reason:str='none', more_info:str='None'):
        """Generate simple status messages

        Args:
            status (str, optional): Status. Defaults to 'success'.
            reason (str, optional): Reason. Defaults to 'none'.
            more_info (str, optional): Extra info. Defaults to 'None'.

        Returns:
            dict: Status/result
        """
        return {'status':status,
            'reason':reason,
            'more_info':more_info}
        
    def _run_query(self, query:str, values:list, mode:str):
        try:
            resp = self.cur.execute(query, values)
            self.conn.commit()
            if mode in ['insert','update', 'delete']:
                return self._simple_status(reason=f'{mode}', more_info=self.cur.lastrowid) # Simple status
            elif mode in ['get']: 
                resp = self.cur.fetchall()
                return self._format(resp, self.cur.description)
            elif mode in ['advanced_get']: # in case the respose columns have duplicate names
                resp = self.cur.fetchall() 
                return resp, self.cur.description
                
            
        except sqlite3.IntegrityError as e:
            if e.sqlite_errorcode == 2067: # Unique constraint failed
                return self._simple_status(status='error',
                                   reason='SQLITE_CONSTRAINT_UNIQUE',
                                   more_info=e.args[0].split(':')[1])
                
            elif e.sqlite_errorcode == 1555: # Unique constraint failed for primary key
                return self._simple_status(status='error',
                                   reason='SQLITE_CONSTRAINT_PRIMARYKEY',
                                   more_info=e.args[0].split(':')[1].strip())
            
            elif e.sqlite_errorcode == 787: # Foreign Key Constraint Failed
                return self._simple_status(status='error',
                                   reason='SQLITE_CONSTRAINT_FOREIGNKEY',
                                   more_info=e.args[0])
            
            else:
                return self._simple_status(status='error',
                                   reason='IntegrityError',
                                   more_info=e)
    
        except Exception as e:
            return self._simple_status(status='error',
                                   reason='OTHER ERROR',
                                   more_info=e)

    def _format(self, items:list, keys:list):
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
            
        return formatted_items
    
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
    
    def _sql_items(self, items:dict, mode:str='insert'):
        keys = list()
        values = list()
        questionmarks = list()
        for key, val in items.items():
            if val != None:  # Skip blank items
                if mode == 'insert':
                    keys.append(key)
                elif mode == 'set':
                    keys.append(key +'=?')
                values.append(val)
                questionmarks.append("?")
        
        return keys, values, questionmarks
    
    @open_and_close
    def insert(self, table:str, items:dict): # Insert into table
        sql_query = "INSERT INTO {table} ({keys}) VALUES({keyvars})"
        keys, values, questionmarks = self._sql_items(items)
        
        sql_query = sql_query.format(table=table, keys=",".join(keys), keyvars=",".join(questionmarks))
        
        return self._run_query(sql_query, values, mode='insert')
        
        
    @open_and_close    
    def get(self, table:str, columns:list=["*"], filters:dict=None, order:dict=None): 
        """Run SQL get queries
        
        THE COLUMNS ARE NOT INJECTION SAFE! DO NOT LET USERS SEND ANYTHING HERE, AND NEVER SEND UNTRUSTED INPUT TO table OR columns

        Args:
            table (str): Table name
            columns(list, optional): List of columns to be returned, Defaults to ['*'] (all columns)
            filters (dict): Key should be the column name to filter by, values should be the variables
            order (dict): Key should be the column name to order by, values should be ASC or DESC
            
        Returns:
            tuple of items and their keys
        """
        if len(columns) == 0:
            columns = ['*']        
        sql_query = """SELECT {columns} FROM {table} {filters} {order}"""
        
        filter_str, filter_items = self._sql_filters(filters)
            
        order_str = "" # Will contain order string (if any)
        order_items = list()
        if order:
            for var, direction in order.items():
                if direction.lower() not in ['asc', 'desc']: # Skip invalid order/sort
                    raise ValueError(f'Invalid order direction {direction} specified for {var}@')
                
                order_items.append(f"{var} {direction.upper()}") 
            
            order_str = "ORDER BY " + ", ".join(order_items)
            
        sql_query = sql_query.format(columns=",".join(columns), table=table, filters=filter_str, order =order_str)
        return self._run_query(sql_query, filter_items, mode='get')
    
    @open_and_close
    def update(self, table:str, filters:dict, items:dict):
        sql_query = """UPDATE {table} SET {keys} {filters}"""
        
        filter_str, filter_items = self._sql_filters(filters)
        keys, value_items, questionmarks = self._sql_items(items, mode='set')
            
        all_items = value_items + filter_items
            
        sql_query = sql_query.format(table=table, keys=",".join(keys), filters=filter_str)
        return self._run_query(sql_query, all_items, mode='update')
    
    @open_and_close
    def delete(self, table:str, filters:dict):
        sql_query = """DELETE FROM {table} {filters}"""
        
        filter_str, filter_items = self._sql_filters(filters)
        
        sql_query = sql_query.format(table=table, filters=filter_str)
        return self._run_query(sql_query, filter_items, mode='delete')
