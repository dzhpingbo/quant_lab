"""Train/valid/test, walk-forward, and regime validation helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from quant_lab.us_stock_selection.strategy_templates import expand_template_grid
from quant_lab.us_stock_selection.utils import annualized_return, calmar_ratio, max_drawdown, nav_from_returns, parse_params


@dataclass(frozen=True)
class TimeSplit:
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    valid_start: pd.Timestamp
    valid_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp
    mode: str


def build_time_split(index: pd.Index, config: dict[str, Any]) -> TimeSplit:
    dates = pd.DatetimeIndex(index).sort_values()
    if len(dates) == 0:
        raise ValueError("Cannot split an empty date index.")

    val_cfg = config.get("validation", {})
    preferred = {
        "train_start": pd.Timestamp(val_cfg.get("preferred_train_start", dates.min())),
        "train_end": pd.Timestamp(val_cfg.get("preferred_train_end", dates.max())),
        "valid_start": pd.Timestamp(val_cfg.get("preferred_valid_start", dates.min())),
        "valid_end": pd.Timestamp(val_cfg.get("preferred_valid_end", dates.max())),
        "test_start": pd.Timestamp(val_cfg.get("preferred_test_start", dates.min())),
        "test_end": pd.Timestamp(val_cfg.get("preferred_test_end", dates.max())),
    }
    if preferred["train_start"] >= dates.min() and preferred["test_end"] <= dates.max():
        candidate = TimeSplit(
            train_start=max(preferred["train_start"], dates.min()),
            train_end=min(preferred["train_end"], dates.max()),
            valid_start=max(preferred["valid_start"], dates.min()),
            valid_end=min(preferred["valid_end"], dates.max()),
            test_start=max(preferred["test_start"], dates.min()),
            test_end=min(preferred["test_end"], dates.max()),
            mode="preferred_dates",
        )
        if candidate.train_start < candidate.train_end < candidate.valid_start < candidate.valid_end < candidate.test_start < candidate.test_end:
            return candidate

    n = len(dates)
    train_end_idx = max(int(n * 0.6), 1)
    valid_end_idx = max(int(n * 0.8), train_end_idx + 1)
    return TimeSplit(
        train_start=dates[0],
        train_end=dates[train_end_idx - 1],
        valid_start=dates[train_end_idx],
        valid_end=dates[valid_end_idx - 1],
        test_start=dates[valid_end_idx],
        test_end=dates[-1],
        mode="ratio_fallback",
    )


def evaluate_segment(
    returns: pd.Series,
    benchmark_returns: pd.Series,
    position: pd.Series,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> dict[str, float]:
    seg_returns = returns.loc[(returns.index >= start) & (returns.index <= end)].fillna(0.0)
    seg_bench = benchmark_returns.loc[(benchmark_returns.index >= start) & (benchmark_returns.index <= end)].fillna(0.0)
    seg_pos = position.loc[(position.index >= start) & (position.index <= end)].fillna(0.0)
    if seg_returns.empty:
        return {
            "cagr": 0.0,
            "calmar": 0.0,
            "max_drawdown": 0.0,
            "exposure": 0.0,
            "trades_proxy": 0.0,
            "benchmark_cagr": 0.0,
            "benchmark_max_drawdown": 0.0,
            "benchmark_calmar": 0.0,
        }
    seg_nav = nav_from_returns(seg_returns)
    seg_bench_nav = nav_from_returns(seg_bench)
    bench_dd = max_drawdown(seg_bench_nav)
    return {
        "cagr": annualized_return(seg_returns),
        "calmar": calmar_ratio(seg_returns),
        "max_drawdown": max_drawdown(seg_nav),
        "exposure": float(seg_pos.mean()),
        "trades_proxy": float(seg_pos.diff().abs().sum() / 2.0),
        "benchmark_cagr": annualized_return(seg_bench),
        "benchmark_max_drawdown": bench_dd,
        "benchmark_calmar": annualized_return(seg_bench) / abs(bench_dd) if bench_dd != 0 else 0.0,
    }


class ValidationEngine:
    """Run walk-forward and regime validation using selected strategy templates."""

    def __init__(self, config: dict[str, Any], logger):
        self.config = config
        self.logger = logger

    def walk_forward_validate(
        self,
        ticker: str,
        frame: pd.DataFrame,
        market_context: pd.DataFrame,
        asset_meta: dict[str, Any],
        best_strategy_row: pd.Series,
        adapter,
        search_space: dict[str, Any],
    ) -> pd.DataFrame:
        cfg = self.config.get("walk_forward", {})
        train_days = int(cfg.get("train_days", 756))
        test_days = int(cfg.get("test_days", 126))
        anchored = bool(cfg.get("anchored_expanding", True))
        strict_walk_forward = bool(cfg.get("strict_parameter_selection", True))
        candidate_specs = self._walk_forward_candidate_specs(
            ticker=ticker,
            asset_meta=asset_meta,
            best_strategy_row=best_strategy_row,
            search_space=search_space,
            strict_walk_forward=strict_walk_forward,
        )

        rows: list[dict[str, Any]] = []
        dates = pd.DatetimeIndex(frame.index)
        fold = 0
        start = 0
        while start + train_days + test_days <= len(dates):
            fold += 1
            train_start = 0 if anchored else start
            train_end = start + train_days
            test_end = train_end + test_days
            train_slice = dates[train_start:train_end]
            test_slice = dates[train_end:test_end]

            best_train_score = -np.inf
            best_params: dict[str, Any] | None = None
            best_template: str | None = None
            best_train_metrics: dict[str, float] = {}
            candidate_count = sum(len(param_grid) for _template, param_grid in candidate_specs)
            self.logger.info(f"Walk-forward {ticker} fold {fold}: testing {candidate_count} historical parameter set(s)")
            for candidate_template, param_grid in candidate_specs:
                for params in param_grid:
                    train_bundle = adapter.run_backtest(
                        ticker=ticker,
                        frame=frame.loc[: train_slice[-1]],
                        market_context=market_context.loc[: train_slice[-1]],
                        template_name=candidate_template,
                        params=dict(params),
                        asset_meta=asset_meta,
                    )
                    train_metrics = evaluate_segment(
                        train_bundle.returns,
                        train_bundle.benchmark_returns,
                        train_bundle.position,
                        train_slice[0],
                        train_slice[-1],
                    )
                    score = train_metrics["calmar"] + 0.5 * train_metrics["cagr"]
                    if score > best_train_score:
                        best_train_score = score
                        best_params = dict(params)
                        best_template = candidate_template
                        best_train_metrics = train_metrics

            if best_params is None or best_template is None:
                start += test_days
                continue

            best_bundle = adapter.run_backtest(
                ticker=ticker,
                frame=frame.loc[: test_slice[-1]],
                market_context=market_context.loc[: test_slice[-1]],
                template_name=best_template,
                params=dict(best_params),
                asset_meta=asset_meta,
            )
            test_metrics = evaluate_segment(
                best_bundle.returns,
                best_bundle.benchmark_returns,
                best_bundle.position,
                test_slice[0],
                test_slice[-1],
            )
            rows.append(
                {
                    "ticker": ticker,
                    "fold": fold,
                    "mode": "anchored" if anchored else "rolling",
                    "strict_parameter_selection": strict_walk_forward,
                    "selected_strategy": best_template,
                    "template_name": best_template,
                    "selected_params": str(best_params),
                    "train_start": train_slice[0].date().isoformat(),
                    "train_end": train_slice[-1].date().isoformat(),
                    "test_start": test_slice[0].date().isoformat(),
                    "test_end": test_slice[-1].date().isoformat(),
                    "train_calmar": best_train_metrics.get("calmar", best_train_score),
                    "train_cagr": best_train_metrics.get("cagr", 0.0),
                    "test_cagr": test_metrics["cagr"],
                    "test_calmar": test_metrics["calmar"],
                    "test_maxdd": test_metrics["max_drawdown"],
                    "test_max_drawdown": test_metrics["max_drawdown"],
                    "test_exposure": test_metrics["exposure"],
                    "test_trades": test_metrics["trades_proxy"],
                    "test_trades_proxy": test_metrics["trades_proxy"],
                    "bh_test_cagr": test_metrics["benchmark_cagr"],
                    "bh_test_calmar": test_metrics["benchmark_calmar"],
                    "strategy_vs_bh_calmar_diff": test_metrics["calmar"] - test_metrics["benchmark_calmar"],
                    "pass_fold": bool(
                        test_metrics["cagr"] >= float(self.config.get("selection_rules", {}).get("min_oos_cagr", 0.2))
                        and abs(test_metrics["max_drawdown"]) <= float(self.config.get("selection_rules", {}).get("max_oos_drawdown", 0.5))
                    ),
                }
            )
            start += test_days

        return pd.DataFrame(rows)

    def _walk_forward_candidate_specs(
        self,
        ticker: str,
        asset_meta: dict[str, Any],
        best_strategy_row: pd.Series,
        search_space: dict[str, Any],
        strict_walk_forward: bool,
    ) -> list[tuple[str, list[dict[str, Any]]]]:
        cfg = self.config.get("walk_forward", {})
        if not strict_walk_forward:
            template_name = str(best_strategy_row["template_name"])
            return [(template_name, [parse_params(best_strategy_row.get("params", {}))])]

        max_per_template = int(cfg.get("max_combinations_per_template", 8))
        max_total = int(cfg.get("max_total_parameter_sets", 48))
        specs: list[tuple[str, list[dict[str, Any]]]] = []
        used = 0
        for candidate_template, template_cfg in search_space.items():
            if not self._template_applies(template_cfg, asset_meta, ticker):
                continue
            grid = expand_template_grid(candidate_template, search_space)
            if not grid:
                continue
            if max_per_template > 0 and len(grid) > max_per_template:
                idx = np.linspace(0, len(grid) - 1, max_per_template).round().astype(int)
                grid = [grid[int(i)] for i in sorted(set(idx))]
            remaining = max_total - used if max_total > 0 else len(grid)
            if remaining <= 0:
                break
            grid = grid[:remaining]
            specs.append((candidate_template, grid))
            used += len(grid)
        if not specs:
            template_name = str(best_strategy_row["template_name"])
            specs = [(template_name, [parse_params(best_strategy_row.get("params", {}))])]
        return specs

    @staticmethod
    def _template_applies(template_cfg: dict[str, Any], asset_meta: dict[str, Any], ticker: str) -> bool:
        if not bool(template_cfg.get("enabled", True)):
            return False
        applies = template_cfg.get("applies_to", {}) or {}
        tickers = set(str(item).upper() for item in applies.get("tickers", []))
        if tickers and str(ticker).upper() not in tickers:
            return False
        if bool(applies.get("leveraged_only", False)) and not bool(asset_meta.get("is_leveraged", False)):
            return False
        asset_types = set(str(item).lower() for item in applies.get("asset_types", []))
        if asset_types and str(asset_meta.get("asset_type", "")).lower() not in asset_types:
            return False
        return True

    def walk_forward_summary(self, walk_forward_df: pd.DataFrame) -> pd.DataFrame:
        if walk_forward_df.empty:
            return pd.DataFrame(columns=["ticker", "wf_fold_count", "wf_pass_rate", "wf_mean_calmar", "wf_mean_cagr", "wf_mean_bh_calmar"])
        grouped = walk_forward_df.groupby("ticker").agg(
            wf_fold_count=("fold", "count"),
            wf_pass_rate=("pass_fold", "mean"),
            wf_mean_calmar=("test_calmar", "mean"),
            wf_mean_cagr=("test_cagr", "mean"),
            wf_mean_bh_calmar=("bh_test_calmar", "mean"),
            wf_mean_vs_bh_calmar=("strategy_vs_bh_calmar_diff", "mean"),
            wf_mean_trades=("test_trades_proxy", "mean"),
        )
        return grouped.reset_index()

    def regime_validate(
        self,
        ticker: str,
        bundle,
        market_context: pd.DataFrame,
    ) -> pd.DataFrame:
        if bundle.returns.empty:
            return pd.DataFrame()
        benchmark = market_context.reindex(bundle.returns.index)
        regime_rows: list[dict[str, Any]] = []
        regime_masks = self._regime_masks(benchmark)
        for regime_name, mask in regime_masks.items():
            seg_returns = bundle.returns.where(mask, 0.0)
            active = mask.fillna(False)
            if int(active.sum()) < 20:
                continue
            nav = nav_from_returns(seg_returns)
            regime_rows.append(
                {
                    "ticker": ticker,
                    "regime": regime_name,
                    "observations": int(active.sum()),
                    "cagr": annualized_return(seg_returns),
                    "calmar": calmar_ratio(seg_returns),
                    "max_drawdown": max_drawdown(nav),
                    "exposure": float(bundle.position.where(active, 0.0).mean()),
                }
            )
        return pd.DataFrame(regime_rows)

    def regime_score(self, regime_df: pd.DataFrame) -> pd.DataFrame:
        if regime_df.empty:
            return pd.DataFrame(columns=["ticker", "regime_score_raw"])
        grouped = regime_df.groupby("ticker").agg(
            mean_regime_calmar=("calmar", "mean"),
            mean_regime_cagr=("cagr", "mean"),
            worst_regime_drawdown=("max_drawdown", "min"),
            regime_count=("regime", "count"),
        )
        grouped["regime_score_raw"] = (
            50.0 * grouped["mean_regime_calmar"].clip(lower=0.0)
            + 30.0 * grouped["mean_regime_cagr"].clip(lower=0.0)
            + 20.0 * (1.0 - grouped["worst_regime_drawdown"].abs().clip(upper=1.0))
        ).clip(lower=0.0, upper=100.0)
        return grouped.reset_index()[["ticker", "regime_score_raw"]]

    @staticmethod
    def _regime_masks(market_context: pd.DataFrame) -> dict[str, pd.Series]:
        qqq_trend = market_context.get("QQQ_trend", pd.Series(index=market_context.index, dtype=float)).fillna(0.0)
        spy_trend = market_context.get("SPY_trend", pd.Series(index=market_context.index, dtype=float)).fillna(0.0)
        tlt_trend = market_context.get("TLT_trend", pd.Series(index=market_context.index, dtype=float)).fillna(0.0)
        realized = market_context.get("benchmark_realized_vol_20", pd.Series(index=market_context.index, dtype=float)).ffill()
        threshold = realized.rolling(252, min_periods=20).median().fillna(realized.median())
        return {
            "bull": (qqq_trend > 0.0) & (spy_trend > 0.0),
            "bear": (qqq_trend <= 0.0) & (spy_trend <= 0.0),
            "high_vol": realized >= threshold,
            "low_vol": realized < threshold,
            "risk_off": (tlt_trend > 0.0) & (qqq_trend <= 0.0),
        }
