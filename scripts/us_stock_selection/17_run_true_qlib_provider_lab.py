"""Run Alpha158/Alpha360 models on a true Qlib US provider."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from quant_lab.us_stock_selection.true_qlib_provider import run_true_provider_lab


def main():
    parser = argparse.ArgumentParser(description="Run true Qlib provider lab.")
    parser.add_argument("--provider-uri", default="~/.qlib/qlib_data/us_data")
    parser.add_argument("--output-dir", default="outputs/us_stock_selection/qlib_true_provider_lab")
    parser.add_argument("--max-model-runs", type=int, default=36)
    parser.add_argument("--feature-sets", default="Alpha158,Alpha360,Alpha158_custom")
    parser.add_argument("--models", default="Ridge,LightGBM")
    parser.add_argument("--labels", default="forward_return_5d,forward_return_20d")
    args = parser.parse_args()
    outputs = run_true_provider_lab(
        args.output_dir,
        provider_uri=args.provider_uri,
        max_model_runs=args.max_model_runs,
        feature_sets=[item.strip() for item in args.feature_sets.split(",") if item.strip()],
        model_names=[item.strip() for item in args.models.split(",") if item.strip()],
        labels=[item.strip() for item in args.labels.split(",") if item.strip()],
    )
    print({key: len(value) for key, value in outputs.items()})


if __name__ == "__main__":
    main()
