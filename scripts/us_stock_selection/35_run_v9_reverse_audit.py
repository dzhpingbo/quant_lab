"""Run v9/v8.2 reverse audit without expansion or trading integration."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from quant_lab.us_stock_selection.chatgpt_bridge import publish_for_chatgpt
from quant_lab.us_stock_selection.utils import (
    PROJECT_ROOT as ROOT,
    create_run_artifacts,
    ensure_dir,
    load_yaml,
    make_logger,
    merge_many_dicts,
    save_json,
    save_text,
    save_yaml,
)
from quant_lab.us_stock_selection.v9_reverse_audit import run_v9_reverse_audit
from quant_lab.us_stock_selection.v9_reverse_audit_reporting import (
    build_v9_reverse_audit_excel,
    build_v9_reverse_audit_report,
    package_v9_reverse_audit_run,
)


DEFAULT_V9_RUN = ROOT / "outputs" / "us_stock_selection" / "run_20260502_222407"
DEFAULT_V8_2_RUN = ROOT / "outputs" / "us_stock_selection" / "run_20260502_220641"
DEFAULT_V8_1_RUN = ROOT / "outputs" / "us_stock_selection" / "run_20260502_210856"
DEFAULT_STORE = ROOT / "data" / "unified_ohlcv" / "us_stock_selection"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run bounded v9/v8.2 reverse audit; no expansion, no v10, no trading.")
    parser.add_argument("--config", default="configs/us_stock_selection/validation_config.yaml")
    parser.add_argument("--v9-run-dir", default=str(DEFAULT_V9_RUN))
    parser.add_argument("--v8-2-run-dir", default=str(DEFAULT_V8_2_RUN))
    parser.add_argument("--v8-1-run-dir", default=str(DEFAULT_V8_1_RUN))
    parser.add_argument("--unified-store-dir", default=str(DEFAULT_STORE))
    parser.add_argument("--run-dir", default="", help="Existing run dir to resume; empty creates a new run.")
    parser.add_argument("--dry-run-init", action="store_true")
    parser.add_argument("--skip-bridge", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = merge_many_dicts(load_yaml("configs/us_stock_selection/factor_groups.yaml"), load_yaml(args.config))
    output_root = ROOT / config.get("paths", {}).get("output_root", "outputs/us_stock_selection")
    if args.run_dir:
        run_dir = ensure_dir(args.run_dir)
        timestamp = run_dir.name.replace("run_", "")
        logs_dir = ensure_dir(run_dir / "logs")
        reports_dir = ensure_dir(run_dir / "reports")
    else:
        artifacts = create_run_artifacts(output_root)
        run_dir = artifacts.run_dir
        timestamp = artifacts.timestamp
        logs_dir = artifacts.logs_dir
        reports_dir = artifacts.reports_dir

    logger = make_logger(logs_dir / "v9_reverse_audit.log", level=str(config.get("logging", {}).get("level", "INFO")))
    logger.info(f"Prepared v9 reverse audit run {run_dir}")
    save_yaml(config, run_dir / "run_config.yaml")
    save_text(
        "\n".join(
            [
                "# v9 reverse audit scope",
                "",
                "Task: v9_reverse_audit_no_expansion.",
                "No Nasdaq100/S&P500/full-market expansion.",
                "No v10 entry.",
                "No strategy search, no gate change, no broker API, no real trading.",
                f"v9_run_dir: `{args.v9_run_dir}`",
                f"v8_2_run_dir: `{args.v8_2_run_dir}`",
                f"v8_1_run_dir: `{args.v8_1_run_dir}`",
                "",
            ]
        ),
        run_dir / "V9_REVERSE_AUDIT_SCOPE.md",
    )
    if args.dry_run_init:
        print({"run_dir": str(run_dir), "stage": "v9_reverse_audit_no_expansion", "dry_run_init": True})
        return

    audit_dir = ensure_dir(run_dir / "v9_reverse_audit")
    result = run_v9_reverse_audit(
        out_dir=audit_dir,
        v9_run_dir=args.v9_run_dir,
        v8_2_run_dir=args.v8_2_run_dir,
        v8_1_run_dir=args.v8_1_run_dir,
        unified_store_dir=args.unified_store_dir,
        project_root=ROOT,
        logger=logger,
    )
    verdict = result["verdict"]
    save_json(verdict, run_dir / "v9_reverse_audit_verdict.json")
    build_v9_reverse_audit_report(reports_dir / "us_stock_selection_v9_reverse_audit_report.md", result)
    build_v9_reverse_audit_excel(reports_dir / "us_stock_selection_v9_reverse_audit_summary.xlsx", result)
    update_summaries(run_dir, result)
    shutil.copy2(logs_dir / "v9_reverse_audit.log", logs_dir / "run.log")
    zip_path = package_v9_reverse_audit_run(run_dir, timestamp)
    logger.info(f"Packaged v9 reverse audit zip {zip_path}")

    manifest = {}
    if not args.skip_bridge:
        manifest = publish_for_chatgpt(run_dir=run_dir, max_csv_mb=5.0, include_xlsx=False, git_push=False)
        logger.info(f"Published ChatGPT bridge packet {manifest.get('review_packet', '')}")

    print(
        {
            "run_dir": str(run_dir),
            "zip_path": str(zip_path),
            "classification": verdict.get("classification"),
            "requires_human_review": verdict.get("requires_human_review"),
            "allow_enter_v10": verdict.get("allow_enter_v10"),
            "bridge_run": manifest.get("run_id", "") if isinstance(manifest, dict) else "",
        }
    )


def update_summaries(run_dir: Path, result: dict[str, object]) -> None:
    verdict = result["verdict"]
    pool = result["pool_a_replay_audit"]
    negatives = result["negative_controls"]
    benchmark = result["benchmark"]
    stress = result["stress_test"]
    pool_failed = int((~pool["pass"].astype(bool)).sum()) if isinstance(pool, pd.DataFrame) and not pool.empty else 0
    neg_suspicious = (
        int(negatives["leakage_or_backtest_bug_suspected"].astype(bool).sum())
        if isinstance(negatives, pd.DataFrame) and not negatives.empty
        else 0
    )
    lines = [
        "# RUN_SUMMARY",
        "",
        "本轮目标：执行 v9/v8.2 reverse audit；只审计未来函数、执行口径、Pool A reproduction、benchmark/stress 和数据治理。",
        "",
        f"新 run 目录：`{run_dir}`",
        f"最终分类：`{verdict.get('classification')}`",
        f"是否允许进入 v10：`{verdict.get('allow_enter_v10')}`",
        f"是否允许扩 Nasdaq100：`{verdict.get('allow_expand_nasdaq100')}`",
        f"是否允许扩 S&P500：`{verdict.get('allow_expand_sp500')}`",
        f"是否允许交易执行：`{verdict.get('allow_trade_execution')}`",
        "",
        "核心审计结果：",
        f"- Time alignment pass: `{verdict.get('time_alignment_pass')}`",
        f"- Pool A replay pass: `{verdict.get('pool_a_replay_pass')}`；failed rows `{pool_failed}`",
        f"- Negative controls pass: `{verdict.get('negative_controls_pass')}`；suspicious controls `{neg_suspicious}`",
        f"- Benchmark rows: `{len(benchmark) if isinstance(benchmark, pd.DataFrame) else 0}`",
        f"- Stress rows: `{len(stress) if isinstance(stress, pd.DataFrame) else 0}`",
        f"- Requires human review: `{verdict.get('requires_human_review')}`",
        f"- Reason: `{verdict.get('reason')}`",
        "",
        "结论：本轮仍不是交易化；不得进入 v10，不得扩 Nasdaq100/S&P500。若分类为 `invalid_or_needs_human_review`，下一步只能人工复核 Pool A 口径和数据来源。",
        "",
    ]
    text = "\n".join(lines)
    save_text(text, run_dir / "RUN_SUMMARY.md")
    save_text(text, ROOT / "RUN_SUMMARY.md")

    next_text = f"""# NEXT_STEPS

当前状态：v9/v8.2 reverse audit 已完成。

- Run：`{run_dir}`
- Classification：`{verdict.get('classification')}`
- Allow v10：`{verdict.get('allow_enter_v10')}`
- Requires human review：`{verdict.get('requires_human_review')}`

硬边界：

1. 不扩 Nasdaq100，不扩 S&P500，不做全市场扩池。
2. 不进入 v10。
3. 不接券商 API，不做真实交易。
4. 不通过调 gate、ranking 权重或更换主线策略改善结果。

下一步自动计划：

1. 人工复核 `v9_reverse_audit/pool_a_replay_audit.csv` 中 v8.2 frozen 与 v9 local replay 的差异。
2. 人工复核 `v9_reverse_audit/universe_policy_audit.csv` 中 PLTR/SNOW 等 baseline-only exception。
3. 若需继续，只允许做同池、同策略、同 gate 的数据口径复核；不得扩池或交易化。
"""
    save_text(next_text, run_dir / "NEXT_STEPS.md")
    save_text(next_text, ROOT / "NEXT_STEPS.md")


if __name__ == "__main__":
    main()
