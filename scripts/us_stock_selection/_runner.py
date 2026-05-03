"""Shared runner for stage-specific entry points."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from quant_lab.us_stock_selection import USStockSelectionPipeline


def build_parser(description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--config",
        default="configs/us_stock_selection/validation_config.yaml",
        help="Pipeline config path.",
    )
    return parser


def run_stage(stage_name: str, description: str):
    parser = build_parser(description)
    args = parser.parse_args()
    pipeline = USStockSelectionPipeline(args.config)
    pipeline.prepare_run()
    method = getattr(pipeline, stage_name)
    method()
    if stage_name != "run_reporting_stage":
        pipeline.run_reporting_stage()
