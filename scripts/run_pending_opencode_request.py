from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import threading


CODEMASTER_ROOT = Path("/Users/brando/Documents/trae_projects/CodeMaster")
WORKSPACE_ROOT = Path("/Users/brando/Documents/trae_projects/CodeMaster/isolated_autoruns/IPRight")
REQUESTS_ROOT = WORKSPACE_ROOT / ".codemaster_orchestration" / "opencode" / "requests"
DISPATCH_ROOT = WORKSPACE_ROOT / ".codemaster_orchestration" / "opencode" / "dispatch"
ARTIFACTS_ROOT = WORKSPACE_ROOT / ".codemaster_orchestration" / "artifacts"


def _resolve_request_path() -> Path:
    if len(sys.argv) > 1:
        return Path(sys.argv[1])
    candidates = sorted(REQUESTS_ROOT.glob("opencode_session_request_*.json"))
    if not candidates:
        raise SystemExit("No opencode session request found.")
    return candidates[-1]


def _resolve_dispatch_path(trace_id: str) -> Path:
    return DISPATCH_ROOT / f"opencode_session_dispatch_{trace_id}.json"


def _stream_to_outputs(stream, console, target: Path) -> None:
    with target.open("w", encoding="utf-8") as handle:
        for line in iter(stream.readline, ""):
            console.write(line)
            console.flush()
            handle.write(line)
            handle.flush()
    stream.close()


def main() -> int:
    sys.path.insert(0, str(CODEMASTER_ROOT))
    from src.integrations.opencode_adapter import OpencodeBackendAdapter  # noqa: WPS433

    request_path = _resolve_request_path()
    payload = json.loads(request_path.read_text(encoding="utf-8"))
    command = payload.get("command")
    if not isinstance(command, list) or not command:
        raise SystemExit(f"Invalid command in {request_path}")
    trace_id = str(payload.get("trace_id") or "").strip()
    if not trace_id:
        raise SystemExit(f"Missing trace_id in {request_path}")
    dispatch_path = _resolve_dispatch_path(trace_id)
    if not dispatch_path.exists():
        raise SystemExit(f"Missing dispatch file for trace {trace_id}: {dispatch_path}")

    ARTIFACTS_ROOT.mkdir(parents=True, exist_ok=True)
    stdout_path = ARTIFACTS_ROOT / f"opencode_session_stdout_{trace_id}.log"
    stderr_path = ARTIFACTS_ROOT / f"opencode_session_stderr_{trace_id}.log"
    exitcode_path = ARTIFACTS_ROOT / f"opencode_session_exitcode_{trace_id}.txt"

    print(f"[opencode] request={request_path}")
    print(f"[opencode] dispatch={dispatch_path}")
    print("[opencode] launching prepared session command...")
    process = subprocess.Popen(
        command,
        cwd=str(WORKSPACE_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    stdout_thread = threading.Thread(
        target=_stream_to_outputs,
        args=(process.stdout, sys.stdout, stdout_path),
        daemon=True,
    )
    stderr_thread = threading.Thread(
        target=_stream_to_outputs,
        args=(process.stderr, sys.stderr, stderr_path),
        daemon=True,
    )
    stdout_thread.start()
    stderr_thread.start()
    returncode = process.wait()
    stdout_thread.join()
    stderr_thread.join()
    exitcode_path.write_text(str(returncode), encoding="utf-8")
    OpencodeBackendAdapter.complete_async_session_from_files(
        workspace_root=WORKSPACE_ROOT,
        dispatch_path=dispatch_path,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        exitcode_path=exitcode_path,
    )
    response_path = DISPATCH_ROOT / f"opencode_session_response_{trace_id}.json"
    print(f"[opencode] returncode={returncode}")
    print(f"[opencode] response={response_path}")
    return int(returncode)


if __name__ == "__main__":
    raise SystemExit(main())
