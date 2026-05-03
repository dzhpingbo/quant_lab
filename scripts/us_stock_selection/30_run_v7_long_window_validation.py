"""Run v7 annual/long-window validation and multi-portfolio audit."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from quant_lab.us_stock_selection.local_qlib_provider_builder import default_local_provider_uri
from quant_lab.us_stock_selection.utils import PROJECT_ROOT as ROOT, create_run_artifacts, load_yaml, make_logger, merge_many_dicts, save_text, save_yaml
from quant_lab.us_stock_selection.v7_long_window import package_v7_long_window_run, run_v7_long_window_validation


DEFAULT_CACHE_RUN = ROOT / "outputs" / "us_stock_selection" / "run_20260426_035045"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run v7 long-window validation.")
    parser.add_argument("--config", default="configs/us_stock_selection/validation_config.yaml")
    parser.add_argument("--provider-uri", default=str(default_local_provider_uri()))
    parser.add_argument("--source-cache-run", default=str(DEFAULT_CACHE_RUN))
    parser.add_argument("--rebuild-cache", action="store_true")
    args = parser.parse_args()

    config = merge_many_dicts(load_yaml("configs/us_stock_selection/factor_groups.yaml"), load_yaml(args.config))
    artifacts = create_run_artifacts(ROOT / config.get("paths", {}).get("output_root", "outputs/us_stock_selection"))
    logger = make_logger(artifacts.logs_dir / "run.log", level=str(config.get("logging", {}).get("level", "INFO")))
    logger.info(f"Prepared v7 long-window run {artifacts.run_dir}")
    save_yaml(config, artifacts.run_dir / "run_config.yaml")

    outputs = run_v7_long_window_validation(
        run_dir=artifacts.run_dir,
        provider_uri=args.provider_uri,
        source_cache_run=args.source_cache_run,
        rebuild_cache=args.rebuild_cache,
    )
    verdict = outputs["verdict"]
    zip_path = package_v7_long_window_run(artifacts.run_dir, artifacts.timestamp)
    update_run_summary(artifacts.run_dir, zip_path, verdict, outputs["conservative"])
    update_next_steps(verdict)
    # Repackage after root summaries are updated.
    zip_path = package_v7_long_window_run(artifacts.run_dir, artifacts.timestamp)
    logger.info(f"Packaged v7 long-window zip {zip_path}")
    print(
        {
            "run_dir": str(artifacts.run_dir),
            "zip_path": str(zip_path),
            "classification": verdict.get("classification"),
            "allow_enter_v8": verdict.get("allow_enter_v8"),
            "must_send_to_chatgpt": verdict.get("must_send_to_chatgpt"),
            "reason": verdict.get("reason"),
            "best": verdict.get("best", {}),
        }
    )


def update_run_summary(run_dir: Path, zip_path: Path, verdict: dict, conservative: pd.DataFrame) -> None:
    best = verdict.get("best", {}) if isinstance(verdict, dict) else {}
    text = f"""# RUN_SUMMARY

本轮目标：v7 long-window validation，使用年度/两年 OOS 测试窗口减少短窗口年化和 Calmar 放大。

新 run 目录：`{run_dir}`

zip：`{zip_path}`

当前分类：`{verdict.get("classification")}`

是否允许进入 v8：`{verdict.get("allow_enter_v8")}`

是否需要发给 ChatGPT/用户决策：`{verdict.get("must_send_to_chatgpt")}`

核心原因：{verdict.get("reason")}

最佳策略：`{best.get("strategy_key")}`

核心指标：
- annual_like_window_count: `{best.get("annual_like_window_count")}`
- annual_like_mean_cagr: `{best.get("annual_like_mean_cagr")}`
- annual_like_mean_calmar_winsor: `{best.get("annual_like_mean_calmar_winsor")}`
- annual_like_cagr20_pass_rate: `{best.get("annual_like_cagr20_pass_rate")}`
- annual_like_calmar1_pass_rate: `{best.get("annual_like_calmar1_pass_rate")}`
- top_holding_contribution: `{best.get("top_holding_contribution")}`
- avg_herfindahl: `{best.get("avg_herfindahl")}`
- cost50_mean_cagr: `{verdict.get("cost50_mean_cagr")}`
- same_window_qqq_cagr_win_rate: `{verdict.get("same_window_qqq_cagr_win_rate")}`
- same_window_qqq_calmar_win_rate: `{verdict.get("same_window_qqq_calmar_win_rate")}`

本轮输出：
- `v7_long_window/wf_detail.csv`
- `v7_long_window/long_window_conservative_summary.csv`
- `v7_long_window/long_window_recalc_check.csv`
- `v7_long_window/long_window_cost_sensitivity.csv`
- `v7_long_window/long_window_same_window_benchmark.csv`
- `reports/us_stock_selection_v7_long_window_report.md`
- `reports/us_stock_selection_v7_long_window_summary.xlsx`
"""
    save_text(text, run_dir / "RUN_SUMMARY.md")
    save_text(text, ROOT / "RUN_SUMMARY.md")


def update_next_steps(verdict: dict) -> None:
    classification = verdict.get("classification")
    if classification == "credible_research_candidate":
        body = """# NEXT_STEPS

当前状态：v7 long-window validation 达到 `credible_research_candidate`。

必须暂停自动推进：请把 RUN_SUMMARY.md 和 v7 long-window 报告发给 ChatGPT/用户审阅后，再决定是否进入 v8。

禁止事项：
1. 未经审阅不要进入 v8；
2. 不扩 Nasdaq100/S&P500；
3. 不把结果直接当作可交易结论。
"""
    elif classification == "promising_but_needs_more_validation":
        body = """# NEXT_STEPS

当前下一步：继续 v7 证据加固，不进入 v8，不扩 Nasdaq100/S&P500。

当前分类：`promising_but_needs_more_validation`

已完成：
1. TopKDropout 严格 n_drop 已修复；
2. v7 long-window annual/2Y OOS 已运行；
3. Top5 equal / Top5 dropout / Top10 dropout 已做统一保守口径、成本、同窗口基准和 recompute 检查。

下一轮优先事项：
1. 重点复核 long-window 最佳策略的持仓贡献和 leave-one-ticker / leave-one-year；
2. 若集中度仍偏高，优先比较 Top10 dropout 或加 max contribution 约束，而不是进入 v8；
3. 继续避免短窗口年化 Calmar 作为主结论；
4. 不扩 Nasdaq100/S&P500。
"""
    else:
        body = f"""# NEXT_STEPS

当前下一步：v7 long-window 未通过，继续失败复盘，不进入 v8，不扩 Nasdaq100/S&P500。

当前分类：`{classification}`

优先事项：
1. 检查 reported vs recomputed、dropout、权重、月频调仓；
2. 若无实现 bug，降低模型/组合复杂度；
3. 若连续多轮无改进，准备失败复盘并考虑换研究路线。
"""
    save_text(body, ROOT / "NEXT_STEPS.md")


if __name__ == "__main__":
    main()
