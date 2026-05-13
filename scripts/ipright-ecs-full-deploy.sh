#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/ipright}"
BACKEND_DIR="${BACKEND_DIR:-$APP_ROOT/backend}"
FRONTEND_DIR="${FRONTEND_DIR:-$APP_ROOT/frontend}"
STATIC_ROOT="${STATIC_ROOT:-/var/www/ipright}"
ENV_FILE="${ENV_FILE:-$BACKEND_DIR/.env.production}"
PYTHON_BIN="${PYTHON_BIN:-/usr/bin/python3.11}"
PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-$APP_ROOT/shared/ms-playwright}"
RELEASE_TS="$(date +%Y%m%d-%H%M%S)"
STATIC_RELEASE="$STATIC_ROOT/releases/$RELEASE_TS"

echo "== IPRight ECS full deploy =="
echo "APP_ROOT=$APP_ROOT"
echo "BACKEND_DIR=$BACKEND_DIR"
echo "FRONTEND_DIR=$FRONTEND_DIR"
echo "STATIC_RELEASE=$STATIC_RELEASE"
echo "PYTHON_BIN=$PYTHON_BIN"

mkdir -p "$APP_ROOT/shared/workspace"
mkdir -p "$PLAYWRIGHT_BROWSERS_PATH"
mkdir -p "$STATIC_ROOT/releases"

echo "-- backend venv --"
cd "$BACKEND_DIR"
"$PYTHON_BIN" -m venv .venv
. .venv/bin/activate
export PLAYWRIGHT_BROWSERS_PATH
pip install --upgrade pip
pip install -e .
pip install playwright

echo "-- system packages --"
if command -v dnf >/dev/null 2>&1; then
  sudo dnf install -y \
    chromium-headless \
    libreoffice-core \
    libreoffice-writer \
    atk \
    at-spi2-atk \
    gtk3 \
    libXcomposite \
    libXdamage \
    libXScrnSaver
elif command -v yum >/dev/null 2>&1; then
  sudo yum install -y \
    chromium-headless \
    libreoffice-core \
    libreoffice-writer \
    atk \
    at-spi2-atk \
    gtk3 \
    libXcomposite \
    libXdamage \
    libXScrnSaver
else
  echo "warning: unsupported package manager; install Chromium and LibreOffice deps manually" >&2
fi

if [ -f "$ENV_FILE" ]; then
  set -a
  . "$ENV_FILE"
  set +a
else
  echo "missing env file: $ENV_FILE" >&2
  exit 1
fi

echo "-- playwright --"
if python -c "import playwright" >/dev/null 2>&1; then
  python -m playwright install chromium
  python -m playwright install-deps chromium || true
  if ! find "$PLAYWRIGHT_BROWSERS_PATH" -maxdepth 3 -type f \( -name 'headless_shell' -o -name 'chrome-headless-shell' -o -name 'chrome' \) | grep -q .; then
    echo "playwright browser executable missing under $PLAYWRIGHT_BROWSERS_PATH" >&2
    exit 1
  fi
else
  echo "playwright module not installed; screenshot capability may fail" >&2
fi

echo "-- migrate --"
alembic upgrade head

echo "-- frontend build --"
cd "$FRONTEND_DIR"
npm ci
npm run build

echo "-- publish static --"
sudo mkdir -p "$STATIC_RELEASE"
sudo rsync -a --delete dist/ "$STATIC_RELEASE"/
if [ -d "$STATIC_ROOT/current" ] && [ ! -L "$STATIC_ROOT/current" ]; then
  sudo rm -rf "$STATIC_ROOT/current"
fi
sudo ln -sfn "$STATIC_RELEASE" "$STATIC_ROOT/current"

echo "-- restart services --"
sudo systemctl daemon-reload
sudo systemctl restart ipright-api
sudo systemctl restart ipright-worker
sudo systemctl reload nginx

echo "-- health --"
curl -fsSL http://127.0.0.1:18000/health
curl -I http://127.0.0.1/ || true

echo "deploy completed"
