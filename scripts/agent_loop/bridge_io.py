"""Shared IO helpers for the Codex-auth local agent loop."""

from __future__ import annotations

import json
import os
import re
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
    return str(read_bridge_current_task_info(config).get("text", ""))


def read_bridge_current_task_info(config: dict[str, Any]) -> dict[str, Any]:
    if bridge_mode(config) == "github_issue":
        from github_bridge import read_current_task_info

        return read_current_task_info(config)
    task_path = bridge_dir(config) / "reviewer_inbox" / "CURRENT_TASK.md"
    return {
        "text": read_text(task_path, 12000),
        "source": f"local_file:{task_path}",
        "source_kind": "local_file",
    }


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


def publish_bridge_need_human(config: dict[str, Any], reason: str, violations: list[Any], round_index: int | None = None) -> dict[str, Any]:
    if bridge_mode(config) != "github_issue":
        return {}
    from github_bridge import publish_need_human

    return publish_need_human(config, reason, violations=violations, round_index=round_index)


def find_latest_run(config: dict[str, Any]) -> Path | None:
    base = outputs_dir(config)
    patterns = [
        "run_????????_??????",
        "formal_v9_????????_??????",
        "v82_canonical_rebuild_????????_??????",
        "score_provenance_alignment_audit_????????_??????",
        "v82_v9_replay_diff_audit_????????_??????",
        "v9_reverse_audit_????????_??????",
    ]
    runs = []
    for pattern in patterns:
        runs.extend([p for p in base.glob(pattern) if p.is_dir()])
    runs = sorted(set(runs), key=lambda p: p.stat().st_mtime if p.exists() else 0)
    return runs[-1] if runs else None


_WINDOWS_CODEX_FALLBACK_PATHS: list[str] = [
    # Standalone installer (Windows) — most common if NOT installed via npm
    os.path.join(os.path.expanduser("~"), ".codex", ".sandbox-bin", "codex.exe"),
    # VS Code ChatGPT extension bundled binary
    os.path.join(
        os.environ.get("USERPROFILE", ""),
        ".vscode", "extensions",
    ),
    # npm global
    os.path.join(os.environ.get("APPDATA", ""), "npm", "codex.cmd"),
    os.path.join(os.environ.get("APPDATA", ""), "npm", "codex"),
    # pnpm global
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "pnpm", "codex.cmd"),
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "pnpm", "codex"),
    # system-wide nodejs
    r"C:\Program Files\nodejs\codex.cmd",
    r"C:\Program Files\nodejs\codex",
    # volta
    os.path.join(os.environ.get("VOLTA_HOME", ""), "bin", "codex.exe"),
]


def resolve_executable(command: str) -> str:
    """Resolve a command to an absolute executable path.

    Resolution order:
    1. If ``command`` is already an absolute path and exists → use as-is.
    2. ``shutil.which(command)`` on the current PATH.
    3. On Windows, if the bare command name is ``codex`` (or ``codex.cmd``),
       probe a list of well-known npm / pnpm / volta / fnm install locations.
    4. If still unresolved, raise ``FileNotFoundError`` with a diagnostic
       message listing the current PATH and suggested fix actions.

    This function never reads or prints credentials / tokens.
    """
    # Case 1: absolute path already given
    p = Path(command)
    if p.is_absolute():
        if p.exists():
            return str(p)
        raise FileNotFoundError(
            f"[resolve_executable] Codex CLI not found at configured path:\n"
            f"  command = {command!r}\n"
            f"Please update loop_config_auth.yaml → codex.command to the correct absolute path."
        )

    # Case 2: shutil.which on PATH
    found = shutil.which(command)
    if found:
        return found

    # Case 3: Windows fallback probe for bare "codex" / "codex.cmd"
    bare = Path(command).stem.lower()  # strips .cmd / .exe suffix if any
    if sys.platform.startswith("win") and bare == "codex":
        for candidate in _WINDOWS_CODEX_FALLBACK_PATHS:
            if candidate and Path(candidate).exists():
                return candidate

    # Case 4: not found anywhere — raise with diagnostic
    path_dirs = os.environ.get("PATH", "")
    npm_prefix_hint = ""
    npm_exe = shutil.which("npm")
    if npm_exe:
        try:
            result = subprocess.run(
                [npm_exe, "config", "get", "prefix"],
                capture_output=True, text=True, timeout=10,
            )
            npm_prefix = result.stdout.strip()
            npm_prefix_hint = (
                f"\n  npm prefix = {npm_prefix!r}"
                f"\n  Expected codex.cmd at: {os.path.join(npm_prefix, 'codex.cmd')}"
            )
        except Exception:
            pass

    raise FileNotFoundError(
        f"[resolve_executable] Codex CLI executable not found.\n"
        f"  command configured = {command!r}\n"
        f"  shutil.which result = None\n"
        f"{npm_prefix_hint}"
        f"\nDiagnosis steps:\n"
        f"  1. Run in PowerShell:  where.exe codex\n"
        f"  2. Run:                npm config get prefix\n"
        f"  3. Check if codex.cmd exists in that prefix directory.\n"
        f"  4. If not installed, run:  npm install -g @openai/codex\n"
        f"  5. After finding the path, update loop_config_auth.yaml:\n"
        f"       codex:\n"
        f"         command: \"C:/Users/<you>/AppData/Roaming/npm/codex.cmd\"\n"
        f"\nCurrent PATH entries:\n"
        + "\n".join(f"  {d}" for d in path_dirs.split(os.pathsep)[:20])
    )


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
    raw_command = str(config.get("codex", {}).get("command", "codex"))
    # Resolve to absolute path; raises FileNotFoundError with diagnostics if not found.
    command = resolve_executable(raw_command)
    # Write resolved path back into config so reviewer / worker see the same value.
    if "codex" not in config or not isinstance(config.get("codex"), dict):
        config["codex"] = {}
    config["codex"]["command"] = command
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
        "supports_bypass_approvals_and_sandbox": "--dangerously-bypass-approvals-and-sandbox" in help_text,
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
    target = next_round_archive_path(base / "rounds", round_index)
    target.mkdir(parents=True, exist_ok=True)
    for rel in ["reviewer_inbox", "reviewer_outbox", "codex_inbox", "codex_outbox"]:
        src = base / rel
        if src.exists():
            dst = target / rel
            shutil.copytree(src, dst)
    write_json(target / "round_archive.json", {"round": round_index, "archived_at": datetime.now().isoformat(timespec="seconds")})
    return target


def next_round_archive_path(rounds_dir: Path, round_index: int) -> Path:
    base = rounds_dir / f"round_{round_index:03d}"
    if not base.exists():
        return base
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    candidate = rounds_dir / f"round_{round_index:03d}_{timestamp}"
    counter = 2
    while candidate.exists():
        candidate = rounds_dir / f"round_{round_index:03d}_{timestamp}_{counter}"
        counter += 1
    return candidate


def detect_safety_violation(config: dict[str, Any], text: str) -> list[str]:
    """Return unique safety violation ids for compatibility with older callers."""
    return safety_violation_ids(detect_safety_violation_details(config, text))


def safety_violation_ids(details: list[dict[str, Any]]) -> list[str]:
    seen: set[str] = set()
    ids: list[str] = []
    for item in details:
        violation = str(item.get("violation", ""))
        if violation and violation not in seen:
            seen.add(violation)
            ids.append(violation)
    return ids


def detect_safety_violation_details(config: dict[str, Any], text: str) -> list[dict[str, Any]]:
    """Detect only real hard-block actions and return debuggable snippets.

    The safety gate has three layers:
    1. Match explicit high-risk action phrases such as placing orders, broker
       connections, and reading/using credentials.
    2. Ignore matches that are clearly negated, policy text, classification
       rules, or "no broker / no API key" style safety instructions.
    3. Allow offline audit/replay/backtest tasks when no real hard-block action
       remains after layer 2.
    """
    if not text:
        return []
    rules = _safety_rules(config)
    details: list[dict[str, Any]] = []
    for rule in rules:
        if not rule["enabled"]:
            continue
        for pattern, label in rule["patterns"]:
            for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                if _match_is_policy_or_negated(text, match.start(), match.end()):
                    continue
                details.append(
                    {
                        "violation": rule["violation"],
                        "phrase": label,
                        "matched_text": match.group(0),
                        "start": match.start(),
                        "end": match.end(),
                        "context": _context_window(text, match.start(), match.end()),
                        "line": _line_context(text, match.start(), match.end()),
                    }
                )
    return details


def _safety_rules(config: dict[str, Any]) -> list[dict[str, Any]]:
    safety = config.get("safety", {}) or {}
    return [
        {
            "violation": "trade_or_broker_api_requested",
            "enabled": not safety.get("allow_broker_api", False),
            "patterns": [
                (r"\bconnect\s+to\s+broker\b", "connect to broker"),
                (r"\buse\s+broker\s+api\b", "use broker API"),
                (r"\bbroker\s+api\b", "broker API"),
                (r"\bconnect\s+exchange\b", "connect exchange"),
                (r"连接券商", "连接券商"),
                (r"券商\s*(?:api|接口)", "券商接口"),
            ],
        },
        {
            "violation": "trade_execution_requested",
            "enabled": not safety.get("allow_trade_execution", False),
            "patterns": [
                (r"\bplace\s+order\b", "place order"),
                (r"\bsubmit\s+order\b", "submit order"),
                (r"\bsend\s+order\b", "send order"),
                (r"\bmarket\s+order\b", "market order"),
                (r"\blimit\s+order\b", "limit order"),
                (r"\bcancel\s+order\b", "cancel order"),
                (r"\blive\s+trading\b", "live trading"),
                (r"\breal\s+money\b", "real money"),
                (r"\bproduction\s+trading\b", "production trading"),
                (r"\bauto\s+execute\s+trades\b", "auto execute trades"),
                (r"\buse\s+real\s+account\b", "use real account"),
                (r"实盘交易", "实盘交易"),
                (r"自动下单", "自动下单"),
                (r"提交订单", "提交订单"),
                (r"真实账户", "真实账户"),
                (r"(?<!不)(?<!不要)(?<!不得)(?<!禁止)(?<!不能)下单", "下单"),
            ],
        },
        {
            "violation": "credential_or_secret_requested",
            "enabled": True,
            "patterns": [
                (r"\bread\s+api\s+key\b", "read API key"),
                (r"\bload\s+api\s+key\b", "load API key"),
                (r"\buse\s+api\s+key\b", "use API key"),
                (r"\bread\s+secret\b", "read secret"),
                (r"\bload\s+secret\b", "load secret"),
                (r"\buse\s+secret(?:\s+token)?\b", "use secret"),
                (r"\bread\s+token\b", "read token"),
                (r"\bload\s+token\b", "load token"),
                (r"\buse\s+token\b", "use token"),
                (r"\bread\s+credential\b", "read credential"),
                (r"\bload\s+credential\b", "load credential"),
                (r"\buse\s+credential\b", "use credential"),
                (r"读取密钥", "读取密钥"),
                (r"使用密钥", "使用密钥"),
                (r"读取凭证", "读取凭证"),
                (r"使用凭证", "使用凭证"),
                (r"读取\s*(?:api\s*key|secret|token|credential)", "读取 credential"),
                (r"使用\s*(?:api\s*key|secret|token|credential)", "使用 credential"),
            ],
        },
        {
            "violation": "nasdaq100_expansion_requested",
            "enabled": not safety.get("allow_expand_nasdaq100", False),
            "patterns": [
                (r"\bexpand\s+nasdaq100\b", "expand Nasdaq100"),
                (r"\bnasdaq100\s+universe\b", "Nasdaq100 universe"),
                (r"\benter\s+nasdaq100\b", "enter Nasdaq100"),
                (r"扩展?\s*nasdaq100", "扩 Nasdaq100"),
                (r"进入\s*nasdaq100", "进入 Nasdaq100"),
            ],
        },
        {
            "violation": "sp500_expansion_requested",
            "enabled": not safety.get("allow_expand_sp500", False),
            "patterns": [
                (r"\bexpand\s+s&p500\b", "expand S&P500"),
                (r"\bexpand\s+sp500\b", "expand SP500"),
                (r"\bs&p500\s+universe\b", "S&P500 universe"),
                (r"\bsp500\s+universe\b", "SP500 universe"),
                (r"扩展?\s*(?:s&p500|sp500)", "扩 S&P500"),
                (r"进入\s*(?:s&p500|sp500)", "进入 S&P500"),
            ],
        },
        {
            "violation": "delete_outputs_requested",
            "enabled": not safety.get("allow_delete_outputs", False),
            "patterns": [
                (r"\bdelete\s+outputs\b", "delete outputs"),
                (r"\bremove\s+outputs\b", "remove outputs"),
                (r"\brecursive\s+delete\b", "recursive delete"),
                (r"删除\s*outputs", "删除 outputs"),
                (r"大范围删除", "大范围删除"),
            ],
        },
        {
            "violation": "automatic_git_push_requested",
            "enabled": not safety.get("allow_git_push", False),
            "patterns": [
                (r"\bgit\s+push\b", "git push"),
                (r"\bautomatic\s+push\b", "automatic push"),
                (r"\bauto\s+push\b", "auto push"),
                (r"自动\s*push", "自动 push"),
                (r"自动推送", "自动推送"),
            ],
        },
        {
            "violation": "system_config_change_requested",
            "enabled": True,
            "patterns": [
                (r"\bmodify\s+system\s+config(?:uration)?\b", "modify system config"),
                (r"修改系统配置", "修改系统配置"),
            ],
        },
        {
            "violation": "external_network_download_requested",
            "enabled": not safety.get("allow_external_network_download", False),
            "patterns": [
                (r"\bdownload\s+(?:market\s+)?data\b", "download market data"),
                (r"联网下载行情", "联网下载行情"),
            ],
        },
    ]


def _contains_action_phrase(text: str, phrase: str) -> bool:
    pattern = re.escape(phrase)
    for match in re.finditer(pattern, text, flags=re.IGNORECASE):
        if not _match_is_policy_or_negated(text, match.start(), match.end()):
            return True
    return False


def _match_is_policy_or_negated(text: str, start: int, end: int) -> bool:
    prefix = text[max(0, start - 80) : start]
    context = _context_window(text, start, end, radius=180)
    line = _line_context(text, start, end)
    paragraph = _paragraph_context(text, start, end)
    lowered_context = f"{context}\n{line}\n{paragraph}".lower()
    if _is_negated_safety_context(prefix):
        return True
    allow_markers = [
        "不要下单",
        "不得下单",
        "不能下单",
        "不允许下单",
        "禁止下单",
        "不要连接券商",
        "不得连接券商",
        "禁止连接券商",
        "不要实盘",
        "不得实盘",
        "禁止实盘",
        "不要使用 api key",
        "不得使用 api key",
        "禁止使用 api key",
        "不读取 api key",
        "不使用 api key",
        "不读取 secret",
        "不使用 secret",
        "不读取 token",
        "不使用 token",
        "不读取 credential",
        "不使用 credential",
        "hard block 测试",
        "hard block test",
        "blocked_by_safety_gate 分类规则",
        "blocked_by_safety_gate",
        "分类规则",
        "禁止事项",
        "safety gate 规则说明",
        "仅限离线研究",
        "只读取本地项目",
        "local-only",
        "offline research",
        "no broker",
        "no order",
        "no live trading",
        "no api key",
        "no secret",
        "no token",
        "no credential",
        "审计是否存在",
        "使用风险",
        "交易风险",
        "风险",
    ]
    return any(marker in lowered_context for marker in allow_markers)


def _is_negated_safety_context(window: str) -> bool:
    lowered = window.lower()
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
        "只审计",
        "仅审计",
        "审计是否",
        "检查是否",
    ]
    return any(word in lowered for word in negations)


def _context_window(text: str, start: int, end: int, radius: int = 120) -> str:
    left = max(0, start - radius)
    right = min(len(text), end + radius)
    return text[left:right].replace("\r", "").replace("\n", "\\n")


def _line_context(text: str, start: int, end: int) -> str:
    left = text.rfind("\n", 0, start) + 1
    right = text.find("\n", end)
    if right < 0:
        right = len(text)
    return text[left:right].strip()


def _paragraph_context(text: str, start: int, end: int) -> str:
    left = text.rfind("\n\n", 0, start)
    left = 0 if left < 0 else left + 2
    right = text.find("\n\n", end)
    if right < 0:
        right = len(text)
    return text[left:right].strip()
