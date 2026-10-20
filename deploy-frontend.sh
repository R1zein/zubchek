#!/usr/bin/env bash
# Build the committed frontend locally and publish it to the VPS.
#
#   bash deploy-frontend.sh
#
# What it does (one SSH connection — the server drops rapid reconnects):
#   1. builds `git HEAD:frontend` in a clean temp checkout (uncommitted changes
#      are NOT deployed) with the production VITE_* variables
#   2. backs up /opt/zubchek/frontend-dist
#   3. replaces the CONTENTS of frontend-dist in place — Caddy bind-mounts the
#      directory by inode, so deleting/recreating it would make the site 404
#   4. checks that Caddy serves the new index.html and its JS bundle
#
# Rollback: on the server, `cd /opt/zubchek && find frontend-dist -mindepth 1
#   -delete && cp -a frontend-dist.bak-<stamp>/. frontend-dist/`
set -euo pipefail

SERVER=root@104.171.132.55
export VITE_API_BASE_URL=https://api.zubchek.com
export VITE_SITE_URL=https://zubchek.com
export VITE_APP_TITLE=Zubchek

cd "$(dirname "$0")"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

echo "Building $(git log --oneline -1) ..."
git archive --format=tar HEAD frontend | tar -x -C "$tmp"
(
  cd "$tmp/frontend"
  CI=true corepack pnpm install --frozen-lockfile >/dev/null
  corepack pnpm exec vite build >/dev/null
)
dist="$tmp/frontend/dist"
[ -s "$dist/index.html" ] || { echo "build produced no index.html"; exit 1; }
bundle=$(grep -oE '/assets/index-[A-Za-z0-9_-]+\.js' "$dist/index.html" | head -1)
echo "built: $(find "$dist" -type f | wc -l) files, entry $bundle"

tar -C "$dist" -cf "$tmp/dist.tar" .
ssh -o ServerAliveInterval=15 "$SERVER" "BUNDLE='$bundle' bash -s" < <(
cat <<'REMOTE'
set -euo pipefail
cd /opt/zubchek
stamp=$(date +%Y%m%d-%H%M%S)
cp -a frontend-dist "frontend-dist.bak-$stamp"
echo "backup: frontend-dist.bak-$stamp"
mkdir -p /tmp/zfront && rm -rf /tmp/zfront/*
base64 -d > /tmp/zfront/dist.tar <<'B64'
REMOTE
base64 < "$tmp/dist.tar"
cat <<'REMOTE'
B64
mkdir /tmp/zfront/new && tar -x -f /tmp/zfront/dist.tar -C /tmp/zfront/new
[ -s /tmp/zfront/new/index.html ] || { echo "upload broken, frontend-dist untouched"; exit 1; }
find frontend-dist -mindepth 1 -delete
cp -a /tmp/zfront/new/. frontend-dist/
rm -rf /tmp/zfront

code=$(curl -s -o /dev/null -w "%{http_code}" --resolve zubchek.com:443:127.0.0.1 https://zubchek.com/)
js=$(curl -s -o /dev/null -w "%{http_code}" --resolve zubchek.com:443:127.0.0.1 "https://zubchek.com$BUNDLE")
echo "site: index $code, bundle $js"
[ "$code" = 200 ] && [ "$js" = 200 ] || { echo "SITE CHECK FAILED — roll back with frontend-dist.bak-$stamp"; exit 1; }
REMOTE
)
