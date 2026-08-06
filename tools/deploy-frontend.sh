#!/usr/bin/env bash
# deploy-frontend.sh — kopiera frontend-filer in i loreweavers-cauldron
# ---------------------------------------------------------------------
# docker compose up -d tappar docker cp:ade filer (bara backend/data är
# bind-mountat). Kör detta efter varje compose up / restart för att
# frontend (inkl. sprites.js) ska vara den senaste versionen.
set -euo pipefail
cd "$(dirname "$0")/.."
C=loreweavers-cauldron
if ! docker ps --format '{{.Names}}' | grep -qx "$C"; then
  echo "Fel: containern '$C' körs inte. Starta först: docker compose up -d" >&2
  exit 1
fi
docker cp frontend/sprites.js "$C":/app/frontend/sprites.js
for f in frontend/*.html; do
  docker cp "$f" "$C":/app/"$f"
done
echo "✓ Frontend kopierat till $C"
docker exec "$C" md5sum /app/frontend/sprites.js
md5sum frontend/sprites.js
