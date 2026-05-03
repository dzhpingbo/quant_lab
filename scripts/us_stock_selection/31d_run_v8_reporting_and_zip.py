"""Rebuild v8 reports and zip from existing stage outputs only."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from quant_lab.us_stock_selection.utils import ensure_dir, make_logger, save_json, save_text
from quant_lab.us_stock_selection.v8_reporting import build_v8_excel, build_v8_report, classify_v8, package_v8_run


DEFAULT_RUN = PROJECT_ROOT / "outputs" / "us_stock_selection" / "run_20260426_095958"


def _read_csv(path: Path, required: bool = True) -> pd.DataFrame:
    if not path.exists():
        if required:
            raise FileNotFoundError(path)
        return pd.DataFrame()
    return pd.read_csv(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run v8 stage 31d: reporting and zip from existing files.")
    parser.add_argument("--run-dir", default=str(DEFAULT_RUN), help="Existing v8 run directory to read.")
    parser.add_argument("--timestamp", default="", help="Zip timestamp override; defaults to run dir suffix.")
    parser.add_argument("--no-zip", action="store_true", help="Rebuild reports but skip packaging.")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    logs_dir = ensure_dir(run_dir / "logs")
    reports_dir = ensure_dir(run_dir / "reports")
    logger = make_logger(logs_dir / "31d_reporting_and_zip.log", level="INFO")
    timestamp = args.timestamp or run_dir.name.replace("run_", "")
    logger.info(f"Reading existing v8 outputs from {run_dir}; no core backtests will be recomputed.")

    # This stage intentionally reads previous CSV outputs only. Missing required
    # inputs stop the stage instead of silently rebuilding research results.
    paper_metrics = _read_csv(run_dir / "v8_paper_trading" / "paper_trading_metrics.csv")
    decision_ledger = _read_csv(run_dir / "v8_paper_trading" / "monthly_decision_ledger.csv")
    monthly_holdings = _read_csv(run_dir / "v8_paper_trading" / "monthly_holdings.csv")
    trades = _read_csv(run_dir / "v8_paper_trading" / "trades.csv")
    convergence = _read_csv(run_dir / "v8_model_stability" / "elasticnet_convergence_check.csv")
    challengers = _read_csv(run_dir / "v8_model_stability" / "challenger_model_results.csv")
    stress = _read_csv(run_dir / "v8_execution_sim" / "execution_stress_results.csv")
    attribution = {
        "holding_concentration": _read_csv(run_dir / "v8_attribution" / "holding_concentration.csv", required=False),
        "ticker_contribution": _read_csv(run_dir / "v8_attribution" / "ticker_contribution.csv"),
        "yearly": _read_csv(run_dir / "v8_attribution" / "yearly_return.csv"),
        "monthly": _read_csv(run_dir / "v8_attribution" / "monthly_return.csv"),
        "top_months": _read_csv(run_dir / "v8_attribution" / "top_return_months.csv", required=False),
    }
    paper_metrics_dict = paper_metrics.iloc[0].to_dict() if not paper_metrics.empty else {}
    verdict = classify_v8(paper_metrics_dict, convergence, challengers, stress, attribution)
    save_json(verdict, run_dir / "v8_verdict.json")
    save_json(verdict, run_dir / "v8_execution_sim" / "v8_verdict.json")
    build_v8_report(
        reports_dir / "us_stock_selection_v8_paper_trading_report.md",
        paper_metrics,
        convergence,
        challengers,
        stress,
        attribution,
        verdict,
    )
    build_v8_excel(
        reports_dir / "us_stock_selection_v8_summary.xlsx",
        {
            "paper_metrics": paper_metrics,
            "decision_ledger": decision_ledger,
            "monthly_holdings": monthly_holdings,
            "trades": trades,
            "elasticnet_convergence": convergence,
            "challenger_models": challengers,
            "execution_stress": stress,
            "ticker_contribution": attribution["ticker_contribution"],
            "yearly_return": attribution["yearly"],
            "monthly_return": attribution["monthly"],
            "verdict": pd.DataFrame([verdict]),
        },
    )
    save_text(
        "\n".join(
            [
                "# v8 reporting stage",
                "",
                f"run_dir: `{run_dir}`",
                f"classification: `{verdict.get('classification')}`",
                f"allow_enter_v9: `{verdict.get('allow_enter_v9')}`",
                "",
                "This stage rebuilt reports by reading existing CSV outputs only.",
                "",
            ]
        ),
        run_dir / "STAGE_31D_REPORTING_AND_ZIP.md",
    )
    zip_path = "" if args.no_zip else str(package_v8_run(run_dir, timestamp))
    if zip_path:
        logger.info(f"Packaged v8 zip {zip_path}")
    logger.info("Completed stage 31d reporting and zip.")
    print({"run_dir": str(run_dir), "stage": "31d", "classification": verdict.get("classification"), "zip_path": zip_path})


if __name__ == "__main__":
    main()
