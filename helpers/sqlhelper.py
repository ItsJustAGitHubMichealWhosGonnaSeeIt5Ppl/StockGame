# Misc helpers
import sqlite3
from datetime import datetime, date

def _iso8601(date_type:str='datetime'): # Get an ISO formatted datetime
        now = datetime.now()
        date_type = date_type.lower() # Easier to work with
        if date_type == 'datetime':
            now = now.strftime("%Y-%m-%d %H:%M:%S")
            
        elif date_type == 'date':
            now = now.strftime("%Y-%m-%d")
            
        else:
            raise ValueError(f"Date type must be 'datetime' or 'date', not {date_type}!")
        
        return now

class SqlHelper: # Simple helper for SQL
    def __init__(self, db_name:str):
        self.conn = sqlite3.connect(db_name)
        self.cur = self.conn.cursor()
        self.cur.execute("PRAGMA foreign_keys = ON;")
    
    def _error(self, status:str='success', reason:str='none', more_info:str='None'):
            return {'status':status,
             'reason':reason,
             'more_info':more_info}
    
    def _format(self, items:list, keys:list):
        item_keys = [key[0] for key in keys] # Extract keys
        formatted_items = []
        
        for item in items: # Extract the individual values
            formatted_item = {}
            for count, value in enumerate(item):
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
        for key, val in items.items(): #TODO better way?
            if val != None:  # Skip blank items
                if mode == 'insert':
                    keys.append(key)
                elif mode == 'set':
                    keys.append(key +'=?')
                values.append(val)
                questionmarks.append("?") #TODO this is dogshit
        
        return keys, values, questionmarks
    
    def insert(self, table:str, items:dict): # Insert into table
        sql_query = "INSERT INTO {table} ({keys}) VALUES({keyvars})"
        keys, values, questionmarks = self._sql_items(items)
        
        sql_query = sql_query.format(table=table, keys=",".join(keys), keyvars=",".join(questionmarks))
        try:
            self.cur.execute(sql_query, values)
            self.conn.commit()
            
        except sqlite3.IntegrityError as e:
            if e.sqlite_errorcode == 2067: # Unique constraint failed
                return self._error(status='error',
                                   reason='SQLITE_CONSTRAINT_UNIQUE',
                                   more_info=e.args[0].split(':')[1])
            
            elif e.sqlite_errorcode == 787: # Foreign Key Constraint Failed
                return self._error(status='error',
                                   reason='SQLITE_CONSTRAINT_FOREIGNKEY',
                                   more_info=e.args[0])
            
            else:
                return self._error(status='error',
                                   reason='IntegrityError',
                                   more_info=e)


        except Exception as e:
            return self._error(status='error',
                                   reason='OTHER ERROR',
                                   more_info=e)
    
        return self._error(reason='inserted', more_info=self.cur.lastrowid)
        
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
        self.cur.execute(sql_query, filter_items)
        resp = self.cur.fetchall()
        return self._format(resp, self.cur.description) #TODO add errors
    
    def update(self, table:str, filters:dict, items:dict):
        sql_query = """UPDATE {table} SET {keys} {filters}"""
        
        filter_str, filter_items = self._sql_filters(filters)
        keys, value_items, questionmarks = self._sql_items(items, mode='set')
            
        all_items = value_items + filter_items
            
        sql_query = sql_query.format(table=table, keys=",".join(keys), filters=filter_str)
        self.cur.execute(sql_query, all_items)
        self.conn.commit()
        return "something happened" #TODO add errors
    