#!/usr/bin/env bash
#
# Import and deploy the Maternity Mirth channel(s) via the Mirth REST API.
#
# The stock nextgenhealthcare/connect image does NOT auto-load channels from a
# mounted directory — channels live in Mirth's internal database. This script
# pushes the exported channel XML in mirth/channels/ into a running Mirth
# instance and deploys it so the MLLP listener on port 6661 goes live.
#
# It deletes any existing copy first, then creates + deploys fresh, so it is
# safe to re-run (Mirth's ?override=true returns false against an existing
# channel, so a clean delete→create is the reliable path).
#
# Usage:
#   docker compose up -d
#   ./scripts/import_channels.sh
#
# Env overrides: MIRTH_URL, MIRTH_USER, MIRTH_PASS
#
set -euo pipefail

MIRTH_URL="${MIRTH_URL:-https://localhost:8443}"
MIRTH_USER="${MIRTH_USER:-admin}"
MIRTH_PASS="${MIRTH_PASS:-admin}"

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CHANNEL_DIR="$REPO_ROOT/mirth/channels"
CHANNEL_ID="7f3a9c10-4d2b-4e6a-9b21-000000000001"

mirth_api() {
  curl -sk -u "$MIRTH_USER:$MIRTH_PASS" -H "X-Requested-With: import_channels.sh" "$@"
}

# Wait until the channels endpoint (not just server status) actually responds —
# the channel subsystem comes up a little after the REST API starts.
echo "Waiting for Mirth channel API at $MIRTH_URL ..."
for _ in $(seq 1 40); do
  if mirth_api "$MIRTH_URL/api/channels" -o /dev/null -w '%{http_code}' 2>/dev/null | grep -q 200; then
    ok=1
    break
  fi
  sleep 3
done
if [ "${ok:-0}" != "1" ]; then
  echo "ERROR: Mirth channel API never became reachable at $MIRTH_URL" >&2
  exit 1
fi

for xml in "$CHANNEL_DIR"/*.xml; do
  [ -e "$xml" ] || { echo "No channel XML found in $CHANNEL_DIR" >&2; exit 1; }
  echo "Importing $(basename "$xml") ..."
  # Delete any existing copy (ignore 404), then create fresh.
  mirth_api -X DELETE "$MIRTH_URL/api/channels/$CHANNEL_ID" -o /dev/null || true
  result=$(mirth_api -X POST "$MIRTH_URL/api/channels" \
    -H "Content-Type: application/xml" \
    --data-binary "@$xml")
  case "$result" in
    *'"boolean":true'*) echo "  imported OK" ;;
    *) echo "ERROR: import did not succeed: $result" >&2; exit 1 ;;
  esac
done

echo "Deploying channel $CHANNEL_ID ..."
mirth_api -X POST "$MIRTH_URL/api/channels/$CHANNEL_ID/_deploy" >/dev/null

# Confirm it reached STARTED.
for _ in $(seq 1 20); do
  if mirth_api "$MIRTH_URL/api/channels/statuses" | grep -q "<state>STARTED</state>"; then
    echo ""
    echo "Done. 'Maternity Inbound HL7' is deployed and listening on MLLP port 6661."
    echo "Smoke test:  python scripts/mllp_send.py samples/adt_a01_normal_delivery.hl7"
    exit 0
  fi
  sleep 2
done
echo "WARNING: channel deployed but did not report STARTED; check the Mirth dashboard." >&2
