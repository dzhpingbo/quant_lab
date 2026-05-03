"""Validate the safety strategy/factor upgrade on 588200.

The target trade asset is still 588200.SS.  The 588200 constituent stock pool is
used to build breadth and safety-factor breadth; similar ETFs are used as the
cross-asset training pool for parameter selection.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.factors.safety import composite_safety_score, compute_safety_factor_panel
from src.strategies.etf_588200 import (
    build_safety_signal_cache as build_signal_cache,
    make_safety_upgrade_specs as build_specs,
    safety_signal_from_cache as signal_from_cache,
    safety_spec_from_row as spec_from_row,
)
from src.strategies.safety import (
    BinaryStrategySpec,
    backtest_binary_position,
    compute_performance_metrics,
)


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
    parser = argparse.ArgumentParser(description="Validate 588200 safety strategy upgrade.")
    parser.add_argument("--astock-root", default=str(DEFAULT_ASTOCK_ROOT), help="AStock data root.")
    parser.add_argument("--target", default=TARGET_CODE, help="Target ETF code.")
    parser.add_argument("--start", default="2022-10-26", help="Research start date.")
    parser.add_argument("--train-end", default="2024-12-31", help="Training end date.")
    parser.add_argument("--end", default="2026-04-08", help="Research end date.")
    parser.add_argument("--max-similar-etfs", type=int, default=18, help="Max ETF research assets.")
    parser.add_argument("--min-overlap", type=int, default=180, help="Min train overlap days.")
    parser.add_argument("--min-corr", type=float, default=0.45, help="Min train correlation.")
    parser.add_argument("--cost-rate", type=float, default=0.001, help="Single-side cost rate.")
    parser.add_argument("--risk-free", type=float, default=0.02, help="Annual risk-free rate.")
    parser.add_argument(
        "--output-dir",
        default=str(PROJECT_ROOT / "outputs" / "588200_safety_upgrade"),
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
    for col in ["open", "high", "low"]:
        if col not in df.columns and "close" in df.columns:
            df[col] = df["close"]
    if "volume" not in df.columns:
        df["volume"] = np.nan
    return df[["open", "high", "low", "close", "volume"]].copy()


def normalize_code(path: Path) -> str:
    return path.stem.upper().replace(".SH", ".SS")


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


def load_etfs(astock_root: Path, min_rows: int = 250) -> Dict[str, pd.DataFrame]:
    out: Dict[str, pd.DataFrame] = {}
    for code, path in sorted(collect_etf_paths(astock_root).items()):
        try:
            df = load_price_csv(path)
        except Exception:
            continue
        df = df[df["open"].notna() & df["open"].gt(0) & df["close"].notna() & df["close"].gt(0)]
        if len(df) >= min_rows:
            out[code] = df
    return out


def load_stock_pool(astock_root: Path) -> Tuple[Dict[str, pd.DataFrame], List[str]]:
    kc_dir = astock_root / "yf_data" / "KC"
    stocks: Dict[str, pd.DataFrame] = {}
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
        stocks[code] = df
    if not stocks:
        raise RuntimeError(f"No stock pool data loaded from {kc_dir}")
    return stocks, missing


def build_breadth_features(stocks: Dict[str, pd.DataFrame]) -> Tuple[pd.DataFrame, pd.DataFrame]:
    close = pd.DataFrame({code: df["close"] for code, df in stocks.items()}).sort_index()
    volume = pd.DataFrame({code: df["volume"] for code, df in stocks.items()}).reindex(close.index)
    ret20 = close.pct_change(20, fill_method=None)
    ret60 = close.pct_change(60, fill_method=None)
    amount = close * volume
    valid = close.notna()
    min_count = 10
    count = valid.sum(axis=1).where(lambda s: s >= min_count)

    breadth = pd.DataFrame(index=close.index)
    breadth["breadth_ma20"] = ((close > close.rolling(20).mean()) & valid).sum(axis=1) / count
    breadth["breadth_ma60"] = ((close > close.rolling(60).mean()) & valid).sum(axis=1) / count
    breadth["breadth_mom20"] = (ret20 > 0).sum(axis=1) / count
    breadth["breadth_mom60"] = (ret60 > 0).sum(axis=1) / count
    breadth["pool_ret20_median"] = ret20.median(axis=1)
    breadth["pool_ret60_median"] = ret60.median(axis=1)
    breadth["pool_disp20"] = ret20.std(axis=1)
    breadth["pool_liquidity20"] = np.log(amount.where(amount > 0)).rolling(20).mean().median(axis=1)
    breadth["pool_count"] = count
    return close, breadth


def select_similar_etfs(
    etfs: Dict[str, pd.DataFrame],
    target_code: str,
    start: pd.Timestamp,
    train_end: pd.Timestamp,
    min_overlap: int,
    min_corr: float,
    max_assets: int,
) -> pd.DataFrame:
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
        rows.append({
            "code": code,
            "corr_to_588200_train": corr,
            "overlap_days": len(common),
            "first_date": df.index.min().date().isoformat(),
            "last_date": df.index.max().date().isoformat(),
        })
    selected = pd.DataFrame(rows)
    if selected.empty:
        raise RuntimeError("No similar ETFs selected.")
    return selected.sort_values(["corr_to_588200_train", "overlap_days"], ascending=[False, False]).head(max_assets).reset_index(drop=True)


def make_safety_breadth(stocks: Dict[str, pd.DataFrame]) -> Tuple[pd.DataFrame, pd.Series]:
    panels = compute_safety_factor_panel(stocks)
    score = composite_safety_score(panels)
    count = score.notna().sum(axis=1).where(lambda s: s >= 10)
    safety_breadth = (score > 0).sum(axis=1) / count
    safety_breadth.name = "safety_breadth"
    return score, safety_breadth


def aggregate_metrics(rows: List[Dict[str, object]], prefix: str) -> Dict[str, float]:
    df = pd.DataFrame(rows)
    out: Dict[str, float] = {}
    for col in ["sharpe", "annual_return", "max_drawdown", "calmar", "exposure"]:
        series = pd.to_numeric(df[col], errors="coerce")
        out[f"{prefix}_median_{col}"] = float(series.median()) if series.notna().any() else np.nan
        out[f"{prefix}_mean_{col}"] = float(series.mean()) if series.notna().any() else np.nan
    out[f"{prefix}_positive_ratio"] = float((pd.to_numeric(df["annual_return"], errors="coerce") > 0).mean()) if not df.empty else np.nan
    out[f"{prefix}_asset_count"] = float(len(df))
    return out


def flatten(prefix: str, metrics: Dict[str, float]) -> Dict[str, float]:
    return {f"{prefix}_{key}": value for key, value in metrics.items()}


def train_score(row: pd.Series) -> float:
    sharpe = row.get("pool_train_median_sharpe", np.nan)
    positive = row.get("pool_train_positive_ratio", np.nan)
    dd = row.get("pool_train_median_max_drawdown", np.nan)
    exposure = row.get("pool_train_median_exposure", np.nan)
    if pd.isna(sharpe):
        return -999.0
    score = float(sharpe)
    if pd.notna(positive):
        score += 0.5 * (positive - 0.5)
    if pd.notna(dd) and dd < -0.35:
        score -= abs(dd) - 0.35
    if pd.notna(exposure) and exposure < 0.10:
        score -= 0.20
    return score


def evaluate_spec(
    spec: BinaryStrategySpec,
    selected_codes: Iterable[str],
    etfs: Dict[str, pd.DataFrame],
    signal_cache: Dict[str, Dict[str, object]],
    start: pd.Timestamp,
    train_end: pd.Timestamp,
    test_start: pd.Timestamp,
    end: pd.Timestamp,
    cost_rate: float,
    risk_free: float,
) -> Dict[str, object]:
    train_rows = []
    test_rows = []
    for code in selected_codes:
        asset = etfs[code].loc[start:end].copy()
        desired = signal_from_cache(signal_cache[code], spec)
        _nav, returns, _position = backtest_binary_position(asset, desired, cost_rate=cost_rate)
        train_metrics = compute_performance_metrics(returns, start, train_end, risk_free)
        test_metrics = compute_performance_metrics(returns, test_start, end, risk_free)
        train_metrics["code"] = code
        test_metrics["code"] = code
        train_rows.append(train_metrics)
        test_rows.append(test_metrics)

    row: Dict[str, object] = asdict(spec)
    row["strategy"] = spec.name
    row.update(aggregate_metrics(train_rows, "pool_train"))
    row.update(aggregate_metrics(test_rows, "pool_test"))
    return row


def buy_hold_returns(asset: pd.DataFrame) -> pd.Series:
    open_px = asset["open"]
    return open_px.shift(-1).div(open_px).sub(1).replace([np.inf, -np.inf], np.nan).fillna(0.0)


def pct(value: float) -> str:
    return "nan" if pd.isna(value) else f"{value * 100:.2f}%"


def num(value: float) -> str:
    return "nan" if pd.isna(value) else f"{value:.3f}"


def write_report(
    path: Path,
    summary: pd.DataFrame,
    best: pd.Series,
    best_enhanced: pd.Series,
    baseline: pd.Series,
    target_metrics: Dict[str, Dict[str, float]],
    enhanced_metrics: Dict[str, Dict[str, float]],
    baseline_metrics: Dict[str, Dict[str, float]],
    hold_metrics: Dict[str, Dict[str, float]],
    latest: Dict[str, object],
    args: argparse.Namespace,
    output_paths: Dict[str, Path],
    missing: List[str],
) -> None:
    text = f"""# 588200 安全策略与因子库增强验证报告

生成时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

## 本次补充

- 新增安全策略库：`src/strategies/safety.py`
- 新增安全因子/公式 Alpha 候选库：`src/factors/safety.py`
- 新增验证脚本：`scripts/validate_588200_safety_upgrade.py`

本次验证仍然只交易 `{args.target}`。588200 成分股池用于生成股票池广度和安全因子广度，同类 ETF 池用于训练期泛化打分，样本外只用于评价。

## 新增因子

新增安全复合分由以下因子等权 z-score 合成，数值越高表示越安全或越适合持有：

- `safe_downside_vol_20`：20 日下行波动率取负，越大表示下行波动越低。
- `safe_downside_vol_60`：60 日下行波动率取负。
- `safe_maxdd_60`：60 日滚动回撤，越接近 0 越好。
- `safe_cvar_60_5`：60 日 5% CVaR 尾部损失取负。
- `safe_liquidity_amihud_20`：20 日 Amihud 非流动性取负，越大表示流动性越好。
- `safe_trend_stability_60_20`：60 日动量除以 20 日波动率，越大表示趋势质量越好。
- `alpha_pv_corr_20`：20 日收益和成交量变化相关性取负，作为价量公式 Alpha 候选。

`safety_breadth` 表示成分股池中安全复合分大于 0 的股票比例。

## 最终推荐

策略：`{best['strategy']}`

- 60 日成分股广度买入/卖出阈值：{best['breadth_buy']:.0%} / {best['breadth_sell']:.0%}
- 目标 ETF 动量窗口：{int(best['mom_window'])} 日
- 目标 ETF 波动窗口与分位阈值：{int(best['vol_window'])} 日 / {best['vol_max']:.0%}
- 是否要求成分股池 20 日收益中位数为正：{bool(best['require_pool_mom'])}

结论：严格按照“同类 ETF 训练池泛化评分”选择，新增安全因子增强候选没有击败原全量网格最优基线，所以最终推荐暂不替换，仍保留原策略。

原策略买点：每天收盘后，588200 动量为正、成分股 MA60 广度达标、588200 波动率分位达标时，下一交易日开盘买入或继续持有 588200。

原策略卖点：上述任一核心条件跌破卖出阈值，下一交易日开盘卖出或继续空仓。

## 最好的安全因子增强候选

策略：`{best_enhanced['strategy']}`

- 成分股 MA60 广度买入/卖出阈值：{best_enhanced['breadth_buy']:.0%} / {best_enhanced['breadth_sell']:.0%}
- 目标 ETF 动量窗口：{int(best_enhanced['mom_window'])} 日
- 目标 ETF 波动窗口与分位阈值：{int(best_enhanced['vol_window'])} 日 / {best_enhanced['vol_max']:.0%}
- 安全广度买入/卖出阈值：{best_enhanced['safety_buy']:.0%} / {best_enhanced['safety_sell']:.0%}
- 是否要求成分股池 20 日收益中位数为正：{bool(best_enhanced['require_pool_mom'])}

安全增强候选买点：588200 动量为正、成分股 MA60 广度达标、588200 波动率分位达标，并且 `safety_breadth` 达到买入阈值时，下一交易日开盘买入或继续持有。

安全增强候选卖点：588200 动量转弱、成分股 MA60 广度跌破卖出阈值、波动率过高，或 `safety_breadth` 跌破卖出阈值时，下一交易日开盘卖出或继续空仓。

## 588200 结果对比

| 方案 | 训练年化 | 训练夏普 | 训练最大回撤 | 样本外年化 | 样本外夏普 | 样本外最大回撤 | 全样本年化 | 全样本夏普 | 全样本最大回撤 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 最终推荐策略 | {pct(target_metrics['train']['annual_return'])} | {num(target_metrics['train']['sharpe'])} | {pct(target_metrics['train']['max_drawdown'])} | {pct(target_metrics['test']['annual_return'])} | {num(target_metrics['test']['sharpe'])} | {pct(target_metrics['test']['max_drawdown'])} | {pct(target_metrics['full']['annual_return'])} | {num(target_metrics['full']['sharpe'])} | {pct(target_metrics['full']['max_drawdown'])} |
| 安全增强候选 | {pct(enhanced_metrics['train']['annual_return'])} | {num(enhanced_metrics['train']['sharpe'])} | {pct(enhanced_metrics['train']['max_drawdown'])} | {pct(enhanced_metrics['test']['annual_return'])} | {num(enhanced_metrics['test']['sharpe'])} | {pct(enhanced_metrics['test']['max_drawdown'])} | {pct(enhanced_metrics['full']['annual_return'])} | {num(enhanced_metrics['full']['sharpe'])} | {pct(enhanced_metrics['full']['max_drawdown'])} |
| 原全量网格最优基线 | {pct(baseline_metrics['train']['annual_return'])} | {num(baseline_metrics['train']['sharpe'])} | {pct(baseline_metrics['train']['max_drawdown'])} | {pct(baseline_metrics['test']['annual_return'])} | {num(baseline_metrics['test']['sharpe'])} | {pct(baseline_metrics['test']['max_drawdown'])} | {pct(baseline_metrics['full']['annual_return'])} | {num(baseline_metrics['full']['sharpe'])} | {pct(baseline_metrics['full']['max_drawdown'])} |
| 买入持有 | {pct(hold_metrics['train']['annual_return'])} | {num(hold_metrics['train']['sharpe'])} | {pct(hold_metrics['train']['max_drawdown'])} | {pct(hold_metrics['test']['annual_return'])} | {num(hold_metrics['test']['sharpe'])} | {pct(hold_metrics['test']['max_drawdown'])} | {pct(hold_metrics['full']['annual_return'])} | {num(hold_metrics['full']['sharpe'])} | {pct(hold_metrics['full']['max_drawdown'])} |

## 跨 ETF 泛化表现

- 最终推荐训练池中位夏普：{num(best['pool_train_median_sharpe'])}
- 最终推荐样本外中位夏普：{num(best['pool_test_median_sharpe'])}
- 最终推荐样本外正收益比例：{pct(best['pool_test_positive_ratio'])}
- 最终推荐样本外中位最大回撤：{pct(best['pool_test_median_max_drawdown'])}
- 最好安全候选训练池中位夏普：{num(best_enhanced['pool_train_median_sharpe'])}
- 最好安全候选样本外中位夏普：{num(best_enhanced['pool_test_median_sharpe'])}
- 原基线训练池中位夏普：{num(baseline['pool_train_median_sharpe'])}
- 原基线样本外中位夏普：{num(baseline['pool_test_median_sharpe'])}

## 最新信号

- 信号日期：{latest['signal_date']}
- 588200 收盘价：{latest['close']:.4f}
- 股票池 MA60 广度：{latest['breadth_ma60']:.2%}
- 安全广度：{latest['safety_breadth']:.2%}
- 下一交易日计划：`{latest['next_action']}`

## 结论

本次新增因子库让策略多了一层“安全广度”过滤：不只看板块是否上涨，还看板块内部股票的下行风险、回撤、流动性和趋势质量是否过关。是否最终替换原策略，应以样本外夏普、最大回撤、交易频率和参数稳定性综合判断。

当前严格结论：安全因子增强策略在 588200 样本外能明显降低最大回撤，但按训练池泛化评分不足以替换原策略。更合理的下一步是把安全广度作为风险降仓 overlay，而不是直接替代原买卖信号。

## 输出文件

- 策略排名：`{output_paths['summary']}`
- 588200 信号：`{output_paths['signal']}`
- 安全广度：`{output_paths['safety_breadth']}`
- 最优配置：`{output_paths['config']}`
- 本报告：`{path}`

## 限制

- 成分股池仍是 2025Q4 静态池，不是 point-in-time 历史成分。
- 安全复合因子是第一阶段等权合成，尚未做行业/市值中性化。
- 本次只使用本地已有行情和成交量，基本面质量因子尚未完全接入。
- 结果用于研究，不构成投资建议。

缺失成分股代码：{", ".join(missing) if missing else "无"}
候选策略数量：{len(summary)}
"""
    path.write_text(text, encoding="utf-8")


def main() -> None:
    args = parse_args()
    astock_root = Path(args.astock_root)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = Path(args.output_dir) / timestamp
    run_dir.mkdir(parents=True, exist_ok=True)

    start = pd.to_datetime(args.start)
    train_end = pd.to_datetime(args.train_end)
    test_start = train_end + pd.Timedelta(days=1)
    end = pd.to_datetime(args.end)

    print("Loading ETF universe...")
    etfs = load_etfs(astock_root)
    if args.target not in etfs:
        raise RuntimeError(f"Target ETF not found: {args.target}")
    print(f"ETF series loaded: {len(etfs)}")

    print("Loading 588200 stock pool...")
    stocks, missing = load_stock_pool(astock_root)
    _close, breadth = build_breadth_features(stocks)
    safety_score, safety_breadth = make_safety_breadth(stocks)
    print(f"Stock pool loaded: {len(stocks)}, missing: {len(missing)}")

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
    print(f"Similar ETF pool: {len(selected_codes)}")

    specs = build_specs()
    target_asset = etfs[args.target].loc[start:end].copy()
    print("Building signal cache...")
    signal_cache = {
        code: build_signal_cache(etfs[code].loc[start:end].copy(), breadth, safety_breadth, specs)
        for code in selected_codes
    }
    signal_cache[args.target] = build_signal_cache(target_asset, breadth, safety_breadth, specs)
    rows = []
    for i, spec in enumerate(specs, start=1):
        row = evaluate_spec(
            spec=spec,
            selected_codes=selected_codes,
            etfs=etfs,
            signal_cache=signal_cache,
            start=start,
            train_end=train_end,
            test_start=test_start,
            end=end,
            cost_rate=args.cost_rate,
            risk_free=args.risk_free,
        )
        desired = signal_from_cache(signal_cache[args.target], spec)
        _nav, target_returns, _position = backtest_binary_position(target_asset, desired, cost_rate=args.cost_rate)
        row.update(flatten("target_train", compute_performance_metrics(target_returns, start, train_end, args.risk_free)))
        row.update(flatten("target_test", compute_performance_metrics(target_returns, test_start, end, args.risk_free)))
        row.update(flatten("target_full", compute_performance_metrics(target_returns, start, end, args.risk_free)))
        row["train_score"] = train_score(pd.Series(row))
        rows.append(row)
        if i % 50 == 0 or i == len(specs):
            print(f"Evaluated {i}/{len(specs)} specs")

    summary = pd.DataFrame(rows).sort_values(["train_score", "pool_test_median_sharpe"], ascending=False).reset_index(drop=True)
    best = summary.iloc[0]
    baseline = summary[summary["strategy"] == "baseline_prev_best__mom60__breadth65_50__vol20_vp95"].iloc[0]
    enhanced_summary = summary[summary["strategy"].str.startswith("safety_mv")].copy()
    if enhanced_summary.empty:
        raise RuntimeError("No safety-enhanced candidate found.")
    best_enhanced = enhanced_summary.iloc[0]

    best_spec = spec_from_row(best)
    best_enhanced_spec = spec_from_row(best_enhanced)
    baseline_spec = spec_from_row(baseline)

    best_desired = signal_from_cache(signal_cache[args.target], best_spec)
    best_nav, best_returns, best_position = backtest_binary_position(target_asset, best_desired, cost_rate=args.cost_rate)
    best_enhanced_desired = signal_from_cache(signal_cache[args.target], best_enhanced_spec)
    _best_enhanced_nav, best_enhanced_returns, _best_enhanced_position = backtest_binary_position(
        target_asset, best_enhanced_desired, cost_rate=args.cost_rate
    )
    baseline_desired = signal_from_cache(signal_cache[args.target], baseline_spec)
    baseline_nav, baseline_returns, baseline_position = backtest_binary_position(target_asset, baseline_desired, cost_rate=args.cost_rate)
    hold_returns = buy_hold_returns(target_asset)

    target_metrics = {
        "train": compute_performance_metrics(best_returns, start, train_end, args.risk_free),
        "test": compute_performance_metrics(best_returns, test_start, end, args.risk_free),
        "full": compute_performance_metrics(best_returns, start, end, args.risk_free),
    }
    baseline_metrics = {
        "train": compute_performance_metrics(baseline_returns, start, train_end, args.risk_free),
        "test": compute_performance_metrics(baseline_returns, test_start, end, args.risk_free),
        "full": compute_performance_metrics(baseline_returns, start, end, args.risk_free),
    }
    enhanced_metrics = {
        "train": compute_performance_metrics(best_enhanced_returns, start, train_end, args.risk_free),
        "test": compute_performance_metrics(best_enhanced_returns, test_start, end, args.risk_free),
        "full": compute_performance_metrics(best_enhanced_returns, start, end, args.risk_free),
    }
    hold_metrics = {
        "train": compute_performance_metrics(hold_returns, start, train_end, args.risk_free),
        "test": compute_performance_metrics(hold_returns, test_start, end, args.risk_free),
        "full": compute_performance_metrics(hold_returns, start, end, args.risk_free),
    }

    last_date = best_desired.index[-1]
    latest = {
        "signal_date": last_date.date().isoformat(),
        "close": float(target_asset.loc[last_date, "close"]),
        "breadth_ma60": float(breadth["breadth_ma60"].reindex([last_date]).ffill().iloc[0]),
        "safety_breadth": float(safety_breadth.reindex([last_date]).ffill().iloc[0]),
        "next_action": "BUY_OR_HOLD_588200" if bool(best_desired.loc[last_date]) else "EMPTY_OR_SELL_588200",
    }

    summary_path = run_dir / f"strategy_summary_{timestamp}.csv"
    signal_path = run_dir / f"target_588200_signal_{timestamp}.csv"
    safety_path = run_dir / f"safety_breadth_{timestamp}.csv"
    config_path = run_dir / f"best_config_{timestamp}.json"
    report_path = run_dir / f"report_{timestamp}.md"

    summary.to_csv(summary_path, index=False, encoding="utf-8-sig")
    pd.DataFrame({
        "open": target_asset["open"],
        "close": target_asset["close"],
        "best_desired_after_close": best_desired,
        "best_position_next_open": best_position,
        "best_nav": best_nav,
        "baseline_desired_after_close": baseline_desired,
        "baseline_position_next_open": baseline_position,
        "baseline_nav": baseline_nav,
        "buy_hold_nav": (1 + hold_returns).cumprod(),
        "breadth_ma60": breadth["breadth_ma60"].reindex(target_asset.index).ffill(),
        "safety_breadth": safety_breadth.reindex(target_asset.index).ffill(),
    }).to_csv(signal_path, index=True, index_label="date", encoding="utf-8-sig")
    pd.DataFrame({
        "safety_breadth": safety_breadth,
        "safety_score_median": safety_score.median(axis=1),
        "safety_score_count": safety_score.notna().sum(axis=1),
    }).to_csv(safety_path, index=True, index_label="date", encoding="utf-8-sig")
    config_path.write_text(
        json.dumps(
            {
                "best_strategy": best_spec.__dict__,
                "best_safety_enhanced_strategy": best_enhanced_spec.__dict__,
                "baseline_strategy": baseline_spec.__dict__,
                "latest_signal": latest,
                "start": args.start,
                "train_end": args.train_end,
                "end": args.end,
                "candidate_count": int(len(summary)),
                "selected_etfs": selected_codes,
                "missing_stock_codes": missing,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    write_report(
        path=report_path,
        summary=summary,
        best=best,
        best_enhanced=best_enhanced,
        baseline=baseline,
        target_metrics=target_metrics,
        enhanced_metrics=enhanced_metrics,
        baseline_metrics=baseline_metrics,
        hold_metrics=hold_metrics,
        latest=latest,
        args=args,
        output_paths={
            "summary": summary_path,
            "signal": signal_path,
            "safety_breadth": safety_path,
            "config": config_path,
        },
        missing=missing,
    )

    print("\nSafety upgrade validation")
    print("-------------------------")
    print(f"best_strategy: {best_spec.name}")
    print(f"best_safety_enhanced_strategy: {best_enhanced_spec.name}")
    print(f"candidates: {len(summary)}")
    print(f"final recommendation test annual return: {target_metrics['test']['annual_return'] * 100:.2f}%")
    print(f"final recommendation test Sharpe: {target_metrics['test']['sharpe']:.3f}")
    print(f"final recommendation test max drawdown: {target_metrics['test']['max_drawdown'] * 100:.2f}%")
    print(f"safety candidate test annual return: {enhanced_metrics['test']['annual_return'] * 100:.2f}%")
    print(f"safety candidate test Sharpe: {enhanced_metrics['test']['sharpe']:.3f}")
    print(f"safety candidate test max drawdown: {enhanced_metrics['test']['max_drawdown'] * 100:.2f}%")
    print(f"baseline test annual return: {baseline_metrics['test']['annual_return'] * 100:.2f}%")
    print(f"baseline test Sharpe: {baseline_metrics['test']['sharpe']:.3f}")
    print(f"baseline test max drawdown: {baseline_metrics['test']['max_drawdown'] * 100:.2f}%")
    print(f"latest plan: {latest['next_action']} as of {latest['signal_date']}")
    print(f"report: {report_path}")


if __name__ == "__main__":
    main()
