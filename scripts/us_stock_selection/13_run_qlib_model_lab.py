"""Run the v4 Qlib-first model lab stage."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from quant_lab.us_stock_selection import USStockSelectionPipeline


def main():
    parser = argparse.ArgumentParser(description="Run v4 Qlib model lab.")
    parser.add_argument("--config", default="configs/us_stock_selection/validation_config.yaml")
    args = parser.parse_args()
    pipeline = USStockSelectionPipeline(args.config)
    pipeline.prepare_run()
    pipeline.run_qlib_env_check_stage()
    pipeline.run_universe_stage()
    pipeline.run_feature_stage()
    pipeline.run_qlib_data_stage_v4()
    pipeline.run_qlib_model_lab_stage()
    print({"run_dir": str(pipeline.artifacts.run_dir), "model_rows": len(pipeline.qlib_model_metrics_df)})


if __name__ == "__main__":
    main()
