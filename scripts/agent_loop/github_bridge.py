"""GitHub Issue bridge for the Codex auth loop.

This module only talks to GitHub through the installed ``gh`` CLI.  It never
reads, prints, or stores GitHub tokens, and it does not use the OpenAI API.
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from bridge_io import (
    bridge_dir,
    project_root,
    read_json,
    read_text,
    rel_path,
    run_cmd,
    truncate_large_text,
    write_json,
    write_text,
)


CONTROL_SECTIONS = [
    "CURRENT_TASK",
    "REVIEWER_DECISION",
    "NEXT_CODEX_TASK",
    "WORKER_STATUS",
    "RUN_OUTPUTS",
    "SAFETY_GATE_RESULT",
    "ROUND_ARCHIVE",
    "HUMAN_ACTION_REQUIRED",
]


class GitHubBridgeError(RuntimeError):
    """Raised when the GitHub bridge cannot be initialized safely."""


def github_config(config: dict[str, Any]) -> dict[str, Any]:
    return dict(config.get("bridge", {}).get("github", {}) or {})


def state_dir(config: dict[str, Any]) -> Path:
    gh_cfg = github_config(config)
    value = gh_cfg.get("state_dir") or config.get("bridge", {}).get("state_dir") or "docs/chatgpt_bridge/github_state"
    return rel_path(config, value)


def init_bridge(config: dict[str, Any]) -> dict[str, Any]:
    """Initialize gh auth, repo detection, the control issue, and state files."""
    info = find_or_create_control_issue(config)
    config["_github_bridge"] = info
    issue = read_control_issue(config)
    current_task = parse_current_task(issue)
    update_state_files(
        config,
        current_task=current_task,
        round_summary=render_round_summary(
            {
                "status": "github_bridge_initialized",
                "repo": info.get("repo", ""),
                "issue_number": info.get("issue_number"),
                "issue_url": info.get("issue_url", ""),
            }
        ),
    )
    return {**info, "current_task_present": bool(current_task.strip())}


def ensure_gh_auth(config: dict[str, Any]) -> dict[str, Any]:
    """Check gh CLI and auth state with clear setup hints on failure."""
    root = project_root(config)
    if shutil.which("gh") is None:
        raise GitHubBridgeError(_setup_hint("GitHub CLI not found: gh is not installed or not on PATH.", root))

    version = run_cmd(["gh", "--version"], root, timeout=30)
    auth = run_cmd(["gh", "auth", "status"], root, timeout=30)
    remotes = run_cmd(["git", "remote", "-v"], root, timeout=30)
    diagnostics = {
        "gh_version_returncode": version.returncode,
        "gh_version_stdout": version.stdout.strip(),
        "gh_version_stderr": version.stderr.strip(),
        "gh_auth_status_returncode": auth.returncode,
        "gh_auth_status_stdout": auth.stdout.strip(),
        "gh_auth_status_stderr": auth.stderr.strip(),
        "git_remote_returncode": remotes.returncode,
        "git_remote_stdout": remotes.stdout.strip(),
        "git_remote_stderr": remotes.stderr.strip(),
    }
    if version.returncode != 0:
        raise GitHubBridgeError(_setup_hint(f"GitHub CLI check failed:\n{version.stderr or version.stdout}", root, diagnostics))
    if auth.returncode != 0:
        raise GitHubBridgeError(_setup_hint(f"GitHub CLI is not logged in:\n{auth.stderr or auth.stdout}", root, diagnostics))
    return diagnostics


def detect_repo(config: dict[str, Any]) -> str:
    gh_cfg = github_config(config)
    configured = str(gh_cfg.get("repo") or "auto_detect").strip()
    if configured and configured != "auto_detect":
        return normalize_repo(configured)

    root = project_root(config)
    inside = run_cmd(["git", "rev-parse", "--is-inside-work-tree"], root, timeout=30)
    remotes = run_cmd(["git", "remote", "-v"], root, timeout=30)
    if inside.returncode != 0:
        raise GitHubBridgeError(
            _setup_hint(
                "Cannot auto-detect GitHub repo because project_root is not inside a git repository.",
                root,
                {
                    "git_rev_parse_returncode": inside.returncode,
                    "git_rev_parse_stdout": inside.stdout.strip(),
                    "git_rev_parse_stderr": inside.stderr.strip(),
                    "git_remote_returncode": remotes.returncode,
                    "git_remote_stdout": remotes.stdout.strip(),
                    "git_remote_stderr": remotes.stderr.strip(),
                },
            )
        )

    origin = run_cmd(["git", "remote", "get-url", "origin"], root, timeout=30)
    if origin.returncode != 0 or not origin.stdout.strip():
        raise GitHubBridgeError(
            _setup_hint(
                "Cannot auto-detect GitHub repo because git remote origin is missing.",
                root,
                {
                    "git_remote_get_url_returncode": origin.returncode,
                    "git_remote_get_url_stdout": origin.stdout.strip(),
                    "git_remote_get_url_stderr": origin.stderr.strip(),
                    "git_remote_stdout": remotes.stdout.strip(),
                    "git_remote_stderr": remotes.stderr.strip(),
                },
            )
        )
    return parse_github_remote(origin.stdout.strip())


def normalize_repo(value: str) -> str:
    value = value.strip()
    if re.fullmatch(r"[\w.-]+/[\w.-]+", value):
        return value[:-4] if value.endswith(".git") else value
    return parse_github_remote(value)


def parse_github_remote(remote: str) -> str:
    remote = remote.strip()
    patterns = [
        r"^git@github\.com:(?P<repo>[\w.-]+/[\w.-]+?)(?:\.git)?$",
        r"^ssh://git@github\.com/(?P<repo>[\w.-]+/[\w.-]+?)(?:\.git)?$",
        r"^https://(?:[^/@]+@)?github\.com/(?P<repo>[\w.-]+/[\w.-]+?)(?:\.git)?/?$",
        r"^http://(?:[^/@]+@)?github\.com/(?P<repo>[\w.-]+/[\w.-]+?)(?:\.git)?/?$",
    ]
    for pattern in patterns:
        match = re.match(pattern, remote)
        if match:
            return match.group("repo")
    raise GitHubBridgeError(f"Unable to parse GitHub repo from remote origin: {remote}")


def find_or_create_control_issue(config: dict[str, Any]) -> dict[str, Any]:
    gh_cfg = github_config(config)
    if not bool(gh_cfg.get("enabled", True)):
        raise GitHubBridgeError("GitHub bridge is configured with github.enabled=false.")
    if not bool(gh_cfg.get("use_gh_cli", True)):
        raise GitHubBridgeError("GitHub bridge currently supports use_gh_cli=true only.")

    diagnostics = ensure_gh_auth(config)
    repo = detect_repo(config)
    title = str(gh_cfg.get("issue_title") or "Codex Agent Loop Control")
    issue_number = gh_cfg.get("issue_number")
    if issue_number:
        issue = gh_json(config, ["issue", "view", str(issue_number), "--repo", repo, "--json", "number,title,url"])
        info = {
            "mode": "github_issue",
            "repo": repo,
            "issue_number": int(issue["number"]),
            "issue_title": issue.get("title", title),
            "issue_url": issue.get("url", ""),
            "gh_diagnostics": diagnostics,
        }
        update_state_files(config, bridge_info=info)
        return info

    existing = gh_json(config, ["issue", "list", "--repo", repo, "--state", "open", "--limit", "100", "--json", "number,title,url"])
    for issue in existing:
        if str(issue.get("title", "")).strip() == title:
            info = {
                "mode": "github_issue",
                "repo": repo,
                "issue_number": int(issue["number"]),
                "issue_title": issue.get("title", title),
                "issue_url": issue.get("url", ""),
                "gh_diagnostics": diagnostics,
            }
            update_state_files(config, bridge_info=info)
            return info

    if not bool(gh_cfg.get("create_issue_if_missing", True)):
        raise GitHubBridgeError(f'GitHub control issue "{title}" was not found and create_issue_if_missing=false.')

    body_path = state_dir(config) / "CONTROL_ISSUE_BODY.md"
    write_text(body_path, render_control_issue_body())
    created = run_gh(config, ["issue", "create", "--repo", repo, "--title", title, "--body-file", str(body_path)])
    if created.returncode != 0:
        raise GitHubBridgeError(f"Failed to create GitHub control issue:\n{created.stderr or created.stdout}")
    match = re.search(r"/issues/(\d+)", created.stdout)
    if not match:
        raise GitHubBridgeError(f"GitHub issue was created but issue number could not be parsed from output:\n{created.stdout}")
    issue_number = int(match.group(1))
    issue = gh_json(config, ["issue", "view", str(issue_number), "--repo", repo, "--json", "number,title,url"])
    info = {
        "mode": "github_issue",
        "repo": repo,
        "issue_number": int(issue["number"]),
        "issue_title": issue.get("title", title),
        "issue_url": issue.get("url", created.stdout.strip()),
        "gh_diagnostics": diagnostics,
    }
    update_state_files(config, bridge_info=info)
    return info


def read_control_issue(config: dict[str, Any]) -> dict[str, Any]:
    info = get_bridge_info(config)
    issue = gh_json(
        config,
        [
            "issue",
            "view",
            str(info["issue_number"]),
            "--repo",
            str(info["repo"]),
            "--json",
            "number,title,body,url,comments",
        ],
    )
    return issue


def parse_current_task(issue: dict[str, Any]) -> str:
    task = parse_latest_section(issue, "CURRENT_TASK")
    if "请在这里写入下一轮任务" in task:
        return ""
    return task


def parse_next_codex_task(issue: dict[str, Any]) -> str:
    return parse_latest_section(issue, "NEXT_CODEX_TASK")


def read_current_task(config: dict[str, Any]) -> str:
    issue = read_control_issue(config)
    current_task = parse_current_task(issue)
    update_state_files(config, current_task=current_task)
    return current_task


def read_next_codex_task(config: dict[str, Any]) -> str:
    issue = read_control_issue(config)
    return parse_next_codex_task(issue)


def publish_reviewer_decision(
    config: dict[str, Any],
    decision: dict[str, Any],
    next_task: str,
    notes: str = "",
    validation: dict[str, Any] | None = None,
    round_index: int | None = None,
) -> dict[str, Any]:
    validation = validation or {}
    safety = {
        "decision_value": validation.get("decision_value") or decision.get("decision"),
        "valid": validation.get("valid", True),
        "error": validation.get("error", ""),
        "requires_human_review": bool(decision.get("requires_human_review")) or str(decision.get("decision", "")).upper() == "NEED_HUMAN",
    }
    update_state_files(config, reviewer_decision=decision, next_codex_task=next_task)
    body = "\n\n".join(
        [
            f"# Reviewer Decision{_round_suffix(round_index)}",
            _section("REVIEWER_DECISION", f"```json\n{json.dumps(decision, ensure_ascii=False, indent=2)}\n```"),
            _section("NEXT_CODEX_TASK", next_task or "_empty_"),
            _section("SAFETY_GATE_RESULT", f"```json\n{json.dumps(safety, ensure_ascii=False, indent=2)}\n```"),
            _section("HUMAN_ACTION_REQUIRED", human_action_text(decision, safety)),
            _section("RUN_OUTPUTS", notes[:6000] if notes else "_Reviewer notes file updated locally._"),
        ]
    )
    return post_issue_comment(config, body)


def publish_next_codex_task(config: dict[str, Any], next_task: str, round_index: int | None = None) -> dict[str, Any]:
    update_state_files(config, next_codex_task=next_task)
    body = "\n\n".join([f"# Next Codex Task{_round_suffix(round_index)}", _section("NEXT_CODEX_TASK", next_task or "_empty_")])
    return post_issue_comment(config, body)


def publish_worker_status(
    config: dict[str, Any],
    status: dict[str, Any],
    last_message: str = "",
    round_index: int | None = None,
) -> dict[str, Any]:
    update_state_files(config, codex_run_status=status, round_summary=render_round_summary(status))
    outputs = {
        "new_run": status.get("new_run", ""),
        "post_worker_publish": status.get("post_worker_publish", {}),
        "worker_task": status.get("worker_task", ""),
    }
    body = "\n\n".join(
        [
            f"# Worker Status{_round_suffix(round_index)}",
            _section("WORKER_STATUS", f"```json\n{json.dumps(status, ensure_ascii=False, indent=2)}\n```"),
            _section("RUN_OUTPUTS", f"```json\n{json.dumps(outputs, ensure_ascii=False, indent=2)}\n```"),
            _section("HUMAN_ACTION_REQUIRED", "_none_" if status.get("phase") != "blocked_by_safety_gate" else "Worker was not executed because the safety gate blocked the task."),
            truncate_large_text(last_message, 6000) if last_message else "",
        ]
    ).strip()
    return post_issue_comment(config, body)


def publish_round_summary(config: dict[str, Any], summary: dict[str, Any], round_index: int | None = None) -> dict[str, Any]:
    update_state_files(config, codex_run_status=summary, round_summary=render_round_summary(summary))
    archive = summary.get("round_archive") or summary.get("archive") or ""
    body = "\n\n".join(
        [
            f"# Round Summary{_round_suffix(round_index)}",
            _section("WORKER_STATUS", f"```json\n{json.dumps(summary, ensure_ascii=False, indent=2)}\n```"),
            _section("ROUND_ARCHIVE", str(archive) if archive else "_not archived yet_"),
        ]
    )
    return post_issue_comment(config, body)


def publish_need_human(
    config: dict[str, Any],
    reason: str,
    violations: list[str] | None = None,
    round_index: int | None = None,
) -> dict[str, Any]:
    decision = {
        "decision": "NEED_HUMAN",
        "reason": reason,
        "violations": violations or [],
        "requires_human_review": True,
        "written_at": datetime.now().isoformat(timespec="seconds"),
    }
    update_state_files(config, reviewer_decision=decision, next_codex_task="暂停执行，等待用户/ChatGPT 人工审阅。\n")
    body = "\n\n".join(
        [
            f"# Human Action Required{_round_suffix(round_index)}",
            _section("REVIEWER_DECISION", f"```json\n{json.dumps(decision, ensure_ascii=False, indent=2)}\n```"),
            _section("SAFETY_GATE_RESULT", f"Blocked by safety gate: {', '.join(violations or []) or reason}"),
            _section("HUMAN_ACTION_REQUIRED", reason),
        ]
    )
    return post_issue_comment(config, body)


def publish_dry_run(config: dict[str, Any], summary: dict[str, Any]) -> dict[str, Any]:
    update_state_files(config, codex_run_status=summary, round_summary=render_round_summary(summary))
    body = "\n\n".join(
        [
            "# Dry Run Status",
            _section("WORKER_STATUS", f"```json\n{json.dumps(summary, ensure_ascii=False, indent=2)}\n```"),
            _section("RUN_OUTPUTS", "Dry-run completed. Reviewer and Worker were not executed."),
            _section("HUMAN_ACTION_REQUIRED", "_none_"),
        ]
    )
    return post_issue_comment(config, body)


def post_issue_comment(config: dict[str, Any], body: str) -> dict[str, Any]:
    info = get_bridge_info(config)
    comment_path = state_dir(config) / "LAST_ISSUE_COMMENT.md"
    stamped = f"{body.rstrip()}\n\n---\n_written_at: {datetime.now().isoformat(timespec='seconds')}_\n"
    write_text(comment_path, stamped)
    proc = run_gh(config, ["issue", "comment", str(info["issue_number"]), "--repo", str(info["repo"]), "--body-file", str(comment_path)])
    if proc.returncode != 0:
        raise GitHubBridgeError(f"Failed to post GitHub issue comment:\n{proc.stderr or proc.stdout}")
    return {
        "repo": info.get("repo", ""),
        "issue_number": info.get("issue_number"),
        "issue_url": info.get("issue_url", ""),
        "comment_stdout": proc.stdout.strip(),
        "posted_at": datetime.now().isoformat(timespec="seconds"),
    }


def update_state_files(
    config: dict[str, Any],
    *,
    current_task: str | None = None,
    reviewer_decision: dict[str, Any] | None = None,
    next_codex_task: str | None = None,
    codex_run_status: dict[str, Any] | None = None,
    round_summary: str | None = None,
    bridge_info: dict[str, Any] | None = None,
) -> dict[str, str]:
    target = state_dir(config)
    target.mkdir(parents=True, exist_ok=True)
    written: dict[str, str] = {}
    if current_task is not None:
        written["CURRENT_TASK.md"] = str(write_text(target / "CURRENT_TASK.md", current_task))
    if reviewer_decision is not None:
        written["REVIEWER_DECISION.json"] = str(write_json(target / "REVIEWER_DECISION.json", reviewer_decision))
    if next_codex_task is not None:
        written["NEXT_CODEX_TASK.md"] = str(write_text(target / "NEXT_CODEX_TASK.md", next_codex_task))
    if codex_run_status is not None:
        written["CODEX_RUN_STATUS.json"] = str(write_json(target / "CODEX_RUN_STATUS.json", codex_run_status))
    if round_summary is not None:
        written["ROUND_SUMMARY.md"] = str(write_text(target / "ROUND_SUMMARY.md", round_summary))
    if bridge_info is not None:
        safe_info = dict(bridge_info)
        safe_info.pop("gh_diagnostics", None)
        written["BRIDGE_INFO.json"] = str(write_json(target / "BRIDGE_INFO.json", safe_info))
    maybe_commit_state_files(config, written)
    return written


def maybe_commit_state_files(config: dict[str, Any], written: dict[str, str]) -> None:
    if not written:
        return
    gh_cfg = github_config(config)
    if not bool(gh_cfg.get("allow_commit_state_files", False)):
        return
    root = project_root(config)
    paths = [str(Path(path)) for path in written.values()]
    add = run_cmd(["git", "add", *paths], root, timeout=60)
    if add.returncode != 0:
        raise GitHubBridgeError(f"Failed to stage GitHub state files:\n{add.stderr or add.stdout}")
    commit = run_cmd(["git", "commit", "-m", "Update Codex GitHub bridge state"], root, timeout=120)
    if commit.returncode != 0 and "nothing to commit" not in (commit.stdout + commit.stderr).lower():
        raise GitHubBridgeError(f"Failed to commit GitHub state files:\n{commit.stderr or commit.stdout}")
    if bool(gh_cfg.get("allow_push", False)):
        push = run_cmd(["git", "push"], root, timeout=300)
        if push.returncode != 0:
            raise GitHubBridgeError(f"Failed to push GitHub state files:\n{push.stderr or push.stdout}")


def get_bridge_info(config: dict[str, Any]) -> dict[str, Any]:
    cached = config.get("_github_bridge")
    if cached:
        return dict(cached)
    info_path = state_dir(config) / "BRIDGE_INFO.json"
    info = read_json(info_path)
    if info.get("repo") and info.get("issue_number"):
        config["_github_bridge"] = info
        return info
    info = find_or_create_control_issue(config)
    config["_github_bridge"] = info
    return info


def gh_json(config: dict[str, Any], args: list[str]) -> Any:
    proc = run_gh(config, args)
    if proc.returncode != 0:
        raise GitHubBridgeError(f"gh command failed: gh {' '.join(args)}\n{proc.stderr or proc.stdout}")
    try:
        return json.loads(proc.stdout or "null")
    except json.JSONDecodeError as exc:
        raise GitHubBridgeError(f"gh command did not return valid JSON: gh {' '.join(args)}\n{exc}\n{proc.stdout[:2000]}") from exc


def run_gh(config: dict[str, Any], args: list[str]):
    return run_cmd(["gh", *args], project_root(config), timeout=120)


def parse_latest_section(issue: dict[str, Any], section_name: str) -> str:
    candidates: list[tuple[str, str]] = []
    body = issue.get("body") or ""
    found = extract_section(body, section_name)
    if found:
        candidates.append(("0000-issue-body", found))
    for comment in issue.get("comments") or []:
        text = comment.get("body") or ""
        found = extract_section(text, section_name)
        if found:
            candidates.append((str(comment.get("createdAt") or ""), found))
    if not candidates:
        return ""
    candidates.sort(key=lambda item: item[0])
    return candidates[-1][1].strip()


def extract_section(text: str, section_name: str) -> str:
    marker = re.compile(
        rf"<!--\s*codex-bridge:section\s+{re.escape(section_name)}\s*-->\s*(.*?)\s*<!--\s*/codex-bridge:section\s+{re.escape(section_name)}\s*-->",
        re.IGNORECASE | re.DOTALL,
    )
    match = marker.search(text or "")
    if match:
        return strip_section_heading(match.group(1).strip(), section_name)

    heading = re.compile(
        rf"(?ims)^#{{1,6}}\s+{re.escape(section_name)}\s*$\s*(.*?)(?=^#{{1,6}}\s+[A-Z0-9_ ]+\s*$|\Z)"
    )
    match = heading.search(text or "")
    if match:
        return match.group(1).strip()
    return ""


def strip_section_heading(text: str, section_name: str) -> str:
    lines = text.splitlines()
    if not lines:
        return ""
    if re.match(rf"^#{{1,6}}\s+{re.escape(section_name)}\s*$", lines[0].strip(), re.IGNORECASE):
        lines = lines[1:]
        while lines and not lines[0].strip():
            lines = lines[1:]
    return "\n".join(lines).strip()


def render_control_issue_body() -> str:
    parts = [
        "# Codex Agent Loop Control",
        "This issue is the automation bridge for ChatGPT / Reviewer / Worker / Codex. Use comments or edit the CURRENT_TASK section to provide the next task. The loop writes decisions, statuses, run outputs, safety gate results, and archive paths back here.",
    ]
    defaults = {
        "CURRENT_TASK": "请在这里写入下一轮任务。也可以新增一条包含 `## CURRENT_TASK` 的评论。",
        "HUMAN_ACTION_REQUIRED": "_none_",
    }
    for name in CONTROL_SECTIONS:
        parts.append(_section(name, defaults.get(name, "_pending_")))
    return "\n\n".join(parts) + "\n"


def render_round_summary(status: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# GitHub Bridge Round Summary",
            "",
            f"- status: `{status.get('status') or status.get('phase') or 'unknown'}`",
            f"- round: `{status.get('round', '')}`",
            f"- new_run: `{status.get('new_run', '')}`",
            f"- archive: `{status.get('round_archive') or status.get('archive') or ''}`",
            f"- written_at: `{datetime.now().isoformat(timespec='seconds')}`",
            "",
            "```json",
            json.dumps(status, ensure_ascii=False, indent=2),
            "```",
            "",
        ]
    )


def human_action_text(decision: dict[str, Any], safety: dict[str, Any]) -> str:
    if str(decision.get("decision", "")).upper() == "NEED_HUMAN" or safety.get("requires_human_review"):
        return str(decision.get("reason") or safety.get("error") or "Reviewer requested human review.")
    return "_none_"


def _section(name: str, content: str) -> str:
    return f"<!-- codex-bridge:section {name} -->\n## {name}\n\n{content.rstrip()}\n<!-- /codex-bridge:section {name} -->"


def _round_suffix(round_index: int | None) -> str:
    return "" if round_index is None else f" - Round {round_index:03d}"


def _setup_hint(reason: str, root: Path, diagnostics: dict[str, Any] | None = None) -> str:
    lines = [
        reason.strip(),
        "",
        "GitHub bridge setup required:",
        "1. Install GitHub CLI: https://cli.github.com/",
        "2. Run: gh auth login",
        "3. Ensure the current project_root is a git repository.",
        "4. Ensure git remote origin points to the intended GitHub repository.",
        "",
        f"project_root: {root}",
    ]
    if diagnostics:
        lines.extend(["", "Diagnostics:", json.dumps(diagnostics, ensure_ascii=False, indent=2)])
    return "\n".join(lines)
