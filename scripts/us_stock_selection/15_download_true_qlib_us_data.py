"""Download or document the true Qlib US provider dataset."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from quant_lab.us_stock_selection.true_qlib_provider import official_download_attempt, qlib_provider_health_check
from quant_lab.us_stock_selection.utils import PROJECT_ROOT as ROOT, ensure_dir


def main():
    parser = argparse.ArgumentParser(description="Prepare true Qlib US provider data.")
    parser.add_argument("--target-dir", default="~/.qlib/qlib_data/us_data")
    parser.add_argument("--output-dir", default="outputs/us_stock_selection/qlib_data_true_provider")
    parser.add_argument("--execute", action="store_true", help="Actually run qlib.cli.data if provider is missing.")
    args = parser.parse_args()
    out_dir = ensure_dir(ROOT / args.output_dir)
    status = official_download_attempt(out_dir, target_dir=args.target_dir, execute=args.execute)
    health, _sample = qlib_provider_health_check(out_dir, provider_uri=args.target_dir)
    print({"download": status, "health": health})


if __name__ == "__main__":
    main()
