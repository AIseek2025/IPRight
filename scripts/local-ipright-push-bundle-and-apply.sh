#!/usr/bin/env bash
set -euo pipefail

if [ $# -lt 2 ]; then
  echo "Usage: $0 <ssh_user>@<ecs_ip> <remote_app_root>" >&2
  exit 1
fi

TARGET="$1"
REMOTE_APP_ROOT="$2"
LOCAL_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUNDLE_PATH="/tmp/ipright-main.bundle"
TOPLEVEL="$(git -C "$LOCAL_ROOT" rev-parse --show-toplevel)"

if [ "$TOPLEVEL" != "$LOCAL_ROOT" ]; then
  echo "IPRight is not yet an independent git repository." >&2
  echo "Current git toplevel: $TOPLEVEL" >&2
  echo "Please initialize/bind a standalone repo for $LOCAL_ROOT before using this script." >&2
  exit 1
fi

echo "== create bundle =="
git -C "$LOCAL_ROOT" bundle create "$BUNDLE_PATH" HEAD

echo "== upload bundle =="
scp "$BUNDLE_PATH" "$TARGET:/tmp/ipright-main.bundle"

echo "== apply bundle =="
ssh "$TARGET" "mkdir -p '$REMOTE_APP_ROOT' && cd '$REMOTE_APP_ROOT' && \
  if [ ! -d .git ]; then git init; fi && \
  git fetch /tmp/ipright-main.bundle HEAD && \
  git checkout -f FETCH_HEAD"

echo "== run deploy script =="
ssh "$TARGET" "cd '$REMOTE_APP_ROOT' && bash scripts/ipright-ecs-full-deploy.sh"
