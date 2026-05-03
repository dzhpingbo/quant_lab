"""Run v7 fast strict walk-forward from feature cache."""

from __future__ import annotations

import argparse
from pathlib import Path

from scripts.us_stock_selection._bootstrap import PROJECT_ROOT  # noqa: F401

from quant_lab.us_stock_selection.fast_walk_forward import run_fast_walk_forward
from quant_lab.us_stock_selection.local_qlib_provider_builder import default_local_provider_uri


def main() -> None:
    parser = argparse.ArgumentParser(description="Run v7 fast walk-forward.")
    parser.add_argument("--run-dir", default="outputs/us_stock_selection/manual_v7")
    parser.add_argument("--provider-uri", default=str(default_local_provider_uri()))
    parser.add_argument("--feature-sets", default="Alpha158,Alpha360")
    parser.add_argument("--models", default="LightGBM,Ridge,ElasticNet")
    parser.add_argument("--labels", default="label_5d,label_20d")
    parser.add_argument("--wf-modes", default="anchored,rolling_2y_6m,rolling_3y_1y")
    parser.add_argument("--no-resume", action="store_true")
    args = parser.parse_args()
    run_dir = Path(args.run_dir)
    outputs = run_fast_walk_forward(
        run_dir / "v7_fast_walk_forward",
        cache_dir=run_dir / "v7_feature_cache",
        provider_uri=args.provider_uri,
        feature_sets=[x.strip() for x in args.feature_sets.split(",") if x.strip()],
        models=[x.strip() for x in args.models.split(",") if x.strip()],
        labels=[x.strip() for x in args.labels.split(",") if x.strip()],
        wf_modes=[x.strip() for x in args.wf_modes.split(",") if x.strip()],
        resume=not args.no_resume,
    )
    print(outputs["assessment"])


if __name__ == "__main__":
    main()
