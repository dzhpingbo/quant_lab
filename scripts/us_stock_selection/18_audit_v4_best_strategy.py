"""Audit the v4 best fallback strategy for leakage, concentration, WF, and stress."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from quant_lab.us_stock_selection.utils import load_yaml, merge_many_dicts
from quant_lab.us_stock_selection.v4_audit import audit_v4_best_strategy


def main():
    parser = argparse.ArgumentParser(description="Audit v4 best strategy.")
    parser.add_argument("--v4-run-dir", default="outputs/us_stock_selection/run_20260425_114504")
    parser.add_argument("--output-dir", default="outputs/us_stock_selection/v5_audit_standalone")
    parser.add_argument("--config", default="configs/us_stock_selection/validation_config.yaml")
    args = parser.parse_args()
    config = merge_many_dicts(load_yaml("configs/us_stock_selection/factor_groups.yaml"), load_yaml(args.config))
    outputs = audit_v4_best_strategy(args.v4_run_dir, args.output_dir, config)
    print(outputs["summary"])


if __name__ == "__main__":
    main()
