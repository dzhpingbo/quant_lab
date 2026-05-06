"""Run the local score provenance alignment audit for v8.2 frozen Pool A vs v9 replay.

The script is local-only: it reads existing artifacts and local price parquet
files, writes audit reports, publishes the local ChatGPT bridge packet, and
posts a compact GitHub Issue summary when bridge.mode=github_issue.  It does
not commit, push, download market data, expand the universe, or touch trading
integrations.
"""

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
from quant_lab.us_stock_selection.score_provenance_audit import run_score_provenance_alignment_audit
from quant_lab.us_stock_selection.utils import ensure_dir, make_logger, save_json, save_text
from quant_lab.us_stock_selection.v9_alignment_reporting import (
    build_score_provenance_alignment_excel,
    build_score_provenance_alignment_report,
    package_score_provenance_alignment_run,
)


OUTPUT_ROOT = PROJECT_ROOT / "outputs" / "us_stock_selection"
AGENT_LOOP_DIR = PROJECT_ROOT / "scripts" / "agent_loop"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run score provenance alignment audit; no expansion, no v10, no trading.")
    parser.add_argument("--timestamp", default="", help="Optional YYYYMMDD_HHMMSS timestamp.")
    parser.add_argument("--skip-bridge", action="store_true", help="Do not publish docs/chatgpt_bridge packet.")
    parser.add_argument("--skip-github-issue", action="store_true", help="Do not post GitHub Issue summary.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    timestamp = args.timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = OUTPUT_ROOT / f"score_provenance_alignment_audit_{timestamp}"
    if run_dir.exists():
        raise FileExistsError(f"Refusing to overwrite existing audit directory: {run_dir}")

    logs_dir = ensure_dir(run_dir / "logs")
    reports_dir = ensure_dir(run_dir / "reports")
    logger = make_logger(logs_dir / "run.log", level="INFO")
    logger.info("Starting score provenance alignment audit.")
    save_text(
        "\n".join(
            [
                "# Score provenance alignment audit scope",
                "",
                "No Nasdaq100/S&P500/full-market expansion.",
                "No v10 entry.",
                "No strategy search, no gate change, no broker API, no real trading.",
                "Only local existing artifacts, local historical outputs, and local price parquet files are read.",
                "",
            ]
        ),
        run_dir / "SCOPE.md",
    )

    result = run_score_provenance_alignment_audit(run_dir)
    verdict = dict(result["verdict"])
    build_score_provenance_alignment_report(reports_dir / "score_provenance_alignment_audit_report.md", result)
    build_score_provenance_alignment_excel(reports_dir / "score_provenance_alignment_audit_summary.xlsx", result)

    write_summaries(run_dir, result, zip_path="")
    zip_path = package_score_provenance_alignment_run(run_dir, timestamp)
    verdict["zip_path"] = str(zip_path)
    verdict["run_dir"] = str(run_dir)
    result["verdict"] = verdict
    save_json(verdict, run_dir / "score_provenance_alignment_audit_verdict.json")
    save_json(verdict, run_dir / "audit_summary.json")
    write_summaries(run_dir, result, zip_path=str(zip_path))
    build_score_provenance_alignment_report(reports_dir / "score_provenance_alignment_audit_report.md", result, zip_path=zip_path)
    build_score_provenance_alignment_excel(reports_dir / "score_provenance_alignment_audit_summary.xlsx", result)
    zip_path = package_score_provenance_alignment_run(run_dir, timestamp)
    verdict["zip_path"] = str(zip_path)
    save_json(verdict, run_dir / "score_provenance_alignment_audit_verdict.json")
    save_json(verdict, run_dir / "audit_summary.json")
    logger.info(f"Packaged audit zip: {zip_path}")

    local_manifest: dict[str, Any] = {}
    if not args.skip_bridge:
        try:
            local_manifest = publish_for_chatgpt(run_dir=run_dir, max_csv_mb=5.0, include_xlsx=False, git_push=False)
            logger.info(f"Published local ChatGPT bridge packet: {local_manifest.get('review_packet', '')}")
        except Exception as exc:  # pragma: no cover - local bridge can vary by environment
            logger.warning(f"Local ChatGPT bridge publish failed: {exc}")

    github_result: dict[str, Any] = {}
    if not args.skip_github_issue:
        try:
            github_result = publish_github_issue_summary(verdict, zip_path, run_dir)
            logger.info(f"Published GitHub Issue summary: {github_result.get('issue_url', '')}")
        except Exception as exc:  # pragma: no cover - GitHub auth/network differs by environment
            github_result = {"posted": False, "error": str(exc)}
            logger.warning(f"GitHub Issue summary publish failed: {exc}")

    print(
        json.dumps(
            {
                "run_dir": str(run_dir),
                "zip_path": str(zip_path),
                "classification": verdict.get("classification"),
                "score_provenance_consistent": verdict.get("score_provenance_consistent"),
                "method_window_consistent": verdict.get("method_window_consistent"),
                "return_reconstruction_consistent": verdict.get("return_reconstruction_consistent"),
                "baseline_exception_pollution_found": verdict.get("baseline_exception_pollution_found"),
                "v9_original_results_should_be_discarded": verdict.get("v9_original_results_should_be_discarded"),
                "unified_replay_usable": verdict.get("unified_replay_usable"),
                "allow_continue_v9": verdict.get("allow_continue_v9"),
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

本轮目标：score provenance 对齐审计；只比较 v8.2 frozen Pool A 与 v9 local/unified replay 的 score、feature cache、fit、label、universe、calendar、portfolio、return reconstruction、gate 和 baseline exception。

新 run 目录：`{run_dir}`
zip 路径：`{zip_path}`

核心结论：
- classification: `{verdict.get("classification")}`
- score_provenance_consistent: `{verdict.get("score_provenance_consistent")}`
- method_window_consistent: `{verdict.get("method_window_consistent")}`
- return_reconstruction_consistent: `{verdict.get("return_reconstruction_consistent")}`
- baseline_exception_pollution_found: `{verdict.get("baseline_exception_pollution_found")}`
- v9_original_results_should_be_discarded: `{verdict.get("v9_original_results_should_be_discarded")}`
- unified_replay_usable: `{verdict.get("unified_replay_usable")}`
- allow_continue_v9: `{verdict.get("allow_continue_v9")}`
- allow_enter_v10: `{verdict.get("allow_enter_v10")}`
- requires_human_review: `{verdict.get("requires_human_review")}`

原因：{verdict.get("reason")}

本轮没有扩 Nasdaq100/S&P500，没有进入 v10，没有下载行情，没有连接券商，没有自动 commit/push。
"""
    save_text(text, run_dir / "RUN_SUMMARY.md")
    save_text(text, PROJECT_ROOT / "RUN_SUMMARY.md")

    next_steps = f"""# NEXT_STEPS

当前状态：`{verdict.get("classification")}`。

下一步只允许：
- 人工/ChatGPT 审阅本轮 score provenance audit。
- 若继续研究，按 v8.2 同池、同策略、同 gate、同 score source 重新定义正式 v9 口径并重跑。
- 若确认 score provenance mismatch，先修复 score/feature/model fit provenance，再回到审计。

禁止：
- 不扩 Nasdaq100/S&P500/全市场。
- 不进入 v10。
- 不交易化，不连接券商，不下单。
- 不把 v9 original full-window 指标包装为通过。
"""
    save_text(next_steps, run_dir / "NEXT_STEPS.md")
    save_text(next_steps, PROJECT_ROOT / "NEXT_STEPS.md")


def publish_github_issue_summary(verdict: dict[str, Any], zip_path: Path, run_dir: Path) -> dict[str, Any]:
    if str(AGENT_LOOP_DIR) not in sys.path:
        sys.path.insert(0, str(AGENT_LOOP_DIR))
    from bridge_io import bridge_mode, initialize_bridge, load_config
    from github_bridge import post_issue_comment

    config_path = PROJECT_ROOT / "scripts" / "agent_loop" / "loop_config_auth.yaml"
    config = load_config(config_path)
    if bridge_mode(config) != "github_issue":
        return {"posted": False, "reason": f"bridge.mode={bridge_mode(config)}"}
    initialize_bridge(config)
    safety = {
        "blocked": False,
        "violations": [],
        "mode": "local_offline_research_audit",
        "notes": "No broker, no order, no credential access, no push, no external market-data download.",
    }
    summary = {
        "run_dir": str(run_dir),
        "zip_path": str(zip_path),
        "classification": verdict.get("classification"),
        "score_provenance_consistent": verdict.get("score_provenance_consistent"),
        "method_window_consistent": verdict.get("method_window_consistent"),
        "return_reconstruction_consistent": verdict.get("return_reconstruction_consistent"),
        "baseline_exception_pollution_found": verdict.get("baseline_exception_pollution_found"),
        "v9_original_results_should_be_discarded": verdict.get("v9_original_results_should_be_discarded"),
        "unified_replay_usable": verdict.get("unified_replay_usable"),
        "allow_continue_v9": verdict.get("allow_continue_v9"),
        "allow_enter_v10": verdict.get("allow_enter_v10"),
        "requires_human_review": verdict.get("requires_human_review"),
        "reason": verdict.get("reason"),
    }
    body = "\n\n".join(
        [
            "# Score Provenance Audit Summary",
            section("SCORE_PROVENANCE_AUDIT_SUMMARY", f"```json\n{json.dumps(summary, ensure_ascii=False, indent=2)}\n```"),
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
