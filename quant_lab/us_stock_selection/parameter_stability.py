"""Parameter-neighborhood stability diagnostics for selected strategies."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from quant_lab.us_stock_selection.utils import parse_params


class ParameterStabilityAnalyzer:
    """Estimate whether each best parameter point is supported by nearby high-scoring variants."""

    def __init__(self, config: dict[str, Any], logger):
        self.config = config
        self.logger = logger

    def run(self, all_results_df: pd.DataFrame, best_strategy_df: pd.DataFrame) -> pd.DataFrame:
        if all_results_df.empty or best_strategy_df.empty:
            return pd.DataFrame(
                columns=[
                    "ticker",
                    "template_name",
                    "params",
                    "template_combo_count",
                    "top5_count",
                    "top10_count",
                    "top20_count",
                    "nearby_top10_count",
                    "nearby_top20_count",
                    "parameter_island_risk",
                    "parameter_stability_score",
                ]
            )

        rows: list[dict[str, Any]] = []
        for _, best in best_strategy_df.iterrows():
            ticker = str(best["ticker"])
            template_name = str(best["template_name"])
            subset = all_results_df.loc[
                (all_results_df["ticker"].astype(str) == ticker)
                & (all_results_df["template_name"].astype(str) == template_name)
            ].copy()
            if subset.empty:
                continue

            score_col = "valid_calmar" if "valid_calmar" in subset.columns else "test_calmar"
            subset[score_col] = pd.to_numeric(subset[score_col], errors="coerce").fillna(-np.inf)
            subset = subset.sort_values(score_col, ascending=False).reset_index(drop=True)
            best_params = parse_params(best.get("params", {}))
            subset_params = [parse_params(raw) for raw in subset["params"]]
            distances = pd.Series([_param_distance(best_params, params, subset_params) for params in subset_params], index=subset.index)
            n = len(subset)
            top5_n = max(1, int(np.ceil(n * 0.05)))
            top10_n = max(1, int(np.ceil(n * 0.10)))
            top20_n = max(1, int(np.ceil(n * 0.20)))
            top10_idx = set(subset.head(top10_n).index)
            top20_idx = set(subset.head(top20_n).index)
            neighbor_mask = distances.gt(0.0) & distances.le(1.50)
            nearby_top10_count = int(sum(idx in top10_idx for idx in subset.index[neighbor_mask]))
            nearby_top20_count = int(sum(idx in top20_idx for idx in subset.index[neighbor_mask]))
            top20_near_share = nearby_top20_count / max(top20_n - 1, 1)
            plateau_share = float((subset[score_col] >= float(best.get(score_col, subset[score_col].iloc[0])) * 0.80).mean()) if float(best.get(score_col, 0.0)) > 0 else 0.0
            stability_score = float(np.clip(35.0 * top20_near_share + 35.0 * plateau_share + 30.0 * min(nearby_top10_count / 3.0, 1.0), 0.0, 100.0))
            island_risk = bool(nearby_top10_count == 0 and nearby_top20_count <= 1 and n >= 10)

            rows.append(
                {
                    "ticker": ticker,
                    "template_name": template_name,
                    "params": best.get("params", ""),
                    "score_basis": score_col,
                    "template_combo_count": n,
                    "top5_count": top5_n,
                    "top10_count": top10_n,
                    "top20_count": top20_n,
                    "nearby_top10_count": nearby_top10_count,
                    "nearby_top20_count": nearby_top20_count,
                    "plateau_share_80pct": plateau_share,
                    "parameter_island_risk": island_risk,
                    "parameter_stability_score": stability_score,
                }
            )

        return pd.DataFrame(rows).sort_values(["parameter_stability_score", "ticker"], ascending=[False, True]).reset_index(drop=True)


def _param_distance(best_params: dict[str, Any], params: dict[str, Any], all_params: list[dict[str, Any]]) -> float:
    keys = sorted(set(best_params) | set(params))
    if not keys:
        return 0.0
    distance = 0.0
    for key in keys:
        left = best_params.get(key)
        right = params.get(key)
        if left == right:
            continue
        values = [item.get(key) for item in all_params if key in item]
        numeric_values = [float(v) for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
        if isinstance(left, (int, float)) and isinstance(right, (int, float)) and numeric_values:
            unique = sorted(set(numeric_values))
            if len(unique) >= 2:
                diffs = [b - a for a, b in zip(unique[:-1], unique[1:]) if b > a]
                step = min(diffs) if diffs else max(abs(max(unique) - min(unique)), 1.0)
            else:
                step = max(abs(unique[0]), 1.0)
            distance += abs(float(left) - float(right)) / max(step, 1e-12)
        else:
            distance += 1.0
    return float(distance)
