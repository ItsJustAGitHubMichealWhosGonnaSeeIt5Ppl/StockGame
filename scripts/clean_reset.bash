#! /bin/bash
# 
# Run this script to clean the database and start the bot
# 
# Set up your python environment beforehand if required
# 

source .env

if [ -e "$DB_NAME" ]; then
  rm "$DB_NAME"
  echo "Removed existing database"
fi

python3 discord_bot.py
echo "Started bot (database create/migrate handled on startup)"
