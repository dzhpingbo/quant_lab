"""Run v7 reverse audit for the suspicious fast walk-forward candidate."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from quant_lab.us_stock_selection.local_qlib_provider_builder import default_local_provider_uri
from quant_lab.us_stock_selection.utils import PROJECT_ROOT as ROOT, create_run_artifacts, make_logger
from quant_lab.us_stock_selection.v7_audit import package_v7_audit_run, run_v7_audit


DEFAULT_SOURCE_RUN = ROOT / "outputs" / "us_stock_selection" / "run_20260425_214159"


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit v7 fast walk-forward metrics and TopK dropout logic.")
    parser.add_argument("--source-run-dir", default=str(DEFAULT_SOURCE_RUN))
    parser.add_argument("--provider-uri", default=str(default_local_provider_uri()))
    parser.add_argument("--output-root", default=str(ROOT / "outputs" / "us_stock_selection"))
    args = parser.parse_args()

    artifacts = create_run_artifacts(args.output_root)
    logger = make_logger(artifacts.logs_dir / "run.log")
    logger.info(f"Prepared v7 audit run {artifacts.run_dir}")
    logger.info(f"Source v7 run: {args.source_run_dir}")

    outputs = run_v7_audit(
        source_run_dir=args.source_run_dir,
        audit_run_dir=artifacts.run_dir,
        provider_uri=args.provider_uri,
    )
    zip_path = package_v7_audit_run(artifacts.run_dir, artifacts.timestamp)
    logger.info(f"Packaged v7 audit zip {zip_path}")
    verdict = outputs["classification"]
    conservative = outputs["conservative"]
    print(
        {
            "audit_run_dir": str(artifacts.run_dir),
            "zip_path": str(zip_path),
            "classification": verdict.get("classification"),
            "allow_enter_v8": verdict.get("allow_enter_v8"),
            "reason": verdict.get("reason"),
            "conservative_summary": conservative.to_dict(orient="records")[:1],
        }
    )


if __name__ == "__main__":
    main()
