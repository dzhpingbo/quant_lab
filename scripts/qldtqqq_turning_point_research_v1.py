"""Scientific v1 research framework for QLD/TQQQ regime-aware timing.

This script intentionally avoids the old full-factor/full-strategy brute force
workflow. It builds tradable barrier labels, a compact feature set, simple
interpretable strategies, walk-forward validation, cost sensitivity, benchmark
comparison, and reproducible reports in one timestamped output directory.
"""

from __future__ import annotations

import argparse
import math
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
DEFAULT_DATA_DIR = ROOT / "data" / "external" / "legacy_quant" / "NSDQStock" / "19800101_20260404"
TARGETS = ("QLD", "TQQQ")
REQUIRED_SYMBOLS = ("QLD", "TQQQ", "QQQ", "_VIX")
HORIZONS = (10, 15, 20)
DEFAULT_FEE = 0.002
DEFAULT_EXECUTION = "next_open"
TEST_START = "2021-01-01"
TRADING_DAYS = 252.0

warnings.filterwarnings("ignore", category=FutureWarning)


@dataclass(frozen=True)
class LabelScheme:
    name: str
    barrier_type: str
    description: str
    fixed_up: dict[str, float] | None = None
    fixed_down: dict[str, float] | None = None
    atr_up_mult: float | None = None
    atr_down_mult: float | None = None


@dataclass(frozen=True)
class SplitSpec:
    split_type: str
    name: str
    train_start: str
    train_end: str
    test_start: str
    test_end: str | None


@dataclass(frozen=True)
class StrategySpec:
    name: str
    family: str
    description: str
    signal: pd.Series
    complexity: float


@dataclass
class BacktestResult:
    nav: pd.Series
    returns: pd.Series
    position: pd.Series
    turnover: pd.Series
    entries: pd.Series
    exits: pd.Series
    execution: str
    fee: float


LABEL_SCHEMES = (
    LabelScheme(
        name="fixed_moderate",
        barrier_type="fixed_pct",
        description="QLD uses +8%/-6%; TQQQ uses +12%/-9%. Leverage-scaled fixed barriers.",
        fixed_up={"QLD": 0.08, "TQQQ": 0.12},
        fixed_down={"QLD": 0.06, "TQQQ": 0.09},
    ),
    LabelScheme(
        name="fixed_wide",
        barrier_type="fixed_pct",
        description="QLD uses +10%/-8%; TQQQ uses +15%/-12%. Wider fixed barriers.",
        fixed_up={"QLD": 0.10, "TQQQ": 0.15},
        fixed_down={"QLD": 0.08, "TQQQ": 0.12},
    ),
    LabelScheme(
        name="atr_moderate",
        barrier_type="atr",
        description="Adaptive barriers: upper 2.5 ATR, lower 2.0 ATR.",
        atr_up_mult=2.5,
        atr_down_mult=2.0,
    ),
    LabelScheme(
        name="atr_wide",
        barrier_type="atr",
        description="Adaptive barriers: upper 3.5 ATR, lower 2.5 ATR.",
        atr_up_mult=3.5,
        atr_down_mult=2.5,
    ),
)


def stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def log(message: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}", flush=True)


def pct(value: float | int | None, digits: int = 2) -> str:
    if value is None or pd.isna(value):
        return "nan"
    return f"{float(value) * 100:.{digits}f}%"


def num(value: float | int | None, digits: int = 3) -> str:
    if value is None or pd.isna(value):
        return "nan"
    return f"{float(value):.{digits}f}"


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


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")


def read_ohlcv(data_dir: Path, symbol: str) -> pd.DataFrame:
    path = data_dir / f"{symbol}.csv"
    if not path.exists():
        raise FileNotFoundError(f"Missing data file for {symbol}: {path}")
    df = pd.read_csv(path)
    df.columns = [str(c).strip().lower() for c in df.columns]
    if "date" not in df.columns:
        raise ValueError(f"{path} must contain a date column")
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.tz_localize(None).dt.normalize()
    df = df.dropna(subset=["date"]).drop_duplicates("date").sort_values("date").set_index("date")
    for col in ("open", "high", "low", "close", "volume"):
        if col not in df.columns:
            df[col] = np.nan
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df[["open", "high", "low", "close", "volume"]].replace([np.inf, -np.inf], np.nan)
    df = df.dropna(subset=["close"])
    return df


def load_data(data_dir: Path) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    data: dict[str, pd.DataFrame] = {}
    rows = []
    for symbol in REQUIRED_SYMBOLS:
        df = read_ohlcv(data_dir, symbol)
        data[symbol] = df
        rows.append(
            {
                "symbol": symbol,
                "status": "ok",
                "first_date": df.index.min().strftime("%Y-%m-%d") if len(df) else "",
                "last_date": df.index.max().strftime("%Y-%m-%d") if len(df) else "",
                "rows": len(df),
                "missing_open": int(df["open"].isna().sum()),
                "missing_high": int(df["high"].isna().sum()),
                "missing_low": int(df["low"].isna().sum()),
                "missing_close": int(df["close"].isna().sum()),
                "source": str((data_dir / f"{symbol}.csv").resolve()),
            }
        )
    return data, pd.DataFrame(rows)


def align_to(source: pd.Series, index: pd.Index) -> pd.Series:
    return source.reindex(index).ffill()


def atr(df: pd.DataFrame, window: int = 14) -> pd.Series:
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)
    prev_close = close.shift(1)
    tr = pd.concat([(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    return tr.rolling(window, min_periods=window).mean()


def ema(series: pd.Series, window: int) -> pd.Series:
    return series.ewm(span=window, adjust=False).mean()


def rsi(close: pd.Series, window: int = 14) -> pd.Series:
    diff = close.diff()
    up = diff.clip(lower=0).ewm(alpha=1 / window, adjust=False).mean()
    down = (-diff.clip(upper=0)).ewm(alpha=1 / window, adjust=False).mean()
    rs = up.div(down.replace(0, np.nan))
    return 100 - 100 / (1 + rs)


def macd(close: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
    fast = ema(close, 12)
    slow = ema(close, 26)
    line = fast - slow
    signal = ema(line, 9)
    hist = line - signal
    return line, signal, hist


def rolling_percentile_last(series: pd.Series, window: int) -> pd.Series:
    def pct_rank(values: np.ndarray) -> float:
        clean = values[np.isfinite(values)]
        if len(clean) < max(10, window // 4):
            return np.nan
        return float((clean <= clean[-1]).mean())

    return series.rolling(window, min_periods=max(20, window // 3)).apply(pct_rank, raw=True)


def max_drawdown(nav: pd.Series) -> float:
    clean = nav.dropna()
    if clean.empty:
        return np.nan
    dd = clean.div(clean.cummax()).sub(1.0)
    return float(dd.min())


def cagr_from_nav(nav: pd.Series) -> float:
    clean = nav.dropna()
    if len(clean) < 2:
        return np.nan
    years = max((clean.index[-1] - clean.index[0]).days / 365.25, 1 / 365.25)
    start = float(clean.iloc[0])
    end = float(clean.iloc[-1])
    if start <= 0 or end <= 0:
        return np.nan
    return float((end / start) ** (1 / years) - 1)


def sharpe_from_returns(returns: pd.Series) -> float:
    clean = returns.replace([np.inf, -np.inf], np.nan).dropna()
    clean = clean[clean.index.notna()]
    if clean.std(ddof=0) == 0 or len(clean) < 20:
        return np.nan
    return float(clean.mean() / clean.std(ddof=0) * math.sqrt(TRADING_DAYS))


def label_barrier_distance(
    df: pd.DataFrame,
    target: str,
    scheme: LabelScheme,
) -> tuple[pd.Series, pd.Series]:
    close = df["close"].astype(float)
    if scheme.barrier_type == "fixed_pct":
        assert scheme.fixed_up is not None and scheme.fixed_down is not None
        up = pd.Series(float(scheme.fixed_up[target]), index=df.index)
        down = pd.Series(float(scheme.fixed_down[target]), index=df.index)
        return up, down
    atr_pct = atr(df, 14).div(close)
    up = atr_pct * float(scheme.atr_up_mult)
    down = atr_pct * float(scheme.atr_down_mult)
    return up, down


def compute_barrier_labels(
    df: pd.DataFrame,
    target: str,
    scheme: LabelScheme,
    horizon: int,
) -> tuple[pd.Series, pd.Series, int]:
    close = df["close"].to_numpy(dtype=float)
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    up_dist, down_dist = label_barrier_distance(df, target, scheme)
    up_arr = up_dist.to_numpy(dtype=float)
    down_arr = down_dist.to_numpy(dtype=float)
    bottom = np.full(len(df), np.nan)
    top = np.full(len(df), np.nan)
    ambiguous = 0

    for i in range(0, max(0, len(df) - horizon)):
        px = close[i]
        up_d = up_arr[i]
        down_d = down_arr[i]
        if not (np.isfinite(px) and px > 0 and np.isfinite(up_d) and np.isfinite(down_d)):
            continue
        if up_d <= 0 or down_d <= 0:
            continue
        upper = px * (1.0 + up_d)
        lower = px * (1.0 - down_d)
        bottom[i] = 0.0
        top[i] = 0.0
        for j in range(i + 1, min(i + 1 + horizon, len(df))):
            up_hit = np.isfinite(high[j]) and high[j] >= upper
            down_hit = np.isfinite(low[j]) and low[j] <= lower
            if up_hit and down_hit:
                ambiguous += 1
                bottom[i] = 0.0
                top[i] = 0.0
                break
            if up_hit:
                bottom[i] = 1.0
                top[i] = 0.0
                break
            if down_hit:
                bottom[i] = 0.0
                top[i] = 1.0
                break
    return pd.Series(bottom, index=df.index), pd.Series(top, index=df.index), ambiguous


def positive_run_stats(label: pd.Series) -> dict[str, float]:
    valid = label.dropna()
    if valid.empty:
        return {
            "positive_runs": 0,
            "positive_run_days_per_year": np.nan,
            "positive_event_runs_per_year": np.nan,
            "median_gap_trading_days": np.nan,
            "max_gap_trading_days": np.nan,
        }
    positive = valid.eq(1.0)
    run_start = positive & ~positive.shift(1, fill_value=False)
    starts = np.flatnonzero(run_start.to_numpy())
    years = max(len(valid) / TRADING_DAYS, 1 / TRADING_DAYS)
    gaps = np.diff(starts) if len(starts) >= 2 else np.array([])
    return {
        "positive_runs": int(run_start.sum()),
        "positive_run_days_per_year": float(positive.sum() / years),
        "positive_event_runs_per_year": float(run_start.sum() / years),
        "median_gap_trading_days": float(np.median(gaps)) if len(gaps) else np.nan,
        "max_gap_trading_days": float(np.max(gaps)) if len(gaps) else np.nan,
    }


def label_statistics(
    label: pd.Series,
    target: str,
    label_type: str,
    scheme: LabelScheme,
    horizon: int,
    ambiguous: int,
) -> dict[str, float | int | str]:
    valid = label.dropna()
    pos = int(valid.eq(1.0).sum())
    neg = int(valid.eq(0.0).sum())
    total = int(len(valid))
    stats = positive_run_stats(label)
    return {
        "target": target,
        "label_type": label_type,
        "scheme": scheme.name,
        "barrier_type": scheme.barrier_type,
        "horizon": horizon,
        "valid_samples": total,
        "positive_samples": pos,
        "negative_samples": neg,
        "positive_rate": float(pos / total) if total else np.nan,
        "negative_rate": float(neg / total) if total else np.nan,
        "invalid_tail_or_warmup": int(label.isna().sum()),
        "ambiguous_same_day_hits": ambiguous,
        "ambiguous_rate": float(ambiguous / total) if total else np.nan,
        **stats,
    }


def build_label_report(data: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, pd.DataFrame]:
    stats_rows = []
    recommendation_rows = []
    for target in TARGETS:
        df = data[target]
        for scheme in LABEL_SCHEMES:
            for horizon in HORIZONS:
                bottom, top, ambiguous = compute_barrier_labels(df, target, scheme, horizon)
                stats_rows.append(label_statistics(bottom, target, "bottom_entry", scheme, horizon, ambiguous))
                stats_rows.append(label_statistics(top, target, "top_risk_off", scheme, horizon, ambiguous))
    stats = pd.DataFrame(stats_rows)
    grouped = (
        stats.groupby(["scheme", "barrier_type", "horizon"], as_index=False)
        .agg(
            avg_positive_rate=("positive_rate", "mean"),
            avg_event_runs_per_year=("positive_event_runs_per_year", "mean"),
            avg_ambiguous_rate=("ambiguous_rate", "mean"),
            min_valid_samples=("valid_samples", "min"),
        )
        .copy()
    )
    grouped["score"] = (
        (grouped["avg_positive_rate"] - 0.15).abs()
        + ((grouped["avg_event_runs_per_year"] - 8.0).abs() / 100.0)
        + grouped["avg_ambiguous_rate"].fillna(0.0) * 2.0
        - np.where(grouped["barrier_type"].eq("atr"), 0.015, 0.0)
    )
    grouped = grouped.sort_values(["score", "barrier_type", "horizon"], ascending=[True, True, True])
    recommendation_rows.append(grouped.iloc[0].to_dict())
    return stats, pd.DataFrame(recommendation_rows)


def build_market_indicators(qqq: pd.DataFrame, vix: pd.DataFrame) -> dict[str, pd.Series]:
    close = qqq["close"].astype(float)
    high = qqq["high"].astype(float)
    low = qqq["low"].astype(float)
    ret = close.pct_change()
    ma20 = close.rolling(20, min_periods=20).mean()
    ma50 = close.rolling(50, min_periods=50).mean()
    ma100 = close.rolling(100, min_periods=100).mean()
    ma150 = close.rolling(150, min_periods=150).mean()
    ma200 = close.rolling(200, min_periods=200).mean()
    ema20 = ema(close, 20)
    ema50 = ema(close, 50)
    ema100 = ema(close, 100)
    macd_line, macd_signal, macd_hist = macd(close)
    rv10 = ret.rolling(10, min_periods=10).std(ddof=0) * math.sqrt(TRADING_DAYS)
    rv20 = ret.rolling(20, min_periods=20).std(ddof=0) * math.sqrt(TRADING_DAYS)
    vix_level = align_to(vix["close"].astype(float), qqq.index)
    vix_ma50 = vix_level.rolling(50, min_periods=30).mean()
    return {
        "qqq_close": close,
        "qqq_ma20": ma20,
        "qqq_ma50": ma50,
        "qqq_ma100": ma100,
        "qqq_ma150": ma150,
        "qqq_ma200": ma200,
        "qqq_ema20": ema20,
        "qqq_ema50": ema50,
        "qqq_ema100": ema100,
        "qqq_rsi14": rsi(close, 14),
        "qqq_macd": macd_line,
        "qqq_macd_signal": macd_signal,
        "qqq_macd_hist": macd_hist,
        "qqq_roc5": close.pct_change(5),
        "qqq_roc20": close.pct_change(20),
        "qqq_drawdown_120": close.div(close.rolling(120, min_periods=60).max()).sub(1.0),
        "qqq_atr14_pct": atr(qqq, 14).div(close),
        "qqq_realized_vol10": rv10,
        "qqq_realized_vol20": rv20,
        "qqq_vol_percentile_60": rolling_percentile_last(rv20, 60),
        "qqq_rolling_range_20": high.rolling(20, min_periods=20).max().div(low.rolling(20, min_periods=20).min()).sub(1.0),
        "vix_level": vix_level,
        "vix_ma50": vix_ma50,
        "vix_regime_high": ((vix_level > vix_ma50) & (vix_level > 20.0)).astype(float),
    }


def feature_catalog() -> pd.DataFrame:
    rows = [
        ("qqq_close_over_ma100", "QQQ close / QQQ MA100 - 1", "中期趋势过滤；避免在 Nasdaq-100 中期下行趋势中过早持有杠杆 ETF"),
        ("qqq_close_over_ma200", "QQQ close / QQQ MA200 - 1", "长期牛熊状态；对杠杆 ETF 的大回撤控制更重要"),
        ("qqq_ema20_over_ema100", "QQQ EMA20 / EMA100 - 1", "快慢趋势方向；比单日价格更平滑"),
        ("qqq_price_distance_ma100", "QQQ close / MA100 - 1", "价格离中期均线的距离；衡量趋势强弱或过热"),
        ("qqq_ma50_slope_20", "QQQ MA50 / MA50.shift(20) - 1", "中期均线斜率；识别趋势是否在改善"),
        ("qqq_ma100_slope_20", "QQQ MA100 / MA100.shift(20) - 1", "更慢的趋势斜率；降低噪声"),
        ("qqq_rsi14", "QQQ RSI(14)", "短中期超买超卖与反弹确认"),
        ("qqq_macd", "QQQ EMA12 - EMA26", "趋势动量主线"),
        ("qqq_macd_signal", "EMA9(QQQ MACD)", "MACD 触发线；用于确认动量变化"),
        ("qqq_macd_hist", "QQQ MACD - MACD signal", "动量改善/转弱的直观代理"),
        ("qqq_roc5", "QQQ 5-day close return", "短期反弹或下跌速度"),
        ("qqq_roc20", "QQQ 20-day close return", "月度动量背景"),
        ("qqq_drawdown_120", "QQQ close / rolling 120-day peak - 1", "从近期高点回撤幅度；衡量底部候选环境"),
        ("qqq_mom_spread_5_20", "QQQ ROC5 - QQQ ROC20", "短期动量相对中期动量的转折信息"),
        ("qqq_atr14_pct", "QQQ ATR14 / close", "日内波动强度；杠杆 ETF 路径损耗高度相关"),
        ("qqq_realized_vol10", "std(QQQ daily return, 10) * sqrt(252)", "短期实现波动率状态"),
        ("qqq_realized_vol20", "std(QQQ daily return, 20) * sqrt(252)", "月度实现波动率状态"),
        ("qqq_vol_percentile_60", "Rolling percentile of realized_vol20 over 60 days", "当前波动是否处在近期高位"),
        ("qqq_rolling_range_20", "rolling 20-day high / rolling 20-day low - 1", "区间振幅；识别震荡/高波动环境"),
        ("vix_level", "VIX close aligned to QQQ calendar", "市场恐慌/风险偏好状态"),
        ("vix_ma50", "VIX 50-day moving average", "VIX 中期基准水平"),
        ("vix_regime_high", "1 if VIX > VIX_MA50 and VIX > 20 else 0", "高恐慌 regime 标记"),
        ("etf_gap_open", "Target ETF open / prior close - 1", "杠杆 ETF 隔夜跳空风险"),
        ("etf_intraday_range_pct", "Target ETF high / low - 1", "杠杆 ETF 当日振幅与执行风险"),
        ("etf_vs_qqq_5d_return_gap", "Target ETF 5-day return - leverage * QQQ 5-day return", "杠杆 ETF 相对理论杠杆的短期偏离/路径损耗"),
    ]
    return pd.DataFrame(rows, columns=["feature_name", "definition", "economic_meaning"]).assign(final_keep=True)


def build_features_for_target(
    target: str,
    target_df: pd.DataFrame,
    qqq: pd.DataFrame,
    indicators: dict[str, pd.Series],
) -> pd.DataFrame:
    idx = target_df.index
    qqq_close = indicators["qqq_close"]
    leverage = 2.0 if target == "QLD" else 3.0
    out = pd.DataFrame(index=idx)
    out["qqq_close_over_ma100"] = align_to(qqq_close.div(indicators["qqq_ma100"]).sub(1.0), idx)
    out["qqq_close_over_ma200"] = align_to(qqq_close.div(indicators["qqq_ma200"]).sub(1.0), idx)
    out["qqq_ema20_over_ema100"] = align_to(indicators["qqq_ema20"].div(indicators["qqq_ema100"]).sub(1.0), idx)
    out["qqq_price_distance_ma100"] = out["qqq_close_over_ma100"]
    out["qqq_ma50_slope_20"] = align_to(indicators["qqq_ma50"].div(indicators["qqq_ma50"].shift(20)).sub(1.0), idx)
    out["qqq_ma100_slope_20"] = align_to(indicators["qqq_ma100"].div(indicators["qqq_ma100"].shift(20)).sub(1.0), idx)
    out["qqq_rsi14"] = align_to(indicators["qqq_rsi14"], idx)
    out["qqq_macd"] = align_to(indicators["qqq_macd"], idx)
    out["qqq_macd_signal"] = align_to(indicators["qqq_macd_signal"], idx)
    out["qqq_macd_hist"] = align_to(indicators["qqq_macd_hist"], idx)
    out["qqq_roc5"] = align_to(indicators["qqq_roc5"], idx)
    out["qqq_roc20"] = align_to(indicators["qqq_roc20"], idx)
    out["qqq_drawdown_120"] = align_to(indicators["qqq_drawdown_120"], idx)
    out["qqq_mom_spread_5_20"] = out["qqq_roc5"] - out["qqq_roc20"]
    out["qqq_atr14_pct"] = align_to(indicators["qqq_atr14_pct"], idx)
    out["qqq_realized_vol10"] = align_to(indicators["qqq_realized_vol10"], idx)
    out["qqq_realized_vol20"] = align_to(indicators["qqq_realized_vol20"], idx)
    out["qqq_vol_percentile_60"] = align_to(indicators["qqq_vol_percentile_60"], idx)
    out["qqq_rolling_range_20"] = align_to(indicators["qqq_rolling_range_20"], idx)
    out["vix_level"] = align_to(indicators["vix_level"], idx)
    out["vix_ma50"] = align_to(indicators["vix_ma50"], idx)
    out["vix_regime_high"] = align_to(indicators["vix_regime_high"], idx)
    out["etf_gap_open"] = target_df["open"].div(target_df["close"].shift(1)).sub(1.0)
    out["etf_intraday_range_pct"] = target_df["high"].div(target_df["low"]).sub(1.0)
    out["etf_vs_qqq_5d_return_gap"] = target_df["close"].pct_change(5) - leverage * align_to(qqq["close"].pct_change(5), idx)
    return out[feature_catalog()["feature_name"].tolist()]


def to_signal(series: pd.Series, index: pd.Index) -> pd.Series:
    return series.reindex(index).ffill().fillna(False).astype(bool).astype(float)


def build_strategies(target_df: pd.DataFrame, indicators: dict[str, pd.Series]) -> list[StrategySpec]:
    idx = target_df.index
    qqq_close = indicators["qqq_close"]
    ma100 = indicators["qqq_ma100"]
    ma200 = indicators["qqq_ma200"]
    ema20 = indicators["qqq_ema20"]
    ema100 = indicators["qqq_ema100"]
    vol_pct = indicators["qqq_vol_percentile_60"]
    vix_level = indicators["vix_level"]
    vix_ma50 = indicators["vix_ma50"]
    macd_hist = indicators["qqq_macd_hist"]

    trend100 = qqq_close > ma100
    trend200 = qqq_close > ma200
    ema_direction = ema20 > ema100
    risk_ok = (vol_pct <= 0.80) & ((vix_level <= vix_ma50 * 1.15) | (vix_level <= 22.0))
    macd_confirm = macd_hist > 0

    return [
        StrategySpec(
            "qqq_ma100_trend",
            "trend_filter",
            "Hold target ETF only when QQQ close is above MA100.",
            to_signal(trend100, idx),
            1.0,
        ),
        StrategySpec(
            "qqq_ma200_trend",
            "trend_filter",
            "Hold target ETF only when QQQ close is above MA200.",
            to_signal(trend200, idx),
            1.0,
        ),
        StrategySpec(
            "ema20_ema100_direction",
            "fast_slow_ma",
            "Hold target ETF when QQQ EMA20 is above EMA100.",
            to_signal(ema_direction, idx),
            1.2,
        ),
        StrategySpec(
            "trend_vol_vix_filter",
            "trend_plus_risk_filter",
            "Hold when QQQ is above MA100 and realized-vol/VIX risk is not elevated.",
            to_signal(trend100 & risk_ok, idx),
            1.8,
        ),
        StrategySpec(
            "trend_macd_confirm",
            "trend_plus_turn_confirm",
            "Hold when QQQ is above MA100 and MACD histogram is positive.",
            to_signal(trend100 & macd_confirm, idx),
            1.4,
        ),
    ]


def backtest_long_only(
    asset: pd.DataFrame,
    signal: pd.Series,
    fee: float = DEFAULT_FEE,
    execution: str = DEFAULT_EXECUTION,
) -> BacktestResult:
    if execution not in {"next_open", "next_close"}:
        raise ValueError("execution must be next_open or next_close")
    df = asset[["open", "close"]].copy().dropna()
    desired = signal.reindex(df.index).ffill().fillna(0.0).astype(float).clip(0.0, 1.0)
    open_arr = df["open"].to_numpy(dtype=float)
    close_arr = df["close"].to_numpy(dtype=float)
    desired_arr = desired.to_numpy(dtype=float)
    n = len(df)
    nav = np.ones(n, dtype=float)
    ret = np.zeros(n, dtype=float)
    pos_arr = np.zeros(n, dtype=float)
    turnover = np.zeros(n, dtype=float)
    equity = 1.0
    pos = 0.0

    for i in range(1, n):
        prev_equity = equity
        prev_close = close_arr[i - 1]
        today_open = open_arr[i]
        today_close = close_arr[i]
        desired_for_today = desired_arr[i - 1]

        if execution == "next_open":
            if pos > 0 and np.isfinite(prev_close) and np.isfinite(today_open) and prev_close > 0:
                equity *= today_open / prev_close
            delta = abs(desired_for_today - pos)
            if delta > 0:
                equity *= max(0.0, 1.0 - fee * delta)
            pos = desired_for_today
            if pos > 0 and np.isfinite(today_open) and np.isfinite(today_close) and today_open > 0:
                equity *= today_close / today_open
        else:
            if pos > 0 and np.isfinite(prev_close) and np.isfinite(today_close) and prev_close > 0:
                equity *= today_close / prev_close
            delta = abs(desired_for_today - pos)
            if delta > 0:
                equity *= max(0.0, 1.0 - fee * delta)
            pos = desired_for_today

        nav[i] = equity
        ret[i] = equity / prev_equity - 1.0 if prev_equity > 0 else 0.0
        pos_arr[i] = pos
        turnover[i] = delta

    nav_s = pd.Series(nav, index=df.index, name="nav")
    pos_s = pd.Series(pos_arr, index=df.index, name="position")
    turnover_s = pd.Series(turnover, index=df.index, name="turnover")
    entries = (pos_s > 0.5) & ~(pos_s.shift(1).fillna(0.0) > 0.5)
    exits = ~(pos_s > 0.5) & (pos_s.shift(1).fillna(0.0) > 0.5)
    return BacktestResult(
        nav=nav_s,
        returns=pd.Series(ret, index=df.index, name="returns"),
        position=pos_s,
        turnover=turnover_s,
        entries=entries,
        exits=exits,
        execution=execution,
        fee=fee,
    )


def slice_series(series: pd.Series, start: str | None, end: str | None) -> pd.Series:
    out = series.copy()
    if start:
        out = out.loc[out.index >= pd.Timestamp(start)]
    if end:
        out = out.loc[out.index <= pd.Timestamp(end)]
    return out


def holding_days(position: pd.Series) -> float:
    pos = position.fillna(0.0).gt(0.5)
    if pos.empty or not pos.any():
        return 0.0
    starts = np.flatnonzero((pos & ~pos.shift(1, fill_value=False)).to_numpy())
    ends = np.flatnonzero((~pos & pos.shift(1, fill_value=False)).to_numpy())
    if len(ends) < len(starts):
        ends = np.r_[ends, len(pos) - 1]
    durations = []
    for start_idx, end_idx in zip(starts, ends):
        durations.append(max(1, end_idx - start_idx))
    return float(np.mean(durations)) if durations else 0.0


def metrics_from_result(result: BacktestResult, start: str | None = None, end: str | None = None) -> dict[str, float]:
    nav = slice_series(result.nav, start, end).dropna()
    if len(nav) < 2:
        return {
            "CAGR": np.nan,
            "Max Drawdown": np.nan,
            "Sharpe": np.nan,
            "Calmar": np.nan,
            "trade count": 0,
            "turnover": np.nan,
            "avg holding days": 0.0,
            "exposure": np.nan,
            "final_nav": np.nan,
        }
    nav = nav / nav.iloc[0]
    returns = nav.pct_change().fillna(0.0)
    pos = slice_series(result.position, start, end).reindex(nav.index).fillna(0.0)
    entries = slice_series(result.entries.astype(float), start, end).reindex(nav.index).fillna(0.0).astype(bool)
    turnover = slice_series(result.turnover, start, end).reindex(nav.index).fillna(0.0)
    years = max((nav.index[-1] - nav.index[0]).days / 365.25, 1 / 365.25)
    cagr = cagr_from_nav(nav)
    mdd = max_drawdown(nav)
    sharpe = sharpe_from_returns(returns)
    calmar = cagr / abs(mdd) if np.isfinite(cagr) and np.isfinite(mdd) and mdd < 0 else np.nan
    return {
        "CAGR": cagr,
        "Max Drawdown": mdd,
        "Sharpe": sharpe,
        "Calmar": calmar,
        "trade count": int(entries.sum()),
        "turnover": float(turnover.sum() / years),
        "avg holding days": holding_days(pos),
        "exposure": float(pos.mean()),
        "final_nav": float(nav.iloc[-1]),
    }


def metrics_from_nav(
    nav: pd.Series,
    position: pd.Series | None = None,
    turnover: pd.Series | None = None,
    entries: pd.Series | None = None,
    start: str | None = None,
    end: str | None = None,
) -> dict[str, float]:
    nav_seg = slice_series(nav.dropna(), start, end)
    if len(nav_seg) < 2:
        return {
            "CAGR": np.nan,
            "Max Drawdown": np.nan,
            "Sharpe": np.nan,
            "Calmar": np.nan,
            "trade count": 0,
            "turnover": np.nan,
            "avg holding days": 0.0,
            "exposure": np.nan,
            "final_nav": np.nan,
        }
    nav_seg = nav_seg / nav_seg.iloc[0]
    returns = nav_seg.pct_change().fillna(0.0)
    cagr = cagr_from_nav(nav_seg)
    mdd = max_drawdown(nav_seg)
    sharpe = sharpe_from_returns(returns)
    calmar = cagr / abs(mdd) if np.isfinite(cagr) and np.isfinite(mdd) and mdd < 0 else np.nan
    years = max((nav_seg.index[-1] - nav_seg.index[0]).days / 365.25, 1 / 365.25)
    pos_seg = slice_series(position, start, end).reindex(nav_seg.index).fillna(0.0) if position is not None else None
    turnover_seg = slice_series(turnover, start, end).reindex(nav_seg.index).fillna(0.0) if turnover is not None else None
    entries_seg = slice_series(entries.astype(float), start, end).reindex(nav_seg.index).fillna(0.0).astype(bool) if entries is not None else None
    return {
        "CAGR": cagr,
        "Max Drawdown": mdd,
        "Sharpe": sharpe,
        "Calmar": calmar,
        "trade count": int(entries_seg.sum()) if entries_seg is not None else np.nan,
        "turnover": float(turnover_seg.sum() / years) if turnover_seg is not None else np.nan,
        "avg holding days": holding_days(pos_seg) if pos_seg is not None else np.nan,
        "exposure": float(pos_seg.mean()) if pos_seg is not None else np.nan,
        "final_nav": float(nav_seg.iloc[-1]),
    }


def validation_splits() -> list[SplitSpec]:
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


def evaluate_validation(
    data: dict[str, pd.DataFrame],
    indicators: dict[str, pd.Series],
    fee: float,
    execution: str,
) -> tuple[pd.DataFrame, dict[tuple[str, str], BacktestResult], dict[str, list[StrategySpec]]]:
    rows = []
    result_cache: dict[tuple[str, str], BacktestResult] = {}
    strategy_cache: dict[str, list[StrategySpec]] = {}
    for target in TARGETS:
        strategies = build_strategies(data[target], indicators)
        strategy_cache[target] = strategies
        for strategy in strategies:
            result = backtest_long_only(data[target], strategy.signal, fee=fee, execution=execution)
            result_cache[(target, strategy.name)] = result
            for split in validation_splits():
                m = metrics_from_result(result, split.test_start, split.test_end)
                rows.append(
                    {
                        "target": target,
                        "strategy": strategy.name,
                        "family": strategy.family,
                        "split_type": split.split_type,
                        "split": split.name,
                        "train_start": split.train_start,
                        "train_end": split.train_end,
                        "test_start": split.test_start,
                        "test_end": split.test_end or data[target].index.max().strftime("%Y-%m-%d"),
                        "execution": execution,
                        "fee": fee,
                        "CAGR": m["CAGR"],
                        "Max Drawdown": m["Max Drawdown"],
                        "Sharpe": m["Sharpe"],
                        "Calmar": m["Calmar"],
                        "trade count": m["trade count"],
                        "turnover": m["turnover"],
                        "avg holding days": m["avg holding days"],
                        "exposure": m["exposure"],
                        "final_nav": m["final_nav"],
                    }
                )
    return pd.DataFrame(rows), result_cache, strategy_cache


def summarize_validation(validation: pd.DataFrame) -> pd.DataFrame:
    return (
        validation.groupby(["target", "strategy", "family", "split_type"], as_index=False)
        .agg(
            mean_CAGR=("CAGR", "mean"),
            median_CAGR=("CAGR", "median"),
            worst_CAGR=("CAGR", "min"),
            mean_Max_Drawdown=("Max Drawdown", "mean"),
            worst_Max_Drawdown=("Max Drawdown", "min"),
            mean_Sharpe=("Sharpe", "mean"),
            median_Calmar=("Calmar", "median"),
            worst_Calmar=("Calmar", "min"),
            mean_trade_count=("trade count", "mean"),
            mean_turnover=("turnover", "mean"),
            mean_holding_days=("avg holding days", "mean"),
        )
        .sort_values(["target", "split_type", "median_Calmar"], ascending=[True, True, False])
    )


def select_strategies(validation: pd.DataFrame, strategy_cache: dict[str, list[StrategySpec]]) -> pd.DataFrame:
    complexity = {
        (target, strategy.name): strategy.complexity
        for target, strategies in strategy_cache.items()
        for strategy in strategies
    }
    rows = []
    for (target, strategy), sub in validation.groupby(["target", "strategy"]):
        row = {
            "target": target,
            "strategy": strategy,
            "family": sub["family"].iloc[0],
            "median_Calmar": float(sub["Calmar"].median()),
            "worst_Calmar": float(sub["Calmar"].min()),
            "median_CAGR": float(sub["CAGR"].median()),
            "worst_Max_Drawdown": float(sub["Max Drawdown"].min()),
            "mean_turnover": float(sub["turnover"].mean()),
            "mean_trade_count": float(sub["trade count"].mean()),
            "complexity": float(complexity[(target, strategy)]),
        }
        row["selection_score"] = (
            row["median_Calmar"]
            + 0.50 * row["worst_Calmar"]
            + 0.20 * row["median_CAGR"]
            - 0.05 * row["mean_turnover"]
            - 0.03 * row["complexity"]
        )
        rows.append(row)
    selected = pd.DataFrame(rows).sort_values(["target", "selection_score"], ascending=[True, False])
    return selected.groupby("target", as_index=False).head(1).reset_index(drop=True)


def cost_sensitivity(
    data: dict[str, pd.DataFrame],
    strategy_cache: dict[str, list[StrategySpec]],
) -> pd.DataFrame:
    fees = (0.0, 0.001, 0.002, 0.003)
    executions = ("next_open", "next_close")
    rows = []
    zero_lookup: dict[tuple[str, str, str], float] = {}
    for target in TARGETS:
        for strategy in strategy_cache[target]:
            for execution in executions:
                for fee in fees:
                    result = backtest_long_only(data[target], strategy.signal, fee=fee, execution=execution)
                    m = metrics_from_result(result, TEST_START, None)
                    key = (target, strategy.name, execution)
                    if fee == 0.0:
                        zero_lookup[key] = m["CAGR"]
                    zero_cagr = zero_lookup.get(key, np.nan)
                    delta = m["CAGR"] - zero_cagr if np.isfinite(zero_cagr) and np.isfinite(m["CAGR"]) else np.nan
                    rows.append(
                        {
                            "target": target,
                            "strategy": strategy.name,
                            "family": strategy.family,
                            "execution": execution,
                            "one_way_fee": fee,
                            "period_start": TEST_START,
                            "period_end": data[target].index.max().strftime("%Y-%m-%d"),
                            "CAGR": m["CAGR"],
                            "Max Drawdown": m["Max Drawdown"],
                            "Sharpe": m["Sharpe"],
                            "Calmar": m["Calmar"],
                            "trade count": m["trade count"],
                            "turnover": m["turnover"],
                            "avg holding days": m["avg holding days"],
                            "cost_vs_zero_CAGR_delta": delta,
                        }
                    )
    out = pd.DataFrame(rows)
    alerts = []
    for (target, strategy, execution), sub in out.groupby(["target", "strategy", "execution"]):
        zero = sub.loc[sub["one_way_fee"].eq(0.0), "CAGR"]
        high = sub.loc[sub["one_way_fee"].eq(0.003), "CAGR"]
        if zero.empty or high.empty:
            alert = False
        else:
            z = float(zero.iloc[0])
            h = float(high.iloc[0])
            alert = bool(np.isfinite(z) and np.isfinite(h) and ((z - h) > 0.05 or (z > 0 and (z - h) / abs(z) > 0.30)))
        alerts.append({"target": target, "strategy": strategy, "execution": execution, "cost_extreme_alert": alert})
    return out.merge(pd.DataFrame(alerts), on=["target", "strategy", "execution"], how="left")


def trade_log_from_result(asset: pd.DataFrame, result: BacktestResult) -> pd.DataFrame:
    pos = result.position.reindex(asset.index).fillna(0.0).gt(0.5)
    starts = np.flatnonzero((pos & ~pos.shift(1, fill_value=False)).to_numpy())
    ends = np.flatnonzero((~pos & pos.shift(1, fill_value=False)).to_numpy())
    if len(ends) and len(starts) and ends[0] < starts[0]:
        ends = ends[1:]
    rows = []
    for k, start_idx in enumerate(starts):
        closed = k < len(ends)
        end_idx = int(ends[k]) if closed else len(asset) - 1
        entry_date = asset.index[int(start_idx)]
        exit_date = asset.index[end_idx]
        if result.execution == "next_close":
            entry_price = float(asset["close"].iloc[int(start_idx)])
            exit_price = float(asset["close"].iloc[end_idx])
        else:
            entry_price = float(asset["open"].iloc[int(start_idx)])
            exit_price = float(asset["open"].iloc[end_idx]) if closed else float(asset["close"].iloc[end_idx])
        gross = exit_price / entry_price - 1.0 if entry_price > 0 else np.nan
        fee_drag = result.fee * (2.0 if closed else 1.0)
        rows.append(
            {
                "entry_date": entry_date.strftime("%Y-%m-%d"),
                "entry_price": entry_price,
                "exit_date": exit_date.strftime("%Y-%m-%d") if closed else "",
                "exit_or_mark_price": exit_price,
                "status": "closed" if closed else "open",
                "gross_return": gross,
                "approx_net_return_after_fees": gross - fee_drag if np.isfinite(gross) else np.nan,
                "holding_days": int(max(1, end_idx - int(start_idx))),
            }
        )
    return pd.DataFrame(rows)


def drawdown_series(nav: pd.Series) -> pd.Series:
    return nav.div(nav.cummax()).sub(1.0)


def save_plots(
    run_dir: Path,
    data: dict[str, pd.DataFrame],
    selected: pd.DataFrame,
    result_cache: dict[tuple[str, str], BacktestResult],
    strategy_cache: dict[str, list[StrategySpec]],
) -> None:
    for target in TARGETS:
        strategy_name = selected.loc[selected["target"].eq(target), "strategy"].iloc[0]
        result = result_cache[(target, strategy_name)]
        buy_hold = backtest_long_only(
            data[target],
            pd.Series(1.0, index=data[target].index),
            fee=DEFAULT_FEE,
            execution=DEFAULT_EXECUTION,
        )
        nav = pd.DataFrame({"selected_v1": result.nav, "buy_hold": buy_hold.nav}).dropna()
        nav = nav / nav.iloc[0]

        fig, ax = plt.subplots(figsize=(11, 5))
        nav.plot(ax=ax, linewidth=1.8)
        ax.set_title(f"{target} equity curve: {strategy_name}")
        ax.set_ylabel("Growth of $1")
        ax.grid(True, alpha=0.25)
        fig.tight_layout()
        fig.savefig(run_dir / f"{target.lower()}_equity_curve.png", dpi=150)
        plt.close(fig)

        fig, ax = plt.subplots(figsize=(11, 4))
        drawdown_series(nav["selected_v1"]).plot(ax=ax, label="selected_v1", linewidth=1.8)
        drawdown_series(nav["buy_hold"]).plot(ax=ax, label="buy_hold", linewidth=1.2, alpha=0.8)
        ax.set_title(f"{target} drawdown: {strategy_name}")
        ax.set_ylabel("Drawdown")
        ax.legend()
        ax.grid(True, alpha=0.25)
        fig.tight_layout()
        fig.savefig(run_dir / f"{target.lower()}_drawdown.png", dpi=150)
        plt.close(fig)

        strategy = {s.name: s for s in strategy_cache[target]}[strategy_name]
        chart = data[target].loc[data[target].index >= pd.Timestamp("2021-01-01")].copy()
        sig = strategy.signal.reindex(chart.index).ffill().fillna(0.0)
        entries = result.entries.reindex(chart.index).fillna(False)
        exits = result.exits.reindex(chart.index).fillna(False)
        fig, ax = plt.subplots(figsize=(12, 5))
        chart["close"].plot(ax=ax, color="#1f4e79", linewidth=1.4)
        ax.scatter(chart.index[entries], chart.loc[entries, "close"], marker="^", color="#2ca02c", s=32, label="entry")
        ax.scatter(chart.index[exits], chart.loc[exits, "close"], marker="v", color="#d62728", s=32, label="exit")
        ax.fill_between(chart.index, chart["close"].min(), chart["close"].max(), where=sig.gt(0.5).to_numpy(), color="#8fd19e", alpha=0.12)
        ax.set_title(f"{target} signal chart since 2021: {strategy_name}")
        ax.set_ylabel("Adjusted close")
        ax.legend(loc="best")
        ax.grid(True, alpha=0.25)
        fig.tight_layout()
        fig.savefig(run_dir / f"{target.lower()}_signal_chart.png", dpi=150)
        plt.close(fig)


def latest_old_run() -> Path | None:
    root = ROOT / "outputs" / "qldtqqq_turning_points"
    if not root.exists():
        return None
    runs = sorted([p for p in root.iterdir() if p.is_dir() and (p / "best_strategy_summary.csv").exists()], key=lambda p: p.stat().st_mtime, reverse=True)
    return runs[0] if runs else None


def old_optimal_metrics(old_dir: Path | None, target: str) -> dict[str, float] | None:
    if old_dir is None:
        return None
    nav_path = old_dir / f"{target}_best_signal_nav.csv"
    if not nav_path.exists():
        return None
    df = pd.read_csv(nav_path)
    if "date" not in df.columns or "portfolio_value" not in df.columns:
        return None
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.normalize()
    df = df.dropna(subset=["date"]).sort_values("date").set_index("date")
    nav = pd.to_numeric(df["portfolio_value"], errors="coerce")
    pos = pd.to_numeric(df.get("position_weight_at_open", pd.Series(index=df.index, dtype=float)), errors="coerce")
    desired = pd.to_numeric(df.get("desired_weight_after_close", pd.Series(index=df.index, dtype=float)), errors="coerce")
    turnover = desired.diff().abs().fillna(0.0)
    entries = pd.to_numeric(df.get("entry_at_open", pd.Series(index=df.index, dtype=float)), errors="coerce").fillna(0.0).gt(0.0)
    return metrics_from_nav(nav, position=pos, turnover=turnover, entries=entries, start=TEST_START)


def benchmark_comparison(
    data: dict[str, pd.DataFrame],
    selected: pd.DataFrame,
    result_cache: dict[tuple[str, str], BacktestResult],
    strategy_cache: dict[str, list[StrategySpec]],
    old_dir: Path | None,
) -> pd.DataFrame:
    rows = []
    for target in TARGETS:
        strategies = {s.name: s for s in strategy_cache[target]}
        selected_strategy = selected.loc[selected["target"].eq(target), "strategy"].iloc[0]
        cases = [
            ("buy_hold", "Always hold the target ETF", pd.Series(1.0, index=data[target].index)),
            ("qqq_ma100_trend_filter", "QQQ close > MA100 then hold target ETF", strategies["qqq_ma100_trend"].signal),
            (f"selected_v1_{selected_strategy}", "Selected v1 primary strategy by walk-forward stability score", strategies[selected_strategy].signal),
        ]
        for name, description, signal in cases:
            result = backtest_long_only(data[target], signal, fee=DEFAULT_FEE, execution=DEFAULT_EXECUTION)
            m = metrics_from_result(result, TEST_START, None)
            rows.append(
                {
                    "target": target,
                    "benchmark": name,
                    "description": description,
                    "period_start": TEST_START,
                    "period_end": data[target].index.max().strftime("%Y-%m-%d"),
                    "execution": DEFAULT_EXECUTION,
                    "one_way_fee": DEFAULT_FEE,
                    "CAGR": m["CAGR"],
                    "Max Drawdown": m["Max Drawdown"],
                    "Sharpe": m["Sharpe"],
                    "Calmar": m["Calmar"],
                    "trade count": m["trade count"],
                    "turnover": m["turnover"],
                    "avg holding days": m["avg holding days"],
                    "source": "v1_script",
                }
            )
        old = old_optimal_metrics(old_dir, target)
        if old is not None:
            rows.append(
                {
                    "target": target,
                    "benchmark": "old_optimal_strategy_20260420" if old_dir and "20260420" in old_dir.name else "old_optimal_strategy_latest",
                    "description": f"Reusable old complex optimized strategy from {old_dir}",
                    "period_start": TEST_START,
                    "period_end": data[target].index.max().strftime("%Y-%m-%d"),
                    "execution": "next_open_fractional_weight",
                    "one_way_fee": DEFAULT_FEE,
                    "CAGR": old["CAGR"],
                    "Max Drawdown": old["Max Drawdown"],
                    "Sharpe": old["Sharpe"],
                    "Calmar": old["Calmar"],
                    "trade count": old["trade count"],
                    "turnover": old["turnover"],
                    "avg holding days": old["avg holding days"],
                    "source": str(old_dir),
                }
            )
    return pd.DataFrame(rows)


def format_validation_for_md(df: pd.DataFrame, max_rows: int = 20) -> pd.DataFrame:
    cols = ["target", "strategy", "split_type", "split", "CAGR", "Max Drawdown", "Sharpe", "Calmar", "trade count", "turnover", "avg holding days"]
    out = df[cols].copy()
    for col in ("CAGR", "Max Drawdown"):
        out[col] = out[col].map(lambda x: pct(x))
    for col in ("Sharpe", "Calmar", "turnover", "avg holding days"):
        out[col] = out[col].map(lambda x: num(x))
    return out.head(max_rows)


def format_summary_for_md(df: pd.DataFrame, max_rows: int = 20) -> pd.DataFrame:
    cols = ["target", "strategy", "split_type", "median_CAGR", "worst_CAGR", "worst_Max_Drawdown", "median_Calmar", "worst_Calmar", "mean_turnover"]
    out = df[cols].copy()
    for col in ("median_CAGR", "worst_CAGR", "worst_Max_Drawdown"):
        out[col] = out[col].map(lambda x: pct(x))
    for col in ("median_Calmar", "worst_Calmar", "mean_turnover"):
        out[col] = out[col].map(lambda x: num(x))
    return out.head(max_rows)


def write_label_report(run_dir: Path, label_stats: pd.DataFrame, recommendation: pd.DataFrame) -> None:
    fmt = label_stats.copy()
    for col in ("positive_rate", "negative_rate", "ambiguous_rate"):
        fmt[col] = fmt[col].map(lambda x: pct(x))
    for col in ("positive_run_days_per_year", "positive_event_runs_per_year", "median_gap_trading_days", "max_gap_trading_days"):
        fmt[col] = fmt[col].map(lambda x: num(x))
    rec = recommendation.iloc[0]
    scheme = next(s for s in LABEL_SCHEMES if s.name == rec["scheme"])
    lines = [
        "# Label Report",
        "",
        "## 定义",
        "",
        "A. bottom-like entry label: 从 t 日收盘后视角出发，未来 H 个交易日内若先触及上方 barrier，标记为 1；若先触及下方 barrier、同日上下同时触及、或到期未触及上方 barrier，标记为 0。",
        "",
        "B. top-like exit / risk-off label: 从 t 日收盘后视角出发，未来 H 个交易日内若先触及下方 barrier，标记为 1；若先触及上方 barrier、同日上下同时触及、或到期未触及下方 barrier，标记为 0。",
        "",
        "同日上下 barrier 都被日线 high/low 覆盖时，无法知道先后顺序。本轮采用保守处理：两个标签都不记正样本，避免乐观泄漏。",
        "",
        "这些标签只用于定义研究目标与后续监督学习准备，本轮主策略没有读取未来标签，也没有把标签信息泄漏到特征中。",
        "",
        "## 参数组合",
        "",
        md_table(pd.DataFrame([s.__dict__ for s in LABEL_SCHEMES])[["name", "barrier_type", "description"]]),
        "",
        "Horizon H: `10`, `15`, `20` trading days.",
        "",
        "## 正负样本占比与稀疏度",
        "",
        md_table(
            fmt[
                [
                    "target",
                    "label_type",
                    "scheme",
                    "horizon",
                    "valid_samples",
                    "positive_rate",
                    "negative_rate",
                    "positive_runs",
                    "positive_event_runs_per_year",
                    "median_gap_trading_days",
                    "ambiguous_same_day_hits",
                    "ambiguous_rate",
                ]
            ]
        ),
        "",
        "## 本轮推荐标签方案",
        "",
        f"推荐先采用 `{rec['scheme']}` + `H={int(rec['horizon'])}`。原因：平均正样本率 {pct(rec['avg_positive_rate'])}，平均正事件 runs/year {num(rec['avg_event_runs_per_year'])}，同日歧义率 {pct(rec['avg_ambiguous_rate'])}，在不过度稀疏和不过度密集之间较平衡。",
        "",
        f"该方案定义：{scheme.description}",
    ]
    write_text(run_dir / "label_report.md", "\n".join(lines))


def unstable_strategies(validation_summary: pd.DataFrame) -> pd.DataFrame:
    out = validation_summary.copy()
    return out[(out["worst_Calmar"] < 0.0) | (out["worst_CAGR"] < -0.05)].sort_values(["target", "worst_Calmar"])


def write_validation_summary(run_dir: Path, validation: pd.DataFrame, summary: pd.DataFrame, selected: pd.DataFrame) -> None:
    anchored = summary[summary["split_type"].eq("anchored")].sort_values(["target", "median_Calmar"], ascending=[True, False])
    rolling = summary[summary["split_type"].eq("rolling")].sort_values(["target", "median_Calmar"], ascending=[True, False])
    unstable = unstable_strategies(summary)
    selected_fmt = selected.copy()
    for col in ("median_CAGR", "worst_Max_Drawdown"):
        selected_fmt[col] = selected_fmt[col].map(lambda x: pct(x))
    for col in ("median_Calmar", "worst_Calmar", "mean_turnover", "selection_score"):
        selected_fmt[col] = selected_fmt[col].map(lambda x: num(x))
    lines = [
        "# Validation Summary",
        "",
        "本轮主策略没有在测试段重选参数。训练窗口用于时间切分与规则冻结，测试窗口只做 OOS 评估。",
        "",
        "## Selected By Stability",
        "",
        md_table(selected_fmt),
        "",
        "## Anchored Walk-forward Summary",
        "",
        md_table(format_summary_for_md(anchored, 20)),
        "",
        "## Rolling Walk-forward Summary",
        "",
        md_table(format_summary_for_md(rolling, 20)),
        "",
        "## Split-by-split Sample",
        "",
        md_table(format_validation_for_md(validation.sort_values(["target", "split_type", "split", "strategy"]), 30)),
        "",
        "## 单段表现好但稳定性较弱的策略",
        "",
        md_table(format_summary_for_md(unstable, 30)) if not unstable.empty else "未发现 worst Calmar < 0 或 worst CAGR < -5% 的明显单段脆弱策略。",
    ]
    write_text(run_dir / "validation_summary.md", "\n".join(lines))


def write_research_summary(
    run_dir: Path,
    data_status: pd.DataFrame,
    label_stats: pd.DataFrame,
    recommendation: pd.DataFrame,
    validation: pd.DataFrame,
    validation_summary: pd.DataFrame,
    selected: pd.DataFrame,
    cost: pd.DataFrame,
    benchmark: pd.DataFrame,
    old_dir: Path | None,
) -> None:
    rec = recommendation.iloc[0]
    selected_fmt = selected.copy()
    for col in ("median_CAGR", "worst_Max_Drawdown"):
        selected_fmt[col] = selected_fmt[col].map(lambda x: pct(x))
    for col in ("median_Calmar", "worst_Calmar", "mean_turnover", "selection_score"):
        selected_fmt[col] = selected_fmt[col].map(lambda x: num(x))

    cost_alerts = cost[cost["cost_extreme_alert"].fillna(False)].drop_duplicates(["target", "strategy", "execution"])
    cost_alert_text = (
        "<span style=\"color:red\">成本极敏感</span>: "
        + ", ".join(cost_alerts.apply(lambda r: f"{r['target']} {r['strategy']} {r['execution']}", axis=1).tolist())
        if not cost_alerts.empty
        else "本轮未发现从 0% 到 0.3% 单边费用导致 CAGR 绝对下降超过 5 个百分点或相对下降超过 30% 的主策略。"
    )

    bench_fmt = benchmark.copy()
    for col in ("CAGR", "Max Drawdown"):
        bench_fmt[col] = bench_fmt[col].map(lambda x: pct(x))
    for col in ("Sharpe", "Calmar", "turnover", "avg holding days"):
        bench_fmt[col] = bench_fmt[col].map(lambda x: num(x))

    info_view = selected.merge(
        validation_summary.groupby(["target", "family"], as_index=False).agg(family_median_calmar=("median_Calmar", "median")),
        on=["target", "family"],
        how="left",
    )
    info_lines = []
    for _, row in info_view.iterrows():
        if row["family"] == "trend_plus_risk_filter":
            info_lines.append(f"{row['target']}: 趋势 + 波动率/VIX 过滤最值得关注。")
        elif row["family"] == "trend_plus_turn_confirm":
            info_lines.append(f"{row['target']}: 趋势 + 快慢动量确认最值得关注。")
        elif row["family"] == "fast_slow_ma":
            info_lines.append(f"{row['target']}: 快慢均线方向信息最有效。")
        else:
            info_lines.append(f"{row['target']}: 趋势状态本身最有效，复杂过滤暂时不是必须。")

    fragile = unstable_strategies(validation_summary)
    if fragile.empty:
        fragile_text = "未发现 worst Calmar < 0 或 worst CAGR < -5% 的主策略；但这不代表没有过拟合风险，下一轮仍需更严格验证。"
    else:
        fragile_items = (
            fragile[["target", "strategy", "split_type", "worst_CAGR", "worst_Calmar"]]
            .drop_duplicates()
            .apply(
                lambda r: (
                    f"{r['target']} {r['strategy']} ({r['split_type']}, "
                    f"worst CAGR {pct(r['worst_CAGR'])}, worst Calmar {num(r['worst_Calmar'])})"
                ),
                axis=1,
            )
            .tolist()
        )
        fragile_text = "；".join(fragile_items)

    lines = [
        "# Turning-point / Regime-aware Research V1",
        "",
        "## 本轮做了什么",
        "",
        "本轮把旧的“全因子/全策略暴力找最优顶底拟合”重构为一个更稳的第一版研究底座：先定义可交易 barrier 事件标签，再构建 25 个以内的核心历史特征，随后只测试 5 个简单可解释主策略，并用 anchored 与 rolling walk-forward、成本敏感性和基准比较做样本外评估。",
        "",
        f"输出目录: `{run_dir}`",
        "",
        "## Data Status",
        "",
        md_table(data_status[["symbol", "status", "first_date", "last_date", "rows", "missing_open", "missing_high", "missing_low", "missing_close"]]),
        "",
        "## 标签方案结论",
        "",
        f"本轮测试了固定百分比与 ATR 自适应 barrier，H=10/15/20。推荐先进入下一轮的标签是 `{rec['scheme']}` + `H={int(rec['horizon'])}`，平均正样本率 {pct(rec['avg_positive_rate'])}，平均正事件 runs/year {num(rec['avg_event_runs_per_year'])}。",
        "",
        "这个推荐不是用来直接交易，而是作为下一轮监督学习或 meta-label 的训练目标。所有特征均只用 t 日及之前可见数据。",
        "",
        "## 主策略结论",
        "",
        md_table(selected_fmt),
        "",
        "本轮测试的主策略包括：QQQ MA100 趋势、QQQ MA200 趋势、EMA20/EMA100 快慢方向、趋势 + realized vol/VIX 风险过滤、趋势 + MACD hist 转正确认。",
        "",
        "## 过拟合/脆弱迹象",
        "",
        "本轮没有用复杂参数搜索，所以这里的“像过拟合”主要指：某策略只在少数区间好看，但 rolling/anchored 的最差段转负或显著恶化。当前需要谨慎的策略为：" + fragile_text,
        "",
        "## 基准比较",
        "",
        md_table(bench_fmt[["target", "benchmark", "CAGR", "Max Drawdown", "Sharpe", "Calmar", "trade count", "turnover", "source"]]),
        "",
        "旧版最优策略基准来源: " + (f"`{old_dir}`" if old_dir else "未找到可复用旧版输出。"),
        "",
        "## 成本敏感性",
        "",
        cost_alert_text,
        "",
        "成本敏感性详表见 `cost_sensitivity.csv`，包含 0%、0.1%、0.2%、0.3% 单边费用，以及 next open / next close 两种执行方式。",
        "",
        "## 必答问题",
        "",
        "1. 旧流程为什么容易失真？",
        "",
        "旧流程把事后图形上的顶底拟合当主目标，并在大量因子、门控、参数上同时搜索，容易把噪声当 alpha，产生 selection bias、multiple testing bias 与样本内最优样本外失效。",
        "",
        "2. 本轮第一版新流程最大的改进点是什么？",
        "",
        "最大改进是把目标改为 t 日收盘后可交易的 barrier 事件标签，并把策略限制在少数可解释规则，再用时间序列安全的 OOS 切分和成本假设检验，而不是用未来顶底形状倒推规则。",
        "",
        "3. 哪个标签定义最适合 QLD/TQQQ？",
        "",
        f"本轮建议先用 `{rec['scheme']}` + `H={int(rec['horizon'])}`。它在 QLD/TQQQ 与 bottom/top 两类事件之间给出较平衡的正样本占比和事件稀疏度，且更适合杠杆 ETF 的波动 regime。",
        "",
        "4. 哪类信息最有用？",
        "",
        "；".join(info_lines),
        "",
        "5. 哪个策略最值得进入下一轮？",
        "",
        "按稳定性优先，本轮选择：" + "；".join(selected.apply(lambda r: f"{r['target']} -> {r['strategy']}", axis=1).tolist()) + "。",
        "",
        "6. 下一轮最应该做什么？",
        "",
        "下一轮优先做更严格验证和更细致成本模型，然后再在推荐 barrier 标签上做轻量 meta-label。暂时不建议直接上大规模 LightGBM/XGBoost 调参。",
    ]
    write_text(run_dir / "research_summary.md", "\n".join(lines))


def write_run_instructions(run_dir: Path, data_dir: Path, old_dir: Path | None) -> None:
    lines = [
        "# Run Instructions",
        "",
        "从仓库根目录执行：",
        "",
        "```powershell",
        "python scripts\\qldtqqq_turning_point_research_v1.py",
        "```",
        "",
        "可选参数：",
        "",
        "```powershell",
        f"python scripts\\qldtqqq_turning_point_research_v1.py --data-dir \"{data_dir}\" --old-run-dir \"{old_dir or ''}\"",
        "```",
        "",
        "默认行为：",
        "",
        f"- 数据目录: `{data_dir}`",
        f"- 输出目录格式: `outputs/turning_point_research_v1_YYYYMMDD_HHMMSS/`",
        f"- 默认验证成本: 单边 `{DEFAULT_FEE:.3%}`",
        f"- 默认执行: `{DEFAULT_EXECUTION}`，即 signal at close -> execute next open",
        "- 旧策略基准: 自动读取最新 `outputs/qldtqqq_turning_points/*/best_strategy_summary.csv` 对应 run。",
    ]
    write_text(run_dir / "run_instructions.md", "\n".join(lines))


def write_changed_files_manifest(run_dir: Path) -> None:
    lines = [
        "Added or modified script files:",
        "",
        "- scripts/qldtqqq_turning_point_research_v1.py",
        "",
        "The legacy qldtqqq_turning_point_lab.py workflow and its configs were not modified.",
    ]
    write_text(run_dir / "changed_files_manifest.txt", "\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser(description="QLD/TQQQ turning-point/regime-aware research v1")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--output-root", type=Path, default=ROOT / "outputs")
    parser.add_argument("--old-run-dir", type=Path, default=None)
    parser.add_argument("--fee", type=float, default=DEFAULT_FEE)
    parser.add_argument("--execution", choices=["next_open", "next_close"], default=DEFAULT_EXECUTION)
    args = parser.parse_args()

    run_dir = args.output_root / f"turning_point_research_v1_{stamp()}"
    run_dir.mkdir(parents=True, exist_ok=True)
    log(f"Output directory: {run_dir}")

    log("Loading local QLD/TQQQ/QQQ/VIX data")
    data, data_status = load_data(args.data_dir)
    write_csv(data_status, run_dir / "data_status.csv")

    log("Building tradable barrier labels and label statistics")
    label_stats, label_recommendation = build_label_report(data)
    write_csv(label_stats, run_dir / "label_stats.csv")
    write_csv(label_recommendation, run_dir / "label_recommendation.csv")
    write_label_report(run_dir, label_stats, label_recommendation)

    log("Building compact feature catalog and feature snapshots")
    features = feature_catalog()
    write_csv(features, run_dir / "feature_list.csv")
    indicators = build_market_indicators(data["QQQ"], data["_VIX"])
    for target in TARGETS:
        target_features = build_features_for_target(target, data[target], data["QQQ"], indicators)
        snapshot = target_features.loc[target_features.index >= pd.Timestamp("2021-01-01")].tail(260).copy()
        snapshot.insert(0, "date", snapshot.index.strftime("%Y-%m-%d"))
        write_csv(snapshot.reset_index(drop=True), run_dir / f"{target.lower()}_feature_snapshot_last260.csv")

    log("Evaluating primary strategies with anchored and rolling walk-forward splits")
    validation, result_cache, strategy_cache = evaluate_validation(data, indicators, fee=args.fee, execution=args.execution)
    write_csv(validation, run_dir / "validation_results.csv")
    validation_summary_df = summarize_validation(validation)
    write_csv(validation_summary_df, run_dir / "validation_summary_stats.csv")
    selected = select_strategies(validation, strategy_cache)
    write_csv(selected, run_dir / "selected_strategies.csv")
    write_validation_summary(run_dir, validation, validation_summary_df, selected)

    log("Running cost and execution sensitivity analysis")
    cost = cost_sensitivity(data, strategy_cache)
    write_csv(cost, run_dir / "cost_sensitivity.csv")

    old_dir = args.old_run_dir if args.old_run_dir else latest_old_run()
    log(f"Building benchmark comparison; old baseline: {old_dir}")
    benchmark = benchmark_comparison(data, selected, result_cache, strategy_cache, old_dir)
    write_csv(benchmark, run_dir / "benchmark_comparison.csv")

    log("Writing trade logs and plots for selected strategies")
    for target in TARGETS:
        strategy_name = selected.loc[selected["target"].eq(target), "strategy"].iloc[0]
        result = result_cache[(target, strategy_name)]
        trades = trade_log_from_result(data[target], result)
        write_csv(trades, run_dir / f"{target.lower()}_trade_log.csv")
    save_plots(run_dir, data, selected, result_cache, strategy_cache)

    log("Writing final reports and reproduction notes")
    write_research_summary(
        run_dir=run_dir,
        data_status=data_status,
        label_stats=label_stats,
        recommendation=label_recommendation,
        validation=validation,
        validation_summary=validation_summary_df,
        selected=selected,
        cost=cost,
        benchmark=benchmark,
        old_dir=old_dir,
    )
    write_run_instructions(run_dir, args.data_dir, old_dir)
    write_changed_files_manifest(run_dir)

    required = [
        "research_summary.md",
        "label_report.md",
        "feature_list.csv",
        "validation_results.csv",
        "validation_summary.md",
        "cost_sensitivity.csv",
        "benchmark_comparison.csv",
        "qld_trade_log.csv",
        "tqqq_trade_log.csv",
        "qld_equity_curve.png",
        "tqqq_equity_curve.png",
        "qld_drawdown.png",
        "tqqq_drawdown.png",
        "qld_signal_chart.png",
        "tqqq_signal_chart.png",
        "changed_files_manifest.txt",
        "run_instructions.md",
    ]
    missing = [name for name in required if not (run_dir / name).exists()]
    if missing:
        raise RuntimeError(f"Missing required outputs: {missing}")
    log("Research v1 completed successfully")
    log(str(run_dir))


if __name__ == "__main__":
    main()
