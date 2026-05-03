"""Buy-and-hold benchmark metrics for per-ticker strategy audits."""

from __future__ import annotations

from typing import Any

import pandas as pd

from quant_lab.us_stock_selection.utils import annualized_volatility, nav_from_returns
from quant_lab.us_stock_selection.validation import build_time_split, evaluate_segment


class BuyHoldAnalyzer:
    """Compute train/valid/test/full buy-and-hold metrics for each ticker."""

    def __init__(self, config: dict[str, Any], logger):
        self.config = config
        self.logger = logger

    def run(
        self,
        universe_df: pd.DataFrame,
        loaded_data: dict[str, pd.DataFrame],
    ) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        meta = universe_df.set_index("ticker").to_dict(orient="index") if not universe_df.empty else {}

        for ticker in universe_df.get("ticker", []):
            frame = loaded_data.get(ticker, pd.DataFrame())
            if frame.empty:
                continue
            close = frame["adj_close"].fillna(frame["close"]).astype(float)
            returns = close.pct_change(fill_method=None).fillna(0.0)
            position = pd.Series(1.0, index=returns.index)
            split = build_time_split(returns.index, self.config)

            train = evaluate_segment(returns, returns, position, split.train_start, split.train_end)
            valid = evaluate_segment(returns, returns, position, split.valid_start, split.valid_end)
            test = evaluate_segment(returns, returns, position, split.test_start, split.test_end)
            full = evaluate_segment(returns, returns, position, returns.index.min(), returns.index.max())
            test_returns = returns.loc[(returns.index >= split.test_start) & (returns.index <= split.test_end)].fillna(0.0)
            test_nav = nav_from_returns(test_returns)

            rows.append(
                {
                    "ticker": ticker,
                    "universe_name": meta.get(ticker, {}).get("universe_name", ""),
                    "asset_type": meta.get(ticker, {}).get("asset_type", ""),
                    "is_leveraged": bool(meta.get(ticker, {}).get("is_leveraged", False)),
                    "train_cagr": train["cagr"],
                    "train_max_drawdown": train["max_drawdown"],
                    "train_calmar": train["calmar"],
                    "valid_cagr": valid["cagr"],
                    "valid_max_drawdown": valid["max_drawdown"],
                    "valid_calmar": valid["calmar"],
                    "test_cagr": test["cagr"],
                    "test_max_drawdown": test["max_drawdown"],
                    "test_calmar": test["calmar"],
                    "full_cagr": full["cagr"],
                    "full_max_drawdown": full["max_drawdown"],
                    "full_calmar": full["calmar"],
                    "test_total_return": float(test_nav.iloc[-1] - 1.0) if not test_nav.empty else 0.0,
                    "test_volatility": annualized_volatility(test_returns),
                    "test_benchmark_exposure": 1.0,
                    "split_mode": split.mode,
                    "test_start": split.test_start.date().isoformat(),
                    "test_end": split.test_end.date().isoformat(),
                }
            )

        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(rows).sort_values("ticker").reset_index(drop=True)


def attach_buyhold_comparison(strategy_df: pd.DataFrame, buyhold_df: pd.DataFrame) -> pd.DataFrame:
    """Attach v2 buy-and-hold deltas to a strategy result table."""
    if strategy_df.empty:
        return strategy_df
    out = strategy_df.copy()
    if buyhold_df.empty:
        for col in (
            "bh_test_cagr",
            "bh_test_max_drawdown",
            "bh_test_calmar",
            "strategy_vs_bh_cagr_diff",
            "strategy_vs_bh_calmar_diff",
            "strategy_beats_bh_cagr",
            "strategy_beats_bh_calmar",
            "strategy_beats_bh_both",
        ):
            out[col] = False if col.startswith("strategy_beats") else 0.0
        return out

    bh = buyhold_df.rename(
        columns={
            "test_cagr": "bh_test_cagr",
            "test_max_drawdown": "bh_test_max_drawdown",
            "test_calmar": "bh_test_calmar",
        }
    )[["ticker", "bh_test_cagr", "bh_test_max_drawdown", "bh_test_calmar"]]
    out = out.drop(
        columns=[
            "bh_test_cagr",
            "bh_test_max_drawdown",
            "bh_test_calmar",
            "strategy_vs_bh_cagr_diff",
            "strategy_vs_bh_calmar_diff",
            "strategy_beats_bh_cagr",
            "strategy_beats_bh_calmar",
            "strategy_beats_bh_both",
        ],
        errors="ignore",
    )
    out = out.merge(bh, how="left", on="ticker")
    out["strategy_vs_bh_cagr_diff"] = out["test_cagr"].fillna(0.0) - out["bh_test_cagr"].fillna(0.0)
    out["strategy_vs_bh_calmar_diff"] = out["test_calmar"].fillna(0.0) - out["bh_test_calmar"].fillna(0.0)
    out["strategy_beats_bh_cagr"] = out["strategy_vs_bh_cagr_diff"] > 0.0
    out["strategy_beats_bh_calmar"] = out["strategy_vs_bh_calmar_diff"] > 0.0
    out["strategy_beats_bh_both"] = out["strategy_beats_bh_cagr"] & out["strategy_beats_bh_calmar"]
    out["beats_buy_and_hold"] = out["strategy_beats_bh_cagr"]
    return out
