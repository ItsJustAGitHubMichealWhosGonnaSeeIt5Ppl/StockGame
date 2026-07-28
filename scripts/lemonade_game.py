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


## IMPORTS
# BUILT-IN
from datetime import datetime, timedelta
import logging
import os

# EXTERNAL
from dateutil.relativedelta import relativedelta
from dotenv import load_dotenv

# INTERNAL
import sys
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(current_dir))
from stocks import Backend

def main():
    load_dotenv()
    # Logging setup
    logger = logging.getLogger('RecurringGames')
    # Environment vars
    db_name = os.getenv('DB_NAME')
    owner = os.getenv('OWNER')
    if not db_name or not owner:
        raise RuntimeError('DB_NAME and OWNER must be set.')
    try:
        OWNER = int(owner)
    except ValueError as exc:
        raise RuntimeError('OWNER must be a numeric user ID.') from exc
    DB_NAME = db_name
    logger.debug(f'DB name: {DB_NAME} | Owner ID: {OWNER}')
    be = Backend(db_name=DB_NAME)

    # Date stuff
    today = datetime.today()
    start_of_month = today + relativedelta(months=1, day=1)
    str_start_month = datetime.strftime(start_of_month, '%Y-%m-%d')
    end_of_month = start_of_month + relativedelta(months=1, days=-1)
    days_untl_nxt_mnth: timedelta = start_of_month - today

    if days_untl_nxt_mnth.days <= create_days_before:
        exists = False
        logger.debug(f'Trying to create game "{name}".')
        existing_games = be.get_many_games(name=name, owner_id=OWNER)
        for game in existing_games:
            if game.start_date == start_of_month and game.end_date and game.end_date == end_of_month:
                logger.warning(f'Game "{name}" not created.  Found game ID({game.id}) with the same name, start date, and end date.')
                exists = True
        if not exists:
            try:
                be.add_game(
                    user_id=int(OWNER),
                    name=name.format(date=datetime.strftime(start_of_month, date_format)),
                    start_date=str_start_month,
                    end_date=datetime.strftime(end_of_month, '%Y-%m-%d')
                    )
                logger.debug(f'Created game "{name}".')
            except Exception as e:
                logger.exception(f'Error when creating game "{name}".', exc_info=e)
                raise Exception(f'An unexpected error occurred while trying to create game "{name}"', e)
    else:
        logger.debug(f'Game "{name}" not created.  {days_untl_nxt_mnth} days until the start of next month.  Game are set to be created with {create_days_before} days or less until the next month.')

if __name__ == "__main__":
    main()
