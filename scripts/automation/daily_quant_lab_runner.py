"""Daily automation runner for quant_lab research runs.

The runner executes an approved data precheck or update command when configured,
runs the current approved frozen strategy command, records evidence, and packages
the run. It never trades, commits, pushes, deletes, restores, or cleans files.
"""

from __future__ import annotations

import argparse
import fnmatch
import importlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any


REQUIRED_LOGS = {
    "data_update": ("data_update_stdout.log", "data_update_stderr.log"),
    "strategy": ("strategy_stdout.log", "strategy_stderr.log"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the daily quant_lab data and frozen strategy automation.")
    parser.add_argument("--config", default="scripts/automation/daily_quant_lab_config.yaml", help="YAML config path.")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without executing them.")
    parser.add_argument("--skip-update", action="store_true", help="Skip the data update step.")
    parser.add_argument("--skip-strategy", action="store_true", help="Skip the strategy step.")
    parser.add_argument("--date", default=datetime.now().date().isoformat(), help="Run date in YYYY-MM-DD format.")
    parser.add_argument("--max-runtime-minutes", type=float, default=None, help="Per-command timeout override.")
    parser.add_argument("--allow-dirty", action="store_true", help="Record dirty status and continue. Dirty trees do not fail by default.")
    return parser.parse_args()


def load_yaml_config(path: Path) -> dict[str, Any]:
    try:
        import yaml
    except Exception as exc:  # pragma: no cover - depends on host env
        raise RuntimeError(f"Cannot import PyYAML required for config loading: {exc}") from exc
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Config must be a mapping: {path}")
    return data


def project_path(project_root: Path, value: str | Path | None) -> Path | None:
    if value is None:
        return None
    path = Path(str(value)).expanduser()
    if path.is_absolute():
        return path
    return project_root / path


def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    return value


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(jsonable(payload), indent=2, ensure_ascii=False), encoding="utf-8")


def append_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", errors="replace") as fh:
        fh.write(text)


def run_git(project_root: Path, args: list[str]) -> str:
    proc = subprocess.run(["git", *args], cwd=str(project_root), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    return proc.stdout


def snapshot_git(project_root: Path, path: Path) -> dict[str, Any]:
    branch = run_git(project_root, ["branch", "--show-current"]).strip()
    head = run_git(project_root, ["rev-parse", "HEAD"]).strip()
    origin_master = run_git(project_root, ["rev-parse", "origin/master"]).strip()
    ahead_behind = run_git(project_root, ["rev-list", "--left-right", "--count", "origin/master...HEAD"]).strip()
    status = run_git(project_root, ["status", "--short"])
    status_text = status if status else "(clean)\n"
    text = (
        f"branch: {branch}\n"
        f"HEAD: {head}\n"
        f"origin/master: {origin_master}\n"
        f"ahead_behind_origin_master_HEAD: {ahead_behind}\n\n"
        "git status --short:\n"
        f"{status_text}"
    )
    path.write_text(text, encoding="utf-8")
    return {
        "branch": branch,
        "head": head,
        "origin_master": origin_master,
        "ahead_behind": ahead_behind,
        "status_short": status,
        "dirty": bool(status.strip()),
    }


def write_environment(project_root: Path, run_dir: Path, config: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    py_exe = str(config.get("python_executable", "python"))
    try:
        py_probe = subprocess.run([py_exe, "--version"], cwd=str(project_root), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
        configured_python_version = py_probe.stdout.strip()
    except Exception as exc:
        configured_python_version = f"ERROR: {exc}"
    payload = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "run_date": args.date,
        "project_root": str(project_root),
        "cwd": os.getcwd(),
        "runner_python_executable": sys.executable,
        "runner_python_version": sys.version,
        "configured_python_executable": py_exe,
        "configured_python_version": configured_python_version,
        "platform": platform.platform(),
        "machine": platform.node(),
        "dry_run": bool(args.dry_run),
        "allow_dirty_flag": bool(args.allow_dirty),
    }
    lines = [f"{key}: {value}" for key, value in payload.items()]
    (run_dir / "environment.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return payload


def command_entry(config: dict[str, Any], key: str) -> dict[str, Any]:
    value = config.get(key)
    if value is None:
        return {"enabled": False, "command": [], "note": "not configured"}
    if isinstance(value, dict):
        return value
    return {"enabled": True, "command": value}


def is_enabled(config: dict[str, Any], step: str, command_key: str) -> bool:
    enabled_steps = config.get("enabled_steps", {}) or {}
    step_enabled = bool(enabled_steps.get(step, True))
    cmd_enabled = bool(command_entry(config, command_key).get("enabled", True))
    return step_enabled and cmd_enabled


def render_part(value: Any, context: dict[str, str]) -> str:
    text = str(value)
    for key, replacement in context.items():
        text = text.replace("{" + key + "}", replacement)
    return text


def quote_command_part(value: str) -> str:
    return subprocess.list2cmdline([value])


def normalize_python_command(command: str | list[str], context: dict[str, str]) -> str | list[str]:
    python_executable = context.get("python_executable", "python")
    if isinstance(command, list):
        if command and command[0].strip().lower() in {"python", "python.exe"}:
            return [python_executable, *command[1:]]
        return command

    prefix_len = len(command) - len(command.lstrip())
    prefix = command[:prefix_len]
    stripped = command[prefix_len:]
    lowered = stripped.lower()
    for token in ("python.exe", "python"):
        if lowered == token:
            return prefix + quote_command_part(python_executable)
        if lowered.startswith(token + " "):
            return prefix + quote_command_part(python_executable) + stripped[len(token):]
    return command


def render_command(raw: Any, context: dict[str, str]) -> str | list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return normalize_python_command([render_part(part, context) for part in raw], context)
    return normalize_python_command(render_part(raw, context), context)


def command_to_display(command: str | list[str]) -> str:
    if isinstance(command, list):
        return subprocess.list2cmdline(command)
    return command


def timeout_for(config: dict[str, Any], step: str, override: float | None) -> float:
    if override is not None:
        return max(1.0, override)
    values = config.get("timeout_minutes", {}) or {}
    if isinstance(values, dict):
        return float(values.get(step, values.get("default", 60)))
    return float(values or 60)


def run_configured_command(
    *,
    project_root: Path,
    run_dir: Path,
    config: dict[str, Any],
    args: argparse.Namespace,
    step: str,
    command_key: str,
    stdout_name: str,
    stderr_name: str,
) -> dict[str, Any]:
    entry = command_entry(config, command_key)
    stdout_path = run_dir / stdout_name
    stderr_path = run_dir / stderr_name
    context = {
        "project_root": str(project_root),
        "run_dir": str(run_dir),
        "run_date": args.date,
        "python_executable": str(config.get("python_executable", "python")),
    }
    enabled = is_enabled(config, step, command_key)
    if (step == "data_update" and args.skip_update) or (step == "strategy" and args.skip_strategy):
        enabled = False
        skip_reason = "skipped by command line"
    else:
        skip_reason = str(entry.get("note", "step disabled"))

    raw_command = entry.get("command", [])
    command = render_command(raw_command, context)
    display = command_to_display(command)
    base = {
        "step": step,
        "enabled": enabled,
        "dry_run": bool(args.dry_run),
        "command": display,
        "stdout_log": str(stdout_path),
        "stderr_log": str(stderr_path),
        "started_at": datetime.now().isoformat(timespec="seconds"),
    }

    if not enabled:
        msg = f"SKIPPED {step}: {skip_reason}\n"
        stdout_path.write_text(msg, encoding="utf-8")
        stderr_path.write_text("", encoding="utf-8")
        return {**base, "status": "skipped", "returncode": 0, "finished_at": datetime.now().isoformat(timespec="seconds")}

    if not command:
        msg = f"FAILED {step}: enabled but command is empty.\n"
        stdout_path.write_text("", encoding="utf-8")
        stderr_path.write_text(msg, encoding="utf-8")
        return {**base, "status": "failed", "returncode": 2, "finished_at": datetime.now().isoformat(timespec="seconds"), "error": msg.strip()}

    if args.dry_run:
        msg = f"DRY RUN {step}: {display}\n"
        stdout_path.write_text(msg, encoding="utf-8")
        stderr_path.write_text("", encoding="utf-8")
        print(msg.rstrip())
        return {**base, "status": "dry_run", "returncode": 0, "finished_at": datetime.now().isoformat(timespec="seconds")}

    timeout_seconds = timeout_for(config, step, args.max_runtime_minutes) * 60.0
    shell = isinstance(command, str)
    with stdout_path.open("w", encoding="utf-8", errors="replace") as stdout_fh, stderr_path.open("w", encoding="utf-8", errors="replace") as stderr_fh:
        stdout_fh.write(f"COMMAND: {display}\n\n")
        stdout_fh.flush()
        try:
            proc = subprocess.run(
                command,
                cwd=str(project_root),
                shell=shell,
                text=True,
                stdout=stdout_fh,
                stderr=stderr_fh,
                timeout=timeout_seconds,
                check=False,
            )
            status = "success" if proc.returncode == 0 else "failed"
            returncode = int(proc.returncode)
        except subprocess.TimeoutExpired as exc:
            stderr_fh.write(f"\nTIMEOUT after {timeout_seconds / 60.0:.2f} minutes: {exc}\n")
            status = "failed"
            returncode = 124
    return {**base, "status": status, "returncode": returncode, "finished_at": datetime.now().isoformat(timespec="seconds")}


def preflight(project_root: Path, config_path: Path, config: dict[str, Any]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    checks.append({"check": "project_root_exists", "path": str(project_root), "pass": project_root.exists() and project_root.is_dir()})
    checks.append({"check": "config_readable", "path": str(config_path), "pass": config_path.exists() and config_path.is_file()})
    python_exe = str(config.get("python_executable", "python"))
    python_candidate = Path(python_exe).expanduser()
    if python_candidate.is_absolute():
        python_path = str(python_candidate)
        python_pass = python_candidate.exists() and python_candidate.is_file()
    else:
        python_path = shutil.which(python_exe) or ""
        python_pass = bool(python_path)
    checks.append({"check": "python_available", "python_executable": python_exe, "resolved": python_path, "pass": python_pass})

    project_root_text = str(project_root)
    if project_root_text not in sys.path:
        sys.path.insert(0, project_root_text)

    for module in config.get("dependency_imports", []) or []:
        try:
            importlib.import_module(str(module))
            checks.append({"check": "dependency_import", "module": str(module), "pass": True})
        except Exception as exc:
            checks.append({"check": "dependency_import", "module": str(module), "pass": False, "error": str(exc)})

    strategy = command_entry(config, "strategy_run_command").get("command", [])
    if isinstance(strategy, list):
        scripts = [project_root / part for part in strategy if str(part).endswith(".py")]
        for script in scripts:
            checks.append({"check": "strategy_script_exists", "path": str(script), "pass": script.exists()})

    return {"checks": checks, "pass": all(bool(row.get("pass")) for row in checks)}


def summarize_path(path: Path, max_files: int = 200000) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "exists": False}
    if path.is_file():
        stat = path.stat()
        return {
            "path": str(path),
            "exists": True,
            "is_file": True,
            "file_count": 1,
            "total_bytes": stat.st_size,
            "newest_file": str(path),
            "newest_mtime": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        }
    file_count = 0
    total_bytes = 0
    newest_mtime = 0.0
    newest_file = ""
    truncated = False
    for root, _dirs, files in os.walk(path):
        for name in files:
            file_count += 1
            if file_count > max_files:
                truncated = True
                break
            fpath = Path(root) / name
            try:
                stat = fpath.stat()
            except OSError:
                continue
            total_bytes += stat.st_size
            if stat.st_mtime > newest_mtime:
                newest_mtime = stat.st_mtime
                newest_file = str(fpath)
        if truncated:
            break
    return {
        "path": str(path),
        "exists": True,
        "is_file": False,
        "file_count": file_count,
        "total_bytes": total_bytes,
        "newest_file": newest_file,
        "newest_mtime": datetime.fromtimestamp(newest_mtime).isoformat(timespec="seconds") if newest_mtime else "",
        "truncated": truncated,
    }


def run_data_sanity(project_root: Path, run_dir: Path, config: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    command_result: dict[str, Any] | None = None
    if is_enabled(config, "data_sanity", "data_sanity_command"):
        command_result = run_configured_command(
            project_root=project_root,
            run_dir=run_dir,
            config=config,
            args=args,
            step="data_sanity",
            command_key="data_sanity_command",
            stdout_name="data_sanity_stdout.log",
            stderr_name="data_sanity_stderr.log",
        )
    paths = [project_path(project_root, item) for item in (config.get("data_sanity_paths", []) or [])]
    summaries = [summarize_path(path) for path in paths if path is not None]
    payload = {"command_result": command_result, "directory_checks": summaries}
    write_json(run_dir / "data_sanity_summary.json", payload)
    return payload


def is_forbidden(path: Path, project_root: Path, forbidden_patterns: list[str]) -> bool:
    try:
        rel = path.resolve().relative_to(project_root.resolve()).as_posix()
    except Exception:
        rel = path.as_posix()
    rel_lower = rel.lower()
    for pattern in forbidden_patterns:
        pat = str(pattern).replace("\\", "/").rstrip("/").lower()
        if rel_lower == pat or rel_lower.startswith(pat + "/") or fnmatch.fnmatch(rel_lower, pat):
            return True
    return False


def collect_artifacts(project_root: Path, run_dir: Path, config: dict[str, Any], started_at: float) -> dict[str, Any]:
    forbidden = list(config.get("forbidden_paths", []) or [])
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for pattern in config.get("artifact_globs", []) or []:
        base_pattern = str(project_path(project_root, pattern) or pattern)
        for raw in glob_paths(base_pattern):
            path = Path(raw)
            if not path.is_file():
                continue
            if is_forbidden(path, project_root, forbidden):
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            if stat.st_mtime + 1e-6 < started_at:
                continue
            key = str(path.resolve()).lower()
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "path": str(path),
                    "size_bytes": stat.st_size,
                    "mtime": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
                }
            )
    rows.sort(key=lambda item: item["path"])
    payload = {"generated_or_touched_after_run_start": rows, "count": len(rows)}
    write_json(run_dir / "artifacts_manifest.json", payload)
    return payload


def glob_paths(pattern: str) -> list[str]:
    import glob

    return glob.glob(pattern, recursive=True)


def extract_core_metrics(project_root: Path, started_at: float) -> dict[str, Any]:
    verdicts = sorted(
        (project_root / "outputs" / "us_stock_selection").glob("v82_frozen_formal_audit_*/v82_frozen_formal_audit_verdict.json"),
        key=lambda p: p.stat().st_mtime if p.exists() else 0,
        reverse=True,
    )
    for path in verdicts:
        try:
            if path.stat().st_mtime + 1e-6 < started_at:
                continue
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        keys = [
            "run_id",
            "classification",
            "gate_result",
            "strategy_id",
            "cagr",
            "calmar",
            "max_drawdown",
            "cost50_cagr",
            "cost50_calmar",
            "formal_replay_completed",
            "score_provenance_gap",
            "zip_path",
        ]
        return {key: payload.get(key) for key in keys if key in payload}
    return {"message": "Core metrics were not automatically extracted."}


def zip_run_dir(run_dir: Path) -> Path:
    zip_path = run_dir / "run_result.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(run_dir.rglob("*")):
            if not path.is_file() or path.resolve() == zip_path.resolve():
                continue
            archive.write(path, path.relative_to(run_dir))
    return zip_path


def load_data_update_result(run_dir: Path) -> dict[str, Any]:
    for name in [
        "refresh_v82_provider_safe.json",
        "v82_provider_check_after_refresh.json",
        "v82_provider_check.json",
    ]:
        path = run_dir / name
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(payload, dict):
            return payload
    return {}


def write_summary(run_dir: Path, payload: dict[str, Any]) -> None:
    status = payload.get("status", "FAILED")
    data_description = str(payload.get("data_update_description", "") or "data update")
    data_result = payload.get("data_update_result", {}) if isinstance(payload.get("data_update_result"), dict) else {}
    data_download = data_result.get("data_download_performed", payload.get("data_download_performed"))
    replacement = data_result.get("replacement_performed", "")
    old_latest = data_result.get("old_latest_data_date", "")
    new_latest = data_result.get("new_latest_data_date", "")
    provider_check_status = data_result.get("provider_check_final_status", "")
    lines = [
        f"# {status} - Daily Quant Lab Run",
        "",
        f"- Run date: `{payload.get('run_date')}`",
        f"- Run directory: `{payload.get('run_dir')}`",
        f"- Dry run: `{payload.get('dry_run')}`",
        f"- Data precheck / update status: `{payload.get('steps', {}).get('data_update', {}).get('status')}`",
        f"- Data command description: `{data_description}`",
        f"- Data download performed: `{data_download}`",
        f"- Provider replaced/synced: `{replacement}`",
        f"- Old latest_data_date: `{old_latest}`",
        f"- New latest_data_date: `{new_latest}`",
        f"- Provider check final_status: `{provider_check_status}`",
        f"- Strategy status: `{payload.get('steps', {}).get('strategy', {}).get('status')}`",
        f"- Git dirty before: `{payload.get('git_before', {}).get('dirty')}`",
        f"- Git dirty after: `{payload.get('git_after', {}).get('dirty')}`",
        f"- Zip: `{payload.get('zip_path', '')}`",
        "",
        "## Approved Strategy",
        "",
        str(payload.get("approved_strategy_note", "")),
        "",
        "## Commands",
        "",
        f"- data_update_command: `{payload.get('steps', {}).get('data_update', {}).get('command', '')}`",
        f"- strategy_run_command: `{payload.get('steps', {}).get('strategy', {}).get('command', '')}`",
        "",
        "## Data Precheck",
        "",
        f"- Description: `{data_description}`",
        f"- Data refresh command executed: `{payload.get('steps', {}).get('data_update', {}).get('status') not in {'skipped', None}}`",
        f"- Data download performed: `{data_download}`",
        f"- Provider replaced/synced: `{replacement}`",
        f"- Old latest_data_date: `{old_latest}`",
        f"- New latest_data_date: `{new_latest}`",
        f"- Provider check final_status: `{provider_check_status}`",
        "",
        "## Core Metrics",
        "",
        "```json",
        json.dumps(payload.get("core_metrics", {}), indent=2, ensure_ascii=False),
        "```",
        "",
        "## Notes",
        "",
    ]
    for note in payload.get("notes", []):
        lines.append(f"- {note}")
    (run_dir / "run_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    write_json(run_dir / "run_summary.json", payload)


def main() -> int:
    args = parse_args()
    started_at = time.time()
    config_path = Path(args.config).resolve()
    config = load_yaml_config(config_path)
    data_entry = command_entry(config, "data_update_command")
    data_description = str(data_entry.get("description") or data_entry.get("note") or "")
    data_download_performed = bool(data_entry.get("data_download_performed", True)) if data_entry.get("enabled", True) else False
    project_root = project_path(Path.cwd(), config.get("project_root")) or Path.cwd()
    project_root = project_root.resolve()
    output_root = project_path(project_root, config.get("output_root", "outputs/daily_quant_lab_runs"))
    assert output_root is not None
    run_dir = output_root / now_stamp()
    run_dir.mkdir(parents=True, exist_ok=False)

    for stdout_name, stderr_name in REQUIRED_LOGS.values():
        (run_dir / stdout_name).write_text("", encoding="utf-8")
        (run_dir / stderr_name).write_text("", encoding="utf-8")

    notes: list[str] = []
    if data_entry.get("enabled") is False:
        notes.append("No explicit approved daily data update command was found; data update is disabled in config.")
    elif data_download_performed is False:
        notes.append("Data precheck / freshness check executed when not skipped.")
        notes.append("No data download was performed by the configured data precheck command.")
    else:
        notes.append("Data refresh command executed when not skipped; refresh report records whether download and provider sync occurred.")
    notes.append("No commit, push, broker connection, or trading action is performed by this runner.")

    steps: dict[str, Any] = {}
    preflight_result = preflight(project_root, config_path, config)
    write_json(run_dir / "preflight.json", preflight_result)
    env = write_environment(project_root, run_dir, config, args)
    git_before = snapshot_git(project_root, run_dir / "git_status_before.txt")
    if git_before.get("dirty"):
        notes.append("Working tree was dirty before the run; this is recorded and does not fail by default.")

    success = bool(preflight_result["pass"])
    if not success:
        notes.append("Preflight failed; core commands were not executed.")

    if success:
        steps["data_update"] = run_configured_command(
            project_root=project_root,
            run_dir=run_dir,
            config=config,
            args=args,
            step="data_update",
            command_key="data_update_command",
            stdout_name="data_update_stdout.log",
            stderr_name="data_update_stderr.log",
        )
        if steps["data_update"].get("returncode", 0) != 0:
            success = False

    data_sanity = run_data_sanity(project_root, run_dir, config, args)

    if success:
        steps["strategy"] = run_configured_command(
            project_root=project_root,
            run_dir=run_dir,
            config=config,
            args=args,
            step="strategy",
            command_key="strategy_run_command",
            stdout_name="strategy_stdout.log",
            stderr_name="strategy_stderr.log",
        )
        if steps["strategy"].get("returncode", 0) != 0:
            success = False
    else:
        steps["strategy"] = {
            "step": "strategy",
            "status": "skipped",
            "returncode": 0,
            "command": command_to_display(render_command(command_entry(config, "strategy_run_command").get("command", []), {
                "project_root": str(project_root),
                "run_dir": str(run_dir),
                "run_date": args.date,
                "python_executable": str(config.get("python_executable", "python")),
            })),
        }
        append_text(run_dir / "strategy_stdout.log", "SKIPPED strategy because an earlier core step failed.\n")

    if success and is_enabled(config, "optional_report", "optional_report_command"):
        steps["optional_report"] = run_configured_command(
            project_root=project_root,
            run_dir=run_dir,
            config=config,
            args=args,
            step="optional_report",
            command_key="optional_report_command",
            stdout_name="optional_report_stdout.log",
            stderr_name="optional_report_stderr.log",
        )
        if steps["optional_report"].get("returncode", 0) != 0:
            success = False

    git_after = snapshot_git(project_root, run_dir / "git_status_after.txt")
    artifacts = collect_artifacts(project_root, run_dir, config, started_at)
    core_metrics = extract_core_metrics(project_root, started_at)
    data_update_result = load_data_update_result(run_dir)

    payload = {
        "status": "SUCCESS" if success else "FAILED",
        "run_date": args.date,
        "run_dir": str(run_dir),
        "dry_run": bool(args.dry_run),
        "config_path": str(config_path),
        "project_root": str(project_root),
        "environment": env,
        "preflight": preflight_result,
        "git_before": git_before,
        "git_after": git_after,
        "steps": steps,
        "data_sanity": data_sanity,
        "artifacts": artifacts,
        "core_metrics": core_metrics,
        "approved_strategy_note": config.get("approved_strategy_note", ""),
        "data_update_description": data_description,
        "data_download_performed": data_download_performed,
        "data_update_result": data_update_result,
        "notes": notes,
    }
    write_summary(run_dir, payload)
    zip_path = zip_run_dir(run_dir)
    payload["zip_path"] = str(zip_path)
    write_summary(run_dir, payload)
    zip_run_dir(run_dir)
    print(json.dumps({"status": payload["status"], "run_dir": str(run_dir), "zip_path": str(zip_path)}, indent=2))
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
