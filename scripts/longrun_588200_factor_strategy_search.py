"""Long-run 588200 factor/strategy search with checkpoints.

Run pattern:
1. Start in background with redirected stdout/stderr.
2. The script writes `strategy_summary_checkpoint.csv` every N specs.
3. Resume with the same --run-dir and --resume.
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.factors.safety import SAFETY_FACTORS, compute_safety_factor_panel, cross_section_zscore
from src.strategies.etf_588200 import (
    LongRunStrategySpec as LongRunSpec,
    build_longrun_signal_cache as build_signal_cache,
    longrun_signal_from_cache as signal_from_cache,
    longrun_spec_from_row as spec_from_row,
    make_longrun_specs as make_specs,
)
from src.strategies.safety import backtest_binary_position, compute_performance_metrics


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
    parser = argparse.ArgumentParser(description="Long-run 588200 factor strategy search.")
    parser.add_argument("--astock-root", default=str(DEFAULT_ASTOCK_ROOT), help="AStock data root.")
    parser.add_argument("--target", default=TARGET_CODE)
    parser.add_argument("--start", default="2022-10-26")
    parser.add_argument("--train-end", default="2024-12-31")
    parser.add_argument("--end", default="2026-04-08")
    parser.add_argument("--max-similar-etfs", type=int, default=18)
    parser.add_argument("--min-overlap", type=int, default=180)
    parser.add_argument("--min-corr", type=float, default=0.45)
    parser.add_argument("--cost-rate", type=float, default=0.001)
    parser.add_argument("--risk-free", type=float, default=0.02)
    parser.add_argument("--checkpoint-every", type=int, default=50)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--run-dir", default=None)
    parser.add_argument(
        "--output-dir",
        default=str(PROJECT_ROOT / "outputs" / "588200_longrun_factor_strategy"),
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
        if col not in df.columns:
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


def load_etfs(astock_root: Path) -> Dict[str, pd.DataFrame]:
    out: Dict[str, pd.DataFrame] = {}
    for code, path in sorted(collect_etf_paths(astock_root).items()):
        try:
            df = load_price_csv(path)
        except Exception:
            continue
        df = df[df["open"].notna() & df["open"].gt(0) & df["close"].notna() & df["close"].gt(0)]
        if len(df) >= 250:
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
        raise RuntimeError("No stock pool loaded.")
    return stocks, missing


def build_breadth_features(stocks: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    close = pd.DataFrame({code: df["close"] for code, df in stocks.items()}).sort_index()
    volume = pd.DataFrame({code: df["volume"] for code, df in stocks.items()}).reindex(close.index)
    ret20 = close.pct_change(20, fill_method=None)
    ret60 = close.pct_change(60, fill_method=None)
    amount = close * volume
    valid = close.notna()
    count = valid.sum(axis=1).where(lambda s: s >= 10)
    out = pd.DataFrame(index=close.index)
    out["breadth_ma20"] = ((close > close.rolling(20).mean()) & valid).sum(axis=1) / count
    out["breadth_ma60"] = ((close > close.rolling(60).mean()) & valid).sum(axis=1) / count
    out["breadth_mom20"] = (ret20 > 0).sum(axis=1) / count
    out["breadth_mom60"] = (ret60 > 0).sum(axis=1) / count
    out["pool_ret20_median"] = ret20.median(axis=1)
    out["pool_ret60_median"] = ret60.median(axis=1)
    out["pool_disp20"] = ret20.std(axis=1)
    out["pool_liquidity20"] = np.log(amount.where(amount > 0)).rolling(20).mean().median(axis=1)
    out["pool_count"] = count
    return out


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


def factor_breadth_features(stocks: Dict[str, pd.DataFrame]) -> Tuple[Dict[str, pd.Series], pd.DataFrame]:
    panels = compute_safety_factor_panel(stocks)
    breadths: Dict[str, pd.Series] = {}
    factor_matrix = {}
    z_panels: Dict[str, pd.DataFrame] = {}
    for name, panel in panels.items():
        z = cross_section_zscore(panel)
        z_panels[name] = z
        count = z.notna().sum(axis=1).where(lambda s: s >= 10)
        breadth = (z > 0).sum(axis=1) / count
        breadth.name = name
        breadths[name] = breadth
        factor_matrix[name] = z.stack(future_stack=True)

    groups = {
        "group_safety_risk": [n for n in breadths if n.startswith("safe_")],
        "group_momentum_trend": [
            n for n in breadths
            if n.startswith("alpha_mom") or n.startswith("alpha_ma") or n.startswith("alpha_channel") or n.startswith("alpha_efficiency")
        ],
        "group_volume_price": [n for n in breadths if "pv_corr" in n or "volume" in n or "intraday" in n],
        "group_reversal": [n for n in breadths if "reversal" in n or "skew" in n],
    }
    for group, names in groups.items():
        if not names:
            continue
        score = pd.concat([z_panels[name].stack(future_stack=True).rename(name) for name in names], axis=1).mean(axis=1).unstack()
        count = score.notna().sum(axis=1).where(lambda s: s >= 10)
        breadths[group] = ((score > 0).sum(axis=1) / count).rename(group)
        factor_matrix[group] = score.stack(future_stack=True)

    combo_core = [
        name for name in [
            "alpha_pv_corr_20",
            "alpha_reversal_20",
            "alpha_reversal_5",
            "alpha_pv_corr_60",
            "safe_low_vol_60",
            "safe_low_vol_120",
            "safe_liquidity_amihud_60",
            "alpha_efficiency_60",
            "safe_cvar_60_5",
            "alpha_mom_60_skip20",
            "safe_downside_vol_60",
            "alpha_intraday_strength_60",
            "alpha_td9_buy_setup_4_9",
            "alpha_td9_sell_pressure_4_9",
        ]
        if name in z_panels
    ]
    combo_specs: Dict[str, Tuple[str, ...]] = {}
    for left, right in itertools.combinations(combo_core, 2):
        combo_specs[f"combo2__{left}__{right}"] = (left, right)
    for trio in itertools.combinations(combo_core[:9], 3):
        combo_specs[f"combo3__{'__'.join(trio)}"] = trio
    curated = {
        "combo_reversal_pv_td9": ("alpha_reversal_20", "alpha_pv_corr_20", "alpha_td9_buy_setup_4_9"),
        "combo_reversal_lowvol_liq": ("alpha_reversal_20", "safe_low_vol_60", "safe_liquidity_amihud_60"),
        "combo_td9_lowrisk": ("alpha_td9_buy_setup_4_9", "safe_low_vol_60", "safe_cvar_60_5"),
        "combo_momentum_quality": ("alpha_mom_60_skip20", "alpha_efficiency_60", "safe_low_vol_60"),
        "combo_volume_reversal": ("alpha_pv_corr_20", "alpha_volume_mom_20_60", "alpha_reversal_20"),
    }
    for name, members in curated.items():
        if all(member in z_panels for member in members):
            combo_specs[name] = members

    for combo_name, members in combo_specs.items():
        score = pd.concat([z_panels[member].stack(future_stack=True).rename(member) for member in members], axis=1).mean(axis=1).unstack()
        count = score.notna().sum(axis=1).where(lambda s: s >= 10)
        breadths[combo_name] = ((score > 0).sum(axis=1) / count).rename(combo_name)
        factor_matrix[combo_name] = score.stack(future_stack=True)

    flat = pd.DataFrame(factor_matrix)
    return breadths, flat.corr(method="spearman")


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
    return {f"{prefix}_{k}": v for k, v in metrics.items()}


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
    if pd.notna(exposure) and exposure < 0.08:
        score -= 0.25
    return score


def evaluate_spec(
    spec: LongRunSpec,
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
        tr = compute_performance_metrics(returns, start, train_end, risk_free)
        te = compute_performance_metrics(returns, test_start, end, risk_free)
        tr["code"] = code
        te["code"] = code
        train_rows.append(tr)
        test_rows.append(te)
    row: Dict[str, object] = asdict(spec)
    row["strategy"] = spec.name
    row.update(aggregate_metrics(train_rows, "pool_train"))
    row.update(aggregate_metrics(test_rows, "pool_test"))
    return row


def write_checkpoint(rows: List[Dict[str, object]], path: Path) -> None:
    if rows:
        pd.DataFrame(rows).to_csv(path, index=False, encoding="utf-8-sig")


def load_checkpoint(path: Path) -> Tuple[List[Dict[str, object]], set[str]]:
    if not path.exists():
        return [], set()
    df = pd.read_csv(path)
    if df.empty:
        return [], set()
    return df.to_dict("records"), set(df["strategy"].astype(str))


def buy_hold_returns(asset: pd.DataFrame) -> pd.Series:
    open_px = asset["open"]
    return open_px.shift(-1).div(open_px).sub(1).replace([np.inf, -np.inf], np.nan).fillna(0.0)


def pct(value: float) -> str:
    return "nan" if pd.isna(value) else f"{value * 100:.2f}%"


def num(value: float) -> str:
    return "nan" if pd.isna(value) else f"{value:.3f}"


def markdown_table(df: pd.DataFrame) -> str:
    headers = list(df.columns)
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for _, row in df.iterrows():
        vals = []
        for col in headers:
            value = row[col]
            vals.append(f"{value:.4f}" if isinstance(value, (float, np.floating)) else str(value))
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines)


def describe_factor_signal(signal: Optional[str]) -> str:
    if not signal or pd.isna(signal):
        return "未启用额外因子宽度过滤。"
    glossary = {
        "alpha_td9_buy_setup_4_9": "神奇九转买入结构进度：收盘价连续低于 4 日前收盘价时计数推进，越高表示越接近 9 转买入结构。",
        "alpha_td9_sell_pressure_4_9": "神奇九转卖出压力的反向安全信号：收盘价连续高于 4 日前收盘价时代表卖压推进，本因子反向处理后，数值越高表示九转卖压越轻。",
        "alpha_intraday_strength_60": "60 日日内强度：收盘价在每日高低价区间中的位置均值，越高表示收盘更靠近日内高位，短中期承接更强。",
        "alpha_reversal_5": "5 日反转：最近 5 日收益的相反数，越高表示短期越超跌。",
        "alpha_reversal_20": "20 日反转：最近 20 日收益的相反数，越高表示阶段性越超跌。",
        "alpha_pv_corr_20": "20 日价量相关反向因子：收益率与成交量变化的滚动相关系数取反，越高表示上涨放量/下跌缩量压力更轻。",
        "alpha_pv_corr_60": "60 日价量相关反向因子：收益率与成交量变化的滚动相关系数取反，越高表示中期价量压力更轻。",
        "safe_low_vol_60": "60 日低波动因子：实现波动率取反，越高表示波动越低。",
        "safe_low_vol_120": "120 日低波动因子：实现波动率取反，越高表示中期波动越低。",
        "safe_downside_vol_60": "60 日下行波动因子：下跌日波动率取反，越高表示下行波动越低。",
        "safe_liquidity_amihud_60": "60 日 Amihud 流动性安全因子：价格冲击成本取反，越高表示流动性越好。",
        "safe_cvar_60_5": "60 日 CVaR 安全因子：尾部亏损风险取反，越高表示尾部风险越低。",
        "alpha_efficiency_60": "60 日趋势效率：净涨跌幅与路径波动的比值，越高表示趋势更顺。",
        "alpha_mom_60_skip20": "跳过近 20 日后的 60 日动量，用于降低短期反转噪声。",
    }
    if signal.startswith("combo"):
        members = signal.split("__")[1:]
        details = [glossary.get(member, member) for member in members]
        return "组合因子宽度：先对成员因子做成分股横截面 z-score，再求平均组合分数，最后计算组合分数大于 0 的成分股占比。成员解释：" + "；".join(details) + "。"
    return glossary.get(signal, f"{signal}：本地因子库中的横截面因子宽度信号，数值表示该因子得分大于 0 的成分股占比。")


def write_report(
    path: Path,
    best: pd.Series,
    best_spec: LongRunSpec,
    target_metrics: Dict[str, Dict[str, float]],
    hold_metrics: Dict[str, Dict[str, float]],
    latest: Dict[str, object],
    top_table: pd.DataFrame,
    output_paths: Dict[str, Path],
    args: argparse.Namespace,
    candidate_count: int,
    missing: List[str],
) -> None:
    factor_text = best_spec.factor_signal or "无"
    factor_rule = (
        "无额外因子广度过滤。"
        if best_spec.factor_signal is None
        else f"因子广度 `{best_spec.factor_signal}` >= {best_spec.factor_buy:.0%} 才允许买入，<= {best_spec.factor_sell:.0%} 触发退出。"
    )
    factor_description = describe_factor_signal(best_spec.factor_signal)
    factor_threshold_text = (
        "- 因子广度阈值：未启用。"
        if best_spec.factor_signal is None
        else f"- `fb{int((best_spec.factor_buy or 0) * 100)}` / `fs{int((best_spec.factor_sell or 0) * 100)}`：因子广度买入阈值/卖出阈值；买入阈值更高、卖出阈值更低，是为了减少来回交易。"
    )
    text = f"""# 588200 长跑因子策略搜索报告

生成时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

## 搜索口径

- 候选策略数量：{candidate_count}
- 训练期：{args.start} 至 {args.train_end}
- 样本外：{(pd.to_datetime(args.train_end) + pd.Timedelta(days=1)).date()} 至 {args.end}
- 选择规则：只按同类 ETF 训练池 `train_score` 选择最优，再报告 588200 样本外表现。
- 最终交易对象：`{args.target}`
- 成分股缺失代码：{", ".join(missing) if missing else "无"}

## 最优策略

策略：`{best_spec.name}`

- 策略族：`{best_spec.family}`
- 588200 动量窗口：{best_spec.mom_window} 日
- 成分股 MA60 广度买入/卖出阈值：{best_spec.breadth_buy:.0%} / {best_spec.breadth_sell:.0%}
- 588200 波动率窗口/上限分位：{best_spec.vol_window} 日 / {best_spec.vol_max:.0%}
- 额外因子广度：`{factor_text}`
- 是否要求成分股池 20 日收益中位数为正：{best_spec.require_pool_mom}

## 指标名称解释

- `mom{best_spec.mom_window}`：588200 自身 {best_spec.mom_window} 日动量，大于 0 表示当前价格高于 {best_spec.mom_window} 个交易日前。
- `breadth_ma60`：588200 成分股池中，收盘价站上各自 60 日均线的股票占比。
- `vol{best_spec.vol_window}` / `vp{int(best_spec.vol_max * 100)}`：588200 {best_spec.vol_window} 日波动率分位，`vp{int(best_spec.vol_max * 100)}` 表示只在波动率不高于 {best_spec.vol_max:.0%} 分位时允许买入。
- `{factor_text}`：{factor_description}
{factor_threshold_text}

## 买点规则

每天收盘后检查，全部满足时，下一交易日开盘买入或继续持有 588200：

1. 588200 的 {best_spec.mom_window} 日动量大于 0。
2. 成分股池 MA60 广度不低于 {best_spec.breadth_buy:.0%}。
3. 588200 的 {best_spec.vol_window} 日波动率分位不高于 {best_spec.vol_max:.0%}。
4. {factor_rule}

## 卖点规则

任一条件触发时，下一交易日开盘卖出或继续空仓：

1. 588200 的 {best_spec.mom_window} 日动量小于等于 0。
2. 成分股池 MA60 广度跌到 {best_spec.breadth_sell:.0%} 或更低。
3. 588200 的 {best_spec.vol_window} 日波动率分位高于 {min(best_spec.vol_max + 0.10, 0.98):.0%}。
4. 如果启用额外因子广度，则因子广度跌破卖出阈值。

## 588200 回测结果

| 区间 | 策略年化 | 策略夏普 | 策略最大回撤 | 买入持有年化 | 买入持有夏普 | 买入持有最大回撤 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 训练期 | {pct(target_metrics['train']['annual_return'])} | {num(target_metrics['train']['sharpe'])} | {pct(target_metrics['train']['max_drawdown'])} | {pct(hold_metrics['train']['annual_return'])} | {num(hold_metrics['train']['sharpe'])} | {pct(hold_metrics['train']['max_drawdown'])} |
| 样本外 | {pct(target_metrics['test']['annual_return'])} | {num(target_metrics['test']['sharpe'])} | {pct(target_metrics['test']['max_drawdown'])} | {pct(hold_metrics['test']['annual_return'])} | {num(hold_metrics['test']['sharpe'])} | {pct(hold_metrics['test']['max_drawdown'])} |
| 全样本 | {pct(target_metrics['full']['annual_return'])} | {num(target_metrics['full']['sharpe'])} | {pct(target_metrics['full']['max_drawdown'])} | {pct(hold_metrics['full']['annual_return'])} | {num(hold_metrics['full']['sharpe'])} | {pct(hold_metrics['full']['max_drawdown'])} |

## 跨 ETF 泛化

- 训练池中位夏普：{num(best['pool_train_median_sharpe'])}
- 训练池正收益比例：{pct(best['pool_train_positive_ratio'])}
- 样本外中位夏普：{num(best['pool_test_median_sharpe'])}
- 样本外正收益比例：{pct(best['pool_test_positive_ratio'])}
- 样本外中位最大回撤：{pct(best['pool_test_median_max_drawdown'])}

## 最新信号

- 信号日期：{latest['signal_date']}
- 588200 收盘价：{latest['close']:.4f}
- 下一交易日计划：`{latest['next_action']}`

## 参数排名前十

{markdown_table(top_table)}

## 输出文件

- 策略排名：`{output_paths['summary']}`
- 588200 信号：`{output_paths['signal']}`
- 因子相关性矩阵：`{output_paths['factor_corr']}`
- 最优配置：`{output_paths['config']}`
- 断点文件：`{output_paths['checkpoint']}`
- 本报告：`{path}`

## 限制

- 成分股池仍是 2025Q4 静态池。
- 因子广度来自本地行情可计算因子，基本面 point-in-time 因子尚未纳入。
- 本报告用于研究，不构成投资建议。
"""
    path.write_text(text, encoding="utf-8")


def main() -> None:
    args = parse_args()
    start = pd.to_datetime(args.start)
    train_end = pd.to_datetime(args.train_end)
    test_start = train_end + pd.Timedelta(days=1)
    end = pd.to_datetime(args.end)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = Path(args.run_dir) if args.run_dir else Path(args.output_dir) / f"longrun_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = run_dir / "strategy_summary_checkpoint.csv"

    print("Loading data...", flush=True)
    astock_root = Path(args.astock_root)
    etfs = load_etfs(astock_root)
    stocks, missing = load_stock_pool(astock_root)
    stocks = {code: df.loc[start:end].copy() for code, df in stocks.items()}
    breadth = build_breadth_features(stocks)
    factor_breadths, factor_corr = factor_breadth_features(stocks)
    selected = select_similar_etfs(etfs, args.target, start, train_end, args.min_overlap, args.min_corr, args.max_similar_etfs)
    selected_codes = selected["code"].tolist()
    specs = make_specs(factor_breadths.keys())
    print(f"ETF series loaded: {len(etfs)}", flush=True)
    print(f"Stock pool loaded: {len(stocks)}, missing: {len(missing)}", flush=True)
    print(f"Factor breadth signals: {len(factor_breadths)}", flush=True)
    print(f"Strategy specs: {len(specs)}", flush=True)

    print("Building signal cache...", flush=True)
    target_asset = etfs[args.target].loc[start:end].copy()
    signal_cache = {
        code: build_signal_cache(etfs[code].loc[start:end].copy(), breadth, factor_breadths, specs)
        for code in selected_codes
    }
    signal_cache[args.target] = build_signal_cache(target_asset, breadth, factor_breadths, specs)

    rows, completed = load_checkpoint(checkpoint_path) if args.resume else ([], set())
    if completed:
        print(f"Resuming checkpoint: {len(completed)} completed", flush=True)
    remaining = [spec for spec in specs if spec.name not in completed]
    print(f"Remaining specs: {len(remaining)}", flush=True)
    for i, spec in enumerate(remaining, start=1):
        row = evaluate_spec(spec, selected_codes, etfs, signal_cache, start, train_end, test_start, end, args.cost_rate, args.risk_free)
        desired = signal_from_cache(signal_cache[args.target], spec)
        _nav, target_returns, _position = backtest_binary_position(target_asset, desired, cost_rate=args.cost_rate)
        row.update(flatten("target_train", compute_performance_metrics(target_returns, start, train_end, args.risk_free)))
        row.update(flatten("target_test", compute_performance_metrics(target_returns, test_start, end, args.risk_free)))
        row.update(flatten("target_full", compute_performance_metrics(target_returns, start, end, args.risk_free)))
        row["train_score"] = train_score(pd.Series(row))
        rows.append(row)
        if args.checkpoint_every > 0 and (i % args.checkpoint_every == 0 or i == len(remaining)):
            write_checkpoint(rows, checkpoint_path)
            print(f"Checkpoint saved: {len(rows)}/{len(specs)} -> {checkpoint_path}", flush=True)

    write_checkpoint(rows, checkpoint_path)
    summary = pd.DataFrame(rows).sort_values(["train_score", "pool_test_median_sharpe"], ascending=False).reset_index(drop=True)
    best = summary.iloc[0]
    best_spec = spec_from_row(best)
    best_desired = signal_from_cache(signal_cache[args.target], best_spec)
    target_nav, target_returns, target_position = backtest_binary_position(target_asset, best_desired, cost_rate=args.cost_rate)
    hold_returns = buy_hold_returns(target_asset)
    target_metrics = {
        "train": compute_performance_metrics(target_returns, start, train_end, args.risk_free),
        "test": compute_performance_metrics(target_returns, test_start, end, args.risk_free),
        "full": compute_performance_metrics(target_returns, start, end, args.risk_free),
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
        "next_action": "BUY_OR_HOLD_588200" if bool(best_desired.loc[last_date]) else "EMPTY_OR_SELL_588200",
    }

    out_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    summary_path = run_dir / f"strategy_summary_{out_ts}.csv"
    signal_path = run_dir / f"target_588200_signal_{out_ts}.csv"
    corr_path = run_dir / f"factor_spearman_corr_{out_ts}.csv"
    config_path = run_dir / f"best_config_{out_ts}.json"
    report_path = run_dir / f"report_{out_ts}.md"
    summary.to_csv(summary_path, index=False, encoding="utf-8-sig")
    factor_corr.to_csv(corr_path, encoding="utf-8-sig")
    pd.DataFrame({
        "open": target_asset["open"],
        "close": target_asset["close"],
        "desired_after_close": best_desired,
        "position_next_open": target_position,
        "strategy_nav": target_nav,
        "buy_hold_nav": (1 + hold_returns).cumprod(),
    }).to_csv(signal_path, index=True, index_label="date", encoding="utf-8-sig")
    config_path.write_text(
        json.dumps(
            {
                "best_strategy": asdict(best_spec),
                "latest_signal": latest,
                "candidate_count": int(len(summary)),
                "factor_signal_count": int(len(factor_breadths)),
                "selected_etfs": selected_codes,
                "missing_stock_codes": missing,
                "run_dir": str(run_dir),
                "checkpoint": str(checkpoint_path),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    top_cols = [
        "strategy", "family", "factor_signal", "train_score",
        "pool_train_median_sharpe", "pool_test_median_sharpe",
        "target_test_annual_return", "target_test_sharpe", "target_test_max_drawdown",
    ]
    write_report(
        report_path,
        best,
        best_spec,
        target_metrics,
        hold_metrics,
        latest,
        summary.head(10)[top_cols],
        {
            "summary": summary_path,
            "signal": signal_path,
            "factor_corr": corr_path,
            "config": config_path,
            "checkpoint": checkpoint_path,
        },
        args,
        len(summary),
        missing,
    )

    print("\nLong-run search completed", flush=True)
    print(f"best_strategy: {best_spec.name}", flush=True)
    print(f"candidate_count: {len(summary)}", flush=True)
    print(f"588200 test annual return: {target_metrics['test']['annual_return'] * 100:.2f}%", flush=True)
    print(f"588200 test Sharpe: {target_metrics['test']['sharpe']:.3f}", flush=True)
    print(f"588200 test max drawdown: {target_metrics['test']['max_drawdown'] * 100:.2f}%", flush=True)
    print(f"latest plan: {latest['next_action']} as of {latest['signal_date']}", flush=True)
    print(f"report: {report_path}", flush=True)


if __name__ == "__main__":
    main()
