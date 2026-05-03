"""Backtest robust Top3/Top5 portfolios from Qlib predictions."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from scripts.us_stock_selection._bootstrap import PROJECT_ROOT  # noqa: F401

from quant_lab.us_stock_selection.local_qlib_provider_builder import default_local_provider_uri
from quant_lab.us_stock_selection.portfolio_robustifier import build_benchmark_comparison_v6, run_robust_portfolio_backtests


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest robust v6 portfolios.")
    parser.add_argument("--run-dir", default="outputs/us_stock_selection/manual_v6_workflow")
    parser.add_argument("--provider-uri", default=str(default_local_provider_uri()))
    args = parser.parse_args()
    run_dir = Path(args.run_dir)
    pred_index_path = run_dir / "qlib_workflow" / "predictions" / "prediction_index.csv"
    pred_index = pd.read_csv(pred_index_path) if pred_index_path.exists() else pd.DataFrame()
    outputs = run_robust_portfolio_backtests(run_dir / "v6_portfolio_backtest", args.provider_uri, pred_index)
    comp = build_benchmark_comparison_v6(run_dir / "benchmark", args.provider_uri, outputs["results"], outputs["daily"])
    print({"robust_results": len(outputs["results"]), "benchmark_rows": len(comp)})


if __name__ == "__main__":
    main()
