"""Generate current-position template CSV files for daily trading packets.

The script writes only ``*.template.csv`` files. It never writes real
``current_positions_*.csv`` files, reads broker accounts, connects brokers,
submits orders, searches strategies, or changes frozen strategy logic.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = ROOT / "outputs" / "daily_quant_lab_runs"
INPUTS_DIR = ROOT / "inputs"


DEFAULT_ROWS = {
    "current_positions_us_v82.template.csv": ["MSTR", "INTC", "NOW", "PLTR", "TQQQ"],
    "current_positions_qldtqqq.template.csv": ["QLD", "TQQQ"],
    "current_positions_588200.template.csv": ["588200"],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create current-position template CSV files.")
    parser.add_argument("--run-dir", default="", help="Optional daily run directory whose target holdings should seed templates.")
    parser.add_argument("--latest", action="store_true", help="Use the latest daily run with all_target_holdings.csv.")
    return parser.parse_args()


def latest_run_dir() -> Path | None:
    candidates = sorted(
        [path for path in OUTPUT_ROOT.glob("20*") if path.is_dir() and (path / "all_target_holdings.csv").exists()],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def tickers_from_run(run_dir: Path) -> dict[str, list[str]]:
    holdings_path = run_dir / "all_target_holdings.csv"
    if not holdings_path.exists():
        return {}
    data = pd.read_csv(holdings_path)
    out: dict[str, list[str]] = {}
    if "job_id" not in data.columns or "ticker" not in data.columns:
        return out
    us = sorted(data.loc[data["job_id"].astype(str).eq("us_v82"), "ticker"].dropna().astype(str).str.upper().unique().tolist())
    q = sorted(data.loc[data["job_id"].astype(str).eq("qld_tqqq"), "ticker"].dropna().astype(str).str.upper().unique().tolist())
    etf = sorted(data.loc[data["job_id"].astype(str).eq("588200"), "ticker"].dropna().astype(str).str.upper().unique().tolist())
    if us:
        out["current_positions_us_v82.template.csv"] = us
    if q:
        out["current_positions_qldtqqq.template.csv"] = q
    if etf:
        out["current_positions_588200.template.csv"] = etf
    return out


def write_template(path: Path, tickers: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["ticker", "current_shares"])
        for ticker in tickers:
            writer.writerow([ticker, 0])


def main() -> int:
    args = parse_args()
    rows = {key: list(value) for key, value in DEFAULT_ROWS.items()}
    run_dir = Path(args.run_dir) if args.run_dir else latest_run_dir() if args.latest else None
    if run_dir is not None:
        rows.update(tickers_from_run(run_dir))
    for name, tickers in rows.items():
        write_template(INPUTS_DIR / name, tickers)
    print({"templates_written": sorted(rows.keys()), "real_current_positions_written": False})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
