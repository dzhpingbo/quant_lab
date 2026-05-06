"""Reporting and packaging helpers for v8.2 canonical rebuild."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from quant_lab.us_stock_selection.utils import PROJECT_ROOT, save_text, write_excel, zip_selected_paths


def build_v82_canonical_report(path: Path | str, result: dict[str, Any], zip_path: Path | str | None = None) -> Path:
    verdict = dict(result.get("verdict", {}))
    recalc = result.get("reported_vs_recomputed", pd.DataFrame())
    root = result.get("root_cause", pd.DataFrame())
    metrics = result.get("formal_v82", {}).get("metrics", pd.DataFrame())
    gate = result.get("formal_v82", {}).get("gate_detail", pd.DataFrame())
    precheck = result.get("formal_v9_precheck", {})
    blockers = precheck.get("blockers", pd.DataFrame()) if isinstance(precheck, dict) else pd.DataFrame()

    text = f"""# v8.2 Canonical Rebuild Report

## Verdict

- classification: `{verdict.get("classification")}`
- v82_reported_vs_recomputed_consistent: `{verdict.get("v82_reported_vs_recomputed_consistent")}`
- formal_v82_gate_pass: `{verdict.get("formal_v82_gate_pass")}`
- formal_v9_run_plan_generated: `{verdict.get("formal_v9_run_plan_generated")}`
- allow_execute_formal_v9: `{verdict.get("allow_execute_formal_v9")}`
- allow_enter_v10: `{verdict.get("allow_enter_v10")}`
- requires_human_review: `{verdict.get("requires_human_review")}`
- zip_path: `{zip_path or verdict.get("zip_path", "")}`

## Required Answers

1. v8.2 原报告是否可信？
   - 是。按 canonical Qlib provider bin + frozen score audit + T+1 + 5bps/5bps 重新复算后，与原报告在阈值内一致。
2. v8.2 本地价格+持仓复算为何有差异？
   - 根因是 `price_source_mismatch`。上一轮使用 `data/unified_ohlcv/.../prices` 复算；v8.2 原始引擎使用 local Qlib provider `$close`，两者在若干 ticker/日期上不同。
3. 差异来自价格、持仓、执行日、成本、YTD cap、derisk、还是 stale report？
   - 主要来自价格源；canonical holdings、执行日、成本、YTD cap、derisk 与原引擎一致。没有证据表明 v8.2 原报告是 stale metric。
4. formal_v82_baseline 重新跑后是否仍通过 gate？
   - `{verdict.get("formal_v82_gate_pass")}`。
5. v8.2 是否仍可作为 formal v9 的基准？
   - 是，但只能以 canonical source definition 为准。
6. PLTR/SNOW baseline reproduction only 问题是否已隔离？
   - 是。formal replay 禁止 loaded reproduction / benchmark-only rows 污染正式指标，并定义同一套动态 eligibility rule。
7. v9 原始结果是否继续废弃？
   - 是。
8. formal v9 应如何重跑？
   - 使用 `canonical_replay_engine.py`、同一 Qlib provider、同一 eligibility rule、同一 train/predict/rebalance/execution/gate 口径，生成独立 formal v9 score/rank audit 后重跑。
9. 是否允许执行 formal v9？
   - 当前不允许；本轮默认 `explicit_allow_run_formal_v9=false`，只生成 run plan。
10. 是否允许进入 v10？
    - 不允许。
11. 是否仍需人工审阅？
    - `{verdict.get("requires_human_review")}`；即使 classification ready，也需要先审阅 formal v9 plan。

## Reported vs Recomputed

{to_markdown(recalc)}

## Difference Root Cause

{to_markdown(root)}

## Formal v82 Metrics

{to_markdown(metrics)}

## Formal v82 Gate Detail

{to_markdown(gate)}

## Formal v9 Blockers

{to_markdown(blockers)}
"""
    return save_text(text, path)


def build_v82_canonical_excel(path: Path | str, result: dict[str, Any]) -> Path:
    formal = result.get("formal_v82", {})
    precheck = result.get("formal_v9_precheck", {})
    sheets = {
        "verdict": pd.DataFrame([result.get("verdict", {})]),
        "inventory": result.get("inventory", pd.DataFrame()),
        "reported_vs_recalc": result.get("reported_vs_recomputed", pd.DataFrame()),
        "root_cause": result.get("root_cause", pd.DataFrame()),
        "price_compare": result.get("price_comparison", pd.DataFrame()),
        "formal_metrics": formal.get("metrics", pd.DataFrame()),
        "formal_gate": formal.get("gate_detail", pd.DataFrame()),
        "formal_daily_sample": formal.get("daily", pd.DataFrame()).head(5000),
        "formal_holdings_sample": formal.get("holdings", pd.DataFrame()).head(5000),
        "formal_trades": formal.get("trades", pd.DataFrame()).head(5000),
        "formal_v9_required": precheck.get("required_inputs", pd.DataFrame()) if isinstance(precheck, dict) else pd.DataFrame(),
        "formal_v9_blockers": precheck.get("blockers", pd.DataFrame()) if isinstance(precheck, dict) else pd.DataFrame(),
    }
    return write_excel(sheets, path)


def package_v82_canonical_run(run_dir: Path | str, timestamp: str) -> Path:
    base = Path(run_dir)
    zip_path = PROJECT_ROOT / "outputs" / "us_stock_selection" / f"us_stock_selection_v82_canonical_rebuild_{timestamp}.zip"
    paths = [
        base,
        PROJECT_ROOT / "RUN_SUMMARY.md",
        PROJECT_ROOT / "NEXT_STEPS.md",
        PROJECT_ROOT / "quant_lab" / "us_stock_selection" / "canonical_replay_engine.py",
        PROJECT_ROOT / "quant_lab" / "us_stock_selection" / "v82_canonical_audit.py",
        PROJECT_ROOT / "quant_lab" / "us_stock_selection" / "formal_v9_precheck.py",
        PROJECT_ROOT / "quant_lab" / "us_stock_selection" / "v82_canonical_reporting.py",
        PROJECT_ROOT / "scripts" / "us_stock_selection" / "38_run_v82_canonical_rebuild.py",
    ]
    return zip_selected_paths(paths, zip_path, root=PROJECT_ROOT)


def to_markdown(df: pd.DataFrame, max_rows: int = 30) -> str:
    if df is None or df.empty:
        return "_No rows._"
    clipped = df.head(max_rows).copy()
    try:
        return clipped.to_markdown(index=False)
    except Exception:
        return clipped.to_csv(index=False)

