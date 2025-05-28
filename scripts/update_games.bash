#! /bin/bash
#
# This script will update all your currently running games.  If you plan to have hourly games, make sure your cronjob runs hourly!
#
# Set up your python environment beforehand if required
#

source .env

python3 update_games.py # Update all running games

