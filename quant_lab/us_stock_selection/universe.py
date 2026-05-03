"""Universe construction for the US stock selection study."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from quant_lab.us_stock_selection.utils import PROJECT_ROOT, load_yaml


def load_universe_definitions(config_dir: Path | str) -> dict[str, dict[str, Any]]:
    directory = Path(config_dir)
    payload: dict[str, dict[str, Any]] = {}
    for path in sorted(directory.glob("universe_*.yaml")):
        data = load_yaml(path)
        payload[data["name"]] = data
    return payload


def build_universe_table(
    universe_names: list[str],
    config_dir: Path | str,
) -> pd.DataFrame:
    definitions = load_universe_definitions(config_dir)
    rows: list[dict[str, Any]] = []
    for universe_name in universe_names:
        if universe_name not in definitions:
            raise KeyError(f"Unknown universe '{universe_name}'. Available: {sorted(definitions)}")
        definition = definitions[universe_name]
        for item in definition.get("tickers", []):
            rows.append(
                {
                    "ticker": str(item["ticker"]).upper(),
                    "universe_name": universe_name,
                    "asset_type": item.get("asset_type", definition.get("asset_type", "equity")),
                    "sector": item.get("sector", ""),
                    "theme": item.get("theme", ""),
                    "is_leveraged": bool(item.get("is_leveraged", False)),
                    "market": "us",
                }
            )
    if not rows:
        return pd.DataFrame(columns=["ticker", "universe_name", "asset_type", "sector", "theme", "is_leveraged", "market"])
    table = pd.DataFrame(rows)
    aggregate = (
        table.groupby("ticker", as_index=False)
        .agg(
            universe_name=("universe_name", lambda values: "|".join(sorted(set(values)))),
            asset_type=("asset_type", "first"),
            sector=("sector", "first"),
            theme=("theme", "first"),
            is_leveraged=("is_leveraged", "max"),
            market=("market", "first"),
        )
        .sort_values("ticker")
        .reset_index(drop=True)
    )
    return aggregate


def apply_quality_filter(
    universe_df: pd.DataFrame,
    quality_df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    merged = universe_df.merge(
        quality_df[
            [
                "ticker",
                "passes_quality",
                "meets_min_length",
                "passes_missing_check",
                "passes_liquidity_check",
                "passes_anomaly_check",
                "possible_adjustment_issue",
            ]
        ],
        how="left",
        on="ticker",
    )
    merged["passes_quality"] = merged["passes_quality"].fillna(False)

    def exclusion_reason(row: pd.Series) -> str:
        if bool(row.get("passes_quality", False)):
            return ""
        reasons: list[str] = []
        if not bool(row.get("meets_min_length", False)):
            reasons.append("history_too_short")
        if not bool(row.get("passes_missing_check", False)):
            reasons.append("missing_rate_too_high")
        if not bool(row.get("passes_liquidity_check", False)):
            reasons.append("liquidity_too_low")
        if not bool(row.get("passes_anomaly_check", False)):
            reasons.append("price_or_return_anomaly")
        if bool(row.get("possible_adjustment_issue", False)):
            reasons.append("possible_adjustment_issue")
        return "|".join(reasons) or "quality_check_failed"

    merged["exclusion_reason"] = merged.apply(exclusion_reason, axis=1)
    eligible = merged.loc[merged["passes_quality"]].copy()
    excluded = merged.loc[~merged["passes_quality"]].copy()
    return eligible.reset_index(drop=True), excluded.reset_index(drop=True)


def load_universe_config_snapshot(config_dir: Path | str) -> dict[str, Any]:
    return load_yaml(Path(config_dir) / "validation_config.yaml")

