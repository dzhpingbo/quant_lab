"""Reviewer role wrapper for the Codex-auth local loop."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from bridge_io import (
    bridge_dir,
    bridge_mode,
    codex_status,
    detect_safety_violation,
    project_root,
    read_bridge_current_task,
    read_json,
    read_text,
    rel_path,
    run_cmd,
    summarize_review_files,
    write_json,
    write_text,
)


VALID_DECISIONS = {"CONTINUE", "STOP", "NEED_HUMAN"}


def build_review_task(config: dict[str, Any], round_index: int) -> Path:
    root = project_root(config)
    codex_cfg = config.get("codex", {})
    task_path = rel_path(config, codex_cfg.get("reviewer_task", "docs/chatgpt_bridge/reviewer_inbox/REVIEW_TASK.md"))
    template = read_text(root / "scripts" / "agent_loop" / "reviewer_prompt_template.md", max_chars=20000)
    review = summarize_review_files(config)
    current_task = read_bridge_current_task(config)
    current_task_header = "## GitHub Issue CURRENT_TASK" if bridge_mode(config) == "github_issue" else "## Local CURRENT_TASK"
    text = f"""{template}

---

# 自动注入的最新审阅上下文

round_index: `{round_index}`
project_root: `{root}`
bridge_mode: `{bridge_mode(config)}`

{current_task_header}

{current_task or "_未提供 CURRENT_TASK；Reviewer 可基于最新 run 和 NEXT_STEPS.md 继续审阅。_"}

## AGENTS.md

{read_text(root / "AGENTS.md", 12000)}

## docs/US_STOCK_SELECTION_AUTORUN.md

{read_text(root / "docs" / "US_STOCK_SELECTION_AUTORUN.md", 12000)}

## NEXT_STEPS.md

{read_text(root / "NEXT_STEPS.md", 8000)}

## RUN_SUMMARY.md

{read_text(root / "RUN_SUMMARY.md", 8000)}

## docs/chatgpt_bridge/LATEST.md

{read_text(bridge_dir(config) / "LATEST.md", 5000)}

## latest_run_manifest.json

```json
{json.dumps(review.get("manifest", {}), ensure_ascii=False, indent=2)}
```

## REVIEW_PACKET.md excerpt

{review.get("review_packet_excerpt", "")}

## selected_report.md excerpt

{review.get("selected_report_excerpt", "")}

## small_tables summary

{review.get("small_tables", "")}

请现在只执行 Reviewer 职责，并写出要求的三个文件。
"""
    write_text(task_path, text)
    return task_path


def run_codex_reviewer(config: dict[str, Any], task_path: Path, timeout_sec: int = 1800) -> dict[str, Any]:
    root = project_root(config)
    codex_cfg = config.get("codex", {})
    command = str(codex_cfg.get("command", "codex"))
    last_message = rel_path(config, codex_cfg.get("reviewer_last_message", "docs/chatgpt_bridge/reviewer_outbox/REVIEWER_LAST_MESSAGE.md"))
    prompt = task_path.read_text(encoding="utf-8", errors="replace")
    status = codex_status(config)
    attempts = []
    base = [command, "exec"]
    if status.get("supports_cd"):
        base.extend(["--cd", str(root)])
    if status.get("supports_skip_git_repo_check"):
        base.append("--skip-git-repo-check")
    if status.get("supports_output_last_message"):
        base.extend(["-o", str(last_message)])
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
                "role": "reviewer",
                "success": True,
                "command": cmd,
                "returncode": proc.returncode,
                "stdout_tail": proc.stdout[-4000:],
                "stderr_tail": proc.stderr[-4000:],
                "last_message": str(last_message),
                "codex_status": status,
            }
    return {
        "role": "reviewer",
        "success": False,
        "command": attempts[-1],
        "returncode": last_proc.returncode if last_proc else None,
        "stdout_tail": (last_proc.stdout if last_proc else "")[-4000:],
        "stderr_tail": (last_proc.stderr if last_proc else "")[-4000:],
        "last_message": str(last_message),
        "codex_status": status,
    }


def validate_reviewer_outputs(config: dict[str, Any]) -> dict[str, Any]:
    base = bridge_dir(config) / "reviewer_outbox"
    decision_path = base / "REVIEWER_DECISION.json"
    notes_path = base / "REVIEWER_NOTES.md"
    task_path = base / "NEXT_CODEX_TASK.md"
    result: dict[str, Any] = {
        "valid": False,
        "decision_path": str(decision_path),
        "notes_path": str(notes_path),
        "next_task_path": str(task_path),
        "error": "",
        "decision": {},
    }
    if not decision_path.exists():
        result["error"] = "REVIEWER_DECISION.json not found"
        return result
    if not task_path.exists():
        result["error"] = "NEXT_CODEX_TASK.md not found"
        return result
    decision = read_json(decision_path)
    raw = str(decision.get("decision", "")).upper()
    if raw not in VALID_DECISIONS:
        result["error"] = f"Invalid reviewer decision: {raw}"
        result["decision"] = decision
        return result
    violations = detect_safety_violation(config, task_path.read_text(encoding="utf-8", errors="replace"))
    if violations and raw == "CONTINUE":
        decision["decision"] = "NEED_HUMAN"
        decision["requires_human_review"] = True
        decision["reason"] = f"Safety violation in generated task: {','.join(violations)}"
        write_json(decision_path, decision)
        write_text(task_path, "暂停执行，等待用户/ChatGPT 人工审阅。\n")
        raw = "NEED_HUMAN"
    result.update({"valid": True, "decision": decision, "decision_value": raw})
    return result


def write_invalid_reviewer_stop(config: dict[str, Any], reason: str) -> None:
    base = bridge_dir(config) / "reviewer_outbox"
    base.mkdir(parents=True, exist_ok=True)
    write_json(
        base / "REVIEWER_DECISION.json",
        {
            "decision": "NEED_HUMAN",
            "reason": reason,
            "next_stage": "manual_review",
            "risk_level": "high",
            "allow_expand_universe": False,
            "allow_expand_nasdaq100": False,
            "allow_trade_execution": False,
            "requires_human_review": True,
            "codex_task_file": "docs/chatgpt_bridge/reviewer_outbox/NEXT_CODEX_TASK.md",
            "written_at": datetime.now().isoformat(timespec="seconds"),
        },
    )
    write_text(base / "REVIEWER_NOTES.md", f"# Reviewer invalid output\n\n{reason}\n")
    write_text(base / "NEXT_CODEX_TASK.md", "暂停执行，等待用户/ChatGPT 人工审阅。\n")


def publish_reviewer_outputs(config: dict[str, Any], validation: dict[str, Any], round_index: int) -> dict[str, Any]:
    from bridge_io import publish_bridge_reviewer_outputs

    return publish_bridge_reviewer_outputs(config, validation, round_index)
