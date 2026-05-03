"""Prepare/check Qlib US data or export the local qlib-like panel fallback."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from quant_lab.us_stock_selection import USStockSelectionPipeline


def main():
    parser = argparse.ArgumentParser(description="Prepare v4 Qlib US data stage.")
    parser.add_argument("--config", default="configs/us_stock_selection/validation_config.yaml")
    args = parser.parse_args()
    pipeline = USStockSelectionPipeline(args.config)
    pipeline.prepare_run()
    pipeline.run_qlib_env_check_stage()
    pipeline.run_universe_stage()
    pipeline.run_feature_stage()
    pipeline.run_qlib_data_stage_v4()
    print({"run_dir": str(pipeline.artifacts.run_dir), "qlib_data_status": pipeline.qlib_data_status})


if __name__ == "__main__":
    main()
