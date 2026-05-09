"""Check the frozen v8.2 Qlib provider before the daily strategy run.

This script is intentionally read-only. It checks provider freshness and
coverage for the current approved frozen v8.2 mainline, but it does not
download data, rebuild providers, train models, search strategies, trade,
connect brokers, commit, or push.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shlex
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROVIDER_DIR = Path(r"C:\Users\Administrator\.qlib\qlib_data\us_data_local_2026_v91_growth")
DEFAULT_V8_1_RUN_DIR = PROJECT_ROOT / "outputs" / "us_stock_selection" / "run_20260502_210856"
DEFAULT_SCORE_AUDIT = DEFAULT_V8_1_RUN_DIR / "v8_1_model_switch" / "Alpha360_LGBModel" / "score_rank_audit_trail.csv"
PRIMARY_STRATEGY_ID = "top5_ytdcap80p_derisk100p"
BENCHMARK_TICKERS = {"SPY", "QQQ", "QLD", "TQQQ", "SHY"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only v8.2 frozen provider freshness and coverage check.")
    parser.add_argument("--provider-dir", default=str(DEFAULT_PROVIDER_DIR), help="Qlib provider directory to check.")
    parser.add_argument("--strategy-command", default="", help="Frozen strategy command; used only to locate known v8.2 inputs.")
    parser.add_argument("--strategy-config", default="", help="Optional JSON/YAML config with required_tickers or score_rank_audit.")
    parser.add_argument("--max-stale-days", type=int, default=7, help="Maximum allowed age for latest provider data date.")
    parser.add_argument("--dry-run", action="store_true", help="Run checks and report results without modifying anything.")
    parser.add_argument("--json-out", default="", help="Optional JSON output path.")
    parser.add_argument("--md-out", default="", help="Optional Markdown output path.")
    return parser.parse_args()


def iso_from_timestamp(ts: float | None) -> str:
    if not ts:
        return ""
    return datetime.fromtimestamp(ts).isoformat(timespec="seconds")


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except Exception:
        return str(path)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def load_structured_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"strategy config not found: {path}")
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        data = json.loads(text)
    else:
        try:
            import yaml
        except Exception as exc:
            raise RuntimeError(f"PyYAML is required for YAML strategy config: {exc}") from exc
        data = yaml.safe_load(text) or {}
    if not isinstance(data, dict):
        raise ValueError(f"strategy config must be a mapping: {path}")
    return data


def path_from_config(value: Any) -> Path:
    path = Path(str(value)).expanduser()
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def command_option_value(command: str, option: str) -> str:
    if not command:
        return ""
    try:
        tokens = shlex.split(command, posix=False)
    except ValueError:
        tokens = command.split()
    cleaned = [token.strip().strip('"').strip("'") for token in tokens]
    for index, token in enumerate(cleaned):
        if token == option and index + 1 < len(cleaned):
            return cleaned[index + 1]
        if token.startswith(option + "="):
            return token.split("=", 1)[1]
    return ""


def score_audit_from_inputs(strategy_command: str, strategy_config: str) -> tuple[Path | None, str, list[str]]:
    warnings: list[str] = []
    if strategy_config:
        cfg_path = path_from_config(strategy_config)
        try:
            cfg = load_structured_config(cfg_path)
        except Exception as exc:
            return None, f"strategy_config:{rel(cfg_path)}", [f"Could not read strategy config: {exc}"]
        for key in ("required_tickers", "tickers"):
            values = cfg.get(key)
            if isinstance(values, list) and values:
                return None, f"strategy_config:{rel(cfg_path)}:{key}", []
        score_path = cfg.get("score_rank_audit") or cfg.get("score_rank_audit_trail")
        if score_path:
            return path_from_config(score_path), f"strategy_config:{rel(cfg_path)}", []
        v8_1_run = cfg.get("v8_1_run_dir")
        if v8_1_run:
            return path_from_config(v8_1_run) / "v8_1_model_switch" / "Alpha360_LGBModel" / "score_rank_audit_trail.csv", f"strategy_config:{rel(cfg_path)}:v8_1_run_dir", []
        warnings.append(f"Strategy config did not expose required_tickers, score_rank_audit, or v8_1_run_dir: {rel(cfg_path)}")

    v8_1_from_command = command_option_value(strategy_command, "--v8-1-run-dir")
    if v8_1_from_command:
        return path_from_config(v8_1_from_command) / "v8_1_model_switch" / "Alpha360_LGBModel" / "score_rank_audit_trail.csv", "strategy_command:--v8-1-run-dir", warnings

    if strategy_command and "51_run_v82_frozen_formal_audit.py" not in strategy_command.replace("\\", "/"):
        warnings.append("Strategy command was provided but is not the known v8.2 frozen formal audit entrypoint; using default frozen score audit path.")

    return DEFAULT_SCORE_AUDIT, "default_v8_1_score_rank_audit_trail", warnings


def load_required_tickers(strategy_command: str, strategy_config: str) -> dict[str, Any]:
    warnings: list[str] = []
    explicit_tickers: list[str] = []
    if strategy_config:
        cfg_path = path_from_config(strategy_config)
        if cfg_path.exists():
            try:
                cfg = load_structured_config(cfg_path)
                for key in ("required_tickers", "tickers"):
                    values = cfg.get(key)
                    if isinstance(values, list) and values:
                        explicit_tickers = sorted({str(item).upper() for item in values if str(item).strip()})
                        return {
                            "strategy_id": cfg.get("strategy_id", PRIMARY_STRATEGY_ID),
                            "source": f"strategy_config:{rel(cfg_path)}:{key}",
                            "score_audit_path": "",
                            "tickers": explicit_tickers,
                            "warnings": warnings,
                        }
            except Exception as exc:
                warnings.append(f"Could not parse explicit tickers from strategy config: {exc}")

    score_path, source, source_warnings = score_audit_from_inputs(strategy_command, strategy_config)
    warnings.extend(source_warnings)
    if score_path is None:
        warnings.append("Could not locate a stable score_rank_audit source for required ticker coverage.")
        return {
            "strategy_id": PRIMARY_STRATEGY_ID,
            "source": source,
            "score_audit_path": "",
            "tickers": [],
            "warnings": warnings,
        }
    if not score_path.exists():
        warnings.append(f"Score rank audit file not found: {score_path}")
        return {
            "strategy_id": PRIMARY_STRATEGY_ID,
            "source": source,
            "score_audit_path": str(score_path),
            "tickers": [],
            "warnings": warnings,
        }
    tickers: set[str] = set()
    try:
        with score_path.open("r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            field_map = {str(name).lower(): name for name in (reader.fieldnames or [])}
            ticker_col = field_map.get("ticker")
            if not ticker_col:
                warnings.append(f"Score rank audit has no ticker column: {score_path}")
            else:
                for row in reader:
                    ticker = str(row.get(ticker_col, "")).strip().upper()
                    if ticker:
                        tickers.add(ticker)
    except Exception as exc:
        warnings.append(f"Could not read score rank audit tickers: {exc}")

    if tickers:
        tickers.update(BENCHMARK_TICKERS)
    else:
        warnings.append("Required ticker list is empty after reading score rank audit.")
    return {
        "strategy_id": PRIMARY_STRATEGY_ID,
        "source": source,
        "score_audit_path": str(score_path),
        "tickers": sorted(tickers),
        "warnings": warnings,
    }


def summarize_provider(provider: Path) -> dict[str, Any]:
    file_count = 0
    total_bytes = 0
    latest_mtime = 0.0
    latest_file = ""
    if provider.exists():
        for root, _dirs, files in os.walk(provider):
            for name in files:
                path = Path(root) / name
                try:
                    stat = path.stat()
                except OSError:
                    continue
                file_count += 1
                total_bytes += stat.st_size
                if stat.st_mtime > latest_mtime:
                    latest_mtime = stat.st_mtime
                    latest_file = str(path)
    return {
        "file_count": file_count,
        "total_size_mb": round(total_bytes / (1024 * 1024), 3),
        "latest_mtime": iso_from_timestamp(latest_mtime),
        "latest_mtime_file": latest_file,
    }


def read_latest_calendar_date(provider: Path) -> tuple[str, str]:
    calendar_path = provider / "calendars" / "day.txt"
    if not calendar_path.exists():
        return "", "missing calendars/day.txt"
    try:
        lines = [line.strip() for line in calendar_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except Exception as exc:
        return "", f"could not read calendars/day.txt: {exc}"
    for raw in reversed(lines):
        token = raw.replace(",", " ").split()[0]
        try:
            return date.fromisoformat(token).isoformat(), "calendars/day.txt"
        except ValueError:
            continue
    return "", "could not parse calendars/day.txt"


def list_feature_tickers(provider: Path) -> dict[str, Any]:
    features = provider / "features"
    close_files: dict[str, Path] = {}
    volume_files: dict[str, Path] = {}
    if features.exists():
        for child in features.iterdir():
            if not child.is_dir():
                continue
            ticker = child.name.upper()
            close_path = child / "close.day.bin"
            volume_path = child / "volume.day.bin"
            if close_path.exists():
                close_files[ticker] = close_path
            if volume_path.exists():
                volume_files[ticker] = volume_path
    return {
        "features_dir_exists": features.exists(),
        "close_file_count": len(close_files),
        "volume_file_count": len(volume_files),
        "close_tickers": sorted(close_files),
        "volume_tickers": sorted(volume_files),
    }


def build_markdown(payload: dict[str, Any]) -> str:
    coverage = payload.get("required_ticker_coverage", {})
    stale = payload.get("stale_check_result", {})
    lines = [
        f"# v8.2 Provider Check - {payload.get('final_status')}",
        "",
        f"- Generated at: `{payload.get('generated_at')}`",
        f"- Provider: `{payload.get('provider_dir')}`",
        f"- Mode: `check_only_no_data_download`",
        f"- Dry run: `{payload.get('dry_run')}`",
        f"- Data download performed: `False`",
        f"- Provider exists: `{payload.get('provider_exists')}`",
        f"- Close/volume files exist: `{payload.get('close_volume_exists')}`",
        f"- File count: `{payload.get('file_count')}`",
        f"- Total size MB: `{payload.get('total_size_mb')}`",
        f"- Latest mtime: `{payload.get('latest_mtime')}`",
        f"- Latest data date: `{payload.get('latest_data_date')}`",
        f"- Stale check: `{stale.get('status')}` ({stale.get('detail', '')})",
        f"- Required ticker coverage: `{coverage.get('status')}` ({coverage.get('covered_count')}/{coverage.get('required_count')})",
        "",
        "## Warnings",
        "",
    ]
    warnings = payload.get("warnings", [])
    lines.extend([f"- {item}" for item in warnings] or ["- none"])
    lines.extend(["", "## Errors", ""])
    errors = payload.get("errors", [])
    lines.extend([f"- {item}" for item in errors] or ["- none"])
    missing_close = coverage.get("missing_close", [])
    missing_volume = coverage.get("missing_volume", [])
    if missing_close or missing_volume:
        lines.extend(
            [
                "",
                "## Missing Required Files",
                "",
                f"- Missing close: `{', '.join(missing_close) if missing_close else 'none'}`",
                f"- Missing volume: `{', '.join(missing_volume) if missing_volume else 'none'}`",
            ]
        )
    return "\n".join(lines) + "\n"


def run_check(args: argparse.Namespace) -> dict[str, Any]:
    provider = Path(args.provider_dir).expanduser()
    warnings: list[str] = []
    errors: list[str] = []

    provider_exists = provider.exists() and provider.is_dir()
    if not provider_exists:
        errors.append(f"Provider directory does not exist: {provider}")

    summary = summarize_provider(provider)
    features = list_feature_tickers(provider)
    close_volume_exists = bool(features["close_file_count"] and features["volume_file_count"])
    if provider_exists and not features["features_dir_exists"]:
        errors.append(f"Provider features directory is missing: {provider / 'features'}")
    if provider_exists and not close_volume_exists:
        errors.append("Provider has no close.day.bin or no volume.day.bin files.")

    latest_data_date, latest_data_source = read_latest_calendar_date(provider)
    today = date.today()
    stale_check: dict[str, Any] = {
        "max_stale_days": args.max_stale_days,
        "latest_data_date": latest_data_date,
        "latest_data_source": latest_data_source,
        "today": today.isoformat(),
        "status": "UNKNOWN",
        "detail": "",
    }
    if latest_data_date:
        data_age_days = (today - date.fromisoformat(latest_data_date)).days
        stale_check["latest_data_age_days"] = data_age_days
        if data_age_days < 0:
            warnings.append(f"Provider latest_data_date is in the future: {latest_data_date}")
            stale_check.update({"status": "WARN", "detail": "latest_data_date is in the future"})
        elif data_age_days > args.max_stale_days:
            errors.append(
                f"Provider latest_data_date {latest_data_date} is {data_age_days} days old, above max_stale_days={args.max_stale_days}."
            )
            stale_check.update({"status": "FAIL", "detail": "latest_data_date is stale"})
        else:
            stale_check.update({"status": "PASS", "detail": "latest_data_date is within threshold"})
    else:
        warnings.append(f"Could not parse latest provider data date: {latest_data_source}")
        stale_check.update({"status": "WARN", "detail": latest_data_source})

    if summary["latest_mtime"]:
        latest_mtime_date = datetime.fromisoformat(summary["latest_mtime"]).date()
        mtime_age_days = (today - latest_mtime_date).days
        stale_check["latest_mtime_age_days"] = mtime_age_days
        if mtime_age_days > args.max_stale_days and not latest_data_date:
            errors.append(
                f"Provider latest_mtime {summary['latest_mtime']} is {mtime_age_days} days old and latest_data_date is unavailable."
            )
    elif provider_exists:
        errors.append("Provider exists but no files were found.")

    required = load_required_tickers(args.strategy_command, args.strategy_config)
    warnings.extend(required.get("warnings", []))
    required_tickers = set(required.get("tickers", []))
    close_tickers = set(features["close_tickers"])
    volume_tickers = set(features["volume_tickers"])
    missing_close = sorted(required_tickers - close_tickers)
    missing_volume = sorted(required_tickers - volume_tickers)
    if required_tickers:
        if missing_close:
            errors.append(f"Missing close.day.bin for required tickers: {', '.join(missing_close)}")
        if missing_volume:
            errors.append(f"Missing volume.day.bin for required tickers: {', '.join(missing_volume)}")
        coverage_status = "PASS" if not missing_close and not missing_volume else "FAIL"
    else:
        coverage_status = "UNKNOWN"
        warnings.append("Required ticker coverage could not be checked because no stable required ticker list was parsed.")

    if errors:
        final_status = "FAIL"
    elif warnings:
        final_status = "WARN"
    else:
        final_status = "PASS"

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "script": rel(Path(__file__)),
        "dry_run": bool(args.dry_run),
        "provider_dir": str(provider),
        "provider_exists": provider_exists,
        "close_volume_exists": close_volume_exists,
        "file_count": summary["file_count"],
        "total_size_mb": summary["total_size_mb"],
        "latest_mtime": summary["latest_mtime"],
        "latest_mtime_file": summary["latest_mtime_file"],
        "latest_data_date": latest_data_date,
        "latest_data_date_source": latest_data_source,
        "stale_check_result": stale_check,
        "feature_file_counts": {
            "close_file_count": features["close_file_count"],
            "volume_file_count": features["volume_file_count"],
        },
        "required_ticker_coverage": {
            "strategy_id": required.get("strategy_id", PRIMARY_STRATEGY_ID),
            "source": required.get("source", ""),
            "score_audit_path": required.get("score_audit_path", ""),
            "required_count": len(required_tickers),
            "covered_count": len(required_tickers - set(missing_close) - set(missing_volume)) if required_tickers else 0,
            "missing_close": missing_close,
            "missing_volume": missing_volume,
            "status": coverage_status,
        },
        "warnings": warnings,
        "errors": errors,
        "final_status": final_status,
        "data_download_performed": False,
        "provider_modified": False,
        "forbidden_actions": [
            "no v10",
            "no pool expansion",
            "no strategy search",
            "no MVE2/P6 promotion",
            "no broker connection",
            "no trading",
            "no commit or push",
        ],
    }


def main() -> int:
    args = parse_args()
    payload = run_check(args)
    if args.json_out:
        write_json(Path(args.json_out), payload)
    if args.md_out:
        md_path = Path(args.md_out)
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(build_markdown(payload), encoding="utf-8")

    print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
    return 0 if payload["final_status"] in {"PASS", "WARN"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
