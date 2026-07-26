#!/usr/bin/env bash
set -euo pipefail

# One-command bring-up for the Maternity HL7-to-FHIR Pipeline.
# Starts all services, waits for health, and deploys the Mirth channel.
#
# Usage:
#   ./scripts/up.sh               # AU mode (default)
#   PROFILE_REGION=eu PROFILE_COUNTRY=uk ./scripts/up.sh   # EU mode

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}Starting Maternity HL7-to-FHIR Pipeline...${NC}"
echo ""

# Ensure runtime directories exist (deadletter uses a bind-mount).
mkdir -p "$REPO_ROOT/deadletter" "$REPO_ROOT/logs/fastapi"

# Start services.
echo "Starting Docker Compose services..."
docker compose -f "$REPO_ROOT/docker-compose.yml" up -d --build

# Wait for FastAPI health (Mirth depends on FastAPI, HAPI comes up first).
echo "Waiting for FastAPI health..."
for i in $(seq 1 60); do
  if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
    echo "  FastAPI healthy."
    break
  fi
  if [ "$i" -eq 60 ]; then
    echo "ERROR: FastAPI did not become healthy within 60 attempts." >&2
    exit 1
  fi
  sleep 2
done

# Wait for Mirth to be ready.
echo "Waiting for Mirth Connect..."
for i in $(seq 1 40); do
  if curl -sfk -H "X-Requested-With: up.sh" "https://localhost:8443/api/server/status" > /dev/null 2>&1; then
    echo "  Mirth ready."
    break
  fi
  if [ "$i" -eq 40 ]; then
    echo "ERROR: Mirth did not become ready within 40 attempts." >&2
    exit 1
  fi
  sleep 3
done

# Deploy the Mirth channel.
echo "Deploying Mirth channel..."
"$REPO_ROOT/scripts/import_channels.sh"

echo ""
echo -e "${GREEN}Pipeline ready.${NC}"
echo ""
echo "  FastAPI:     http://localhost:8000"
echo "  HAPI FHIR:   http://localhost:8080/fhir"
echo "  Mirth Admin: https://localhost:8443"
echo "  MLLP:        port 6661"
echo ""
echo "Smoke test:  python scripts/mllp_send.py samples/adt_a01_normal_delivery.hl7"
