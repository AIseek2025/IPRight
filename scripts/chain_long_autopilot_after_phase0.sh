#!/bin/zsh
set -euo pipefail

WORKSPACE_ROOT="/Users/brando/Documents/trae_projects/CodeMaster/isolated_autoruns/IPRight"

echo "[chain] waiting for current phase0 opencode run to finish..."
while pgrep -f "python3 /Users/brando/Documents/trae_projects/CodeMaster/isolated_autoruns/IPRight/scripts/run_pending_opencode_request.py" >/dev/null 2>&1; do
  sleep 20
done

echo "[chain] current phase0 run finished, launching 10h+ long autopilot..."
python3 "$WORKSPACE_ROOT/scripts/launch_codemaster_ipright_long_autopilot.py"
python3 "$WORKSPACE_ROOT/scripts/run_pending_opencode_request.py"
