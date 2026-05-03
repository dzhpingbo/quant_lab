"""
Generalized 588200 buy/sell strategy research.

This script treats the stock/ETF universe as a research sample pool. The final
signal is still a 588200 buy/empty signal, but strategy selection is based on
cross-asset performance over similar ETFs plus breadth features from the 588200
theme stock pool.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

from src.strategies.etf_588200 import (
    GeneralizedStrategySpec as StrategySpec,
    build_generalized_indicator_cache as build_indicator_cache,
    generalized_signal as generate_desired_position,
    generalized_signal_from_indicators as generate_desired_position_from_indicators,
    generalized_specs_grid as specs_grid,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ASTOCK_ROOT = PROJECT_ROOT / "data" / "external" / "legacy_quant" / "AStock"
TARGET_CODE = "588200.SS"

CODES_588200 = [
    "688981", "688041", "688256", "688008", "688012", "688072", "688521", "688347",
    "688126", "688110", "688498", "688525", "688120", "688002", "688249", "688361",
    "688099", "688313", "688396", "688385", "688608", "688213", "688047", "688019",
    "688037", "688220", "688234", "688200", "688052", "688702", "688018", "688082",
    "688536", "688582", "688484", "688141", "688728", "688409", "688279", "688709",
    "688172", "688798", "688153", "688146", "688332", "688352", "688432", "688584",
    "688449", "688605",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Research generalized 588200 timing strategies.")
    parser.add_argument("--astock-root", default=str(DEFAULT_ASTOCK_ROOT), help="AStock data root.")
    parser.add_argument("--start", default="2022-10-26", help="Research start date.")
    parser.add_argument("--train-end", default="2024-12-31", help="Cross-asset training end date.")
    parser.add_argument("--end", default="2026-04-08", help="Research end date.")
    parser.add_argument("--target", default=TARGET_CODE, help="Target ETF code.")
    parser.add_argument("--max-similar-etfs", type=int, default=18, help="Max ETF research assets.")
    parser.add_argument("--min-overlap", type=int, default=180, help="Min target/train overlap days.")
    parser.add_argument("--min-corr", type=float, default=0.45, help="Min train correlation to target.")
    parser.add_argument("--cost-rate", type=float, default=0.001, help="Single-side cost rate.")
    parser.add_argument("--risk-free", type=float, default=0.02, help="Annual risk-free rate.")
    parser.add_argument(
        "--grid",
        choices=["compact", "full"],
        default="compact",
        help="compact is a fast robust grid; full expands the parameter search for long runs.",
    )
    parser.add_argument(
        "--run-dir",
        default=None,
        help="Existing or new run directory. Use with --resume to continue a checkpointed run.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from strategy_summary_checkpoint.csv in --run-dir if present.",
    )
    parser.add_argument(
        "--checkpoint-every",
        type=int,
        default=10,
        help="Write checkpoint after every N newly evaluated specs. 0 disables intermediate checkpoints.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(PROJECT_ROOT / "outputs" / "588200_generalized_strategy"),
        help="Output directory.",
    )
    return parser.parse_args()


def load_price_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df.columns = [str(c).strip().lower() for c in df.columns]
    date_col = next((c for c in df.columns if c in {"date", "datetime"}), df.columns[0])
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.dropna(subset=[date_col]).set_index(date_col).sort_index()
    df = df[~df.index.duplicated(keep="last")]
    for col in ["open", "high", "low", "close", "volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "open" not in df.columns and "close" in df.columns:
        df["open"] = df["close"]
    if "volume" not in df.columns:
        df["volume"] = np.nan
    return df[["open", "close", "volume"]].copy()


def normalize_code(path: Path) -> str:
    stem = path.stem.upper()
    return stem.replace(".SH", ".SS")


def collect_etf_paths(astock_root: Path) -> Dict[str, Path]:
    paths: Dict[str, Path] = {}
    for root in [astock_root / "ETF" / "yf_etf_data", astock_root / "ETF"]:
        if not root.exists():
            continue
        for path in root.glob("*.csv"):
            code = normalize_code(path)
            if code not in paths or "yf_etf_data" in str(path):
                paths[code] = path
    return paths


def load_etfs(paths: Dict[str, Path], min_rows: int = 300) -> Dict[str, pd.DataFrame]:
    etfs: Dict[str, pd.DataFrame] = {}
    for code, path in sorted(paths.items()):
        try:
            df = load_price_csv(path)
        except Exception:
            continue
        df = df[df["open"].notna() & df["open"].gt(0) & df["close"].notna() & df["close"].gt(0)]
        if len(df) >= min_rows:
            etfs[code] = df
    return etfs


def load_stock_pool(astock_root: Path) -> Tuple[pd.DataFrame, pd.DataFrame, List[str]]:
    kc_dir = astock_root / "yf_data" / "KC"
    closes: Dict[str, pd.Series] = {}
    volumes: Dict[str, pd.Series] = {}
    missing: List[str] = []
    for code in CODES_588200:
        candidates = [kc_dir / f"{code}.SS.csv", kc_dir / f"{code}.SH.csv", kc_dir / f"{code}.csv"]
        path = next((p for p in candidates if p.exists()), None)
        if path is None:
            missing.append(code)
            continue
        df = load_price_csv(path)
        if df["close"].notna().sum() < 180:
            missing.append(code)
            continue
        closes[code] = df["close"]
        volumes[code] = df["volume"]
    if not closes:
        raise RuntimeError(f"No stock pool data loaded from {kc_dir}")
    close = pd.DataFrame(closes).sort_index()
    volume = pd.DataFrame(volumes).reindex(close.index)
    return close, volume, missing


def build_breadth_features(close: pd.DataFrame, volume: pd.DataFrame) -> pd.DataFrame:
    ret20 = close.pct_change(20, fill_method=None)
    ret60 = close.pct_change(60, fill_method=None)
    amount = close * volume
    valid = close.notna()
    min_count = 10

    features = pd.DataFrame(index=close.index)
    count = valid.sum(axis=1).where(lambda s: s >= min_count)
    features["breadth_ma20"] = ((close > close.rolling(20).mean()) & valid).sum(axis=1) / count
    features["breadth_ma60"] = ((close > close.rolling(60).mean()) & valid).sum(axis=1) / count
    features["breadth_mom20"] = (ret20 > 0).sum(axis=1) / count
    features["breadth_mom60"] = (ret60 > 0).sum(axis=1) / count
    features["pool_ret20_median"] = ret20.median(axis=1)
    features["pool_ret60_median"] = ret60.median(axis=1)
    features["pool_disp20"] = ret20.std(axis=1)
    features["pool_liquidity20"] = np.log(amount.where(amount > 0)).rolling(20).mean().median(axis=1)
    features["pool_count"] = count
    return features


def select_similar_etfs(
    etfs: Dict[str, pd.DataFrame],
    target_code: str,
    start: pd.Timestamp,
    train_end: pd.Timestamp,
    min_overlap: int,
    min_corr: float,
    max_assets: int,
) -> pd.DataFrame:
    if target_code not in etfs:
        raise RuntimeError(f"Target ETF {target_code} not found in ETF data.")
    target_ret = etfs[target_code]["close"].pct_change(fill_method=None).loc[start:train_end]

    rows = []
    for code, df in etfs.items():
        if code == target_code:
            continue
        ret = df["close"].pct_change(fill_method=None).loc[start:train_end]
        common = pd.concat([target_ret.rename("target"), ret.rename("asset")], axis=1).dropna()
        if len(common) < min_overlap:
            continue
        corr = common["target"].corr(common["asset"])
        if pd.isna(corr) or corr < min_corr:
            continue
        vol_diff = abs(common["asset"].std() - common["target"].std())
        rows.append({
            "code": code,
            "corr_to_588200_train": corr,
            "overlap_days": len(common),
            "vol_diff": vol_diff,
            "first_date": df.index.min().date().isoformat(),
            "last_date": df.index.max().date().isoformat(),
        })
    selected = pd.DataFrame(rows)
    if selected.empty:
        raise RuntimeError("No similar ETFs selected; lower --min-corr or --min-overlap.")
    selected = selected.sort_values(["corr_to_588200_train", "overlap_days"], ascending=[False, False])
    return selected.head(max_assets).reset_index(drop=True)


def backtest_signal(asset: pd.DataFrame, desired: pd.Series, cost_rate: float) -> Tuple[pd.Series, pd.Series, pd.Series]:
    idx = asset.index
    open_px = asset["open"].reindex(idx)
    open_ret = open_px.shift(-1).div(open_px).sub(1).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    position = desired.shift(1).reindex(idx).fillna(0.0)
    turnover = position.diff().abs().fillna(position.abs())
    returns = position * open_ret - turnover * cost_rate
    nav = (1 + returns).cumprod()
    return nav, returns, position


def compute_metrics(returns: pd.Series, start: pd.Timestamp, end: pd.Timestamp, risk_free: float) -> Dict[str, float]:
    r = returns.loc[start:end].dropna()
    if len(r) < 60:
        return {
            "total_return": np.nan,
            "annual_return": np.nan,
            "annual_vol": np.nan,
            "sharpe": np.nan,
            "max_drawdown": np.nan,
            "calmar": np.nan,
            "win_rate": np.nan,
            "exposure": np.nan,
            "days": float(len(r)),
        }
    nav = (1 + r).cumprod()
    years = len(r) / 252
    total_return = nav.iloc[-1] - 1
    annual_return = nav.iloc[-1] ** (1 / years) - 1
    annual_vol = r.std() * np.sqrt(252)
    sharpe = (annual_return - risk_free) / annual_vol if annual_vol > 1e-12 else np.nan
    drawdown = nav / nav.cummax() - 1
    max_drawdown = drawdown.min()
    calmar = annual_return / abs(max_drawdown) if max_drawdown < 0 else np.nan
    return {
        "total_return": float(total_return),
        "annual_return": float(annual_return),
        "annual_vol": float(annual_vol),
        "sharpe": float(sharpe),
        "max_drawdown": float(max_drawdown),
        "calmar": float(calmar),
        "win_rate": float((r > 0).mean()),
        "exposure": float((r != 0).mean()),
        "days": float(len(r)),
    }


def buy_hold_returns(asset: pd.DataFrame) -> pd.Series:
    open_px = asset["open"]
    return open_px.shift(-1).div(open_px).sub(1).replace([np.inf, -np.inf], np.nan).fillna(0.0)


def flatten(prefix: str, metrics: Dict[str, float]) -> Dict[str, float]:
    return {f"{prefix}_{key}": value for key, value in metrics.items()}


def train_score(row: pd.Series) -> float:
    sharpe = row.get("pool_train_median_sharpe", np.nan)
    positive = row.get("pool_train_positive_ratio", np.nan)
    dd = row.get("pool_train_median_max_drawdown", np.nan)
    if pd.isna(sharpe):
        return -999.0
    score = float(sharpe)
    if pd.notna(positive):
        score += 0.5 * (positive - 0.5)
    if pd.notna(dd) and dd < -0.40:
        score -= (abs(dd) - 0.40)
    return score


def aggregate_pool(rows: List[Dict[str, object]], prefix: str) -> Dict[str, float]:
    df = pd.DataFrame(rows)
    out: Dict[str, float] = {}
    for col in ["sharpe", "annual_return", "max_drawdown", "calmar", "exposure"]:
        series = pd.to_numeric(df[col], errors="coerce")
        out[f"{prefix}_median_{col}"] = float(series.median()) if series.notna().any() else np.nan
        out[f"{prefix}_mean_{col}"] = float(series.mean()) if series.notna().any() else np.nan
    out[f"{prefix}_positive_ratio"] = float((pd.to_numeric(df["annual_return"], errors="coerce") > 0).mean()) if not df.empty else np.nan
    out[f"{prefix}_asset_count"] = float(len(df))
    return out


def evaluate_spec_on_assets(
    spec: StrategySpec,
    asset_codes: Iterable[str],
    etfs: Dict[str, pd.DataFrame],
    breadth: pd.DataFrame,
    train_start: pd.Timestamp,
    train_end: pd.Timestamp,
    test_start: pd.Timestamp,
    test_end: pd.Timestamp,
    risk_free: float,
    cost_rate: float,
    indicator_cache: Optional[Dict[str, pd.DataFrame]] = None,
) -> Dict[str, float]:
    train_rows = []
    test_rows = []
    for code in asset_codes:
        asset = etfs[code].loc[train_start:test_end].copy()
        if indicator_cache is not None and code in indicator_cache:
            desired = generate_desired_position_from_indicators(indicator_cache[code], spec)
        else:
            desired = generate_desired_position(asset, breadth, spec)
        _nav, returns, _position = backtest_signal(asset, desired, cost_rate)
        train_metrics = compute_metrics(returns, train_start, train_end, risk_free)
        test_metrics = compute_metrics(returns, test_start, test_end, risk_free)
        train_metrics["code"] = code
        test_metrics["code"] = code
        train_rows.append(train_metrics)
        test_rows.append(test_metrics)
    out = {}
    out.update(aggregate_pool(train_rows, "pool_train"))
    out.update(aggregate_pool(test_rows, "pool_test"))
    return out


def markdown_table(df: pd.DataFrame) -> str:
    headers = list(df.columns)
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for _, row in df.iterrows():
        vals = []
        for col in headers:
            value = row[col]
            if isinstance(value, (float, np.floating)):
                vals.append(f"{value:.4f}")
            else:
                vals.append(str(value))
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines)


def pct(value: float) -> str:
    return "nan" if pd.isna(value) else f"{value * 100:.2f}%"


def num(value: float) -> str:
    return "nan" if pd.isna(value) else f"{value:.3f}"


def strategy_rule_details(best: pd.Series) -> str:
    family = str(best["family"])
    ma_window = int(best["ma_window"])
    breadth_buy = float(best["breadth_buy"])
    breadth_sell = float(best["breadth_sell"])
    mom_window = int(best["mom_window"])
    vol_window = int(best["vol_window"])
    vol_max = float(best["vol_max"])
    rsi_buy = float(best["rsi_buy"])
    rsi_exit = float(best["rsi_exit"])
    require_pool_mom = bool(best["require_pool_mom"])

    common = f"""
## 指标含义

- `strategy`：策略唯一名称，把策略族和参数拼在一起，便于复现。
- `family`：策略族。当前为 `{family}`，表示用动量和波动率过滤做买卖择时。
- `mom{mom_window}`：588200 自身的 {mom_window} 日价格动量，计算为“今日收盘价 / {mom_window} 个交易日前收盘价 - 1”。
- `ma{ma_window}`：在当前 `{family}` 策略族里，它不是 588200 自身价格均线，而是成分股池广度的均线窗口。
- `breadth_ma60`：588200 成分股池中，收盘价站上各自 60 日均线的股票比例。
- `bb{int(breadth_buy * 100)}`：广度买入阈值，`breadth_ma60 >= {breadth_buy:.0%}` 才允许买入。
- `bs{int(breadth_sell * 100)}`：广度卖出阈值，`breadth_ma60 <= {breadth_sell:.0%}` 触发卖出或继续空仓。
- `vol{vol_window}`：588200 最近 {vol_window} 日收益率波动率。
- `vp{int(vol_max * 100)}`：波动率分位上限，买入时要求最近 {vol_window} 日波动率不高于过去一年分位的 {vol_max:.0%}。
- `poolmom`：是否额外要求成分股池 20 日收益中位数大于 0；当前为 `{require_pool_mom}`。
- `RSI`：只给 `pullback_trend` 策略族使用；当前 `{family}` 策略族不使用 RSI。
"""
    if family == "momentum_vol":
        pool_mom_note = "\n4. 成分股池 20 日收益中位数大于 0。" if require_pool_mom else ""
        return common + f"""
## 买点规则

在每天收盘后检查以下条件，全部满足时，下一交易日开盘买入或继续持有 588200：

1. 588200 的 {mom_window} 日价格动量大于 0，也就是当前收盘价高于 {mom_window} 个交易日前收盘价。
2. 成分股池 MA60 广度不低于 {breadth_buy:.0%}，也就是至少 {breadth_buy:.0%} 的成分股站上各自 60 日均线。
3. 588200 最近 {vol_window} 日波动率分位不高于 {vol_max:.0%}，避免在极端波动失控时追入。{pool_mom_note}

## 卖点规则

只要出现以下任一条件，每天收盘后生成空仓信号，下一交易日开盘卖出或继续空仓：

1. 588200 的 {mom_window} 日价格动量小于等于 0。
2. 成分股池 MA60 广度跌到 {breadth_sell:.0%} 或更低。
3. 588200 最近 {vol_window} 日波动率分位高于 {min(vol_max + 0.10, 0.98):.0%}。

## 容易误解的地方

这不是“588200 收盘价上穿自身 60 日均线就买、下穿就卖”。当前策略真正用到的是 588200 的 {mom_window} 日动量、成分股池 MA60 广度和 588200 的 {vol_window} 日波动率分位。
"""
    if family == "trend_breadth":
        pool_mom_note = "\n3. 成分股池 20 日收益中位数大于 0。" if require_pool_mom else ""
        return common + f"""
## 买点规则

在每天收盘后检查以下条件，全部满足时，下一交易日开盘买入或继续持有 588200：

1. 588200 收盘价高于自身 MA{ma_window}。
2. 成分股池广度不低于 {breadth_buy:.0%}。{pool_mom_note}

## 卖点规则

只要出现以下任一条件，下一交易日开盘卖出或继续空仓：

1. 588200 收盘价不再高于自身 MA{ma_window}。
2. 成分股池广度跌到 {breadth_sell:.0%} 或更低。
"""
    if family == "pullback_trend":
        return common + f"""
## 买点规则

在每天收盘后检查以下条件，全部满足时，下一交易日开盘买入或继续持有 588200：

1. 588200 收盘价高于自身 MA{ma_window}，说明大趋势没有走坏。
2. 成分股池广度不低于 {breadth_buy:.0%}。
3. 588200 的 RSI14 不高于 {rsi_buy:.0f}，表示在上升趋势中出现回调。

## 卖点规则

只要出现以下任一条件，下一交易日开盘卖出或继续空仓：

1. 588200 收盘价不再高于自身 MA{ma_window}。
2. 成分股池广度跌到 {breadth_sell:.0%} 或更低。
3. RSI14 升到 {rsi_exit:.0f} 或更高，表示回调修复后止盈退出。
"""
    return common + "\n## 买点和卖点\n\n未知策略族，需补充规则说明。\n"


def write_checkpoint(rows: List[Dict[str, object]], path: Path) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False, encoding="utf-8-sig")


def load_checkpoint(path: Path) -> Tuple[List[Dict[str, object]], set[str]]:
    if not path.exists():
        return [], set()
    checkpoint = pd.read_csv(path)
    if checkpoint.empty or "strategy" not in checkpoint.columns:
        return [], set()
    rows = checkpoint.to_dict("records")
    completed = set(checkpoint["strategy"].astype(str))
    return rows, completed


def latest_trade_plan(target_asset: pd.DataFrame, breadth: pd.DataFrame, spec: StrategySpec) -> Dict[str, object]:
    desired = generate_desired_position(target_asset, breadth, spec)
    last_date = desired.dropna().index[-1]
    last_signal = bool(desired.loc[last_date])
    return {
        "signal_date": last_date.date().isoformat(),
        "next_action": "BUY_OR_HOLD_588200" if last_signal else "EMPTY_OR_SELL_588200",
        "desired_position": int(last_signal),
        "close": float(target_asset.loc[last_date, "close"]),
        "breadth_ma60": float(breadth["breadth_ma60"].reindex([last_date]).ffill().iloc[0]),
        "pool_ret20_median": float(breadth["pool_ret20_median"].reindex([last_date]).ffill().iloc[0]),
    }


def write_report(
    path: Path,
    best: pd.Series,
    selected_etfs: pd.DataFrame,
    target_metrics: Dict[str, Dict[str, float]],
    target_hold: Dict[str, Dict[str, float]],
    latest: Dict[str, object],
    stock_missing: List[str],
    output_paths: Dict[str, Path],
    top_table: pd.DataFrame,
    args: argparse.Namespace,
) -> None:
    test_start = (pd.to_datetime(args.train_end) + pd.Timedelta(days=1)).date()
    missing_text = ", ".join(stock_missing) if stock_missing else "无"
    checkpoint_text = output_paths.get("checkpoint")
    family = str(best["family"])
    ma_label = "股票池广度均线窗口" if family == "momentum_vol" else "价格趋势均线"
    rule_note = (
        "注意：本次最优策略属于 `momentum_vol`，其中 `ma60` 不是 588200 自身价格的 60 日均线买卖规则，"
        "而是股票池广度使用 MA60 作为判断窗口。实际买卖由 60 日价格动量、股票池 MA60 广度和 20 日波动率分位共同决定。"
        if family == "momentum_vol"
        else "本策略族会直接使用价格均线作为趋势过滤条件。"
    )
    report = f"""# 588200 泛化买卖策略研究报告

生成时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

## 研究口径

本报告不把 588200 成分股当成最终交易组合；最终交易对象仍然是 `{args.target}`。ETF 样本池用于跨资产训练和选择参数，588200 成分股池只用于生成主题广度指标。

- 目标资产：`{args.target}`
- 网格模式：`{args.grid}`
- 训练期：{args.start} 至 {args.train_end}
- 样本外：{test_start} 至 {args.end}
- 同类 ETF 训练样本数：{len(selected_etfs)}
- 成分股池缺失代码：{missing_text}
- 成本假设：单边换手成本 {args.cost_rate:.4%}
- 排名规则：只用同类 ETF 训练期表现打分，再检查 588200 样本外表现，避免直接用 588200 样本外挑参数。

## 当前推荐策略

推荐策略：`{best['strategy']}`

- 策略族：`{best['family']}`
- {ma_label}：MA{int(best['ma_window'])}
- 广度买入阈值：{best['breadth_buy']:.0%}
- 广度卖出阈值：{best['breadth_sell']:.0%}
- 动量窗口：{int(best['mom_window'])}
- 波动窗口：{int(best['vol_window'])}
- 波动率上限分位：{best['vol_max']:.0%}
- RSI 买入/退出：{best['rsi_buy']:.0f} / {best['rsi_exit']:.0f}，仅 `pullback_trend` 策略族使用
- 是否要求股票池 20 日收益中位数为正：{bool(best['require_pool_mom'])}

{rule_note}

执行口径：每日收盘后生成信号，下一个交易日开盘执行。持仓只有两种：满仓 588200 或空仓。

{strategy_rule_details(best)}

## 588200 回测结果

| 区间 | 策略年化 | 策略夏普 | 策略最大回撤 | 买入持有年化 | 买入持有夏普 | 买入持有最大回撤 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 训练期 | {pct(target_metrics['train']['annual_return'])} | {num(target_metrics['train']['sharpe'])} | {pct(target_metrics['train']['max_drawdown'])} | {pct(target_hold['train']['annual_return'])} | {num(target_hold['train']['sharpe'])} | {pct(target_hold['train']['max_drawdown'])} |
| 样本外 | {pct(target_metrics['test']['annual_return'])} | {num(target_metrics['test']['sharpe'])} | {pct(target_metrics['test']['max_drawdown'])} | {pct(target_hold['test']['annual_return'])} | {num(target_hold['test']['sharpe'])} | {pct(target_hold['test']['max_drawdown'])} |
| 全样本 | {pct(target_metrics['full']['annual_return'])} | {num(target_metrics['full']['sharpe'])} | {pct(target_metrics['full']['max_drawdown'])} | {pct(target_hold['full']['annual_return'])} | {num(target_hold['full']['sharpe'])} | {pct(target_hold['full']['max_drawdown'])} |

## 跨 ETF 泛化结果

- 训练池中位夏普：{num(best['pool_train_median_sharpe'])}
- 训练池正收益比例：{pct(best['pool_train_positive_ratio'])}
- 样本外中位夏普：{num(best['pool_test_median_sharpe'])}
- 样本外正收益比例：{pct(best['pool_test_positive_ratio'])}
- 样本外中位最大回撤：{pct(best['pool_test_median_max_drawdown'])}

## 最新信号

- 信号日期：{latest['signal_date']}
- 收盘价：{latest['close']:.4f}
- 股票池 MA60 广度：{latest['breadth_ma60']:.2%}
- 股票池 20 日收益中位数：{latest['pool_ret20_median']:.2%}
- 下一交易日计划：`{latest['next_action']}`

## 同类 ETF 样本池

{markdown_table(selected_etfs.head(30))}

## 参数排名前十

{markdown_table(top_table)}

## 输出文件

- 策略参数排名：`{output_paths['summary']}`
- 同类 ETF 样本池：`{output_paths['universe']}`
- 588200 净值和信号：`{output_paths['target_signal']}`
- 最优配置：`{output_paths['config']}`
- 断点文件：`{checkpoint_text}`
- 本报告：`{path}`

## 使用方法

在项目根目录运行全量网格：

```powershell
python scripts\\research_588200_generalized_strategy.py --grid full --start {args.start} --train-end {args.train_end} --end {args.end}
```

如果长跑中断，用同一个运行目录恢复：

```powershell
python scripts\\research_588200_generalized_strategy.py --grid full --resume --run-dir "{path.parent}"
```

实盘或模拟盘使用：

1. 每个交易日收盘后运行脚本，或至少在准备交易前运行一次。
2. 看最新报告里的“下一交易日计划”：`BUY_OR_HOLD_588200` 表示下一个交易日开盘买入或继续持有 588200；`EMPTY_OR_SELL_588200` 表示下一个交易日开盘卖出或继续空仓。
3. 不根据成分股 TopN 下单；成分股只用于生成广度指标。

## 限制

- 当前成分股池仍是 2025Q4 静态池，不是历史 point-in-time 成分池。
- 同类 ETF 样本池用训练期与 588200 的相关性筛选，属于数据驱动近邻池，不等同于官方基金分类。
- 回测没有完整模拟涨跌停、停牌、滑点、盘口深度和 ETF 折溢价。
- 结果用于研究，不构成投资建议。
"""
    path.write_text(report, encoding="utf-8")


def main() -> None:
    args = parse_args()
    astock_root = Path(args.astock_root)
    output_root = Path(args.output_dir)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = Path(args.run_dir) if args.run_dir else output_root / timestamp
    run_dir.mkdir(parents=True, exist_ok=True)

    start = pd.to_datetime(args.start)
    train_end = pd.to_datetime(args.train_end)
    test_start = train_end + pd.Timedelta(days=1)
    end = pd.to_datetime(args.end)

    print("Loading ETF universe...")
    etfs = load_etfs(collect_etf_paths(astock_root), min_rows=250)
    print(f"ETF series loaded: {len(etfs)}")

    print("Loading 588200 stock breadth pool...")
    stock_close, stock_volume, stock_missing = load_stock_pool(astock_root)
    breadth = build_breadth_features(stock_close, stock_volume)

    selected = select_similar_etfs(
        etfs=etfs,
        target_code=args.target,
        start=start,
        train_end=train_end,
        min_overlap=args.min_overlap,
        min_corr=args.min_corr,
        max_assets=args.max_similar_etfs,
    )
    selected_codes = selected["code"].tolist()
    print(f"Similar ETF research pool: {len(selected_codes)}")

    specs = specs_grid(args.grid)
    print(f"Strategy specs in {args.grid} grid: {len(specs)}")
    target_asset_for_scoring = etfs[args.target].loc[start:end].copy()
    cache_assets = {code: etfs[code].loc[start:end].copy() for code in selected_codes}
    cache_assets[args.target] = target_asset_for_scoring
    print("Building shared indicator cache...")
    indicator_cache = build_indicator_cache(cache_assets, breadth, specs)

    checkpoint_path = run_dir / "strategy_summary_checkpoint.csv"
    rows, completed = load_checkpoint(checkpoint_path) if args.resume else ([], set())
    if completed:
        print(f"Resuming from checkpoint: {len(completed)} completed specs loaded.")
    remaining_specs = [spec for spec in specs if spec.name not in completed]
    target_asset_for_scoring = etfs[args.target].loc[start:end].copy()
    print(f"Running {len(remaining_specs)} remaining strategy specs across {len(selected_codes)} ETFs...")
    for evaluated_count, spec in enumerate(remaining_specs, start=1):
        agg = evaluate_spec_on_assets(
            spec=spec,
            asset_codes=selected_codes,
            etfs=etfs,
            breadth=breadth,
            train_start=start,
            train_end=train_end,
            test_start=test_start,
            test_end=end,
            risk_free=args.risk_free,
            cost_rate=args.cost_rate,
            indicator_cache=indicator_cache,
        )
        row = {
            "strategy": spec.name,
            "family": spec.family,
            "ma_window": spec.ma_window,
            "breadth_buy": spec.breadth_buy,
            "breadth_sell": spec.breadth_sell,
            "mom_window": spec.mom_window,
            "vol_window": spec.vol_window,
            "vol_max": spec.vol_max,
            "rsi_buy": spec.rsi_buy,
            "rsi_exit": spec.rsi_exit,
            "require_pool_mom": spec.require_pool_mom,
        }
        row.update(agg)
        target_desired_for_scoring = generate_desired_position_from_indicators(indicator_cache[args.target], spec)
        _target_nav_for_scoring, target_returns_for_scoring, _target_position_for_scoring = backtest_signal(
            target_asset_for_scoring,
            target_desired_for_scoring,
            args.cost_rate,
        )
        row.update(flatten("target_train", compute_metrics(target_returns_for_scoring, start, train_end, args.risk_free)))
        row.update(flatten("target_test", compute_metrics(target_returns_for_scoring, test_start, end, args.risk_free)))
        row.update(flatten("target_full", compute_metrics(target_returns_for_scoring, start, end, args.risk_free)))
        rows.append(row)
        if args.checkpoint_every > 0 and evaluated_count % args.checkpoint_every == 0:
            write_checkpoint(rows, checkpoint_path)
            print(f"Checkpoint saved: {len(rows)}/{len(specs)} specs -> {checkpoint_path}")
    write_checkpoint(rows, checkpoint_path)

    summary = pd.DataFrame(rows)
    summary["train_score"] = summary.apply(train_score, axis=1)
    summary = summary.sort_values(["train_score", "pool_test_median_sharpe"], ascending=False).reset_index(drop=True)
    best = summary.iloc[0]
    best_spec = next(spec for spec in specs if spec.name == best["strategy"])

    target_asset = etfs[args.target].loc[start:end].copy()
    target_desired = generate_desired_position_from_indicators(indicator_cache[args.target], best_spec)
    target_nav, target_returns, target_position = backtest_signal(target_asset, target_desired, args.cost_rate)
    hold_returns = buy_hold_returns(target_asset)
    target_metrics = {
        "train": compute_metrics(target_returns, start, train_end, args.risk_free),
        "test": compute_metrics(target_returns, test_start, end, args.risk_free),
        "full": compute_metrics(target_returns, start, end, args.risk_free),
    }
    hold_metrics = {
        "train": compute_metrics(hold_returns, start, train_end, args.risk_free),
        "test": compute_metrics(hold_returns, test_start, end, args.risk_free),
        "full": compute_metrics(hold_returns, start, end, args.risk_free),
    }
    latest = latest_trade_plan(target_asset, breadth, best_spec)

    summary_path = run_dir / f"strategy_summary_{timestamp}.csv"
    universe_path = run_dir / f"research_universe_{timestamp}.csv"
    signal_path = run_dir / f"target_588200_signal_{timestamp}.csv"
    config_path = run_dir / f"best_config_{timestamp}.json"
    report_path = run_dir / f"report_{timestamp}.md"

    summary.to_csv(summary_path, index=False, encoding="utf-8-sig")
    selected.to_csv(universe_path, index=False, encoding="utf-8-sig")
    target_out = pd.DataFrame({
        "open": target_asset["open"],
        "close": target_asset["close"],
        "desired_after_close": target_desired,
        "position_next_open": target_position,
        "strategy_nav": target_nav,
        "buy_hold_nav": (1 + hold_returns).cumprod(),
        "breadth_ma60": breadth["breadth_ma60"].reindex(target_asset.index).ffill(),
        "pool_ret20_median": breadth["pool_ret20_median"].reindex(target_asset.index).ffill(),
    })
    target_out.to_csv(signal_path, encoding="utf-8-sig")

    config = {
        "target": args.target,
        "strategy": best_spec.name,
        "strategy_params": best_spec.__dict__,
        "latest_signal": latest,
        "grid": args.grid,
        "candidate_count": int(len(specs)),
        "run_dir": str(run_dir),
        "checkpoint": str(checkpoint_path),
        "start": args.start,
        "train_end": args.train_end,
        "end": args.end,
        "cost_rate": args.cost_rate,
        "research_etfs": selected_codes,
    }
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")

    top_table = summary.head(10)[[
        "strategy",
        "pool_train_median_sharpe",
        "pool_train_positive_ratio",
        "pool_test_median_sharpe",
        "pool_test_positive_ratio",
        "pool_test_median_max_drawdown",
        "target_test_annual_return",
        "target_test_sharpe",
        "target_test_max_drawdown",
    ]]
    write_report(
        path=report_path,
        best=best,
        selected_etfs=selected,
        target_metrics=target_metrics,
        target_hold=hold_metrics,
        latest=latest,
        stock_missing=stock_missing,
        output_paths={
            "summary": summary_path,
            "universe": universe_path,
            "target_signal": signal_path,
            "config": config_path,
            "checkpoint": checkpoint_path,
        },
        top_table=top_table,
        args=args,
    )

    print("\nBest generalized strategy")
    print("-------------------------")
    print(f"grid: {args.grid}, specs evaluated: {len(summary)}")
    print(f"strategy: {best_spec.name}")
    print(f"ETF pool train median Sharpe: {best['pool_train_median_sharpe']:.3f}")
    print(f"ETF pool test median Sharpe: {best['pool_test_median_sharpe']:.3f}")
    print(f"588200 test annual return: {target_metrics['test']['annual_return'] * 100:.2f}%")
    print(f"588200 test Sharpe: {target_metrics['test']['sharpe']:.3f}")
    print(f"588200 test max drawdown: {target_metrics['test']['max_drawdown'] * 100:.2f}%")
    print(f"Latest plan: {latest['next_action']} as of {latest['signal_date']}")
    print(f"report: {report_path}")


if __name__ == "__main__":
    main()
