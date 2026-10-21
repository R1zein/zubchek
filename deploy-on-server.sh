#!/usr/bin/env bash
# Deploy the backend from GitHub, run ON THE SERVER — for when no computer
# with SSH access is at hand (e.g. from the Timeweb web console on a phone):
#
#   curl -sL https://raw.githubusercontent.com/R1zein/zubchek/main/deploy-on-server.sh | bash
#
# Optional first argument: branch/tag/commit to deploy (default: main).
# Same steps as deploy-backend.sh, except the AI relay settings in .env are
# left as they are (they're already on the server):
#   1. backs up /opt/zubchek/backend and /opt/zubchek/.env
#   2. downloads <ref> from GitHub and copies its backend/ over the old one
#   3. rebuilds + restarts the backend container
#   4. checks /health and makes one tiny real AI call through the relay
#
# Rollback: `cd /opt/zubchek && rm -rf backend && mv backend.bak-<stamp> backend &&
#   cp .env.bak-<stamp> .env && docker compose build backend && docker compose up -d backend`
set -euo pipefail

REF=${1:-main}
cd /opt/zubchek
stamp=$(date +%Y%m%d-%H%M%S)
cp -a backend "backend.bak-$stamp"
cp -a .env ".env.bak-$stamp"
echo "backups: backend.bak-$stamp .env.bak-$stamp"

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
curl -fsSL "https://codeload.github.com/R1zein/zubchek/tar.gz/$REF" | tar -xz -C "$tmp"
src=$(find "$tmp" -mindepth 1 -maxdepth 1 -type d | head -1)
[ -f "$src/backend/main.py" ] || { echo "download failed: no backend/ in $REF"; exit 1; }
rm -rf "$src/backend/logs"
cp -a "$src/backend/." backend/
echo "deployed backend from $REF"

docker compose build backend 2>&1 | tail -2
docker compose up -d backend 2>&1 | tail -1
sleep 10
docker compose ps --format '{{.Service}}: {{.Status}}'

docker compose exec -T backend python - <<'PY'
import asyncio, urllib.request
print("health:", urllib.request.urlopen("http://localhost:8000/health", timeout=10).read().decode())
from services.aihub import AIHubService
from schemas.aihub import GenTxtRequest, ChatMessage
from services.teeth_analysis import get_ai_model
async def main():
    r = await AIHubService().gentxt(GenTxtRequest(
        model=get_ai_model(), max_tokens=2000,
        messages=[ChatMessage(role="user", content="Ответь одним словом: работает")]))
    print(f"AI via relay: OK ({get_ai_model()}) -> {r.content.strip()[:40]!r}")
try:
    asyncio.run(main())
except Exception as e:
    print("AI via relay: FAILED ->", str(e)[:300])
PY
