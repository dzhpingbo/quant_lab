"""Cross-asset ranking and strategy mineability scoring."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from quant_lab.us_stock_selection.utils import rescale_to_score


class RankingEngine:
    """Combine OOS performance, robustness, factors, and quality into one score."""

    def __init__(self, config: dict[str, Any], logger):
        self.config = config
        self.logger = logger

    def build_final_ranking(
        self,
        best_strategy_df: pd.DataFrame,
        factor_support_df: pd.DataFrame,
        walk_forward_df: pd.DataFrame,
        regime_score_df: pd.DataFrame,
        quality_df: pd.DataFrame,
        universe_df: pd.DataFrame,
        parameter_stability_df: pd.DataFrame | None = None,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        weights = self.config.get("ranking", {}).get("weights", {})
        if best_strategy_df.empty:
            empty = pd.DataFrame()
            return empty, empty

        wf_summary = self._walk_forward_summary(walk_forward_df)
        base_strategy_df = best_strategy_df.copy()
        if parameter_stability_df is not None and not parameter_stability_df.empty:
            drop_cols = [col for col in ("parameter_stability_score", "parameter_island_risk") if col in base_strategy_df.columns]
            base_strategy_df = base_strategy_df.drop(columns=drop_cols)
            parameter_cols = [
                "ticker",
                "parameter_stability_score",
                "parameter_island_risk",
                "nearby_top10_count",
                "nearby_top20_count",
                "plateau_share_80pct",
            ]
            base_strategy_df = base_strategy_df.merge(parameter_stability_df.loc[:, [col for col in parameter_cols if col in parameter_stability_df.columns]], how="left", on="ticker")

        merged = (
            base_strategy_df.merge(factor_support_df, how="left", on="ticker")
            .merge(wf_summary, how="left", on="ticker")
            .merge(regime_score_df, how="left", on="ticker")
            .merge(
                quality_df[
                    [
                        "ticker",
                        "missing_rate",
                        "average_dollar_volume",
                        "passes_quality",
                        "possible_adjustment_issue",
                        "is_leveraged",
                    ]
                ],
                how="left",
                on="ticker",
            )
            .merge(universe_df[["ticker", "universe_name", "asset_type", "theme"]], how="left", on="ticker")
        )

        if "bh_test_cagr" not in merged.columns:
            merged["bh_test_cagr"] = merged.get("benchmark_cagr", 0.0)
        if "bh_test_max_drawdown" not in merged.columns:
            merged["bh_test_max_drawdown"] = merged.get("benchmark_max_drawdown", 0.0)
        if "bh_test_calmar" not in merged.columns:
            merged["bh_test_calmar"] = merged.get("benchmark_calmar", 0.0)
        if "strategy_vs_bh_cagr_diff" not in merged.columns:
            merged["strategy_vs_bh_cagr_diff"] = merged["test_cagr"] - merged["bh_test_cagr"]
        if "strategy_vs_bh_calmar_diff" not in merged.columns:
            merged["strategy_vs_bh_calmar_diff"] = merged["test_calmar"] - merged["bh_test_calmar"]
        merged["strategy_vs_bh_cagr_diff"] = pd.to_numeric(merged["strategy_vs_bh_cagr_diff"], errors="coerce").fillna(0.0)
        merged["strategy_vs_bh_calmar_diff"] = pd.to_numeric(merged["strategy_vs_bh_calmar_diff"], errors="coerce").fillna(0.0)
        if "strategy_beats_bh_cagr" not in merged.columns:
            merged["strategy_beats_bh_cagr"] = merged["strategy_vs_bh_cagr_diff"] > 0.0
        if "strategy_beats_bh_calmar" not in merged.columns:
            merged["strategy_beats_bh_calmar"] = merged["strategy_vs_bh_calmar_diff"] > 0.0
        if "strategy_beats_bh_both" not in merged.columns:
            merged["strategy_beats_bh_both"] = merged["strategy_beats_bh_cagr"] & merged["strategy_beats_bh_calmar"]
        merged["strategy_beats_bh_cagr"] = merged["strategy_beats_bh_cagr"].fillna(False).astype(bool)
        merged["strategy_beats_bh_calmar"] = merged["strategy_beats_bh_calmar"].fillna(False).astype(bool)
        merged["strategy_beats_bh_both"] = merged["strategy_beats_bh_both"].fillna(False).astype(bool)

        merged["oos_calmar_score"] = rescale_to_score(merged["test_calmar"], higher_is_better=True)
        merged["cagr_score"] = rescale_to_score(merged["test_cagr"], higher_is_better=True)
        merged["drawdown_score"] = rescale_to_score(merged["test_max_drawdown"].abs(), higher_is_better=False)
        merged["robustness_score"] = rescale_to_score(merged["robustness_score_raw"].fillna(0.0), higher_is_better=True)
        merged["strategy_vs_bh_calmar_score"] = rescale_to_score(merged["strategy_vs_bh_calmar_diff"].fillna(0.0), higher_is_better=True)
        if "parameter_stability_score" not in merged.columns:
            merged["parameter_stability_score"] = 50.0
        merged["parameter_stability_score"] = pd.to_numeric(merged["parameter_stability_score"], errors="coerce").fillna(50.0).clip(lower=0.0, upper=100.0)
        if "parameter_island_risk" not in merged.columns:
            merged["parameter_island_risk"] = False
        merged["parameter_island_risk"] = merged["parameter_island_risk"].fillna(False).astype(bool)
        merged["factor_support_score"] = rescale_to_score(merged["factor_support_score_raw"].fillna(0.0), higher_is_better=True)
        merged["regime_score"] = rescale_to_score(merged["regime_score_raw"].fillna(0.0), higher_is_better=True)
        merged["simplicity_score"] = rescale_to_score(-merged["strategy_complexity"], higher_is_better=True)
        merged["liquidity_score"] = rescale_to_score(merged["average_dollar_volume"].fillna(0.0), higher_is_better=True)

        decay = (merged["valid_calmar"] - merged["test_calmar"]).clip(lower=0.0).fillna(0.0)
        merged["overfit_penalty"] = (
            8.0 * merged["spike_prone"].fillna(False).astype(float)
            + 8.0 * merged["parameter_island_risk"].fillna(False).astype(float)
            + 8.0 * (merged["number_of_trades"] < float(self.config.get("selection_rules", {}).get("min_oos_trades", 20))).astype(float)
            + 8.0 * rescale_to_score(decay, higher_is_better=True).div(100.0)
            + 6.0 * (merged["test_cagr"] < float(self.config.get("selection_rules", {}).get("min_oos_cagr", 0.2))).astype(float)
        )
        merged["data_quality_penalty"] = (
            10.0 * merged["missing_rate"].fillna(1.0).clip(lower=0.0, upper=1.0)
            + 5.0 * merged["possible_adjustment_issue"].fillna(False).astype(float)
            + 4.0 * (~merged["passes_quality"].fillna(False)).astype(float)
        )
        merged["leverage_penalty"] = merged["is_leveraged"].fillna(False).astype(float) * float(
            self.config.get("ranking", {}).get("leverage_penalty", 3.0)
        )

        merged["final_score"] = (
            float(weights.get("oos_calmar_score", 0.25)) * merged["oos_calmar_score"]
            + float(weights.get("cagr_score", 0.15)) * merged["cagr_score"]
            + float(weights.get("robustness_score", 0.15)) * merged["robustness_score"]
            + float(weights.get("strategy_vs_bh_calmar_score", 0.10)) * merged["strategy_vs_bh_calmar_score"]
            + float(weights.get("parameter_stability_score", 0.10)) * merged["parameter_stability_score"]
            + float(weights.get("factor_support_score", 0.10)) * merged["factor_support_score"]
            + float(weights.get("regime_score", 0.10)) * merged["regime_score"]
            + float(weights.get("simplicity_score", 0.05)) * merged["simplicity_score"]
            - merged["overfit_penalty"]
            - merged["data_quality_penalty"]
            - merged["leverage_penalty"]
        )

        merged["historical_cagr_rank"] = merged["bh_test_cagr"].rank(method="min", ascending=False)
        merged["mineability_rank"] = merged["final_score"].rank(method="min", ascending=False)
        merged["robustness_rank"] = merged["robustness_score"].rank(method="min", ascending=False)
        risk_reducer = (
            (~merged["strategy_beats_bh_cagr"])
            & (merged["strategy_vs_bh_calmar_diff"] > 0.15)
            & (merged["test_max_drawdown"].abs() <= merged["bh_test_max_drawdown"].abs() * 0.85)
        )
        merged["classification"] = np.select(
            [
                merged["strategy_beats_bh_both"],
                risk_reducer,
                (merged["robustness_score"] >= 70.0) & (merged["parameter_stability_score"] >= 60.0) & (merged["test_calmar"] > 0.0),
                (merged["historical_cagr_rank"] <= max(5, len(merged) * 0.2)) & (~merged["strategy_beats_bh_calmar"]),
                (merged["overfit_penalty"] >= 12.0) | merged["parameter_island_risk"],
            ],
            [
                "return_enhancer",
                "risk_reducer",
                "strategy_friendly",
                "historical_winner_hard_to_mine",
                "overfit_suspect",
            ],
            default="reject_for_now",
        )

        final_df = merged.sort_values(["final_score", "test_calmar", "test_cagr"], ascending=[False, False, False]).reset_index(drop=True)
        top_n = int(self.config.get("reporting", {}).get("top_n", 20))
        top_df = final_df.head(top_n).copy()
        return final_df, top_df

    def _walk_forward_summary(self, walk_forward_df: pd.DataFrame) -> pd.DataFrame:
        if walk_forward_df.empty:
            return pd.DataFrame(columns=["ticker", "wf_fold_count", "wf_pass_rate", "wf_mean_calmar", "wf_mean_cagr", "robustness_score_raw"])
        grouped = walk_forward_df.groupby("ticker").agg(
            wf_fold_count=("fold", "count"),
            wf_pass_rate=("pass_fold", "mean"),
            wf_mean_calmar=("test_calmar", "mean"),
            wf_mean_cagr=("test_cagr", "mean"),
        )
        grouped["robustness_score_raw"] = (
            40.0 * grouped["wf_pass_rate"].fillna(0.0)
            + 35.0 * grouped["wf_mean_calmar"].clip(lower=0.0)
            + 25.0 * grouped["wf_mean_cagr"].clip(lower=0.0)
        ).clip(lower=0.0, upper=100.0)
        return grouped.reset_index()
