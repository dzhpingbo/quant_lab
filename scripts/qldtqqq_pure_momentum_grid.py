"""Pure momentum grid for QLD/TQQQ.

This is intentionally narrower than qldtqqq_turning_point_lab.py:
- No TD9, VIX, PE, fear/greed, Bollinger, or ML inputs.
- Signals are built only from asset/QQQ price momentum: MA crosses,
  price-vs-MA filters, ROC/time-series momentum, and Donchian breakouts.
- Position modes are either binary long/cash or momentum signal with volatility
  sizing. Volatility sizing is treated as risk sizing, not a signal input.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Mapping

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT_ROOT = ROOT / "outputs" / "qldtqqq_pure_momentum"
QLD_TQQQ_ROOT = ROOT / "outputs" / "qldtqqq_turning_points"
TARGETS = ("QLD", "TQQQ")
WF_START = "2014-01-01"
TEST_START = "2021-01-01"
FOLDS = (
    ("2014_2016", "2014-01-01", "2016-12-31"),
    ("2017_2019", "2017-01-01", "2019-12-31"),
    ("2020_2022", "2020-01-01", "2022-12-31"),
    ("2023_latest", "2023-01-01", None),
)


@dataclass(frozen=True)
class Candidate:
    name: str
    family: str
    source_symbol: str
    signal: pd.Series
    notes: str


def stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def pct(value) -> str:
    if value is None or pd.isna(value):
        return "nan"
    return f"{float(value) * 100:.2f}%"


def jclean(value):
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
    return jclean(obj)


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(jready(data), ensure_ascii=False, indent=2), encoding="utf-8")


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


def read_price_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    cols = {str(c).strip().lower(): c for c in df.columns}
    date_col = cols.get("date") or df.columns[0]
    dates = pd.to_datetime(df[date_col], errors="coerce")
    out = pd.DataFrame(index=dates)
    for name in ("open", "high", "low", "close", "volume"):
        source = cols.get(name)
        out[name] = pd.to_numeric(df[source], errors="coerce").to_numpy() if source is not None else np.nan
    out.index.name = "date"
    out = out.dropna(subset=["close"]).sort_index()
    out = out[~out.index.duplicated(keep="last")]
    for col in ("open", "high", "low"):
        out[col] = out[col].fillna(out["close"])
    out["volume"] = out["volume"].fillna(0.0)
    return out[["open", "high", "low", "close", "volume"]]


def latest_turning_run() -> Path:
    runs = []
    if QLD_TQQQ_ROOT.exists():
        for path in QLD_TQQQ_ROOT.glob("qldtqqq_turning_*"):
            if (
                (path / "report.md").exists()
                and (path / "best_strategy_summary.csv").exists()
                and (path / "updated_data" / "QLD.csv").exists()
                and (path / "updated_data" / "TQQQ.csv").exists()
                and (path / "updated_data" / "QQQ.csv").exists()
            ):
                runs.append(path)
    if not runs:
        raise RuntimeError("No qldtqqq_turning_* run with updated_data for QLD/TQQQ/QQQ.")
    return max(runs, key=lambda p: p.stat().st_mtime)


def load_data(data_run: Path) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    data = {}
    rows = []
    for symbol in ("QLD", "TQQQ", "QQQ"):
        path = data_run / "updated_data" / f"{symbol}.csv"
        if not path.exists():
            raise FileNotFoundError(path)
        frame = read_price_csv(path)
        data[symbol] = frame
        rows.append(
            {
                "symbol": symbol,
                "path": str(path),
                "first": frame.index.min().strftime("%Y-%m-%d"),
                "last": frame.index.max().strftime("%Y-%m-%d"),
                "rows": int(len(frame)),
            }
        )
    latest = min(frame.index.max() for frame in data.values())
    for key in list(data):
        data[key] = data[key].loc[data[key].index <= latest].copy()
    status = pd.DataFrame(rows)
    status["used_latest_cutoff"] = latest.strftime("%Y-%m-%d")
    return data, status


def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window).mean()


def ema(series: pd.Series, window: int) -> pd.Series:
    return series.ewm(span=window, adjust=False).mean()


def ma(series: pd.Series, window: int, ma_type: str) -> pd.Series:
    return ema(series, window) if ma_type == "ema" else sma(series, window)


def state_from_score(score: pd.Series, enter: float, exit_: float, name: str) -> pd.Series:
    held = False
    out = []
    for value in score.astype(float):
        if np.isnan(value):
            out.append(1.0 if held else 0.0)
            continue
        if not held and value >= enter:
            held = True
        elif held and value <= exit_:
            held = False
        out.append(1.0 if held else 0.0)
    return pd.Series(out, index=score.index, name=name)


def monthly_signal(raw: pd.Series, name: str) -> pd.Series:
    months = pd.Series(raw.index, index=raw.index).dt.to_period("M")
    month_end = months.ne(months.shift(-1))
    return raw.where(month_end).ffill().fillna(0.0).rename(name)


def donchian_signal(frame: pd.DataFrame, entry: int, exit_: int, name: str) -> pd.Series:
    close = frame["close"].astype(float)
    high = frame["high"].rolling(entry).max().shift(1)
    low = frame["low"].rolling(exit_).min().shift(1)
    held = False
    out = []
    for c, h, l in zip(close, high, low):
        if not held and pd.notna(h) and c > h:
            held = True
        elif held and pd.notna(l) and c < l:
            held = False
        out.append(1.0 if held else 0.0)
    return pd.Series(out, index=frame.index, name=name)


def build_candidates(target: str, data: Mapping[str, pd.DataFrame]) -> list[Candidate]:
    index = data[target].index
    sources = {"asset": data[target].reindex(index).ffill(), "qqq": data["QQQ"].reindex(index).ffill()}
    candidates: dict[str, Candidate] = {}

    def add(name: str, family: str, source_symbol: str, signal: pd.Series, notes: str) -> None:
        candidates[name] = Candidate(name, family, source_symbol, signal.reindex(index).ffill().fillna(0.0).clip(0, 1), notes)

    add("buy_hold", "baseline", target, pd.Series(1.0, index=index), "Always hold target.")

    fast_windows = (2, 3, 5, 8, 10, 13, 20, 21, 30, 40, 50)
    slow_windows = (20, 30, 40, 50, 60, 80, 100, 120, 150, 180, 200, 250)
    bands = (0.0, 0.0025, 0.005, 0.01, 0.02)
    for source_name, frame in sources.items():
        close = frame["close"].astype(float)
        for ma_type in ("sma", "ema"):
            for fast in fast_windows:
                for slow in slow_windows:
                    if fast >= slow:
                        continue
                    ratio = ma(close, fast, ma_type).div(ma(close, slow, ma_type).replace(0, np.nan)) - 1.0
                    for band in bands:
                        name = f"{source_name}_{ma_type}_cross_f{fast}_s{slow}_b{band:.4f}"
                        sig = state_from_score(ratio, band, -band, name)
                        add(
                            name,
                            "ma_cross",
                            source_name,
                            sig,
                            f"{source_name.upper()} {ma_type.upper()} fast {fast} over slow {slow}; enter/exit hysteresis band {band:.2%}.",
                        )

            for window in (50, 60, 80, 100, 120, 150, 180, 200, 220, 250):
                dist = close.div(ma(close, window, ma_type).replace(0, np.nan)) - 1.0
                for band in bands:
                    name = f"{source_name}_{ma_type}_price_ma{window}_b{band:.4f}"
                    sig = state_from_score(dist, band, -band, name)
                    add(
                        name,
                        "price_vs_ma",
                        source_name,
                        sig,
                        f"{source_name.upper()} close above/below {ma_type.upper()}{window}; hysteresis band {band:.2%}.",
                    )

        for window in (20, 40, 60, 80, 100, 120, 180, 252):
            roc = close.pct_change(window)
            for enter, exit_ in ((0.0, 0.0), (0.02, -0.02), (0.04, -0.02), (0.06, 0.0)):
                name = f"{source_name}_roc{window}_e{enter:.2f}_x{exit_:.2f}"
                sig = state_from_score(roc, enter, exit_, name)
                add(
                    name,
                    "time_series_momentum_roc",
                    source_name,
                    sig,
                    f"{source_name.upper()} {window}-day return momentum; enter >= {enter:.0%}, exit <= {exit_:.0%}.",
                )

        for entry, exit_ in ((20, 10), (40, 20), (55, 20), (80, 40), (120, 60), (180, 90)):
            name = f"{source_name}_donchian_e{entry}_x{exit_}"
            add(
                name,
                "donchian_breakout",
                source_name,
                donchian_signal(frame, entry, exit_, name),
                f"{source_name.upper()} Donchian breakout: enter above prior {entry}-day high, exit below prior {exit_}-day low.",
            )

        for months, days in ((6, 126), (8, 168), (10, 210), (12, 252)):
            dist = close.div(sma(close, days).replace(0, np.nan)) - 1.0
            for band in (0.0, 0.005, 0.01):
                name = f"{source_name}_monthly_sma{months}m_b{band:.4f}"
                raw = state_from_score(dist, band, -band, name)
                add(
                    name,
                    "monthly_ma_timing",
                    source_name,
                    monthly_signal(raw, name),
                    f"{source_name.upper()} month-end timing against approximate {months}-month SMA; band {band:.2%}.",
                )

    return list(candidates.values())


def weighted_backtest(asset: pd.DataFrame, signal: pd.Series, mode: str, cost: float, target: str) -> dict[str, pd.Series]:
    index = asset.index
    open_price = asset["open"].astype(float).ffill()
    close = asset["close"].astype(float).ffill()
    sig = signal.reindex(index).ffill().fillna(0.0).clip(0, 1)
    target_at_open = sig.shift(1).fillna(0.0)
    if mode == "vol_target":
        vol_target = 0.20 if target == "QLD" else 0.25
        vol = close.pct_change(fill_method=None).rolling(20).std() * math.sqrt(252)
        weight = target_at_open * (vol_target / vol.replace(0, np.nan)).clip(0, 1).shift(1).fillna(0.0)
    else:
        weight = target_at_open
    weight = weight.clip(0, 1).rename("position_weight")

    prev_weight = weight.shift(1).fillna(0.0)
    open_ret = open_price.pct_change(fill_method=None).fillna(0.0)
    turnover = (weight - prev_weight).abs()
    returns = (prev_weight * open_ret - turnover * cost).rename("returns")
    value = (1.0 + returns.fillna(0.0)).cumprod().rename("value")
    in_pos = weight > 0.01
    prev = in_pos.shift(1, fill_value=False).astype(bool)
    entries = in_pos & ~prev
    exits = ~in_pos & prev
    return {"returns": returns, "position": weight, "value": value, "entries": entries, "exits": exits, "desired": sig}


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
        return {"total_return": np.nan, "annual_return": np.nan, "sharpe": np.nan, "sortino": np.nan, "max_drawdown": np.nan, "calmar": np.nan, "exposure": np.nan, "avg_weight": np.nan, "trades": 0, "years": 0.0}
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


def cycle_metrics(result: Mapping[str, pd.Series]) -> dict:
    out = {}
    annuals = []
    calmars = []
    pass_count = 0
    cycle_count = 0
    for name, start, end in FOLDS:
        metric = metrics_from(result, start, end)
        for key in ("annual_return", "max_drawdown", "sharpe", "calmar"):
            out[f"cycle_{name}_{key}"] = metric[key]
        if not pd.isna(metric["annual_return"]) and metric["years"] >= 0.75:
            annuals.append(metric["annual_return"])
            if not pd.isna(metric["calmar"]):
                calmars.append(metric["calmar"])
            cycle_count += 1
            if metric["annual_return"] > 0 and metric["max_drawdown"] > (-0.30 if metric["max_drawdown"] < -0.20 else -0.20):
                pass_count += 1
    out["cycle_positive_rate"] = pass_count / cycle_count if cycle_count else np.nan
    out["cycle_median_annual"] = float(np.nanmedian(annuals)) if annuals else np.nan
    out["cycle_median_calmar"] = float(np.nanmedian(calmars)) if calmars else np.nan
    return out


def score_row(row: Mapping[str, float], target: str) -> float:
    required = ("wf_annual_return", "wf_sharpe", "wf_calmar", "test_annual_return", "test_calmar", "wf_max_drawdown")
    if any(pd.isna(row.get(k, np.nan)) for k in required):
        return -999.0
    dd_soft = -0.22 if target == "QLD" else -0.30
    dd_hard = -0.35 if target == "QLD" else -0.45
    score = (
        0.24 * float(np.clip(row["wf_calmar"], -2, 4))
        + 0.20 * float(np.clip(row["test_calmar"], -2, 4))
        + 0.15 * float(np.clip(row["wf_sharpe"], -2, 3))
        + 0.13 * float(np.clip(row["test_sharpe"], -2, 3))
        + 0.15 * float(np.clip(row["wf_annual_return"], -0.5, 1.0))
        + 0.08 * float(np.clip(row["test_annual_return"], -0.5, 1.0))
        + 0.05 * float(np.clip(row.get("cycle_median_calmar", 0), -2, 4))
    )
    for key in ("wf_max_drawdown", "test_max_drawdown"):
        dd = float(row.get(key, 0.0))
        if dd < dd_soft:
            score -= 2.0 * (abs(dd) - abs(dd_soft))
        if dd < dd_hard:
            score -= 3.0 * (abs(dd) - abs(dd_hard))
    if row.get("wf_trades", 0) < 3:
        score -= 0.40
    if row.get("wf_exposure", 0.0) < 0.10:
        score -= 0.30
    return float(score)


def operations(target: str, asset: pd.DataFrame, result: Mapping[str, pd.Series], strategy: str) -> pd.DataFrame:
    rows = []
    for dt in asset.index:
        if bool(result["entries"].get(dt, False)):
            rows.append({"target": target, "strategy": strategy, "date": dt.strftime("%Y-%m-%d"), "action": "BUY_OPEN", "open": float(asset.loc[dt, "open"]), "close": float(asset.loc[dt, "close"]), "weight_after_open": float(result["position"].loc[dt])})
        if bool(result["exits"].get(dt, False)):
            rows.append({"target": target, "strategy": strategy, "date": dt.strftime("%Y-%m-%d"), "action": "SELL_OPEN", "open": float(asset.loc[dt, "open"]), "close": float(asset.loc[dt, "close"]), "weight_after_open": float(result["position"].loc[dt])})
    return pd.DataFrame(rows)


def evaluate_target(target: str, data: Mapping[str, pd.DataFrame], run_dir: Path, cost: float) -> dict:
    asset = data[target]
    candidates = build_candidates(target, data)
    rows = []
    results: dict[str, dict[str, pd.Series]] = {}
    for candidate in candidates:
        for mode in ("binary", "vol_target"):
            strategy_id = f"{candidate.name}__{mode}"
            try:
                result = weighted_backtest(asset, candidate.signal, mode, cost, target)
                wf = metrics_from(result, WF_START, None)
                test = metrics_from(result, TEST_START, None)
                full = metrics_from(result, None, None)
                row = {
                    "target": target,
                    "strategy": candidate.name,
                    "family": candidate.family,
                    "source_symbol": candidate.source_symbol,
                    "position_mode": mode,
                    "notes": candidate.notes,
                    "error": "",
                    "latest_date": asset.index.max().strftime("%Y-%m-%d"),
                }
                for prefix, metric in (("wf", wf), ("test", test), ("full", full)):
                    for key, value in metric.items():
                        row[f"{prefix}_{key}"] = value
                row.update(cycle_metrics(result))
                row["score"] = score_row(row, target)
                results[strategy_id] = result
            except Exception as exc:
                row = {"target": target, "strategy": candidate.name, "family": candidate.family, "source_symbol": candidate.source_symbol, "position_mode": mode, "notes": candidate.notes, "error": f"{type(exc).__name__}: {exc}", "score": -999.0}
            rows.append(row)
            if len(rows) % 500 == 0:
                pd.DataFrame(rows).sort_values("score", ascending=False).to_csv(run_dir / f"{target}_partial_rank.csv", index=False, encoding="utf-8-sig")
    rank = pd.DataFrame(rows).sort_values("score", ascending=False)
    rank.to_csv(run_dir / f"{target}_strategy_rank.csv", index=False, encoding="utf-8-sig")
    rank.head(50).to_csv(run_dir / f"{target}_top50_by_score.csv", index=False, encoding="utf-8-sig")
    rank.sort_values(["wf_annual_return", "score"], ascending=False).head(50).to_csv(run_dir / f"{target}_top50_by_wf_return.csv", index=False, encoding="utf-8-sig")
    best = rank.iloc[0].to_dict()
    result = results[f"{best['strategy']}__{best['position_mode']}"]
    ops = operations(target, asset, result, best["strategy"])
    nav = pd.DataFrame(
        {
            "open": asset["open"],
            "close": asset["close"],
            "signal_after_close": result["desired"],
            "position_weight_at_open": result["position"],
            "entry_at_open": result["entries"].astype(int),
            "exit_at_open": result["exits"].astype(int),
            "portfolio_value": result["value"],
            "portfolio_return": result["returns"],
        }
    )
    ops.to_csv(run_dir / f"{target}_best_operations.csv", index=False, encoding="utf-8-sig")
    nav.to_csv(run_dir / f"{target}_best_signal_nav.csv", encoding="utf-8-sig")
    return {"target": target, "rank": rank, "best": best, "result": result, "operations": ops, "nav": nav}


def find_baseline() -> tuple[Path | None, pd.DataFrame]:
    runs = []
    if QLD_TQQQ_ROOT.exists():
        for path in QLD_TQQQ_ROOT.glob("qldtqqq_turning_*"):
            summary = path / "best_strategy_summary.csv"
            if summary.exists():
                runs.append(path)
    if not runs:
        return None, pd.DataFrame()
    latest = max(runs, key=lambda p: p.stat().st_mtime)
    return latest, pd.read_csv(latest / "best_strategy_summary.csv")


def compact_best_rows(summaries: list[dict], baseline_run: Path | None, baseline: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for item in summaries:
        best = item["best"]
        base = baseline[baseline["target"] == item["target"]].iloc[0].to_dict() if not baseline.empty and "target" in baseline and (baseline["target"] == item["target"]).any() else {}
        base_wf = float(str(base.get("wf_annual_return", "nan")).replace("%", "")) / 100 if base else np.nan
        base_dd = float(str(base.get("wf_max_drawdown", "nan")).replace("%", "")) / 100 if base else np.nan
        rows.append(
            {
                "target": item["target"],
                "pure_momentum_strategy": best["strategy"],
                "family": best["family"],
                "source_symbol": best["source_symbol"],
                "position_mode": best["position_mode"],
                "score": round(float(best["score"]), 4),
                "wf_annual_return": pct(best["wf_annual_return"]),
                "wf_max_drawdown": pct(best["wf_max_drawdown"]),
                "wf_sharpe": round(float(best["wf_sharpe"]), 3),
                "wf_calmar": round(float(best["wf_calmar"]), 3),
                "test_annual_return": pct(best["test_annual_return"]),
                "test_max_drawdown": pct(best["test_max_drawdown"]),
                "test_calmar": round(float(best["test_calmar"]), 3),
                "wf_exposure": pct(best["wf_exposure"]),
                "wf_avg_weight": pct(best["wf_avg_weight"]),
                "wf_trades": int(best["wf_trades"]),
                "combo_strategy": base.get("strategy", ""),
                "combo_wf_annual_return": base.get("wf_annual_return", ""),
                "combo_wf_max_drawdown": base.get("wf_max_drawdown", ""),
                "pure_minus_combo_annual": pct(best["wf_annual_return"] - base_wf) if not pd.isna(base_wf) else "",
                "pure_minus_combo_drawdown": pct(best["wf_max_drawdown"] - base_dd) if not pd.isna(base_dd) else "",
                "baseline_run": str(baseline_run) if baseline_run else "",
            }
        )
    return pd.DataFrame(rows)


def write_report(run_dir: Path, summaries: list[dict], data_status: pd.DataFrame, baseline_run: Path | None, baseline: pd.DataFrame, cost: float) -> None:
    best_rows = compact_best_rows(summaries, baseline_run, baseline)
    best_rows.to_csv(run_dir / "best_pure_momentum_summary.csv", index=False, encoding="utf-8-sig")
    lines = [
        "# QLD/TQQQ Pure Momentum Grid Report",
        "",
        f"- Run directory: `{run_dir}`",
        f"- Data run: `{data_status['path'].iloc[0] if not data_status.empty else ''}`",
        f"- Walk-forward OOS starts: `{WF_START}`",
        f"- Test starts: `{TEST_START}`",
        f"- Execution: signal after close, target position at next open.",
        f"- Cost model: one-way `{cost:.2%}`.",
        "- Inputs: only QLD/TQQQ/QQQ price momentum. No TD9, VIX, PE, fear/greed, Bollinger, or ML.",
        "",
        "## Data Status",
        "",
        md_table(data_status),
        "",
        "## Best Pure Momentum vs qldtqqq Combo",
        "",
        md_table(best_rows),
    ]
    for item in summaries:
        best = item["best"]
        lines += [
            "",
            f"## {item['target']} Best Pure Momentum",
            "",
            f"- Strategy: `{best['strategy']}`",
            f"- Family/source/mode: `{best['family']}` / `{best['source_symbol']}` / `{best['position_mode']}`",
            f"- Rule: {best['notes']}",
            f"- Walk-forward annual/maxDD/sharpe/calmar: {pct(best['wf_annual_return'])} / {pct(best['wf_max_drawdown'])} / {best['wf_sharpe']:.3f} / {best['wf_calmar']:.3f}",
            f"- Test annual/maxDD/sharpe/calmar: {pct(best['test_annual_return'])} / {pct(best['test_max_drawdown'])} / {best['test_sharpe']:.3f} / {best['test_calmar']:.3f}",
            f"- Full annual/maxDD/sharpe/calmar: {pct(best['full_annual_return'])} / {pct(best['full_max_drawdown'])} / {best['full_sharpe']:.3f} / {best['full_calmar']:.3f}",
            f"- Exposure/avg weight/trades: {pct(best['wf_exposure'])} / {pct(best['wf_avg_weight'])} / {int(best['wf_trades'])}",
            "",
            "Recent operations:",
            "",
            md_table(item["operations"].tail(20)) if not item["operations"].empty else "_No operations._",
        ]
    lines += [
        "",
        "## Files",
        "",
        "- `best_pure_momentum_summary.csv`: comparison summary.",
        "- `QLD_strategy_rank.csv`, `TQQQ_strategy_rank.csv`: full rankings.",
        "- `QLD_top50_by_score.csv`, `TQQQ_top50_by_score.csv`: score leaders.",
        "- `QLD_top50_by_wf_return.csv`, `TQQQ_top50_by_wf_return.csv`: raw walk-forward return leaders.",
        "- `QLD_best_signal_nav.csv`, `TQQQ_best_signal_nav.csv`: daily signal and NAV.",
        "",
        "## Limitations",
        "",
        "- This is still historical optimization across many MA/ROC/breakout parameters.",
        "- Pure momentum can look excellent in persistent Nasdaq trends but can whipsaw in sideways regimes.",
        "- Volatility sizing uses realized volatility for risk sizing, but the entry/exit signal remains pure price momentum.",
    ]
    (run_dir / "report.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    write_json(run_dir / "best_config.json", {"run_dir": str(run_dir), "cost": cost, "baseline_run": str(baseline_run) if baseline_run else None, "best": best_rows.to_dict("records")})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-run", default="", help="qldtqqq_turning_* run directory with updated_data.")
    parser.add_argument("--cost", type=float, default=0.002)
    args = parser.parse_args()

    data_run = Path(args.data_run) if args.data_run else latest_turning_run()
    data, status = load_data(data_run)
    run_dir = OUT_ROOT / f"pure_momentum_{stamp()}"
    run_dir.mkdir(parents=True, exist_ok=True)
    status.to_csv(run_dir / "data_status.csv", index=False, encoding="utf-8-sig")
    baseline_run, baseline = find_baseline()
    summaries = [evaluate_target(target, data, run_dir, args.cost) for target in TARGETS]
    write_report(run_dir, summaries, status, baseline_run, baseline, args.cost)
    print(run_dir)


if __name__ == "__main__":
    main()
