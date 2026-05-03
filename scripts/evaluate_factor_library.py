"""Evaluate local factor library candidates.

This first version evaluates the new safety/formula-alpha factors on the
588200 constituent stock pool and writes IC, coverage, and correlation reports.
"""

from __future__ import annotations

import argparse
import sys
import warnings
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=RuntimeWarning)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.factors.safety import SAFETY_FACTORS, compute_safety_factor_panel


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate local factor library.")
    parser.add_argument("--astock-root", default=str(DEFAULT_ASTOCK_ROOT), help="AStock data root.")
    parser.add_argument("--start", default="2022-10-26", help="Start date.")
    parser.add_argument("--end", default="2026-04-08", help="End date.")
    parser.add_argument("--forward-days", type=int, default=20, help="Forward return horizon.")
    parser.add_argument(
        "--output-dir",
        default=str(PROJECT_ROOT / "outputs" / "factor_library_eval"),
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


def load_588200_stock_pool(astock_root: Path) -> tuple[Dict[str, pd.DataFrame], List[str]]:
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
    return stocks, missing


def rank_ic_series(factor_panel: pd.DataFrame, forward_ret: pd.DataFrame) -> pd.Series:
    values = {}
    for dt in factor_panel.index.intersection(forward_ret.index):
        f = factor_panel.loc[dt].dropna()
        r = forward_ret.loc[dt].dropna()
        common = f.index.intersection(r.index)
        if len(common) < 10:
            continue
        values[dt] = f.loc[common].rank().corr(r.loc[common].rank())
    return pd.Series(values, dtype=float)


def quantile_spread(factor_panel: pd.DataFrame, forward_ret: pd.DataFrame, q: float = 0.2) -> float:
    spreads = []
    for dt in factor_panel.index.intersection(forward_ret.index):
        f = factor_panel.loc[dt].dropna()
        r = forward_ret.loc[dt].dropna()
        common = f.index.intersection(r.index)
        if len(common) < 10:
            continue
        f = f.loc[common]
        r = r.loc[common]
        high = f >= f.quantile(1 - q)
        low = f <= f.quantile(q)
        if high.sum() == 0 or low.sum() == 0:
            continue
        spreads.append(r.loc[high].mean() - r.loc[low].mean())
    return float(np.nanmean(spreads)) if spreads else np.nan


def markdown_table(df: pd.DataFrame) -> str:
    headers = list(df.columns)
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for _, row in df.iterrows():
        values = []
        for col in headers:
            value = row[col]
            values.append(f"{value:.4f}" if isinstance(value, (float, np.floating)) else str(value))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def write_report(
    path: Path,
    summary_path: Path,
    summary: pd.DataFrame,
    corr_path: Path,
    args: argparse.Namespace,
    missing: List[str],
) -> None:
    top = summary.sort_values("ic_ir", ascending=False).head(20)
    lines = [
        "# 因子库体检报告",
        "",
        f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        f"- 样本：588200 2025Q4 成分股池",
        f"- 区间：{args.start} 至 {args.end}",
        f"- 前向收益窗口：{args.forward_days} 个交易日",
        f"- 缺失股票：{', '.join(missing) if missing else '无'}",
        "",
        "## IC 排名前二十",
        "",
        markdown_table(top),
        "",
        "## 解释",
        "",
        "- `ic_mean`：RankIC 均值，越高表示因子横截面排序越能解释未来收益。",
        "- `ic_ir`：IC 均值 / IC 标准差，越高越稳定。",
        "- `ic_positive_rate`：RankIC 为正的日期比例。",
        "- `quantile_spread`：最高 20% 分组未来收益均值减最低 20% 分组未来收益均值。",
        "- `coverage`：因子有效值覆盖率。",
        "",
        "## 输出文件",
        "",
        f"- 因子 IC 汇总：`{summary_path}`",
        f"- 因子相关性矩阵：`{corr_path}`",
        f"- 本报告：`{path}`",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = parse_args()
    astock_root = Path(args.astock_root)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = Path(args.output_dir) / timestamp
    run_dir.mkdir(parents=True, exist_ok=True)

    start = pd.to_datetime(args.start)
    end = pd.to_datetime(args.end)
    stocks, missing = load_588200_stock_pool(astock_root)
    stocks = {code: df.loc[start:end].copy() for code, df in stocks.items()}
    close = pd.DataFrame({code: df["close"] for code, df in stocks.items()}).sort_index()
    forward_ret = close.shift(-args.forward_days).div(close).sub(1)

    panels = compute_safety_factor_panel(stocks)
    rows = []
    flat_factors = {}
    for name, panel in panels.items():
        panel = panel.reindex(close.index)
        ic = rank_ic_series(panel, forward_ret)
        coverage = panel.notna().sum().sum() / panel.size if panel.size else np.nan
        rows.append(
            {
                "factor": name,
                "category": SAFETY_FACTORS[name].meta.category,
                "description": SAFETY_FACTORS[name].meta.description,
                "ic_mean": float(ic.mean()) if len(ic) else np.nan,
                "ic_std": float(ic.std()) if len(ic) else np.nan,
                "ic_ir": float(ic.mean() / ic.std()) if len(ic) and ic.std() > 0 else np.nan,
                "ic_positive_rate": float((ic > 0).mean()) if len(ic) else np.nan,
                "quantile_spread": quantile_spread(panel, forward_ret),
                "coverage": float(coverage),
                "ic_days": int(len(ic)),
            }
        )
        try:
            flat_factors[name] = panel.stack(future_stack=True)
        except TypeError:
            flat_factors[name] = panel.stack(dropna=False)

    summary = pd.DataFrame(rows).sort_values("ic_ir", ascending=False).reset_index(drop=True)
    factor_matrix = pd.DataFrame(flat_factors)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        corr = factor_matrix.corr(method="spearman")

    summary_path = run_dir / f"factor_ic_summary_{timestamp}.csv"
    corr_path = run_dir / f"factor_spearman_corr_{timestamp}.csv"
    report_path = run_dir / f"report_{timestamp}.md"
    summary.to_csv(summary_path, index=False, encoding="utf-8-sig")
    corr.to_csv(corr_path, encoding="utf-8-sig")
    write_report(report_path, summary_path, summary, corr_path, args, missing)

    print("Factor library evaluation")
    print("-------------------------")
    print(f"factors: {len(summary)}")
    print(f"stocks: {len(stocks)}")
    print(summary[["factor", "ic_mean", "ic_ir", "ic_positive_rate", "quantile_spread", "coverage"]].to_string(index=False))
    print(f"report: {report_path}")


if __name__ == "__main__":
    main()
