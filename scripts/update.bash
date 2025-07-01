#! /bin/bash
# Move this file outside the container!
cd StockGame/

if [ $(id -u) -ne 0 ]
  then echo "Run as root"
  exit
fi

# Pull latest version
sudo git pull

# Go back a folder (where this script should be)
cd ../

# Bring container offline
docker compose -f compose.yaml down

# Build updated container
docker compose -f compose.yaml build

# Bring container back online
docker compose -f compose.yaml up -d
