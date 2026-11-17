#!/usr/bin/env bash
# Deploy the committed backend, preserving the working AI configuration.
#
#   bash deploy-backend.sh
#
# What it does (one SSH connection — the server drops rapid reconnects):
#   1. backs up /opt/zubchek/backend and /opt/zubchek/.env
#   2. uploads `git HEAD:backend` (uncommitted changes are NOT deployed)
#   3. backs up the database; optionally sets MODEL when explicitly provided
#   4. rebuilds + restarts the backend container
#   5. checks /health and makes one tiny real AI call through the relay
#
# Rollback: on the server, `cd /opt/zubchek && rm -rf backend &&
#   mv backend.bak-<stamp> backend && cp .env.bak-<stamp> .env &&
#   docker compose build backend && docker compose up -d backend`
set -euo pipefail

SERVER=root@104.171.132.55
MODEL=${MODEL:-}
[[ "$MODEL" =~ ^[A-Za-z0-9._:/-]*$ ]] || { echo "Invalid MODEL"; exit 1; }

cd "$(dirname "$0")"

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
git archive --format=tar -o "$tmp/deploy.tar" HEAD backend ':(exclude)backend/logs'
echo "Deploying $(git log --oneline -1) with model ${MODEL:-unchanged} ..."
ssh -o ConnectTimeout=15 -o ServerAliveInterval=15 "$SERVER" "MODEL='$MODEL' bash -s" < <(
cat <<'REMOTE'
set -euo pipefail
cd /opt/zubchek
umask 077
stamp=$(date +%Y%m%d-%H%M%S)
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' | gzip > "db.bak-$stamp.sql.gz"
echo "database backup: db.bak-$stamp.sql.gz"
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

if [ -n "$MODEL" ]; then
  sed -i "s#^APP_AI_MODEL=.*#APP_AI_MODEL=${MODEL}#" .env
fi
rm -rf /tmp/zdeploy
echo "AI configuration preserved (unless MODEL explicitly supplied)"

docker compose build backend 2>&1 | tail -2
docker compose up -d backend 2>&1 | tail -1
for attempt in $(seq 1 45); do
  if docker compose exec -T backend python -c 'import urllib.request; urllib.request.urlopen("http://localhost:8000/health", timeout=2)' >/dev/null 2>&1; then break; fi
  sleep 2
done
docker compose ps --format '{{.Service}}: {{.Status}}'

docker compose exec -T backend python - <<'PY'
import asyncio, json, urllib.request, urllib.error
print("health:", urllib.request.urlopen("http://localhost:8000/health", timeout=10).read().decode())
for path, expected in [("/api/v1/reports/1", 404), ("/api/v1/entities/users_profiles", 401)]:
    try:
        response = urllib.request.urlopen("http://localhost:8000" + path, timeout=10)
        status = response.status
    except urllib.error.HTTPError as e:
        status = e.code
    assert status == expected, f"Access check failed: {path} -> {status}"
print("Report access protection: OK")
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
