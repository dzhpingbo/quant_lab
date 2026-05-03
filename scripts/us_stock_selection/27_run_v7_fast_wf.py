"""Run v7 feature-cache fast walk-forward end to end."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from quant_lab.us_stock_selection.fast_walk_forward import run_fast_walk_forward
from quant_lab.us_stock_selection.feature_cache import build_feature_cache
from quant_lab.us_stock_selection.local_qlib_provider_builder import default_local_provider_uri
from quant_lab.us_stock_selection.utils import (
    PROJECT_ROOT as ROOT,
    create_run_artifacts,
    load_yaml,
    make_logger,
    merge_many_dicts,
    save_yaml,
)
from quant_lab.us_stock_selection.v7_reporting import (
    build_run_summary,
    build_v7_excel,
    build_v7_report,
    package_v7_run,
    update_next_steps,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run v7 fast walk-forward.")
    parser.add_argument("--config", default="configs/us_stock_selection/validation_config.yaml")
    parser.add_argument("--provider-uri", default=str(default_local_provider_uri()))
    parser.add_argument("--feature-sets", default="Alpha158,Alpha360")
    parser.add_argument("--models", default="LightGBM,Ridge,ElasticNet")
    parser.add_argument("--labels", default="label_5d,label_20d")
    parser.add_argument("--wf-modes", default="anchored,rolling_2y_6m,rolling_3y_1y")
    parser.add_argument("--overwrite-cache", action="store_true")
    parser.add_argument("--no-resume", action="store_true")
    args = parser.parse_args()

    config = merge_many_dicts(load_yaml("configs/us_stock_selection/factor_groups.yaml"), load_yaml(args.config))
    artifacts = create_run_artifacts(ROOT / config.get("paths", {}).get("output_root", "outputs/us_stock_selection"))
    logger = make_logger(artifacts.logs_dir / "run.log", level=str(config.get("logging", {}).get("level", "INFO")))
    logger.info(f"Prepared v7 run {artifacts.run_dir}")
    save_yaml(config, artifacts.run_dir / "run_config.yaml")

    v7_cache_dir = artifacts.run_dir / "v7_feature_cache"
    v7_wf_dir = artifacts.run_dir / "v7_fast_walk_forward"
    v7_reports_dir = artifacts.run_dir / "v7_reports"
    for path in [v7_cache_dir, v7_wf_dir, v7_reports_dir]:
        path.mkdir(parents=True, exist_ok=True)

    feature_sets = [x.strip() for x in args.feature_sets.split(",") if x.strip()]
    models = [x.strip() for x in args.models.split(",") if x.strip()]
    labels = [x.strip() for x in args.labels.split(",") if x.strip()]
    wf_modes = [x.strip() for x in args.wf_modes.split(",") if x.strip()]

    cache_outputs = build_feature_cache(v7_cache_dir, provider_uri=args.provider_uri, feature_sets=feature_sets, overwrite=args.overwrite_cache)
    wf_outputs = run_fast_walk_forward(
        v7_wf_dir,
        cache_dir=v7_cache_dir,
        provider_uri=args.provider_uri,
        feature_sets=feature_sets,
        models=models,
        labels=labels,
        wf_modes=wf_modes,
        resume=not args.no_resume,
    )

    cache_status = cache_outputs["status"]
    wf_detail = wf_outputs["detail"]
    wf_summary = wf_outputs["summary"]
    conservative_summary = wf_outputs.get("conservative_summary", pd.DataFrame())
    assessment = wf_outputs["assessment"]
    build_v7_report(artifacts.reports_dir / "us_stock_selection_v7_fast_wf_report.md", cache_status, wf_detail, wf_summary, assessment)
    build_v7_report(v7_reports_dir / "us_stock_selection_v7_fast_wf_report.md", cache_status, wf_detail, wf_summary, assessment)
    build_v7_excel(
        artifacts.reports_dir / "us_stock_selection_v7_summary.xlsx",
        {
            "feature_cache": cache_status,
            "wf_summary": wf_summary,
            "conservative_summary": conservative_summary,
            "wf_detail": wf_detail,
            "assessment": pd.DataFrame([assessment]),
            "best": pd.DataFrame([assessment.get("best", {})]),
        },
    )
    build_v7_excel(
        v7_reports_dir / "us_stock_selection_v7_summary.xlsx",
        {
            "feature_cache": cache_status,
            "wf_summary": wf_summary,
            "conservative_summary": conservative_summary,
            "wf_detail": wf_detail,
            "assessment": pd.DataFrame([assessment]),
            "best": pd.DataFrame([assessment.get("best", {})]),
        },
    )
    run_summary = build_run_summary(artifacts.run_dir / "RUN_SUMMARY.md", artifacts.run_dir, "", assessment)
    root_summary = build_run_summary(ROOT / "RUN_SUMMARY.md", artifacts.run_dir, "", assessment)
    update_next_steps(ROOT / "NEXT_STEPS.md", assessment)
    zip_path = package_v7_run(artifacts.run_dir, artifacts.timestamp)
    build_run_summary(artifacts.run_dir / "RUN_SUMMARY.md", artifacts.run_dir, zip_path, assessment)
    build_run_summary(ROOT / "RUN_SUMMARY.md", artifacts.run_dir, zip_path, assessment)
    zip_path = package_v7_run(artifacts.run_dir, artifacts.timestamp)
    print(
        {
            "run_dir": str(artifacts.run_dir),
            "zip_path": str(zip_path),
            "feature_cache_rows": len(cache_status),
            "wf_detail_rows": len(wf_detail),
            "wf_summary_rows": len(wf_summary),
            "classification": assessment.get("classification"),
            "strict_walk_forward_passed": assessment.get("strict_walk_forward_passed"),
            "best": assessment.get("best", {}),
        }
    )


if __name__ == "__main__":
    main()
