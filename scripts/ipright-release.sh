#!/usr/bin/env bash
# IPRight standardized release script.
#
# Goals:
#   * Always deploy a specific, version-controlled git commit (never the
#     mutable working tree).
#   * Pin every release into its own commit-hash directory on the remote
#     so we can roll back atomically by repointing the "current" symlink.
#   * Append an auditable record to deploy/release-history.log on every
#     successful release (commit, branch, timestamp, operator, target).
#
# Safety preconditions (will abort if violated):
#   1. Working tree must be clean (no unstaged or staged diffs, no
#      untracked files inside backend/, workers/, frontend/).
#   2. HEAD must already exist on the configured remote (default
#      ``origin``) - we refuse to deploy something that would not be
#      reproducible from the remote.
#
# Usage:
#   scripts/ipright-release.sh <ssh_target> [remote_app_root]
#       <ssh_target>      e.g. admin@10.0.0.5
#       remote_app_root   default /opt/ipright
#
# Environment knobs:
#   IPRIGHT_RELEASE_REMOTE   git remote to verify against (default origin)
#   IPRIGHT_RELEASE_BRANCH   if set, refuse to release any branch but this
#   IPRIGHT_SKIP_RESTART     set to 1 to skip systemctl restart steps
#   IPRIGHT_RELEASE_NOTE     optional free-form note appended to history
#
set -euo pipefail

if [ $# -lt 1 ]; then
  cat >&2 <<USAGE
Usage: $0 <ssh_user>@<ecs_ip> [remote_app_root]
USAGE
  exit 1
fi

TARGET="$1"
REMOTE_APP_ROOT="${2:-/opt/ipright}"
LOCAL_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HISTORY_LOG="$LOCAL_ROOT/deploy/release-history.log"
REMOTE_NAME="${IPRIGHT_RELEASE_REMOTE:-origin}"

cd "$LOCAL_ROOT"

if ! command -v git >/dev/null; then
  echo "ERROR: git is required" >&2
  exit 3
fi

# 1. Working tree must be clean.
if [ -n "$(git status --porcelain)" ]; then
  echo "ERROR: working tree is dirty. Commit or stash before releasing." >&2
  git status --short >&2
  exit 4
fi

# 2. HEAD commit must be reachable on the remote.
COMMIT="$(git rev-parse HEAD)"
SHORT_COMMIT="$(git rev-parse --short=12 HEAD)"
BRANCH="$(git rev-parse --abbrev-ref HEAD)"

if [ -n "${IPRIGHT_RELEASE_BRANCH:-}" ] && [ "$BRANCH" != "$IPRIGHT_RELEASE_BRANCH" ]; then
  echo "ERROR: refusing to release from branch '$BRANCH' (expected '$IPRIGHT_RELEASE_BRANCH')." >&2
  exit 5
fi

if ! git fetch --quiet "$REMOTE_NAME"; then
  echo "ERROR: failed to fetch from remote '$REMOTE_NAME'" >&2
  exit 6
fi

if ! git branch -r --contains "$COMMIT" | grep -q "^[[:space:]]*${REMOTE_NAME}/"; then
  echo "ERROR: commit $SHORT_COMMIT is not present on remote '$REMOTE_NAME'." >&2
  echo "Push first: git push $REMOTE_NAME $BRANCH" >&2
  exit 7
fi

OPERATOR="${SUDO_USER:-${USER:-unknown}}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RELEASE_ID="${TIMESTAMP}-${SHORT_COMMIT}"
ARCHIVE_NAME="ipright-${RELEASE_ID}.tar.gz"
LOCAL_ARCHIVE="/tmp/${ARCHIVE_NAME}"
REMOTE_RELEASES_DIR="${REMOTE_APP_ROOT}/releases"
REMOTE_RELEASE_DIR="${REMOTE_RELEASES_DIR}/${RELEASE_ID}"
REMOTE_CURRENT_LINK="${REMOTE_APP_ROOT}/current"

echo "== building archive of commit ${SHORT_COMMIT} =="
git archive --format=tar.gz --prefix="ipright-${RELEASE_ID}/" \
  -o "$LOCAL_ARCHIVE" "$COMMIT"
ls -lh "$LOCAL_ARCHIVE"

echo "== uploading archive to ${TARGET}:/tmp/ =="
scp "$LOCAL_ARCHIVE" "$TARGET:/tmp/${ARCHIVE_NAME}"

echo "== extracting on ${TARGET} =="
ssh "$TARGET" bash <<EOF
set -euo pipefail
sudo mkdir -p "${REMOTE_RELEASES_DIR}"
sudo tar -xzf "/tmp/${ARCHIVE_NAME}" -C "${REMOTE_RELEASES_DIR}/"
sudo mv "${REMOTE_RELEASES_DIR}/ipright-${RELEASE_ID}" "${REMOTE_RELEASE_DIR}"
sudo chown -R \$(id -u):\$(id -g) "${REMOTE_RELEASE_DIR}" 2>/dev/null || true

# Atomic flip of the "current" symlink.
PREVIOUS_TARGET=""
if [ -L "${REMOTE_CURRENT_LINK}" ]; then
  PREVIOUS_TARGET="\$(readlink -f ${REMOTE_CURRENT_LINK})"
fi
sudo ln -sfn "${REMOTE_RELEASE_DIR}" "${REMOTE_CURRENT_LINK}.new"
sudo mv -Tf "${REMOTE_CURRENT_LINK}.new" "${REMOTE_CURRENT_LINK}"
echo "Previous: \${PREVIOUS_TARGET:-<none>}"
echo "Current:  \$(readlink -f ${REMOTE_CURRENT_LINK})"

if [ "\${IPRIGHT_SKIP_RESTART:-${IPRIGHT_SKIP_RESTART:-0}}" != "1" ]; then
  sudo systemctl restart ipright-api || true
  sudo systemctl restart ipright-worker || true
  sleep 3
  systemctl is-active ipright-api || true
  systemctl is-active ipright-worker || true
fi

rm -f "/tmp/${ARCHIVE_NAME}"
EOF

rm -f "$LOCAL_ARCHIVE"

mkdir -p "$(dirname "$HISTORY_LOG")"
NOTE="${IPRIGHT_RELEASE_NOTE:-}"
{
  printf '%s\trelease_id=%s\tcommit=%s\tbranch=%s\toperator=%s\ttarget=%s\tremote_path=%s\tnote=%s\n' \
    "$TIMESTAMP" "$RELEASE_ID" "$COMMIT" "$BRANCH" "$OPERATOR" "$TARGET" "$REMOTE_RELEASE_DIR" "${NOTE//[$'\t\n']/ }"
} >> "$HISTORY_LOG"

echo
echo "== release recorded =="
echo "  release_id : $RELEASE_ID"
echo "  commit     : $COMMIT"
echo "  branch     : $BRANCH"
echo "  operator   : $OPERATOR"
echo "  target     : $TARGET"
echo "  remote dir : $REMOTE_RELEASE_DIR"
echo "  history    : $HISTORY_LOG"
