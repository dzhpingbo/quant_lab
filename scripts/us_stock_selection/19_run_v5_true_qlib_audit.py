"""Run v5 true Qlib provider preparation plus v4 best-strategy audit."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from quant_lab.us_stock_selection.qlib_data_converter import prepare_local_qlib_dump_inputs
from quant_lab.us_stock_selection.true_qlib_provider import (
    default_true_provider_uri,
    official_download_attempt,
    qlib_provider_health_check,
    run_true_provider_lab,
)
from quant_lab.us_stock_selection.utils import (
    PROJECT_ROOT as ROOT,
    create_run_artifacts,
    load_env_config,
    load_yaml,
    make_logger,
    merge_many_dicts,
    save_yaml,
)
from quant_lab.us_stock_selection.v4_audit import audit_v4_best_strategy
from quant_lab.us_stock_selection.v5_reporting import build_v5_excel, build_v5_report, package_v5_run


def main():
    parser = argparse.ArgumentParser(description="Run v5 true Qlib + fallback audit.")
    parser.add_argument("--config", default="configs/us_stock_selection/validation_config.yaml")
    parser.add_argument("--v4-run-dir", default="outputs/us_stock_selection/run_20260425_114504")
    parser.add_argument("--max-true-model-runs", type=int, default=12)
    parser.add_argument("--true-feature-sets", default="Alpha158,Alpha360,Alpha158_custom")
    parser.add_argument("--true-models", default="Ridge,LightGBM")
    parser.add_argument("--true-labels", default="forward_return_5d,forward_return_20d")
    args = parser.parse_args()

    config = merge_many_dicts(load_yaml("configs/us_stock_selection/factor_groups.yaml"), load_yaml(args.config))
    artifacts = create_run_artifacts(ROOT / config.get("paths", {}).get("output_root", "outputs/us_stock_selection"))
    logger = make_logger(artifacts.logs_dir / "run.log", level=str(config.get("logging", {}).get("level", "INFO")))
    logger.info(f"Prepared v5 run {artifacts.run_dir}")
    save_yaml(config, artifacts.run_dir / "run_config.yaml")

    provider_dir = artifacts.run_dir / "qlib_data_true_provider"
    true_lab_dir = artifacts.run_dir / "qlib_true_provider_lab"
    provider_dir.mkdir(parents=True, exist_ok=True)
    true_lab_dir.mkdir(parents=True, exist_ok=True)

    download_status = official_download_attempt(provider_dir, target_dir=default_true_provider_uri(), execute=False)
    health, _sample = qlib_provider_health_check(provider_dir, provider_uri=default_true_provider_uri())
    local_conversion = prepare_local_qlib_dump_inputs(provider_dir, config, load_env_config(), logger=logger)

    if health.get("provider_readable"):
        true_outputs = run_true_provider_lab(
            true_lab_dir,
            provider_uri=default_true_provider_uri(),
            max_model_runs=args.max_true_model_runs,
            feature_sets=[item.strip() for item in args.true_feature_sets.split(",") if item.strip()],
            model_names=[item.strip() for item in args.true_models.split(",") if item.strip()],
            labels=[item.strip() for item in args.true_labels.split(",") if item.strip()],
        )
    else:
        true_outputs = {"model_runs": pd.DataFrame(), "signal_quality": pd.DataFrame(), "backtest_results": pd.DataFrame()}

    audit_outputs = audit_v4_best_strategy(ROOT / args.v4_run_dir, artifacts.run_dir, config, logger=logger)

    for src, dst_dir in [
        (ROOT / args.v4_run_dir / "benchmark" / "comparison_v4.csv", artifacts.benchmark_dir),
        (ROOT / args.v4_run_dir / "ranking" / "final_ticker_ranking.csv", artifacts.ranking_dir),
    ]:
        if src.exists():
            shutil.copy2(src, dst_dir / src.name)

    true_results = true_outputs.get("backtest_results", pd.DataFrame())
    stress = {k: v for k, v in audit_outputs.items() if k in {"cost_sensitivity", "rebalance_sensitivity", "topk_sensitivity", "safe_asset_sensitivity", "remove_top_contributor_test", "leave_one_year_out"}}
    build_v5_report(
        artifacts.reports_dir / "us_stock_selection_v5_true_qlib_and_audit_report.md",
        health,
        local_conversion,
        true_results,
        audit_outputs["summary"],
        audit_outputs["leakage"],
        audit_outputs["holdings"],
        audit_outputs["yearly_return"],
        audit_outputs["wf_summary"],
        stress,
    )
    build_v5_excel(
        artifacts.reports_dir / "us_stock_selection_v5_summary.xlsx",
        {
            "provider_health": pd.DataFrame([health]),
            "download_status": pd.DataFrame([download_status]),
            "local_conversion": pd.DataFrame([local_conversion]),
            "true_model_runs": true_outputs.get("model_runs", pd.DataFrame()),
            "true_signal_quality": true_outputs.get("signal_quality", pd.DataFrame()),
            "true_backtest": true_results,
            "leakage": pd.DataFrame([audit_outputs["leakage"]]),
            "alignment": audit_outputs["alignment"],
            "holdings": audit_outputs["holdings"],
            "yearly_holding": audit_outputs["yearly_holding"],
            "return_attr": audit_outputs["return_attribution"],
            "yearly_return": audit_outputs["yearly_return"],
            "safe_switch": audit_outputs["safe_switch"],
            "wf_summary": audit_outputs["wf_summary"],
            "wf_anchored": audit_outputs["wf_anchored_detail"],
            "wf_rolling_3y": audit_outputs["wf_rolling_3y_detail"],
            "wf_rolling_5y": audit_outputs["wf_rolling_5y_detail"],
            "cost_stress": stress.get("cost_sensitivity", pd.DataFrame()),
            "rebalance_stress": stress.get("rebalance_sensitivity", pd.DataFrame()),
            "topk_stress": stress.get("topk_sensitivity", pd.DataFrame()),
            "safe_asset_stress": stress.get("safe_asset_sensitivity", pd.DataFrame()),
            "remove_top": stress.get("remove_top_contributor_test", pd.DataFrame()),
            "leave_one_year": stress.get("leave_one_year_out", pd.DataFrame()),
        },
    )
    zip_path = package_v5_run(artifacts.run_dir, artifacts.timestamp)
    print(
        {
            "run_dir": str(artifacts.run_dir),
            "zip_path": str(zip_path),
            "true_provider_readable": health.get("provider_readable"),
            "true_provider_rows": len(true_results),
            "classification": audit_outputs["summary"].get("classification"),
        }
    )


if __name__ == "__main__":
    main()
