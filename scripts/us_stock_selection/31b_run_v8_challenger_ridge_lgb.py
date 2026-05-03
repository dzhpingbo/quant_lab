"""Run only the v8 Ridge and LightGBM challenger stage."""

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
    save_dataframe,
    save_text,
    save_yaml,
)
from quant_lab.us_stock_selection.v8_paper_trading import ModelSpec, run_paper_trading_replay


DEFAULT_SOURCE_RUN = ROOT / "outputs" / "us_stock_selection" / "run_20260426_060824"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run v8 stage 31b: Ridge/LGB challenger checks.")
    parser.add_argument("--config", default="configs/us_stock_selection/validation_config.yaml")
    parser.add_argument("--provider-uri", default=str(default_local_provider_uri()))
    parser.add_argument("--source-run", default=str(DEFAULT_SOURCE_RUN))
    parser.add_argument("--run-dir", default="", help="Existing run dir to reuse; empty creates a new run.")
    parser.add_argument("--dry-run-init", action="store_true", help="Create directories and stop before challenger fits.")
    args = parser.parse_args()

    config = merge_many_dicts(load_yaml("configs/us_stock_selection/factor_groups.yaml"), load_yaml(args.config))
    output_root = ROOT / config.get("paths", {}).get("output_root", "outputs/us_stock_selection")
    if args.run_dir:
        run_dir = ensure_dir(args.run_dir)
        logs_dir = ensure_dir(run_dir / "logs")
        timestamp = run_dir.name.replace("run_", "")
    else:
        artifacts = create_run_artifacts(output_root)
        run_dir = artifacts.run_dir
        logs_dir = artifacts.logs_dir
        timestamp = artifacts.timestamp

    logger = make_logger(logs_dir / "31b_challenger_ridge_lgb.log", level=str(config.get("logging", {}).get("level", "INFO")))
    save_yaml(config, run_dir / "run_config.yaml")
    cache_dir = ensure_dir(run_dir / "v7_feature_cache")
    model_dir = ensure_dir(run_dir / "v8_model_stability")
    save_text(
        "Stage 31b writes challenger_model_results.csv for Ridge and LGBModel only.\n",
        run_dir / "STAGE_31B_CHALLENGER_RIDGE_LGB.md",
    )
    logger.info(f"Prepared v8 stage 31b run_dir={run_dir} timestamp={timestamp}")

    if args.dry_run_init:
        # Operational self-check: stop before cache copy and challenger model fits.
        logger.info("Dry-run init requested; stopping before cache copy and challenger fits.")
        print({"run_dir": str(run_dir), "stage": "31b", "dry_run_init": True})
        return

    source_cache = Path(args.source_run) / "v7_feature_cache"
    fallback = ROOT / "outputs" / "us_stock_selection" / "run_20260426_035045" / "v7_feature_cache"
    shutil.copytree(source_cache if source_cache.exists() else fallback, cache_dir, dirs_exist_ok=True)
    specs = [
        ModelSpec("Ridge", feature_set="Alpha360", label="label_5d", params={"alpha": 1.0}),
        ModelSpec("LGBModel", feature_set="Alpha360", label="label_5d", params={"n_estimators": 80}),
    ]
    rows: list[dict] = []
    for spec in specs:
        tag = f"{spec.feature_set}_{spec.name}"
        logger.info(f"Running challenger {tag}")
        result = run_paper_trading_replay(model_dir / tag, cache_dir=cache_dir, provider_uri=args.provider_uri, model_spec=spec, save_outputs=False)
        conv = result["convergence"]
        rows.append(
            {
                "run_id": tag,
                "feature_set": spec.feature_set,
                "model": spec.name,
                "label": spec.label,
                "decision_count": int(len(result["decisions"])),
                "warning_count": int(conv["fit_warning_count"].sum()) if not conv.empty else 0,
                **result["metrics"],
            }
        )
    challengers = pd.DataFrame(rows).sort_values(["calmar", "cagr"], ascending=[False, False])
    save_dataframe(challengers, model_dir / "challenger_model_results.csv")
    logger.info("Completed stage 31b challenger checks.")
    print({"run_dir": str(run_dir), "stage": "31b", "status": "completed", "rows": int(len(challengers))})


if __name__ == "__main__":
    main()
