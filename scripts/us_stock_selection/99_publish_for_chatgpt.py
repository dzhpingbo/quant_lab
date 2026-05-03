"""Publish a compact ChatGPT review packet for the latest us_stock_selection run."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from quant_lab.us_stock_selection.chatgpt_bridge import DEFAULT_BRIDGE_DIR, publish_for_chatgpt


def parse_bool(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Publish compact review artifacts to docs/chatgpt_bridge.")
    parser.add_argument("--run-dir", default="", help="Run directory. Defaults to latest outputs/us_stock_selection/run_*.")
    parser.add_argument("--bridge-dir", default=str(DEFAULT_BRIDGE_DIR))
    parser.add_argument("--git-push", action="store_true")
    parser.add_argument("--max-csv-mb", type=float, default=5.0)
    parser.add_argument("--include-xlsx", default="false")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = publish_for_chatgpt(
        run_dir=args.run_dir or None,
        bridge_dir=args.bridge_dir,
        max_csv_mb=float(args.max_csv_mb),
        include_xlsx=parse_bool(args.include_xlsx),
        git_push=bool(args.git_push),
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
