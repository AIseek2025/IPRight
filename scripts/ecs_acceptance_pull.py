#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shlex
import shutil
import time
import traceback
from pathlib import Path

import paramiko


def main() -> int:
    parser = argparse.ArgumentParser(description="Run ECS acceptance and pull artifacts.")
    parser.add_argument("--host", required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--workspace", required=True)
    args = parser.parse_args()

    root = Path(args.workspace).resolve()
    local_demo = root / "scripts" / "demo_runner.py"
    pull_root = root / "tmp" / "ecs_acceptance"
    pull_exports = pull_root / "exports"
    result_path = pull_root / "result.json"

    pull_root.mkdir(parents=True, exist_ok=True)
    if pull_exports.exists():
        shutil.rmtree(pull_exports)
    pull_exports.mkdir(parents=True, exist_ok=True)
    result: dict[str, object] = {"stage": "init", "exit_code": None, "error": None}

    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(hostname=args.host, username=args.user, password=args.password, timeout=20)
        result["stage"] = "connected"

        sftp = client.open_sftp()
        sftp.put(str(local_demo), "/opt/ipright/scripts/demo_runner.py")
        result["stage"] = "uploaded_demo_runner"

        cmd = (
            "cd /opt/ipright && "
            ". backend/.venv/bin/activate && "
            "python -m pip install -q -r examples/demo_app/backend/requirements.txt && "
            "cd examples/demo_app/frontend && "
            "npm ci --silent && "
            "cd /opt/ipright && "
            "rm -rf tmp/demo_output && "
            "rm -f tmp/ecs_acceptance_done.txt tmp/ecs_acceptance_exit.txt tmp/ecs_acceptance_runtime.log && "
            "( python scripts/demo_runner.py && "
            "python scripts/export_pdf.py tmp/demo_output/exports ); "
            "rc=$?; echo \"$rc\" > tmp/ecs_acceptance_exit.txt; "
            "touch tmp/ecs_acceptance_done.txt; "
            "exit $rc"
        )
        launcher = (
            "bash -lc "
            + shlex.quote(
                "cd /opt/ipright && "
                f"nohup bash -lc {shlex.quote(cmd)} > tmp/ecs_acceptance_runtime.log 2>&1 < /dev/null & echo $!"
            )
        )
        stdin, stdout, stderr = client.exec_command(launcher, timeout=60)
        pid_text = stdout.read().decode("utf-8", errors="ignore").strip()
        result["stage"] = "remote_job_started"
        result["remote_pid"] = pid_text
        sftp.close()
        client.close()

        exit_code = None
        for _ in range(240):
            time.sleep(5)
            poll_client = paramiko.SSHClient()
            poll_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            poll_client.connect(hostname=args.host, username=args.user, password=args.password, timeout=20)
            stdin, stdout, stderr = poll_client.exec_command(
                "if [ -f /opt/ipright/tmp/ecs_acceptance_done.txt ]; then cat /opt/ipright/tmp/ecs_acceptance_exit.txt; fi",
                timeout=30,
            )
            exit_payload = stdout.read().decode("utf-8", errors="ignore").strip()
            poll_client.close()
            if exit_payload:
                exit_code = int(exit_payload)
                result["stage"] = "remote_command_finished"
                break

        fetch_client = paramiko.SSHClient()
        fetch_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        fetch_client.connect(hostname=args.host, username=args.user, password=args.password, timeout=20)
        fetch_sftp = fetch_client.open_sftp()

        runtime_stdout = ""
        try:
            runtime_stdout = fetch_sftp.file("/opt/ipright/tmp/ecs_acceptance_runtime.log", "r").read().decode("utf-8", errors="ignore")
        except FileNotFoundError:
            runtime_stdout = ""

        (pull_root / "ecs_stdout.log").write_text(runtime_stdout, encoding="utf-8")
        (pull_root / "ecs_stderr.log").write_text("", encoding="utf-8")

        if exit_code is None:
            result["stage"] = "remote_command_timeout"
            result["exit_code"] = -1
            fetch_sftp.close()
            fetch_client.close()
            result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            return 1

        result["exit_code"] = exit_code

        if exit_code == 0:
            for name in ["report.json", "screenshot_manifest.json"]:
                fetch_sftp.get(f"/opt/ipright/tmp/demo_output/{name}", str(pull_root / name))

            for name in [
                "software_manual.docx",
                "source_code_book.docx",
                "system_architecture.png",
                "software_manual.pdf",
                "source_code_book.pdf",
            ]:
                remote_path = f"/opt/ipright/tmp/demo_output/exports/{name}"
                try:
                    fetch_sftp.stat(remote_path)
                except FileNotFoundError:
                    continue
                fetch_sftp.get(remote_path, str(pull_exports / name))
            result["stage"] = "artifacts_pulled"

        fetch_sftp.close()
        fetch_client.close()
    except Exception:
        result["error"] = traceback.format_exc()
        result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return 1

    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if result.get("exit_code", 1) == 0 else int(result["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
