#!/usr/bin/env bash
# Deploy the committed backend to the VPS and point it at the AI relay.
#
#   bash deploy-backend.sh
#
# What it does (one SSH connection — the server drops rapid reconnects):
#   1. backs up /opt/zubchek/backend and /opt/zubchek/.env
#   2. uploads `git HEAD:backend` (uncommitted changes are NOT deployed)
#   3. sets APP_AI_BASE_URL from relay/.relay-prefix and APP_AI_MODEL
#   4. rebuilds + restarts the backend container
#   5. checks /health and makes one tiny real AI call through the relay
#
# Rollback: on the server, `cd /opt/zubchek && rm -rf backend &&
#   mv backend.bak-<stamp> backend && cp .env.bak-<stamp> .env &&
#   docker compose build backend && docker compose up -d backend`
set -euo pipefail

SERVER=root@104.171.132.55
RELAY_HOST=https://zubchek-ai.bdnj7916.workers.dev
MODEL=${MODEL:-claude-sonnet-5-5}

cd "$(dirname "$0")"
[ -s relay/.relay-prefix ] || { echo "relay/.relay-prefix missing — see DEPLOY.md §4"; exit 1; }

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
git archive --format=tar -o "$tmp/deploy.tar" HEAD backend ':(exclude)backend/logs'
mkdir -p "$tmp/_deploy"
cp relay/.relay-prefix "$tmp/_deploy/relay-prefix"
tar --append -f "$tmp/deploy.tar" -C "$tmp" _deploy/relay-prefix

echo "Deploying $(git log --oneline -1) with model $MODEL ..."
ssh -o ServerAliveInterval=15 "$SERVER" "MODEL='$MODEL' RELAY_HOST='$RELAY_HOST' bash -s" < <(
cat <<'REMOTE'
set -euo pipefail
cd /opt/zubchek
stamp=$(date +%Y%m%d-%H%M%S)
cp -a backend "backend.bak-$stamp"
cp -a .env ".env.bak-$stamp"
echo "backups: backend.bak-$stamp .env.bak-$stamp"

mkdir -p /tmp/zdeploy && rm -rf /tmp/zdeploy/*
base64 -d > /tmp/zdeploy/deploy.tar <<'B64'
REMOTE
base64 < "$tmp/deploy.tar"
cat <<'REMOTE'
B64
tar -x -f /tmp/zdeploy/deploy.tar -C /tmp/zdeploy
cp -a /tmp/zdeploy/backend/. backend/
rm -f backend/services/r2_storage.py backend/railway.json

prefix=$(tr -d '\r\n' < /tmp/zdeploy/_deploy/relay-prefix)
sed -i "s#^APP_AI_BASE_URL=.*#APP_AI_BASE_URL=${RELAY_HOST}/${prefix}/v1#" .env
sed -i "s#^APP_AI_MODEL=.*#APP_AI_MODEL=${MODEL}#" .env
rm -rf /tmp/zdeploy
echo "env: model=$(grep -E '^APP_AI_MODEL=' .env | cut -d= -f2), base=${RELAY_HOST}/<prefix>/v1"

docker compose build backend 2>&1 | tail -2
docker compose up -d backend 2>&1 | tail -1
sleep 10
docker compose ps --format '{{.Service}}: {{.Status}}'

docker compose exec -T backend python - <<'PY'
import asyncio, json, urllib.request
print("health:", urllib.request.urlopen("http://localhost:8000/health", timeout=10).read().decode())
from services.aihub import AIHubService
from schemas.aihub import GenTxtRequest, ChatMessage
from services.teeth_analysis import get_ai_model
async def main():
    r = await AIHubService().gentxt(GenTxtRequest(
        model=get_ai_model(), max_tokens=2000,
        messages=[ChatMessage(role="user", content="Ответь одним словом: работает")]))
    print(f"AI via relay: OK ({get_ai_model()}) -> {r.content.strip()[:40]!r}, finish={r.finish_reason}")
try:
    asyncio.run(main())
except Exception as e:
    print("AI via relay: FAILED ->", str(e)[:300])
PY
REMOTE
)
