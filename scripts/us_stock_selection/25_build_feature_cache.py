"""Build v7 Alpha158/Alpha360 parquet feature cache."""

from __future__ import annotations

import argparse
from pathlib import Path

from scripts.us_stock_selection._bootstrap import PROJECT_ROOT  # noqa: F401

from quant_lab.us_stock_selection.feature_cache import build_feature_cache
from quant_lab.us_stock_selection.local_qlib_provider_builder import default_local_provider_uri


def main() -> None:
    parser = argparse.ArgumentParser(description="Build v7 feature cache.")
    parser.add_argument("--run-dir", default="outputs/us_stock_selection/manual_v7")
    parser.add_argument("--provider-uri", default=str(default_local_provider_uri()))
    parser.add_argument("--feature-sets", default="Alpha158,Alpha360")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    outputs = build_feature_cache(
        Path(args.run_dir) / "v7_feature_cache",
        provider_uri=args.provider_uri,
        feature_sets=[x.strip() for x in args.feature_sets.split(",") if x.strip()],
        overwrite=args.overwrite,
    )
    print(outputs["status"].to_dict(orient="records"))


if __name__ == "__main__":
    main()
