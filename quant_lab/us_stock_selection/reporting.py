"""Report generation and packaging helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from quant_lab.us_stock_selection.utils import (
    PROJECT_ROOT,
    basic_html_page,
    dataframe_to_html,
    save_text,
    write_excel,
    zip_selected_paths,
)


class ReportBuilder:
    """Generate markdown, HTML, Excel, and zip deliverables."""

    def __init__(self, config: dict[str, Any], logger):
        self.config = config
        self.logger = logger

    def build_markdown_report(
        self,
        report_path: Path | str,
        universe_df: pd.DataFrame,
        excluded_df: pd.DataFrame,
        top_df: pd.DataFrame,
        best_strategy_df: pd.DataFrame,
        factor_rank_df: pd.DataFrame,
        final_ranking_df: pd.DataFrame,
        buyhold_df: pd.DataFrame | None = None,
        parameter_stability_df: pd.DataFrame | None = None,
        walk_forward_summary_df: pd.DataFrame | None = None,
        rotation_df: pd.DataFrame | None = None,
        qlib_status: dict[str, Any] | None = None,
    ) -> Path:
        buyhold_df = buyhold_df if buyhold_df is not None else pd.DataFrame()
        parameter_stability_df = parameter_stability_df if parameter_stability_df is not None else pd.DataFrame()
        walk_forward_summary_df = walk_forward_summary_df if walk_forward_summary_df is not None else pd.DataFrame()
        rotation_df = rotation_df if rotation_df is not None else pd.DataFrame()
        qlib_status = qlib_status or {}
        top5 = top_df.head(5).copy()
        best_top5 = best_strategy_df.head(5).copy()
        hard_to_mine = final_ranking_df.loc[
            final_ranking_df["classification"].isin(["historical_winner_hard_to_mine", "historical_winner_but_hard_to_mine"]),
            [col for col in ["ticker", "bh_test_cagr", "test_cagr", "test_calmar", "final_score"] if col in final_ranking_df.columns],
        ].head(10)
        return_enhancer = final_ranking_df.loc[
            final_ranking_df["classification"] == "return_enhancer",
            [col for col in ["ticker", "test_cagr", "bh_test_cagr", "test_calmar", "bh_test_calmar", "final_score"] if col in final_ranking_df.columns],
        ].head(10)
        risk_reducer = final_ranking_df.loc[
            final_ranking_df["classification"] == "risk_reducer",
            [col for col in ["ticker", "test_cagr", "bh_test_cagr", "test_calmar", "bh_test_calmar", "test_max_drawdown", "bh_test_max_drawdown"] if col in final_ranking_df.columns],
        ].head(10)
        overfit_risk = final_ranking_df.loc[
            final_ranking_df["classification"].isin(["overfit_suspect", "high_return_but_overfit_risk"]),
            [col for col in ["ticker", "test_calmar", "overfit_penalty", "parameter_island_risk", "parameter_stability_score"] if col in final_ranking_df.columns],
        ].head(10)
        leveraged = final_ranking_df.loc[
            final_ranking_df.get("is_leveraged", pd.Series(False, index=final_ranking_df.index)).fillna(False).astype(bool),
            [col for col in ["ticker", "template_name", "test_cagr", "bh_test_cagr", "test_calmar", "bh_test_calmar", "classification", "final_score"] if col in final_ranking_df.columns],
        ]
        beats_cagr = int(final_ranking_df.get("strategy_beats_bh_cagr", pd.Series(dtype=bool)).fillna(False).sum()) if not final_ranking_df.empty else 0
        beats_calmar = int(final_ranking_df.get("strategy_beats_bh_calmar", pd.Series(dtype=bool)).fillna(False).sum()) if not final_ranking_df.empty else 0

        def _table(df: pd.DataFrame, columns: list[str] | None = None) -> str:
            if df.empty:
                return "_No rows_\n"
            safe_columns = [col for col in (columns or list(df.columns)) if col in df.columns]
            subset = df.loc[:, safe_columns].copy().fillna("")
            cols = list(subset.columns)
            header = "| " + " | ".join(cols) + " |"
            separator = "| " + " | ".join(["---"] * len(cols)) + " |"
            rows = []
            for _, row in subset.iterrows():
                values = [str(row[col]).replace("|", "/") for col in cols]
                rows.append("| " + " | ".join(values) + " |")
            return "\n".join([header, separator, *rows]) + "\n"

        text = f"""# US Stock Selection Report

## 0. V2 Acceptance Patch Summary
- This v2 run keeps the MVP structure and adds audit outputs instead of rewriting the project.
- New benchmark output: `benchmark/buyhold_by_ticker.csv`.
- New comparison fields: `bh_test_cagr`, `bh_test_calmar`, `strategy_vs_bh_*`, and `strategy_beats_bh_*`.
- New templates include `aggressive_breakout`, `trend_takeprofit`, `momentum_pullback_reentry`, and `leveraged_etf_guardrail`.
- The `trend_takeprofit` implementation is simplified: it does not use true partial position sizing; after the take-profit threshold is touched it ratchets the stop to breakeven / fast MA.
- Walk-forward now selects strategy parameters from historical windows rather than replaying one full-sample best parameter.
- Qlib status is explicit: `{qlib_status.get("status", "unknown")}`.

## 1. Universe Included
- Included universes: {", ".join(self.config.get("universe_selection", {}).get("include_universes", []))}
- Eligible tickers after data-quality screening: {len(universe_df)}
- Scope note: this v2 still covers core ETFs and Mag7 first. Nasdaq 100 and S&P 500 expansion is intentionally deferred until strategy expression and validation quality improve.

{_table(universe_df.head(30), ["ticker", "universe_name", "asset_type", "theme", "is_leveraged"])}

## 2. Excluded Tickers And Reasons

{_table(excluded_df.head(30), ["ticker", "universe_name", "exclusion_reason"] if not excluded_df.empty else None)}

## 3. Final Top 20 Ranking

{_table(top_df, ["ticker", "final_score", "test_cagr", "bh_test_cagr", "test_calmar", "bh_test_calmar", "strategy_vs_bh_calmar_diff", "test_max_drawdown", "classification"])}

## 4. Best Strategy For Top 5

{_table(top5, ["ticker", "template_name", "params", "test_cagr", "bh_test_cagr", "test_calmar", "bh_test_calmar", "test_max_drawdown", "number_of_trades"])}

## 5. Top 5 Core Metrics

{_table(best_top5, ["ticker", "template_name", "test_cagr", "test_max_drawdown", "test_calmar", "bh_test_cagr", "bh_test_calmar", "strategy_beats_bh_cagr", "strategy_beats_bh_calmar"])}

## 6. CAGR >= 20% Check

{_table(top_df.loc[:, ["ticker", "test_cagr", "passes_cagr_rule"]])}

## 7. Buy-And-Hold Comparison

Strategies beating buy-and-hold CAGR: {beats_cagr}. Strategies beating buy-and-hold Calmar: {beats_calmar}.

{_table(top_df, ["ticker", "test_cagr", "bh_test_cagr", "strategy_vs_bh_cagr_diff", "test_calmar", "bh_test_calmar", "strategy_vs_bh_calmar_diff", "strategy_beats_bh_cagr", "strategy_beats_bh_calmar", "strategy_beats_bh_both"])}

Buy-and-hold benchmark detail is saved to `benchmark/buyhold_by_ticker.csv`.

{_table(buyhold_df.head(20), ["ticker", "test_cagr", "test_max_drawdown", "test_calmar", "full_cagr", "full_max_drawdown", "full_calmar"])}

## 8. Return Enhancers

These are strategies that beat buy-and-hold CAGR and do not sacrifice Calmar.

{_table(return_enhancer)}

## 9. Risk Reducers

These are strategies where CAGR may trail buy-and-hold, but Calmar and drawdown control improve enough to matter.

{_table(risk_reducer)}

## 10. Historical Winners But Hard To Mine

{_table(hard_to_mine)}

## 11. Parameter Stability Analysis

{_table(parameter_stability_df.head(20), ["ticker", "template_name", "parameter_stability_score", "parameter_island_risk", "nearby_top10_count", "nearby_top20_count", "plateau_share_80pct"])}

## 12. Strict Walk-Forward Result

The walk-forward detail file is `walk_forward/walk_forward_window_detail.csv`; summary is `walk_forward/walk_forward_summary_by_ticker.csv`.

{_table(walk_forward_summary_df.head(20), ["ticker", "wf_fold_count", "wf_pass_rate", "wf_mean_cagr", "wf_mean_calmar", "wf_mean_bh_calmar", "wf_mean_vs_bh_calmar"])}

## 13. Qlib Runtime Status

{_table(pd.DataFrame([qlib_status]))}

## 14. Leveraged ETF Special Review

{_table(leveraged)}

## 15. Rotation Strategy Snapshot

{_table(rotation_df.head(10), ["strategy_name", "params", "cagr", "max_drawdown", "calmar", "average_exposure"])}

## 16. Suspected Overfit Cases

{_table(overfit_risk)}

## 17. Candidates Worth Deeper Research

- Prioritize names with positive `test_calmar`, higher `final_score`, stable walk-forward behavior, and lower `overfit_penalty`.
- Names that work under simple templates and across multiple regimes should be treated as more credible than isolated complex wins.
- If CAGR still does not beat buy-and-hold, treat the strategy as a risk-control candidate only when Calmar and max drawdown improve clearly.

## 18. Next Research Focus

- Do not expand to Nasdaq 100 / S&P 500 yet unless the v2 top candidates show credible return enhancement or risk reduction after cost stress.
- Next priority is improving signal expression, qlib runtime installation/provider setup, and stress-testing the leveraged ETF guardrail.

## Factor Support Snapshot

{_table(factor_rank_df.head(20), ["ticker", "factor_name", "composite_score", "rank_ic", "stability_score"])}
"""
        return save_text(text, report_path)

    def build_html_report(
        self,
        report_path: Path | str,
        top_df: pd.DataFrame,
        best_strategy_df: pd.DataFrame,
        excluded_df: pd.DataFrame,
        final_ranking_df: pd.DataFrame,
    ) -> Path:
        summary = top_df.head(20)
        best_cols = ["ticker", "template_name", "params", "test_cagr", "test_calmar", "test_max_drawdown"]
        excluded_cols = ["ticker", "exclusion_reason"] if not excluded_df.empty else None
        rank_cols = ["ticker", "classification", "final_score", "overfit_penalty"]
        html_body = (
            "<div class='card'><h1>US Stock Selection Report</h1>"
            "<p>This report ranks US tickers by strategy mineability under the current local data, factor coverage, and search framework rather than by raw historical return alone.</p></div>"
            "<div class='card'><h2>Top Candidates</h2>"
            f"{dataframe_to_html(summary, max_rows=20)}</div>"
            "<div class='card'><h2>Best Strategy By Ticker</h2>"
            f"{dataframe_to_html(best_strategy_df.loc[:, best_cols].head(20), max_rows=20)}</div>"
            "<div class='card'><h2>Excluded Tickers</h2>"
            f"{dataframe_to_html(excluded_df.loc[:, excluded_cols].head(20) if excluded_cols else excluded_df, max_rows=20)}</div>"
            "<div class='card'><h2>Classification Snapshot</h2>"
            f"{dataframe_to_html(final_ranking_df.loc[:, rank_cols].head(20), max_rows=20)}</div>"
        )
        return save_text(basic_html_page("US Stock Selection Report", html_body), report_path)

    def build_excel_summary(
        self,
        output_path: Path | str,
        sheets: dict[str, pd.DataFrame],
    ) -> Path:
        return write_excel(sheets, output_path)

    def package_run(
        self,
        run_dir: Path | str,
        timestamp: str,
    ) -> Path:
        base = Path(run_dir).resolve()
        zip_name = f"us_stock_selection_quant_lab_v2_{timestamp}.zip"
        zip_path = base.parent / zip_name
        paths = [
            PROJECT_ROOT / "configs" / "us_stock_selection",
            PROJECT_ROOT / "scripts" / "us_stock_selection",
            PROJECT_ROOT / "quant_lab" / "us_stock_selection",
            PROJECT_ROOT / "README_US_STOCK_SELECTION.md",
            base / "benchmark",
            base / "reports",
            base / "ranking",
            base / "strategy_search",
            base / "factor_screen",
            base / "data_quality",
            base / "walk_forward",
            base / "regime_validation",
            base / "qlib",
            base / "logs",
        ]
        return zip_selected_paths(paths, zip_path, root=PROJECT_ROOT)
