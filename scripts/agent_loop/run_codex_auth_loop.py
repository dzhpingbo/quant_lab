"""Local no-API-key Codex auth loop for quant_lab us_stock_selection.

The loop uses the installed Codex CLI auth/session state.  It does not call the
OpenAI API directly and does not require OPENAI_API_KEY.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from bridge_io import (
    archive_round,
    bridge_dir,
    bridge_mode,
    call_publish_for_chatgpt,
    codex_status,
    detect_safety_violation,
    ensure_bridge_dirs,
    find_latest_run,
    initialize_bridge,
    load_config,
    project_root,
    publish_bridge_dry_run,
    publish_bridge_need_human,
    publish_bridge_round_summary,
    publish_bridge_worker_status,
    read_bridge_current_task,
    read_text,
    write_json,
)
from codex_reviewer import build_review_task, publish_reviewer_outputs, run_codex_reviewer, validate_reviewer_outputs, write_invalid_reviewer_stop
from codex_worker import (
    call_publish_after_worker,
    capture_last_message,
    copy_task_to_inbox,
    detect_new_run,
    run_codex_worker,
    write_CODEX_RUN_STATUS,
    write_worker_message,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Codex auth-loop with Reviewer and Worker roles.")
    parser.add_argument("--config", default="scripts/agent_loop/loop_config_auth.yaml")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-rounds", type=int, default=None)
    parser.add_argument("--review-only", action="store_true")
    parser.add_argument("--worker-only", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = Path.cwd() / config_path
    config = load_config(config_path)
    max_rounds = int(args.max_rounds or config.get("loop", {}).get("max_rounds", 10))
    ensure_bridge_dirs(config)
    try:
        bridge_context = initialize_bridge(config)
    except Exception as exc:
        summary = {
            "mode": "dry_run" if args.dry_run else "run",
            "status": "bridge_init_failed",
            "bridge_mode": bridge_mode(config),
            "project_root": str(project_root(config)),
            "error": str(exc),
            "openai_api_key_required": False,
            "openai_api_key_present_but_unused": bool(os.environ.get("OPENAI_API_KEY")),
        }
        write_json(bridge_dir(config) / "codex_outbox" / "CODEX_RUN_STATUS.json", summary)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        raise SystemExit(2)
    status = codex_status(config)
    latest = find_latest_run(config)
    summary: dict[str, Any] = {
        "mode": "dry_run" if args.dry_run else "run",
        "bridge_mode": bridge_mode(config),
        "bridge_context": bridge_context,
        "project_root": str(project_root(config)),
        "openai_api_key_required": False,
        "openai_api_key_present_but_unused": bool(os.environ.get("OPENAI_API_KEY")),
        "codex_status": status,
        "latest_run_before_loop": str(latest) if latest else "",
        "max_rounds": max_rounds,
        "rounds": [],
    }
    if status.get("version_returncode") != 0 or status.get("exec_help_returncode") != 0:
        summary["status"] = "codex_cli_unavailable"
        write_json(bridge_dir(config) / "codex_outbox" / "CODEX_RUN_STATUS.json", summary)
        publish_bridge_round_summary(config, summary, round_index=None)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        raise SystemExit(1)

    if latest is not None:
        publish = call_publish_for_chatgpt(config, run_dir=latest)
        summary["initial_publish"] = {"returncode": publish.get("returncode"), "manifest_run_id": publish.get("manifest", {}).get("run_id")}

    if args.dry_run:
        task = build_review_task(config, round_index=1)
        summary.update(
            {
                "status": "dry_run_passed",
                "review_task": str(task),
                "would_call_reviewer": True,
                "would_call_worker": not args.review_only,
            }
        )
        write_json(bridge_dir(config) / "codex_outbox" / "CODEX_RUN_STATUS.json", summary)
        publish_result = publish_bridge_dry_run(config, summary)
        if publish_result:
            summary["bridge_publish_dry_run"] = publish_result
            write_json(bridge_dir(config) / "codex_outbox" / "CODEX_RUN_STATUS.json", summary)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    consecutive_failures = 0
    current_latest = latest
    for round_index in range(1, max_rounds + 1):
        round_status: dict[str, Any] = {"round": round_index, "phase": "review"}
        current_task = read_bridge_current_task(config)
        round_status["current_task_present"] = bool(current_task.strip())
        current_task_violations = detect_safety_violation(config, current_task)
        if current_task_violations:
            reason = f"CURRENT_TASK blocked by safety gate: {','.join(current_task_violations)}"
            write_invalid_reviewer_stop(config, reason)
            validation = validate_reviewer_outputs(config)
            round_status.update(
                {
                    "phase": "blocked_by_safety_gate",
                    "decision": "NEED_HUMAN",
                    "safety_violations": current_task_violations,
                    "reviewer_validation": validation,
                }
            )
            publish_reviewer_outputs(config, validation, round_index)
            publish_bridge_need_human(config, reason, current_task_violations, round_index=round_index)
            summary["rounds"].append(round_status)
            summary["status"] = "stopped_need_human"
            finalize_round(config, round_status, round_index)
            break
        task = build_review_task(config, round_index=round_index)
        round_status["review_task"] = str(task)
        if not args.worker_only:
            reviewer = run_codex_reviewer(config, task)
            round_status["reviewer_run"] = reviewer
            if not reviewer.get("success"):
                consecutive_failures += 1
                write_invalid_reviewer_stop(config, "Codex reviewer execution failed. Check REVIEWER_LAST_MESSAGE.md and CODEX_RUN_STATUS.json.")
                validation = validate_reviewer_outputs(config)
                round_status["reviewer_validation"] = validation
                publish_reviewer_outputs(config, validation, round_index)
                summary["rounds"].append(round_status)
                if should_stop_on_error(config, consecutive_failures):
                    summary["status"] = "stopped_reviewer_failed"
                    finalize_round(config, round_status, round_index)
                    break
            validation = validate_reviewer_outputs(config)
            round_status["reviewer_validation"] = validation
            if not validation.get("valid"):
                consecutive_failures += 1
                write_invalid_reviewer_stop(config, validation.get("error", "Invalid reviewer output"))
                validation = validate_reviewer_outputs(config)
                round_status["reviewer_validation_after_stop"] = validation
                publish_reviewer_outputs(config, validation, round_index)
                summary["rounds"].append(round_status)
                if should_stop_on_error(config, consecutive_failures):
                    summary["status"] = "stopped_invalid_reviewer_output"
                    finalize_round(config, round_status, round_index)
                    break
            publish_reviewer_outputs(config, validation, round_index)
            decision = str(validation.get("decision_value", "")).upper()
            round_status["decision"] = decision
            if decision in {"STOP", "NEED_HUMAN"}:
                round_status["phase"] = "stopped_by_reviewer"
                summary["rounds"].append(round_status)
                summary["status"] = f"stopped_{decision.lower()}"
                finalize_round(config, round_status, round_index)
                break
            if args.review_only:
                round_status["phase"] = "review_only_complete"
                summary["rounds"].append(round_status)
                summary["status"] = "review_only_complete"
                finalize_round(config, round_status, round_index)
                break

        round_status["phase"] = "worker"
        before = current_latest or find_latest_run(config)
        worker_task = copy_task_to_inbox(config)
        round_status["worker_task"] = str(worker_task)
        worker_task_text = read_text(worker_task, 30000)
        worker_task_violations = detect_safety_violation(config, worker_task_text)
        if worker_task_violations:
            reason = f"Worker task blocked by safety gate: {','.join(worker_task_violations)}"
            round_status.update({"phase": "blocked_by_safety_gate", "decision": "NEED_HUMAN", "safety_violations": worker_task_violations})
            write_worker_message(config, reason + "\nWorker was not executed.\n")
            write_CODEX_RUN_STATUS(config, round_status)
            publish_bridge_need_human(config, reason, worker_task_violations, round_index=round_index)
            publish_bridge_worker_status(config, round_status, round_index=round_index)
            summary["rounds"].append(round_status)
            summary["status"] = "stopped_need_human"
            finalize_round(config, round_status, round_index)
            break
        worker = run_codex_worker(config, worker_task)
        round_status["worker_run"] = worker
        if not worker.get("success"):
            consecutive_failures += 1
            write_worker_message(config, "Worker Codex execution failed. See CODEX_RUN_STATUS.json.\n")
            round_status["worker_last_message"] = capture_last_message(config)
            write_CODEX_RUN_STATUS(config, round_status)
            publish_bridge_worker_status(config, round_status, round_index=round_index)
            summary["rounds"].append(round_status)
            if should_stop_on_error(config, consecutive_failures):
                summary["status"] = "stopped_worker_failed"
                finalize_round(config, round_status, round_index)
                break
        new_run = detect_new_run(config, before)
        round_status["new_run"] = str(new_run) if new_run else ""
        publish = call_publish_after_worker(config, run_dir=new_run or find_latest_run(config))
        round_status["post_worker_publish"] = {"returncode": publish.get("returncode"), "manifest_run_id": publish.get("manifest", {}).get("run_id")}
        write_CODEX_RUN_STATUS(config, round_status)
        publish_bridge_worker_status(config, round_status, round_index=round_index)
        summary["rounds"].append(round_status)
        finalize_round(config, round_status, round_index)
        current_latest = new_run or find_latest_run(config)
        if args.worker_only:
            summary["status"] = "worker_only_complete"
            break
    else:
        summary["status"] = "max_rounds_reached"

    if "status" not in summary:
        summary["status"] = "completed"
    write_JSON_status = bridge_dir(config) / "codex_outbox" / "CODEX_RUN_STATUS.json"
    write_json(write_JSON_status, summary)
    publish_bridge_round_summary(config, summary, round_index=None)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def should_stop_on_error(config: dict[str, Any], consecutive_failures: int) -> bool:
    if bool(config.get("loop", {}).get("stop_on_error", True)):
        return True
    return consecutive_failures >= int(config.get("loop", {}).get("consecutive_failure_limit", 2))


def finalize_round(config: dict[str, Any], round_status: dict[str, Any], round_index: int) -> Path:
    archive = archive_round(config, round_index)
    round_status["round_archive"] = str(archive)
    publish_bridge_round_summary(config, round_status, round_index=round_index)
    return archive


if __name__ == "__main__":
    main()
