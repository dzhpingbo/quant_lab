"""Daily multi-job automation runner for quant_lab.

The runner executes only configured research jobs. It records git state,
environment details, per-job logs, job summaries, a top-level summary, and a
zip of the daily run directory. It never trades, connects to brokers, commits,
pushes, deletes, restores, or cleans files.
"""

from __future__ import annotations

import argparse
import fnmatch
import glob
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

from daily_trading_packet import generate_trading_packets
from validate_daily_trading_packet import validate_run_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run daily quant_lab frozen research automation.")
    parser.add_argument("--config", default="scripts/automation/daily_quant_lab_config.yaml", help="YAML config path.")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without executing them.")
    parser.add_argument("--skip-update", action="store_true", help="Skip data/update commands.")
    parser.add_argument("--skip-strategy", action="store_true", help="Skip replay/strategy commands.")
    parser.add_argument("--date", default=datetime.now().date().isoformat(), help="Run date in YYYY-MM-DD format.")
    parser.add_argument("--max-runtime-minutes", type=float, default=None, help="Per-command timeout override.")
    parser.add_argument("--allow-dirty", action="store_true", help="Record dirty status and continue.")
    parser.add_argument("--job", action="append", default=[], help="Run only a configured job id. Can be repeated.")
    return parser.parse_args()


def load_yaml_config(path: Path) -> dict[str, Any]:
    try:
        import yaml
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(f"Cannot import PyYAML required for config loading: {exc}") from exc
    with path.open("r", encoding="utf-8") as fh:
        payload = yaml.safe_load(fh) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Config must be a mapping: {path}")
    return payload


def project_path(project_root: Path, value: str | Path | None) -> Path | None:
    if value is None:
        return None
    path = Path(str(value)).expanduser()
    return path if path.is_absolute() else project_root / path


def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def create_unique_run_dir(output_root: Path) -> Path:
    base = now_stamp()
    for index in range(100):
        name = base if index == 0 else f"{base}_{index:02d}"
        candidate = output_root / name
        try:
            candidate.mkdir(parents=True, exist_ok=False)
            return candidate
        except FileExistsError:
            continue
    raise FileExistsError(f"Could not create a unique run directory under {output_root} for timestamp {base}")


def jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): jsonable(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    return value


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(jsonable(payload), ensure_ascii=False, indent=2), encoding="utf-8")


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
    python_exe = str(config.get("python_executable", "python"))
    try:
        probe = subprocess.run([python_exe, "--version"], cwd=str(project_root), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
        configured_python_version = probe.stdout.strip()
    except Exception as exc:
        configured_python_version = f"ERROR: {exc}"
    payload = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "run_date": args.date,
        "project_root": str(project_root),
        "cwd": os.getcwd(),
        "runner_python_executable": sys.executable,
        "runner_python_version": sys.version,
        "configured_python_executable": python_exe,
        "configured_python_version": configured_python_version,
        "platform": platform.platform(),
        "machine": platform.node(),
        "dry_run": bool(args.dry_run),
        "selected_jobs": args.job,
    }
    (run_dir / "environment.txt").write_text("\n".join(f"{k}: {v}" for k, v in payload.items()) + "\n", encoding="utf-8")
    return payload


def quote_command_part(value: str) -> str:
    return subprocess.list2cmdline([value])


def render_part(value: Any, context: dict[str, str]) -> str:
    text = str(value)
    for key, replacement in context.items():
        text = text.replace("{" + key + "}", replacement)
    return text


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
    return subprocess.list2cmdline(command) if isinstance(command, list) else command


def timeout_for(config: dict[str, Any], step: str, job: dict[str, Any] | None, override: float | None) -> float:
    if override is not None:
        return max(1.0, override)
    if job and isinstance(job.get("timeout_minutes"), dict):
        return float(job["timeout_minutes"].get(step, job["timeout_minutes"].get("default", 60)))
    values = config.get("timeout_minutes", {}) or {}
    if isinstance(values, dict):
        return float(values.get(step, values.get("default", 60)))
    return float(values or 60)


def command_value(entry: Any) -> Any:
    if entry is None:
        return []
    if isinstance(entry, dict):
        return entry.get("command", [])
    return entry


def command_enabled(entry: Any) -> bool:
    if entry is None:
        return False
    if isinstance(entry, dict):
        return bool(entry.get("enabled", True))
    return True


def run_command(
    *,
    project_root: Path,
    job_dir: Path,
    config: dict[str, Any],
    args: argparse.Namespace,
    job: dict[str, Any],
    step: str,
    entry: Any,
    stdout_name: str,
    stderr_name: str,
    skip: bool,
) -> dict[str, Any]:
    stdout_path = job_dir / stdout_name
    stderr_path = job_dir / stderr_name
    context = {
        "project_root": str(project_root),
        "run_dir": str(job_dir.parent),
        "job_dir": str(job_dir),
        "run_date": args.date,
        "python_executable": str(config.get("python_executable", "python")),
    }
    enabled = command_enabled(entry) and not skip
    raw = command_value(entry)
    command = render_command(raw, context)
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
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    if not enabled:
        reason = "skipped by command line" if skip else "step disabled or not configured"
        stdout_path.write_text(f"SKIPPED {step}: {reason}\n", encoding="utf-8")
        stderr_path.write_text("", encoding="utf-8")
        return {**base, "status": "skipped", "returncode": 0, "finished_at": datetime.now().isoformat(timespec="seconds")}
    if not command:
        msg = f"FAILED {step}: enabled but command is empty.\n"
        stdout_path.write_text("", encoding="utf-8")
        stderr_path.write_text(msg, encoding="utf-8")
        return {**base, "status": "failed", "returncode": 2, "finished_at": datetime.now().isoformat(timespec="seconds"), "error": msg.strip()}
    if args.dry_run:
        stdout_path.write_text(f"DRY RUN {step}: {display}\n", encoding="utf-8")
        stderr_path.write_text("", encoding="utf-8")
        print(f"DRY RUN {job.get('id')} {step}: {display}")
        return {**base, "status": "dry_run", "returncode": 0, "finished_at": datetime.now().isoformat(timespec="seconds")}

    timeout_seconds = timeout_for(config, step, job, args.max_runtime_minutes) * 60.0
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


def normalize_jobs(config: dict[str, Any]) -> list[dict[str, Any]]:
    jobs = config.get("jobs")
    if isinstance(jobs, list) and jobs:
        return [dict(job) for job in jobs if isinstance(job, dict)]
    legacy = {
        "id": "us_v82",
        "enabled": True,
        "output_subdir": "job_us_v82",
        "data_command": config.get("data_update_command"),
        "strategy_command": config.get("strategy_run_command"),
        "metrics_extractor": "us_v82_formal_audit",
    }
    return [legacy]


def select_jobs(config: dict[str, Any], requested: list[str]) -> tuple[list[dict[str, Any]], list[str]]:
    jobs = normalize_jobs(config)
    known = {str(job.get("id")) for job in jobs}
    missing = [job_id for job_id in requested if job_id not in known]
    selected = []
    for job in jobs:
        job_id = str(job.get("id", ""))
        if requested and job_id not in requested:
            continue
        if not bool(job.get("enabled", True)):
            continue
        selected.append(job)
    return selected, missing


def preflight(project_root: Path, config_path: Path, config: dict[str, Any], jobs: list[dict[str, Any]], missing_jobs: list[str]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    checks.append({"check": "project_root_exists", "path": str(project_root), "pass": project_root.exists() and project_root.is_dir()})
    checks.append({"check": "config_readable", "path": str(config_path), "pass": config_path.exists() and config_path.is_file()})
    checks.append({"check": "requested_jobs_exist", "missing_jobs": missing_jobs, "pass": not missing_jobs})
    python_exe = str(config.get("python_executable", "python"))
    candidate = Path(python_exe).expanduser()
    if candidate.is_absolute():
        resolved = str(candidate)
        ok = candidate.exists() and candidate.is_file()
    else:
        resolved = shutil.which(python_exe) or ""
        ok = bool(resolved)
    checks.append({"check": "python_available", "python_executable": python_exe, "resolved": resolved, "pass": ok})

    project_root_text = str(project_root)
    if project_root_text not in sys.path:
        sys.path.insert(0, project_root_text)
    for module in config.get("dependency_imports", []) or []:
        try:
            importlib.import_module(str(module))
            checks.append({"check": "dependency_import", "module": str(module), "pass": True})
        except Exception as exc:
            checks.append({"check": "dependency_import", "module": str(module), "pass": False, "error": str(exc)})

    for job in jobs:
        for key in ("data_command", "strategy_command", "live_signal_command", "optional_report_command"):
            raw = command_value(job.get(key))
            parts = raw if isinstance(raw, list) else str(raw).split()
            for part in parts:
                if str(part).endswith(".py"):
                    script = project_path(project_root, str(part))
                    checks.append({"check": "job_script_exists", "job": job.get("id"), "path": str(script), "pass": bool(script and script.exists())})
    return {"checks": checks, "pass": all(bool(row.get("pass")) for row in checks)}


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


def collect_artifacts(project_root: Path, config: dict[str, Any], started_at: float, output_path: Path) -> dict[str, Any]:
    forbidden = list(config.get("forbidden_paths", []) or [])
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for pattern in config.get("artifact_globs", []) or []:
        pattern_text = str(pattern).replace("\\", "/")
        if "outputs/daily_quant_lab_runs" in pattern_text:
            candidates = output_path.parent.rglob("*")
        else:
            base_pattern = str(project_path(project_root, pattern) or pattern)
            candidates = (Path(raw) for raw in glob.glob(base_pattern, recursive=True))
        for path in candidates:
            if not path.is_file() or is_forbidden(path, project_root, forbidden):
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
            rows.append({"path": str(path), "size_bytes": stat.st_size, "mtime": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds")})
    rows.sort(key=lambda row: row["path"])
    payload = {"generated_or_touched_after_start": rows, "count": len(rows)}
    write_json(output_path, payload)
    return payload


def load_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def extract_us_v82_metrics(project_root: Path, started_at: float) -> dict[str, Any]:
    verdicts = sorted(
        (project_root / "outputs" / "us_stock_selection").glob("v82_frozen_formal_audit_*/v82_frozen_formal_audit_verdict.json"),
        key=lambda path: path.stat().st_mtime if path.exists() else 0,
        reverse=True,
    )
    for path in verdicts:
        try:
            if path.stat().st_mtime + 1e-6 < started_at:
                continue
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        keys = ["run_id", "classification", "gate_result", "strategy_id", "cagr", "calmar", "max_drawdown", "zip_path"]
        return {key: payload.get(key) for key in keys if key in payload}
    return {"message": "No us_v82 metrics extracted."}


def extract_job_metrics(project_root: Path, job: dict[str, Any], job_dir: Path, started_at: float) -> dict[str, Any]:
    extractor = str(job.get("metrics_extractor", ""))
    if extractor == "qldtqqq_frozen_daily":
        payload = load_json_if_exists(job_dir / "qldtqqq_job_summary.json")
        return {"results": payload.get("results", []), "status": payload.get("status"), "latest_data_date": payload.get("latest_data_date")}
    if extractor == "etf_588200_frozen_daily":
        payload = load_json_if_exists(job_dir / "588200_job_summary.json")
        return {"result": payload.get("result", {}), "status": payload.get("status")}
    if extractor == "us_v82_formal_audit":
        data_result = load_json_if_exists(job_dir / "refresh_v82_provider_safe.json")
        return {"data_update_result": data_result, "core_metrics": extract_us_v82_metrics(project_root, started_at)}
    return {"message": f"No extractor implemented for {extractor}."}


def job_status_from_steps(steps: dict[str, Any], dry_run: bool) -> str:
    if dry_run:
        return "DRY_RUN"
    failed = any(step.get("returncode", 0) != 0 for step in steps.values())
    if failed:
        return "FAILED"
    if steps and all(step.get("status") == "skipped" for step in steps.values()):
        return "SKIPPED"
    return "SUCCESS"


def write_job_summary(job_dir: Path, payload: dict[str, Any]) -> None:
    lines = [
        f"# {payload.get('status')} - {payload.get('job_id')}",
        "",
        f"- Job directory: `{payload.get('job_dir')}`",
        f"- Metrics extractor: `{payload.get('metrics_extractor')}`",
        f"- Data status: `{payload.get('steps', {}).get('data', {}).get('status', 'not_configured')}`",
        f"- Strategy status: `{payload.get('steps', {}).get('strategy', {}).get('status', 'not_configured')}`",
        f"- Live signal status: `{payload.get('steps', {}).get('live_signal', {}).get('status', 'not_configured')}`",
        f"- Trading packet status: `{payload.get('trading_packet_status', 'not_configured')}`",
        f"- Trading packet: `{payload.get('daily_trading_packet_path', '')}`",
        f"- Order ticket: `{payload.get('order_ticket_path', '')}`",
        "",
        "## Metrics",
        "",
        "```json",
        json.dumps(jsonable(payload.get("metrics", {})), indent=2, ensure_ascii=False),
        "```",
    ]
    (job_dir / "job_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    write_json(job_dir / "job_summary.json", payload)


def run_job(project_root: Path, run_dir: Path, config: dict[str, Any], args: argparse.Namespace, job: dict[str, Any]) -> dict[str, Any]:
    job_started_at = time.time()
    job_id = str(job.get("id"))
    job_dir = run_dir / str(job.get("output_subdir", f"job_{job_id}"))
    job_dir.mkdir(parents=True, exist_ok=True)
    steps: dict[str, Any] = {}

    data_entry = job.get("data_command")
    if data_entry is not None:
        steps["data"] = run_command(
            project_root=project_root,
            job_dir=job_dir,
            config=config,
            args=args,
            job=job,
            step="data",
            entry=data_entry,
            stdout_name="data_stdout.log",
            stderr_name="data_stderr.log",
            skip=bool(args.skip_update),
        )

    data_failed = steps.get("data", {}).get("returncode", 0) != 0
    strategy_entry = job.get("strategy_command")
    if strategy_entry is not None:
        steps["strategy"] = run_command(
            project_root=project_root,
            job_dir=job_dir,
            config=config,
            args=args,
            job=job,
            step="strategy",
            entry=strategy_entry,
            stdout_name="stdout.log",
            stderr_name="stderr.log",
            skip=bool(args.skip_strategy or data_failed),
        )

    live_signal_entry = job.get("live_signal_command")
    if live_signal_entry is not None and not args.skip_strategy and not data_failed and steps.get("strategy", {}).get("returncode", 0) == 0:
        steps["live_signal"] = run_command(
            project_root=project_root,
            job_dir=job_dir,
            config=config,
            args=args,
            job=job,
            step="live_signal",
            entry=live_signal_entry,
            stdout_name="live_signal_stdout.log",
            stderr_name="live_signal_stderr.log",
            skip=False,
        )
    optional_entry = job.get("optional_report_command")
    if optional_entry is not None and not args.skip_strategy and not data_failed and steps.get("strategy", {}).get("returncode", 0) == 0:
        steps["optional_report"] = run_command(
            project_root=project_root,
            job_dir=job_dir,
            config=config,
            args=args,
            job=job,
            step="optional_report",
            entry=optional_entry,
            stdout_name="optional_report_stdout.log",
            stderr_name="optional_report_stderr.log",
            skip=False,
        )

    status = job_status_from_steps(steps, args.dry_run)
    metrics = extract_job_metrics(project_root, job, job_dir, job_started_at) if not args.dry_run else {}
    artifacts = collect_artifacts(project_root, config, job_started_at, job_dir / "artifacts_manifest.json")
    payload = {
        "job_id": job_id,
        "status": status,
        "job_dir": str(job_dir),
        "enabled": True,
        "metrics_extractor": job.get("metrics_extractor", ""),
        "steps": steps,
        "metrics": metrics,
        "artifacts": artifacts,
    }
    write_job_summary(job_dir, payload)
    return payload


def zip_run_dir(run_dir: Path) -> Path:
    zip_path = run_dir / "run_result.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(run_dir.rglob("*")):
            if path.is_file() and path.resolve() != zip_path.resolve():
                archive.write(path, path.relative_to(run_dir))
    return zip_path


def write_summary(run_dir: Path, payload: dict[str, Any]) -> None:
    lines = [
        f"# {payload.get('status')} - Daily Quant Lab Multi-Job Run",
        "",
        f"- Run date: `{payload.get('run_date')}`",
        f"- Run directory: `{payload.get('run_dir')}`",
        f"- Dry run: `{payload.get('dry_run')}`",
        f"- Git dirty before: `{payload.get('git_before', {}).get('dirty')}`",
        f"- Git dirty after: `{payload.get('git_after', {}).get('dirty')}`",
        f"- Zip: `{payload.get('zip_path', '')}`",
        f"- Trading summary: `{payload.get('trading_packets', {}).get('daily_quant_trading_summary_path', '')}`",
        f"- All order tickets: `{payload.get('trading_packets', {}).get('all_order_tickets_path', '')}`",
        f"- Trading packet validation: `{payload.get('trading_packet_validation_status', '')}`",
        f"- Validation summary: `{payload.get('validation_summary_path', '')}`",
        "",
        "## Jobs",
        "",
        "| Job | Status | Data | Strategy | Live Signal | Trading Packet | Summary |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for job in payload.get("jobs", []):
        steps = job.get("steps", {})
        lines.append(
            f"| `{job.get('job_id')}` | `{job.get('status')}` | `{steps.get('data', {}).get('status', '')}` | `{steps.get('strategy', {}).get('status', '')}` | `{steps.get('live_signal', {}).get('status', '')}` | `{job.get('trading_packet_status', '')}` | `{Path(job.get('job_dir', '')) / 'job_summary.md'}` |"
        )
    lines.extend(["", "## Job Metrics", "", "```json", json.dumps(jsonable(payload.get("job_metrics", {})), indent=2, ensure_ascii=False), "```", "", "## Notes", ""])
    for note in payload.get("notes", []):
        lines.append(f"- {note}")
    (run_dir / "run_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    write_json(run_dir / "run_summary.json", payload)


def main() -> int:
    args = parse_args()
    started_at = time.time()
    config_path = Path(args.config).resolve()
    config = load_yaml_config(config_path)
    project_root = project_path(Path.cwd(), config.get("project_root")) or Path.cwd()
    project_root = project_root.resolve()
    output_root = project_path(project_root, config.get("output_root", "outputs/daily_quant_lab_runs"))
    assert output_root is not None
    run_dir = create_unique_run_dir(output_root)

    jobs, missing_jobs = select_jobs(config, args.job)
    notes = [
        "No commit, push, broker connection, live trading, strategy search, v10, or pool expansion is performed by this runner.",
        "QLD/TQQQ and 588200 jobs are fixed frozen replay jobs when enabled.",
    ]

    preflight_result = preflight(project_root, config_path, config, jobs, missing_jobs)
    write_json(run_dir / "preflight.json", preflight_result)
    env = write_environment(project_root, run_dir, config, args)
    git_before = snapshot_git(project_root, run_dir / "git_status_before.txt")
    if git_before.get("dirty"):
        notes.append("Working tree was dirty before the run; this is recorded and does not fail by default.")

    job_payloads: list[dict[str, Any]] = []
    if preflight_result.get("pass"):
        for job in jobs:
            job_payloads.append(run_job(project_root, run_dir, config, args, job))
    else:
        notes.append("Preflight failed; jobs were not executed.")

    trading_packets = generate_trading_packets(
        project_root=project_root,
        run_dir=run_dir,
        config=config,
        jobs=jobs,
        job_payloads=job_payloads,
        asof_date=args.date,
        dry_run=bool(args.dry_run),
    )
    if trading_packets.get("enabled"):
        notes.append("Trading packet layer generated human-review target holdings, order tickets, and risk status; no orders were sent.")
        for job_payload in job_payloads:
            write_job_summary(Path(job_payload["job_dir"]), job_payload)

    validation_result: dict[str, Any] = {}
    if trading_packets.get("enabled") and not args.dry_run and trading_packets.get("status") != "DISABLED":
        validation_result = validate_run_dir(run_dir, strict=True)
        notes.append(f"Trading packet validation status: {validation_result.get('validation_status')}.")

    git_after = snapshot_git(project_root, run_dir / "git_status_after.txt")
    artifacts = collect_artifacts(project_root, config, started_at, run_dir / "artifacts_manifest.json")

    if args.dry_run:
        overall_status = "DRY_RUN"
        success = bool(preflight_result.get("pass"))
    else:
        success = (
            bool(preflight_result.get("pass"))
            and all(job.get("status") in {"SUCCESS", "SKIPPED"} for job in job_payloads)
            and trading_packets.get("status", "PASS") != "FAILED"
            and validation_result.get("validation_status", "READY_FOR_MANUAL_REVIEW") != "FAILED"
        )
        overall_status = "SUCCESS" if success else "FAILED"
    payload = {
        "status": overall_status,
        "run_date": args.date,
        "run_dir": str(run_dir),
        "dry_run": bool(args.dry_run),
        "config_path": str(config_path),
        "project_root": str(project_root),
        "environment": env,
        "preflight": preflight_result,
        "git_before": git_before,
        "git_after": git_after,
        "jobs": job_payloads,
        "job_metrics": {job.get("job_id"): job.get("metrics", {}) for job in job_payloads},
        "trading_packets": trading_packets,
        "trading_packets_generated": bool(trading_packets.get("enabled")) and trading_packets.get("status") not in {"DISABLED", "DRY_RUN"},
        "all_target_holdings_path": trading_packets.get("all_target_holdings_path", ""),
        "all_order_tickets_path": trading_packets.get("all_order_tickets_path", ""),
        "daily_quant_trading_summary_path": trading_packets.get("daily_quant_trading_summary_path", ""),
        "trading_packet_validation_status": validation_result.get("validation_status", ""),
        "validation_summary_path": str(run_dir / "validation_summary.md") if validation_result else "",
        "formal_trade_allowed_count": validation_result.get("formal_trade_allowed_count", 0),
        "example_only_count": validation_result.get("example_only_count", 0),
        "blocked_order_count": validation_result.get("blocked_order_count", 0),
        "needs_position_file_count": validation_result.get("needs_position_file_count", 0),
        "needs_manual_price_count": validation_result.get("needs_manual_price_count", 0),
        "blocked_stale_signal_count": validation_result.get("blocked_stale_signal_count", 0),
        "blocking_warnings_count": validation_result.get("blocking_warnings_count", 0),
        "cross_sleeve_conflict_count": validation_result.get("cross_sleeve_conflict_count", 0),
        "duplicate_symbol_count": validation_result.get("duplicate_symbol_count", 0),
        "opposite_target_position_count": validation_result.get("opposite_target_position_count", 0),
        "opposite_trade_side_count": validation_result.get("opposite_trade_side_count", 0),
        "mixed_formal_blocked_count": validation_result.get("mixed_formal_blocked_count", 0),
        "requires_manual_sleeve_allocation": validation_result.get("requires_manual_sleeve_allocation", False),
        "duplicate_symbols": validation_result.get("duplicate_symbols", []),
        "artifacts": artifacts,
        "approved_strategy_note": config.get("approved_strategy_note", ""),
        "notes": notes,
    }
    write_summary(run_dir, payload)
    zip_path = zip_run_dir(run_dir)
    payload["zip_path"] = str(zip_path)
    write_summary(run_dir, payload)
    zip_run_dir(run_dir)
    console_payload = {
        "status": payload["status"],
        "run_dir": str(run_dir),
        "zip_path": str(zip_path),
        "daily_quant_trading_summary_path": trading_packets.get("daily_quant_trading_summary_path", ""),
        "all_order_tickets_path": trading_packets.get("all_order_tickets_path", ""),
        "order_summary": trading_packets.get("order_summary", {}),
        "blocking_warnings_count": trading_packets.get("order_summary", {}).get("blocking_warnings_count", 0),
        "validation_status": validation_result.get("validation_status", ""),
        "formal_trade_allowed_count": validation_result.get("formal_trade_allowed_count", 0),
        "example_only_count": validation_result.get("example_only_count", 0),
        "blocked_order_count": validation_result.get("blocked_order_count", 0),
        "needs_position_file_count": validation_result.get("needs_position_file_count", 0),
        "needs_manual_price_count": validation_result.get("needs_manual_price_count", 0),
        "blocked_stale_signal_count": validation_result.get("blocked_stale_signal_count", 0),
        "cross_sleeve_conflict_count": validation_result.get("cross_sleeve_conflict_count", 0),
        "duplicate_symbol_count": validation_result.get("duplicate_symbol_count", 0),
        "duplicate_symbols": validation_result.get("duplicate_symbols", []),
        "has_stale_signal": bool(validation_result.get("blocked_stale_signal_count", 0)),
        "has_adjusted_price_warning": bool(validation_result.get("adjusted_price_warning_count", 0)),
        "has_missing_current_positions": bool(validation_result.get("needs_position_file_count", 0)),
        "requires_manual_sleeve_allocation": bool(validation_result.get("requires_manual_sleeve_allocation", False)),
    }
    job_results = trading_packets.get("job_results", {}) if isinstance(trading_packets.get("job_results"), dict) else {}
    us_holdings = job_results.get("us_v82", {}).get("holdings", []) if isinstance(job_results.get("us_v82"), dict) else []
    qld_rows = job_results.get("qld_tqqq", {}).get("holdings", []) if isinstance(job_results.get("qld_tqqq"), dict) else []
    etf_rows = job_results.get("588200", {}).get("holdings", []) if isinstance(job_results.get("588200"), dict) else []
    console_payload["us_v82_top5"] = [row.get("ticker") for row in us_holdings[:5]]
    console_payload["qld_target"] = next(({"action": row.get("action"), "target_position": row.get("target_position")} for row in qld_rows if row.get("ticker") == "QLD"), {})
    console_payload["tqqq_target"] = next(({"action": row.get("action"), "target_position": row.get("target_position")} for row in qld_rows if row.get("ticker") == "TQQQ"), {})
    console_payload["588200_target"] = next(({"action": row.get("action"), "target_position": row.get("target_position")} for row in etf_rows), {})
    print(json.dumps(jsonable(console_payload), indent=2, ensure_ascii=False))
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
