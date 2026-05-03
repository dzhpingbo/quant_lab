"""
Optimize and backtest a 588200 constituent-stock rotation strategy.

The optimizer uses a static 2025Q4 588200 constituent universe because that is
the local data we currently have. It chooses the recommended configuration on
the training window only, then reports out-of-sample performance separately.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ASTOCK_ROOT = PROJECT_ROOT / "data" / "external" / "legacy_quant" / "AStock"

CODES_588200 = [
    "688981", "688041", "688256", "688008", "688012", "688072", "688521", "688347",
    "688126", "688110", "688498", "688525", "688120", "688002", "688249", "688361",
    "688099", "688313", "688396", "688385", "688608", "688213", "688047", "688019",
    "688037", "688220", "688234", "688200", "688052", "688702", "688018", "688082",
    "688536", "688582", "688484", "688141", "688728", "688409", "688279", "688709",
    "688172", "688798", "688153", "688146", "688332", "688352", "688432", "688584",
    "688449", "688605",
]


FACTOR_RECIPES: Dict[str, Dict[str, float]] = {
    "MOM60": {"mom60": 1.0},
    "MOM120_SKIP20": {"mom120_skip20": 1.0},
    "REV5": {"rev5": 1.0},
    "REV20": {"rev20": 1.0},
    "LOW_VOL20": {"low_vol20": 1.0},
    "RISK_ADJ_MOM60": {"risk_adj_mom60": 1.0},
    "MA_TREND": {"ma_trend_20_60": 0.7, "liquidity20": 0.3},
    "TREND_QUALITY": {"mom60": 0.5, "risk_adj_mom60": 0.3, "low_vol20": 0.2},
    "DEFENSIVE_MOM": {"mom120_skip20": 0.4, "low_vol60": 0.35, "downside_q20": 0.25},
    "REVERSAL_DEFENSIVE": {"rev5": 0.5, "low_vol20": 0.3, "rsi_reversal": 0.2},
    "BALANCED": {
        "mom60": 0.30,
        "mom120_skip20": 0.25,
        "low_vol20": 0.20,
        "risk_adj_mom60": 0.15,
        "liquidity20": 0.10,
    },
}

REGIMES = ["none", "etf_ma60", "pool_ma60"]
FREQUENCIES = ["W", "M"]
TOP_NS = [5, 8, 10, 15]


@dataclass(frozen=True)
class StrategyConfig:
    recipe: str
    freq: str
    top_n: int
    regime: str

    @property
    def name(self) -> str:
        return f"{self.recipe}__{self.freq}__top{self.top_n}__{self.regime}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Optimize 588200 stock-pool strategy.")
    parser.add_argument("--astock-root", default=str(DEFAULT_ASTOCK_ROOT), help="AStock data root.")
    parser.add_argument("--start", default="2022-10-26", help="Backtest start date.")
    parser.add_argument("--end", default="2026-04-10", help="Backtest end date.")
    parser.add_argument("--train-end", default="2024-12-31", help="Last in-sample date.")
    parser.add_argument("--cost-rate", type=float, default=0.001, help="One-way turnover cost rate.")
    parser.add_argument("--risk-free", type=float, default=0.02, help="Annual risk-free rate.")
    parser.add_argument(
        "--output-dir",
        default=str(PROJECT_ROOT / "outputs" / "588200_strategy_optimization"),
        help="Directory for reports and CSV outputs.",
    )
    return parser.parse_args()


def load_price_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df.columns = [str(c).strip().lower() for c in df.columns]
    date_col = next((c for c in df.columns if c in {"date", "datetime"}), None)
    if date_col is None:
        date_col = df.columns[0]
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


def load_constituent_panels(astock_root: Path) -> Tuple[Dict[str, pd.DataFrame], List[str]]:
    kc_dir = astock_root / "yf_data" / "KC"
    data: Dict[str, pd.DataFrame] = {}
    missing: List[str] = []

    for code in CODES_588200:
        candidates = [
            kc_dir / f"{code}.SS.csv",
            kc_dir / f"{code}.SH.csv",
            kc_dir / f"{code}.csv",
        ]
        path = next((p for p in candidates if p.exists()), None)
        if path is None:
            missing.append(code)
            continue
        df = load_price_csv(path)
        if df["close"].notna().sum() >= 180:
            data[code] = df
        else:
            missing.append(code)

    if not data:
        raise RuntimeError(f"No constituent data loaded from {kc_dir}")
    return data, missing


def make_panel(data: Dict[str, pd.DataFrame], field: str) -> pd.DataFrame:
    panel = pd.concat({code: df[field] for code, df in data.items()}, axis=1).sort_index()
    panel.index.name = "date"
    return panel


def load_benchmark(astock_root: Path) -> Optional[pd.DataFrame]:
    candidates = [
        astock_root / "ETF" / "yf_etf_data" / "588200.SS.csv",
        astock_root / "ETF" / "588200.SH.csv",
        astock_root / "ETF" / "yf_etf_data" / "588000.SS.csv",
        astock_root / "ETF" / "588000.SH.csv",
    ]
    for path in candidates:
        if path.exists():
            df = load_price_csv(path)
            df = df[df["open"].notna() & df["open"].gt(0)]
            if not df.empty:
                df.attrs["source"] = str(path)
                return df
    return None


def cross_section_zscore(frame: pd.DataFrame) -> pd.DataFrame:
    mean = frame.mean(axis=1)
    std = frame.std(axis=1).replace(0, np.nan)
    return frame.sub(mean, axis=0).div(std, axis=0).clip(-3, 3)


def calc_rsi_reversal(close: pd.DataFrame, window: int = 14) -> pd.DataFrame:
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - 100 / (1 + rs)
    return -rsi


def build_features(close: pd.DataFrame, volume: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    ret = close.pct_change(fill_method=None)
    vol20 = ret.rolling(20).std() * np.sqrt(252)
    vol60 = ret.rolling(60).std() * np.sqrt(252)
    amount = close * volume

    features = {
        "mom20": close.pct_change(20, fill_method=None),
        "mom60": close.pct_change(60, fill_method=None),
        "mom120_skip20": close.shift(20).pct_change(120, fill_method=None),
        "rev5": -close.pct_change(5, fill_method=None),
        "rev20": -close.pct_change(20, fill_method=None),
        "low_vol20": -vol20,
        "low_vol60": -vol60,
        "risk_adj_mom60": close.pct_change(60, fill_method=None) / (ret.rolling(60).std() * np.sqrt(60)).replace(0, np.nan),
        "liquidity20": np.log(amount.where(amount > 0)).rolling(20).mean(),
        "rsi_reversal": calc_rsi_reversal(close),
        "ma_trend_20_60": close.rolling(20).mean() / close.rolling(60).mean() - 1,
        "downside_q20": ret.rolling(20).quantile(0.10),
    }
    return features


def combine_score(features: Dict[str, pd.DataFrame], recipe: Dict[str, float]) -> pd.DataFrame:
    score: Optional[pd.DataFrame] = None
    for factor_name, weight in recipe.items():
        z = cross_section_zscore(features[factor_name])
        score = z * weight if score is None else score.add(z * weight, fill_value=0)
    return score if score is not None else pd.DataFrame()


def rebalance_dates(index: pd.DatetimeIndex, freq: str) -> pd.DatetimeIndex:
    s = pd.Series(index, index=index)
    rule = "W-FRI" if freq == "W" else "ME"
    sampled = s.resample(rule).last().dropna()
    return pd.DatetimeIndex(sampled.values)


def build_regime(
    regime: str,
    dates: pd.DatetimeIndex,
    benchmark: Optional[pd.DataFrame],
    close: pd.DataFrame,
) -> pd.Series:
    if regime == "none":
        return pd.Series(True, index=dates)

    if regime == "etf_ma60" and benchmark is not None:
        s = benchmark["close"].reindex(dates).ffill()
    else:
        s = close.mean(axis=1).reindex(dates).ffill()

    ok = s > s.rolling(60, min_periods=40).mean()
    return ok.fillna(False)


def run_strategy(
    config: StrategyConfig,
    score: pd.DataFrame,
    open_px: pd.DataFrame,
    close: pd.DataFrame,
    volume: pd.DataFrame,
    benchmark: Optional[pd.DataFrame],
    start: str,
    end: str,
    cost_rate: float,
) -> Tuple[pd.Series, pd.Series, pd.DataFrame, pd.DataFrame]:
    dates = open_px.loc[start:end].index
    if len(dates) < 80:
        raise RuntimeError("Not enough dates for backtest.")

    weights_at_trade = pd.DataFrame(np.nan, index=dates, columns=open_px.columns, dtype=float)
    trades = []
    regime = build_regime(config.regime, close.index, benchmark, close)

    for signal_date in rebalance_dates(dates, config.freq):
        if signal_date not in dates:
            continue
        pos = dates.get_loc(signal_date)
        if isinstance(pos, slice) or pos + 1 >= len(dates):
            continue
        execution_date = dates[pos + 1]

        target = pd.Series(0.0, index=open_px.columns)
        is_risk_on = bool(regime.reindex([signal_date]).ffill().iloc[0])
        selected: List[str] = []

        if is_risk_on and signal_date in score.index:
            tradable = (
                open_px.loc[execution_date].gt(0)
                & close.loc[signal_date].notna()
                & volume.loc[signal_date].fillna(0).gt(0)
                & score.loc[signal_date].notna()
            )
            candidates = score.loc[signal_date].where(tradable).dropna()
            if len(candidates) >= max(3, min(config.top_n, 5)):
                selected = candidates.nlargest(min(config.top_n, len(candidates))).index.tolist()
                target.loc[selected] = 1.0 / len(selected)

        weights_at_trade.loc[execution_date] = target
        trades.append({
            "signal_date": signal_date.date().isoformat(),
            "execution_date": execution_date.date().isoformat(),
            "risk_on": is_risk_on,
            "selected_count": len(selected),
            "selected": ",".join(selected),
        })

    weights = weights_at_trade.ffill().fillna(0.0)
    prev_weights = weights.shift(1).fillna(0.0)
    turnover = weights.sub(prev_weights).abs().sum(axis=1)
    costs = turnover * cost_rate

    asset_ret = open_px.shift(-1).div(open_px).sub(1).replace([np.inf, -np.inf], np.nan)
    portfolio_ret = weights.mul(asset_ret).sum(axis=1).fillna(0.0) - costs
    nav = (1 + portfolio_ret).cumprod()
    nav.name = config.name

    trade_df = pd.DataFrame(trades)
    diagnostics = pd.DataFrame({
        "turnover": turnover,
        "cost": costs,
        "holdings": weights.gt(0).sum(axis=1),
    })
    return nav, portfolio_ret, weights, trade_df.join(diagnostics.reindex(pd.to_datetime(trade_df["execution_date"])).reset_index(drop=True)) if not trade_df.empty else trade_df


def compute_metrics(
    returns: pd.Series,
    start: Optional[pd.Timestamp],
    end: Optional[pd.Timestamp],
    risk_free: float,
) -> Dict[str, float]:
    r = returns.copy()
    if start is not None:
        r = r[r.index >= start]
    if end is not None:
        r = r[r.index <= end]
    r = r.dropna()

    if len(r) < 20:
        return {
            "total_return": np.nan,
            "annual_return": np.nan,
            "annual_vol": np.nan,
            "sharpe": np.nan,
            "max_drawdown": np.nan,
            "calmar": np.nan,
            "win_rate": np.nan,
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
    win_rate = (r > 0).mean()
    return {
        "total_return": float(total_return),
        "annual_return": float(annual_return),
        "annual_vol": float(annual_vol),
        "sharpe": float(sharpe),
        "max_drawdown": float(max_drawdown),
        "calmar": float(calmar),
        "win_rate": float(win_rate),
        "days": float(len(r)),
    }


def benchmark_returns(benchmark: Optional[pd.DataFrame], index: pd.DatetimeIndex) -> Optional[pd.Series]:
    if benchmark is None:
        return None
    open_px = benchmark["open"].reindex(index).ffill()
    ret = open_px.shift(-1).div(open_px).sub(1).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    ret.name = "588200_ETF"
    return ret


def train_score(row: pd.Series) -> float:
    sharpe = row.get("train_sharpe", np.nan)
    annual_return = row.get("train_annual_return", np.nan)
    max_drawdown = row.get("train_max_drawdown", np.nan)
    if pd.isna(sharpe):
        return -999.0
    score = float(sharpe)
    if pd.notna(annual_return) and annual_return <= 0:
        score -= 1.0
    if pd.notna(max_drawdown) and max_drawdown < -0.55:
        score -= (abs(max_drawdown) - 0.55) * 2
    return score


def flatten_metrics(prefix: str, metrics: Dict[str, float]) -> Dict[str, float]:
    return {f"{prefix}_{k}": v for k, v in metrics.items()}


def pct(x: float) -> str:
    return "nan" if pd.isna(x) else f"{x * 100:.2f}%"


def num(x: float) -> str:
    return "nan" if pd.isna(x) else f"{x:.3f}"


def markdown_table(df: pd.DataFrame) -> str:
    headers = list(df.columns)
    lines = [
        "| " + " | ".join(str(c) for c in headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for _, row in df.iterrows():
        values = []
        for col in headers:
            value = row[col]
            if isinstance(value, (float, np.floating)):
                values.append(f"{value:.4f}")
            else:
                values.append(str(value))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def write_report(
    report_path: Path,
    best: pd.Series,
    all_results: pd.DataFrame,
    bench_metrics: Dict[str, Dict[str, float]],
    output_paths: Dict[str, Path],
    args: argparse.Namespace,
    loaded_count: int,
    missing: List[str],
    benchmark_source: Optional[str],
) -> None:
    recipe = FACTOR_RECIPES[str(best["recipe"])]
    factor_lines = "\n".join(f"- `{name}`: 权重 {weight:g}" for name, weight in recipe.items())
    top_rows = all_results.head(10)
    ranking_table = markdown_table(top_rows[[
        "recipe", "freq", "top_n", "regime", "train_sharpe", "test_sharpe",
        "full_annual_return", "full_max_drawdown",
    ]])

    bench_text = ""
    for name, metrics in bench_metrics.items():
        bench_text += (
            f"- {name}: 全样本年化 {pct(metrics.get('full_annual_return', np.nan))}, "
            f"夏普 {num(metrics.get('full_sharpe', np.nan))}, "
            f"最大回撤 {pct(metrics.get('full_max_drawdown', np.nan))}\n"
        )
    bench_section = bench_text or "- 无可用基准。\n"
    test_start_label = pd.to_datetime(args.train_end).date() + pd.Timedelta(days=1)

    text = f"""# 588200 股票池最优买卖策略回测报告

生成时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

## 结论

本次推荐策略为 `{best['strategy']}`。

- 训练期：{args.start} 至 {args.train_end}
- 样本外：{test_start_label} 至 {args.end}
- 股票池：588200 2025Q4 静态成分股，成功加载 {loaded_count} 只
- 成本假设：单边换手成本 {args.cost_rate:.4%}
- 基准数据：{benchmark_source or "未找到 588200/588000 ETF 基准"}

## 推荐策略参数

- 因子组合：`{best['recipe']}`
- 调仓频率：`{'周频，每周最后一个交易日收盘后生成信号，下一交易日开盘执行' if best['freq'] == 'W' else '月频，每月最后一个交易日收盘后生成信号，下一交易日开盘执行'}`
- 持仓数量：Top {int(best['top_n'])}
- 风控开关：`{best['regime']}`
- 买入规则：在风险开关为开启时，按综合因子分数从高到低买入 Top {int(best['top_n'])}，等权配置。
- 卖出规则：下一次调仓时，不在新 Top {int(best['top_n'])} 内的股票卖出；若风险开关关闭，则组合清仓转现金。
- 执行口径：只使用信号日收盘前可见数据，下一交易日开盘成交，避免调仓日收益前视。

## 因子权重

{factor_lines}

## 绩效摘要

| 区间 | 总收益 | 年化收益 | 年化波动 | 夏普 | 最大回撤 | Calmar | 胜率 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 训练期 | {pct(best['train_total_return'])} | {pct(best['train_annual_return'])} | {pct(best['train_annual_vol'])} | {num(best['train_sharpe'])} | {pct(best['train_max_drawdown'])} | {num(best['train_calmar'])} | {pct(best['train_win_rate'])} |
| 样本外 | {pct(best['test_total_return'])} | {pct(best['test_annual_return'])} | {pct(best['test_annual_vol'])} | {num(best['test_sharpe'])} | {pct(best['test_max_drawdown'])} | {num(best['test_calmar'])} | {pct(best['test_win_rate'])} |
| 全样本 | {pct(best['full_total_return'])} | {pct(best['full_annual_return'])} | {pct(best['full_annual_vol'])} | {num(best['full_sharpe'])} | {pct(best['full_max_drawdown'])} | {num(best['full_calmar'])} | {pct(best['full_win_rate'])} |

## 基准对比

{bench_section}

## 前十名参数组合

{ranking_table}

## 输出文件

- 参数绩效明细：`{output_paths['summary']}`
- 净值曲线：`{output_paths['nav']}`
- 推荐策略调仓明细：`{output_paths['trades']}`
- 推荐策略配置：`{output_paths['config']}`
- 本报告：`{report_path}`

## 使用方法

在项目根目录运行：

```powershell
python scripts\\optimize_588200_strategy.py --start {args.start} --train-end {args.train_end} --end {args.end}
```

常用参数：

- `--cost-rate 0.001`：单边换手成本，默认 0.10%。
- `--train-end YYYY-MM-DD`：训练期截止日；策略只用训练期选择最优参数。
- `--output-dir PATH`：结果输出目录。

实盘使用时，在每个调仓日收盘后运行脚本，查看 `best_trades_*.csv` 最新一行的 `selected` 列；下一交易日开盘按等权买入这些股票，并卖出不在名单中的旧持仓。若 `risk_on=False`，则不新开仓并清掉旧持仓。

## 风险与限制

- 当前股票池是 2025Q4 静态成分股，不是历史 point-in-time 成分股，仍有成分股幸存者偏差。
- 回测没有模拟涨跌停无法成交、停牌、滑点冲击、盘口深度和 A 股 T+1 细节。
- “最优”指训练期风险调整收益最优，不保证未来最优；样本外指标应比训练期指标更重要。
- 588200 ETF 自身上市较晚，本报告默认从 2022-10-26 开始，便于与 588200 可交易区间对齐。
"""
    if missing:
        text += "\n## 未加载代码\n\n" + ", ".join(missing) + "\n"
    report_path.write_text(text, encoding="utf-8")


def main() -> None:
    args = parse_args()
    astock_root = Path(args.astock_root)
    output_dir = Path(args.output_dir)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = output_dir / timestamp
    run_dir.mkdir(parents=True, exist_ok=True)

    data, missing = load_constituent_panels(astock_root)
    open_px = make_panel(data, "open")
    close = make_panel(data, "close")
    volume = make_panel(data, "volume")
    benchmark = load_benchmark(astock_root)
    benchmark_source = benchmark.attrs.get("source") if benchmark is not None else None

    features = build_features(close, volume)
    train_end = pd.to_datetime(args.train_end)
    test_start = train_end + pd.Timedelta(days=1)
    start_ts = pd.to_datetime(args.start)
    end_ts = pd.to_datetime(args.end)

    navs: Dict[str, pd.Series] = {}
    returns_map: Dict[str, pd.Series] = {}
    trades_map: Dict[str, pd.DataFrame] = {}
    rows: List[Dict[str, object]] = []

    print(f"Loaded {len(data)} 588200 constituents. Missing: {len(missing)}")
    print(f"Benchmark: {benchmark_source or 'none'}")
    print("Running parameter grid...")

    for recipe_name, recipe in FACTOR_RECIPES.items():
        score = combine_score(features, recipe)
        for freq in FREQUENCIES:
            for top_n in TOP_NS:
                for regime in REGIMES:
                    config = StrategyConfig(recipe=recipe_name, freq=freq, top_n=top_n, regime=regime)
                    nav, returns, _weights, trades = run_strategy(
                        config=config,
                        score=score,
                        open_px=open_px,
                        close=close,
                        volume=volume,
                        benchmark=benchmark,
                        start=args.start,
                        end=args.end,
                        cost_rate=args.cost_rate,
                    )
                    train = compute_metrics(returns, start_ts, train_end, args.risk_free)
                    test = compute_metrics(returns, test_start, end_ts, args.risk_free)
                    full = compute_metrics(returns, start_ts, end_ts, args.risk_free)
                    row = {
                        "strategy": config.name,
                        "recipe": recipe_name,
                        "freq": freq,
                        "top_n": top_n,
                        "regime": regime,
                        "rebalance_count": int(len(trades)),
                    }
                    row.update(flatten_metrics("train", train))
                    row.update(flatten_metrics("test", test))
                    row.update(flatten_metrics("full", full))
                    rows.append(row)
                    navs[config.name] = nav
                    returns_map[config.name] = returns
                    trades_map[config.name] = trades

    summary = pd.DataFrame(rows)
    summary["train_score"] = summary.apply(train_score, axis=1)
    summary = summary.sort_values(["train_score", "test_sharpe", "full_sharpe"], ascending=False)
    best = summary.iloc[0]

    bench_metrics: Dict[str, Dict[str, float]] = {}
    bench_ret = benchmark_returns(benchmark, open_px.loc[args.start:args.end].index)
    if bench_ret is not None:
        bench_metrics["588200 ETF"] = flatten_metrics(
            "full", compute_metrics(bench_ret, start_ts, end_ts, args.risk_free)
        )

    pool_ret = open_px.loc[args.start:args.end].pct_change(fill_method=None).mean(axis=1).fillna(0.0)
    pool_ret.name = "pool_equal_weight_daily"
    bench_metrics["股票池日等权"] = flatten_metrics(
        "full", compute_metrics(pool_ret, start_ts, end_ts, args.risk_free)
    )

    summary_path = run_dir / f"summary_{timestamp}.csv"
    nav_path = run_dir / f"nav_{timestamp}.csv"
    trades_path = run_dir / f"best_trades_{timestamp}.csv"
    config_path = run_dir / f"best_config_{timestamp}.json"
    report_path = run_dir / f"report_{timestamp}.md"

    summary.to_csv(summary_path, index=False, encoding="utf-8-sig")
    nav_df = pd.DataFrame({name: nav for name, nav in navs.items()})
    if bench_ret is not None:
        nav_df["BENCH_588200_ETF"] = (1 + bench_ret).cumprod()
    nav_df["BENCH_POOL_EQUAL_WEIGHT"] = (1 + pool_ret).cumprod()
    nav_df.to_csv(nav_path, encoding="utf-8-sig")

    best_trades = trades_map[str(best["strategy"])]
    best_trades.to_csv(trades_path, index=False, encoding="utf-8-sig")

    best_config = {
        "strategy": str(best["strategy"]),
        "recipe": str(best["recipe"]),
        "factor_weights": FACTOR_RECIPES[str(best["recipe"])],
        "freq": str(best["freq"]),
        "top_n": int(best["top_n"]),
        "regime": str(best["regime"]),
        "start": args.start,
        "train_end": args.train_end,
        "end": args.end,
        "cost_rate": args.cost_rate,
        "benchmark_source": benchmark_source,
    }
    config_path.write_text(json.dumps(best_config, ensure_ascii=False, indent=2), encoding="utf-8")

    write_report(
        report_path=report_path,
        best=best,
        all_results=summary,
        bench_metrics=bench_metrics,
        output_paths={
            "summary": summary_path,
            "nav": nav_path,
            "trades": trades_path,
            "config": config_path,
        },
        args=args,
        loaded_count=len(data),
        missing=missing,
        benchmark_source=benchmark_source,
    )

    print("\nBest strategy")
    print("-------------")
    print(f"strategy: {best['strategy']}")
    print(f"train sharpe: {best['train_sharpe']:.3f}")
    print(f"test sharpe: {best['test_sharpe']:.3f}")
    print(f"full annual return: {best['full_annual_return'] * 100:.2f}%")
    print(f"full max drawdown: {best['full_max_drawdown'] * 100:.2f}%")
    print(f"report: {report_path}")


if __name__ == "__main__":
    main()
