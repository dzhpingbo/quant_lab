"""Reporting helpers for the v8.2/v9 score provenance alignment audit."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from quant_lab.us_stock_selection.utils import PROJECT_ROOT, ensure_dir, save_text, write_excel, zip_selected_paths


def build_score_provenance_alignment_report(path: Path | str, result: dict[str, Any], zip_path: Path | str | None = None) -> Path:
    out = Path(path)
    verdict = dict(result.get("verdict", {}))
    tables: dict[str, pd.DataFrame] = dict(result.get("tables", {}))

    score_source = tables.get("score_source_alignment", pd.DataFrame())
    score_summary = tables.get("score_rank_diff_summary", pd.DataFrame())
    reconstruction = tables.get("return_reconstruction_check", pd.DataFrame())
    gate = tables.get("gate_recompute_alignment", pd.DataFrame())
    baseline = tables.get("baseline_exception_pollution_detail", pd.DataFrame())
    missing = tables.get("missing_files", pd.DataFrame())

    avg_overlap = verdict.get("avg_top5_overlap_ratio", "")
    avg_corr = verdict.get("avg_score_rank_correlation", "")
    text = f"""# Score Provenance Alignment Audit Report

## Executive verdict

- classification: `{verdict.get("classification", "")}`
- score_provenance_consistent: `{verdict.get("score_provenance_consistent", "")}`
- method_window_consistent: `{verdict.get("method_window_consistent", "")}`
- return_reconstruction_consistent: `{verdict.get("return_reconstruction_consistent", "")}`
- baseline_exception_pollution_found: `{verdict.get("baseline_exception_pollution_found", "")}`
- requires_human_review: `{verdict.get("requires_human_review", "")}`
- allow_enter_v10: `{verdict.get("allow_enter_v10", "")}`
- allow_trade_execution: `{verdict.get("allow_trade_execution", "")}`
- zip_path: `{zip_path or verdict.get("zip_path", "")}`

本轮结论：v8.2 冻结主线与 v9 local replay 不是可直接等价比较的 score provenance。v9 原始 full-window 指标应废弃；unified replay 只适合作为审计证据，不足以作为正式 v9 通过结果。

## Required answers

1. v8.2 与 v9 的 score 是不是同源？
   - 不是。v8.2 来自 v8.1 Alpha360/LGBModel runtime score trail；v9 local replay 重新构造本地 Alpha360-compatible feature frame 并重新 fit。平均 Top5 overlap `{avg_overlap}`，平均 score/rank correlation `{avg_corr}`。
2. v8.2 与 v9 的训练窗口是否一致？
   - 不完全一致。两者都声明从 2020-01-02 起训，但 v8.2 使用导出的 `train_end_label_safe` 和冻结 score trail，v9 使用 reverse audit 中本地 refit 的 label-safe cutoff；模型 provenance 不同。
3. label_5d 定义是否一致？
   - 名义上一致，均记录为 `adj_close.shift(-6) / adj_close.shift(-1) - 1` / one-day lag 后 5d forward return；但 feature/cache 与 model fit 链路不同。
4. Alpha360 feature cache 是否一致？
   - 不一致。v8.2 指向 v8.1 Alpha360/Qlib provider artifact；本地 `data/features_cache/us_stock_selection` 是 legacy feature_builder cache，并不是 v8.2 Alpha360 cache。
5. v9 原始 CAGR 12.23% / 10.53% 为什么低？
   - v9 original daily_nav 从 2020-01-02 起算，包含 2020-2023 大量 zero-exposure 天数，摊薄 CAGR 与 Calmar；且 score provenance 与 v8.2 不同。
6. 统一窗口后 37.35% / 31.70% 为什么高？
   - unified window 截到 2024-01-02 至 2026-04-17，剔除了 zero-exposure 2020-2023，因此年化指标显著抬升；但仍未贴近 v8.2 冻结主线。
7. 是窗口差异、方法差异、score 差异、还是 exception pollution？
   - 同时存在窗口差异、方法/score provenance 差异和 baseline exception pollution；核心阻断是 score/method provenance 不一致。
8. baseline_exception_pollution 的具体来源是什么？
   - PLTR/SNOW 是 baseline reproduction only ticker，因 listed_after_2020_train_start 被标记为 v9 not ready，却出现在 Pool A reproduction/local replay 贡献中。
9. v9 原始结果是否应废弃？
   - 是。原始 full-window 指标不能与 v8.2 575-day 冻结窗口比较。
10. unified replay 是否可作为有效结果？
    - 不能作为正式通过结果；只能作为审计证据。它证明窗口对指标影响很大，但未证明 score provenance 对齐。
11. 是否允许继续 v9？
    - 不允许直接继续 v9 扩展或升级；下一步只能同池、同策略、同 gate 重新对齐 score provenance 或重跑正式 v9。
12. 是否允许进入 v10？
    - 不允许。
13. 是否仍需人工审阅？
    - 需要。当前 classification 要求人工复核或按 v8.2 score source 重跑。

## Score source alignment

{to_markdown(score_source, max_rows=20)}

## Score/rank monthly summary

{to_markdown(score_summary, max_rows=30)}

## Return reconstruction

{to_markdown(reconstruction, max_rows=20)}

## Unified gate recompute

{to_markdown(gate, max_rows=20)}

## Baseline exception pollution detail

{to_markdown(baseline, max_rows=20)}

## Missing inputs

{to_markdown(missing, max_rows=30)}

## Next allowed action

{verdict.get("next_allowed_action", "Stop and wait for review.")}
"""
    return save_text(text, out)


def build_score_provenance_alignment_excel(path: Path | str, result: dict[str, Any]) -> Path:
    tables: dict[str, pd.DataFrame] = dict(result.get("tables", {}))
    verdict = pd.DataFrame([result.get("verdict", {})])
    sheets = {
        "verdict": verdict,
        "manifest": tables.get("run_manifest_alignment", pd.DataFrame()),
        "universe": tables.get("universe_alignment", pd.DataFrame()),
        "score_source": tables.get("score_source_alignment", pd.DataFrame()),
        "model_fit": tables.get("model_fit_provenance", pd.DataFrame()),
        "score_summary": tables.get("score_rank_diff_summary", pd.DataFrame()),
        "score_rank_sample": tables.get("score_rank_diff", pd.DataFrame()).head(5000),
        "portfolio": tables.get("portfolio_decision_alignment", pd.DataFrame()).head(5000),
        "portfolio_diff": tables.get("portfolio_decision_diff", pd.DataFrame()),
        "calendar": tables.get("calendar_alignment", pd.DataFrame()),
        "reconstruction": tables.get("return_reconstruction_check", pd.DataFrame()),
        "gate": tables.get("gate_recompute_alignment", pd.DataFrame()),
        "baseline_pollution": tables.get("baseline_exception_pollution_detail", pd.DataFrame()),
        "missing": tables.get("missing_files", pd.DataFrame()),
    }
    return write_excel(sheets, path)


def package_score_provenance_alignment_run(run_dir: Path | str, timestamp: str) -> Path:
    base = Path(run_dir)
    zip_path = PROJECT_ROOT / "outputs" / "us_stock_selection" / f"us_stock_selection_score_provenance_alignment_audit_{timestamp}.zip"
    paths = [
        base,
        PROJECT_ROOT / "RUN_SUMMARY.md",
        PROJECT_ROOT / "NEXT_STEPS.md",
        PROJECT_ROOT / "quant_lab" / "us_stock_selection" / "score_provenance_audit.py",
        PROJECT_ROOT / "quant_lab" / "us_stock_selection" / "v9_alignment_reporting.py",
        PROJECT_ROOT / "scripts" / "us_stock_selection" / "37_run_score_provenance_alignment_audit.py",
    ]
    return zip_selected_paths(paths, zip_path, root=PROJECT_ROOT)


def to_markdown(df: pd.DataFrame, max_rows: int = 20) -> str:
    if df is None or df.empty:
        return "_No rows._"
    clipped = df.head(max_rows).copy()
    try:
        return clipped.to_markdown(index=False)
    except Exception:
        return clipped.to_csv(index=False)

