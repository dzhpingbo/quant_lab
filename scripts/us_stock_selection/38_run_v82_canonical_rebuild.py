"""Run v8.2 canonical source-of-truth rebuild and formal v9 precheck."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from quant_lab.us_stock_selection.chatgpt_bridge import publish_for_chatgpt
from quant_lab.us_stock_selection.utils import ensure_dir, make_logger, save_json, save_text
from quant_lab.us_stock_selection.v82_canonical_audit import run_v82_canonical_rebuild
from quant_lab.us_stock_selection.v82_canonical_reporting import (
    build_v82_canonical_excel,
    build_v82_canonical_report,
    package_v82_canonical_run,
)


OUTPUT_ROOT = PROJECT_ROOT / "outputs" / "us_stock_selection"
AGENT_LOOP_DIR = PROJECT_ROOT / "scripts" / "agent_loop"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run v8.2 canonical rebuild; no expansion, no v10, no trading.")
    parser.add_argument("--timestamp", default="", help="Optional YYYYMMDD_HHMMSS timestamp.")
    parser.add_argument("--provider-uri", default=r"C:\Users\Administrator\.qlib\qlib_data\us_data_local_2026")
    parser.add_argument("--v8-1-run-dir", default=str(OUTPUT_ROOT / "run_20260502_210856"))
    parser.add_argument("--v8-2-run-dir", default=str(OUTPUT_ROOT / "run_20260502_220641"))
    parser.add_argument("--explicit-allow-run-formal-v9", action="store_true")
    parser.add_argument("--skip-bridge", action="store_true")
    parser.add_argument("--skip-github-issue", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    timestamp = args.timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = OUTPUT_ROOT / f"v82_canonical_rebuild_{timestamp}"
    if run_dir.exists():
        raise FileExistsError(f"Refusing to overwrite existing audit directory: {run_dir}")

    logs_dir = ensure_dir(run_dir / "logs")
    reports_dir = ensure_dir(run_dir / "reports")
    logger = make_logger(logs_dir / "run.log", level="INFO")
    logger.info("Starting v8.2 canonical rebuild.")
    save_text(
        "\n".join(
            [
                "# v8.2 canonical rebuild scope",
                "",
                "No Nasdaq100/S&P500/full-market expansion.",
                "No v10 entry.",
                "No strategy search, no parameter retuning, no broker API, no real trading.",
                "Only local frozen artifacts and local Qlib provider bin files are read.",
                "",
            ]
        ),
        run_dir / "SCOPE.md",
    )

    result = run_v82_canonical_rebuild(
        run_dir,
        provider_uri=args.provider_uri,
        v8_1_run_dir=args.v8_1_run_dir,
        v8_2_run_dir=args.v8_2_run_dir,
        explicit_allow_run_formal_v9=bool(args.explicit_allow_run_formal_v9),
    )
    build_v82_canonical_report(reports_dir / "v82_canonical_rebuild_report.md", result)
    build_v82_canonical_excel(reports_dir / "v82_canonical_rebuild_summary.xlsx", result)
    write_summaries(run_dir, result, zip_path="")

    zip_path = package_v82_canonical_run(run_dir, timestamp)
    verdict = dict(result["verdict"])
    verdict["zip_path"] = str(zip_path)
    verdict["run_dir"] = str(run_dir)
    result["verdict"] = verdict
    save_json(verdict, run_dir / "v82_canonical_rebuild_verdict.json")
    save_json(verdict, run_dir / "audit_summary.json")
    write_summaries(run_dir, result, zip_path=str(zip_path))
    build_v82_canonical_report(reports_dir / "v82_canonical_rebuild_report.md", result, zip_path=zip_path)
    build_v82_canonical_excel(reports_dir / "v82_canonical_rebuild_summary.xlsx", result)
    zip_path = package_v82_canonical_run(run_dir, timestamp)
    verdict["zip_path"] = str(zip_path)
    save_json(verdict, run_dir / "v82_canonical_rebuild_verdict.json")
    save_json(verdict, run_dir / "audit_summary.json")
    logger.info(f"Packaged v8.2 canonical rebuild zip: {zip_path}")

    local_manifest: dict[str, Any] = {}
    if not args.skip_bridge:
        try:
            local_manifest = publish_for_chatgpt(run_dir=run_dir, max_csv_mb=5.0, include_xlsx=False, git_push=False)
            logger.info(f"Published local ChatGPT bridge packet: {local_manifest.get('review_packet', '')}")
        except Exception as exc:
            logger.warning(f"Local ChatGPT bridge publish failed: {exc}")

    github_result: dict[str, Any] = {}
    if not args.skip_github_issue:
        try:
            github_result = publish_github_issue_summary(verdict, result, zip_path, run_dir)
            logger.info(f"Published GitHub Issue summary: {github_result.get('issue_url', '')}")
        except Exception as exc:
            github_result = {"posted": False, "error": str(exc)}
            logger.warning(f"GitHub Issue summary publish failed: {exc}")

    print(
        json.dumps(
            {
                "run_dir": str(run_dir),
                "zip_path": str(zip_path),
                "classification": verdict.get("classification"),
                "v82_reported_vs_recomputed_consistent": verdict.get("v82_reported_vs_recomputed_consistent"),
                "root_cause": verdict.get("root_cause"),
                "formal_v82_gate_pass": verdict.get("formal_v82_gate_pass"),
                "formal_v82_cagr": verdict.get("formal_v82_cagr"),
                "formal_v82_calmar": verdict.get("formal_v82_calmar"),
                "formal_v82_max_drawdown": verdict.get("formal_v82_max_drawdown"),
                "pltr_snow_pollution_isolated": verdict.get("pltr_snow_pollution_isolated"),
                "v9_original_results_discarded": verdict.get("v9_original_results_discarded"),
                "unified_replay_role": verdict.get("unified_replay_role"),
                "formal_v9_run_plan_generated": verdict.get("formal_v9_run_plan_generated"),
                "allow_execute_formal_v9": verdict.get("allow_execute_formal_v9"),
                "allow_enter_v10": verdict.get("allow_enter_v10"),
                "requires_human_review": verdict.get("requires_human_review"),
                "local_bridge_run": local_manifest.get("run_id", "") if isinstance(local_manifest, dict) else "",
                "github_issue_posted": bool(github_result and not github_result.get("error")),
                "github_issue": github_result.get("issue_url", "") if isinstance(github_result, dict) else "",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def write_summaries(run_dir: Path, result: dict[str, Any], zip_path: str) -> None:
    verdict = dict(result["verdict"])
    text = f"""# RUN_SUMMARY

本轮目标：v8.2 canonical source-of-truth 重建与 formal v9 前置修复。

新 run 目录：`{run_dir}`
zip 路径：`{zip_path}`

核心结论：
- classification: `{verdict.get("classification")}`
- v82_reported_vs_recomputed_consistent: `{verdict.get("v82_reported_vs_recomputed_consistent")}`
- root_cause: `{verdict.get("root_cause")}`
- formal_v82_gate_pass: `{verdict.get("formal_v82_gate_pass")}`
- formal_v82_cagr: `{verdict.get("formal_v82_cagr")}`
- formal_v82_calmar: `{verdict.get("formal_v82_calmar")}`
- formal_v82_max_drawdown: `{verdict.get("formal_v82_max_drawdown")}`
- PLTR/SNOW pollution isolated: `{verdict.get("pltr_snow_pollution_isolated")}`
- v9 original discarded: `{verdict.get("v9_original_results_discarded")}`
- unified replay role: `{verdict.get("unified_replay_role")}`
- formal_v9_run_plan_generated: `{verdict.get("formal_v9_run_plan_generated")}`
- allow_execute_formal_v9: `{verdict.get("allow_execute_formal_v9")}`
- allow_enter_v10: `{verdict.get("allow_enter_v10")}`

原因：{verdict.get("reason")}

本轮没有扩 Nasdaq100/S&P500，没有进入 v10，没有下载行情，没有连接券商，没有自动 commit/push。
"""
    save_text(text, run_dir / "RUN_SUMMARY.md")
    save_text(text, PROJECT_ROOT / "RUN_SUMMARY.md")

    next_steps = f"""# NEXT_STEPS

当前状态：`{verdict.get("classification")}`。

下一步只允许：
- 审阅 `formal_v82_baseline/` 与 `formal_v9_precheck/`。
- 若批准 formal v9，必须单独开启下一轮，并显式允许执行 formal v9。
- formal v9 必须使用 canonical replay engine、同一 eligibility rule、同一 gate。

禁止：
- 不扩 Nasdaq100/S&P500/全市场。
- 不进入 v10。
- 不交易化，不连接券商，不下单。
- 不复用 v9 original metrics 或 unified replay 作为正式结果。
"""
    save_text(next_steps, run_dir / "NEXT_STEPS.md")
    save_text(next_steps, PROJECT_ROOT / "NEXT_STEPS.md")


def publish_github_issue_summary(verdict: dict[str, Any], result: dict[str, Any], zip_path: Path, run_dir: Path) -> dict[str, Any]:
    if str(AGENT_LOOP_DIR) not in sys.path:
        sys.path.insert(0, str(AGENT_LOOP_DIR))
    from bridge_io import bridge_mode, initialize_bridge, load_config
    from github_bridge import post_issue_comment

    config_path = PROJECT_ROOT / "scripts" / "agent_loop" / "loop_config_auth.yaml"
    config = load_config(config_path)
    if bridge_mode(config) != "github_issue":
        return {"posted": False, "reason": f"bridge.mode={bridge_mode(config)}"}
    initialize_bridge(config)
    gate = result.get("formal_v82", {}).get("gate_result", {})
    precheck = result.get("formal_v9_precheck", {}).get("precheck", {})
    safety = {
        "blocked": False,
        "violations": [],
        "mode": "local_offline_research_audit",
        "notes": "No broker, no order, no credential access, no push, no external market-data download, no v10.",
    }
    summary = {
        "run_dir": str(run_dir),
        "zip_path": str(zip_path),
        "classification": verdict.get("classification"),
        "v82_reported_vs_recomputed_consistent": verdict.get("v82_reported_vs_recomputed_consistent"),
        "root_cause": verdict.get("root_cause"),
        "formal_v82_gate_pass": verdict.get("formal_v82_gate_pass"),
        "formal_v82_cagr": verdict.get("formal_v82_cagr"),
        "formal_v82_calmar": verdict.get("formal_v82_calmar"),
        "formal_v82_max_drawdown": verdict.get("formal_v82_max_drawdown"),
        "pltr_snow_pollution_isolated": verdict.get("pltr_snow_pollution_isolated"),
        "formal_v9_run_plan_generated": verdict.get("formal_v9_run_plan_generated"),
        "allow_execute_formal_v9": verdict.get("allow_execute_formal_v9"),
        "allow_enter_v10": verdict.get("allow_enter_v10"),
        "reason": verdict.get("reason"),
    }
    body = "\n\n".join(
        [
            "# v8.2 Canonical Rebuild Summary",
            section("V82_CANONICAL_REBUILD_SUMMARY", f"```json\n{json.dumps(summary, ensure_ascii=False, indent=2)}\n```"),
            section("FORMAL_V82_GATE_RESULT", f"```json\n{json.dumps(gate, ensure_ascii=False, indent=2, default=str)}\n```"),
            section("FORMAL_V9_PRECHECK", f"```json\n{json.dumps(precheck, ensure_ascii=False, indent=2)}\n```"),
            section("CLASSIFICATION", str(verdict.get("classification", ""))),
            section("NEXT_ALLOWED_ACTION", str(verdict.get("next_allowed_action", ""))),
            section("SAFETY_GATE_RESULT", f"```json\n{json.dumps(safety, ensure_ascii=False, indent=2)}\n```"),
        ]
    )
    return post_issue_comment(config, body)


def section(name: str, content: str) -> str:
    return f"<!-- codex-bridge:section {name} -->\n## {name}\n\n{content.rstrip()}\n<!-- /codex-bridge:section {name} -->"


if __name__ == "__main__":
    main()

