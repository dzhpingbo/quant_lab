"""Worker role wrapper for the Codex-auth local loop."""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from bridge_io import (
    bridge_dir,
    bridge_mode,
    call_publish_for_chatgpt,
    codex_status,
    find_latest_run,
    project_root,
    read_bridge_next_codex_task,
    read_text,
    rel_path,
    run_cmd,
    write_json,
    write_text,
)


def copy_task_to_inbox(config: dict[str, Any]) -> Path:
    src = rel_path(config, config.get("codex", {}).get("next_codex_task", "docs/chatgpt_bridge/reviewer_outbox/NEXT_CODEX_TASK.md"))
    dst = rel_path(config, config.get("codex", {}).get("worker_task", "docs/chatgpt_bridge/codex_inbox/TASK.md"))
    dst.parent.mkdir(parents=True, exist_ok=True)
    if bridge_mode(config) == "github_issue":
        task = read_bridge_next_codex_task(config)
        if task.strip():
            write_text(dst, task)
            return dst
    shutil.copy2(src, dst)
    return dst


def run_codex_worker(config: dict[str, Any], task_path: Path, timeout_sec: int = 7200) -> dict[str, Any]:
    root = project_root(config)
    codex_cfg = config.get("codex", {})
    command = str(codex_cfg.get("command", "codex"))
    last_message = rel_path(config, codex_cfg.get("worker_last_message", "docs/chatgpt_bridge/codex_outbox/CODEX_LAST_MESSAGE.md"))
    worker_template = read_text(root / "scripts" / "agent_loop" / "worker_prompt_template.md", 12000)
    prompt = f"{worker_template}\n\n---\n\n# TASK.md\n\n{task_path.read_text(encoding='utf-8', errors='replace')}\n"
    status = codex_status(config)
    attempts = []
    base = [command, "exec"]
    if status.get("supports_cd"):
        base.extend(["--cd", str(root)])
    if status.get("supports_skip_git_repo_check"):
        base.append("--skip-git-repo-check")
    if status.get("supports_output_last_message"):
        base.extend(["-o", str(last_message)])
    approval = str(codex_cfg.get("approval", "")).lower()
    if status.get("supports_bypass_approvals_and_sandbox") and approval in {"full-auto", "full_auto", "bypass", "danger-full-access"}:
        bypass = list(base)
        bypass.append("--dangerously-bypass-approvals-and-sandbox")
        bypass.append("-")
        attempts.append(bypass)
    if status.get("supports_full_auto"):
        full = list(base)
        full.append("--full-auto")
        if status.get("supports_sandbox") and codex_cfg.get("sandbox"):
            full.extend(["--sandbox", str(codex_cfg.get("sandbox"))])
        full.append("-")
        attempts.append(full)
    fallback = list(base)
    fallback.append("-")
    attempts.append(fallback)

    last_proc = None
    for cmd in attempts:
        proc = run_cmd(cmd, root, input_text=prompt, timeout=timeout_sec)
        last_proc = proc
        if proc.returncode == 0:
            return {
                "role": "worker",
                "success": True,
                "command": cmd,
                "returncode": proc.returncode,
                "stdout_tail": proc.stdout[-4000:],
                "stderr_tail": proc.stderr[-4000:],
                "last_message": str(last_message),
                "codex_status": status,
            }
    return {
        "role": "worker",
        "success": False,
        "command": attempts[-1],
        "returncode": last_proc.returncode if last_proc else None,
        "stdout_tail": (last_proc.stdout if last_proc else "")[-4000:],
        "stderr_tail": (last_proc.stderr if last_proc else "")[-4000:],
        "last_message": str(last_message),
        "codex_status": status,
    }


def capture_last_message(config: dict[str, Any]) -> str:
    path = rel_path(config, config.get("codex", {}).get("worker_last_message", "docs/chatgpt_bridge/codex_outbox/CODEX_LAST_MESSAGE.md"))
    return read_text(path, 12000)


def detect_new_run(config: dict[str, Any], before: Path | None) -> Path | None:
    after = find_latest_run(config)
    if before is None:
        return after
    if after and after.name != before.name:
        return after
    return None


def write_CODEX_RUN_STATUS(config: dict[str, Any], status: dict[str, Any]) -> Path:
    out = bridge_dir(config) / "codex_outbox" / "CODEX_RUN_STATUS.json"
    status = dict(status)
    status["written_at"] = datetime.now().isoformat(timespec="seconds")
    return write_json(out, status)


def call_publish_after_worker(config: dict[str, Any], run_dir: Path | None) -> dict[str, Any]:
    return call_publish_for_chatgpt(config, run_dir=run_dir)


def write_worker_message(config: dict[str, Any], text: str) -> Path:
    path = rel_path(config, config.get("codex", {}).get("worker_last_message", "docs/chatgpt_bridge/codex_outbox/CODEX_LAST_MESSAGE.md"))
    return write_text(path, text)


def publish_worker_status(config: dict[str, Any], status: dict[str, Any], round_index: int | None = None) -> dict[str, Any]:
    from bridge_io import publish_bridge_worker_status

    return publish_bridge_worker_status(config, status, round_index=round_index)
