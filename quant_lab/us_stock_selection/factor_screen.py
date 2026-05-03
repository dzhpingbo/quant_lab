"""Factor registry adapter and per-ticker factor screening."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from src.factors import SAFETY_FACTORS, list_external_panel_factors
from src.factors.liquidity import LIQUIDITY_FACTORS
from src.factors.momentum import MOMENTUM_FACTORS
from src.factors.quality import QUALITY_FACTORS
from src.factors.reversal import REVERSAL_FACTORS
from src.factors.valuation import VALUATION_FACTORS
from src.factors.volatility import VOLATILITY_FACTORS


@dataclass(frozen=True)
class FactorScoreRecord:
    ticker: str
    factor_name: str
    ic: float
    rank_ic: float
    icir: float
    mutual_information: float
    quantile_spread: float
    stability_score: float
    decay_score: float
    missing_rate: float
    outlier_rate: float
    composite_score: float
    is_effective: bool
    is_stable_effective: bool


class FactorRegistryAdapter:
    """Unify local feature, factor-object, and archived external factor names."""

    def __init__(self, feature_columns: list[str] | None = None):
        self.local_factor_objects = {
            **MOMENTUM_FACTORS,
            **REVERSAL_FACTORS,
            **VOLATILITY_FACTORS,
            **LIQUIDITY_FACTORS,
            **QUALITY_FACTORS,
            **VALUATION_FACTORS,
        }
        self.safety_factor_objects = SAFETY_FACTORS
        self.feature_columns = set(feature_columns or [])
        self.external_factor_names = set(list_external_panel_factors())

    def list_available(self) -> list[str]:
        return sorted(
            set(self.local_factor_objects)
            | set(self.safety_factor_objects)
            | self.external_factor_names
            | self.feature_columns
        )

    def classify(self, name: str) -> str:
        if name in self.feature_columns:
            return "feature_frame"
        if name in self.local_factor_objects:
            return "local_factor"
        if name in self.safety_factor_objects:
            return "safety_factor"
        if name in self.external_factor_names:
            return "external_panel_factor"
        return "unknown"


class FactorScreenEngine:
    """Evaluate factor predictiveness and stability per ticker."""

    def __init__(self, config: dict[str, Any], logger):
        self.config = config
        self.logger = logger
        self.factor_cfg = config.get("factor_screen", {})

    def run(
        self,
        feature_map: dict[str, pd.DataFrame],
        selected_factors: list[str],
    ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        ic_rows: list[dict[str, Any]] = []
        ranked_rows: list[dict[str, Any]] = []
        support_rows: list[dict[str, Any]] = []

        for ticker, feature_df in feature_map.items():
            ticker_rows: list[FactorScoreRecord] = []
            for factor_name in selected_factors:
                if factor_name not in feature_df.columns:
                    continue
                record = self._score_one_factor(ticker, factor_name, feature_df)
                if record is None:
                    continue
                ticker_rows.append(record)
                ic_rows.append(record.__dict__)

            if not ticker_rows:
                support_rows.append(
                    {
                        "ticker": ticker,
                        "effective_factor_count": 0,
                        "stable_effective_factor_count": 0,
                        "top_factor_name": "",
                        "top_factor_score": 0.0,
                        "direction_consistency": 0.0,
                        "factor_support_score_raw": 0.0,
                    }
                )
                continue

            ticker_df = pd.DataFrame([row.__dict__ for row in ticker_rows]).sort_values(
                ["composite_score", "rank_ic"],
                ascending=[False, False],
            )
            ticker_df["rank_within_ticker"] = np.arange(1, len(ticker_df) + 1)
            ranked_rows.extend(ticker_df.head(20).to_dict(orient="records"))

            effective_count = int(ticker_df["is_effective"].sum())
            stable_count = int(ticker_df["is_stable_effective"].sum())
            direction_consistency = float((ticker_df["rank_ic"] > 0).mean())
            factor_support_raw = (
                0.35 * min(stable_count / max(len(ticker_df), 1), 1.0)
                + 0.25 * min(effective_count / max(len(ticker_df), 1), 1.0)
                + 0.20 * min(float(ticker_df["composite_score"].head(5).mean()) / 100.0, 1.0)
                + 0.20 * direction_consistency
            )
            support_rows.append(
                {
                    "ticker": ticker,
                    "effective_factor_count": effective_count,
                    "stable_effective_factor_count": stable_count,
                    "top_factor_name": ticker_df.iloc[0]["factor_name"],
                    "top_factor_score": float(ticker_df.iloc[0]["composite_score"]),
                    "direction_consistency": direction_consistency,
                    "factor_support_score_raw": factor_support_raw * 100.0,
                }
            )

        ic_df = pd.DataFrame(ic_rows)
        if not ic_df.empty:
            ic_df = ic_df.sort_values(["ticker", "composite_score"], ascending=[True, False]).reset_index(drop=True)

        rank_df = pd.DataFrame(ranked_rows)
        if not rank_df.empty:
            rank_df = rank_df.sort_values(["ticker", "rank_within_ticker"]).reset_index(drop=True)

        support_df = pd.DataFrame(support_rows)
        if not support_df.empty:
            support_df = support_df.sort_values("ticker").reset_index(drop=True)
        return ic_df, rank_df, support_df

    def _score_one_factor(
        self,
        ticker: str,
        factor_name: str,
        feature_df: pd.DataFrame,
    ) -> FactorScoreRecord | None:
        target_col = self.factor_cfg.get("target_label", "risk_adjusted_label")
        factor = feature_df[factor_name].replace([np.inf, -np.inf], np.nan)
        label = feature_df[target_col].replace([np.inf, -np.inf], np.nan)
        valid = factor.notna() & label.notna()
        if int(valid.sum()) < int(self.factor_cfg.get("min_samples", 80)):
            return None

        factor_valid = factor.loc[valid]
        label_valid = label.loc[valid]

        ic = float(factor_valid.corr(label_valid))
        rank_ic = float(factor_valid.rank().corr(label_valid.rank()))
        chunk = int(self.factor_cfg.get("chunk_size", 63))
        chunk_scores = []
        for start in range(0, len(factor_valid), chunk):
            sub_factor = factor_valid.iloc[start : start + chunk]
            sub_label = label_valid.iloc[start : start + chunk]
            if len(sub_factor) < 15:
                continue
            chunk_scores.append(float(sub_factor.rank().corr(sub_label.rank())))
        if len(chunk_scores) >= 2 and np.nanstd(chunk_scores) > 0:
            icir = float(np.nanmean(chunk_scores) / np.nanstd(chunk_scores))
            stability_score = float((np.array(chunk_scores) > 0).mean())
        else:
            icir = 0.0
            stability_score = 0.0

        quantiles = pd.qcut(factor_valid.rank(method="first"), q=5, labels=False, duplicates="drop")
        grouped = label_valid.groupby(quantiles).mean()
        quantile_spread = float(grouped.iloc[-1] - grouped.iloc[0]) if len(grouped) >= 2 else 0.0

        decay_scores = []
        for horizon in (5, 10, 20, 60):
            horizon_col = f"forward_return_{horizon}d"
            if horizon_col not in feature_df.columns:
                continue
            horizon_label = feature_df.loc[valid, horizon_col].replace([np.inf, -np.inf], np.nan)
            valid_horizon = factor_valid.notna() & horizon_label.notna()
            if int(valid_horizon.sum()) < 30:
                continue
            decay_scores.append(float(factor_valid.loc[valid_horizon].rank().corr(horizon_label.loc[valid_horizon].rank())))
        decay_score = float(np.nanmean(np.abs(decay_scores))) if decay_scores else 0.0

        mutual_information = 0.0
        try:
            from sklearn.feature_selection import mutual_info_regression

            mutual_information = float(
                mutual_info_regression(
                    factor_valid.to_numpy().reshape(-1, 1),
                    label_valid.to_numpy(),
                    random_state=42,
                )[0]
            )
        except Exception:
            mutual_information = 0.0

        factor_mean = float(factor_valid.mean())
        factor_std = float(factor_valid.std(ddof=0))
        if factor_std == 0:
            outlier_rate = 0.0
        else:
            outlier_rate = float(((factor_valid - factor_mean).abs() > 3.0 * factor_std).mean())
        missing_rate = float(feature_df[factor_name].isna().mean())

        composite_score = (
            25.0 * np.clip(abs(rank_ic), 0.0, 1.0)
            + 15.0 * np.clip(abs(ic), 0.0, 1.0)
            + 15.0 * np.clip(icir / 3.0, -1.0, 1.0)
            + 10.0 * np.clip(mutual_information / 0.1, 0.0, 1.0)
            + 10.0 * np.clip(abs(quantile_spread) / 0.15, 0.0, 1.0)
            + 10.0 * stability_score
            + 10.0 * np.clip(decay_score / 0.2, 0.0, 1.0)
            + 5.0 * (1.0 - min(missing_rate, 1.0))
        )
        composite_score -= 5.0 * min(outlier_rate * 10.0, 1.0)
        is_effective = abs(rank_ic) >= float(self.factor_cfg.get("min_abs_rank_ic", 0.03))
        is_stable_effective = bool(is_effective and stability_score >= float(self.factor_cfg.get("min_stability_score", 0.55)))

        return FactorScoreRecord(
            ticker=ticker,
            factor_name=factor_name,
            ic=ic,
            rank_ic=rank_ic,
            icir=icir,
            mutual_information=mutual_information,
            quantile_spread=quantile_spread,
            stability_score=stability_score,
            decay_score=decay_score,
            missing_rate=missing_rate,
            outlier_rate=outlier_rate,
            composite_score=float(composite_score),
            is_effective=is_effective,
            is_stable_effective=is_stable_effective,
        )
