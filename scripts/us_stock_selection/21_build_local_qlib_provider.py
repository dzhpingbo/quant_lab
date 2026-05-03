"""Build local 2022-2026 Qlib bin provider from quant_lab US data."""

from __future__ import annotations

import argparse
from pathlib import Path

from scripts.us_stock_selection._bootstrap import PROJECT_ROOT  # noqa: F401

from quant_lab.us_stock_selection.local_qlib_provider_builder import (
    build_local_qlib_provider,
    default_local_provider_uri,
    locate_or_clone_qlib_source,
)
from quant_lab.us_stock_selection.utils import load_env_config, load_yaml, make_logger, merge_many_dicts


def main() -> None:
    parser = argparse.ArgumentParser(description="Build local Qlib bin provider.")
    parser.add_argument("--config", default="configs/us_stock_selection/validation_config.yaml")
    parser.add_argument("--run-dir", default="outputs/us_stock_selection/manual_v6_provider")
    parser.add_argument("--provider-uri", default=str(default_local_provider_uri()))
    parser.add_argument("--no-rebuild", action="store_true")
    args = parser.parse_args()
    run_dir = Path(args.run_dir)
    provider_dir = run_dir / "qlib_local_provider"
    source_dir = run_dir / "qlib_source"
    logger = make_logger(run_dir / "logs" / "run.log")
    source_status = locate_or_clone_qlib_source(source_dir, clone_if_missing=True)
    config = merge_many_dicts(load_yaml("configs/us_stock_selection/factor_groups.yaml"), load_yaml(args.config))
    status = build_local_qlib_provider(provider_dir, config, load_env_config(), logger, qlib_source_dir=source_status.get("selected_source") or None, provider_uri=args.provider_uri, rebuild=not args.no_rebuild)
    print({"provider_uri": args.provider_uri, "success": status.get("local_provider_success")})


if __name__ == "__main__":
    main()
