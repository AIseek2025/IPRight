#!/usr/bin/env bash
# DEPRECATED: this script copies arbitrary local files straight into a
# production deploy path (sudo cp -f ...). It bypasses git, leaves no
# audit trail, and makes rollback effectively impossible. Prefer
# ``scripts/ipright-release.sh`` which packages a specific git commit
# into a versioned remote directory and writes deploy/release-history.log.
#
# This script is intentionally kept around for true emergencies (the
# remote host has no git available, or the patch must be applied before
# CI completes). Anyone running it is asked to confirm the deprecation
# banner first.
set -euo pipefail

cat <<'BANNER' >&2
================================================================
  WARNING: ipright-ecs-rerun-doc-fixes.sh is DEPRECATED.
  Prefer scripts/ipright-release.sh for routine deployments.
  This script:
    * copies local files via sudo cp -f, bypassing git,
    * has no rollback, no audit log, no commit pinning,
    * should only be used for urgent hotfixes.
  Set IPRIGHT_ALLOW_DEPRECATED_DEPLOY=1 to confirm and proceed.
================================================================
BANNER

if [ "${IPRIGHT_ALLOW_DEPRECATED_DEPLOY:-}" != "1" ]; then
  echo "Aborting (IPRIGHT_ALLOW_DEPRECATED_DEPLOY != 1)." >&2
  exit 2
fi

if [ $# -lt 1 ]; then
  echo "Usage: $0 <ssh_user>@<ecs_ip> [task_id] [remote_app_root]" >&2
  exit 1
fi

TARGET="$1"
TASK_ID="${2:-c5f55bc8-9743-45f1-8839-ea48ace92455}"
REMOTE_APP_ROOT="${3:-/opt/ipright}"
LOCAL_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

REMOTE_BACKEND="$REMOTE_APP_ROOT/backend"
REMOTE_WORKER="$REMOTE_APP_ROOT/workers"

FILES=(
  "backend/app/services/document/manual.py:/tmp/ipright-manual.py"
  "backend/app/services/document/base.py:/tmp/ipright-doc-base.py"
  "backend/app/services/document/codebook.py:/tmp/ipright-codebook.py"
  "backend/app/services/project_profile.py:/tmp/ipright-project_profile.py"
  "workers/stages/handlers.py:/tmp/ipright-handlers.py"
)

echo "== upload patches =="
for item in "${FILES[@]}"; do
  LOCAL_FILE="${item%%:*}"
  REMOTE_FILE="${item##*:}"
  scp "$LOCAL_ROOT/$LOCAL_FILE" "$TARGET:$REMOTE_FILE"
done

echo "== apply patches on ECS =="
ssh "$TARGET" bash <<EOF
set -euo pipefail
sudo cp -f /tmp/ipright-manual.py "$REMOTE_BACKEND/app/services/document/manual.py"
sudo cp -f /tmp/ipright-doc-base.py "$REMOTE_BACKEND/app/services/document/base.py"
sudo cp -f /tmp/ipright-codebook.py "$REMOTE_BACKEND/app/services/document/codebook.py"
sudo cp -f /tmp/ipright-project_profile.py "$REMOTE_BACKEND/app/services/project_profile.py"
sudo cp -f /tmp/ipright-handlers.py "$REMOTE_WORKER/stages/handlers.py"
sudo systemctl restart ipright-api
sudo systemctl restart ipright-worker
sleep 4
systemctl is-active ipright-api
systemctl is-active ipright-worker
EOF

echo "== trigger rerun =="
if [ -n "${RERUN_FROM_STAGE:-}" ]; then
  ssh "$TARGET" "curl -sS -X POST 'http://127.0.0.1:18000/api/v1/tasks/$TASK_ID/retry' -H 'Content-Type: application/json' -d '{\"from_stage\":\"$RERUN_FROM_STAGE\"}'"
else
  ssh "$TARGET" "curl -sS -X POST 'http://127.0.0.1:18000/api/v1/tasks/$TASK_ID/retry' -H 'Content-Type: application/json' -d '{}'"
fi

echo
echo "== next checks =="
echo "ssh $TARGET"
echo "TASK_ID=\"$TASK_ID\""
echo "PG_DSN=\$(grep '^IPRIGHT_DATABASE_URL=' $REMOTE_BACKEND/.env.production | cut -d= -f2- | sed 's/postgresql+asyncpg:/postgresql:/')"
echo "psql \"\$PG_DSN\" -c \"select id, build_no, status, current_stage, failure_reason, started_at, finished_at from task_builds where task_id = '\$TASK_ID' order by build_no desc limit 5;\""
echo "journalctl -u ipright-worker -n 260 --no-pager | grep -E \"\$TASK_ID|Running stage|capture|compose_manual|compose_code_book|publish|failed|succeeded|Task orchestrate_task\" || true"
