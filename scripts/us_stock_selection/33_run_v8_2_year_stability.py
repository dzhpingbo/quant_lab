"""Run v8.2 year-stability replay for frozen Alpha360 LGBModel scores."""

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
    save_json,
    save_text,
    save_yaml,
)
from quant_lab.us_stock_selection.v8_2_reporting import build_v8_2_excel, build_v8_2_report, package_v8_2_run
from quant_lab.us_stock_selection.v8_2_year_stability import run_v8_2_year_stability


DEFAULT_V8_1_RUN = ROOT / "outputs" / "us_stock_selection" / "run_20260502_210856"
MEISTOCK_ROOT = Path(r"E:\dzhwork\obsydian\quant_lab\MeiStock")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run v8.2 year stability: no v9, no universe expansion, no model training.")
    parser.add_argument("--config", default="configs/us_stock_selection/validation_config.yaml")
    parser.add_argument("--provider-uri", default=str(default_local_provider_uri()))
    parser.add_argument("--v8-1-run-dir", default=str(DEFAULT_V8_1_RUN))
    parser.add_argument("--run-dir", default="", help="Existing run dir to resume; empty creates a new run.")
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

    logger = make_logger(logs_dir / "v8_2_year_stability.log", level=str(config.get("logging", {}).get("level", "INFO")))
    logger.info(f"Prepared v8.2 year-stability run {run_dir}")
    save_yaml(config, run_dir / "run_config.yaml")
    scope_text = "\n".join(
        [
            "# v8.2 Year Stability Scope",
            "",
            "本轮不进入 v9，不扩 Nasdaq100/S&P500，不交易化，不训练新模型。",
            "主线固定为 Alpha360 + LGBModel + label_5d。",
            "输入来自 v8.1 LGBModel score/rank audit trail，只做组合层稳定性 replay。",
            f"v8_1_run_dir: `{args.v8_1_run_dir}`",
            "",
        ]
    )
    save_text(scope_text, run_dir / "V8_2_YEAR_STABILITY_SCOPE.md")
    if args.dry_run_init:
        logger.info("Dry-run init requested; stopping before replay.")
        print({"run_dir": str(run_dir), "stage": "v8.2_year_stability", "dry_run_init": True})
        return

    out_dir = ensure_dir(run_dir / "v8_2_year_stability")
    result = run_v8_2_year_stability(
        out_dir=out_dir,
        v8_1_run_dir=args.v8_1_run_dir,
        provider_uri=args.provider_uri,
        logger=logger,
    )
    results = result["results"]
    verdict = result["cycle_verdict"]
    benchmark = result["benchmark"]
    save_json(verdict, run_dir / "v8_2_cycle_verdict.json")

    build_v8_2_report(reports_dir / "us_stock_selection_v8_2_year_stability_report.md", results, verdict, benchmark)
    build_v8_2_excel(reports_dir / "us_stock_selection_v8_2_summary.xlsx", build_excel_sheets(result))
    update_summaries(run_dir, results, verdict)
    sync_meistock(run_dir, reports_dir, out_dir, verdict, logger)
    zip_path = package_v8_2_run(run_dir, timestamp)
    logger.info(f"Packaged v8.2 zip {zip_path}")
    print(
        {
            "run_dir": str(run_dir),
            "zip_path": str(zip_path),
            "best_strategy_id": verdict.get("best_strategy_id"),
            "classification": verdict.get("classification"),
            "allow_enter_v9": verdict.get("allow_enter_v9"),
        }
    )


def build_excel_sheets(result: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    sheets: dict[str, pd.DataFrame] = {}
    for name, df in [
        ("results", result["results"]),
        ("stress", result["stress"]),
        ("annual", result["annual"]),
        ("monthly", result["monthly"]),
        ("ticker_contrib", result["ticker_contribution"]),
        ("leave_ticker", result["leave_ticker"]),
        ("leave_year", result["leave_year"]),
        ("benchmark", result["benchmark"]),
    ]:
        sheets[name[:31]] = df.head(1000) if isinstance(df, pd.DataFrame) else pd.DataFrame()
    sheets["cycle_verdict"] = pd.DataFrame([result["cycle_verdict"]])
    return sheets


def update_summaries(run_dir: Path, results: pd.DataFrame, verdict: dict) -> None:
    best = results.iloc[0].to_dict() if results is not None and not results.empty else {}
    lines = [
        "# RUN_SUMMARY",
        "",
        "本轮目标：执行 v8.2 year stability，不进入 v9，不扩 Nasdaq100/S&P500，不交易化。",
        "",
        f"新 run 目录：`{run_dir}`",
        "",
        f"最佳组合：`{best.get('strategy_id', '')}`",
        f"最终分类：`{verdict.get('classification')}`",
        f"是否允许进入 v9：`{verdict.get('allow_enter_v9')}`",
        "",
        "最佳组合核心指标：",
        f"- CAGR: `{best.get('cagr')}`",
        f"- Calmar: `{best.get('calmar')}`",
        f"- MaxDD: `{best.get('max_drawdown')}`",
        f"- 50bps/T+1 CAGR: `{best.get('cost50_t1_cagr')}`",
        f"- 50bps/T+1 Calmar: `{best.get('cost50_t1_calmar')}`",
        f"- single-year share: `{best.get('single_year_share')}`",
        f"- top ticker share: `{best.get('top_ticker_share')}`",
        f"- remove top year CAGR: `{best.get('remove_top_year_cagr')}`",
        f"- remove top year Calmar: `{best.get('remove_top_year_calmar')}`",
        f"- remove top ticker CAGR: `{best.get('remove_top_ticker_cagr')}`",
        f"- remove top ticker Calmar: `{best.get('remove_top_ticker_calmar')}`",
        "",
        "结论：本轮只做研究级 replay。即使 allow_enter_v9=True，也不自动进入 v9；必须用户另行批准。",
        "",
    ]
    text = "\n".join(lines)
    save_text(text, run_dir / "RUN_SUMMARY.md")
    save_text(text, ROOT / "RUN_SUMMARY.md")

    next_text = f"""# NEXT_STEPS

当前状态：v8.2 year stability 已完成。

- Run：`{run_dir}`
- Best strategy：`{best.get('strategy_id', '')}`
- Classification：`{verdict.get('classification')}`
- Allow v9：`{verdict.get('allow_enter_v9')}`

硬边界：

1. 本轮未进入 v9。
2. 未扩 Nasdaq100/S&P500，未扩全市场。
3. 未训练新模型，未交易化。
4. 如果 allow v9 为 True，下一步仍需用户另行批准，且只允许小幅科技成长池预研。
5. 如果 allow v9 为 False，下一步只能继续处理年度集中度/执行敏感性，不能用扩池掩盖问题。
"""
    save_text(next_text, ROOT / "NEXT_STEPS.md")


def sync_meistock(run_dir: Path, reports_dir: Path, out_dir: Path, verdict: dict, logger) -> None:
    try:
        checkpoint = ensure_dir(MEISTOCK_ROOT / "checkpoint" / f"v8_2_year_stability_{run_dir.name.replace('run_', '')}")
        index_lines = [
            "# v8.2 year stability checkpoint",
            "",
            f"- Run: `{run_dir}`",
            f"- Classification: `{verdict.get('classification')}`",
            f"- Allow v9: `{verdict.get('allow_enter_v9')}`",
            f"- Best strategy: `{verdict.get('best_strategy_id')}`",
            "",
            "附件：",
            "- us_stock_selection_v8_2_year_stability_report.md",
            "- us_stock_selection_v8_2_summary.xlsx",
            "- v8_2_year_stability_results.csv",
            "- v8_2_cycle_verdict.json",
        ]
        save_text("\n".join(index_lines) + "\n", checkpoint / "checkpoint.md")
        for src in [
            reports_dir / "us_stock_selection_v8_2_year_stability_report.md",
            reports_dir / "us_stock_selection_v8_2_summary.xlsx",
            out_dir / "v8_2_year_stability_results.csv",
            out_dir / "v8_2_cycle_verdict.json",
            ROOT / "NEXT_STEPS.md",
        ]:
            if src.exists():
                shutil.copy2(src, checkpoint / src.name)
    except Exception as exc:  # pragma: no cover - sync is best-effort
        logger.warning(f"MeiStock sync failed: {exc}")


if __name__ == "__main__":
    main()
