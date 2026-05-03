"""Export reusable Qlib workflow configs from quant_lab strategy specs."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.qlib_ext.strategy_bridge import QlibWorkflowSpec, build_qlib_workflow_config, dump_qlib_workflow_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export a Qlib workflow YAML from a dual-framework strategy spec.")
    parser.add_argument("--strategy", default="topk_dropout_50_5")
    parser.add_argument("--provider-uri", default="./data/qlib_bin")
    parser.add_argument("--market", default="csi300")
    parser.add_argument("--benchmark", default="SH000300")
    parser.add_argument("--start", default="2010-01-01")
    parser.add_argument("--end", default="2026-12-31")
    parser.add_argument("--fit-start", default="2010-01-01")
    parser.add_argument("--fit-end", default="2018-12-31")
    parser.add_argument("--train-start", default="2010-01-01")
    parser.add_argument("--train-end", default="2018-12-31")
    parser.add_argument("--valid-start", default="2019-01-01")
    parser.add_argument("--valid-end", default="2020-12-31")
    parser.add_argument("--test-start", default="2021-01-01")
    parser.add_argument("--test-end", default="2026-12-31")
    parser.add_argument("--output", default="configs/qlib/generated_workflow.yaml")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    spec = QlibWorkflowSpec(
        provider_uri=args.provider_uri,
        market=args.market,
        benchmark=args.benchmark,
        start_time=args.start,
        end_time=args.end,
        fit_start_time=args.fit_start,
        fit_end_time=args.fit_end,
        train_segment=(args.train_start, args.train_end),
        valid_segment=(args.valid_start, args.valid_end),
        test_segment=(args.test_start, args.test_end),
        backtest_start_time=args.test_start,
        backtest_end_time=args.test_end,
        strategy_name=args.strategy,
    )
    path = dump_qlib_workflow_config(build_qlib_workflow_config(spec), ROOT / args.output)
    print(path)


if __name__ == "__main__":
    main()
