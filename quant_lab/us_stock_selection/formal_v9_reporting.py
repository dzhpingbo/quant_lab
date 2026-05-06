"""Reporting and packaging helpers for formal v9."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from quant_lab.us_stock_selection.utils import PROJECT_ROOT, save_text, write_excel, zip_selected_paths


def build_formal_v9_report(path: Path | str, result: dict[str, Any], zip_path: Path | str | None = None) -> Path:
    verdict = dict(result.get("verdict", {}))
    metrics = result.get("metrics", pd.DataFrame())
    eligibility = result.get("eligibility", pd.DataFrame())
    excluded = result.get("excluded", pd.DataFrame())
    gate = result.get("gate_detail", pd.DataFrame())
    reproduction = result.get("pool_a_reproduction_check", pd.DataFrame())
    contrib = result.get("ticker_contribution", pd.DataFrame())
    input_summary = result.get("input_audit", {}).get("summary", {}) if isinstance(result.get("input_audit", {}), dict) else {}
    input_checks = result.get("input_audit", {}).get("checks", pd.DataFrame()) if isinstance(result.get("input_audit", {}), dict) else pd.DataFrame()
    pool = row(metrics, "formal_pool_a_reproduction")
    main = row(metrics, "formal_pool_a_plus_small_growth")
    small = row(metrics, "formal_small_growth_only")
    exhv = row(metrics, "formal_pool_a_plus_small_growth_ex_high_vol")

    text = f"""# Formal v9 Report

## Verdict

- classification: `{verdict.get("classification")}`
- formal_v9_gate_pass: `{verdict.get("formal_v9_gate_pass")}`
- formal_v9_performance_gate_pass: `{verdict.get("formal_v9_performance_gate_pass")}`
- Pool A reproduction pass: `{verdict.get("pool_a_reproduction_pass")}`
- effective universe count: `{verdict.get("effective_universe_count")}`
- effective small-growth count: `{verdict.get("effective_small_growth_count")}`
- effective new growth count: `{verdict.get("effective_new_growth_count")}`
- allow_enter_v10: `{verdict.get("allow_enter_v10")}`
- requires_human_review: `{verdict.get("requires_human_review")}`
- zip_path: `{zip_path or verdict.get("zip_path", "")}`
- provider_uri: `{input_summary.get("provider_uri", verdict.get("formal_provider_uri", ""))}`
- feature_cache: `{input_summary.get("feature_cache_path", "")}`
- score_audit: `{input_summary.get("score_audit_path", verdict.get("formal_score_audit_path", ""))}`
- replay_engine: `{input_summary.get("replay_engine", verdict.get("replay_engine", ""))}`

## Required Answers

1. Pool A reproduction 是否复现 v8.2 canonical？
   - `{verdict.get("pool_a_reproduction_pass")}`。这是 v9.1 provider 下的 canonical v8.2 anchor 复现检查，见 `formal_v9_pool_a_reproduction_check.csv`。
2. v9 使用的正式 universe 是什么？
   - `formal_pool_a_plus_small_growth`。有效新增 growth ticker 数：`{verdict.get("effective_new_growth_count")}`；ticker：`{verdict.get("effective_new_growth_tickers")}`。
3. 哪些 ticker 被剔除？原因是什么？
   - 见 `formal_v9_excluded_tickers.csv`；剔除行不允许进入 formal TopK。
4. Pool A + small growth 是否通过 v9 gate？
   - 最终 formal gate：`{verdict.get("formal_v9_gate_pass")}`；性能 gate：`{verdict.get("formal_v9_performance_gate_pass")}`。细节见 `formal_v9_gate_detail.csv`。
5. small growth only 是否有价值？
   - 只能作为观察项；核心指标见下方 `formal_small_growth_only`，不能作为主结论。
6. 剔除高波动票后结果如何？
   - 见 `formal_pool_a_plus_small_growth_ex_high_vol`。
7. 扩池是否提升了 CAGR / Calmar / 稳定性？
   - 对比 `formal_pool_a_reproduction` 与 `formal_pool_a_plus_small_growth` 的 CAGR / Calmar / concentration / stress gate。
8. 是否增加了 single-year share 或 top ticker share？
   - Pool A + growth single-year share：`{verdict.get("single_year_share")}`；top ticker：`{verdict.get("top_ticker")}`，share：`{verdict.get("top_ticker_share")}`。与 Pool A v9.1 score replay 对比见核心指标表。
9. 是否依赖 MSTR / COIN / PLTR？
   - `{verdict.get("depends_on_coin_mstr_pltr")}`；贡献 share `{verdict.get("controversial_mstr_coin_pltr_share")}`。
10. remove top year / remove top ticker 后是否仍有效？
    - remove top year CAGR/Calmar：`{verdict.get("remove_top_year_cagr")}` / `{verdict.get("remove_top_year_calmar")}`。
    - remove top ticker CAGR/Calmar：`{verdict.get("remove_top_ticker_cagr")}` / `{verdict.get("remove_top_ticker_calmar")}`。
11. 成本压力是否仍过关？
    - Pool A + growth cost50 CAGR/Calmar：`{main.get("cost50_t1_cagr")}` / `{main.get("cost50_t1_calmar")}`。
12. 是否允许进入 v10？
    - 不允许。
13. 是否需要人工审阅？
    - 需要。
14. 下一步应扩科技成长池、行业主题池、还是停止扩池？
    - `{verdict.get("next_allowed_action")}`。不得进入 v10，也不得扩 Nasdaq100/S&P500。

## Input Audit

{to_markdown(input_checks, max_rows=80)}

## Core Metrics

### Pool A v9.1 Score Replay

{kv(pool)}

### Pool A + Small Growth

{kv(main)}

### Small Growth Only

{kv(small)}

### Ex High Vol

{kv(exhv)}

## Pool A Reproduction Check

{to_markdown(reproduction)}

## Gate Detail

{to_markdown(gate)}

## Eligibility

{to_markdown(eligibility, max_rows=80)}

## Excluded Tickers

{to_markdown(excluded, max_rows=80)}

## Top Contributions

{to_markdown(contrib.sort_values(["universe_name", "abs_share"], ascending=[True, False]).head(40) if not contrib.empty else contrib)}
"""
    return save_text(text, path)


def build_formal_v9_excel(path: Path | str, result: dict[str, Any]) -> Path:
    sheets = {
        "verdict": pd.DataFrame([result.get("verdict", {})]),
        "metrics": result.get("metrics", pd.DataFrame()),
        "eligibility": result.get("eligibility", pd.DataFrame()),
        "excluded": result.get("excluded", pd.DataFrame()),
        "gate": result.get("gate_detail", pd.DataFrame()),
        "input_audit": result.get("input_audit", {}).get("checks", pd.DataFrame()) if isinstance(result.get("input_audit", {}), dict) else pd.DataFrame(),
        "reproduction": result.get("pool_a_reproduction_check", pd.DataFrame()),
        "daily_sample": result.get("daily", pd.DataFrame()).head(5000),
        "holdings_sample": result.get("holdings", pd.DataFrame()).head(5000),
        "trades": result.get("trades", pd.DataFrame()).head(5000),
        "decision_ledger": result.get("decision_ledger", pd.DataFrame()).head(5000),
        "score_audit": result.get("score_rank_audit", pd.DataFrame()).head(5000),
        "contribution": result.get("ticker_contribution", pd.DataFrame()).head(5000),
        "yearly": result.get("yearly_return", pd.DataFrame()),
    }
    return write_excel(sheets, path)


def package_formal_v9_run(run_dir: Path | str, timestamp: str) -> Path:
    base = Path(run_dir)
    zip_path = PROJECT_ROOT / "outputs" / "us_stock_selection" / f"us_stock_selection_formal_v9_{timestamp}.zip"
    paths = [
        base,
        PROJECT_ROOT / "RUN_SUMMARY.md",
        PROJECT_ROOT / "NEXT_STEPS.md",
        PROJECT_ROOT / "quant_lab" / "us_stock_selection" / "formal_v9_runner.py",
        PROJECT_ROOT / "quant_lab" / "us_stock_selection" / "formal_v9_reporting.py",
        PROJECT_ROOT / "quant_lab" / "us_stock_selection" / "canonical_replay_engine.py",
        PROJECT_ROOT / "scripts" / "us_stock_selection" / "39_run_formal_v9.py",
    ]
    return zip_selected_paths(paths, zip_path, root=PROJECT_ROOT)


def row(df: pd.DataFrame, universe_name: str) -> dict[str, Any]:
    if df is None or df.empty:
        return {}
    rows = df.loc[df["universe_name"].astype(str).eq(universe_name)]
    return rows.iloc[0].to_dict() if not rows.empty else {}


def kv(data: dict[str, Any]) -> str:
    if not data:
        return "_No result._\n"
    keys = [
        "universe_name",
        "ticker_count",
        "cagr",
        "calmar",
        "max_drawdown",
        "cost50_t1_cagr",
        "cost50_t1_calmar",
        "single_year_share",
        "top_ticker",
        "top_ticker_share",
        "remove_top_year_cagr",
        "remove_top_year_calmar",
        "remove_top_ticker_cagr",
        "remove_top_ticker_calmar",
        "depends_on_coin_mstr_pltr",
        "controversial_mstr_coin_pltr_share",
    ]
    lines = []
    for key in keys:
        value = data.get(key, "")
        if isinstance(value, float):
            value = f"{value:.6f}"
        lines.append(f"- {key}: `{value}`")
    return "\n".join(lines) + "\n"


def to_markdown(df: pd.DataFrame, max_rows: int = 30) -> str:
    if df is None or df.empty:
        return "_No rows._"
    clipped = df.head(max_rows).copy()
    try:
        return clipped.to_markdown(index=False)
    except Exception:
        return clipped.to_csv(index=False)
