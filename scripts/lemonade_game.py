#TODO allow multiple recurring games and store them in JSON file instead of the database because I like when things are difficult 
#TODO allow setup to be done via a commandline tool
# # # # CREATE MONTHLY GAME # # # #
# Run this script daily for ideal results

# # SETTINGS # #
create_days_before = 5 # create game _ days before next month. Maximum 27 days (i think)
name = 'Lemonade Stand {date}' # Game name, add placeholder {date} to show date. EG:  'My Super Cool Game {date}' 
date_format = '%b/%Y' # If showing date, set the format (use datetime.strftime formatting!)

# # PRESET INFO # #
# Games will start on the first of the month
# Games will end on the last of the month
# Players will be able to join after the game starts (pick date is not set) 


# # # # DANGER ZONE - ONLY CHANGE IF YOU KNOW WHAT YOU'RE DOING # # # #
## IMPORTS
# BUILT-IN
from datetime import datetime, timedelta
import logging
import os

# EXTERNAL
from dateutil.relativedelta import relativedelta

# INTERNAL
from stocks import Backend
# Logging setup
logger = logging.getLogger('RecurringGames')
# Environment vars, hope they set them lol
#TODO check if they set them (lol)
try:
    DB_NAME = str(os.getenv('DB_NAME'))
    OWNER = int(os.getenv("OWNER"))
    logger.debug(f'DB name: {DB_NAME} | Owner ID: {OWNER}')
except Exception as e: #TODO errors
    logger.exception('Error when getting environment variables', exc_info=e)
    raise Exception(f'An unexpected error occurred while getting enviroment variables', e)
be = Backend(db_name=DB_NAME) # Create backend thing

# Date stuff
today = datetime.today() # Current date
start_of_month = today + relativedelta(months=1, day =1) # The 1st of the month
str_start_month = datetime.strftime(start_of_month, '%Y-%m-%d') # TODO just let add_game accept datetime
end_of_month = start_of_month + relativedelta(months=1, days=-1) #The last of the month (IDK if there is another way to get)
days_untl_nxt_mnth: timedelta = start_of_month - today # How many days until the next month

if days_untl_nxt_mnth.days <= create_days_before: # Game should be created
    exists = False 
    logger.debug(f'Trying to create game "{name}".')
    existing_games = be.get_many_games(name=name, owner_id=OWNER) # Get existing open and active games to avoid creaating the same game twice # TODO find a better way to track this
    for game in existing_games: 
        if game.start_date == start_of_month and game.end_date and game.end_date == end_of_month: # TODO does this actually work
            logger.warning(f'Game "{name}" not created.  Found game ID({game.id}) with the same name, start date, and end date.')
            exists = True
    if not exists:
        try:
            be.add_game(
                user_id=int(OWNER), #STOP COMPLAINING (ok it was complaining before I swear)
                name=name.format(date=datetime.strftime(start_of_month, date_format)),
                start_date=str_start_month,
                end_date=datetime.strftime(end_of_month, '%Y-%m-%d')
                )
            logger.debug(f'Created game "{name}".')
        except Exception as e: #TODO errors
            logger.exception(f'Error when creating game "{name}".', exc_info=e)
            raise Exception(f'An unexpected error occurred while trying to create game "{name}"', e)
else:
    logger.debug(f'Game "{name}" not created.  {days_untl_nxt_mnth} days until the start of next month.  Game are set to be created with {create_days_before} days or less until the next month.')