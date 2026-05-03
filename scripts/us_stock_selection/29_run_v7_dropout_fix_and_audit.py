"""Run v7 after strict TopKDropout fix, then audit the result.

This is the autorun entrypoint for the post-v7-audit repair loop. It reuses the
existing Alpha360 cache when available, retrains WF models from parquet, runs the
reverse audit, and packages one combined run.
"""

from __future__ import annotations

import argparse
import shutil
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
    ensure_dir,
    load_yaml,
    make_logger,
    merge_many_dicts,
    save_yaml,
    zip_selected_paths,
)
from quant_lab.us_stock_selection.v7_audit import package_v7_audit_run, run_v7_audit
from quant_lab.us_stock_selection.v7_reporting import build_run_summary, build_v7_excel, build_v7_report, package_v7_run


DEFAULT_SOURCE_CACHE_RUN = ROOT / "outputs" / "us_stock_selection" / "run_20260425_214159"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run v7 strict dropout fix and v7 audit.")
    parser.add_argument("--config", default="configs/us_stock_selection/validation_config.yaml")
    parser.add_argument("--provider-uri", default=str(default_local_provider_uri()))
    parser.add_argument("--source-cache-run", default=str(DEFAULT_SOURCE_CACHE_RUN))
    parser.add_argument("--feature-sets", default="Alpha360")
    parser.add_argument("--models", default="ElasticNet")
    parser.add_argument("--labels", default="label_5d")
    parser.add_argument("--wf-modes", default="anchored,rolling_2y_6m,rolling_3y_1y")
    parser.add_argument("--rebuild-cache", action="store_true")
    args = parser.parse_args()

    config = merge_many_dicts(load_yaml("configs/us_stock_selection/factor_groups.yaml"), load_yaml(args.config))
    artifacts = create_run_artifacts(ROOT / config.get("paths", {}).get("output_root", "outputs/us_stock_selection"))
    logger = make_logger(artifacts.logs_dir / "run.log", level=str(config.get("logging", {}).get("level", "INFO")))
    logger.info(f"Prepared v7 dropout fix run {artifacts.run_dir}")
    save_yaml(config, artifacts.run_dir / "run_config.yaml")

    v7_cache_dir = ensure_dir(artifacts.run_dir / "v7_feature_cache")
    v7_wf_dir = ensure_dir(artifacts.run_dir / "v7_fast_walk_forward")
    v7_reports_dir = ensure_dir(artifacts.run_dir / "v7_reports")

    feature_sets = [x.strip() for x in args.feature_sets.split(",") if x.strip()]
    models = [x.strip() for x in args.models.split(",") if x.strip()]
    labels = [x.strip() for x in args.labels.split(",") if x.strip()]
    wf_modes = [x.strip() for x in args.wf_modes.split(",") if x.strip()]

    cache_status = pd.DataFrame()
    source_cache = Path(args.source_cache_run) / "v7_feature_cache"
    if source_cache.exists() and not args.rebuild_cache:
        logger.info(f"Reusing source feature cache {source_cache}")
        shutil.copytree(source_cache, v7_cache_dir, dirs_exist_ok=True)
        status_path = v7_cache_dir / "feature_cache_status.csv"
        cache_status = pd.read_csv(status_path) if status_path.exists() else pd.DataFrame()
        if not cache_status.empty:
            cache_status = cache_status.loc[cache_status["feature_set"].isin(feature_sets)].copy()
    if cache_status.empty:
        logger.info("Building feature cache because no reusable cache status was found")
        cache_outputs = build_feature_cache(v7_cache_dir, provider_uri=args.provider_uri, feature_sets=feature_sets, overwrite=args.rebuild_cache)
        cache_status = cache_outputs["status"]

    wf_outputs = run_fast_walk_forward(
        v7_wf_dir,
        cache_dir=v7_cache_dir,
        provider_uri=args.provider_uri,
        feature_sets=feature_sets,
        models=models,
        labels=labels,
        wf_modes=wf_modes,
        resume=False,
    )
    wf_detail = wf_outputs["detail"]
    wf_summary = wf_outputs["summary"]
    conservative_summary = wf_outputs.get("conservative_summary", pd.DataFrame())
    assessment = wf_outputs["assessment"]

    build_v7_report(artifacts.reports_dir / "us_stock_selection_v7_dropout_fix_report.md", cache_status, wf_detail, wf_summary, assessment)
    build_v7_report(v7_reports_dir / "us_stock_selection_v7_dropout_fix_report.md", cache_status, wf_detail, wf_summary, assessment)
    build_v7_excel(
        artifacts.reports_dir / "us_stock_selection_v7_dropout_fix_summary.xlsx",
        {
            "feature_cache": cache_status,
            "wf_summary": wf_summary,
            "conservative_summary": conservative_summary,
            "wf_detail": wf_detail,
            "assessment": pd.DataFrame([assessment]),
            "best": pd.DataFrame([assessment.get("best", {})]),
        },
    )
    build_run_summary(artifacts.run_dir / "RUN_SUMMARY.md", artifacts.run_dir, "", assessment)

    audit_outputs = run_v7_audit(
        source_run_dir=artifacts.run_dir,
        audit_run_dir=artifacts.run_dir,
        provider_uri=args.provider_uri,
    )
    audit_verdict = audit_outputs["classification"]
    v7_zip = package_v7_run(artifacts.run_dir, artifacts.timestamp)
    audit_zip = package_v7_audit_run(artifacts.run_dir, artifacts.timestamp)
    combined_zip = package_combined_run(artifacts.run_dir, artifacts.timestamp)
    build_run_summary(artifacts.run_dir / "RUN_SUMMARY.md", artifacts.run_dir, combined_zip, assessment)
    build_run_summary(ROOT / "RUN_SUMMARY.md", artifacts.run_dir, combined_zip, assessment)
    logger.info(f"Packaged v7 zip {v7_zip}")
    logger.info(f"Packaged audit zip {audit_zip}")
    logger.info(f"Packaged combined zip {combined_zip}")
    print(
        {
            "run_dir": str(artifacts.run_dir),
            "combined_zip": str(combined_zip),
            "v7_zip": str(v7_zip),
            "audit_zip": str(audit_zip),
            "wf_classification": assessment.get("classification"),
            "audit_classification": audit_verdict.get("classification"),
            "allow_enter_v8": audit_verdict.get("allow_enter_v8"),
            "wf_best": assessment.get("best", {}),
            "audit_reason": audit_verdict.get("reason"),
        }
    )


def package_combined_run(run_dir: Path | str, timestamp: str) -> Path:
    base = Path(run_dir).resolve()
    zip_path = base.parent / f"us_stock_selection_quant_lab_v7_dropout_fix_audit_{timestamp}.zip"
    paths = [
        ROOT / "AGENTS.md",
        ROOT / "NEXT_STEPS.md",
        ROOT / "RUN_SUMMARY.md",
        ROOT / "docs" / "US_STOCK_SELECTION_AUTORUN.md",
        ROOT / "configs" / "us_stock_selection",
        ROOT / "scripts" / "us_stock_selection",
        ROOT / "quant_lab" / "us_stock_selection",
        ROOT / "README_US_STOCK_SELECTION.md",
        base / "v7_feature_cache",
        base / "v7_fast_walk_forward",
        base / "v7_audit",
        base / "v7_reports",
        base / "reports",
        base / "logs",
        base / "RUN_SUMMARY.md",
    ]
    return zip_selected_paths(paths, zip_path, root=ROOT)


if __name__ == "__main__":
    main()
