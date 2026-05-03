"""Locate or clone microsoft/qlib source for dump_bin.py."""

from __future__ import annotations

import argparse
from pathlib import Path

from scripts.us_stock_selection._bootstrap import PROJECT_ROOT  # noqa: F401

from quant_lab.us_stock_selection.local_qlib_provider_builder import locate_or_clone_qlib_source


def main() -> None:
    parser = argparse.ArgumentParser(description="Locate or clone microsoft/qlib source.")
    parser.add_argument("--out-dir", default="outputs/us_stock_selection/qlib_source")
    parser.add_argument("--no-clone", action="store_true")
    args = parser.parse_args()
    status = locate_or_clone_qlib_source(Path(args.out_dir), clone_if_missing=not args.no_clone)
    print(status)


if __name__ == "__main__":
    main()
