import os
import stocks

DB_NAME = str(os.getenv('DB_NAME')) # Only added so itll shut the fuck up about types

gl = stocks.GameLogic(db_name=DB_NAME)
# Update all games
gl.update_all()