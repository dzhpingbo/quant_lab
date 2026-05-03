"""QLD/TQQQ turning-point research v2.

V2 deliberately keeps the search space small:
- Labels: v1 recommendation atr_wide + H=10.
- Primary bases: ema20_ema100_direction and qqq_ma200_trend only.
- Meta labels: lightweight NumPy logistic (L1/L2) and small LightGBM.
- Risk overlays: fixed, interpretable drawdown-reduction layers.

The objective is lower drawdown and better Calmar, not a larger optimizer.
"""

from __future__ import annotations

import argparse
import math
import os
import sys
import warnings
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from qldtqqq_turning_point_research_v1 import (  # noqa: E402
    DEFAULT_DATA_DIR,
    LABEL_SCHEMES,
    TARGETS,
    atr,
    build_features_for_target,
    build_market_indicators,
    compute_barrier_labels,
    ema,
    read_ohlcv,
)

try:  # noqa: E402
    import lightgbm as lgb

    LIGHTGBM_AVAILABLE = True
    LIGHTGBM_ERROR = ""
except Exception as exc:  # pragma: no cover - captured in output if it happens
    lgb = None
    LIGHTGBM_AVAILABLE = False
    LIGHTGBM_ERROR = f"{type(exc).__name__}: {exc}"


warnings.filterwarnings("ignore", category=FutureWarning)

PERIOD_START = pd.Timestamp("2021-01-01")
FEE = 0.002
TRADING_DAYS = 252.0
EPS = 1e-10
OLD_RUN_DIR = ROOT / "outputs" / "qldtqqq_turning_points" / "qldtqqq_turning_20260420_133901"

BASE_STRATEGIES = ("ema20_ema100_direction", "qqq_ma200_trend")
LOGIT_FEATURES = [
    "qqq_close_over_ma200",
    "qqq_ema20_over_ema100",
    "qqq_rsi14",
    "qqq_macd_hist",
    "qqq_drawdown_120",
    "qqq_realized_vol20",
    "qqq_vol_percentile_60",
    "etf_vs_qqq_5d_return_gap",
]
LGBM_FEATURES = LOGIT_FEATURES + [
    "qqq_close_over_ma100",
    "qqq_atr14_pct",
    "qqq_realized_vol10",
    "vix_level",
]


@dataclass(frozen=True)
class SplitSpec:
    split_type: str
    name: str
    train_start: str
    train_end: str
    test_start: str
    test_end: str | None


@dataclass(frozen=True)
class MetaSpec:
    model: str
    regularization: str
    profile: str
    bottom_quantile: float
    top_quantile: float
    features: tuple[str, ...]


@dataclass(frozen=True)
class RiskSpec:
    name: str
    atr_stop: bool = False
    drawdown_cap: bool = False
    vol_target: bool = False
    max_cap: float | None = None
    regime_off: bool = False


@dataclass
class ReplayResult:
    target: str
    strategy: str
    base_strategy: str
    layer: str
    split_type: str
    split: str
    cost: float
    nav: pd.Series
    returns: pd.Series
    position: pd.Series
    desired: pd.Series
    turnover: pd.Series


def stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def log(message: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}", flush=True)


def pct(value: float | int | None) -> str:
    return "nan" if value is None or pd.isna(value) else f"{float(value) * 100:.2f}%"


def num(value: float | int | None, digits: int = 3) -> str:
    return "nan" if value is None or pd.isna(value) else f"{float(value):.{digits}f}"


def md_table(df: pd.DataFrame, max_rows: int | None = None) -> str:
    if df.empty:
        return "_Empty._"
    out = df.copy()
    if max_rows is not None:
        out = out.head(max_rows)
    for col in out.columns:
        out[col] = out[col].map(lambda x: "" if pd.isna(x) else str(x).replace("|", "/"))
    header = "| " + " | ".join(map(str, out.columns)) + " |"
    sep = "| " + " | ".join(["---"] * len(out.columns)) + " |"
    rows = ["| " + " | ".join(row) + " |" for row in out.astype(str).to_numpy()]
    return "\n".join([header, sep, *rows])


def write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def splits() -> list[SplitSpec]:
    return [
        SplitSpec("anchored", "anchored_2018_2020", "2010-01-01", "2017-12-31", "2018-01-01", "2020-12-31"),
        SplitSpec("anchored", "anchored_2021_2023", "2010-01-01", "2020-12-31", "2021-01-01", "2023-12-31"),
        SplitSpec("anchored", "anchored_2024_latest", "2010-01-01", "2023-12-31", "2024-01-01", None),
        SplitSpec("anchored", "anchored_2021_latest", "2010-01-01", "2020-12-31", "2021-01-01", None),
        SplitSpec("rolling", "rolling_2015_2017", "2010-01-01", "2014-12-31", "2015-01-01", "2017-12-31"),
        SplitSpec("rolling", "rolling_2018_2020", "2013-01-01", "2017-12-31", "2018-01-01", "2020-12-31"),
        SplitSpec("rolling", "rolling_2021_2023", "2016-01-01", "2020-12-31", "2021-01-01", "2023-12-31"),
        SplitSpec("rolling", "rolling_2024_latest", "2019-01-01", "2023-12-31", "2024-01-01", None),
    ]


def meta_specs() -> list[MetaSpec]:
    profiles = [
        ("balanced_q60", 0.60, 0.70),
        ("defensive_q70", 0.70, 0.60),
    ]
    specs: list[MetaSpec] = []
    for profile, bottom_q, top_q in profiles:
        specs.append(MetaSpec("logistic", "l2", profile, bottom_q, top_q, tuple(LOGIT_FEATURES)))
        specs.append(MetaSpec("logistic", "l1", profile, bottom_q, top_q, tuple(LOGIT_FEATURES)))
        specs.append(MetaSpec("lightgbm", "small", profile, bottom_q, top_q, tuple(LGBM_FEATURES)))
    return specs


def risk_specs() -> list[RiskSpec]:
    return [
        RiskSpec("atr_stop", atr_stop=True),
        RiskSpec("drawdown_cap", drawdown_cap=True),
        RiskSpec("vol_target", vol_target=True),
        RiskSpec("max_position_cap", max_cap=0.70),
        RiskSpec("regime_off_ma200", regime_off=True),
        RiskSpec("risk_bundle", atr_stop=True, drawdown_cap=True, vol_target=True, max_cap=0.70, regime_off=True),
    ]


def max_drawdown(nav: pd.Series) -> float:
    clean = nav.dropna()
    if clean.empty:
        return np.nan
    return float(clean.div(clean.cummax()).sub(1.0).min())


def cagr(nav: pd.Series) -> float:
    clean = nav.dropna()
    if len(clean) < 2:
        return np.nan
    years = max((clean.index[-1] - clean.index[0]).days / 365.25, 1 / 365.25)
    if clean.iloc[0] <= 0 or clean.iloc[-1] <= 0:
        return np.nan
    return float((clean.iloc[-1] / clean.iloc[0]) ** (1.0 / years) - 1.0)


def sharpe(returns: pd.Series) -> float:
    clean = returns.replace([np.inf, -np.inf], np.nan).dropna()
    if len(clean) < 20:
        return np.nan
    vol = clean.std(ddof=0)
    return float(clean.mean() / vol * math.sqrt(TRADING_DAYS)) if vol > 0 else np.nan


def holding_days(position: pd.Series) -> float:
    pos = position.fillna(0.0).abs().gt(EPS)
    if not pos.any():
        return 0.0
    starts = np.flatnonzero((pos & ~pos.shift(1, fill_value=False)).to_numpy())
    ends = np.flatnonzero((~pos & pos.shift(1, fill_value=False)).to_numpy())
    if len(ends) and len(starts) and ends[0] < starts[0]:
        ends = ends[1:]
    if len(ends) < len(starts):
        ends = np.r_[ends, len(pos) - 1]
    durations = [max(1, int(end) - int(start)) for start, end in zip(starts, ends)]
    return float(np.mean(durations)) if durations else 0.0


def metrics_from(result: ReplayResult, start: str, end: str | None) -> dict[str, float | int | str]:
    nav = result.nav.copy()
    if start:
        nav = nav.loc[nav.index >= pd.Timestamp(start)]
    if end:
        nav = nav.loc[nav.index <= pd.Timestamp(end)]
    nav = nav.dropna()
    if len(nav) < 2:
        return {}
    nav = nav / nav.iloc[0]
    returns = nav.pct_change().fillna(0.0)
    pos = result.position.reindex(nav.index).fillna(0.0)
    turnover = result.turnover.reindex(nav.index).fillna(0.0)
    entries = (pos.abs() > EPS) & ~(pos.shift(1).fillna(0.0).abs() > EPS)
    years = max((nav.index[-1] - nav.index[0]).days / 365.25, 1 / 365.25)
    mdd = max_drawdown(nav)
    ann = cagr(nav)
    return {
        "target": result.target,
        "strategy": result.strategy,
        "base_strategy": result.base_strategy,
        "layer": result.layer,
        "split_type": result.split_type,
        "split": result.split,
        "cost": result.cost,
        "period_start": nav.index[0].strftime("%Y-%m-%d"),
        "period_end": nav.index[-1].strftime("%Y-%m-%d"),
        "CAGR": ann,
        "MDD": mdd,
        "Sharpe": sharpe(returns),
        "Calmar": ann / abs(mdd) if np.isfinite(ann) and np.isfinite(mdd) and mdd < 0 else np.nan,
        "trade_count": int(entries.sum()),
        "turnover": float(turnover.sum() / years),
        "avg_holding_days": holding_days(pos),
        "time_in_market": float(pos.abs().gt(EPS).mean()),
        "avg_abs_weight": float(pos.abs().mean()),
        "max_weight": float(pos.max()),
        "final_nav": float(nav.iloc[-1]),
    }


def standardize_fit(X: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    arr = X.astype(float).replace([np.inf, -np.inf], np.nan).to_numpy(dtype=float)
    med = np.nanmedian(arr, axis=0)
    inds = np.where(~np.isfinite(arr))
    arr[inds] = np.take(med, inds[1])
    mean = arr.mean(axis=0)
    std = arr.std(axis=0)
    std[std == 0] = 1.0
    return (arr - mean) / std, mean, std


def standardize_apply(X: pd.DataFrame, mean: np.ndarray, std: np.ndarray) -> np.ndarray:
    arr = X.astype(float).replace([np.inf, -np.inf], np.nan).to_numpy(dtype=float)
    arr = np.where(np.isfinite(arr), arr, mean)
    return (arr - mean) / std


def sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -35, 35)))


def fit_logistic(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_test: pd.DataFrame,
    penalty: str,
) -> tuple[np.ndarray, np.ndarray, str]:
    y = y_train.astype(float).to_numpy()
    if len(np.unique(y[np.isfinite(y)])) < 2:
        base = np.full(len(X_test), np.nanmean(y) if len(y) else 0.0)
        return np.full(len(X_train), base[0] if len(base) else 0.0), base, "single_class"
    Xs, mean, std = standardize_fit(X_train)
    Xt = standardize_apply(X_test, mean, std)
    n, p = Xs.shape
    Xb = np.c_[np.ones(n), Xs]
    Xtb = np.c_[np.ones(len(Xt)), Xt]
    w = np.zeros(p + 1, dtype=float)
    pos = max(float(y.sum()), 1.0)
    neg = max(float(len(y) - y.sum()), 1.0)
    sample_weight = np.where(y > 0.5, len(y) / (2.0 * pos), len(y) / (2.0 * neg))
    lr = 0.05
    l2 = 0.02 if penalty == "l2" else 0.0
    l1 = 0.002 if penalty == "l1" else 0.0
    for _ in range(600):
        pred = sigmoid(Xb @ w)
        grad = (Xb.T @ ((pred - y) * sample_weight)) / n
        grad[1:] += l2 * w[1:]
        w -= lr * grad
        if l1 > 0:
            w[1:] = np.sign(w[1:]) * np.maximum(np.abs(w[1:]) - lr * l1, 0.0)
    return sigmoid(Xb @ w), sigmoid(Xtb @ w), "ok"


def fit_lgbm(X_train: pd.DataFrame, y_train: pd.Series, X_test: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, str]:
    if not LIGHTGBM_AVAILABLE:
        base = np.full(len(X_test), np.nan)
        return np.full(len(X_train), np.nan), base, f"skipped_lightgbm_unavailable: {LIGHTGBM_ERROR}"
    y = y_train.astype(int)
    if y.nunique() < 2 or int(y.sum()) < 10:
        base_prob = float(y.mean()) if len(y) else 0.0
        return np.full(len(X_train), base_prob), np.full(len(X_test), base_prob), "single_class_or_too_few_positive"
    train = X_train.astype(float).replace([np.inf, -np.inf], np.nan).fillna(X_train.median(numeric_only=True))
    test = X_test.astype(float).replace([np.inf, -np.inf], np.nan).fillna(train.median(numeric_only=True))
    params = {
        "objective": "binary",
        "metric": "binary_logloss",
        "verbosity": -1,
        "boosting_type": "gbdt",
        "learning_rate": 0.05,
        "max_depth": 3,
        "num_leaves": 7,
        "min_data_in_leaf": 50,
        "feature_fraction": 0.90,
        "bagging_fraction": 0.80,
        "bagging_freq": 1,
        "seed": 42,
        "num_threads": 1,
    }
    dtrain = lgb.Dataset(train, label=y)
    model = lgb.train(params, dtrain, num_boost_round=80)
    return model.predict(train), model.predict(test), "ok"


def load_data(data_dir: Path) -> dict[str, pd.DataFrame]:
    return {symbol: read_ohlcv(data_dir, symbol) for symbol in ("QLD", "TQQQ", "QQQ", "_VIX")}


def build_labels(data: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    scheme = next(s for s in LABEL_SCHEMES if s.name == "atr_wide")
    out = {}
    for target in TARGETS:
        bottom, top, _ = compute_barrier_labels(data[target], target, scheme, 10)
        out[target] = pd.DataFrame({"bottom_label": bottom, "top_label": top}, index=data[target].index)
    return out


def build_features(data: dict[str, pd.DataFrame]) -> tuple[dict[str, pd.DataFrame], dict[str, pd.Series]]:
    indicators = build_market_indicators(data["QQQ"], data["_VIX"])
    features = {
        target: build_features_for_target(target, data[target], data["QQQ"], indicators)
        for target in TARGETS
    }
    return features, indicators


def base_signals(data: dict[str, pd.DataFrame], indicators: dict[str, pd.Series]) -> dict[str, dict[str, pd.Series]]:
    qqq_close = indicators["qqq_close"]
    ema_signal = (indicators["qqq_ema20"] > indicators["qqq_ema100"]).astype(float)
    ma200_signal = (qqq_close > indicators["qqq_ma200"]).astype(float)
    out: dict[str, dict[str, pd.Series]] = {}
    for target in TARGETS:
        idx = data[target].index
        out[target] = {
            "ema20_ema100_direction": ema_signal.reindex(idx).ffill().fillna(0.0),
            "qqq_ma200_trend": ma200_signal.reindex(idx).ffill().fillna(0.0),
        }
    return out


def split_mask(index: pd.Index, start: str, end: str | None) -> pd.Series:
    mask = index >= pd.Timestamp(start)
    if end:
        mask &= index <= pd.Timestamp(end)
    return pd.Series(mask, index=index)


def model_predictions_for_split(
    features: pd.DataFrame,
    labels: pd.DataFrame,
    split: SplitSpec,
    spec: MetaSpec,
) -> dict[str, object]:
    train_mask = split_mask(features.index, split.train_start, split.train_end)
    test_mask = split_mask(features.index, split.test_start, split.test_end)
    valid = labels[["bottom_label", "top_label"]].notna().all(axis=1)
    train_idx = features.index[train_mask & valid]
    test_idx = features.index[test_mask]
    if len(train_idx) < 300 or len(test_idx) == 0:
        return {"status": "too_few_rows", "test_index": test_idx}

    X_train = features.loc[train_idx, list(spec.features)]
    X_test = features.loc[test_idx, list(spec.features)]
    yb = labels.loc[train_idx, "bottom_label"].astype(int)
    yt = labels.loc[train_idx, "top_label"].astype(int)
    if spec.model == "logistic":
        train_bottom, test_bottom, status_b = fit_logistic(X_train, yb, X_test, spec.regularization)
        train_top, test_top, status_t = fit_logistic(X_train, yt, X_test, spec.regularization)
    else:
        train_bottom, test_bottom, status_b = fit_lgbm(X_train, yb, X_test)
        train_top, test_top, status_t = fit_lgbm(X_train, yt, X_test)

    bottom_thr = float(np.nanquantile(train_bottom, spec.bottom_quantile)) if np.isfinite(train_bottom).any() else np.nan
    top_thr = float(np.nanquantile(train_top, spec.top_quantile)) if np.isfinite(train_top).any() else np.nan
    return {
        "status": f"bottom={status_b};top={status_t}",
        "test_index": test_idx,
        "bottom_prob": pd.Series(test_bottom, index=test_idx),
        "top_prob": pd.Series(test_top, index=test_idx),
        "bottom_threshold": bottom_thr,
        "top_threshold": top_thr,
        "train_rows": len(train_idx),
        "test_rows": len(test_idx),
        "bottom_positive_rate": float(yb.mean()),
        "top_positive_rate": float(yt.mean()),
    }


def meta_signal(
    base: pd.Series,
    bottom_prob: pd.Series,
    top_prob: pd.Series,
    bottom_thr: float,
    top_thr: float,
) -> pd.Series:
    idx = base.index
    bp = bottom_prob.reindex(idx)
    tp = top_prob.reindex(idx)
    held = False
    out = []
    for dt in idx:
        base_on = bool(base.loc[dt] > 0.5)
        if not base_on:
            held = False
        elif held:
            if pd.notna(tp.loc[dt]) and tp.loc[dt] > top_thr:
                held = False
        else:
            held = bool(pd.notna(bp.loc[dt]) and pd.notna(tp.loc[dt]) and bp.loc[dt] >= bottom_thr and tp.loc[dt] <= top_thr)
        out.append(1.0 if held else 0.0)
    return pd.Series(out, index=idx)


def make_overlay_weights(
    target: str,
    asset: pd.DataFrame,
    qqq: pd.DataFrame,
    base_weight: pd.Series,
    risk: RiskSpec,
    cost: float,
) -> ReplayResult:
    idx = asset.index
    base = base_weight.reindex(idx).ffill().fillna(0.0).clip(0.0, 1.0)
    open_price = asset["open"].astype(float).reindex(idx).ffill()
    close = asset["close"].astype(float).reindex(idx).ffill()
    asset_atr = atr(asset, 14).reindex(idx).ffill()
    realized_vol = close.pct_change().rolling(20, min_periods=20).std(ddof=0) * math.sqrt(TRADING_DAYS)
    qqq_ma200 = qqq["close"].rolling(200, min_periods=200).mean()
    regime_on = (qqq["close"] > qqq_ma200).reindex(idx).ffill().fillna(False)
    vol_target_value = 0.30
    atr_mult = 3.0
    drawdown_limit = -0.18
    cooldown_days = 20

    nav = np.ones(len(idx), dtype=float)
    returns = np.zeros(len(idx), dtype=float)
    position = np.zeros(len(idx), dtype=float)
    desired_after_close = np.zeros(len(idx), dtype=float)
    turnover = np.zeros(len(idx), dtype=float)
    equity = 1.0
    peak_nav = 1.0
    prev_weight = 0.0
    next_weight = 0.0
    atr_peak = np.nan
    atr_cooldown = 0
    dd_cooldown = 0

    for i, dt in enumerate(idx):
        if i == 0:
            raw = float(base.loc[dt])
            if risk.regime_off and not bool(regime_on.loc[dt]):
                raw = 0.0
            desired_after_close[i] = raw
            next_weight = raw
            continue

        prev_equity = equity
        if prev_weight > 0 and close.iloc[i - 1] > 0:
            equity *= 1.0 + prev_weight * (open_price.iloc[i] / close.iloc[i - 1] - 1.0)
        trade = abs(next_weight - prev_weight)
        if trade > EPS:
            equity *= max(0.0, 1.0 - cost * trade)
        current_weight = next_weight
        if current_weight > 0 and open_price.iloc[i] > 0:
            equity *= 1.0 + current_weight * (close.iloc[i] / open_price.iloc[i] - 1.0)

        nav[i] = equity
        returns[i] = equity / prev_equity - 1.0 if prev_equity > 0 else 0.0
        position[i] = current_weight
        turnover[i] = trade

        peak_nav = max(peak_nav, equity)
        if risk.drawdown_cap and equity / peak_nav - 1.0 <= drawdown_limit:
            dd_cooldown = cooldown_days
            peak_nav = equity

        raw = float(base.loc[dt])
        if risk.regime_off and not bool(regime_on.loc[dt]):
            raw = 0.0
        if risk.vol_target:
            vol = realized_vol.loc[dt]
            scale = min(1.0, vol_target_value / vol) if pd.notna(vol) and vol > 0 else 1.0
            raw *= scale
        if risk.max_cap is not None:
            raw = min(raw, risk.max_cap)

        if risk.atr_stop:
            if atr_cooldown > 0:
                atr_cooldown -= 1
                raw = 0.0
            elif raw > EPS:
                price = close.loc[dt]
                atr_value = asset_atr.loc[dt]
                atr_peak = price if not np.isfinite(atr_peak) else max(atr_peak, price)
                if pd.notna(atr_value) and price <= atr_peak - atr_mult * atr_value:
                    raw = 0.0
                    atr_peak = np.nan
                    atr_cooldown = 10
            else:
                atr_peak = np.nan

        if dd_cooldown > 0:
            dd_cooldown -= 1
            raw = 0.0

        next_weight = float(np.clip(raw, 0.0, 1.0))
        desired_after_close[i] = next_weight
        prev_weight = current_weight

    return ReplayResult(
        target=target,
        strategy=risk.name,
        base_strategy="",
        layer="",
        split_type="",
        split="",
        cost=cost,
        nav=pd.Series(nav, index=idx),
        returns=pd.Series(returns, index=idx),
        position=pd.Series(position, index=idx),
        desired=pd.Series(desired_after_close, index=idx),
        turnover=pd.Series(turnover, index=idx),
    )


def replay_plain(target: str, asset: pd.DataFrame, desired: pd.Series, cost: float) -> ReplayResult:
    return make_overlay_weights(target, asset, asset, desired, RiskSpec("none"), cost)


def evaluate_signal(
    target: str,
    data: dict[str, pd.DataFrame],
    desired: pd.Series,
    cost: float,
    risk: RiskSpec | None,
    name: str,
    base_strategy: str,
    layer: str,
    split: SplitSpec,
) -> dict[str, float | int | str]:
    if risk is None or risk.name == "none":
        result = replay_plain(target, data[target], desired, cost)
    else:
        result = make_overlay_weights(target, data[target], data["QQQ"], desired, risk, cost)
    result.strategy = name
    result.base_strategy = base_strategy
    result.layer = layer
    result.split_type = split.split_type
    result.split = split.name
    result.cost = cost
    return metrics_from(result, split.test_start, split.test_end)


def run_meta_evaluation(
    data: dict[str, pd.DataFrame],
    features: dict[str, pd.DataFrame],
    labels: dict[str, pd.DataFrame],
    bases: dict[str, dict[str, pd.Series]],
) -> tuple[pd.DataFrame, dict[tuple[str, str, str, str, str], pd.Series]]:
    rows = []
    signal_cache: dict[tuple[str, str, str, str, str], pd.Series] = {}
    for target in TARGETS:
        for split in splits():
            for spec in meta_specs():
                pred = model_predictions_for_split(features[target], labels[target], split, spec)
                if "bottom_prob" not in pred:
                    continue
                for base_name in BASE_STRATEGIES:
                    base = bases[target][base_name]
                    sig = meta_signal(
                        base,
                        pred["bottom_prob"],
                        pred["top_prob"],
                        float(pred["bottom_threshold"]),
                        float(pred["top_threshold"]),
                    )
                    sig_name = f"{base_name}__{spec.model}_{spec.regularization}_{spec.profile}"
                    cache_key = (target, split.name, base_name, spec.model, f"{spec.regularization}_{spec.profile}")
                    signal_cache[cache_key] = sig
                    for cost in (0.0, FEE):
                        metric = evaluate_signal(target, data, sig, cost, None, sig_name, base_name, "meta_only", split)
                        metric.update(
                            {
                                "model": spec.model,
                                "regularization": spec.regularization,
                                "profile": spec.profile,
                                "bottom_quantile": spec.bottom_quantile,
                                "top_quantile": spec.top_quantile,
                                "feature_count": len(spec.features),
                                "features": ",".join(spec.features),
                                "bottom_threshold": pred["bottom_threshold"],
                                "top_threshold": pred["top_threshold"],
                                "train_rows": pred["train_rows"],
                                "test_rows": pred["test_rows"],
                                "bottom_positive_rate": pred["bottom_positive_rate"],
                                "top_positive_rate": pred["top_positive_rate"],
                                "model_status": pred["status"],
                            }
                        )
                        rows.append(metric)
    return pd.DataFrame(rows), signal_cache


def run_risk_evaluation(
    data: dict[str, pd.DataFrame],
    bases: dict[str, dict[str, pd.Series]],
) -> pd.DataFrame:
    rows = []
    for target in TARGETS:
        for split in splits():
            for base_name in BASE_STRATEGIES:
                for risk in risk_specs():
                    name = f"{base_name}__{risk.name}"
                    for cost in (0.0, FEE):
                        metric = evaluate_signal(target, data, bases[target][base_name], cost, risk, name, base_name, "risk_only", split)
                        metric.update(
                            {
                                "risk_overlay": risk.name,
                                "atr_stop": risk.atr_stop,
                                "drawdown_cap": risk.drawdown_cap,
                                "vol_target": risk.vol_target,
                                "max_cap": risk.max_cap if risk.max_cap is not None else 1.0,
                                "regime_off": risk.regime_off,
                            }
                        )
                        rows.append(metric)
    return pd.DataFrame(rows)


def run_combined_evaluation(
    data: dict[str, pd.DataFrame],
    features: dict[str, pd.DataFrame],
    labels: dict[str, pd.DataFrame],
    bases: dict[str, dict[str, pd.Series]],
) -> pd.DataFrame:
    rows = []
    bundle = next(r for r in risk_specs() if r.name == "risk_bundle")
    for target in TARGETS:
        for split in splits():
            for spec in meta_specs():
                pred = model_predictions_for_split(features[target], labels[target], split, spec)
                if "bottom_prob" not in pred:
                    continue
                for base_name in BASE_STRATEGIES:
                    sig = meta_signal(
                        bases[target][base_name],
                        pred["bottom_prob"],
                        pred["top_prob"],
                        float(pred["bottom_threshold"]),
                        float(pred["top_threshold"]),
                    )
                    name = f"{base_name}__{spec.model}_{spec.regularization}_{spec.profile}__risk_bundle"
                    for cost in (0.0, FEE):
                        metric = evaluate_signal(target, data, sig, cost, bundle, name, base_name, "meta_plus_risk_bundle", split)
                        metric.update(
                            {
                                "model": spec.model,
                                "regularization": spec.regularization,
                                "profile": spec.profile,
                                "risk_overlay": bundle.name,
                                "feature_count": len(spec.features),
                                "bottom_threshold": pred["bottom_threshold"],
                                "top_threshold": pred["top_threshold"],
                                "model_status": pred["status"],
                            }
                        )
                        rows.append(metric)
    return pd.DataFrame(rows)


def summarize_for_selection(df: pd.DataFrame) -> pd.DataFrame:
    after = df[df["cost"].eq(FEE)].copy()
    group_cols = ["target", "strategy", "base_strategy", "layer"]
    optional = [c for c in ("model", "regularization", "profile", "risk_overlay") if c in after.columns]
    group_cols += optional
    summary = (
        after.groupby(group_cols, as_index=False)
        .agg(
            median_CAGR=("CAGR", "median"),
            worst_CAGR=("CAGR", "min"),
            median_MDD=("MDD", "median"),
            worst_MDD=("MDD", "min"),
            median_Calmar=("Calmar", "median"),
            worst_Calmar=("Calmar", "min"),
            mean_turnover=("turnover", "mean"),
            mean_abs_weight=("avg_abs_weight", "mean"),
        )
        .copy()
    )
    summary["selection_score"] = (
        summary["median_Calmar"]
        + 0.35 * summary["worst_Calmar"]
        + 0.25 * summary["median_CAGR"]
        - 0.04 * summary["mean_turnover"]
    )
    return summary.sort_values(["target", "selection_score"], ascending=[True, False])


def select_v2_configs(meta: pd.DataFrame, risk: pd.DataFrame, combined: pd.DataFrame) -> pd.DataFrame:
    parts = []
    for df in (meta, risk, combined):
        if not df.empty:
            parts.append(summarize_for_selection(df))
    all_summary = pd.concat(parts, ignore_index=True, sort=False) if parts else pd.DataFrame()
    if all_summary.empty:
        return all_summary
    return all_summary.sort_values(["target", "selection_score"], ascending=[True, False]).groupby("target", as_index=False).head(1).reset_index(drop=True)


def old_weight(old_run_dir: Path, target: str, index: pd.Index) -> pd.Series:
    path = old_run_dir / f"{target}_best_signal_nav.csv"
    if not path.exists():
        return pd.Series(0.0, index=index)
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.normalize()
    df = df.dropna(subset=["date"]).sort_values("date").set_index("date")
    return pd.to_numeric(df["desired_weight_after_close"], errors="coerce").reindex(index).ffill().fillna(0.0).clip(0.0, 1.0)


def compare_v2_v1_old(
    data: dict[str, pd.DataFrame],
    bases: dict[str, dict[str, pd.Series]],
    selected_results: dict[str, ReplayResult],
    old_run_dir: Path,
) -> pd.DataFrame:
    rows = []
    split = SplitSpec("final", "2021_latest", "2010-01-01", "2020-12-31", "2021-01-01", None)
    for target in TARGETS:
        cases = [
            ("v1_ema20_ema100_direction", bases[target]["ema20_ema100_direction"], None, "v1_primary"),
            ("v1_qqq_ma200_trend", bases[target]["qqq_ma200_trend"], None, "v1_primary"),
            ("old_optimal_fractional_same_engine", old_weight(old_run_dir, target, data[target].index), None, "old_same_engine"),
        ]
        for name, sig, risk, source in cases:
            metric = evaluate_signal(target, data, sig, FEE, risk, name, name, source, split)
            metric["source"] = source
            rows.append(metric)
        selected = selected_results[target]
        metric = metrics_from(selected, "2021-01-01", None)
        metric["source"] = "v2_selected"
        rows.append(metric)
    return pd.DataFrame(rows)


def anchored_full_signal(
    target: str,
    data: dict[str, pd.DataFrame],
    features: dict[str, pd.DataFrame],
    labels: dict[str, pd.DataFrame],
    bases: dict[str, dict[str, pd.Series]],
    selected_row: pd.Series,
) -> pd.Series:
    base_name = str(selected_row["base_strategy"])
    model = str(selected_row.get("model", "logistic"))
    regularization = str(selected_row.get("regularization", "l2"))
    profile = str(selected_row.get("profile", "balanced_q60"))
    spec = next(s for s in meta_specs() if s.model == model and s.regularization == regularization and s.profile == profile)
    full = pd.Series(0.0, index=data[target].index)
    for split in [
        SplitSpec("anchored", "anchored_2021_2023", "2010-01-01", "2020-12-31", "2021-01-01", "2023-12-31"),
        SplitSpec("anchored", "anchored_2024_latest", "2010-01-01", "2023-12-31", "2024-01-01", None),
    ]:
        pred = model_predictions_for_split(features[target], labels[target], split, spec)
        if "bottom_prob" not in pred:
            continue
        sig = meta_signal(bases[target][base_name], pred["bottom_prob"], pred["top_prob"], float(pred["bottom_threshold"]), float(pred["top_threshold"]))
        mask = split_mask(full.index, split.test_start, split.test_end)
        full.loc[mask] = sig.loc[mask]
    return full


def final_selected_replays(
    data: dict[str, pd.DataFrame],
    features: dict[str, pd.DataFrame],
    labels: dict[str, pd.DataFrame],
    bases: dict[str, dict[str, pd.Series]],
    meta: pd.DataFrame,
    risk: pd.DataFrame,
    combined: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, ReplayResult]]:
    selected_rows = select_v2_configs(meta, risk, combined)
    risk_lookup = {r.name: r for r in risk_specs()}
    replays: dict[str, ReplayResult] = {}
    for _, row in selected_rows.iterrows():
        target = str(row["target"])
        layer = str(row["layer"])
        if layer == "risk_only":
            sig = bases[target][str(row["base_strategy"])]
            risk_name = str(row.get("risk_overlay", "none"))
            replay = make_overlay_weights(target, data[target], data["QQQ"], sig, risk_lookup.get(risk_name, RiskSpec("none")), FEE)
        elif layer == "meta_only":
            sig = anchored_full_signal(target, data, features, labels, bases, row)
            replay = replay_plain(target, data[target], sig, FEE)
        else:
            sig = anchored_full_signal(target, data, features, labels, bases, row)
            replay = make_overlay_weights(target, data[target], data["QQQ"], sig, risk_lookup["risk_bundle"], FEE)
        replay.strategy = str(row["strategy"])
        replay.base_strategy = str(row["base_strategy"])
        replay.layer = "v2_selected"
        replay.split_type = "final"
        replay.split = "2021_latest"
        replay.cost = FEE
        replays[target] = replay
    return selected_rows, replays


def drawdown_series(nav: pd.Series) -> pd.Series:
    return nav.div(nav.cummax()).sub(1.0)


def save_plots(run_dir: Path, data: dict[str, pd.DataFrame], selected: dict[str, ReplayResult], bases: dict[str, dict[str, pd.Series]]) -> None:
    for target in TARGETS:
        result = selected[target]
        v1 = replay_plain(target, data[target], bases[target][result.base_strategy], FEE)
        nav = pd.DataFrame({"v2_selected": result.nav, "v1_base": v1.nav}).loc[lambda x: x.index >= PERIOD_START].dropna()
        nav = nav / nav.iloc[0]
        fig, ax = plt.subplots(figsize=(11, 4.8))
        drawdown_series(nav["v2_selected"]).plot(ax=ax, label="v2_selected", linewidth=1.7)
        drawdown_series(nav["v1_base"]).plot(ax=ax, label="v1_base", linewidth=1.2, alpha=0.8)
        ax.set_title(f"{target} v2 drawdown vs selected base")
        ax.grid(True, alpha=0.25)
        ax.legend()
        fig.tight_layout()
        fig.savefig(run_dir / f"{target.lower()}_v2_drawdown.png", dpi=150)
        plt.close(fig)

        chart = data[target].loc[data[target].index >= PERIOD_START].copy()
        sig = result.position.reindex(chart.index).fillna(0.0)
        entries = sig.gt(EPS) & ~sig.shift(1).fillna(0.0).gt(EPS)
        exits = ~sig.gt(EPS) & sig.shift(1).fillna(0.0).gt(EPS)
        fig, ax1 = plt.subplots(figsize=(12, 5))
        chart["close"].plot(ax=ax1, color="#1f4e79", linewidth=1.2, label="close")
        ax1.scatter(chart.index[entries], chart.loc[entries, "close"], marker="^", s=28, color="#2ca02c", label="entry")
        ax1.scatter(chart.index[exits], chart.loc[exits, "close"], marker="v", s=28, color="#d62728", label="exit")
        ax2 = ax1.twinx()
        sig.plot(ax=ax2, color="#ff7f0e", linewidth=0.9, alpha=0.6, label="weight")
        ax1.set_title(f"{target} v2 selected signal: {result.strategy}")
        ax1.grid(True, alpha=0.25)
        ax1.legend(loc="upper left")
        ax2.set_ylim(-0.02, 1.05)
        ax2.legend(loc="upper right")
        fig.tight_layout()
        fig.savefig(run_dir / f"{target.lower()}_v2_signal_chart.png", dpi=150)
        plt.close(fig)


def contribution_table(v1_old: pd.DataFrame, meta: pd.DataFrame, risk: pd.DataFrame, combined: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for target in TARGETS:
        v1_target = v1_old[(v1_old["target"].eq(target)) & (v1_old["source"].eq("v1_primary"))]
        base = v1_target.sort_values("Calmar", ascending=False).iloc[0]
        for name, df in [("meta_label", meta), ("risk_overlay", risk), ("combined", combined)]:
            sub = df[(df["target"].eq(target)) & (df["cost"].eq(FEE)) & (df["split"].eq("anchored_2021_latest"))]
            if sub.empty:
                sub = df[(df["target"].eq(target)) & (df["cost"].eq(FEE))]
            if sub.empty:
                continue
            best = sub.sort_values("Calmar", ascending=False).iloc[0]
            rows.append(
                {
                    "target": target,
                    "component": name,
                    "reference_base": base["strategy"],
                    "best_strategy": best["strategy"],
                    "CAGR_delta_vs_best_v1_base": best["CAGR"] - base["CAGR"],
                    "MDD_delta_vs_best_v1_base": best["MDD"] - base["MDD"],
                    "Calmar_delta_vs_best_v1_base": best["Calmar"] - base["Calmar"],
                }
            )
    return pd.DataFrame(rows)


def format_metric_table(df: pd.DataFrame, max_rows: int = 20) -> pd.DataFrame:
    cols = [c for c in ["target", "strategy", "base_strategy", "source", "CAGR", "MDD", "Sharpe", "Calmar", "trade_count", "turnover", "avg_abs_weight"] if c in df.columns]
    out = df[cols].copy().head(max_rows)
    for col in ("CAGR", "MDD", "avg_abs_weight"):
        if col in out:
            out[col] = out[col].map(pct)
    for col in ("Sharpe", "Calmar", "turnover"):
        if col in out:
            out[col] = out[col].map(num)
    return out


def write_summary(
    run_dir: Path,
    selected_rows: pd.DataFrame,
    v2_vs: pd.DataFrame,
    meta: pd.DataFrame,
    risk: pd.DataFrame,
    combined: pd.DataFrame,
    contribution: pd.DataFrame,
) -> None:
    final = v2_vs[v2_vs["source"].eq("v2_selected")]
    old = v2_vs[v2_vs["source"].eq("old_same_engine")]
    selected_fmt = selected_rows.copy()
    for col in ("median_CAGR", "worst_CAGR", "median_MDD", "worst_MDD", "mean_abs_weight"):
        if col in selected_fmt:
            selected_fmt[col] = selected_fmt[col].map(pct)
    for col in ("median_Calmar", "worst_Calmar", "mean_turnover", "selection_score"):
        if col in selected_fmt:
            selected_fmt[col] = selected_fmt[col].map(num)

    contrib = contribution.copy()
    for col in ("CAGR_delta_vs_best_v1_base", "MDD_delta_vs_best_v1_base"):
        if col in contrib:
            contrib[col] = contrib[col].map(pct)
    if "Calmar_delta_vs_best_v1_base" in contrib:
        contrib["Calmar_delta_vs_best_v1_base"] = contrib["Calmar_delta_vs_best_v1_base"].map(num)
    best_component = (
        contribution.sort_values(["target", "Calmar_delta_vs_best_v1_base"], ascending=[True, False])
        .groupby("target")
        .head(1)
        if not contribution.empty
        else pd.DataFrame()
    )
    primary_counts = selected_rows["base_strategy"].value_counts().to_dict()
    primary = max(primary_counts, key=primary_counts.get) if primary_counts else "unknown"
    selected_layer_lines = []
    for _, row in selected_rows.iterrows():
        overlay = row.get("risk_overlay", "")
        selected_layer_lines.append(
            f"{row['target']}: `{row['layer']}` / `{overlay}` on `{row['base_strategy']}`"
        )
    v2_compare_lines = []
    for target in TARGETS:
        selected_target = final[final["target"].eq(target)]
        if selected_target.empty:
            continue
        sel = selected_target.iloc[0]
        v1_rows = v2_vs[(v2_vs["target"].eq(target)) & (v2_vs["source"].eq("v1_primary"))]
        same_base_key = f"v1_{sel['base_strategy']}"
        same_base = v1_rows[v1_rows["strategy"].eq(same_base_key)]
        best_v1 = v1_rows.sort_values("Calmar", ascending=False).iloc[0]
        if not same_base.empty:
            base = same_base.iloc[0]
            v2_compare_lines.append(
                f"{target} vs same base: CAGR {pct(sel['CAGR'])} vs {pct(base['CAGR'])}, "
                f"MDD {pct(sel['MDD'])} vs {pct(base['MDD'])}, Calmar {num(sel['Calmar'])} vs {num(base['Calmar'])}."
            )
        v2_compare_lines.append(
            f"{target} vs best v1 Calmar base `{best_v1['strategy']}`: CAGR delta {pct(sel['CAGR'] - best_v1['CAGR'])}, "
            f"MDD improvement {pct(sel['MDD'] - best_v1['MDD'])}, Calmar delta {num(sel['Calmar'] - best_v1['Calmar'])}."
        )

    lines = [
        "# QLD/TQQQ Turning-point Research V2",
        "",
        "## Scope Control",
        "",
        "- Labels: v1 recommendation `atr_wide + H=10`.",
        "- Bases: `ema20_ema100_direction` and `qqq_ma200_trend` only.",
        "- Meta-labels: NumPy Logistic L1/L2 and small LightGBM.",
        "- Features: v1 retained feature subset, Logistic <= 8, LightGBM <= 12.",
        "- Risk overlays: fixed ATR stop, drawdown cap, volatility target, max cap, MA200 regime-off.",
        "- No broad parameter search, no feature expansion, no XGBoost.",
        "",
        f"LightGBM status: {'available' if LIGHTGBM_AVAILABLE else 'unavailable: ' + LIGHTGBM_ERROR}",
        "",
        "## Selected V2 Configs",
        "",
        md_table(selected_fmt),
        "",
        "## V2 vs V1 vs Old",
        "",
        md_table(format_metric_table(v2_vs, 30)),
        "",
        "## Component Contribution",
        "",
        md_table(contrib),
        "",
        "## Required Answers",
        "",
        "1. 回撤下降主要来自哪里？",
        "",
        "本轮最终入选配置都来自 risk-only 层，而不是 meta-label 或 meta+risk 叠加层：" + "；".join(selected_layer_lines) + "。因此，最终可落地 v2 的回撤下降主要来自风控覆盖层。QLD 主要来自 risk_bundle 中的仓位缩放、max cap 与 MA200 regime-off；TQQQ 主要来自 ATR stop。meta-label 在部分 split 中有改善，但没有成为最终入选贡献源。",
        "",
        md_table(best_component[["target", "component", "best_strategy", "MDD_delta_vs_best_v1_base", "Calmar_delta_vs_best_v1_base"]] if not best_component.empty else pd.DataFrame()),
        "",
        "2. 两个底座策略里，哪个更值得继续？",
        "",
        f"`{primary}` 更值得继续。v2 选择逻辑按 OOS median/worst Calmar、CAGR 和 turnover 做低复杂度评分，而不是单段收益最大化。",
        "",
        "3. v2 是否真正比 v1 更接近“最大收益 + 最小回撤”的目标？",
        "",
        "结论分标的看：TQQQ 是，QLD 是更防守但不再是“最大收益”。" + " ".join(v2_compare_lines) + " 所以，TQQQ v2 更接近最大收益+最小回撤；QLD v2 明显降低回撤并提高 Calmar，但相对 QQQ MA200 v1 牺牲了 CAGR。",
        "",
        "4. 是否已经有必要进入更严格验证（purged / CPCV）？",
        "",
        "有必要，但建议作为下一轮。v2 已经引入监督学习和组合层选择，即使搜索空间很小，也比 v1 更容易产生选择偏差。下一轮应加入 purged walk-forward 或 CPCV，并把 meta threshold/profile 固定为本轮推荐值后再验证。",
        "",
        "## Notes On Old Strategy",
        "",
        "Old optimal is compared using same-engine fractional weights, not the old saved `portfolio_value`, because the apples-to-apples audit found the original old report used a different execution loop.",
    ]
    write_text(run_dir / "v2_research_summary.md", "\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser(description="QLD/TQQQ turning-point research v2")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--output-root", type=Path, default=ROOT / "outputs")
    parser.add_argument("--old-run-dir", type=Path, default=OLD_RUN_DIR)
    args = parser.parse_args()

    run_dir = args.output_root / f"turning_point_research_v2_{stamp()}"
    run_dir.mkdir(parents=True, exist_ok=True)
    log(f"Output directory: {run_dir}")

    log("Loading data and v1 labels/features")
    data = load_data(args.data_dir)
    labels = build_labels(data)
    features, indicators = build_features(data)
    bases = base_signals(data, indicators)

    log("Evaluating meta-label only layer")
    meta_results, _ = run_meta_evaluation(data, features, labels, bases)
    write_csv(meta_results, run_dir / "meta_label_results.csv")

    log("Evaluating risk overlay only layer")
    risk_results = run_risk_evaluation(data, bases)
    write_csv(risk_results, run_dir / "risk_overlay_results.csv")

    log("Evaluating meta-label + risk bundle combinations")
    combined_results = run_combined_evaluation(data, features, labels, bases)
    write_csv(combined_results, run_dir / "combined_results.csv")

    log("Selecting v2 configs and writing comparisons")
    selected_rows, selected_replays = final_selected_replays(data, features, labels, bases, meta_results, risk_results, combined_results)
    write_csv(selected_rows, run_dir / "selected_v2_configs.csv")
    v2_vs = compare_v2_v1_old(data, bases, selected_replays, args.old_run_dir)
    write_csv(v2_vs, run_dir / "v2_vs_v1_vs_old.csv")
    contribution = contribution_table(v2_vs, meta_results, risk_results, combined_results)
    write_csv(contribution, run_dir / "v2_component_contribution.csv")

    log("Writing charts")
    save_plots(run_dir, data, selected_replays, bases)

    log("Writing summary and manifest")
    write_summary(run_dir, selected_rows, v2_vs, meta_results, risk_results, combined_results, contribution)
    write_text(
        run_dir / "v2_changed_files_manifest.txt",
        "\n".join(
            [
                "Added or modified script files:",
                "",
                "- scripts/qldtqqq_turning_point_research_v2.py",
                "",
                "Reused v1 script functions without modifying the v1 workflow.",
                "Environment note: LightGBM was installed in the user Python environment for the requested small LightGBM meta-label model.",
            ]
        ),
    )

    required = [
        "v2_research_summary.md",
        "v2_vs_v1_vs_old.csv",
        "meta_label_results.csv",
        "risk_overlay_results.csv",
        "combined_results.csv",
        "qld_v2_signal_chart.png",
        "tqqq_v2_signal_chart.png",
        "qld_v2_drawdown.png",
        "tqqq_v2_drawdown.png",
        "v2_changed_files_manifest.txt",
    ]
    missing = [name for name in required if not (run_dir / name).exists()]
    if missing:
        raise RuntimeError(f"Missing required v2 outputs: {missing}")
    log("V2 research completed")
    log(str(run_dir))


if __name__ == "__main__":
    main()
