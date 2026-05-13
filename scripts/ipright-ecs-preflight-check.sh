#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/ipright}"
BACKEND_DIR="${BACKEND_DIR:-$APP_ROOT/backend}"
FRONTEND_DIR="${FRONTEND_DIR:-$APP_ROOT/frontend}"
PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-$APP_ROOT/shared/ms-playwright}"

pass() {
  printf '[PASS] %s\n' "$1"
}

warn() {
  printf '[WARN] %s\n' "$1"
}

fail() {
  printf '[FAIL] %s\n' "$1"
}

check_cmd() {
  local cmd="$1"
  if command -v "$cmd" >/dev/null 2>&1; then
    pass "command available: $cmd"
  else
    fail "command missing: $cmd"
  fi
}

check_path() {
  local path="$1"
  if [ -e "$path" ]; then
    pass "path exists: $path"
  else
    warn "path missing: $path"
  fi
}

check_port_free() {
  local port="$1"
  if lsof -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    warn "port in use: $port"
  else
    pass "port free: $port"
  fi
}

echo "== IPRight ECS preflight =="

check_cmd python3
check_cmd python3.11
check_cmd node
check_cmd npm
check_cmd nginx
check_cmd systemctl
check_cmd docker
check_cmd git
check_cmd rsync
check_cmd curl

if docker compose version >/dev/null 2>&1; then
  pass "docker compose available"
else
  fail "docker compose missing"
fi

if command -v certbot >/dev/null 2>&1; then
  pass "certbot available"
else
  warn "certbot missing"
fi

if command -v libreoffice >/dev/null 2>&1; then
  pass "libreoffice available"
else
  warn "libreoffice missing"
fi

if [ -x "$BACKEND_DIR/.venv/bin/python" ] && "$BACKEND_DIR/.venv/bin/python" -c "import playwright" >/dev/null 2>&1; then
  pass "python playwright module available"
  if find "$PLAYWRIGHT_BROWSERS_PATH" -maxdepth 3 -type f \( -name 'headless_shell' -o -name 'chrome-headless-shell' -o -name 'chrome' \) 2>/dev/null | grep -q .; then
    pass "playwright browser executable available: $PLAYWRIGHT_BROWSERS_PATH"
  else
    fail "playwright browser executable missing: $PLAYWRIGHT_BROWSERS_PATH"
  fi
else
  warn "python playwright module missing"
fi

check_path "$APP_ROOT"
check_path "$BACKEND_DIR"
check_path "$FRONTEND_DIR"
check_path "/etc/nginx/conf.d/ipright.conf"
check_path "/var/www/ipright"
check_path "/var/www/ipright/current"
check_path "/etc/systemd/system/ipright-api.service"
check_path "/etc/systemd/system/ipright-worker.service"

check_port_free 18000
check_port_free 15432
check_port_free 16379
check_port_free 19000
check_port_free 19001

echo "== docker status =="
docker --version || true
docker compose version || true

echo "== systemd status =="
systemctl is-enabled nginx 2>/dev/null || true
systemctl is-active nginx 2>/dev/null || true
systemctl is-enabled ipright-api 2>/dev/null || true
systemctl is-active ipright-api 2>/dev/null || true
systemctl is-enabled ipright-worker 2>/dev/null || true
systemctl is-active ipright-worker 2>/dev/null || true

echo "== nginx test =="
sudo nginx -t || true

echo "== done =="
