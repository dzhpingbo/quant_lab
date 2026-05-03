"""Run v8.1 model-switch validation for LGBModel and Ridge."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from quant_lab.us_stock_selection.local_qlib_provider_builder import default_local_provider_uri
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
from quant_lab.us_stock_selection.v8_1_model_switch import run_v8_1_model_switch
from quant_lab.us_stock_selection.v8_1_reporting import build_v8_1_excel, build_v8_1_report, package_v8_1_run


DEFAULT_SOURCE_RUN = ROOT / "outputs" / "us_stock_selection" / "run_20260426_060824"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run v8.1 model switch: LGBModel/Ridge, no v9, no universe expansion.")
    parser.add_argument("--config", default="configs/us_stock_selection/validation_config.yaml")
    parser.add_argument("--provider-uri", default=str(default_local_provider_uri()))
    parser.add_argument("--source-run", default=str(DEFAULT_SOURCE_RUN))
    parser.add_argument("--run-dir", default="", help="Existing run dir to resume; empty creates new run.")
    parser.add_argument("--models", default="LGBModel,Ridge", help="Comma-separated model names: LGBModel,Ridge")
    parser.add_argument("--resume", action="store_true", default=True)
    parser.add_argument("--no-resume", action="store_false", dest="resume")
    parser.add_argument("--dry-run-init", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = merge_many_dicts(load_yaml("configs/us_stock_selection/factor_groups.yaml"), load_yaml(args.config))
    output_root = ROOT / config.get("paths", {}).get("output_root", "outputs/us_stock_selection")
    if args.run_dir:
        run_dir = ensure_dir(args.run_dir)
        logs_dir = ensure_dir(run_dir / "logs")
        reports_dir = ensure_dir(run_dir / "reports")
        timestamp = run_dir.name.replace("run_", "")
    else:
        artifacts = create_run_artifacts(output_root)
        run_dir = artifacts.run_dir
        logs_dir = artifacts.logs_dir
        reports_dir = artifacts.reports_dir
        timestamp = artifacts.timestamp

    logger = make_logger(logs_dir / "v8_1_model_switch.log", level=str(config.get("logging", {}).get("level", "INFO")))
    logger.info(f"Prepared v8.1 model-switch run {run_dir}")
    save_yaml(config, run_dir / "run_config.yaml")

    cache_dir = ensure_dir(run_dir / "v7_feature_cache")
    source_cache = Path(args.source_run) / "v7_feature_cache"
    fallback = ROOT / "outputs" / "us_stock_selection" / "run_20260426_035045" / "v7_feature_cache"
    out_dir = ensure_dir(run_dir / "v8_1_model_switch")
    save_text(
        "\n".join(
            [
                "# v8.1 model switch",
                "",
                "Scope: switch main model from ElasticNet to LGBModel/Ridge.",
                "Not v9. No Nasdaq100/S&P500 expansion. No trading claim.",
                f"source_run: `{args.source_run}`",
                f"models: `{args.models}`",
                "",
            ]
        ),
        run_dir / "V8_1_MODEL_SWITCH_SCOPE.md",
    )
    if args.dry_run_init:
        logger.info("Dry-run init requested; stopping before cache copy and replay.")
        print({"run_dir": str(run_dir), "stage": "v8.1_model_switch", "dry_run_init": True})
        return

    if not (cache_dir / "alpha360_cache.parquet").exists():
        shutil.copytree(source_cache if source_cache.exists() else fallback, cache_dir, dirs_exist_ok=True)
    models = [m.strip() for m in args.models.split(",") if m.strip()]

    result = run_v8_1_model_switch(
        out_dir,
        cache_dir=cache_dir,
        provider_uri=args.provider_uri,
        models=models,
        resume=args.resume,
        logger=logger,
    )
    summary = result["summary"]
    cycle_verdict = result["cycle_verdict"]
    save_json(cycle_verdict, run_dir / "v8_1_cycle_verdict.json")

    lgb_stability = _read_optional(out_dir / "Alpha360_LGBModel" / "model_stability_summary.csv")
    ridge_stability = _read_optional(out_dir / "Alpha360_Ridge" / "model_stability_summary.csv")
    build_v8_1_report(reports_dir / "us_stock_selection_v8_1_model_switch_report.md", summary, cycle_verdict, lgb_stability, ridge_stability)
    build_v8_1_excel(
        reports_dir / "us_stock_selection_v8_1_summary.xlsx",
        build_excel_sheets(out_dir, summary, cycle_verdict),
    )
    update_summaries(run_dir, summary, cycle_verdict)
    zip_path = package_v8_1_run(run_dir, timestamp)
    logger.info(f"Packaged v8.1 zip {zip_path}")
    print(
        {
            "run_dir": str(run_dir),
            "zip_path": str(zip_path),
            "classification": cycle_verdict.get("classification"),
            "allow_enter_v9": cycle_verdict.get("allow_enter_v9"),
            "best_model_branch": cycle_verdict.get("best_model_branch"),
        }
    )


def _read_optional(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def build_excel_sheets(out_dir: Path, summary: pd.DataFrame, cycle_verdict: dict) -> dict[str, pd.DataFrame]:
    sheets: dict[str, pd.DataFrame] = {
        "summary": summary,
        "cycle_verdict": pd.DataFrame([cycle_verdict]),
    }
    for branch in ["Alpha360_LGBModel", "Alpha360_Ridge"]:
        model_dir = out_dir / branch
        for name, rel in [
            (f"{branch}_paper", "paper_trading_metrics.csv"),
            (f"{branch}_stress", "execution_stress_results.csv"),
            (f"{branch}_ticker", "attribution_ticker_contribution.csv"),
            (f"{branch}_yearly", "attribution_yearly_return.csv"),
            (f"{branch}_leave_ticker", "leave_one_ticker_out.csv"),
            (f"{branch}_leave_year", "leave_one_year_out.csv"),
            (f"{branch}_stability", "model_stability_summary.csv"),
        ]:
            path = model_dir / rel
            if path.exists():
                sheets[name[:31]] = pd.read_csv(path).head(500)
    return sheets


def update_summaries(run_dir: Path, summary: pd.DataFrame, cycle_verdict: dict) -> None:
    best_branch = str(cycle_verdict.get("best_model_branch", ""))
    best = summary.loc[summary["model_branch"] == best_branch].iloc[0].to_dict() if best_branch and not summary.loc[summary["model_branch"] == best_branch].empty else {}
    lines = [
        "# RUN_SUMMARY",
        "",
        "本轮目标：执行 v8.1 model switch，不进入 v9，不扩 Nasdaq100/S&P500，不交易化。",
        "",
        f"新 run 目录：`{run_dir}`",
        "",
        f"最终分类：`{cycle_verdict.get('classification')}`",
        f"是否允许进入 v9：`{cycle_verdict.get('allow_enter_v9')}`",
        f"最佳分支：`{cycle_verdict.get('best_model_branch')}`",
        "",
        "最佳分支核心指标：",
        f"- paper CAGR: `{best.get('paper_cagr')}`",
        f"- paper Calmar: `{best.get('paper_calmar')}`",
        f"- 50bps/T+1 CAGR: `{best.get('cost50_t1_cagr')}`",
        f"- 50bps/T+1 Calmar: `{best.get('cost50_t1_calmar')}`",
        f"- T+2 CAGR: `{best.get('t2_cagr')}`",
        f"- T+2 Calmar: `{best.get('t2_calmar')}`",
        f"- top ticker share: `{best.get('top_ticker_share')}`",
        f"- single-year share: `{best.get('single_year_share')}`",
        f"- remove top ticker CAGR: `{best.get('remove_top_ticker_cagr')}`",
        f"- remove top year CAGR: `{best.get('remove_top_year_cagr')}`",
        "",
        "分支结果：",
    ]
    for _, row in summary.iterrows():
        lines.append(
            f"- `{row.get('model_branch')}`: classification `{row.get('classification')}`, CAGR `{row.get('paper_cagr')}`, Calmar `{row.get('paper_calmar')}`, allow_v9 `{row.get('allow_enter_v9')}`"
        )
    lines.extend(
        [
            "",
            "下一步：如果 allow_enter_v9 仍为 False，则继续修复稳定性/集中度，不允许扩池；如果 True，也只允许后续另行批准的小幅科技成长池研究，不允许 Nasdaq100/S&P500 扩池。",
        ]
    )
    text = "\n".join(lines) + "\n"
    save_text(text, run_dir / "RUN_SUMMARY.md")
    save_text(text, ROOT / "RUN_SUMMARY.md")

    next_text = f"""# NEXT_STEPS

当前状态：v8.1 model switch 已完成。

- Run：`{run_dir}`
- Classification：`{cycle_verdict.get('classification')}`
- Allow v9：`{cycle_verdict.get('allow_enter_v9')}`
- Best model branch：`{cycle_verdict.get('best_model_branch')}`

硬边界：

1. 不交易化。
2. 不扩 Nasdaq100/S&P500。
3. 如果 allow v9 为 True，v9 也只能在用户另行批准后做小幅科技成长池研究。
4. 如果 allow v9 为 False，下一步只能继续修复模型稳定性、执行敏感性或集中度。
"""
    save_text(next_text, ROOT / "NEXT_STEPS.md")


if __name__ == "__main__":
    main()
