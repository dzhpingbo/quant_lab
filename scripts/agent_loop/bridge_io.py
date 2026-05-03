"""Shared IO helpers for the Codex-auth local agent loop."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import yaml


def load_config(path: Path | str) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def project_root(config: dict[str, Any]) -> Path:
    return Path(config.get("project_root", ".")).resolve()


def bridge_dir(config: dict[str, Any]) -> Path:
    bridge_cfg = config.get("bridge", {}) or {}
    value = config.get("bridge_dir") or bridge_cfg.get("local_cache_dir") or (project_root(config) / "docs" / "chatgpt_bridge")
    return Path(value).resolve()


def bridge_mode(config: dict[str, Any]) -> str:
    return str((config.get("bridge", {}) or {}).get("mode") or "local").strip().lower()


def github_state_dir(config: dict[str, Any]) -> Path:
    bridge_cfg = config.get("bridge", {}) or {}
    gh_cfg = bridge_cfg.get("github", {}) or {}
    value = gh_cfg.get("state_dir") or bridge_cfg.get("state_dir") or (bridge_dir(config) / "github_state")
    return rel_path(config, value)


def outputs_dir(config: dict[str, Any]) -> Path:
    return Path(config.get("outputs_dir", project_root(config) / "outputs" / "us_stock_selection")).resolve()


def rel_path(config: dict[str, Any], value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else project_root(config) / path


def ensure_bridge_dirs(config: dict[str, Any]) -> None:
    base = bridge_dir(config)
    for child in [
        base,
        base / "runs",
        base / "rounds",
        base / "reviewer_inbox",
        base / "reviewer_outbox",
        base / "codex_inbox",
        base / "codex_outbox",
        github_state_dir(config),
    ]:
        child.mkdir(parents=True, exist_ok=True)


def initialize_bridge(config: dict[str, Any]) -> dict[str, Any]:
    mode = bridge_mode(config)
    if mode == "local":
        return {"mode": "local", "bridge_dir": str(bridge_dir(config))}
    if mode == "github_issue":
        from github_bridge import init_bridge

        return init_bridge(config)
    raise ValueError(f"Unsupported bridge.mode: {mode}")


def read_bridge_current_task(config: dict[str, Any]) -> str:
    if bridge_mode(config) == "github_issue":
        from github_bridge import read_current_task

        return read_current_task(config)
    task_path = bridge_dir(config) / "reviewer_inbox" / "CURRENT_TASK.md"
    return read_text(task_path, 12000)


def read_bridge_next_codex_task(config: dict[str, Any]) -> str:
    if bridge_mode(config) == "github_issue":
        from github_bridge import read_next_codex_task

        return read_next_codex_task(config)
    return read_text(bridge_dir(config) / "reviewer_outbox" / "NEXT_CODEX_TASK.md", 20000)


def publish_bridge_dry_run(config: dict[str, Any], summary: dict[str, Any]) -> dict[str, Any]:
    if bridge_mode(config) == "github_issue":
        from github_bridge import publish_dry_run

        return publish_dry_run(config, summary)
    return {}


def publish_bridge_reviewer_outputs(config: dict[str, Any], validation: dict[str, Any], round_index: int) -> dict[str, Any]:
    if bridge_mode(config) != "github_issue":
        return {}
    from github_bridge import publish_reviewer_decision

    base = bridge_dir(config) / "reviewer_outbox"
    decision = read_json(base / "REVIEWER_DECISION.json") or validation.get("decision", {})
    next_task = read_text(base / "NEXT_CODEX_TASK.md", 30000)
    notes = read_text(base / "REVIEWER_NOTES.md", 12000)
    return publish_reviewer_decision(config, decision, next_task, notes=notes, validation=validation, round_index=round_index)


def publish_bridge_worker_status(config: dict[str, Any], status: dict[str, Any], round_index: int | None = None) -> dict[str, Any]:
    if bridge_mode(config) != "github_issue":
        return {}
    from github_bridge import publish_worker_status

    last_message = read_text(bridge_dir(config) / "codex_outbox" / "CODEX_LAST_MESSAGE.md", 12000)
    return publish_worker_status(config, status, last_message=last_message, round_index=round_index)


def publish_bridge_round_summary(config: dict[str, Any], summary: dict[str, Any], round_index: int | None = None) -> dict[str, Any]:
    if bridge_mode(config) != "github_issue":
        return {}
    from github_bridge import publish_round_summary

    return publish_round_summary(config, summary, round_index=round_index)


def publish_bridge_need_human(config: dict[str, Any], reason: str, violations: list[str], round_index: int | None = None) -> dict[str, Any]:
    if bridge_mode(config) != "github_issue":
        return {}
    from github_bridge import publish_need_human

    return publish_need_human(config, reason, violations=violations, round_index=round_index)


def find_latest_run(config: dict[str, Any]) -> Path | None:
    base = outputs_dir(config)
    runs = sorted([p for p in base.glob("run_????????_??????") if p.is_dir()], key=lambda p: p.name)
    return runs[-1] if runs else None


def run_cmd(cmd: list[str], cwd: Path, input_text: str | None = None, timeout: int | None = None) -> subprocess.CompletedProcess[str]:
    """Run a command and force UTF-8 stdin/stdout handling.

    Codex CLI validates stdin as UTF-8.  On Windows, ``text=True`` writes stdin
    using the active code page, so Chinese prompts can fail before auth/model
    execution starts.  Bytes mode keeps the prompt unambiguously UTF-8.
    """
    raw_input = input_text.encode("utf-8") if input_text is not None else None
    proc = subprocess.run(cmd, cwd=str(cwd), input=raw_input, capture_output=True, text=False, check=False, timeout=timeout)
    return subprocess.CompletedProcess(
        proc.args,
        proc.returncode,
        stdout=(proc.stdout or b"").decode("utf-8", errors="replace"),
        stderr=(proc.stderr or b"").decode("utf-8", errors="replace"),
    )


def codex_status(config: dict[str, Any]) -> dict[str, Any]:
    root = project_root(config)
    command = str(config.get("codex", {}).get("command", "codex"))
    version = run_cmd([command, "--version"], root)
    help_proc = run_cmd([command, "exec", "--help"], root)
    help_text = (help_proc.stdout or "") + (help_proc.stderr or "")
    return {
        "command": command,
        "version_returncode": version.returncode,
        "version_stdout": version.stdout.strip(),
        "version_stderr": version.stderr.strip(),
        "exec_help_returncode": help_proc.returncode,
        "exec_help_available": help_proc.returncode == 0,
        "supports_full_auto": "--full-auto" in help_text,
        "supports_sandbox": "--sandbox" in help_text,
        "supports_cd": "--cd" in help_text,
        "supports_skip_git_repo_check": "--skip-git-repo-check" in help_text,
        "supports_output_last_message": "--output-last-message" in help_text or "-o," in help_text,
        "help_excerpt": truncate_large_text(help_text, 4000),
    }


def call_publish_for_chatgpt(config: dict[str, Any], run_dir: Path | None = None) -> dict[str, Any]:
    root = project_root(config)
    cmd = [sys.executable, str(root / "scripts" / "us_stock_selection" / "99_publish_for_chatgpt.py")]
    if run_dir is not None:
        cmd.extend(["--run-dir", str(run_dir)])
    cmd.extend(["--bridge-dir", str(bridge_dir(config))])
    if bool(config.get("safety", {}).get("allow_git_push", False)):
        cmd.append("--git-push")
    proc = run_cmd(cmd, root, timeout=300)
    data: dict[str, Any] = {"returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}
    try:
        data["manifest"] = json.loads(proc.stdout)
    except Exception:
        data["manifest"] = {}
    return data


def summarize_review_files(config: dict[str, Any]) -> dict[str, Any]:
    base = bridge_dir(config)
    manifest_path = base / "latest_run_manifest.json"
    manifest = read_json(manifest_path)
    review_packet = Path(manifest.get("review_packet", "")) if manifest.get("review_packet") else base / "LATEST.md"
    selected_report = Path(manifest.get("selected_report", "")) if manifest.get("selected_report") else None
    final_verdict = Path(manifest.get("final_verdict", "")) if manifest.get("final_verdict") else None
    return {
        "latest_md": str(base / "LATEST.md"),
        "manifest_path": str(manifest_path),
        "manifest": manifest,
        "review_packet_path": str(review_packet),
        "review_packet_excerpt": read_text(review_packet, 12000),
        "selected_report_path": str(selected_report) if selected_report else "",
        "selected_report_excerpt": read_text(selected_report, 8000) if selected_report else "",
        "final_verdict_path": str(final_verdict) if final_verdict else "",
        "final_verdict": read_json(final_verdict) if final_verdict else {},
        "small_tables": summarize_small_tables(base, manifest),
    }


def summarize_small_tables(base: Path, manifest: dict[str, Any]) -> str:
    run_dir = Path(manifest.get("bridge_run_dir", "")) if manifest.get("bridge_run_dir") else None
    small_dir = run_dir / "small_tables" if run_dir else base / "runs"
    if not small_dir.exists():
        return ""
    parts = []
    for csv in sorted(small_dir.glob("*.csv")):
        parts.append(f"## {csv.name}\n\n{summarize_csv(csv)}")
    return "\n\n".join(parts)


def summarize_csv(path: Path, max_rows: int = 12) -> str:
    try:
        df = pd.read_csv(path)
    except Exception as exc:
        return f"CSV read failed: {exc}"
    if df.empty:
        return "_empty csv_"
    data = df.head(max_rows).copy()
    for col in data.columns:
        if pd.api.types.is_float_dtype(data[col]):
            data[col] = data[col].map(lambda x: "" if pd.isna(x) else f"{float(x):.6f}")
    return data.to_markdown(index=False)


def truncate_large_text(text: str, max_chars: int = 12000) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n\n...[truncated by agent_loop]..."


def read_text(path: Path | None, max_chars: int = 12000) -> str:
    if not path or not path.exists():
        return ""
    return truncate_large_text(path.read_text(encoding="utf-8", errors="replace"), max_chars)


def read_json(path: Path | None) -> dict[str, Any]:
    if not path or not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def write_json(path: Path, data: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def archive_round(config: dict[str, Any], round_index: int) -> Path:
    base = bridge_dir(config)
    target = base / "rounds" / f"round_{round_index:03d}"
    target.mkdir(parents=True, exist_ok=True)
    for rel in ["reviewer_inbox", "reviewer_outbox", "codex_inbox", "codex_outbox"]:
        src = base / rel
        if src.exists():
            dst = target / rel
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
    write_json(target / "round_archive.json", {"round": round_index, "archived_at": datetime.now().isoformat(timespec="seconds")})
    return target


def detect_safety_violation(config: dict[str, Any], text: str) -> list[str]:
    lowered = text.lower()
    violations = []
    if not config.get("safety", {}).get("allow_trade_execution", False) and any(
        _contains_action_phrase(lowered, k)
        for k in [
            "place order",
            "submit order",
            "send order",
            "real money",
            "live trading",
            "trade execution",
            "自动下单",
            "下单",
            "实盘",
            "真实交易",
            "真实账户",
        ]
    ):
        violations.append("trade_execution_requested")
    if not config.get("safety", {}).get("allow_broker_api", False) and any(
        _contains_action_phrase(lowered, k) for k in ["broker api", "connect to broker", "连接券商", "券商 api", "券商接口"]
    ):
        violations.append("trade_or_broker_api_requested")
    if not config.get("safety", {}).get("allow_expand_nasdaq100", False) and any(
        _contains_action_phrase(lowered, k)
        for k in ["expand nasdaq100", "nasdaq100 universe", "enter nasdaq100", "扩 nasdaq100", "扩展 nasdaq100", "进入 nasdaq100"]
    ):
        violations.append("nasdaq100_expansion_requested")
    if not config.get("safety", {}).get("allow_expand_sp500", False) and any(
        _contains_action_phrase(lowered, k) for k in ["expand s&p500", "expand sp500", "s&p500 universe", "sp500 universe", "扩 s&p500", "扩 sp500", "进入 s&p500", "进入 sp500"]
    ):
        violations.append("sp500_expansion_requested")
    if not config.get("safety", {}).get("allow_delete_outputs", False) and any(
        _contains_action_phrase(lowered, k) for k in ["delete outputs", "删除 outputs", "remove outputs", "recursive delete", "大范围删除"]
    ):
        violations.append("delete_outputs_requested")
    if any(_contains_action_phrase(lowered, k) for k in ["api key", "secret", "token", "credential", "密钥", "凭据"]):
        violations.append("credential_or_secret_requested")
    if not config.get("safety", {}).get("allow_git_push", False) and any(
        _contains_action_phrase(lowered, k) for k in ["git push", "automatic push", "auto push", "自动 push", "自动推送"]
    ):
        violations.append("automatic_git_push_requested")
    if any(_contains_action_phrase(lowered, k) for k in ["modify system config", "修改系统配置", "system configuration"]):
        violations.append("system_config_change_requested")
    return violations


def _contains_action_phrase(text: str, phrase: str) -> bool:
    start = 0
    phrase = phrase.lower()
    while True:
        idx = text.find(phrase, start)
        if idx < 0:
            return False
        window = text[max(0, idx - 80) : min(len(text), idx + len(phrase) + 80)]
        if not _is_negated_safety_context(window):
            return True
        start = idx + len(phrase)


def _is_negated_safety_context(window: str) -> bool:
    negations = [
        "do not",
        "don't",
        "dont",
        "never",
        "not ",
        "no ",
        "without",
        "禁止",
        "不允许",
        "不要",
        "不得",
        "不能",
        "不读取",
        "不使用",
        "不扩",
        "不扩展",
        "无需",
        "不要读取",
        "不要使用",
    ]
    return any(word in window for word in negations)
