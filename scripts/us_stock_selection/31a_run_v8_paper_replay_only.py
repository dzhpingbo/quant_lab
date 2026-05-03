"""Run only the v8 frozen-candidate paper replay stage."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

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
    save_text,
    save_yaml,
)
from quant_lab.us_stock_selection.v8_paper_trading import frozen_model_spec, run_paper_trading_replay


DEFAULT_SOURCE_RUN = ROOT / "outputs" / "us_stock_selection" / "run_20260426_060824"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run v8 stage 31a: paper replay only.")
    parser.add_argument("--config", default="configs/us_stock_selection/validation_config.yaml")
    parser.add_argument("--provider-uri", default=str(default_local_provider_uri()))
    parser.add_argument("--source-run", default=str(DEFAULT_SOURCE_RUN))
    parser.add_argument("--run-dir", default="", help="Existing run dir to reuse; empty creates a new run.")
    parser.add_argument("--dry-run-init", action="store_true", help="Create directories and stop before paper replay.")
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

    logger = make_logger(logs_dir / "31a_paper_replay_only.log", level=str(config.get("logging", {}).get("level", "INFO")))
    save_yaml(config, run_dir / "run_config.yaml")
    cache_dir = ensure_dir(run_dir / "v7_feature_cache")
    paper_dir = ensure_dir(run_dir / "v8_paper_trading")
    save_text(
        "Stage 31a writes the frozen Alpha360 ElasticNet Top5 monthly paper replay outputs only.\n",
        run_dir / "STAGE_31A_PAPER_REPLAY_ONLY.md",
    )
    logger.info(f"Prepared v8 stage 31a run_dir={run_dir} timestamp={timestamp}")

    if args.dry_run_init:
        # Operational self-check: stop before cache copy and model fitting.
        logger.info("Dry-run init requested; stopping before cache copy and run_paper_trading_replay.")
        print({"run_dir": str(run_dir), "stage": "31a", "dry_run_init": True})
        return

    source_cache = Path(args.source_run) / "v7_feature_cache"
    fallback = ROOT / "outputs" / "us_stock_selection" / "run_20260426_035045" / "v7_feature_cache"
    shutil.copytree(source_cache if source_cache.exists() else fallback, cache_dir, dirs_exist_ok=True)
    logger.info("Running frozen Alpha360 ElasticNet Top5 monthly paper replay only.")
    result = run_paper_trading_replay(
        paper_dir,
        cache_dir=cache_dir,
        provider_uri=args.provider_uri,
        model_spec=frozen_model_spec(),
        execution_delay=1,
        cost_bps=5.0,
        slippage_bps=5.0,
        max_weight=0.20,
        rebalance_timing="month_end",
        save_outputs=True,
    )
    logger.info(f"Completed stage 31a paper replay with metrics={result['metrics']}")
    print({"run_dir": str(run_dir), "stage": "31a", "status": "completed", **result["metrics"]})


if __name__ == "__main__":
    main()
