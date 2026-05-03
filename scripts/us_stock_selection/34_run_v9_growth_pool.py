"""Run v9 small tech-growth pool pre-research.

Approved scope: no Nasdaq100/S&P500 expansion, no full-market expansion, no
strategy search, no trading claim.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from quant_lab.us_stock_selection.utils import (
    PROJECT_ROOT as ROOT,
    create_run_artifacts,
    ensure_dir,
    load_yaml,
    make_logger,
    merge_many_dicts,
    save_json,
    save_text,
    save_yaml,
)
from quant_lab.us_stock_selection.v9_growth_pool import run_v9_growth_pool
from quant_lab.us_stock_selection.v9_reporting import build_v9_excel, build_v9_report, package_v9_run


DEFAULT_V8_2_RUN = ROOT / "outputs" / "us_stock_selection" / "run_20260502_220641"
DEFAULT_V8_1_RUN = ROOT / "outputs" / "us_stock_selection" / "run_20260502_210856"
DEFAULT_STORE = ROOT / "data" / "unified_ohlcv" / "us_stock_selection"
MEISTOCK_ROOT = Path(r"E:\dzhwork\obsydian\quant_lab\MeiStock")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run v9 small growth-pool pre-research; fixed v8.2 strategy only.")
    parser.add_argument("--config", default="configs/us_stock_selection/validation_config.yaml")
    parser.add_argument("--v8-2-run-dir", default=str(DEFAULT_V8_2_RUN))
    parser.add_argument("--v8-1-run-dir", default=str(DEFAULT_V8_1_RUN))
    parser.add_argument("--unified-store-dir", default=str(DEFAULT_STORE))
    parser.add_argument("--run-dir", default="")
    parser.add_argument("--dry-run-init", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = merge_many_dicts(load_yaml("configs/us_stock_selection/factor_groups.yaml"), load_yaml(args.config))
    output_root = ROOT / config.get("paths", {}).get("output_root", "outputs/us_stock_selection")
    if args.run_dir:
        run_dir = ensure_dir(args.run_dir)
        timestamp = run_dir.name.replace("run_", "")
        logs_dir = ensure_dir(run_dir / "logs")
        reports_dir = ensure_dir(run_dir / "reports")
    else:
        artifacts = create_run_artifacts(output_root)
        run_dir = artifacts.run_dir
        timestamp = artifacts.timestamp
        logs_dir = artifacts.logs_dir
        reports_dir = artifacts.reports_dir

    logger = make_logger(logs_dir / "v9_growth_pool.log", level=str(config.get("logging", {}).get("level", "INFO")))
    logger.info(f"Prepared v9 small growth-pool run {run_dir}")
    save_yaml(config, run_dir / "run_config.yaml")
    save_text(
        "\n".join(
            [
                "# v9 small growth-pool scope",
                "",
                "批准进入 v9，但仅限小幅科技成长池预研。",
                "不扩 Nasdaq100/S&P500，不全市场扩池，不交易化。",
                "固定主线：Alpha360 + LGBModel + label_5d + top5_ytdcap80p_derisk100p。",
                f"v8_2_run_dir: `{args.v8_2_run_dir}`",
                "",
            ]
        ),
        run_dir / "V9_GROWTH_POOL_SCOPE.md",
    )
    if args.dry_run_init:
        print({"run_dir": str(run_dir), "stage": "v9_growth_pool", "dry_run_init": True})
        return

    out_dir = ensure_dir(run_dir / "v9_growth_pool")
    result = run_v9_growth_pool(
        out_dir=out_dir,
        v8_2_run_dir=args.v8_2_run_dir,
        v8_1_run_dir=args.v8_1_run_dir,
        unified_store_dir=args.unified_store_dir,
        logger=logger,
    )
    verdict = result["cycle_verdict"]
    save_json(verdict, run_dir / "v9_cycle_verdict.json")
    build_v9_report(
        reports_dir / "us_stock_selection_v9_growth_pool_report.md",
        result["results"],
        result["excluded"],
        result["ticker_contribution"],
        verdict,
    )
    build_v9_excel(reports_dir / "us_stock_selection_v9_summary.xlsx", build_excel_sheets(result))
    update_summaries(run_dir, result)
    sync_meistock(run_dir, reports_dir, out_dir, verdict, logger)
    shutil.copy2(logs_dir / "v9_growth_pool.log", logs_dir / "run.log")
    zip_path = package_v9_run(run_dir, timestamp)
    logger.info(f"Packaged v9 zip {zip_path}")
    print(
        {
            "run_dir": str(run_dir),
            "zip_path": str(zip_path),
            "classification": verdict.get("classification"),
            "allow_enter_v10": verdict.get("allow_enter_v10"),
        }
    )


def build_excel_sheets(result: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    sheets = {
        "results": result["results"],
        "excluded": result["excluded"],
        "included": result["included"],
        "quality": result["quality"].head(1000),
        "annual": result["annual"].head(1000),
        "ticker_contrib": result["ticker_contribution"].head(1000),
        "holdings": result["holdings"].head(1000),
        "trades": result["trades"].head(1000),
        "triggers": result["triggers"].head(1000),
        "verdict": pd.DataFrame([result["cycle_verdict"]]),
    }
    return {k[:31]: v for k, v in sheets.items()}


def update_summaries(run_dir: Path, result: dict[str, pd.DataFrame]) -> None:
    verdict = result["cycle_verdict"]
    results = result["results"]
    excluded = result["excluded"]
    expanded = _result_row(results, "pool_a_plus_small_growth")
    pool = _result_row(results, "pool_a_v8_2_reproduction")
    small = _result_row(results, "small_growth_only")
    no_extreme = _result_row(results, "pool_a_plus_small_growth_ex_extreme_vol")
    lines = [
        "# RUN_SUMMARY",
        "",
        "本轮目标：执行 v9 small growth-pool pre-research；仅小幅科技成长池，不扩 Nasdaq100/S&P500，不交易化。",
        "",
        f"新 run 目录：`{run_dir}`",
        f"最终分类：`{verdict.get('classification')}`",
        f"是否允许进入 v10：`{verdict.get('allow_enter_v10')}`",
        "",
        "核心结果：",
        f"- Pool A reproduction CAGR/Calmar: `{pool.get('cagr')}` / `{pool.get('calmar')}`",
        f"- Pool A + small growth CAGR/Calmar: `{expanded.get('cagr')}` / `{expanded.get('calmar')}`",
        f"- Small growth only CAGR/Calmar: `{small.get('cagr')}` / `{small.get('calmar')}`",
        f"- Ex extreme-vol CAGR/Calmar: `{no_extreme.get('cagr')}` / `{no_extreme.get('calmar')}`",
        f"- Excluded tickers: `{', '.join(excluded.get('ticker', pd.Series(dtype=str)).astype(str).tolist()) if not excluded.empty else ''}`",
        "",
        "结论：本轮仍不是交易化，也不允许自动扩 Nasdaq100/S&P500。",
    ]
    text = "\n".join(lines) + "\n"
    save_text(text, run_dir / "RUN_SUMMARY.md")
    save_text(text, ROOT / "RUN_SUMMARY.md")

    next_text = f"""# NEXT_STEPS

当前状态：v9 small growth-pool pre-research 已完成。

- Run：`{run_dir}`
- Classification：`{verdict.get('classification')}`
- Allow v10：`{verdict.get('allow_enter_v10')}`

硬边界：

1. 本轮只验证小幅科技成长池。
2. 不扩 Nasdaq100，不扩 S&P500，不做全市场扩池。
3. 不交易化。
4. 是否进入 v10 需要用户另行批准。
5. 即使进入 v10，也应优先行业主题池/更严格 universe 设计，不应直接扩 Nasdaq100。
"""
    save_text(next_text, ROOT / "NEXT_STEPS.md")


def _result_row(results: pd.DataFrame, universe_name: str) -> dict:
    if results.empty:
        return {}
    rows = results.loc[(results["universe_name"] == universe_name) & (results["top_k"] == 5)]
    if rows.empty:
        rows = results.loc[results["universe_name"] == universe_name]
    return rows.iloc[0].to_dict() if not rows.empty else {}


def sync_meistock(run_dir: Path, reports_dir: Path, out_dir: Path, verdict: dict, logger) -> None:
    try:
        checkpoint = ensure_dir(MEISTOCK_ROOT / "checkpoint" / f"v9_growth_pool_{run_dir.name.replace('run_', '')}")
        save_text(
            "\n".join(
                [
                    "# v9 small growth-pool checkpoint",
                    "",
                    f"- Run: `{run_dir}`",
                    f"- Classification: `{verdict.get('classification')}`",
                    f"- Allow v10: `{verdict.get('allow_enter_v10')}`",
                    "",
                ]
            ),
            checkpoint / "checkpoint.md",
        )
        for src in [
            reports_dir / "us_stock_selection_v9_growth_pool_report.md",
            reports_dir / "us_stock_selection_v9_summary.xlsx",
            out_dir / "v9_growth_pool_results.csv",
            out_dir / "v9_excluded_tickers.csv",
            out_dir / "v9_cycle_verdict.json",
            ROOT / "NEXT_STEPS.md",
        ]:
            if src.exists():
                shutil.copy2(src, checkpoint / src.name)
    except Exception as exc:  # pragma: no cover
        logger.warning(f"MeiStock sync failed: {exc}")


if __name__ == "__main__":
    main()
