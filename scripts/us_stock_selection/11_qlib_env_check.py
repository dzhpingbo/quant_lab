"""Check pyqlib runtime, provider data, model libraries, and GPU availability."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from quant_lab.us_stock_selection.qlib_env import check_qlib_environment
from quant_lab.us_stock_selection.utils import PROJECT_ROOT as ROOT


def main():
    parser = argparse.ArgumentParser(description="Check Qlib runtime and US data environment.")
    parser.add_argument("--provider-uri", default=None, help="Optional Qlib provider URI.")
    parser.add_argument("--output-dir", default="outputs/us_stock_selection/qlib_env_check", help="Output directory.")
    args = parser.parse_args()
    status = check_qlib_environment(ROOT / args.output_dir, provider_uri=args.provider_uri)
    print(status)


if __name__ == "__main__":
    main()
