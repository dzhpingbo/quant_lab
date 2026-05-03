"""QLD/TQQQ turning-point strategy lab.

This script implements a focused version of the user's methodology:

1. Refresh QLD/TQQQ and cross-market data.
2. Label QQQ-driven volatility tops and bottoms.
3. Build TD9, VIX, Bollinger, RSI, breadth, fear/greed, and valuation proxies.
4. Train walk-forward ML models for bottom/top probabilities.
5. Combine rule and ML signals into multi-sleeve strategies.
6. Backtest with strict costs, volatility sizing, trailing stops, and drawdown stops.
7. Write diagnostics for missed tops/bottoms and a reusable report.

The target is not to maximize hindsight return. The ranking prioritizes
out-of-sample Calmar/Sharpe, controlled drawdown, cross-cycle consistency, and
actual turning-point capture.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import warnings
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Mapping

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

TMP = ROOT / ".tmp"
NUMBA_CACHE = ROOT / ".numba_cache"
TMP.mkdir(exist_ok=True)
NUMBA_CACHE.mkdir(exist_ok=True)
os.environ.setdefault("TMP", str(TMP))
os.environ.setdefault("TEMP", str(TMP))
os.environ.setdefault("NUMBA_CACHE_DIR", str(NUMBA_CACHE))
warnings.filterwarnings("ignore", category=FutureWarning)

import vectorbt as vbt
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import precision_recall_fscore_support, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

import vbt_us_leverage_online as base


OUT_ROOT = ROOT / "outputs" / "qldtqqq_turning_points"
TARGETS = ("QLD", "TQQQ")
ESSENTIAL = ("QLD", "TQQQ", "QQQ", "_VIX", "SPY")
CONTEXT = (
    "SPY",
    "TLT",
    "SHY",
    "GLD",
    "IWM",
    "XLK",
    "SOXX",
    "SQQQ",
    "PSQ",
    "UUP",
    "RSP",
    "QQEW",
    "^VXN",
)
FOLDS = (
    ("2014_2016", "2014-01-01", "2016-12-31"),
    ("2017_2019", "2017-01-01", "2019-12-31"),
    ("2020_2022", "2020-01-01", "2022-12-31"),
    ("2023_latest", "2023-01-01", None),
)
WF_START = "2014-01-01"


@dataclass(frozen=True)
class Candidate:
    name: str
    family: str
    signal: pd.Series
    notes: str


@dataclass(frozen=True)
class RiskSpec:
    name: str
    vol_target: float
    max_weight: float
    trail_stop: float
    kill_dd: float
    cooldown: int
    gate: str


def stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def clean_json(value):
    if value is None:
        return None
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    return value


def jready(obj):
    if isinstance(obj, dict):
        return {str(k): jready(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jready(v) for v in obj]
    return clean_json(obj)


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(jready(data), ensure_ascii=False, indent=2), encoding="utf-8")


def checkpoint(run_dir: Path, stage: str, title: str, payload: Mapping[str, object], next_step: str) -> None:
    body = {
        "stage": stage,
        "title": title,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "payload": dict(payload),
        "next_step": next_step,
    }
    write_json(run_dir / f"checkpoint_{stage}.json", body)
    lines = [f"# {title}", "", f"- Stage: `{stage}`", f"- Time: {body['time']}", f"- Next step: {next_step}", "", "## Payload", ""]
    for key, value in payload.items():
        if isinstance(value, (dict, list, tuple)):
            lines.extend([f"### {key}", "", "```json", json.dumps(jready(value), ensure_ascii=False, indent=2), "```", ""])
        else:
            lines.append(f"- {key}: {value}")
    (run_dir / f"checkpoint_{stage}.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


base.full_mod.checkpoint = checkpoint
base.full_mod.write_json = write_json


def pct(value) -> str:
    if value is None or pd.isna(value):
        return "nan"
    return f"{float(value) * 100:.2f}%"


def md_table(df: pd.DataFrame, max_rows: int | None = None) -> str:
    if df is None or df.empty:
        return "_Empty._"
    small = df.copy()
    if max_rows is not None:
        small = small.head(max_rows)
    for col in small.columns:
        small[col] = small[col].map(lambda x: "" if pd.isna(x) else str(x).replace("|", "/"))
    header = "| " + " | ".join(map(str, small.columns)) + " |"
    sep = "| " + " | ".join(["---"] * len(small.columns)) + " |"
    rows = ["| " + " | ".join(row) + " |" for row in small.astype(str).to_numpy()]
    return "\n".join([header, sep, *rows])


def align(frame: pd.DataFrame, index: pd.Index) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame(index=index)
    return frame.reindex(index).ffill()


def ema(series: pd.Series, window: int) -> pd.Series:
    return series.ewm(span=window, adjust=False).mean()


def rsi(close: pd.Series, window: int = 14) -> pd.Series:
    diff = close.diff()
    up = diff.clip(lower=0).ewm(alpha=1 / window, adjust=False).mean()
    down = (-diff.clip(upper=0)).ewm(alpha=1 / window, adjust=False).mean()
    return 100 - 100 / (1 + up.div(down.replace(0, np.nan)))


def rolling_percentile_last(series: pd.Series, window: int) -> pd.Series:
    def pct_rank(values: np.ndarray) -> float:
        values = values[np.isfinite(values)]
        if len(values) < 5:
            return np.nan
        return float((values <= values[-1]).mean())

    return series.rolling(window, min_periods=max(20, window // 5)).apply(pct_rank, raw=True)


def zscore(series: pd.Series, window: int) -> pd.Series:
    mean = series.rolling(window, min_periods=max(20, window // 4)).mean()
    std = series.rolling(window, min_periods=max(20, window // 4)).std(ddof=0)
    return (series - mean).div(std.replace(0, np.nan))


def td_counts(close: pd.Series, lookback: int = 4, setup: int = 9) -> tuple[pd.Series, pd.Series]:
    down = close < close.shift(lookback)
    up = close > close.shift(lookback)
    buy = np.zeros(len(close), dtype=float)
    sell = np.zeros(len(close), dtype=float)
    b_run = 0
    s_run = 0
    for i, (b, s) in enumerate(zip(down.fillna(False), up.fillna(False))):
        b_run = b_run + 1 if b else 0
        s_run = s_run + 1 if s else 0
        buy[i] = min(b_run, setup)
        sell[i] = min(s_run, setup)
    return pd.Series(buy, index=close.index), pd.Series(sell, index=close.index)


def forward_extreme_returns(close: pd.Series, horizon: int) -> tuple[pd.Series, pd.Series]:
    values = close.to_numpy(dtype=float)
    max_ret = np.full(len(values), np.nan)
    min_ret = np.full(len(values), np.nan)
    for i, price in enumerate(values):
        if not np.isfinite(price) or price <= 0:
            continue
        future = values[i + 1 : i + 1 + horizon]
        future = future[np.isfinite(future)]
        if len(future) == 0:
            continue
        max_ret[i] = np.nanmax(future) / price - 1.0
        min_ret[i] = np.nanmin(future) / price - 1.0
    return pd.Series(max_ret, index=close.index), pd.Series(min_ret, index=close.index)


def collapse_events(mask: pd.Series, score: pd.Series, kind: str, min_gap: int = 10) -> pd.DataFrame:
    rows = []
    active: list[pd.Timestamp] = []
    for dt, flag in mask.fillna(False).items():
        if flag:
            active.append(dt)
            continue
        if active:
            subset = score.reindex(active)
            event_dt = subset.idxmin() if kind == "bottom" else subset.idxmax()
            rows.append({"event_type": kind, "event_date": event_dt})
            active = []
    if active:
        subset = score.reindex(active)
        event_dt = subset.idxmin() if kind == "bottom" else subset.idxmax()
        rows.append({"event_type": kind, "event_date": event_dt})
    if not rows:
        return pd.DataFrame(columns=["event_type", "event_date"])
    out = pd.DataFrame(rows).sort_values("event_date")
    kept = []
    last_dt = None
    for row in out.to_dict("records"):
        dt = pd.Timestamp(row["event_date"])
        if last_dt is not None and (dt - last_dt).days < min_gap:
            continue
        kept.append(row)
        last_dt = dt
    return pd.DataFrame(kept)


def label_turning_points(qqq: pd.DataFrame, horizon: int = 20) -> tuple[pd.DataFrame, pd.DataFrame]:
    close = qqq["close"].astype(float)
    future_up, future_down = forward_extreme_returns(close, horizon)
    prior_ret20 = close.pct_change(20)
    prior_ret60 = close.pct_change(60)
    dd20 = close / close.rolling(20).max() - 1.0
    dd60 = close / close.rolling(60).max() - 1.0
    runup20 = close / close.rolling(20).min() - 1.0
    runup60 = close / close.rolling(60).min() - 1.0

    bottom_mask = (
        (future_up >= 0.055)
        & ((dd20 <= -0.035) | (dd60 <= -0.07) | (prior_ret20 < -0.025))
        & (future_down > -0.045)
    )
    top_mask = (
        (future_down <= -0.045)
        & ((runup20 >= 0.055) | (runup60 >= 0.10) | (prior_ret60 > 0.09))
        & (future_up < 0.045)
    )
    labels = pd.DataFrame(
        {
            "bottom_label": bottom_mask.astype(float),
            "top_label": top_mask.astype(float),
            "future_up_20": future_up,
            "future_down_20": future_down,
            "prior_ret20": prior_ret20,
            "prior_ret60": prior_ret60,
            "drawdown20": dd20,
            "drawdown60": dd60,
            "runup20": runup20,
            "runup60": runup60,
        },
        index=close.index,
    )
    bottom_events = collapse_events(bottom_mask, close, "bottom", min_gap=12)
    top_events = collapse_events(top_mask, close, "top", min_gap=12)
    events = pd.concat([bottom_events, top_events], ignore_index=True).sort_values("event_date")
    if not events.empty:
        events["qqq_close"] = events["event_date"].map(close)
    return labels, events


def fetch_cnn_fear_greed(run_dir: Path, index: pd.Index) -> tuple[pd.Series, dict]:
    url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
    meta = {"source": url, "status": "not_used", "rows": 0, "latest": None, "error": ""}
    try:
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
        response.raise_for_status()
        payload = response.json()
        records = []
        hist = ((payload.get("fear_and_greed_historical") or {}).get("data")) or []
        for row in hist:
            x = row.get("x")
            y = row.get("y")
            if x is None or y is None:
                continue
            unit = "ms" if float(x) > 10_000_000_000 else "s"
            records.append({"date": pd.to_datetime(float(x), unit=unit).tz_localize(None).normalize(), "fear_greed": float(y)})
        raw = pd.DataFrame(records).dropna()
        if raw.empty:
            raise RuntimeError("empty CNN fear/greed history")
        raw = raw.drop_duplicates("date", keep="last").set_index("date").sort_index()
        raw.to_csv(run_dir / "cnn_fear_greed_raw.csv", encoding="utf-8-sig")
        series = raw["fear_greed"].reindex(index).ffill()
        meta.update({"status": "ok", "rows": int(len(raw)), "latest": raw.index.max().strftime("%Y-%m-%d")})
        return series.rename("cnn_fear_greed"), meta
    except Exception as exc:
        meta.update({"status": "failed", "error": f"{type(exc).__name__}: {exc}"})
        return pd.Series(np.nan, index=index, name="cnn_fear_greed"), meta


def fetch_sp500_pe(run_dir: Path, index: pd.Index) -> tuple[pd.Series, dict]:
    url = "https://www.multpl.com/s-p-500-pe-ratio/table/by-month"
    meta = {"source": url, "status": "not_used", "rows": 0, "latest": None, "error": ""}
    try:
        tables = pd.read_html(url)
        if not tables:
            raise RuntimeError("no tables")
        raw = tables[0].copy()
        raw.columns = [str(c).strip().lower() for c in raw.columns]
        date_col = next((c for c in raw.columns if "date" in c), raw.columns[0])
        value_col = next((c for c in raw.columns if "value" in c or "ratio" in c), raw.columns[-1])
        raw["date"] = pd.to_datetime(raw[date_col], errors="coerce")
        raw["sp500_pe"] = pd.to_numeric(raw[value_col].astype(str).str.extract(r"([-+]?\d*\.?\d+)")[0], errors="coerce")
        raw = raw.dropna(subset=["date", "sp500_pe"]).drop_duplicates("date", keep="last").set_index("date").sort_index()
        raw.to_csv(run_dir / "sp500_pe_raw.csv", encoding="utf-8-sig")
        series = raw["sp500_pe"].reindex(index).ffill()
        meta.update({"status": "ok", "rows": int(len(raw)), "latest": raw.index.max().strftime("%Y-%m-%d")})
        return series.rename("sp500_pe"), meta
    except Exception as exc:
        meta.update({"status": "failed", "error": f"{type(exc).__name__}: {exc}"})
        return pd.Series(np.nan, index=index, name="sp500_pe"), meta


def build_feature_frame(
    data: Mapping[str, pd.DataFrame],
    index: pd.Index,
    run_dir: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    qqq = align(data["QQQ"], index)
    spy = align(data["SPY"], index)
    vix = align(data["_VIX"], index)
    qclose = qqq["close"].astype(float)
    vclose = vix["close"].astype(float)
    features = pd.DataFrame(index=index)

    q_td_buy, q_td_sell = td_counts(qclose)
    features["td9_buy"] = q_td_buy
    features["td9_sell"] = q_td_sell
    features["td9_net"] = q_td_buy - q_td_sell
    for window in (2, 5, 14):
        features[f"rsi{window}"] = rsi(qclose, window)
    mid = qclose.rolling(20).mean()
    std = qclose.rolling(20).std(ddof=0)
    upper = mid + 2 * std
    lower = mid - 2 * std
    features["boll_pos20"] = (qclose - mid).div((2 * std).replace(0, np.nan))
    features["boll_pctb20"] = (qclose - lower).div((upper - lower).replace(0, np.nan))
    features["boll_width20"] = (upper - lower).div(mid.replace(0, np.nan))
    for window in (20, 60, 120, 252):
        features[f"roc{window}"] = qclose.pct_change(window)
        features[f"drawdown{window}"] = qclose / qclose.rolling(window).max() - 1.0
        features[f"runup{window}"] = qclose / qclose.rolling(window).min() - 1.0
    for window in (50, 100, 150, 200):
        ma = qclose.rolling(window).mean()
        features[f"dist_ma{window}"] = qclose.div(ma.replace(0, np.nan)) - 1.0
        features[f"above_ma{window}"] = (qclose > ma).astype(float)
    features["ema3_120_ratio"] = ema(qclose, 3).div(ema(qclose, 120).replace(0, np.nan)) - 1.0
    features["realized_vol20"] = qclose.pct_change().rolling(20).std() * math.sqrt(252)
    features["realized_vol60"] = qclose.pct_change().rolling(60).std() * math.sqrt(252)
    features["vol_pct252"] = rolling_percentile_last(features["realized_vol20"], 252)

    features["vix"] = vclose
    features["vix_pct252"] = rolling_percentile_last(vclose, 252)
    features["vix_pct756"] = rolling_percentile_last(vclose, 756)
    features["vix_z60"] = zscore(vclose, 60)
    features["vix_chg5"] = vclose.pct_change(5)
    features["vix_spike20"] = vclose.div(vclose.rolling(20).mean().replace(0, np.nan)) - 1.0
    features["vix_contango_proxy"] = vclose - vclose.rolling(20).mean()

    breadth_parts = []
    for symbol in ("QQQ", "SPY", "XLK", "SOXX", "IWM", "RSP", "QQEW"):
        frame = align(data.get(symbol, pd.DataFrame()), index)
        if "close" not in frame:
            continue
        close = frame["close"].astype(float)
        breadth_parts.append((close > close.rolling(50).mean()).astype(float).rename(f"{symbol}_above50"))
        breadth_parts.append((close > close.rolling(200).mean()).astype(float).rename(f"{symbol}_above200"))
    if breadth_parts:
        breadth = pd.concat(breadth_parts, axis=1)
        features["breadth_proxy"] = breadth.mean(axis=1)
    else:
        features["breadth_proxy"] = np.nan

    shy = align(data.get("SHY", pd.DataFrame()), index)
    tlt = align(data.get("TLT", pd.DataFrame()), index)
    if "close" in shy and "close" in tlt:
        features["safe_momentum_gap"] = qclose.pct_change(63) - pd.concat(
            [shy["close"].pct_change(63), tlt["close"].pct_change(63)], axis=1
        ).max(axis=1)
    else:
        features["safe_momentum_gap"] = np.nan

    fng, fng_meta = fetch_cnn_fear_greed(run_dir, index)
    pe, pe_meta = fetch_sp500_pe(run_dir, index)
    features["cnn_fear_greed"] = fng
    features["sp500_pe"] = pe
    features["sp500_pe_pct120"] = rolling_percentile_last(pe, 120)
    valuation_proxy = rolling_percentile_last(qclose.div(qclose.rolling(756).mean()), 756)
    features["valuation_proxy"] = features["sp500_pe_pct120"].fillna(valuation_proxy)

    fear_proxy = (
        0.30 * features["vix_pct252"]
        + 0.22 * (1 - features["rsi14"].clip(0, 100) / 100)
        + 0.20 * (-features["drawdown60"]).clip(0, 0.35).div(0.35)
        + 0.14 * features["vol_pct252"]
        + 0.14 * (1 - features["cnn_fear_greed"].clip(0, 100) / 100)
    )
    features["fear_proxy"] = fear_proxy.clip(0, 1)
    features["greed_proxy"] = (
        0.24 * (features["rsi14"].clip(0, 100) / 100)
        + 0.22 * (1 - features["vix_pct252"])
        + 0.20 * features["runup60"].clip(0, 0.35).div(0.35)
        + 0.18 * features["breadth_proxy"]
        + 0.16 * features["valuation_proxy"]
    ).clip(0, 1)

    scores = pd.DataFrame(index=index)
    scores["bottom_score"] = 0.0
    scores["bottom_score"] += (features["td9_buy"] >= 6).astype(float)
    scores["bottom_score"] += (features["td9_buy"] >= 8).astype(float)
    scores["bottom_score"] += (features["rsi2"] <= 12).astype(float)
    scores["bottom_score"] += (features["rsi14"] <= 32).astype(float)
    scores["bottom_score"] += (features["boll_pctb20"] <= 0.05).astype(float)
    scores["bottom_score"] += (features["vix_pct252"] >= 0.80).astype(float)
    scores["bottom_score"] += (features["vix_spike20"] >= 0.18).astype(float)
    scores["bottom_score"] += (features["drawdown20"] <= -0.07).astype(float)
    scores["bottom_score"] += (features["drawdown60"] <= -0.12).astype(float)
    scores["bottom_score"] += (features["fear_proxy"] >= 0.70).astype(float)
    scores["bottom_score"] += ((features["cnn_fear_greed"] <= 25) & features["cnn_fear_greed"].notna()).astype(float)

    scores["top_score"] = 0.0
    scores["top_score"] += (features["td9_sell"] >= 6).astype(float)
    scores["top_score"] += (features["td9_sell"] >= 8).astype(float)
    scores["top_score"] += (features["rsi2"] >= 88).astype(float)
    scores["top_score"] += (features["rsi14"] >= 70).astype(float)
    scores["top_score"] += (features["boll_pctb20"] >= 0.95).astype(float)
    scores["top_score"] += (features["runup20"] >= 0.09).astype(float)
    scores["top_score"] += (features["runup60"] >= 0.18).astype(float)
    scores["top_score"] += (features["greed_proxy"] >= 0.72).astype(float)
    scores["top_score"] += (features["valuation_proxy"] >= 0.82).astype(float)
    scores["top_score"] += ((features["cnn_fear_greed"] >= 75) & features["cnn_fear_greed"].notna()).astype(float)

    scores["trend_score"] = 0.0
    scores["trend_score"] += (features["above_ma100"] > 0.5).astype(float)
    scores["trend_score"] += (features["above_ma200"] > 0.5).astype(float)
    scores["trend_score"] += (features["ema3_120_ratio"] > 0).astype(float)
    scores["trend_score"] += (features["roc20"] > 0).astype(float)
    scores["trend_score"] += (features["breadth_proxy"] >= 0.55).astype(float)
    scores["risk_off_score"] = scores["top_score"] + (features["vix"] > 35).astype(float) + (scores["trend_score"] <= 1).astype(float)

    meta = {"fear_greed": fng_meta, "sp500_pe": pe_meta}
    return features, scores, meta


def feature_columns(features: pd.DataFrame) -> list[str]:
    exclude = {"cnn_fear_greed", "sp500_pe"}
    cols = []
    for col in features.columns:
        if col in exclude:
            continue
        series = features[col].replace([np.inf, -np.inf], np.nan)
        if series.notna().mean() >= 0.45 and series.nunique(dropna=True) > 5:
            cols.append(col)
    return cols


def fit_predict_fold(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_test: pd.DataFrame,
    random_state: int,
) -> tuple[np.ndarray, dict]:
    if y_train.nunique() < 2:
        raise ValueError("training label has one class")
    logit = make_pipeline(
        SimpleImputer(strategy="median"),
        StandardScaler(),
        LogisticRegression(max_iter=600, class_weight="balanced", C=0.65, random_state=random_state),
    )
    forest = make_pipeline(
        SimpleImputer(strategy="median"),
        RandomForestClassifier(
            n_estimators=320,
            max_depth=5,
            min_samples_leaf=25,
            max_features="sqrt",
            class_weight="balanced_subsample",
            n_jobs=1,
            random_state=random_state,
        ),
    )
    logit.fit(X_train, y_train.astype(int))
    forest.fit(X_train, y_train.astype(int))
    p_logit = logit.predict_proba(X_test)[:, 1]
    p_forest = forest.predict_proba(X_test)[:, 1]
    prob = 0.45 * p_logit + 0.55 * p_forest
    meta = {
        "train_rows": int(len(X_train)),
        "test_rows": int(len(X_test)),
        "positive_rate": float(y_train.mean()),
    }
    return prob, meta


def walk_forward_probabilities(
    features: pd.DataFrame,
    labels: pd.DataFrame,
    cols: list[str],
    run_dir: Path,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    X = features[cols].replace([np.inf, -np.inf], np.nan)
    probs = pd.DataFrame(index=features.index, columns=["bottom_prob", "top_prob"], dtype=float)
    fold_rows = []
    for label_name, prob_name, seed in (("bottom_label", "bottom_prob", 101), ("top_label", "top_prob", 202)):
        y = labels[label_name].reindex(features.index)
        for fold_name, start, end in FOLDS:
            start_ts = pd.Timestamp(start)
            end_ts = pd.Timestamp(end) if end else features.index.max()
            train_mask = (X.index < start_ts) & y.notna()
            test_mask = (X.index >= start_ts) & (X.index <= end_ts)
            valid_cols = X.loc[train_mask].notna().mean()
            selected = valid_cols[valid_cols >= 0.60].index.tolist()
            if len(selected) < 8 or train_mask.sum() < 450 or test_mask.sum() == 0:
                fold_rows.append(
                    {
                        "target_label": label_name,
                        "fold": fold_name,
                        "status": "skipped",
                        "selected_features": len(selected),
                        "train_rows": int(train_mask.sum()),
                        "test_rows": int(test_mask.sum()),
                    }
                )
                continue
            try:
                prob, meta = fit_predict_fold(X.loc[train_mask, selected], y.loc[train_mask], X.loc[test_mask, selected], seed)
                probs.loc[test_mask, prob_name] = prob
                y_test = y.loc[test_mask].dropna()
                p_test = pd.Series(prob, index=X.loc[test_mask].index).reindex(y_test.index)
                pred = p_test >= float(np.nanquantile(p_test, 0.78))
                precision, recall, f1, _ = precision_recall_fscore_support(y_test.astype(int), pred.astype(int), average="binary", zero_division=0)
                try:
                    auc = roc_auc_score(y_test.astype(int), p_test)
                except Exception:
                    auc = np.nan
                row = {
                    "target_label": label_name,
                    "fold": fold_name,
                    "status": "ok",
                    "selected_features": len(selected),
                    "precision_q78": precision,
                    "recall_q78": recall,
                    "f1_q78": f1,
                    "auc": auc,
                    **meta,
                }
            except Exception as exc:
                row = {
                    "target_label": label_name,
                    "fold": fold_name,
                    "status": "failed",
                    "selected_features": len(selected),
                    "train_rows": int(train_mask.sum()),
                    "test_rows": int(test_mask.sum()),
                    "error": f"{type(exc).__name__}: {exc}",
                }
            fold_rows.append(row)
    fold_df = pd.DataFrame(fold_rows)
    fold_df.to_csv(run_dir / "walk_forward_model_folds.csv", index=False, encoding="utf-8-sig")
    probs.to_csv(run_dir / "walk_forward_probabilities.csv", encoding="utf-8-sig")
    return probs, fold_df


def state_machine(
    entry: pd.Series,
    exit_: pd.Series,
    name: str,
    min_hold: int = 0,
    max_hold: int | None = None,
    cooldown: int = 0,
) -> pd.Series:
    held = False
    hold_days = 0
    cool = 0
    out = []
    entry = entry.fillna(False).astype(bool)
    exit_ = exit_.fillna(False).astype(bool)
    for dt in entry.index:
        if cool > 0:
            cool -= 1
        if not held and entry.loc[dt] and cool == 0:
            held = True
            hold_days = 0
        elif held:
            hold_days += 1
            can_exit = hold_days >= min_hold
            too_long = max_hold is not None and hold_days >= max_hold
            if (exit_.loc[dt] and can_exit) or too_long:
                held = False
                hold_days = 0
                cool = cooldown
        out.append(1.0 if held else 0.0)
    return pd.Series(out, index=entry.index, name=name)


def build_candidates(index: pd.Index, features: pd.DataFrame, scores: pd.DataFrame, probs: pd.DataFrame) -> list[Candidate]:
    bottom_score = scores["bottom_score"].reindex(index)
    top_score = scores["top_score"].reindex(index)
    trend_score = scores["trend_score"].reindex(index)
    risk_off = scores["risk_off_score"].reindex(index)
    bottom_prob = probs["bottom_prob"].reindex(index).fillna(0.0)
    top_prob = probs["top_prob"].reindex(index).fillna(0.0)
    candidates: dict[str, Candidate] = {}

    def add(name: str, family: str, signal: pd.Series, notes: str) -> None:
        candidates[name] = Candidate(name, family, signal.reindex(index).ffill().fillna(0.0).clip(0, 1), notes)

    add(
        "core_risk_gate",
        "trend_risk_core",
        pd.Series(1.0, index=index),
        "Core exposure sleeve: stay invested only when the risk gate allows it; sizing, trailing stop, and drawdown kill switch control leverage.",
    )

    qqq_ema_trend = features["ema3_120_ratio"].reindex(index) > 0
    qqq_ma100_trend = features["above_ma100"].reindex(index) > 0.5
    qqq_ma200_trend = features["above_ma200"].reindex(index) > 0.5
    qqq_roc20_ok = features["roc20"].reindex(index) > -0.04
    vix = features["vix"].reindex(index)
    fear_proxy = features["fear_proxy"].reindex(index)
    greed_proxy = features["greed_proxy"].reindex(index)

    def add_core_trim_candidate(
        name: str,
        core: pd.Series,
        bottom_entry: pd.Series,
        top_pressure: pd.Series,
        hard_exit: pd.Series,
        trim_weight: float,
        rebound_weight: float,
        max_rebound_hold: int,
        notes: str,
    ) -> None:
        rebound = state_machine(
            bottom_entry,
            top_pressure | hard_exit,
            name + "_rebound",
            min_hold=3,
            max_hold=max_rebound_hold,
            cooldown=3,
        )
        core = core.fillna(False).astype(bool)
        top_pressure = top_pressure.fillna(False).astype(bool)
        hard_exit = hard_exit.fillna(False).astype(bool)
        raw = pd.Series(0.0, index=index, name=name)
        raw.loc[core] = 1.0
        raw.loc[core & top_pressure] = trim_weight
        raw = pd.concat([raw, rebound.mul(rebound_weight)], axis=1).max(axis=1)
        raw.loc[hard_exit] = 0.0
        add(name, "trend_core_turning_trim", raw, notes)

    for trend_name, core in (
        ("ema3_120", qqq_ema_trend & (trend_score >= 1)),
        ("ma100", qqq_ma100_trend & qqq_roc20_ok),
        ("ma200", qqq_ma200_trend | (qqq_ema_trend & qqq_roc20_ok)),
    ):
        for b_th in (4, 5, 6):
            for t_th in (5, 6, 7):
                for trim in (0.35, 0.55, 0.70):
                    name = f"core_{trend_name}_turn_b{b_th}_t{t_th}_trim{int(trim * 100)}"
                    bottom_entry = (bottom_score >= b_th) | ((bottom_prob >= 0.58) & (fear_proxy >= 0.62))
                    top_pressure = (top_score >= t_th) | ((top_prob >= 0.60) & (top_score >= 3)) | (greed_proxy >= 0.82)
                    hard_exit = (trend_score <= 0) | (vix >= 45) | ((top_score >= t_th + 2) & (top_prob >= 0.66))
                    add_core_trim_candidate(
                        name,
                        core,
                        bottom_entry,
                        top_pressure,
                        hard_exit,
                        trim,
                        1.0,
                        35,
                        (
                            f"Core trend sleeve uses QQQ {trend_name}; TD9/VIX/Bollinger/ML bottom signals restore full weight, "
                            f"top pressure trims to {trim:.0%}, and hard risk exits to cash."
                        ),
                    )

    for pt in (0.62, 0.68, 0.74):
        for trim in (0.40, 0.60):
            name = f"core_ema3_120_ml_toptrim_pt{pt:.2f}_trim{int(trim * 100)}"
            core = (qqq_ema_trend | qqq_ma200_trend) & (vix < 42)
            bottom_entry = (bottom_prob >= 0.56) | (bottom_score >= 5)
            top_pressure = (top_prob >= pt) & ((top_score >= 3) | (greed_proxy >= 0.76))
            hard_exit = (trend_score <= 0) | (vix >= 48) | ((top_prob >= 0.80) & (top_score >= 5))
            add_core_trim_candidate(
                name,
                core,
                bottom_entry,
                top_pressure,
                hard_exit,
                trim,
                1.0,
                45,
                (
                    f"EMA3/120 trend core with walk-forward ML top trim at probability {pt:.2f}; "
                    "bottom model and rule votes restore exposure after pullbacks."
                ),
            )

    for b_th in (4, 5, 6):
        for t_th in (4, 5, 6):
            for trend_min in (1, 2):
                name = f"rule_td9_boll_vix_b{b_th}_t{t_th}_tr{trend_min}"
                entry = (bottom_score >= b_th) & (top_score < t_th) & (trend_score >= trend_min)
                exit_ = (top_score >= t_th) | (risk_off >= t_th + 2)
                add(
                    name,
                    "rule_turning_vote",
                    state_machine(entry, exit_, name, min_hold=3, cooldown=3),
                    f"Enter when composite bottom score >= {b_th} with trend score >= {trend_min}; exit when top/risk score >= {t_th}.",
                )

    for pb in (0.52, 0.56, 0.60, 0.64):
        for pt in (0.52, 0.56, 0.60, 0.64):
            name = f"ml_bottom_top_pb{pb:.2f}_pt{pt:.2f}"
            entry = (bottom_prob >= pb) & (top_prob < pt) & (trend_score >= 1)
            exit_ = (top_prob >= pt) | (risk_off >= 6)
            add(
                name,
                "ml_turning_prob",
                state_machine(entry, exit_, name, min_hold=4, cooldown=5),
                f"Walk-forward ML: enter when bottom probability >= {pb:.2f}; exit when top probability >= {pt:.2f} or risk-off score is high.",
            )

    for pb in (0.54, 0.58, 0.62):
        for b_th in (4, 5):
            for t_th in (4, 5, 6):
                name = f"hybrid_ml_rule_pb{pb:.2f}_b{b_th}_t{t_th}"
                entry = (((bottom_prob >= pb) | (bottom_score >= b_th)) & (top_score < t_th) & (trend_score >= 1))
                exit_ = ((top_prob >= 0.56) & (top_score >= 3)) | (top_score >= t_th) | (risk_off >= t_th + 2)
                add(
                    name,
                    "hybrid_ml_rule",
                    state_machine(entry, exit_, name, min_hold=5, cooldown=5),
                    f"Multi-signal hybrid: ML bottom >= {pb:.2f} or rule bottom >= {b_th}; exit on ML/rule top pressure.",
                )

    for trend_min in (2, 3):
        for pt in (0.54, 0.58, 0.62):
            for t_th in (4, 5, 6):
                name = f"trend_backbone_top_exit_tr{trend_min}_pt{pt:.2f}_t{t_th}"
                entry = (trend_score >= trend_min) & (features["ema3_120_ratio"] > -0.01)
                exit_ = (top_prob >= pt) | (top_score >= t_th) | (trend_score <= 1)
                add(
                    name,
                    "trend_backbone_top_exit",
                    state_machine(entry, exit_, name, min_hold=8, cooldown=4),
                    f"Trend backbone held while trend score >= {trend_min}; top/ML exits are used to cut leverage near wave highs.",
                )

    for b_th in (6, 7):
        for pt in (0.55, 0.60):
            for hold in (10, 15, 20):
                name = f"panic_rebound_b{b_th}_pt{pt:.2f}_h{hold}"
                entry = (bottom_score >= b_th) | ((bottom_prob >= 0.62) & (features["fear_proxy"] >= 0.68))
                exit_ = (top_prob >= pt) | (top_score >= 4)
                add(
                    name,
                    "panic_rebound_sleeve",
                    state_machine(entry, exit_, name, min_hold=2, max_hold=hold, cooldown=5),
                    f"Shorter rebound sleeve for panic lows: enter on very high bottom score; max hold {hold} trading days.",
                )

    for pb in (0.54, 0.58):
        for pt in (0.56, 0.60):
            name = f"ensemble_trend_rebound_pb{pb:.2f}_pt{pt:.2f}"
            trend_sleeve = (trend_score >= 3) & (top_prob < pt) & (top_score < 5)
            rebound_sleeve = (bottom_prob >= pb) | (bottom_score >= 5)
            entry = (trend_sleeve | rebound_sleeve) & (risk_off < 7)
            exit_ = ((top_prob >= pt) & (top_score >= 3)) | (top_score >= 6) | (trend_score <= 0)
            add(
                name,
                "multi_strategy_ensemble",
                state_machine(entry, exit_, name, min_hold=5, cooldown=5),
                "Ensemble of a trend sleeve and a rebound sleeve; exits require ML/rule top confirmation or hard trend failure.",
            )

    return list(candidates.values())


def risk_specs(target: str) -> list[RiskSpec]:
    if target == "TQQQ":
        return [
            RiskSpec("gate_soft_vt22_tr15_k14", 0.22, 1.0, 0.15, 0.14, 15, "soft"),
            RiskSpec("gate_soft_vt25_tr18_k15", 0.25, 1.0, 0.18, 0.15, 15, "soft"),
            RiskSpec("gate_loose_vt32_tr20_k18", 0.32, 1.0, 0.20, 0.18, 15, "loose"),
            RiskSpec("gate_none_vt28_tr18_k18", 0.28, 1.0, 0.18, 0.18, 15, "none"),
            RiskSpec("gate_strict_vt22_tr15_k12", 0.22, 1.0, 0.15, 0.12, 18, "strict"),
            RiskSpec("gate_strict_vt28_tr20_k15", 0.28, 1.0, 0.20, 0.15, 18, "strict"),
            RiskSpec("gate_adaptive_vt25_tr18_k15", 0.25, 1.0, 0.18, 0.15, 15, "adaptive"),
        ]
    return [
        RiskSpec("gate_soft_vt18_tr10_k12", 0.18, 1.0, 0.10, 0.12, 15, "soft"),
        RiskSpec("gate_soft_vt20_tr12_k14", 0.20, 1.0, 0.12, 0.14, 15, "soft"),
        RiskSpec("gate_loose_vt24_tr14_k16", 0.24, 1.0, 0.14, 0.16, 15, "loose"),
        RiskSpec("gate_none_vt22_tr14_k16", 0.22, 1.0, 0.14, 0.16, 15, "none"),
        RiskSpec("gate_strict_vt18_tr10_k10", 0.18, 1.0, 0.10, 0.10, 18, "strict"),
        RiskSpec("gate_strict_vt22_tr14_k12", 0.22, 1.0, 0.14, 0.12, 18, "strict"),
        RiskSpec("gate_adaptive_vt20_tr12_k12", 0.20, 1.0, 0.12, 0.12, 15, "adaptive"),
    ]


def make_gate(index: pd.Index, features: pd.DataFrame, scores: pd.DataFrame, spec: RiskSpec) -> pd.Series:
    f = features.reindex(index)
    s = scores.reindex(index)
    if spec.gate == "none":
        gate = pd.Series(True, index=index)
    elif spec.gate == "strict":
        gate = (
            (f["above_ma150"] > 0.5)
            & (f["above_ma200"] > 0.5)
            & (f["vix"] < 32)
            & (s["risk_off_score"] < 7)
        )
    elif spec.gate == "loose":
        gate = (
            (s["trend_score"] >= 1)
            | (s["bottom_score"] >= 4)
            | (f["ema3_120_ratio"] > -0.03)
        ) & (f["vix"] < 45)
    elif spec.gate == "adaptive":
        panic_bottom = (s["bottom_score"] >= 6) | (f["fear_proxy"] >= 0.78)
        trend_ok = (s["trend_score"] >= 2) & (f["vix"] < 35)
        gate = (trend_ok | panic_bottom) & (f["vix"] < 45)
    else:
        gate = ((s["trend_score"] >= 1) | (s["bottom_score"] >= 5)) & (f["vix"] < 38)
    return gate.fillna(False).astype(float)


def weighted_backtest(
    asset: pd.DataFrame,
    signal: pd.Series,
    features: pd.DataFrame,
    scores: pd.DataFrame,
    spec: RiskSpec,
    cost: float,
) -> dict[str, pd.Series]:
    index = asset.index
    open_price = asset["open"].astype(float).ffill()
    close = asset["close"].astype(float).ffill()
    raw = signal.reindex(index).ffill().fillna(0.0).clip(0, 1)
    gate = make_gate(index, features, scores, spec)
    vol = close.pct_change(fill_method=None).rolling(20).std() * math.sqrt(252)
    vol_scale = spec.vol_target / vol.replace(0, np.nan)
    desired = (raw * gate * vol_scale.clip(0, spec.max_weight)).fillna(0.0).clip(0, spec.max_weight)

    filtered = []
    held = False
    peak_price = np.nan
    cooldown = 0
    for dt, weight in desired.items():
        price = close.loc[dt]
        if cooldown > 0:
            cooldown -= 1
        if weight > 0.01 and cooldown == 0:
            if not held:
                held = True
                peak_price = price
            peak_price = max(peak_price, price)
            if price <= peak_price * (1 - spec.trail_stop):
                held = False
                peak_price = np.nan
                cooldown = spec.cooldown
                filtered.append(0.0)
                continue
            filtered.append(float(weight))
        else:
            held = False
            peak_price = np.nan
            filtered.append(0.0)
    desired = pd.Series(filtered, index=index, name="desired_weight")

    returns = []
    positions = []
    nav = 1.0
    peak_nav = 1.0
    kill_cooldown = 0
    prev_weight = 0.0
    prev_open = np.nan
    for dt, wanted in desired.items():
        opn = open_price.loc[dt]
        if pd.isna(prev_open) or prev_open <= 0:
            period_ret = 0.0
        else:
            period_ret = prev_weight * (opn / prev_open - 1.0)
        if kill_cooldown > 0:
            wanted = 0.0
            kill_cooldown -= 1
        trade = abs(float(wanted) - prev_weight)
        period_ret -= trade * cost
        nav *= max(0.0, 1.0 + period_ret)
        peak_nav = max(peak_nav, nav)
        if nav / peak_nav - 1.0 <= -spec.kill_dd:
            wanted = 0.0
            kill_cooldown = spec.cooldown
            # After a kill event, start a new risk budget from the current NAV.
            # Otherwise a cash portfolio can remain permanently below the old
            # peak and repeatedly re-trigger the kill switch without a chance
            # to recover.
            peak_nav = nav
        returns.append(period_ret)
        positions.append(float(wanted))
        prev_weight = float(wanted)
        prev_open = opn

    ret_s = pd.Series(returns, index=index, name="returns")
    pos_s = pd.Series(positions, index=index, name="position_weight")
    in_pos = pos_s > 0.01
    prev = in_pos.shift(1).fillna(False).astype(bool)
    entries = in_pos & ~prev
    exits = ~in_pos & prev
    return {
        "returns": ret_s,
        "position": pos_s,
        "value": (1.0 + ret_s.fillna(0.0)).cumprod(),
        "desired": desired,
        "entries": entries,
        "exits": exits,
    }


def metrics_from(result: Mapping[str, pd.Series], start: str | None = None, end: str | None = None) -> dict:
    ret = result["returns"].copy()
    pos = result["position"].copy()
    entries = result["entries"].copy()
    if start:
        mask = ret.index >= pd.Timestamp(start)
        ret, pos, entries = ret.loc[mask], pos.loc[mask], entries.loc[mask]
    if end:
        mask = ret.index <= pd.Timestamp(end)
        ret, pos, entries = ret.loc[mask], pos.loc[mask], entries.loc[mask]
    ret = ret.dropna()
    if ret.empty:
        return {
            "total_return": np.nan,
            "annual_return": np.nan,
            "sharpe": np.nan,
            "sortino": np.nan,
            "max_drawdown": np.nan,
            "calmar": np.nan,
            "exposure": np.nan,
            "avg_weight": np.nan,
            "trades": 0,
            "years": 0.0,
        }
    nav = (1.0 + ret.fillna(0.0)).cumprod()
    nav.iloc[0] = 1.0
    years = len(ret) / 252.0
    total = float(nav.iloc[-1] - 1.0)
    ann = (1 + total) ** (1 / years) - 1 if years > 0 and total > -1 else np.nan
    sd = float(ret.std(ddof=0))
    sharpe = float(ret.mean() / sd * math.sqrt(252)) if sd > 0 else np.nan
    downside = ret[ret < 0]
    sortino = float(ret.mean() / downside.std(ddof=0) * math.sqrt(252)) if len(downside) and downside.std(ddof=0) > 0 else np.nan
    dd = nav / nav.cummax() - 1.0
    max_dd = float(dd.min())
    calmar = float(ann / abs(max_dd)) if max_dd < 0 and not pd.isna(ann) else np.nan
    pos_aligned = pos.reindex(ret.index).fillna(0.0)
    return {
        "total_return": total,
        "annual_return": ann,
        "sharpe": sharpe,
        "sortino": sortino,
        "max_drawdown": max_dd,
        "calmar": calmar,
        "exposure": float((pos_aligned > 0.01).mean()),
        "avg_weight": float(pos_aligned.mean()),
        "trades": int(entries.reindex(ret.index).fillna(False).sum()),
        "years": years,
    }


def buy_hold_metrics(asset: pd.DataFrame, start: str | None = None, end: str | None = None) -> dict:
    price = asset["open"].astype(float).ffill()
    ret = price.pct_change(fill_method=None).fillna(0.0)
    result = {
        "returns": ret,
        "position": pd.Series(1.0, index=asset.index),
        "entries": pd.Series(False, index=asset.index),
    }
    return metrics_from(result, start, end)


def cycle_metrics(result: Mapping[str, pd.Series]) -> dict:
    out = {}
    annuals = []
    calmars = []
    pass_count = 0
    cycle_count = 0
    for name, start, end in FOLDS:
        m = metrics_from(result, start, end)
        for key in ("annual_return", "max_drawdown", "sharpe", "calmar"):
            out[f"cycle_{name}_{key}"] = m[key]
        if not pd.isna(m["annual_return"]) and m["years"] >= 0.75:
            annuals.append(m["annual_return"])
            if not pd.isna(m["calmar"]):
                calmars.append(m["calmar"])
            cycle_count += 1
            if m["annual_return"] > 0 and m["max_drawdown"] > -0.28:
                pass_count += 1
    out["cycle_positive_rate"] = pass_count / cycle_count if cycle_count else np.nan
    out["cycle_median_annual"] = float(np.nanmedian(annuals)) if annuals else np.nan
    out["cycle_median_calmar"] = float(np.nanmedian(calmars)) if calmars else np.nan
    return out


def event_capture_metrics(events: pd.DataFrame, result: Mapping[str, pd.Series], window_before: int = 3, window_after: int = 7) -> dict:
    if events.empty:
        return {"bottom_capture": np.nan, "top_capture": np.nan, "entry_precision": np.nan, "exit_precision": np.nan}
    entries = result["entries"][result["entries"].fillna(False)].index
    exits = result["exits"][result["exits"].fillna(False)].index
    index = result["returns"].index

    def around(dt: pd.Timestamp) -> pd.Index:
        if dt not in index:
            loc = index.searchsorted(dt)
        else:
            loc = index.get_loc(dt)
        start = max(0, int(loc) - window_before)
        end = min(len(index), int(loc) + window_after + 1)
        return index[start:end]

    bottom_events = events[events["event_type"] == "bottom"]
    top_events = events[events["event_type"] == "top"]
    bottom_windows = [set(around(pd.Timestamp(ev))) for ev in bottom_events["event_date"]]
    top_windows = [set(around(pd.Timestamp(ev))) for ev in top_events["event_date"]]
    bottom_union = set().union(*bottom_windows) if bottom_windows else set()
    top_union = set().union(*top_windows) if top_windows else set()
    bottom_hits = 0
    top_hits = 0
    entry_set = set(entries)
    exit_set = set(exits)
    for win in bottom_windows:
        if entry_set.intersection(win):
            bottom_hits += 1
    for win in top_windows:
        if exit_set.intersection(win):
            top_hits += 1

    entry_good = 0
    for dt in entries:
        if dt in bottom_union:
            entry_good += 1
    exit_good = 0
    for dt in exits:
        if dt in top_union:
            exit_good += 1
    return {
        "bottom_capture": bottom_hits / len(bottom_events) if len(bottom_events) else np.nan,
        "top_capture": top_hits / len(top_events) if len(top_events) else np.nan,
        "entry_precision": entry_good / len(entries) if len(entries) else np.nan,
        "exit_precision": exit_good / len(exits) if len(exits) else np.nan,
        "bottom_event_count": int(len(bottom_events)),
        "top_event_count": int(len(top_events)),
    }


def score_row(row: Mapping[str, float], target: str) -> float:
    required = ("wf_annual_return", "wf_sharpe", "wf_calmar", "wf_max_drawdown", "test_annual_return", "test_calmar")
    if any(pd.isna(row.get(k, np.nan)) for k in required):
        return -999.0
    dd_soft = -0.18 if target == "QLD" else -0.22
    dd_hard = -0.26 if target == "QLD" else -0.30
    score = (
        0.25 * float(np.clip(row["wf_calmar"], -2, 4))
        + 0.18 * float(np.clip(row["test_calmar"], -2, 4))
        + 0.15 * float(np.clip(row["wf_sharpe"], -2, 3))
        + 0.12 * float(np.clip(row["test_sharpe"], -2, 3))
        + 0.12 * float(np.clip(row["wf_annual_return"], -0.5, 0.8))
        + 0.08 * float(np.clip(row.get("cycle_median_calmar", 0), -2, 4))
        + 0.05 * float(np.nan_to_num(row.get("bottom_capture", 0.0)))
        + 0.05 * float(np.nan_to_num(row.get("top_capture", 0.0)))
    )
    wf_dd = float(row.get("wf_max_drawdown", 0.0))
    test_dd = float(row.get("test_max_drawdown", 0.0))
    if wf_dd < dd_soft:
        score -= 2.5 * (abs(wf_dd) - abs(dd_soft))
    if test_dd < dd_soft:
        score -= 2.0 * (abs(test_dd) - abs(dd_soft))
    if wf_dd < dd_hard:
        score -= 4.0 * (abs(wf_dd) - abs(dd_hard))
    if row.get("wf_exposure", 0.0) < 0.12:
        score -= 0.25
    if row.get("wf_trades", 0.0) < 3:
        score -= 0.35
    if row.get("cycle_positive_rate", 0.0) < 0.50:
        score -= 0.35
    return float(score)


def next_action(asset: pd.DataFrame, result: Mapping[str, pd.Series], next_open_date: str) -> dict:
    latest = asset.index.max()
    weight = float(result["position"].reindex(asset.index).ffill().fillna(0.0).iloc[-1])
    desired = float(result["desired"].reindex(asset.index).ffill().fillna(0.0).iloc[-1])
    prev_weight = float(result["position"].reindex(asset.index).ffill().fillna(0.0).iloc[-2]) if len(asset) > 1 else 0.0
    if weight > 0.01 and prev_weight <= 0.01:
        action = "BUY_OR_INCREASE"
    elif weight <= 0.01 and prev_weight > 0.01:
        action = "SELL_OR_EMPTY"
    elif weight > 0.01:
        action = "HOLD_OR_KEEP_LONG"
    else:
        action = "WAIT_OR_STAY_CASH"
    return {
        "latest_signal_date": latest.strftime("%Y-%m-%d"),
        "next_open_date": next_open_date,
        "latest_open": float(asset["open"].iloc[-1]),
        "latest_close": float(asset["close"].iloc[-1]),
        "desired_weight_after_close": desired,
        "position_weight_at_latest_open": weight,
        "action": action,
    }


def operations(target: str, asset: pd.DataFrame, result: Mapping[str, pd.Series], strategy: str) -> pd.DataFrame:
    rows = []
    for dt in asset.index:
        if bool(result["entries"].get(dt, False)):
            rows.append(
                {
                    "target": target,
                    "strategy": strategy,
                    "date": dt.strftime("%Y-%m-%d"),
                    "action": "BUY_OPEN",
                    "open": float(asset.loc[dt, "open"]),
                    "close": float(asset.loc[dt, "close"]),
                    "position_weight_after_open": float(result["position"].loc[dt]),
                }
            )
        if bool(result["exits"].get(dt, False)):
            rows.append(
                {
                    "target": target,
                    "strategy": strategy,
                    "date": dt.strftime("%Y-%m-%d"),
                    "action": "SELL_OPEN",
                    "open": float(asset.loc[dt, "open"]),
                    "close": float(asset.loc[dt, "close"]),
                    "position_weight_after_open": float(result["position"].loc[dt]),
                }
            )
    return pd.DataFrame(rows)


def trades_from_ops(ops: pd.DataFrame) -> pd.DataFrame:
    if ops.empty:
        return pd.DataFrame()
    rows = []
    entry = None
    for row in ops.to_dict("records"):
        if row["action"] == "BUY_OPEN":
            entry = row
        elif row["action"] == "SELL_OPEN" and entry is not None:
            rows.append(
                {
                    "entry_date": entry["date"],
                    "entry_open": entry["open"],
                    "exit_date": row["date"],
                    "exit_open": row["open"],
                    "trade_return": row["open"] / entry["open"] - 1.0,
                    "holding_days": (pd.Timestamp(row["date"]) - pd.Timestamp(entry["date"])).days,
                }
            )
            entry = None
    if entry is not None:
        rows.append(
            {
                "entry_date": entry["date"],
                "entry_open": entry["open"],
                "exit_date": "",
                "exit_open": np.nan,
                "trade_return": np.nan,
                "holding_days": (pd.Timestamp(datetime.now().date()) - pd.Timestamp(entry["date"])).days,
            }
        )
    return pd.DataFrame(rows)


def classify_missed_event(row: Mapping[str, float]) -> str:
    event_type = row["event_type"]
    if event_type == "bottom":
        if row.get("vix_pct252", np.nan) < 0.60 and row.get("drawdown20", 0.0) > -0.05:
            return "浅回调且VIX未恐慌，传统底部信号弱"
        if row.get("td9_buy", 0.0) < 5 and row.get("rsi14", 50.0) > 35:
            return "TD9/RSI未形成充分超卖"
        if row.get("trend_score", 0.0) <= 1 and row.get("breadth_proxy", 1.0) < 0.40:
            return "熊市/弱广度压制，风控门没有放行"
        if abs(row.get("next1_ret", 0.0)) >= 0.03:
            return "消息或跳空式V形反转，日频信号滞后"
        return "多信号冲突或阈值未达到"
    if row.get("td9_sell", 0.0) < 5 and row.get("rsi14", 50.0) < 68:
        return "强趋势中的突发回落，顶部耗竭信号不明显"
    if row.get("greed_proxy", 0.0) < 0.60 and row.get("valuation_proxy", 0.0) < 0.70:
        return "贪婪/估值代理不极端，顶部信号弱"
    if row.get("trend_score", 0.0) >= 4 and row.get("breadth_proxy", 0.0) >= 0.60:
        return "强趋势延伸顶部，过早退出会损失主升段"
    return "多信号冲突或顶部阈值未达到"


def event_diagnostics(
    events: pd.DataFrame,
    asset: pd.DataFrame,
    features: pd.DataFrame,
    scores: pd.DataFrame,
    probs: pd.DataFrame,
    result: Mapping[str, pd.Series],
) -> pd.DataFrame:
    if events.empty:
        return pd.DataFrame()
    index = asset.index
    entries = result["entries"][result["entries"].fillna(False)].index
    exits = result["exits"][result["exits"].fillna(False)].index
    rows = []
    for event in events.to_dict("records"):
        dt = pd.Timestamp(event["event_date"])
        loc = index.searchsorted(dt)
        if loc >= len(index):
            continue
        win = index[max(0, loc - 3) : min(len(index), loc + 8)]
        hit_dates = entries.intersection(win) if event["event_type"] == "bottom" else exits.intersection(win)
        captured = len(hit_dates) > 0
        row = {
            "event_type": event["event_type"],
            "event_date": dt.strftime("%Y-%m-%d"),
            "target_close": float(asset["close"].reindex(index).iloc[loc]),
            "captured": captured,
            "capture_date": hit_dates[0].strftime("%Y-%m-%d") if captured else "",
            "bottom_prob": float(probs["bottom_prob"].reindex(index).iloc[loc]) if "bottom_prob" in probs else np.nan,
            "top_prob": float(probs["top_prob"].reindex(index).iloc[loc]) if "top_prob" in probs else np.nan,
            "bottom_score": float(scores["bottom_score"].reindex(index).iloc[loc]),
            "top_score": float(scores["top_score"].reindex(index).iloc[loc]),
            "trend_score": float(scores["trend_score"].reindex(index).iloc[loc]),
            "next1_ret": float(asset["close"].pct_change().shift(-1).reindex(index).iloc[loc]),
        }
        for col in ("td9_buy", "td9_sell", "rsi14", "vix_pct252", "drawdown20", "breadth_proxy", "fear_proxy", "greed_proxy", "valuation_proxy"):
            if col in features:
                row[col] = float(features[col].reindex(index).iloc[loc])
        row["miss_reason"] = "" if captured else classify_missed_event(row)
        rows.append(row)
    return pd.DataFrame(rows)


def evaluate_target(
    target: str,
    data: Mapping[str, pd.DataFrame],
    features: pd.DataFrame,
    scores: pd.DataFrame,
    probs: pd.DataFrame,
    events: pd.DataFrame,
    run_dir: Path,
    test_start: str,
    next_open_date: str,
    cost: float,
) -> dict:
    asset = data[target].copy()
    index = asset.index.intersection(features.index)
    asset = asset.reindex(index).dropna(subset=["open", "close"])
    index = asset.index
    target_features = features.reindex(index).ffill()
    target_scores = scores.reindex(index).ffill()
    target_probs = probs.reindex(index).ffill().fillna(0.0)
    candidates = build_candidates(index, target_features, target_scores, target_probs)
    specs = risk_specs(target)
    checkpoint(
        run_dir,
        f"03_candidates_{target}",
        f"{target} turning-point candidate checkpoint",
        {
            "target": target,
            "raw_candidate_count": len(candidates),
            "risk_specs": [s.name for s in specs],
            "estimated_backtests": len(candidates) * len(specs),
        },
        "Backtest candidate/risk-spec combinations and rank by walk-forward robustness.",
    )

    rows = []
    results: dict[str, dict[str, pd.Series]] = {}
    for candidate in candidates:
        for spec in specs:
            strategy_id = f"{candidate.name}__{spec.name}"
            try:
                result = weighted_backtest(asset, candidate.signal, target_features, target_scores, spec, cost)
                wf = metrics_from(result, WF_START, None)
                test = metrics_from(result, test_start, None)
                full = metrics_from(result, None, None)
                cycles = cycle_metrics(result)
                capture = event_capture_metrics(events, result)
                bh = buy_hold_metrics(asset, WF_START, None)
                row = {
                    "target": target,
                    "strategy": candidate.name,
                    "family": candidate.family,
                    "risk_spec": spec.name,
                    "notes": candidate.notes,
                    "error": "",
                    "latest_date": asset.index.max().strftime("%Y-%m-%d"),
                    "buy_hold_wf_annual_return": bh["annual_return"],
                    "buy_hold_wf_max_drawdown": bh["max_drawdown"],
                    "wf_annual_excess_vs_buy_hold": wf["annual_return"] - bh["annual_return"] if not pd.isna(wf["annual_return"]) else np.nan,
                }
                for prefix, metric in (("wf", wf), ("test", test), ("full", full)):
                    for key, value in metric.items():
                        row[f"{prefix}_{key}"] = value
                row.update(cycles)
                row.update(capture)
                row["score"] = score_row(row, target)
                results[strategy_id] = result
            except Exception as exc:
                row = {
                    "target": target,
                    "strategy": candidate.name,
                    "family": candidate.family,
                    "risk_spec": spec.name,
                    "notes": candidate.notes,
                    "error": f"{type(exc).__name__}: {exc}",
                "score": -999.0,
                }
            rows.append(row)
            if len(rows) % 100 == 0:
                pd.DataFrame(rows).sort_values("score", ascending=False).to_csv(
                    run_dir / f"{target}_partial_rank.csv",
                    index=False,
                    encoding="utf-8-sig",
                )
    rank = pd.DataFrame(rows).sort_values("score", ascending=False)
    rank.to_csv(run_dir / f"{target}_strategy_rank.csv", index=False, encoding="utf-8-sig")
    rank.head(50).to_csv(run_dir / f"{target}_top50.csv", index=False, encoding="utf-8-sig")
    best = rank.iloc[0].to_dict()
    best_id = f"{best['strategy']}__{best['risk_spec']}"
    result = results[best_id]
    ops = operations(target, asset, result, best["strategy"])
    trades = trades_from_ops(ops)
    nav = pd.DataFrame(
        {
            "open": asset["open"],
            "close": asset["close"],
            "desired_weight_after_close": result["desired"],
            "position_weight_at_open": result["position"],
            "entry_at_open": result["entries"].astype(int),
            "exit_at_open": result["exits"].astype(int),
            "portfolio_value": result["value"],
            "portfolio_return": result["returns"],
            "bottom_prob": target_probs["bottom_prob"],
            "top_prob": target_probs["top_prob"],
            "bottom_score": target_scores["bottom_score"],
            "top_score": target_scores["top_score"],
            "trend_score": target_scores["trend_score"],
        }
    )
    diagnostics = event_diagnostics(events, asset, target_features, target_scores, target_probs, result)
    reason_summary = (
        diagnostics[~diagnostics["captured"]].groupby(["event_type", "miss_reason"]).size().reset_index(name="count").sort_values(["event_type", "count"], ascending=[True, False])
        if not diagnostics.empty
        else pd.DataFrame()
    )
    ops.to_csv(run_dir / f"{target}_best_operations.csv", index=False, encoding="utf-8-sig")
    trades.to_csv(run_dir / f"{target}_best_trades.csv", index=False, encoding="utf-8-sig")
    nav.to_csv(run_dir / f"{target}_best_signal_nav.csv", encoding="utf-8-sig")
    diagnostics.to_csv(run_dir / f"{target}_turning_event_diagnostics.csv", index=False, encoding="utf-8-sig")
    reason_summary.to_csv(run_dir / f"{target}_miss_reason_summary.csv", index=False, encoding="utf-8-sig")
    action = next_action(asset, result, next_open_date)
    checkpoint(
        run_dir,
        f"04_best_{target}",
        f"{target} best turning-point strategy checkpoint",
        {
            "best": best,
            "next_action": action,
            "operations_file": str(run_dir / f"{target}_best_operations.csv"),
            "event_diagnostics_file": str(run_dir / f"{target}_turning_event_diagnostics.csv"),
        },
        "Write the final QLD/TQQQ turning-point report.",
    )
    return {
        "target": target,
        "rank": rank,
        "best": best,
        "result": result,
        "operations": ops,
        "trades": trades,
        "nav": nav,
        "diagnostics": diagnostics,
        "reason_summary": reason_summary,
        "next_action": action,
    }


def format_summary_rows(summaries: Iterable[dict]) -> pd.DataFrame:
    rows = []
    for item in summaries:
        b = item["best"]
        a = item["next_action"]
        rows.append(
            {
                "target": item["target"],
                "strategy": b["strategy"],
                "family": b["family"],
                "risk_spec": b["risk_spec"],
                "score": round(float(b["score"]), 4),
                "wf_annual_return": pct(b["wf_annual_return"]),
                "wf_max_drawdown": pct(b["wf_max_drawdown"]),
                "wf_sharpe": round(float(b["wf_sharpe"]), 3),
                "wf_calmar": round(float(b["wf_calmar"]), 3),
                "test_annual_return": pct(b["test_annual_return"]),
                "test_max_drawdown": pct(b["test_max_drawdown"]),
                "test_calmar": round(float(b["test_calmar"]), 3),
                "wf_exposure": pct(b["wf_exposure"]),
                "wf_avg_weight": pct(b["wf_avg_weight"]),
                "wf_trades": int(b["wf_trades"]),
                "bottom_capture": pct(b.get("bottom_capture")),
                "top_capture": pct(b.get("top_capture")),
                "buy_hold_wf_annual_return": pct(b.get("buy_hold_wf_annual_return")),
                "buy_hold_wf_max_drawdown": pct(b.get("buy_hold_wf_max_drawdown")),
                "wf_annual_excess_vs_buy_hold": pct(b.get("wf_annual_excess_vs_buy_hold")),
                "latest_action": a["action"],
                "latest_weight": f"{a['position_weight_at_latest_open']:.3f}",
            }
        )
    return pd.DataFrame(rows)


def write_report(
    run_dir: Path,
    summaries: list[dict],
    status: pd.DataFrame,
    feature_meta: Mapping[str, object],
    folds: pd.DataFrame,
    labels: pd.DataFrame,
    events: pd.DataFrame,
    test_start: str,
    next_open_date: str,
    cost: float,
) -> None:
    combined = format_summary_rows(summaries)
    combined.to_csv(run_dir / "best_strategy_summary.csv", index=False, encoding="utf-8-sig")
    events.to_csv(run_dir / "turning_events.csv", index=False, encoding="utf-8-sig")
    labels.to_csv(run_dir / "turning_labels.csv", encoding="utf-8-sig")

    lines = [
        "# QLD/TQQQ Turning-Point Strategy Report",
        "",
        f"- Run directory: `{run_dir}`",
        f"- Walk-forward OOS starts: `{WF_START}`",
        f"- Test period starts: `{test_start}`",
        f"- Execution: signal after close, target weight at next open.",
        f"- Cost model: one-way `{cost:.2%}` including fee/slippage assumption.",
        f"- Next open date requested: `{next_open_date}`",
        f"- vectorbt version available: `{vbt.__version__}`",
        "",
        "## Method",
        "",
        "- Base labels use QQQ because QLD/TQQQ are leveraged Nasdaq-100 wrappers; bottoms mean a pullback with strong 20-day forward rebound, tops mean a run-up with meaningful 20-day forward drawdown.",
        "- Signals include TD9/神奇九转, VIX percentile/spike, Bollinger %B, RSI, trend distance, market breadth proxy, fear/greed proxy, and PE/valuation proxy.",
        "- ML uses expanding walk-forward folds. Each fold trains only on data before the test fold and predicts bottom/top probabilities for the next cycle.",
        "- Final strategies are not a single magic rule: they combine rebound sleeves, trend backbone sleeves, ML top exits, volatility sizing, trailing stops, and drawdown kill switches.",
        "",
        "## Data Status",
        "",
        md_table(status[["symbol", "status", "local_last", "online_last", "merged_last", "rows", "error"]]),
        "",
        "## Optional Macro/Emotion Data",
        "",
        "```json",
        json.dumps(jready(feature_meta), ensure_ascii=False, indent=2),
        "```",
        "",
        "## Walk-Forward Model Diagnostics",
        "",
        md_table(folds),
        "",
        "## Best Strategy Summary",
        "",
        md_table(combined),
    ]

    for item in summaries:
        b = item["best"]
        a = item["next_action"]
        lines.extend(
            [
                "",
                f"## {item['target']} Details",
                "",
                f"- Best strategy: `{b['strategy']}`",
                f"- Family: `{b['family']}`",
                f"- Risk spec: `{b['risk_spec']}`",
                f"- Rule: {b['notes']}",
                f"- Walk-forward annual/maxDD/sharpe/calmar: {pct(b['wf_annual_return'])} / {pct(b['wf_max_drawdown'])} / {b['wf_sharpe']:.3f} / {b['wf_calmar']:.3f}",
                f"- Test annual/maxDD/sharpe/calmar: {pct(b['test_annual_return'])} / {pct(b['test_max_drawdown'])} / {b['test_sharpe']:.3f} / {b['test_calmar']:.3f}",
                f"- Full annual/maxDD/sharpe/calmar: {pct(b['full_annual_return'])} / {pct(b['full_max_drawdown'])} / {b['full_sharpe']:.3f} / {b['full_calmar']:.3f}",
                f"- Exposure/avg weight/trades: {pct(b['wf_exposure'])} / {pct(b['wf_avg_weight'])} / {int(b['wf_trades'])}",
                f"- Turning capture bottom/top: {pct(b.get('bottom_capture'))} / {pct(b.get('top_capture'))}",
                f"- Buy-hold WF annual/maxDD: {pct(b.get('buy_hold_wf_annual_return'))} / {pct(b.get('buy_hold_wf_max_drawdown'))}; annual excess: {pct(b.get('wf_annual_excess_vs_buy_hold'))}",
                f"- Latest action: `{a['action']}`, latest weight `{a['position_weight_at_latest_open']:.3f}`, desired after close `{a['desired_weight_after_close']:.3f}`, latest signal date `{a['latest_signal_date']}`.",
                "",
                "Recent operations:",
                "",
                md_table(item["operations"].tail(20)) if not item["operations"].empty else "_No operations._",
                "",
                "Missed turning-point reasons:",
                "",
                md_table(item["reason_summary"]) if not item["reason_summary"].empty else "_No missed-event summary._",
            ]
        )

    lines.extend(
        [
            "",
            "## Output Files",
            "",
            "- `best_strategy_summary.csv`: best strategy per target.",
            "- `QLD_strategy_rank.csv`, `TQQQ_strategy_rank.csv`: full candidate rankings.",
            "- `QLD_best_signal_nav.csv`, `TQQQ_best_signal_nav.csv`: daily signal, weight, NAV, and probabilities.",
            "- `QLD_turning_event_diagnostics.csv`, `TQQQ_turning_event_diagnostics.csv`: captured/missed top-bottom event diagnostics.",
            "- `QLD_miss_reason_summary.csv`, `TQQQ_miss_reason_summary.csv`: grouped missed-event reasons.",
            "",
            "## Limitations",
            "",
            "- This is research only, not investment advice.",
            "- The method reduces data snooping with walk-forward predictions, but final strategy selection is still based on historical research.",
            "- CNN fear/greed and S&P PE are optional web sources; if unavailable, the script falls back to price-derived proxies.",
            "- QLD/TQQQ are daily-reset leveraged ETFs; realized performance can diverge sharply from unlevered QQQ during volatile sideways markets.",
        ]
    )
    (run_dir / "report.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    write_json(
        run_dir / "best_config.json",
        {
            "run_dir": str(run_dir),
            "wf_start": WF_START,
            "test_start": test_start,
            "next_open_date": next_open_date,
            "cost": cost,
            "best": combined.to_dict("records"),
            "feature_meta": feature_meta,
        },
    )
    checkpoint(
        run_dir,
        "05_final_report",
        "QLD/TQQQ turning-point final report checkpoint",
        {
            "report": str(run_dir / "report.md"),
            "best_config": str(run_dir / "best_config.json"),
            "best_summary": combined.to_dict("records"),
        },
        "Review report, ranks, signal NAV files, and missed turning-point diagnostics.",
    )


def prepare_data(run_dir: Path, today: str) -> tuple[dict[str, pd.DataFrame], pd.DataFrame, pd.Timestamp]:
    data, status, _ = base.full_mod.update_us_data(run_dir, today=today, context_symbols=CONTEXT)
    usable = {k: v for k, v in data.items() if v is not None and not v.empty}
    missing = [symbol for symbol in ESSENTIAL if symbol not in usable]
    if missing:
        raise RuntimeError(f"Missing essential data: {missing}")
    latest = min(usable[symbol].index.max() for symbol in ESSENTIAL)
    for key in list(usable):
        usable[key] = usable[key].loc[usable[key].index <= latest].copy()
    status["used_latest_cutoff"] = latest.strftime("%Y-%m-%d")
    status.to_csv(run_dir / "latest_data_status.csv", index=False, encoding="utf-8-sig")
    return usable, status, latest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--today", default="2026-04-21", help="Exclusive data end date for online download; yfinance convention.")
    parser.add_argument("--test-start", default="2021-01-01")
    parser.add_argument("--next-open-date", default="2026-04-20")
    parser.add_argument("--cost", type=float, default=0.002, help="One-way fee/slippage cost.")
    args = parser.parse_args()

    run_dir = OUT_ROOT / f"qldtqqq_turning_{stamp()}"
    run_dir.mkdir(parents=True, exist_ok=True)
    checkpoint(
        run_dir,
        "00_start",
        "QLD/TQQQ turning-point start checkpoint",
        {
            "targets": TARGETS,
            "context": CONTEXT,
            "today": args.today,
            "test_start": args.test_start,
            "cost": args.cost,
            "method": "TD9/VIX/Bollinger/RSI/breadth/fear-greed/valuation + walk-forward ML + multi-sleeve risk-managed backtest",
        },
        "Refresh market data and build turning-point labels.",
    )
    data, status, latest = prepare_data(run_dir, args.today)
    index = data["QQQ"].index
    labels, events = label_turning_points(data["QQQ"])
    labels.to_csv(run_dir / "turning_labels.csv", encoding="utf-8-sig")
    events.to_csv(run_dir / "turning_events.csv", index=False, encoding="utf-8-sig")
    checkpoint(
        run_dir,
        "01_labels",
        "Turning-point label checkpoint",
        {
            "latest_data_cutoff": latest.strftime("%Y-%m-%d"),
            "label_rows": int(len(labels)),
            "bottom_events": int((events["event_type"] == "bottom").sum()) if not events.empty else 0,
            "top_events": int((events["event_type"] == "top").sum()) if not events.empty else 0,
        },
        "Build features and walk-forward ML probabilities.",
    )
    features, scores, feature_meta = build_feature_frame(data, index, run_dir)
    features.to_csv(run_dir / "feature_frame.csv", encoding="utf-8-sig")
    scores.to_csv(run_dir / "turning_scores.csv", encoding="utf-8-sig")
    cols = feature_columns(features)
    probs, folds = walk_forward_probabilities(features, labels, cols, run_dir)
    checkpoint(
        run_dir,
        "02_features_models",
        "Feature and ML checkpoint",
        {
            "feature_count": int(len(cols)),
            "feature_columns": cols,
            "folds": folds.to_dict("records"),
            "feature_meta": feature_meta,
        },
        "Evaluate QLD and TQQQ turning-point strategy combinations.",
    )
    summaries = [
        evaluate_target(target, data, features, scores, probs, events, run_dir, args.test_start, args.next_open_date, args.cost)
        for target in TARGETS
    ]
    write_report(run_dir, summaries, status, feature_meta, folds, labels, events, args.test_start, args.next_open_date, args.cost)
    print(run_dir)


if __name__ == "__main__":
    main()
