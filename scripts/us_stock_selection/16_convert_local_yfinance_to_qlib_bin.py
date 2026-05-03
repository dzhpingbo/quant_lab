"""Export local quant_lab US OHLCV data into CSV inputs for qlib dump_bin."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from quant_lab.us_stock_selection.qlib_data_converter import prepare_local_qlib_dump_inputs
from quant_lab.us_stock_selection.utils import load_env_config, load_yaml, merge_many_dicts


def main():
    parser = argparse.ArgumentParser(description="Prepare local CSV files for qlib dump_bin conversion.")
    parser.add_argument("--config", default="configs/us_stock_selection/validation_config.yaml")
    parser.add_argument("--output-dir", default="outputs/us_stock_selection/qlib_data_true_provider/local_conversion")
    args = parser.parse_args()
    config = merge_many_dicts(load_yaml("configs/us_stock_selection/factor_groups.yaml"), load_yaml(args.config))
    status = prepare_local_qlib_dump_inputs(args.output_dir, config, load_env_config())
    print(status)


if __name__ == "__main__":
    main()
