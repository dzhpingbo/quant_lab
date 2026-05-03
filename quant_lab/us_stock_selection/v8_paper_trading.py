"""v8 pseudo-live replay for the frozen v7 candidate."""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.exceptions import ConvergenceWarning
from sklearn.impute import SimpleImputer
from sklearn.linear_model import ElasticNet, Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from quant_lab.us_stock_selection.feature_cache import load_feature_cache
from quant_lab.us_stock_selection.qlib_signal_backtest import compute_portfolio_metrics, portfolio_returns
from quant_lab.us_stock_selection.qlib_workflow_runner import load_close_from_provider
from quant_lab.us_stock_selection.utils import ensure_dir, nav_from_returns, save_dataframe
from quant_lab.us_stock_selection.v8_2_audit_trail import build_score_rank_audit_for_decision


FROZEN_FEATURE_SET = "Alpha360"
FROZEN_MODEL = "ElasticNet"
FROZEN_LABEL = "label_5d"
FROZEN_PORTFOLIO = "top5_equal_monthly"


@dataclass(frozen=True)
class ModelSpec:
    name: str
    feature_set: str = FROZEN_FEATURE_SET
    label: str = FROZEN_LABEL
    params: dict[str, Any] | None = None


def frozen_model_spec() -> ModelSpec:
    return ModelSpec("ElasticNet", params={"alpha": 0.001, "l1_ratio": 0.25, "max_iter": 3000, "tol": 1e-4})


def run_paper_trading_replay(
    out_dir: Path | str,
    cache_dir: Path | str,
    provider_uri: Path | str,
    model_spec: ModelSpec | None = None,
    start: str = "2024-01-01",
    end: str = "2026-04-17",
    execution_delay: int = 1,
    cost_bps: float = 5.0,
    slippage_bps: float = 5.0,
    max_weight: float = 0.20,
    min_avg_dollar_volume: float = 20_000_000.0,
    rebalance_timing: str = "month_end",
    save_outputs: bool = True,
    save_audit_trail: bool = True,
    audit_forward_returns: bool = True,
) -> dict[str, Any]:
    """Replay monthly pseudo-live decisions with expanding historical training."""
    out_path = ensure_dir(out_dir)
    spec = model_spec or frozen_model_spec()
    frame, feature_cols = load_feature_cache(cache_dir, spec.feature_set)
    close = load_close_from_provider(provider_uri, start="2020-01-01")
    volume = load_field_from_provider(provider_uri, "$volume", start="2020-01-01", tickers=list(close.columns))
    frame = frame.replace([np.inf, -np.inf], np.nan).copy()
    frame["date"] = pd.to_datetime(frame["date"])
    close = close.loc[(close.index >= "2020-01-01") & (close.index <= pd.Timestamp(end))].ffill()
    volume = volume.reindex(close.index).loc[:, close.columns].ffill()
    dollar_volume = close * volume

    decision_dates = rebalance_dates(close.index, start=start, end=end, timing=rebalance_timing)
    decision_rows: list[dict[str, Any]] = []
    holding_rows: list[dict[str, Any]] = []
    trade_rows: list[dict[str, Any]] = []
    weights = pd.DataFrame(np.nan, index=close.index, columns=close.columns)
    previous = pd.Series(0.0, index=close.columns)
    convergence_rows: list[dict[str, Any]] = []
    audit_parts: list[pd.DataFrame] = []

    for decision_idx, decision_date in enumerate(decision_dates):
        feature_date = latest_available_feature_date(frame, decision_date)
        if pd.isna(feature_date):
            continue
        train_end = trading_offset(close.index, pd.Timestamp(decision_date), -6)
        if pd.isna(train_end):
            continue
        train = frame.loc[(frame["date"] <= train_end) & frame[spec.label].notna()].copy()
        pred_frame = frame.loc[frame["date"] == feature_date].copy()
        if len(train) < 500 or pred_frame.empty:
            continue
        model, fit_info = fit_model(train, pred_frame, feature_cols, spec)
        pred = pred_frame.loc[:, ["date", "instrument"]].copy()
        pred["score"] = model.predict(pred_frame[feature_cols])
        pred["instrument"] = pred["instrument"].astype(str).str.upper()
        tradable = tradable_universe(close, dollar_volume, pred["instrument"].tolist(), decision_date, min_avg_dollar_volume)
        ranked = pred.loc[pred["instrument"].isin(tradable)].sort_values("score", ascending=False)
        selected = ranked.head(5).copy()
        if selected.empty:
            continue
        execution_date = trading_offset(close.index, pd.Timestamp(decision_date), execution_delay)
        if pd.isna(execution_date) or execution_date > close.index.max():
            continue
        current = pd.Series(0.0, index=close.columns)
        raw_weight = min(float(max_weight), 1.0 / len(selected))
        current.loc[selected["instrument"].tolist()] = raw_weight
        if current.sum() > 0 and current.sum() < 0.999 and max_weight >= 1.0 / len(selected):
            current = current / current.sum()
        weights.loc[execution_date] = current

        if save_audit_trail:
            next_execution_date = pd.NaT
            if decision_idx + 1 < len(decision_dates):
                next_execution_date = trading_offset(close.index, pd.Timestamp(decision_dates[decision_idx + 1]), execution_delay)
            history = pd.DataFrame(holding_rows)
            audit_parts.append(
                build_score_rank_audit_for_decision(
                    run_id=out_path.parent.name if out_path.name == "v8_paper_trading" else out_path.name,
                    decision_date=pd.Timestamp(decision_date),
                    feature_date=pd.Timestamp(feature_date),
                    execution_date=pd.Timestamp(execution_date),
                    pred=pred,
                    tradable=tradable,
                    selected=selected,
                    current_weights=current,
                    close=close,
                    dollar_volume=dollar_volume,
                    selection_history=history,
                    selected_period_end_date=None if pd.isna(next_execution_date) else pd.Timestamp(next_execution_date),
                    model_name=spec.name,
                    feature_set=spec.feature_set,
                    label=spec.label,
                    selection_rule=FROZEN_PORTFOLIO,
                    audit_forward_returns=audit_forward_returns,
                )
            )

        delta = current.sub(previous, fill_value=0.0)
        for ticker, delta_weight in delta[delta.abs() > 1e-12].items():
            trade_rows.append(
                {
                    "decision_date": date_str(decision_date),
                    "execution_date": date_str(execution_date),
                    "ticker": ticker,
                    "delta_weight": float(delta_weight),
                    "target_weight": float(current.get(ticker, 0.0)),
                    "price": float(close.loc[execution_date, ticker]) if ticker in close.columns and pd.notna(close.loc[execution_date, ticker]) else np.nan,
                }
            )
        previous = current

        selected_scores = dict(zip(selected["instrument"], selected["score"]))
        decision_rows.append(
            {
                "decision_date": date_str(decision_date),
                "feature_date": date_str(feature_date),
                "prediction_date": date_str(feature_date),
                "train_start": date_str(train["date"].min()),
                "train_end_label_safe": date_str(train_end),
                "execution_date": date_str(execution_date),
                "execution_delay_days": int(execution_delay),
                "feature_set": spec.feature_set,
                "model": spec.name,
                "label": spec.label,
                "selected_tickers": ",".join(selected["instrument"].tolist()),
                "selected_scores": ";".join(f"{k}:{selected_scores[k]:.8f}" for k in selected["instrument"].tolist()),
                "tradable_count": int(len(tradable)),
                "cost_bps": float(cost_bps),
                "slippage_bps": float(slippage_bps),
                **fit_info,
            }
        )
        for ticker in selected["instrument"].tolist():
            holding_rows.append(
                {
                    "decision_date": date_str(decision_date),
                    "execution_date": date_str(execution_date),
                    "ticker": ticker,
                    "weight": float(current[ticker]),
                    "score": float(selected_scores[ticker]),
                    "avg_dollar_volume_20d": float(dollar_volume[ticker].loc[:decision_date].tail(20).mean()) if ticker in dollar_volume else np.nan,
                }
            )
        convergence_rows.append({"decision_date": date_str(decision_date), **fit_info})

    weights = weights.ffill().fillna(0.0)
    local_close = close.loc[(close.index >= pd.Timestamp(start)) & (close.index <= pd.Timestamp(end)), weights.columns].ffill()
    weights = weights.reindex(local_close.index).ffill().fillna(0.0)
    returns, turnover = portfolio_returns(local_close, weights, cost_bps=cost_bps, slippage_bps=slippage_bps)
    metrics = compute_portfolio_metrics(returns, turnover, weights)
    daily_nav = pd.DataFrame({"date": returns.index, "return": returns.values, "nav": nav_from_returns(returns).values, "turnover": turnover.reindex(returns.index).values})
    decisions = pd.DataFrame(decision_rows)
    monthly_holdings = pd.DataFrame(holding_rows)
    trades = pd.DataFrame(trade_rows)
    convergence = pd.DataFrame(convergence_rows)
    audit_trail = pd.concat(audit_parts, ignore_index=True) if audit_parts else pd.DataFrame()
    metrics_row = pd.DataFrame([{**metrics, "model": spec.name, "feature_set": spec.feature_set, "label": spec.label, "portfolio": FROZEN_PORTFOLIO}])

    if save_outputs:
        save_dataframe(decisions, out_path / "monthly_decision_ledger.csv")
        save_dataframe(daily_nav, out_path / "daily_nav.csv")
        save_dataframe(monthly_holdings, out_path / "monthly_holdings.csv")
        save_dataframe(trades, out_path / "trades.csv")
        save_dataframe(metrics_row, out_path / "paper_trading_metrics.csv")
        save_dataframe(convergence, out_path / "fit_convergence_log.csv")
        if save_audit_trail:
            save_dataframe(audit_trail, out_path / "v8_2_score_rank_audit_trail.csv")
    return {
        "metrics": metrics,
        "metrics_df": metrics_row,
        "decisions": decisions,
        "daily_nav": daily_nav,
        "monthly_holdings": monthly_holdings,
        "trades": trades,
        "convergence": convergence,
        "weights": weights,
        "close": local_close,
        "returns": returns,
        "turnover": turnover,
        "audit_trail": audit_trail,
    }


def fit_model(train: pd.DataFrame, pred_frame: pd.DataFrame, feature_cols: list[str], spec: ModelSpec):
    model = make_model(spec)
    info = {"fit_warning_count": 0, "fit_warnings": "", "fit_status": "completed", "train_rows": int(len(train)), "predict_rows": int(len(pred_frame))}
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", ConvergenceWarning)
        warnings.simplefilter("always", RuntimeWarning)
        try:
            model.fit(train[feature_cols], train[spec.label].astype(float))
        except Exception as exc:
            info.update({"fit_status": "failed", "fit_warnings": str(exc)})
            raise
    warning_texts = [str(w.message) for w in caught]
    info["fit_warning_count"] = len(warning_texts)
    info["fit_warnings"] = " | ".join(warning_texts[:5])
    if warning_texts:
        info["fit_status"] = "completed_with_warning"
    return model, info


def make_model(spec: ModelSpec):
    params = dict(spec.params or {})
    if spec.name == "Ridge":
        return make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), Ridge(alpha=float(params.get("alpha", 1.0))))
    if spec.name in {"LGBModel", "LightGBM"}:
        try:
            from lightgbm import LGBMRegressor

            return make_pipeline(
                SimpleImputer(strategy="median"),
                LGBMRegressor(
                    n_estimators=int(params.get("n_estimators", 80)),
                    learning_rate=float(params.get("learning_rate", 0.05)),
                    num_leaves=int(params.get("num_leaves", 31)),
                    subsample=float(params.get("subsample", 0.85)),
                    colsample_bytree=float(params.get("colsample_bytree", 0.85)),
                    random_state=42,
                    n_jobs=4,
                    verbosity=-1,
                ),
            )
        except Exception:
            return make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), Ridge(alpha=1.0))
    return make_pipeline(
        SimpleImputer(strategy="median"),
        StandardScaler(),
        ElasticNet(
            alpha=float(params.get("alpha", 0.001)),
            l1_ratio=float(params.get("l1_ratio", 0.25)),
            max_iter=int(params.get("max_iter", 3000)),
            tol=float(params.get("tol", 1e-4)),
            random_state=42,
            selection=str(params.get("selection", "cyclic")),
        ),
    )


def load_field_from_provider(provider_uri: Path | str, field: str, start: str, tickers: list[str]) -> pd.DataFrame:
    import qlib
    from qlib.config import REG_US
    from qlib.data import D

    qlib.init(provider_uri=str(Path(provider_uri).expanduser()), region=REG_US, expression_cache=None, dataset_cache=None)
    cal = D.calendar(freq="day")
    end = pd.Timestamp(cal[-1]).date().isoformat() if len(cal) else None
    frame = D.features([t.upper() for t in tickers], [field], start_time=start, end_time=end, freq="day").reset_index()
    frame["date"] = pd.to_datetime(frame["datetime"] if "datetime" in frame.columns else frame["date"])
    frame["ticker"] = frame["instrument"].astype(str).str.upper()
    return frame.pivot_table(index="date", columns="ticker", values=field, aggfunc="last").sort_index()


def rebalance_dates(index: pd.DatetimeIndex, start: str, end: str, timing: str = "month_end") -> list[pd.Timestamp]:
    idx = pd.DatetimeIndex(index).sort_values()
    idx = idx[(idx >= pd.Timestamp(start)) & (idx <= pd.Timestamp(end))]
    if idx.empty:
        return []
    if timing == "month_start":
        positions = pd.Series(index=idx, data=np.arange(len(idx)))
        return [pd.Timestamp(idx[int(pos)]) for pos in positions.groupby(idx.to_period("M")).first().dropna().values]
    else:
        target = pd.Series(index=idx, data=np.arange(len(idx))).resample("ME").last().dropna().index
    return [pd.Timestamp(x) for x in idx[idx.isin(target)]]


def latest_available_feature_date(frame: pd.DataFrame, decision_date: pd.Timestamp) -> pd.Timestamp | pd.NaT:
    dates = pd.DatetimeIndex(frame.loc[frame["date"] <= pd.Timestamp(decision_date), "date"].drop_duplicates().sort_values())
    return dates.max() if len(dates) else pd.NaT


def trading_offset(index: pd.DatetimeIndex, date: pd.Timestamp, offset: int) -> pd.Timestamp | pd.NaT:
    idx = pd.DatetimeIndex(index).sort_values()
    if offset >= 0:
        pos = idx.searchsorted(pd.Timestamp(date), side="right")
        target = pos + offset - 1
    else:
        pos = idx.searchsorted(pd.Timestamp(date), side="left")
        target = pos + offset
    if target < 0 or target >= len(idx):
        return pd.NaT
    return pd.Timestamp(idx[target])


def tradable_universe(close: pd.DataFrame, dollar_volume: pd.DataFrame, tickers: list[str], decision_date: pd.Timestamp, min_avg_dollar_volume: float) -> list[str]:
    out: list[str] = []
    for ticker in tickers:
        if ticker not in close.columns:
            continue
        if pd.isna(close.loc[:decision_date, ticker].dropna().tail(1)).all():
            continue
        adv = dollar_volume[ticker].loc[:decision_date].tail(20).mean() if ticker in dollar_volume.columns else np.nan
        if pd.notna(adv) and adv >= min_avg_dollar_volume:
            out.append(ticker)
    return out


def date_str(value: Any) -> str:
    return "" if pd.isna(value) else pd.Timestamp(value).date().isoformat()
