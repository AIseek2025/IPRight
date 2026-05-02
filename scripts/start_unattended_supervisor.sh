#!/bin/zsh
set -euo pipefail

WORKSPACE_ROOT="/Users/brando/Documents/trae_projects/CodeMaster/isolated_autoruns/IPRight"
cd "$WORKSPACE_ROOT"

exec python3 "$WORKSPACE_ROOT/scripts/codemaster_supervisor.py" --max-hours 10 --continue-if-remaining
