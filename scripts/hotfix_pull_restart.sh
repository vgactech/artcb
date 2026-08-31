#!/usr/bin/env bash
# Pull one branch onto a live node and restart artcb. No full liboqs rebuild.
# Usage: bash scripts/hotfix_pull_restart.sh USER@HOST SSH_KEY BRANCH
# Refuses OVH1 152.228.144.34.
set -Eeuo pipefail
TARGET="${1:-}"
SSH_KEY="${2:-}"
BRANCH="${3:-}"
if [ -z "$TARGET" ] || [ -z "$SSH_KEY" ] || [ -z "$BRANCH" ]; then
  echo "Usage: bash scripts/hotfix_pull_restart.sh USER@HOST SSH_KEY BRANCH"
  exit 1
fi
HOST="${TARGET#*@}"
if [ "$HOST" = "152.228.144.34" ]; then
  echo "Refusing to hotfix OVH1"
  exit 1
fi
ssh -i "$SSH_KEY" -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=accept-new \
  "$TARGET" env BRANCH="$BRANCH" bash -s <<'REMOTE'
set -Eeuo pipefail
cd ~/artcb
git fetch origin "$BRANCH"
git checkout -B "$BRANCH" "origin/$BRANCH"
git reset --hard "origin/$BRANCH"
DEPLOYED_SHA=$(git rev-parse HEAD)
printf 'ARTCB_GIT_SHA=%s\nARTCB_GIT_BRANCH=%s\n' "$DEPLOYED_SHA" "$BRANCH" | sudo tee /etc/artcb/release.env >/dev/null
sudo chmod 644 /etc/artcb/release.env
sudo systemctl restart artcb.service
for i in $(seq 1 20); do
  if curl -sf http://127.0.0.1:8000/health >/dev/null; then
    echo "local_health_ok attempt=$i sha=$DEPLOYED_SHA"
    break
  fi
  sleep 2
done
curl -sf http://127.0.0.1:8000/health | python3 -c 'import sys,json; d=json.load(sys.stdin); print({k:d.get(k) for k in ("status","git_sha","git_branch","bootstrap_mode","protocol_version")})'
REMOTE
echo "── OVH1 152.228.144.34 n'a PAS été modifié"
