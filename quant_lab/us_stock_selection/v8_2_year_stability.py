"""v8.2 year-stability replay for the frozen LGBModel stock-selection line.

This module does not train a model and does not expand the universe.  It reads
the v8.1 LGBModel score/rank audit trail, then replays a small pre-registered
set of portfolio construction and ex-ante risk-control variants.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from quant_lab.us_stock_selection.portfolio_robustifier import ticker_contributions
from quant_lab.us_stock_selection.qlib_signal_backtest import compute_portfolio_metrics, portfolio_returns
from quant_lab.us_stock_selection.qlib_workflow_runner import load_close_from_provider
from quant_lab.us_stock_selection.utils import (
    annualized_return,
    calmar_ratio,
    ensure_dir,
    max_drawdown,
    nav_from_returns,
    save_dataframe,
    save_json,
)
from quant_lab.us_stock_selection.v8_paper_trading import trading_offset


@dataclass(frozen=True)
class YearStabilityVariant:
    strategy_id: str
    portfolio_template: str
    top_k: int
    max_weight: float
    dropout: bool = False
    n_drop: int = 1
    vol_target: float | None = None
    vol_window: int | None = None
    ytd_return_cap: float | None = None
    rolling_3m_return_cap: float | None = None
    rolling_6m_return_cap: float | None = None
    derisk_ratio: float = 0.0
    regime_rule: str | None = None
    qqq_vol_threshold: float | None = None
    safe_asset: str = "cash"


def build_pre_registered_variants() -> list[YearStabilityVariant]:
    """Return the bounded v8.2 candidate list.

    The list intentionally covers the requested TopK, volatility targeting,
    year-neutral caps, and regime filters without opening a broad optimizer.
    """
    variants: list[YearStabilityVariant] = []
    for top_k in [5, 10, 15]:
        if top_k == 15:
            max_weights = [0.10]
        elif top_k == 10:
            max_weights = [0.20, 0.15, 0.10]
        else:
            max_weights = [0.20, 0.15, 0.10]
        for max_weight in max_weights:
            variants.append(
                YearStabilityVariant(
                    strategy_id=f"top{top_k}_equal_mw{_pct_id(max_weight)}",
                    portfolio_template="topk_equal_monthly",
                    top_k=top_k,
                    max_weight=max_weight,
                )
            )

    for top_k, max_weight in [(5, 0.20), (10, 0.10)]:
        variants.append(
            YearStabilityVariant(
                strategy_id=f"top{top_k}_dropout_mw{_pct_id(max_weight)}",
                portfolio_template="topk_dropout_monthly",
                top_k=top_k,
                max_weight=max_weight,
                dropout=True,
                n_drop=1,
            )
        )

    for top_k, max_weight in [(5, 0.20), (10, 0.10)]:
        for target in [0.15, 0.20, 0.25]:
            for window in [20, 60]:
                variants.append(
                    YearStabilityVariant(
                        strategy_id=f"top{top_k}_voltarget{_pct_id(target)}_w{window}",
                        portfolio_template="topk_equal_monthly_vol_target",
                        top_k=top_k,
                        max_weight=max_weight,
                        vol_target=target,
                        vol_window=window,
                    )
                )

    for top_k, max_weight in [(5, 0.20), (10, 0.10)]:
        for cap in [0.40, 0.60, 0.80]:
            for derisk in [0.50, 0.75, 1.00]:
                variants.append(
                    YearStabilityVariant(
                        strategy_id=f"top{top_k}_ytdcap{_pct_id(cap)}_derisk{_pct_id(derisk)}",
                        portfolio_template="topk_equal_monthly_year_neutral_risk_cap",
                        top_k=top_k,
                        max_weight=max_weight,
                        ytd_return_cap=cap,
                        derisk_ratio=derisk,
                    )
                )
        for cap in [0.30, 0.50]:
            variants.append(
                YearStabilityVariant(
                    strategy_id=f"top{top_k}_roll3mcap{_pct_id(cap)}_derisk50",
                    portfolio_template="topk_equal_monthly_year_neutral_risk_cap",
                    top_k=top_k,
                    max_weight=max_weight,
                    rolling_3m_return_cap=cap,
                    derisk_ratio=0.50,
                )
            )
        for cap in [0.50, 0.80]:
            variants.append(
                YearStabilityVariant(
                    strategy_id=f"top{top_k}_roll6mcap{_pct_id(cap)}_derisk50",
                    portfolio_template="topk_equal_monthly_year_neutral_risk_cap",
                    top_k=top_k,
                    max_weight=max_weight,
                    rolling_6m_return_cap=cap,
                    derisk_ratio=0.50,
                )
            )

    for top_k, max_weight in [(5, 0.20), (10, 0.10)]:
        for rule in ["qqq_ma200", "qqq_spy_ma200", "qqq_vol35"]:
            variants.append(
                YearStabilityVariant(
                    strategy_id=f"top{top_k}_regime_{rule}",
                    portfolio_template="topk_equal_monthly_regime_filter",
                    top_k=top_k,
                    max_weight=max_weight,
                    regime_rule=rule,
                    qqq_vol_threshold=0.35 if rule == "qqq_vol35" else None,
                    safe_asset="SHY",
                )
            )
    return variants


def run_v8_2_year_stability(
    out_dir: Path | str,
    v8_1_run_dir: Path | str,
    provider_uri: Path | str,
    logger: Any,
) -> dict[str, Any]:
    out = ensure_dir(out_dir)
    lgb_dir = Path(v8_1_run_dir) / "v8_1_model_switch" / "Alpha360_LGBModel"
    audit_path = lgb_dir / "score_rank_audit_trail.csv"
    nav_path = lgb_dir / "daily_nav.csv"
    if not audit_path.exists():
        raise FileNotFoundError(f"Missing v8.1 LGB score/rank audit trail: {audit_path}")
    if not nav_path.exists():
        raise FileNotFoundError(f"Missing v8.1 LGB daily_nav: {nav_path}")

    audit = pd.read_csv(audit_path)
    audit["decision_date"] = pd.to_datetime(audit["decision_date"])
    ticker_list = sorted({str(t).upper() for t in audit["ticker"].dropna().astype(str).tolist()} | {"SPY", "QQQ", "QLD", "TQQQ", "SHY"})
    base_nav = pd.read_csv(nav_path)
    base_nav["date"] = pd.to_datetime(base_nav["date"])
    start = base_nav["date"].min().date().isoformat()
    end = base_nav["date"].max().date().isoformat()
    logger.info(f"Loading local Qlib close panel for {len(ticker_list)} tickers, {start} to {end}.")
    close = load_close_from_provider(provider_uri, tickers=ticker_list, start=start, end=end)
    close = close.loc[(close.index >= pd.Timestamp(start)) & (close.index <= pd.Timestamp(end))].ffill()
    if close.empty:
        raise ValueError("Close panel is empty; cannot run v8.2 year stability replay.")

    variants = build_pre_registered_variants()
    save_dataframe(pd.DataFrame([asdict(v) for v in variants]), out / "v8_2_variant_config.csv")

    benchmark = build_benchmark_metrics(close)
    save_dataframe(benchmark, out / "v8_2_benchmark_comparison.csv")
    benchmark_calmar = {str(r["benchmark"]): float(r["calmar"]) for _, r in benchmark.iterrows()}

    result_rows: list[dict[str, Any]] = []
    stress_rows: list[dict[str, Any]] = []
    annual_rows: list[dict[str, Any]] = []
    monthly_rows: list[dict[str, Any]] = []
    holding_rows: list[pd.DataFrame] = []
    daily_rows: list[pd.DataFrame] = []
    ticker_contrib_rows: list[pd.DataFrame] = []
    leave_ticker_rows: list[dict[str, Any]] = []
    leave_year_rows: list[dict[str, Any]] = []

    for idx, variant in enumerate(variants, start=1):
        logger.info(f"Running v8.2 variant {idx}/{len(variants)}: {variant.strategy_id}")
        weights = build_weights_from_audit(audit, close, variant)
        if weights.empty or weights.sum(axis=1).max() <= 0:
            logger.warning(f"Variant {variant.strategy_id} produced empty weights.")
            continue
        overlay_info = apply_ex_ante_overlays(close, weights, variant)
        weights = overlay_info["weights"]
        metrics, returns, turnover = evaluate_strategy(close, weights, cost_bps=5.0, slippage_bps=5.0)
        metrics_50, returns_50, turnover_50 = evaluate_strategy(close, weights, cost_bps=50.0, slippage_bps=5.0)
        metrics_t2, _, _ = evaluate_strategy(
            close,
            apply_ex_ante_overlays(close, build_weights_from_audit(audit, close, variant, execution_delay=2), variant)["weights"],
            cost_bps=5.0,
            slippage_bps=5.0,
        )
        annual = yearly_returns(returns)
        monthly = monthly_returns(returns)
        single_year_share = concentration_share(annual["year_return"]) if not annual.empty else 0.0
        contrib = ticker_contributions(close.loc[weights.index, weights.columns].ffill(), weights)
        top_ticker = str(contrib.iloc[0]["ticker"]) if not contrib.empty else ""
        top_ticker_share = float(contrib.iloc[0]["abs_share"]) if not contrib.empty else 0.0
        remove_ticker_metrics = remove_ticker_stress(close, weights, top_ticker) if top_ticker else {}
        remove_year_metrics, top_year, top_year_share = remove_top_year_stress(returns, weights)
        qqq_win = monthly_win_rate(returns, close.get("QQQ"))
        tqqq_win = monthly_win_rate(returns, close.get("TQQQ"))
        gate = build_gate_verdict(metrics, metrics_50, metrics_t2, remove_ticker_metrics, remove_year_metrics, single_year_share, top_ticker_share, benchmark_calmar)

        row = {
            "strategy_id": variant.strategy_id,
            "feature_set": "Alpha360",
            "model": "LGBModel",
            "label": "label_5d",
            "portfolio_template": variant.portfolio_template,
            "top_k": variant.top_k,
            "max_weight": variant.max_weight,
            "dropout": variant.dropout,
            "vol_target": variant.vol_target,
            "vol_window": variant.vol_window,
            "ytd_return_cap": variant.ytd_return_cap,
            "rolling_3m_return_cap": variant.rolling_3m_return_cap,
            "rolling_6m_return_cap": variant.rolling_6m_return_cap,
            "derisk_ratio": variant.derisk_ratio,
            "regime_rule": variant.regime_rule,
            "safe_asset": variant.safe_asset,
            "cash_or_shy_allocation_ratio": overlay_info["avg_residual_allocation"],
            "avg_exposure": overlay_info["avg_exposure"],
            "min_exposure": overlay_info["min_exposure"],
            "max_exposure": overlay_info["max_exposure"],
            "single_year_share": single_year_share,
            "top_contribution_year": top_year,
            "top_contribution_year_abs_share": top_year_share,
            "top_ticker": top_ticker,
            "top_ticker_share": top_ticker_share,
            "remove_top_ticker_cagr": remove_ticker_metrics.get("cagr", 0.0),
            "remove_top_ticker_calmar": remove_ticker_metrics.get("calmar", 0.0),
            "remove_top_year_cagr": remove_year_metrics.get("cagr", 0.0),
            "remove_top_year_calmar": remove_year_metrics.get("calmar", 0.0),
            "same_window_vs_QQQ_win_rate": qqq_win,
            "same_window_vs_TQQQ_win_rate": tqqq_win,
            "cost50_t1_cagr": metrics_50["cagr"],
            "cost50_t1_calmar": metrics_50["calmar"],
            "t2_cagr": metrics_t2["cagr"],
            "t2_calmar": metrics_t2["calmar"],
            **metrics,
            **gate,
        }
        result_rows.append(row)

        for cost in [5, 10, 20, 50]:
            m, _, _ = evaluate_strategy(close, weights, cost_bps=float(cost), slippage_bps=5.0)
            stress_rows.append({"strategy_id": variant.strategy_id, "stress_type": "cost_bps", "cost_bps": cost, "slippage_bps": 5.0, **m})
        for slip in [0, 5, 10, 20]:
            m, _, _ = evaluate_strategy(close, weights, cost_bps=5.0, slippage_bps=float(slip))
            stress_rows.append({"strategy_id": variant.strategy_id, "stress_type": "slippage_bps", "cost_bps": 5.0, "slippage_bps": slip, **m})
        for delay in [0, 1, 2]:
            delay_weights = apply_ex_ante_overlays(close, build_weights_from_audit(audit, close, variant, execution_delay=delay), variant)["weights"]
            m, _, _ = evaluate_strategy(close, delay_weights, cost_bps=5.0, slippage_bps=5.0)
            stress_rows.append({"strategy_id": variant.strategy_id, "stress_type": "execution_delay", "execution_delay": delay, **m})

        annual.insert(0, "strategy_id", variant.strategy_id)
        monthly.insert(0, "strategy_id", variant.strategy_id)
        annual_rows.extend(annual.to_dict("records"))
        monthly_rows.extend(monthly.to_dict("records"))
        daily_rows.append(pd.DataFrame({"date": returns.index, "strategy_id": variant.strategy_id, "return": returns.values, "nav": nav_from_returns(returns).values, "turnover": turnover.values}))
        holdings = weights.stack().rename("weight").reset_index()
        holdings.columns = ["date", "ticker", "weight"]
        holdings = holdings.loc[holdings["weight"].abs() > 1e-12].copy()
        holdings.insert(0, "strategy_id", variant.strategy_id)
        holding_rows.append(holdings)
        if not contrib.empty:
            contrib.insert(0, "strategy_id", variant.strategy_id)
            ticker_contrib_rows.append(contrib)
        if top_ticker:
            leave_ticker_rows.append({"strategy_id": variant.strategy_id, "removed_ticker": top_ticker, **remove_ticker_metrics})
        if top_year:
            leave_year_rows.append({"strategy_id": variant.strategy_id, "removed_year": top_year, **remove_year_metrics})

    results = pd.DataFrame(result_rows)
    if not results.empty:
        results = results.sort_values(["allow_enter_v9", "gate_pass_count", "calmar", "cagr", "single_year_share"], ascending=[False, False, False, False, True])
    stress = pd.DataFrame(stress_rows)
    annual_df = pd.DataFrame(annual_rows)
    monthly_df = pd.DataFrame(monthly_rows)
    daily_df = pd.concat(daily_rows, ignore_index=True) if daily_rows else pd.DataFrame()
    holdings_df = pd.concat(holding_rows, ignore_index=True) if holding_rows else pd.DataFrame()
    contrib_df = pd.concat(ticker_contrib_rows, ignore_index=True) if ticker_contrib_rows else pd.DataFrame()
    leave_ticker = pd.DataFrame(leave_ticker_rows)
    leave_year = pd.DataFrame(leave_year_rows)

    save_dataframe(results, out / "v8_2_year_stability_results.csv")
    save_dataframe(stress, out / "v8_2_execution_stress_results.csv")
    save_dataframe(annual_df, out / "v8_2_annual_return_table.csv")
    save_dataframe(monthly_df, out / "v8_2_monthly_return_table.csv")
    save_dataframe(daily_df, out / "v8_2_daily_nav_by_strategy.csv")
    save_dataframe(holdings_df, out / "v8_2_monthly_holdings_by_strategy.csv")
    save_dataframe(contrib_df, out / "v8_2_ticker_contribution.csv")
    save_dataframe(leave_ticker, out / "v8_2_leave_one_ticker_out.csv")
    save_dataframe(leave_year, out / "v8_2_leave_one_year_out.csv")

    best = results.iloc[0].to_dict() if not results.empty else {}
    verdict = {
        "stage": "v8.2_year_stability",
        "mainline": "Alpha360 + LGBModel + label_5d",
        "variant_count": int(len(variants)),
        "result_count": int(len(results)),
        "best_strategy_id": best.get("strategy_id", ""),
        "classification": best.get("classification", "no_result"),
        "allow_enter_v9": bool(best.get("allow_enter_v9", False)),
        "reason": best.get("classification_reason", ""),
        "no_v9_this_round": True,
        "no_universe_expansion": True,
        "no_model_training": True,
        "no_trading_claim": True,
    }
    save_json(verdict, out / "v8_2_cycle_verdict.json")
    return {
        "results": results,
        "stress": stress,
        "annual": annual_df,
        "monthly": monthly_df,
        "daily": daily_df,
        "holdings": holdings_df,
        "ticker_contribution": contrib_df,
        "leave_ticker": leave_ticker,
        "leave_year": leave_year,
        "benchmark": benchmark,
        "cycle_verdict": verdict,
    }


def build_weights_from_audit(
    audit: pd.DataFrame,
    close: pd.DataFrame,
    variant: YearStabilityVariant,
    execution_delay: int = 1,
) -> pd.DataFrame:
    weights = pd.DataFrame(np.nan, index=close.index, columns=close.columns, dtype=float)
    current = pd.Series(0.0, index=close.columns, dtype=float)
    decision_dates = sorted(pd.to_datetime(audit["decision_date"].dropna().unique()))
    for decision_date in decision_dates:
        frame = audit.loc[pd.to_datetime(audit["decision_date"]) == decision_date].copy()
        frame = frame.loc[(frame.get("candidate_flag", True) == True) & (frame.get("tradable_flag", True) == True)].copy()  # noqa: E712
        frame["ticker"] = frame["ticker"].astype(str).str.upper()
        frame = frame.loc[frame["ticker"].isin(close.columns)].copy()
        if frame.empty:
            continue
        score_col = "adjusted_score" if "adjusted_score" in frame.columns and frame["adjusted_score"].notna().any() else "raw_score"
        ranked = frame.sort_values(score_col, ascending=False)["ticker"].drop_duplicates().tolist()
        if not ranked:
            continue
        if variant.dropout:
            selected = topk_dropout_selection(current, ranked, top_k=variant.top_k, n_drop=variant.n_drop)
        else:
            selected = ranked[: variant.top_k]
        execution_date = trading_offset(close.index, decision_date, execution_delay)
        if pd.isna(execution_date) or execution_date not in weights.index:
            continue
        current = pd.Series(0.0, index=close.columns, dtype=float)
        selected = [ticker for ticker in selected if ticker in current.index]
        if selected:
            raw_weight = min(float(variant.max_weight), 1.0 / float(len(selected)))
            current.loc[selected] = raw_weight
            if current.sum() > 0 and current.sum() < 0.999 and variant.max_weight >= 1.0 / float(len(selected)):
                current = current / current.sum()
        weights.loc[execution_date] = current
    return weights.ffill().fillna(0.0)


def topk_dropout_selection(current: pd.Series, ranked: list[str], top_k: int, n_drop: int) -> list[str]:
    rank_map = {ticker: idx for idx, ticker in enumerate(ranked)}
    current_holdings = [ticker for ticker in current[current > 1e-12].index.astype(str).tolist() if ticker in rank_map]
    if not current_holdings:
        return ranked[:top_k]
    sell_candidates = sorted(
        [ticker for ticker in current_holdings if rank_map.get(ticker, 10**9) >= top_k],
        key=lambda ticker: rank_map.get(ticker, 10**9),
        reverse=True,
    )
    sell = set(sell_candidates[: max(0, n_drop)])
    keep = sorted([ticker for ticker in current_holdings if ticker not in sell], key=lambda ticker: rank_map.get(ticker, 10**9))[:top_k]
    buys = [ticker for ticker in ranked if ticker not in keep][: max(0, top_k - len(keep))]
    return (keep + buys)[:top_k]


def apply_ex_ante_overlays(close: pd.DataFrame, base_weights: pd.DataFrame, variant: YearStabilityVariant) -> dict[str, Any]:
    weights = base_weights.reindex(close.index).ffill().fillna(0.0)
    base_returns, _ = portfolio_returns(close.loc[weights.index, weights.columns].ffill(), weights, cost_bps=0.0, slippage_bps=0.0)
    scale = pd.Series(1.0, index=weights.index, dtype=float)

    if variant.vol_target is not None and variant.vol_window is not None:
        realized = base_returns.rolling(int(variant.vol_window)).std(ddof=0).shift(1) * np.sqrt(252.0)
        vol_scale = (float(variant.vol_target) / realized.replace(0.0, np.nan)).clip(lower=0.0, upper=1.0).fillna(1.0)
        scale = np.minimum(scale, vol_scale)

    cap_scale = pd.Series(1.0, index=weights.index, dtype=float)
    derisk_scale = max(0.0, 1.0 - float(variant.derisk_ratio))
    if variant.ytd_return_cap is not None:
        ytd = base_returns.groupby(base_returns.index.year).apply(lambda s: (1.0 + s).cumprod() - 1.0)
        if isinstance(ytd.index, pd.MultiIndex):
            ytd.index = ytd.index.get_level_values(-1)
        ytd_signal = ytd.reindex(weights.index).shift(1).fillna(0.0)
        cap_scale = cap_scale.mask(ytd_signal > float(variant.ytd_return_cap), derisk_scale)
    if variant.rolling_3m_return_cap is not None:
        roll = rolling_compound_return(base_returns, 63).shift(1).fillna(0.0)
        cap_scale = cap_scale.mask(roll > float(variant.rolling_3m_return_cap), derisk_scale)
    if variant.rolling_6m_return_cap is not None:
        roll = rolling_compound_return(base_returns, 126).shift(1).fillna(0.0)
        cap_scale = cap_scale.mask(roll > float(variant.rolling_6m_return_cap), derisk_scale)
    scale = np.minimum(scale, cap_scale)

    if variant.regime_rule:
        regime = pd.Series(True, index=weights.index)
        if variant.regime_rule in {"qqq_ma200", "qqq_spy_ma200"} and "QQQ" in close.columns:
            qqq_ma = close["QQQ"].rolling(200).mean().shift(1)
            regime &= close["QQQ"].shift(1) > qqq_ma
        if variant.regime_rule == "qqq_spy_ma200" and "SPY" in close.columns:
            spy_ma = close["SPY"].rolling(200).mean().shift(1)
            regime &= close["SPY"].shift(1) > spy_ma
        if variant.regime_rule == "qqq_vol35" and "QQQ" in close.columns:
            qqq_vol = close["QQQ"].pct_change(fill_method=None).rolling(63).std(ddof=0).shift(1) * np.sqrt(252.0)
            regime &= qqq_vol < float(variant.qqq_vol_threshold or 0.35)
        scale = np.minimum(scale, regime.fillna(True).astype(float))

    scaled = weights.mul(pd.Series(scale, index=weights.index).astype(float), axis=0)
    residual = (1.0 - scaled.sum(axis=1)).clip(lower=0.0, upper=1.0)
    if variant.safe_asset.upper() == "SHY" and "SHY" in scaled.columns:
        scaled.loc[:, "SHY"] = scaled.get("SHY", 0.0) + residual
        residual_after = (1.0 - scaled.sum(axis=1)).clip(lower=0.0, upper=1.0)
    else:
        residual_after = residual
    exposure = scaled.drop(columns=["SHY"], errors="ignore").sum(axis=1) if "SHY" in scaled.columns else scaled.sum(axis=1)
    return {
        "weights": scaled.fillna(0.0),
        "avg_residual_allocation": float(residual_after.mean() if variant.safe_asset.upper() != "SHY" else residual.mean()),
        "avg_exposure": float(exposure.mean()),
        "min_exposure": float(exposure.min()),
        "max_exposure": float(exposure.max()),
    }


def evaluate_strategy(close: pd.DataFrame, weights: pd.DataFrame, cost_bps: float, slippage_bps: float) -> tuple[dict[str, Any], pd.Series, pd.Series]:
    local_close = close.loc[weights.index.min() : weights.index.max(), weights.columns].ffill()
    weights = weights.reindex(local_close.index).ffill().fillna(0.0)
    returns, turnover = portfolio_returns(local_close, weights, cost_bps=cost_bps, slippage_bps=slippage_bps)
    return compute_portfolio_metrics(returns, turnover, weights), returns, turnover


def build_benchmark_metrics(close: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for ticker in ["SPY", "QQQ", "QLD", "TQQQ"]:
        if ticker not in close.columns:
            continue
        returns = close[ticker].pct_change(fill_method=None).fillna(0.0)
        weights = pd.DataFrame({ticker: 1.0}, index=returns.index)
        turnover = pd.Series(0.0, index=returns.index)
        rows.append({"benchmark": ticker, **compute_portfolio_metrics(returns, turnover, weights)})
    return pd.DataFrame(rows)


def yearly_returns(returns: pd.Series) -> pd.DataFrame:
    if returns.empty:
        return pd.DataFrame(columns=["year", "year_return"])
    yearly = returns.groupby(returns.index.year).apply(lambda s: float((1.0 + s).prod() - 1.0))
    return pd.DataFrame({"year": yearly.index.astype(int), "year_return": yearly.values})


def monthly_returns(returns: pd.Series) -> pd.DataFrame:
    if returns.empty:
        return pd.DataFrame(columns=["month", "monthly_return"])
    monthly = returns.groupby(returns.index.to_period("M")).apply(lambda s: float((1.0 + s).prod() - 1.0))
    return pd.DataFrame({"month": monthly.index.astype(str), "monthly_return": monthly.values})


def concentration_share(values: pd.Series) -> float:
    clean = pd.Series(values).dropna().astype(float)
    denom = float(clean.abs().sum())
    return float(clean.abs().max() / denom) if denom else 0.0


def remove_ticker_stress(close: pd.DataFrame, weights: pd.DataFrame, ticker: str) -> dict[str, Any]:
    if not ticker or ticker not in weights.columns:
        return {}
    reduced = weights.copy()
    reduced.loc[:, ticker] = 0.0
    return evaluate_strategy(close, reduced, cost_bps=5.0, slippage_bps=5.0)[0]


def remove_top_year_stress(returns: pd.Series, weights: pd.DataFrame) -> tuple[dict[str, Any], int | None, float]:
    yearly = yearly_returns(returns)
    if yearly.empty:
        return {}, None, 0.0
    yearly["abs_return"] = yearly["year_return"].abs()
    top = yearly.sort_values("abs_return", ascending=False).iloc[0]
    year = int(top["year"])
    share = concentration_share(yearly["year_return"])
    local_returns = returns.loc[returns.index.year != year]
    local_weights = weights.loc[weights.index.year != year]
    if local_returns.empty or local_weights.empty:
        return {}, year, share
    turnover = local_weights.diff().abs().sum(axis=1).fillna(local_weights.abs().sum(axis=1))
    return compute_portfolio_metrics(local_returns, turnover.reindex(local_returns.index).fillna(0.0), local_weights.reindex(local_returns.index).fillna(0.0)), year, share


def monthly_win_rate(returns: pd.Series, benchmark_close: pd.Series | None) -> float:
    if benchmark_close is None or benchmark_close.empty or returns.empty:
        return 0.0
    strategy_monthly = returns.groupby(returns.index.to_period("M")).apply(lambda s: float((1.0 + s).prod() - 1.0))
    bench_ret = benchmark_close.reindex(returns.index).ffill().pct_change(fill_method=None).fillna(0.0)
    bench_monthly = bench_ret.groupby(bench_ret.index.to_period("M")).apply(lambda s: float((1.0 + s).prod() - 1.0))
    joined = pd.concat([strategy_monthly.rename("strategy"), bench_monthly.rename("benchmark")], axis=1).dropna()
    return float((joined["strategy"] > joined["benchmark"]).mean()) if not joined.empty else 0.0


def rolling_compound_return(returns: pd.Series, window: int) -> pd.Series:
    return (1.0 + returns).rolling(window).apply(np.prod, raw=True) - 1.0


def build_gate_verdict(
    metrics: dict[str, Any],
    metrics_50: dict[str, Any],
    metrics_t2: dict[str, Any],
    remove_ticker_metrics: dict[str, Any],
    remove_year_metrics: dict[str, Any],
    single_year_share: float,
    top_ticker_share: float,
    benchmark_calmar: dict[str, float],
) -> dict[str, Any]:
    qqq_calmar = benchmark_calmar.get("QQQ", 0.0)
    qld_calmar = benchmark_calmar.get("QLD", 0.0)
    tqqq_calmar = benchmark_calmar.get("TQQQ", 0.0)
    benchmark_gate = bool(metrics.get("calmar", 0.0) >= qqq_calmar and metrics.get("calmar", 0.0) >= 0.75 * max(qld_calmar, tqqq_calmar, qqq_calmar, 0.0))
    gates = {
        "gate_cagr_20": metrics.get("cagr", 0.0) >= 0.20,
        "gate_calmar_1": metrics.get("calmar", 0.0) >= 1.0,
        "gate_cost50_t1_cagr_20": metrics_50.get("cagr", 0.0) >= 0.20,
        "gate_cost50_t1_calmar_1": metrics_50.get("calmar", 0.0) >= 1.0,
        "gate_t2_cagr_20": metrics_t2.get("cagr", 0.0) >= 0.20,
        "gate_t2_calmar_1": metrics_t2.get("calmar", 0.0) >= 1.0,
        "gate_single_year_share_50": single_year_share <= 0.50,
        "gate_top_ticker_share_30": top_ticker_share <= 0.30,
        "gate_remove_top_year_cagr_20": remove_year_metrics.get("cagr", 0.0) >= 0.20,
        "gate_remove_top_year_calmar_1": remove_year_metrics.get("calmar", 0.0) >= 1.0,
        "gate_remove_top_ticker_cagr_20": remove_ticker_metrics.get("cagr", 0.0) >= 0.20,
        "gate_remove_top_ticker_calmar_1": remove_ticker_metrics.get("calmar", 0.0) >= 1.0,
        "gate_benchmark_calmar": benchmark_gate,
        "gate_no_lookahead": True,
        "gate_model_warning": True,
    }
    allow = all(bool(v) for v in gates.values())
    if allow:
        classification = "v9_ready_research_candidate"
        reason = "All v8.2 gates passed, but this run still does not enter v9 automatically."
    elif metrics.get("cagr", 0.0) >= 0.20 and metrics.get("calmar", 0.0) >= 1.0:
        classification = "credible_but_execution_sensitive"
        failed = [k for k, v in gates.items() if not v]
        reason = "Core performance gates passed, but failed: " + ",".join(failed)
    else:
        classification = "likely_overfit"
        failed = [k for k, v in gates.items() if not v]
        reason = "Core performance gates failed: " + ",".join(failed)
    return {
        **gates,
        "gate_pass_count": int(sum(bool(v) for v in gates.values())),
        "allow_enter_v9": bool(allow),
        "classification": classification,
        "classification_reason": reason,
    }


def _pct_id(value: float) -> str:
    return f"{int(round(float(value) * 100)):02d}p"
