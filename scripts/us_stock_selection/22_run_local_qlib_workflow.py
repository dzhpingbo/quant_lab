"""Run local-provider Qlib Handler workflows."""

from __future__ import annotations

import argparse
from pathlib import Path

from scripts.us_stock_selection._bootstrap import PROJECT_ROOT  # noqa: F401

from quant_lab.us_stock_selection.local_qlib_provider_builder import default_local_provider_uri
from quant_lab.us_stock_selection.qlib_workflow_runner import run_local_qlib_workflows


def main() -> None:
    parser = argparse.ArgumentParser(description="Run local Qlib workflow.")
    parser.add_argument("--run-dir", default="outputs/us_stock_selection/manual_v6_workflow")
    parser.add_argument("--provider-uri", default=str(default_local_provider_uri()))
    parser.add_argument("--feature-sets", default="Alpha158,Alpha360")
    parser.add_argument("--models", default="LGBModel,Ridge,ElasticNet")
    parser.add_argument("--labels", default="label_5d,label_20d")
    parser.add_argument("--max-runs", type=int, default=12)
    parser.add_argument("--no-qrun", action="store_true")
    args = parser.parse_args()
    outputs = run_local_qlib_workflows(
        Path(args.run_dir) / "qlib_workflow",
        provider_uri=args.provider_uri,
        feature_sets=[x.strip() for x in args.feature_sets.split(",") if x.strip()],
        models=[x.strip() for x in args.models.split(",") if x.strip()],
        labels=[x.strip() for x in args.labels.split(",") if x.strip()],
        max_runs=args.max_runs,
        attempt_qrun=not args.no_qrun,
    )
    print({"model_runs": len(outputs["model_runs"]), "predictions": len(outputs["predictions_index"])})


if __name__ == "__main__":
    main()
