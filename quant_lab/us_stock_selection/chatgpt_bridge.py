"""Publish compact us_stock_selection review packets for ChatGPT.

The bridge copies only review-safe artifacts into ``docs/chatgpt_bridge``:
markdown summaries, compact CSV excerpts/summaries, and verdict JSON.  It does
not copy zip archives, parquet files, model artifacts, or raw market data.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from quant_lab.us_stock_selection.utils import PROJECT_ROOT, ensure_dir, save_dataframe, save_json, save_text


DEFAULT_OUTPUT_BASE = PROJECT_ROOT / "outputs" / "us_stock_selection"
DEFAULT_BRIDGE_DIR = PROJECT_ROOT / "docs" / "chatgpt_bridge"
FORBIDDEN_SUFFIXES = {".zip", ".parquet", ".pkl", ".joblib", ".bin", ".h5", ".feather"}
TABLE_ALIASES = {
    "benchmark": ["benchmark"],
    "attribution": ["ticker_contribution", "attribution", "contribution"],
    "stress_test": ["stress", "execution"],
    "yearly_return": ["yearly_return", "annual_return"],
    "holdings_summary": ["monthly_holdings", "holdings"],
}


@dataclass
class ReviewArtifacts:
    run_dir: Path
    run_id: str
    zip_path: Path | None
    run_summary_path: Path | None
    report_path: Path | None
    next_steps_path: Path | None
    verdict_path: Path | None
    xlsx_paths: list[Path]
    csv_paths: list[Path]
    code_files_from_zip: list[str]


def find_latest_run(base_dir: Path | str = DEFAULT_OUTPUT_BASE) -> Path:
    base = Path(base_dir)
    runs = sorted([p for p in base.glob("run_????????_??????") if p.is_dir()], key=lambda p: p.name)
    if not runs:
        raise FileNotFoundError(f"No run_YYYYMMDD_HHMMSS directories found under {base}")
    return runs[-1]


def collect_review_artifacts(run_dir: Path | str) -> ReviewArtifacts:
    run = Path(run_dir).resolve()
    run_id = run.name
    timestamp = run_id.replace("run_", "")
    zip_candidates = sorted(run.parent.glob(f"*{timestamp}.zip"), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    run_summary = first_existing([run / "RUN_SUMMARY.md", PROJECT_ROOT / "RUN_SUMMARY.md"])
    reports = sorted((run / "reports").glob("*.md"), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True) if (run / "reports").exists() else []
    xlsx_paths = sorted((run / "reports").glob("*.xlsx"), key=lambda p: p.name) if (run / "reports").exists() else []
    verdicts = sorted(
        [p for p in run.rglob("*.json") if any(key in p.name.lower() for key in ["verdict", "decision"])],
        key=lambda p: p.stat().st_mtime if p.exists() else 0,
        reverse=True,
    )
    csv_paths = sorted([p for p in run.rglob("*.csv") if p.is_file() and not any(part.startswith(".") for part in p.parts)], key=lambda p: p.name)
    code_files = list_code_files_from_zip(zip_candidates[0]) if zip_candidates else []
    return ReviewArtifacts(
        run_dir=run,
        run_id=run_id,
        zip_path=zip_candidates[0] if zip_candidates else None,
        run_summary_path=run_summary,
        report_path=reports[0] if reports else None,
        next_steps_path=PROJECT_ROOT / "NEXT_STEPS.md" if (PROJECT_ROOT / "NEXT_STEPS.md").exists() else None,
        verdict_path=verdicts[0] if verdicts else None,
        xlsx_paths=xlsx_paths,
        csv_paths=csv_paths,
        code_files_from_zip=code_files,
    )


def build_review_packet(run_dir: Path | str, bridge_run_dir: Path | str | None = None, max_csv_mb: float = 5.0) -> tuple[str, ReviewArtifacts, dict[str, Any]]:
    artifacts = collect_review_artifacts(run_dir)
    key_metrics = extract_key_metrics(artifacts)
    verdict = read_json_safe(artifacts.verdict_path)
    run_summary_text = read_text_excerpt(artifacts.run_summary_path, max_chars=8000)
    report_excerpt = read_text_excerpt(artifacts.report_path, max_chars=12000)
    next_steps_text = read_text_excerpt(artifacts.next_steps_path, max_chars=5000)
    table_index = summarize_csv_inventory(artifacts.csv_paths, max_csv_mb=max_csv_mb)
    packet = f"""# ChatGPT Review Packet

## Run

- run_id: `{artifacts.run_id}`
- run_dir: `{artifacts.run_dir}`
- zip_path: `{artifacts.zip_path or ""}`
- published_at: `{datetime.now().isoformat(timespec="seconds")}`

## 本轮目标

{extract_goal(run_summary_text, report_excerpt)}

## 新增/修改文件

{format_list(artifacts.code_files_from_zip, empty="未能从 zip 自动识别代码文件；请查看本地 git diff 或 run zip。")}

## 核心结果 / RUN_SUMMARY

{run_summary_text or "_RUN_SUMMARY.md not found._"}

## 核心指标

{dataframe_markdown(key_metrics, max_rows=20)}

## Gate / Verdict

```json
{json.dumps(verdict, ensure_ascii=False, indent=2) if verdict else "{}"}
```

## 当前分类

- classification: `{verdict.get("classification", "") if isinstance(verdict, dict) else ""}`
- allow_enter_v9: `{verdict.get("allow_enter_v9", "") if isinstance(verdict, dict) else ""}`
- allow_enter_v10: `{verdict.get("allow_enter_v10", "") if isinstance(verdict, dict) else ""}`

## 不通过原因 / 已知限制

{extract_limitations(run_summary_text, report_excerpt, verdict)}

## 需要 ChatGPT 审阅的问题

1. 当前 classification 是否与 gate 证据一致？
2. 是否存在未来函数、样本选择偏差、执行口径或数据质量问题？
3. 是否应批准进入下一阶段，还是要求补验证？
4. 如果进入下一阶段，边界条件是否足够明确？

## Codex 建议的下一步

{next_steps_text or "_NEXT_STEPS.md not found._"}

## 关键表格摘要

{dataframe_markdown(table_index, max_rows=30)}

## 重要 CSV 文件路径

{format_list([relative(p) for p in artifacts.csv_paths[:80]], empty="No CSV files found.")}

## selected_report.md excerpt

{report_excerpt or "_No report markdown found under run reports._"}
"""
    manifest_bits = {
        "key_metrics_rows": int(len(key_metrics)),
        "csv_inventory_rows": int(len(table_index)),
    }
    return packet, artifacts, manifest_bits


def export_small_tables(run_dir: Path | str, bridge_run_dir: Path | str, max_csv_mb: float = 5.0, include_xlsx: bool = False) -> dict[str, Any]:
    artifacts = collect_review_artifacts(run_dir)
    bridge = ensure_dir(bridge_run_dir)
    small_dir = ensure_dir(bridge / "small_tables")
    exported: dict[str, Any] = {"small_tables": {}, "skipped": [], "xlsx": []}

    if artifacts.run_summary_path:
        copy_text_file(artifacts.run_summary_path, bridge / "RUN_SUMMARY.md")
    if artifacts.report_path:
        copy_text_file(artifacts.report_path, bridge / "selected_report.md")
    if artifacts.next_steps_path:
        copy_text_file(artifacts.next_steps_path, bridge / "next_steps.md")
    if artifacts.verdict_path:
        save_json(read_json_safe(artifacts.verdict_path), bridge / "final_verdict.json")

    key_metrics = extract_key_metrics(artifacts)
    save_dataframe(key_metrics, bridge / "key_metrics.csv")
    exported["key_metrics"] = str(relative(bridge / "key_metrics.csv"))

    for alias, patterns in TABLE_ALIASES.items():
        source = choose_csv(artifacts.csv_paths, patterns)
        target = small_dir / f"{alias}.csv"
        if source is None:
            save_dataframe(pd.DataFrame([{"status": "not_found", "patterns": ",".join(patterns)}]), target)
            exported["small_tables"][alias] = {"source": "", "target": str(relative(target)), "mode": "not_found"}
            continue
        mode = export_csv_safely(source, target, alias=alias, max_csv_mb=max_csv_mb)
        exported["small_tables"][alias] = {"source": str(relative(source)), "target": str(relative(target)), "mode": mode}

    if include_xlsx:
        for path in artifacts.xlsx_paths:
            exported["xlsx"].append(str(relative(path)))
    else:
        exported["xlsx"] = [f"{relative(p)} (not copied; include_xlsx=false)" for p in artifacts.xlsx_paths]
    return exported


def write_latest_pointer(bridge_run_dir: Path | str, manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    bridge_run = Path(bridge_run_dir).resolve()
    bridge_dir = bridge_run.parents[1] if bridge_run.parent.name == "runs" else bridge_run.parent
    latest_md = bridge_dir / "LATEST.md"
    manifest_path = bridge_dir / "latest_run_manifest.json"
    review_packet = bridge_run / "REVIEW_PACKET.md"
    data = dict(manifest or {})
    data.update(
        {
            "bridge_run_dir": str(bridge_run),
            "bridge_run_dir_repo_relative": relative(bridge_run),
            "review_packet": str(review_packet),
            "review_packet_repo_relative": relative(review_packet),
            "latest_md": str(latest_md),
            "latest_md_repo_relative": relative(latest_md),
            "manifest_path": str(manifest_path),
            "manifest_path_repo_relative": relative(manifest_path),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
    )
    text = f"""# ChatGPT Bridge Latest

Latest bridge run: `{bridge_run.name}`

Primary review file:

`{relative(review_packet)}`

Manifest:

`{relative(manifest_path)}`

Fixed prompt for ChatGPT:

> 请审阅 GitHub quant_lab 仓库 `docs/chatgpt_bridge/LATEST.md` 指向的最新 run，重点检查 REVIEW_PACKET.md、final_verdict.json 和 small_tables 下的关键 CSV 摘要。
"""
    save_text(text, latest_md)
    save_json(data, manifest_path)
    return data


def optional_git_commit_push(run_id: str, bridge_dir: Path | str = DEFAULT_BRIDGE_DIR, git_push: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {
        "git_push_requested": bool(git_push),
        "is_git_repo": False,
        "has_remote": False,
        "commit_attempted": False,
        "commit_success": False,
        "push_attempted": False,
        "push_success": False,
        "message": "",
        "stdout": "",
        "stderr": "",
    }
    repo = run_cmd(["git", "rev-parse", "--show-toplevel"])
    if repo.returncode != 0:
        result["message"] = "Not a git repository; bridge generated locally only."
        result["stderr"] = repo.stderr
        return result
    result["is_git_repo"] = True
    remotes = run_cmd(["git", "remote", "-v"])
    result["has_remote"] = bool(remotes.stdout.strip())
    if not git_push:
        result["message"] = "Git push not requested."
        return result
    if not result["has_remote"]:
        result["message"] = "No git remote configured; skipped commit/push."
        return result

    add = run_cmd(["git", "add", str(Path(bridge_dir)), "NEXT_STEPS.md", "RUN_SUMMARY.md"])
    commit = run_cmd(["git", "commit", "-m", f"Update ChatGPT bridge for {run_id}"])
    result["commit_attempted"] = True
    result["stdout"] += add.stdout + commit.stdout
    result["stderr"] += add.stderr + commit.stderr
    result["commit_success"] = commit.returncode == 0
    if commit.returncode != 0 and "nothing to commit" not in (commit.stdout + commit.stderr).lower():
        result["message"] = "git commit failed; skipped push."
        return result
    push = run_cmd(["git", "push"])
    result["push_attempted"] = True
    result["push_success"] = push.returncode == 0
    result["stdout"] += push.stdout
    result["stderr"] += push.stderr
    result["message"] = "git push completed." if push.returncode == 0 else "git push failed; local bridge is still available."
    return result


def publish_for_chatgpt(
    run_dir: Path | str | None = None,
    bridge_dir: Path | str = DEFAULT_BRIDGE_DIR,
    max_csv_mb: float = 5.0,
    include_xlsx: bool = False,
    git_push: bool = False,
) -> dict[str, Any]:
    run = Path(run_dir).resolve() if run_dir else find_latest_run(DEFAULT_OUTPUT_BASE)
    artifacts = collect_review_artifacts(run)
    bridge_base = ensure_dir(bridge_dir)
    bridge_run = ensure_dir(bridge_base / "runs" / artifacts.run_id)
    packet, artifacts, bits = build_review_packet(run, bridge_run, max_csv_mb=max_csv_mb)
    save_text(packet, bridge_run / "REVIEW_PACKET.md")
    exported = export_small_tables(run, bridge_run, max_csv_mb=max_csv_mb, include_xlsx=include_xlsx)
    manifest = {
        "run_id": artifacts.run_id,
        "run_dir": str(artifacts.run_dir),
        "zip_path": str(artifacts.zip_path or ""),
        "run_summary": str(bridge_run / "RUN_SUMMARY.md"),
        "selected_report": str(bridge_run / "selected_report.md"),
        "final_verdict": str(bridge_run / "final_verdict.json"),
        "next_steps": str(bridge_run / "next_steps.md"),
        "max_csv_mb": float(max_csv_mb),
        "include_xlsx": bool(include_xlsx),
        "exported": exported,
        **bits,
    }
    manifest = write_latest_pointer(bridge_run, manifest)
    git_result = optional_git_commit_push(artifacts.run_id, bridge_dir=bridge_base, git_push=git_push)
    manifest["git"] = git_result
    save_json(manifest, bridge_base / "latest_run_manifest.json")
    save_json(manifest, bridge_run / "manifest.json")
    save_text(json.dumps(git_result, ensure_ascii=False, indent=2), bridge_run / "publish_git_status.json")
    return manifest


def extract_key_metrics(artifacts: ReviewArtifacts) -> pd.DataFrame:
    preferred = [
        "growth_pool_results",
        "year_stability_results",
        "model_switch_summary",
        "strategy_results",
        "paper_trading_metrics",
        "metrics",
    ]
    for needle in preferred:
        candidates = [p for p in artifacts.csv_paths if needle in p.name.lower()]
        if candidates:
            return compact_metric_frame(read_csv_safe(candidates[0]))
    # Fall back to the first small CSV with familiar metric columns.
    for path in artifacts.csv_paths:
        df = read_csv_safe(path, nrows=200)
        if any(col in df.columns for col in ["cagr", "calmar", "max_drawdown", "classification"]):
            return compact_metric_frame(df)
    return pd.DataFrame()


def compact_metric_frame(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    priority = [
        "strategy_id",
        "universe_name",
        "model_branch",
        "classification",
        "allow_enter_v9",
        "allow_enter_v10",
        "v9_gate_pass",
        "cagr",
        "paper_cagr",
        "cost50_t1_cagr",
        "max_drawdown",
        "calmar",
        "paper_calmar",
        "cost50_t1_calmar",
        "single_year_share",
        "top_ticker",
        "top_ticker_share",
        "remove_top_year_cagr",
        "remove_top_year_calmar",
        "remove_top_ticker_cagr",
        "remove_top_ticker_calmar",
    ]
    cols = [c for c in priority if c in df.columns]
    if not cols:
        cols = list(df.columns[:20])
    return df.loc[:, cols].head(50)


def summarize_csv_inventory(paths: list[Path], max_csv_mb: float) -> pd.DataFrame:
    rows = []
    for path in paths:
        size_mb = path.stat().st_size / (1024 * 1024)
        rows.append(
            {
                "csv": relative(path),
                "size_mb": round(size_mb, 3),
                "bridge_mode": "summary_if_selected" if size_mb > max_csv_mb else "copy_if_selected",
            }
        )
    return pd.DataFrame(rows)


def export_csv_safely(source: Path, target: Path, alias: str, max_csv_mb: float) -> str:
    size_mb = source.stat().st_size / (1024 * 1024)
    df = read_csv_safe(source)
    if size_mb <= max_csv_mb:
        if alias == "holdings_summary":
            save_dataframe(summarize_holdings(df), target)
            return "summarized_holdings"
        save_dataframe(df, target)
        return "copied"
    summary = summarize_large_csv(df, alias=alias, source=source, size_mb=size_mb)
    save_dataframe(summary, target)
    return "summarized_large_csv"


def summarize_large_csv(df: pd.DataFrame, alias: str, source: Path, size_mb: float) -> pd.DataFrame:
    if alias == "holdings_summary":
        return summarize_holdings(df).assign(source=str(relative(source)), source_size_mb=round(size_mb, 3))
    rows: list[dict[str, Any]] = [{"section": "meta", "source": str(relative(source)), "rows": len(df), "columns": len(df.columns), "source_size_mb": round(size_mb, 3)}]
    numeric = df.select_dtypes(include="number")
    if not numeric.empty:
        desc = numeric.describe().reset_index().rename(columns={"index": "stat"})
        desc.insert(0, "section", "numeric_describe")
        return pd.concat([pd.DataFrame(rows), desc], ignore_index=True, sort=False)
    return pd.concat([pd.DataFrame(rows), df.head(20).assign(section="head")], ignore_index=True, sort=False)


def summarize_holdings(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    data = df.copy()
    ticker_col = "ticker" if "ticker" in data.columns else None
    weight_col = "weight" if "weight" in data.columns else None
    group_cols = [c for c in ["strategy_id", "universe_name"] if c in data.columns]
    if ticker_col and weight_col:
        out = (
            data.groupby([*group_cols, ticker_col])[weight_col]
            .agg(selection_rows="count", avg_weight="mean", max_weight="max")
            .reset_index()
            .sort_values(["selection_rows", "max_weight"], ascending=False)
        )
        return out.head(200)
    return data.head(200)


def choose_csv(paths: list[Path], patterns: list[str]) -> Path | None:
    scored: list[tuple[int, float, Path]] = []
    for path in paths:
        name = path.name.lower()
        score = sum(1 for pat in patterns if pat in name)
        if score:
            scored.append((score, path.stat().st_mtime, path))
    if not scored:
        return None
    return sorted(scored, key=lambda x: (x[0], x[1]), reverse=True)[0][2]


def list_code_files_from_zip(zip_path: Path | None) -> list[str]:
    if not zip_path or not zip_path.exists():
        return []
    try:
        from zipfile import ZipFile

        with ZipFile(zip_path) as zf:
            names = zf.namelist()
        code = [n for n in names if (n.startswith("scripts/") or n.startswith("quant_lab/")) and n.endswith(".py")]
        return sorted(code)[:80]
    except Exception:
        return []


def read_csv_safe(path: Path, nrows: int | None = None) -> pd.DataFrame:
    try:
        return pd.read_csv(path, nrows=nrows)
    except Exception:
        return pd.DataFrame()


def read_json_safe(path: Path | None) -> dict[str, Any]:
    if not path or not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def read_text_excerpt(path: Path | None, max_chars: int) -> str:
    if not path or not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    return text if len(text) <= max_chars else text[:max_chars] + "\n\n...[truncated for bridge packet]..."


def extract_goal(run_summary: str, report: str) -> str:
    for text in [run_summary, report]:
        for line in text.splitlines():
            if "本轮目标" in line or "Objective" in line or "目标" in line:
                return line.strip()
    return "自动发布器未能从摘要中识别目标；请查看 RUN_SUMMARY / selected_report。"


def extract_limitations(run_summary: str, report: str, verdict: dict[str, Any]) -> str:
    lines: list[str] = []
    for key in ["reason", "classification_reason", "message"]:
        if verdict.get(key):
            lines.append(f"- verdict.{key}: `{verdict.get(key)}`")
    for text in [run_summary, report]:
        for line in text.splitlines():
            lowered = line.lower()
            if any(token in lowered for token in ["failed", "不通过", "限制", "caveat", "风险", "不允许", "阻塞"]):
                lines.append(f"- {line.strip()}")
            if len(lines) >= 20:
                break
        if len(lines) >= 20:
            break
    return "\n".join(lines) if lines else "- 未自动识别；请重点检查 gate/verdict 和核心指标。"


def dataframe_markdown(df: pd.DataFrame, max_rows: int = 20) -> str:
    if df is None or df.empty:
        return "_No table available._"
    data = df.head(max_rows).copy()
    for col in data.columns:
        if pd.api.types.is_float_dtype(data[col]):
            data[col] = data[col].map(lambda x: "" if pd.isna(x) else f"{float(x):.6f}")
    return data.to_markdown(index=False)


def format_list(items: list[str], empty: str) -> str:
    if not items:
        return empty
    return "\n".join(f"- `{item}`" for item in items)


def copy_text_file(src: Path, dst: Path) -> None:
    save_text(src.read_text(encoding="utf-8", errors="replace"), dst)


def first_existing(paths: list[Path]) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None


def relative(path: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(PROJECT_ROOT))
    except Exception:
        return str(path)


def run_cmd(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True, check=False)
    except Exception as exc:
        return subprocess.CompletedProcess(cmd, returncode=1, stdout="", stderr=str(exc))
