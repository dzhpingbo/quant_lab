"""Run the full US stock selection research pipeline."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from quant_lab.us_stock_selection import USStockSelectionPipeline


def main():
    parser = argparse.ArgumentParser(description="Run the full US stock selection pipeline.")
    parser.add_argument(
        "--config",
        default="configs/us_stock_selection/validation_config.yaml",
        help="Validation config path.",
    )
    args = parser.parse_args()

    pipeline = USStockSelectionPipeline(args.config)
    result = pipeline.run_all()
    print(result)


if __name__ == "__main__":
    main()
