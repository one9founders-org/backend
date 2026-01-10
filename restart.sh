#!/bin/bash
# Exit immediately if a command fails
set -e

echo "Stopping and removing containers..."
docker compose down

echo "Starting containers in detached mode..."
docker compose up -d

echo "Restart complete!"
