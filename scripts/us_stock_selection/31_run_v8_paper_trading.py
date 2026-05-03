"""Run v8 frozen-candidate paper-trading replay and execution validation."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from quant_lab.us_stock_selection.local_qlib_provider_builder import default_local_provider_uri
from quant_lab.us_stock_selection.utils import (
    PROJECT_ROOT as ROOT,
    create_run_artifacts,
    ensure_dir,
    load_yaml,
    make_logger,
    merge_many_dicts,
    save_dataframe,
    save_json,
    save_text,
    save_yaml,
)
from quant_lab.us_stock_selection.v8_execution_sim import build_attribution, run_execution_stress_tests
from quant_lab.us_stock_selection.v8_model_stability import run_challenger_models, run_elasticnet_convergence_check
from quant_lab.us_stock_selection.v8_paper_trading import frozen_model_spec, run_paper_trading_replay
from quant_lab.us_stock_selection.v8_reporting import build_v8_excel, build_v8_report, classify_v8, package_v8_run


DEFAULT_SOURCE_RUN = ROOT / "outputs" / "us_stock_selection" / "run_20260426_060824"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run v8 paper-trading replay.")
    parser.add_argument("--config", default="configs/us_stock_selection/validation_config.yaml")
    parser.add_argument("--provider-uri", default=str(default_local_provider_uri()))
    parser.add_argument("--source-run", default=str(DEFAULT_SOURCE_RUN))
    parser.add_argument(
        "--dry-run-init",
        action="store_true",
        help="Only validate argparse/config/logging/output-directory initialization, then stop before any v8 computation.",
    )
    args = parser.parse_args()

    config = merge_many_dicts(load_yaml("configs/us_stock_selection/factor_groups.yaml"), load_yaml(args.config))
    artifacts = create_run_artifacts(ROOT / config.get("paths", {}).get("output_root", "outputs/us_stock_selection"))
    logger = make_logger(artifacts.logs_dir / "run.log", level=str(config.get("logging", {}).get("level", "INFO")))
    logger.info(f"Prepared v8 paper-trading run {artifacts.run_dir}")
    save_yaml(config, artifacts.run_dir / "run_config.yaml")

    cache_dir = ensure_dir(artifacts.run_dir / "v7_feature_cache")
    source_cache = Path(args.source_run) / "v7_feature_cache"
    paper_dir = ensure_dir(artifacts.run_dir / "v8_paper_trading")
    model_dir = ensure_dir(artifacts.run_dir / "v8_model_stability")
    exec_dir = ensure_dir(artifacts.run_dir / "v8_execution_sim")
    attr_dir = ensure_dir(artifacts.run_dir / "v8_attribution")

    if args.dry_run_init:
        # Environment self-check path: verify the entry point, config loading, logging,
        # and output directories without copying large caches or starting model fits.
        logger.info("Dry-run init requested; stopping before v8 feature cache copy and run_paper_trading_replay.")
        save_text(
            "\n".join(
                [
                    "# v8 dry-run init",
                    "",
                    "This run intentionally stopped before the first heavy v8 computation.",
                    f"run_dir: {artifacts.run_dir}",
                    f"source_cache: {source_cache}",
                    f"provider_uri: {args.provider_uri}",
                    "",
                ]
            ),
            artifacts.run_dir / "DRY_RUN_INIT.md",
        )
        print(
            {
                "run_dir": str(artifacts.run_dir),
                "dry_run_init": True,
                "stopped_before": "run_paper_trading_replay",
                "run_config": str(artifacts.run_dir / "run_config.yaml"),
                "log": str(artifacts.logs_dir / "run.log"),
            }
        )
        return

    if source_cache.exists():
        shutil.copytree(source_cache, cache_dir, dirs_exist_ok=True)
    else:
        fallback = ROOT / "outputs" / "us_stock_selection" / "run_20260426_035045" / "v7_feature_cache"
        shutil.copytree(fallback, cache_dir, dirs_exist_ok=True)

    logger.info("Running frozen Alpha360 ElasticNet Top5 monthly pseudo-live replay")
    paper = run_paper_trading_replay(
        paper_dir,
        cache_dir=cache_dir,
        provider_uri=args.provider_uri,
        model_spec=frozen_model_spec(),
        execution_delay=1,
        cost_bps=5.0,
        slippage_bps=5.0,
        max_weight=0.20,
        rebalance_timing="month_end",
        save_outputs=True,
    )
    logger.info("Running ElasticNet convergence diagnostic")
    convergence = run_elasticnet_convergence_check(model_dir, cache_dir=cache_dir, provider_uri=args.provider_uri)
    logger.info("Running challenger models")
    challengers = run_challenger_models(model_dir, cache_dir=cache_dir, provider_uri=args.provider_uri)
    logger.info("Running execution stress tests")
    stress_outputs = run_execution_stress_tests(exec_dir, paper["decisions"], paper["close"], paper["weights"], paper["returns"])
    stress = stress_outputs["stress"]

    logger.info("Running month-start replay for rebalance timing stress")
    month_start = run_paper_trading_replay(
        exec_dir / "month_start_replay",
        cache_dir=cache_dir,
        provider_uri=args.provider_uri,
        model_spec=frozen_model_spec(),
        execution_delay=1,
        cost_bps=5.0,
        slippage_bps=5.0,
        max_weight=0.20,
        rebalance_timing="month_start",
        save_outputs=False,
    )
    month_start_row = {"test_name": "month_start_rebalance", "stress_type": "rebalance_timing", **month_start["metrics"]}
    stress = pd.concat([stress, pd.DataFrame([month_start_row])], ignore_index=True)
    save_dataframe(stress, exec_dir / "execution_stress_results.csv")

    attribution = build_attribution(attr_dir, paper["close"], paper["weights"], paper["returns"])
    verdict = classify_v8(paper["metrics"], convergence, challengers, stress, attribution)
    save_json(verdict, artifacts.run_dir / "v8_verdict.json")
    save_json(verdict, exec_dir / "v8_verdict.json")
    paper_metrics_df = paper["metrics_df"]
    build_v8_report(
        artifacts.reports_dir / "us_stock_selection_v8_paper_trading_report.md",
        paper_metrics_df,
        convergence,
        challengers,
        stress,
        attribution,
        verdict,
    )
    build_v8_excel(
        artifacts.reports_dir / "us_stock_selection_v8_summary.xlsx",
        {
            "paper_metrics": paper_metrics_df,
            "decision_ledger": paper["decisions"],
            "monthly_holdings": paper["monthly_holdings"],
            "trades": paper["trades"],
            "elasticnet_convergence": convergence,
            "challenger_models": challengers,
            "execution_stress": stress,
            "ticker_contribution": attribution["ticker_contribution"],
            "yearly_return": attribution["yearly"],
            "monthly_return": attribution["monthly"],
            "verdict": pd.DataFrame([verdict]),
        },
    )
    update_summaries(artifacts.run_dir, verdict, paper_metrics_df, convergence, challengers, stress, attribution)
    zip_path = package_v8_run(artifacts.run_dir, artifacts.timestamp)
    logger.info(f"Packaged v8 zip {zip_path}")
    print(
        {
            "run_dir": str(artifacts.run_dir),
            "zip_path": str(zip_path),
            "classification": verdict.get("classification"),
            "allow_enter_v9": verdict.get("allow_enter_v9"),
            "paper_cagr": verdict.get("paper_cagr"),
            "paper_calmar": verdict.get("paper_calmar"),
            "cost50_cagr": verdict.get("cost50_cagr"),
            "remove_top_ticker_cagr": verdict.get("remove_top_ticker_cagr"),
            "top_ticker_share": verdict.get("top_ticker_share"),
        }
    )


def update_summaries(
    run_dir: Path,
    verdict: dict,
    paper_metrics: pd.DataFrame,
    convergence: pd.DataFrame,
    challengers: pd.DataFrame,
    stress: pd.DataFrame,
    attribution: dict[str, pd.DataFrame],
) -> None:
    best_challenger = challengers.iloc[0].to_dict() if not challengers.empty else {}
    top_ticker = attribution["ticker_contribution"].iloc[0].to_dict() if not attribution["ticker_contribution"].empty else {}
    text = f"""# RUN_SUMMARY

本轮目标：v8 paper-trading replay，冻结 v7 最佳候选，做研究级上线前仿真与执行真实性验证。

新 run 目录：`{run_dir}`

当前分类：`{verdict.get("classification")}`

是否允许进入 v9：`{verdict.get("allow_enter_v9")}`

paper-trading 核心结果：
- CAGR: `{verdict.get("paper_cagr")}`
- Calmar: `{verdict.get("paper_calmar")}`
- 50bps cost CAGR: `{verdict.get("cost50_cagr")}`
- T+1 CAGR: `{verdict.get("t1_cagr")}`
- T+1 Calmar: `{verdict.get("t1_calmar")}`

ElasticNet 收敛：
- min warning decision rate: `{verdict.get("min_convergence_warning_rate")}`
- convergence/challenger gate: `{verdict.get("gates", {}).get("convergence_or_challenger_ok")}`

最佳 challenger：
- run_id: `{best_challenger.get("run_id")}`
- CAGR: `{best_challenger.get("cagr")}`
- Calmar: `{best_challenger.get("calmar")}`

集中度：
- top ticker: `{top_ticker.get("ticker")}`
- top ticker share: `{verdict.get("top_ticker_share")}`
- remove top ticker CAGR: `{verdict.get("remove_top_ticker_cagr")}`
- remove top ticker Calmar: `{verdict.get("remove_top_ticker_calmar")}`
- single year share: `{verdict.get("single_year_share")}`

输出：
- `v8_paper_trading/monthly_decision_ledger.csv`
- `v8_paper_trading/daily_nav.csv`
- `v8_paper_trading/monthly_holdings.csv`
- `v8_paper_trading/trades.csv`
- `v8_model_stability/elasticnet_convergence_check.csv`
- `v8_model_stability/challenger_model_results.csv`
- `v8_execution_sim/execution_stress_results.csv`
- `v8_attribution/*.csv`
- `reports/us_stock_selection_v8_paper_trading_report.md`
- `reports/us_stock_selection_v8_summary.xlsx`
"""
    save_text(text, run_dir / "RUN_SUMMARY.md")
    save_text(text, ROOT / "RUN_SUMMARY.md")
    if verdict.get("allow_enter_v9"):
        next_text = """# NEXT_STEPS

v8 达到 `v9_ready_research_candidate`。

下一步可以进入 v9，但只能小幅扩科技成长池，仍不要扩 Nasdaq100/S&P500，不要交易化。

v9 前置要求：
1. 保留当前 frozen candidate 作为基准；
2. 只扩半导体、AI 软件、云计算、网络安全、高流动性成长股；
3. 每次扩池都必须保留 paper-trading replay、成本、T+1/T+2、leave-one-ticker/year；
4. 不得把 v8 结果直接当作可实盘结论。
"""
    else:
        next_text = f"""# NEXT_STEPS

v8 未达到 v9_ready。

当前分类：`{verdict.get("classification")}`

下一步：
1. 不扩 Nasdaq100/S&P500；
2. 不交易化；
3. 优先处理模型收敛、challenger 一致性或执行敏感性；
4. 若连续多轮无改进，准备失败复盘。
"""
    save_text(next_text, ROOT / "NEXT_STEPS.md")


if __name__ == "__main__":
    main()
