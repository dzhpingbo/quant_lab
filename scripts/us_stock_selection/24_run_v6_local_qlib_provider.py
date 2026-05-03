"""Run v6 local Qlib provider, Handler workflow, robust portfolio, and report."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from quant_lab.us_stock_selection.local_qlib_provider_builder import (
    build_local_qlib_provider,
    default_local_provider_uri,
    locate_or_clone_qlib_source,
)
from quant_lab.us_stock_selection.portfolio_robustifier import (
    build_benchmark_comparison_v6,
    run_robust_portfolio_backtests,
    run_v6_overfit_checks,
    run_v6_walk_forward,
)
from quant_lab.us_stock_selection.qlib_signal_exporter import combine_prediction_files
from quant_lab.us_stock_selection.qlib_workflow_runner import run_local_qlib_workflows
from quant_lab.us_stock_selection.utils import (
    PROJECT_ROOT as ROOT,
    create_run_artifacts,
    load_env_config,
    load_yaml,
    make_logger,
    merge_many_dicts,
    save_yaml,
)
from quant_lab.us_stock_selection.v6_reporting import build_v6_excel, build_v6_report, package_v6_run


def main() -> None:
    parser = argparse.ArgumentParser(description="Run v6 local Qlib workflow.")
    parser.add_argument("--config", default="configs/us_stock_selection/validation_config.yaml")
    parser.add_argument("--provider-uri", default=str(default_local_provider_uri()))
    parser.add_argument("--max-workflow-runs", type=int, default=12)
    parser.add_argument("--feature-sets", default="Alpha158,Alpha360")
    parser.add_argument("--models", default="LGBModel,Ridge,ElasticNet")
    parser.add_argument("--labels", default="label_5d,label_20d")
    parser.add_argument("--no-rebuild-provider", action="store_true")
    parser.add_argument("--no-qrun", action="store_true")
    args = parser.parse_args()

    config = merge_many_dicts(load_yaml("configs/us_stock_selection/factor_groups.yaml"), load_yaml(args.config))
    artifacts = create_run_artifacts(ROOT / config.get("paths", {}).get("output_root", "outputs/us_stock_selection"))
    logger = make_logger(artifacts.logs_dir / "run.log", level=str(config.get("logging", {}).get("level", "INFO")))
    logger.info(f"Prepared v6 run {artifacts.run_dir}")
    save_yaml(config, artifacts.run_dir / "run_config.yaml")

    qlib_source_dir = artifacts.run_dir / "qlib_source"
    qlib_local_dir = artifacts.run_dir / "qlib_local_provider"
    qlib_workflow_dir = artifacts.run_dir / "qlib_workflow"
    portfolio_dir = artifacts.run_dir / "v6_portfolio_backtest"
    wf_dir = artifacts.run_dir / "v6_walk_forward"
    overfit_dir = artifacts.run_dir / "v6_overfit"
    for path in [qlib_source_dir, qlib_local_dir, qlib_workflow_dir, portfolio_dir, wf_dir, overfit_dir]:
        path.mkdir(parents=True, exist_ok=True)

    source_status = locate_or_clone_qlib_source(qlib_source_dir, clone_if_missing=True)
    provider_status = build_local_qlib_provider(
        qlib_local_dir,
        config,
        load_env_config(),
        logger,
        qlib_source_dir=source_status.get("selected_source") or None,
        provider_uri=args.provider_uri,
        rebuild=not args.no_rebuild_provider,
    )
    workflow_outputs = run_local_qlib_workflows(
        qlib_workflow_dir,
        provider_uri=args.provider_uri,
        feature_sets=[x.strip() for x in args.feature_sets.split(",") if x.strip()],
        models=[x.strip() for x in args.models.split(",") if x.strip()],
        labels=[x.strip() for x in args.labels.split(",") if x.strip()],
        max_runs=args.max_workflow_runs,
        attempt_qrun=not args.no_qrun,
    )
    combine_prediction_files(workflow_outputs.get("predictions_index", pd.DataFrame()), qlib_workflow_dir / "predictions")
    portfolio_outputs = run_robust_portfolio_backtests(
        portfolio_dir,
        args.provider_uri,
        workflow_outputs.get("predictions_index", pd.DataFrame()),
    )
    benchmark = build_benchmark_comparison_v6(artifacts.benchmark_dir, args.provider_uri, portfolio_outputs["results"], portfolio_outputs["daily"])
    wf_outputs = run_v6_walk_forward(wf_dir, args.provider_uri, portfolio_outputs["results"], max_strategies=5)
    overfit_outputs = run_v6_overfit_checks(
        overfit_dir,
        args.provider_uri,
        portfolio_outputs["results"],
        portfolio_outputs["daily"],
        portfolio_outputs["holdings"],
    )
    build_v6_report(
        artifacts.reports_dir / "us_stock_selection_v6_local_qlib_workflow_report.md",
        source_status,
        provider_status,
        workflow_outputs,
        portfolio_outputs,
        benchmark,
        wf_outputs,
        overfit_outputs,
    )
    build_v6_excel(
        artifacts.reports_dir / "us_stock_selection_v6_summary.xlsx",
        {
            "source_status": pd.DataFrame([source_status]),
            "provider_health": pd.DataFrame([provider_status.get("provider_health", {})]),
            "alpha_handler": pd.DataFrame(provider_status.get("alpha_handler_check", {})).T.reset_index(),
            "model_runs": workflow_outputs.get("model_runs", pd.DataFrame()),
            "signal_quality": workflow_outputs.get("signal_quality", pd.DataFrame()),
            "ic_by_year": workflow_outputs.get("ic_by_year", pd.DataFrame()),
            "robust_results": portfolio_outputs.get("results", pd.DataFrame()),
            "benchmark": benchmark,
            "concentration": portfolio_outputs.get("concentration", pd.DataFrame()),
            "yearly_returns": portfolio_outputs.get("yearly", pd.DataFrame()),
            "cost_sensitivity": portfolio_outputs.get("cost_sensitivity", pd.DataFrame()),
            "wf_detail": wf_outputs.get("detail", pd.DataFrame()),
            "wf_summary": wf_outputs.get("summary", pd.DataFrame()),
            "overfit_summary": overfit_outputs.get("summary", pd.DataFrame()),
            "leave_one_ticker": overfit_outputs.get("leave_one_ticker", pd.DataFrame()),
            "leave_one_year": overfit_outputs.get("leave_one_year", pd.DataFrame()),
        },
    )
    zip_path = package_v6_run(artifacts.run_dir, artifacts.timestamp)
    best = portfolio_outputs["results"].head(1).to_dict(orient="records")
    print(
        {
            "run_dir": str(artifacts.run_dir),
            "zip_path": str(zip_path),
            "local_provider_success": provider_status.get("local_provider_success"),
            "workflow_completed": int((workflow_outputs.get("model_runs", pd.DataFrame()).get("status", pd.Series(dtype=str)) == "completed").sum()),
            "robust_results": len(portfolio_outputs["results"]),
            "classification": overfit_outputs.get("verdict", {}).get("classification"),
            "best": best[0] if best else {},
        }
    )


if __name__ == "__main__":
    main()
