#!/usr/bin/env bash
set -euo pipefail

echo "Stopping and removing all containers and volumes..."
docker compose down -v

echo "Cleaning deadletter and logs..."
find deadletter -type f ! -name '.gitkeep' -delete 2>/dev/null || true
find logs -type f ! -name '.gitkeep' -delete 2>/dev/null || true

echo "Reset complete."
