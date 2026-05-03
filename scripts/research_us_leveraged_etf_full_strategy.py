"""Full TQQQ/QLD strategy search using local and archived external libraries.

The script is checkpoint-heavy by design. Each stage writes local recovery
files so the task can continue without chat context.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Mapping

import numpy as np
import pandas as pd
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.factors import (
    EXTERNAL_PANEL_FACTOR_SPECS,
    align_fama_french_to_index,
    compute_external_price_volume_factor_panels,
    list_external_panel_factors,
    list_joinquant_api_factors,
    reusable_external_resource_summary,
)
from src.factors.safety import SAFETY_FACTORS, compute_safety_factor_panel
from src.strategies import external_strategy_template_summary
from src.strategies.safety import backtest_binary_position, compute_performance_metrics


LEGACY_US_DIR = (
    PROJECT_ROOT
    / "data"
    / "external"
    / "legacy_quant"
    / "NSDQStock"
    / "19800101_20260404"
)
OUTPUT_ROOT = PROJECT_ROOT / "outputs" / "us_leveraged_etf_full_strategy"

TARGET_SYMBOLS = ("TQQQ", "QLD")
CORE_SYMBOLS = ("TQQQ", "QLD", "QQQ", "_VIX")
CONTEXT_ETFS = (
    "SQQQ",
    "PSQ",
    "SPY",
    "SSO",
    "UPRO",
    "IWM",
    "XLK",
    "SOXX",
    "TLT",
    "GLD",
    "SHY",
    "UUP",
)

NASDAQ_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/120 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
    "Referer": "https://www.nasdaq.com/",
}


@dataclass(frozen=True)
class Candidate:
    name: str
    family: str
    source: str
    signal: pd.Series
    notes: str = ""


def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def pct(value: float | int | None) -> str:
    if value is None or pd.isna(value):
        return "nan"
    return f"{float(value) * 100:.2f}%"


def clean_float(value):
    if value is None:
        return None
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, (np.floating, float)):
        if not np.isfinite(value):
            return None
        return float(value)
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    return value


def json_ready(obj):
    if isinstance(obj, dict):
        return {str(k): json_ready(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [json_ready(v) for v in obj]
    if isinstance(obj, tuple):
        return [json_ready(v) for v in obj]
    return clean_float(obj)


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(json_ready(data), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def checkpoint(
    run_dir: Path,
    stage: str,
    title: str,
    payload: Mapping[str, object],
    next_step: str,
) -> None:
    body = {
        "stage": stage,
        "title": title,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "payload": dict(payload),
        "next_step": next_step,
    }
    write_json(run_dir / f"checkpoint_{stage}.json", body)
    lines = [
        f"# {title}",
        "",
        f"- Stage: `{stage}`",
        f"- Time: {body['time']}",
        f"- Next step: {next_step}",
        "",
        "## Payload",
        "",
    ]
    for key, value in payload.items():
        if isinstance(value, (dict, list, tuple)):
            rendered = json.dumps(json_ready(value), ensure_ascii=False, indent=2)
            lines.extend([f"### {key}", "", "```json", rendered, "```", ""])
        else:
            lines.append(f"- {key}: {value}")
    (run_dir / f"checkpoint_{stage}.md").write_text(
        "\n".join(lines).rstrip() + "\n",
        encoding="utf-8",
    )


def parse_number(value) -> float:
    if value is None:
        return np.nan
    text = str(value).replace("$", "").replace(",", "").strip()
    if text in {"", "N/A", "None", "--"}:
        return np.nan
    return float(text)


def read_price_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    columns = {str(c).strip().lower(): c for c in df.columns}
    if "date" not in columns:
        raise ValueError(f"Missing date column in {path}")
    dates = pd.to_datetime(df[columns["date"]], errors="coerce")
    out = pd.DataFrame(index=dates)
    for name in ("open", "high", "low", "close", "volume"):
        source = columns.get(name)
        if source is None:
            out[name] = np.nan
        else:
            out[name] = pd.to_numeric(df[source], errors="coerce").to_numpy()
    out.index.name = "date"
    out = out.dropna(subset=["close"]).sort_index()
    out = out[~out.index.duplicated(keep="last")]
    return out


def write_price_csv(path: Path, data: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    out = data[["close", "high", "low", "open", "volume"]].copy()
    out.index.name = "date"
    out.to_csv(path, encoding="utf-8")


def load_local_symbol(symbol: str) -> pd.DataFrame:
    path = LEGACY_US_DIR / f"{symbol}.csv"
    if path.exists():
        return read_price_csv(path)
    return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])


def fetch_nasdaq_etf(symbol: str, from_date: str, to_date: str) -> tuple[pd.DataFrame, str]:
    url = (
        f"https://api.nasdaq.com/api/quote/{symbol}/historical?"
        f"assetclass=etf&fromdate={from_date}&todate={to_date}&limit=9999"
    )
    response = requests.get(url, headers=NASDAQ_HEADERS, timeout=45)
    response.raise_for_status()
    data = response.json().get("data") or {}
    rows = ((data.get("tradesTable") or {}).get("rows")) or []
    records = []
    for row in rows:
        records.append(
            {
                "date": pd.to_datetime(row.get("date"), format="%m/%d/%Y", errors="coerce"),
                "open": parse_number(row.get("open")),
                "high": parse_number(row.get("high")),
                "low": parse_number(row.get("low")),
                "close": parse_number(row.get("close")),
                "volume": parse_number(row.get("volume")),
            }
        )
    df = pd.DataFrame(records)
    if df.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"]), url
    df = df.dropna(subset=["date", "close"]).set_index("date").sort_index()
    df.index.name = "date"
    return df[["open", "high", "low", "close", "volume"]], url


def fetch_cboe_vix() -> tuple[pd.DataFrame, str]:
    url = "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"
    response = requests.get(url, timeout=90)
    response.raise_for_status()
    from io import StringIO

    df = pd.read_csv(StringIO(response.text))
    df = df.rename(columns={c: c.lower() for c in df.columns})
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    out = df.set_index("date").sort_index()
    out["volume"] = 0.0
    out.index.name = "date"
    return out[["open", "high", "low", "close", "volume"]], url


def fetch_yfinance_symbol(symbol: str, from_date: str, to_date: str) -> tuple[pd.DataFrame, str]:
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        os.environ.setdefault(key, "http://127.0.0.1:7897")
    import yfinance as yf

    ticker = "^VIX" if symbol == "_VIX" else symbol
    raw = yf.download(
        ticker,
        start=from_date,
        end=to_date,
        auto_adjust=True,
        progress=False,
        timeout=30,
    )
    if raw is None or raw.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"]), f"yfinance:{ticker}"
    df = raw.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns={str(c): str(c).lower().replace(" ", "_") for c in df.columns})
    rename = {"adj_close": "close"}
    df = df.rename(columns=rename)
    if "close" not in df.columns:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"]), f"yfinance:{ticker}"
    for col in ("open", "high", "low"):
        if col not in df.columns:
            df[col] = df["close"]
    if "volume" not in df.columns:
        df["volume"] = 0.0
    df.index = pd.to_datetime(df.index).tz_localize(None)
    df.index.name = "date"
    return df[["open", "high", "low", "close", "volume"]].sort_index(), f"yfinance:{ticker}"


def merge_price_data(local: pd.DataFrame, online: pd.DataFrame) -> pd.DataFrame:
    frames = [frame for frame in (local, online) if frame is not None and not frame.empty]
    if not frames:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    merged = pd.concat(frames).sort_index()
    merged = merged[~merged.index.duplicated(keep="last")]
    for col in ("open", "high", "low", "close", "volume"):
        merged[col] = pd.to_numeric(merged[col], errors="coerce")
    merged = merged.dropna(subset=["close"])
    return merged[["open", "high", "low", "close", "volume"]]


def update_us_data(
    run_dir: Path,
    today: str,
    context_symbols: Iterable[str],
) -> tuple[dict[str, pd.DataFrame], pd.DataFrame, dict]:
    symbols = list(dict.fromkeys([*CORE_SYMBOLS, *context_symbols]))
    data: dict[str, pd.DataFrame] = {}
    rows = []
    sources = {}
    updated_dir = run_dir / "updated_data"
    from_date = "2000-01-01"
    for symbol in symbols:
        local = load_local_symbol(symbol)
        local_last = local.index.max().strftime("%Y-%m-%d") if not local.empty else None
        online = pd.DataFrame()
        url = ""
        status = "ok"
        error = ""
        try:
            online, url = fetch_yfinance_symbol(symbol, from_date, today)
            if online.empty:
                raise RuntimeError("empty yfinance response")
            status = "ok_yfinance"
        except Exception as yexc:
            try:
                if symbol == "_VIX":
                    online, url = fetch_cboe_vix()
                else:
                    online, url = fetch_nasdaq_etf(symbol, from_date, today)
                status = "ok_fallback"
                error = f"yfinance_failed: {type(yexc).__name__}: {yexc}"
            except Exception as exc:
                status = "online_failed_local_only"
                error = (
                    f"yfinance_failed: {type(yexc).__name__}: {yexc}; "
                    f"fallback_failed: {type(exc).__name__}: {exc}"
                )
        if symbol == "_VIX" and (online.empty or len(online) < 5000):
            try:
                online, url = fetch_cboe_vix()
                status = "ok_cboe"
            except Exception:
                pass
        merged = merge_price_data(local, online)
        data[symbol] = merged
        if not merged.empty:
            write_price_csv(updated_dir / f"{symbol}.csv", merged)
            write_price_csv(LEGACY_US_DIR / f"{symbol}.csv", merged)
        online_last = online.index.max().strftime("%Y-%m-%d") if not online.empty else None
        merged_last = merged.index.max().strftime("%Y-%m-%d") if not merged.empty else None
        if local_last is not None and not online.empty:
            added_rows = int((online.index > pd.Timestamp(local_last)).sum())
        elif local_last is None:
            added_rows = int(len(online))
        else:
            added_rows = 0
        rows.append(
            {
                "symbol": symbol,
                "status": status,
                "local_last": local_last,
                "online_last": online_last,
                "merged_last": merged_last,
                "rows": int(len(merged)),
                "added_or_refreshed_online_rows": added_rows,
                "url": url,
                "error": error,
            }
        )
        sources[symbol] = rows[-1]
    status_df = pd.DataFrame(rows)
    status_df.to_csv(run_dir / "latest_data_status.csv", index=False, encoding="utf-8-sig")
    write_json(run_dir / "data_sources.json", sources)
    checkpoint(
        run_dir,
        "01_data_update",
        "Data Update Checkpoint",
        {
            "symbols": symbols,
            "latest": status_df[["symbol", "merged_last", "rows", "status"]].to_dict("records"),
            "updated_data_dir": str(updated_dir),
            "legacy_dir_updated": str(LEGACY_US_DIR),
        },
        "Build the resource catalog and generate candidate strategies.",
    )
    return data, status_df, sources


def align_series(series: pd.Series, index: pd.Index) -> pd.Series:
    out = series.copy()
    out.index = pd.to_datetime(out.index)
    return out.reindex(index).ffill().fillna(0.0)


def hold_signal(asset: pd.DataFrame) -> pd.Series:
    return pd.Series(1.0, index=asset.index)


def hysteresis_from_goodness(good: pd.Series, buy: float, sell: float, name: str) -> pd.Series:
    good = good.astype(float)
    values = good.to_numpy(dtype=float)
    signal = np.zeros(len(values), dtype=float)
    held = False
    for i, value in enumerate(values):
        if np.isnan(value):
            signal[i] = 1.0 if held else 0.0
            continue
        if not held and value >= buy:
            held = True
        elif held and value <= sell:
            held = False
        signal[i] = 1.0 if held else 0.0
    return pd.Series(signal, index=good.index, name=name)


def rolling_percentile_last(series: pd.Series, window: int) -> pd.Series:
    values = series.astype(float).replace([np.inf, -np.inf], np.nan)
    min_periods = min(window, max(20, window // 5))
    roller = values.rolling(window, min_periods=min_periods)
    if hasattr(roller, "rank"):
        return roller.rank(pct=True)

    def rank_last(window_values: np.ndarray) -> float:
        valid = window_values[~np.isnan(window_values)]
        if len(valid) < min_periods:
            return np.nan
        return float(pd.Series(valid).rank(pct=True).iloc[-1])

    return roller.apply(rank_last, raw=True)


def ma_band_signal(
    asset: pd.DataFrame,
    window: int,
    enter_mult: float,
    exit_mult: float,
    name: str,
) -> pd.Series:
    close = asset["close"]
    ma = close.rolling(window).mean()
    close_values = close.to_numpy(dtype=float)
    ma_values = ma.to_numpy(dtype=float)
    signal = np.zeros(len(close_values), dtype=float)
    held = False
    for i, c in enumerate(close_values):
        m = ma_values[i]
        if pd.isna(m) or pd.isna(c):
            signal[i] = 1.0 if held else 0.0
            continue
        if not held and c >= m * enter_mult:
            held = True
        elif held and c <= m * exit_mult:
            held = False
        signal[i] = 1.0 if held else 0.0
    return pd.Series(signal, index=asset.index, name=name)


def threshold_state_signal(series: pd.Series, enter_max: float, exit_max: float, name: str) -> pd.Series:
    values = series.to_numpy(dtype=float)
    signal = np.zeros(len(values), dtype=float)
    held = False
    for i, value in enumerate(values):
        if np.isnan(value):
            signal[i] = 1.0 if held else 0.0
            continue
        if not held and value <= enter_max:
            held = True
        elif held and value >= exit_max:
            held = False
        signal[i] = 1.0 if held else 0.0
    return pd.Series(signal, index=series.index, name=name)


def macd_signal(asset: pd.DataFrame, fast: int, slow: int, sig: int, name: str) -> pd.Series:
    close = asset["close"]
    macd = close.ewm(span=fast, adjust=False).mean()
    macd = macd - close.ewm(span=slow, adjust=False).mean()
    trigger = macd.ewm(span=sig, adjust=False).mean()
    return hysteresis_from_goodness((macd > trigger).astype(float), 1.0, 0.0, name)


def turtle_signal(asset: pd.DataFrame, entry: int, exit_: int, name: str) -> pd.Series:
    close = asset["close"]
    entry_high = asset["high"].rolling(entry).max().shift(1)
    exit_low = asset["low"].rolling(exit_).min().shift(1)
    close_values = close.to_numpy(dtype=float)
    entry_values = entry_high.to_numpy(dtype=float)
    exit_values = exit_low.to_numpy(dtype=float)
    signal = np.zeros(len(close_values), dtype=float)
    held = False
    for i, c in enumerate(close_values):
        if not held and c > entry_values[i]:
            held = True
        elif held and c < exit_values[i]:
            held = False
        signal[i] = 1.0 if held else 0.0
    return pd.Series(signal, index=asset.index, name=name)


def dual_thrust_signal(asset: pd.DataFrame, window: int, k: float, name: str) -> pd.Series:
    hh = asset["high"].rolling(window).max().shift(1)
    lc = asset["close"].rolling(window).min().shift(1)
    hc = asset["close"].rolling(window).max().shift(1)
    ll = asset["low"].rolling(window).min().shift(1)
    rng = pd.concat([hh - lc, hc - ll], axis=1).max(axis=1)
    upper = asset["open"] + k * rng
    lower = asset["open"] - k * rng
    close = asset["close"]
    close_values = close.to_numpy(dtype=float)
    upper_values = upper.to_numpy(dtype=float)
    lower_values = lower.to_numpy(dtype=float)
    signal = np.zeros(len(close_values), dtype=float)
    held = False
    for i, c in enumerate(close_values):
        if not held and c > upper_values[i]:
            held = True
        elif held and c < lower_values[i]:
            held = False
        signal[i] = 1.0 if held else 0.0
    return pd.Series(signal, index=asset.index, name=name)


def rsi_signal(
    asset: pd.DataFrame,
    window: int,
    enter: float,
    exit_: float,
    name: str,
) -> pd.Series:
    diff = asset["close"].diff()
    up = diff.clip(lower=0).ewm(alpha=1 / window, adjust=False).mean()
    down = (-diff.clip(upper=0)).ewm(alpha=1 / window, adjust=False).mean()
    rsi = 100 - 100 / (1 + up.div(down.replace(0, np.nan)))
    return hysteresis_from_goodness(
        (100 - rsi) / 100.0,
        (100 - enter) / 100.0,
        (100 - exit_) / 100.0,
        name,
    )


def and_signal(left: pd.Series, right: pd.Series, index: pd.Index, name: str) -> pd.Series:
    l_value = align_series(left, index)
    r_value = align_series(right, index)
    return ((l_value > 0.5) & (r_value > 0.5)).astype(float).rename(name)


def trades_per_year(trades: int, returns: pd.Series) -> float:
    if len(returns) == 0:
        return 0.0
    years = len(returns) / 252.0
    return float(trades / years) if years > 0 else 0.0


def robust_score(
    train: Mapping[str, float],
    test: Mapping[str, float],
    full: Mapping[str, float],
    test_trades: int,
    full_trades: int,
) -> float:
    values = {
        "test_calmar": test.get("calmar", np.nan),
        "test_sharpe": test.get("sharpe", np.nan),
        "test_annual": test.get("annual_return", np.nan),
        "full_calmar": full.get("calmar", np.nan),
        "full_sharpe": full.get("sharpe", np.nan),
        "train_sharpe": train.get("sharpe", np.nan),
        "test_dd": test.get("max_drawdown", np.nan),
        "full_dd": full.get("max_drawdown", np.nan),
        "test_exposure": test.get("exposure", np.nan),
    }
    required = ("test_calmar", "test_sharpe", "full_calmar", "full_sharpe")
    if any(pd.isna(values[key]) for key in required):
        return -999.0
    test_calmar = float(np.clip(values["test_calmar"], -2.0, 2.5))
    full_calmar = float(np.clip(values["full_calmar"], -1.0, 1.5))
    test_sharpe = float(np.clip(values["test_sharpe"], -2.0, 2.5))
    full_sharpe = float(np.clip(values["full_sharpe"], -2.0, 2.0))
    test_annual = float(values["test_annual"])
    full_annual = float(full.get("annual_return", np.nan))
    test_exposure = float(values["test_exposure"])
    score = (
        0.30 * test_calmar
        + 0.25 * test_sharpe
        + 0.20 * test_annual
        + 0.15 * full_calmar
        + 0.10 * full_sharpe
    )
    if values["train_sharpe"] and values["test_sharpe"]:
        gap = float(values["train_sharpe"]) - float(values["test_sharpe"]) - 0.35
        score -= 0.06 * max(0.0, gap)
    if values["test_dd"] < -0.55:
        score -= 0.25 * abs(float(values["test_dd"]) + 0.55)
    if values["full_dd"] < -0.65:
        score -= 0.20 * abs(float(values["full_dd"]) + 0.65)
    if test_annual < 0.08:
        score -= 2.0 * (0.08 - test_annual)
    if pd.notna(full_annual) and full_annual < 0.04:
        score -= 1.0 * (0.04 - float(full_annual))
    if test_exposure < 0.20:
        score -= 3.0 * (0.20 - test_exposure)
    if test_exposure < 0.05:
        score -= 0.75
    if full_trades == 0:
        score -= 0.20
    if test_trades == 0:
        score -= 0.10
    if full_trades > 500:
        score -= 0.10
    if values["test_exposure"] < 0.05:
        score -= 0.25
    return float(score)


def evaluate_candidate(
    symbol: str,
    asset: pd.DataFrame,
    candidate: Candidate,
    eval_start: pd.Timestamp,
    test_start: pd.Timestamp,
    fee: float,
    risk_free: float,
) -> tuple[dict, pd.Series, pd.Series, pd.Series]:
    desired = align_series(candidate.signal, asset.index).clip(0.0, 1.0)
    nav, returns, position = backtest_binary_position(asset, desired, cost_rate=fee)
    eval_end = asset.index.max()
    train_end = min(test_start - pd.Timedelta(days=1), eval_end)
    test_begin = max(test_start, eval_start)
    train = compute_performance_metrics(returns, eval_start, train_end, risk_free=risk_free)
    test = compute_performance_metrics(returns, test_begin, eval_end, risk_free=risk_free)
    full = compute_performance_metrics(returns, eval_start, eval_end, risk_free=risk_free)
    train_trades = int(position.loc[eval_start:train_end].diff().abs().fillna(0).sum())
    test_trades = int(position.loc[test_begin:eval_end].diff().abs().fillna(0).sum())
    full_trades = int(position.loc[eval_start:eval_end].diff().abs().fillna(0).sum())
    score = robust_score(train, test, full, test_trades, full_trades)
    last_desired = int(desired.iloc[-1] > 0.5)
    last_position = int(position.iloc[-1] > 0.5)
    if last_desired > last_position:
        action = "BUY_NEXT_OPEN"
    elif last_desired < last_position:
        action = "SELL_NEXT_OPEN"
    else:
        action = "HOLD_OR_BUY" if last_desired else "CASH_OR_SELL"
    row = {
        "symbol": symbol,
        "strategy": candidate.name,
        "family": candidate.family,
        "source": candidate.source,
        "score": score,
        "latest_signal_date": eval_end.strftime("%Y-%m-%d"),
        "latest_close": float(asset["close"].iloc[-1]),
        "last_desired_position": last_desired,
        "last_executed_position": last_position,
        "next_open_action": action,
        "notes": candidate.notes,
    }
    for prefix, metrics in (("train", train), ("test", test), ("full", full)):
        for key, value in metrics.items():
            row[f"{prefix}_{key}"] = clean_float(value)
    row["train_trades"] = train_trades
    row["test_trades"] = test_trades
    row["full_trades"] = full_trades
    row["train_trades_per_year"] = trades_per_year(
        train_trades,
        returns.loc[eval_start:train_end],
    )
    row["test_trades_per_year"] = trades_per_year(test_trades, returns.loc[test_begin:eval_end])
    row["full_trades_per_year"] = trades_per_year(full_trades, returns.loc[eval_start:eval_end])
    return row, desired, nav, position


def trade_stats(asset: pd.DataFrame, position: pd.Series) -> dict:
    pos = position.reindex(asset.index).fillna(0.0)
    changes = pos.diff().fillna(pos)
    entries = list(changes[changes > 0.5].index)
    exits = list(changes[changes < -0.5].index)
    if exits and entries and exits[0] < entries[0]:
        exits = exits[1:]
    closed = []
    for entry, exit_ in zip(entries, exits):
        entry_px = asset.at[entry, "open"] if entry in asset.index else np.nan
        exit_px = asset.at[exit_, "open"] if exit_ in asset.index else np.nan
        if pd.notna(entry_px) and pd.notna(exit_px) and entry_px > 0:
            closed.append({"entry": entry, "exit": exit_, "return": exit_px / entry_px - 1})
    returns = [x["return"] for x in closed]
    return {
        "entries": len(entries),
        "closed_trades": len(closed),
        "trade_win_rate": float(np.mean([r > 0 for r in returns])) if returns else np.nan,
        "avg_trade_return": float(np.mean(returns)) if returns else np.nan,
        "median_trade_return": float(np.median(returns)) if returns else np.nan,
        "trades": closed,
    }


def eval_start_for(asset: pd.DataFrame, requested_start: str) -> pd.Timestamp:
    start = pd.Timestamp(requested_start)
    if len(asset) > 260:
        start = max(start, asset.index[260])
    return start


def build_template_candidates(symbol: str, data: Mapping[str, pd.DataFrame]) -> list[Candidate]:
    asset = data[symbol]
    qqq = data.get("QQQ")
    vix = data.get("_VIX")
    candidates = [
        Candidate("buy_hold", "baseline_strategy", "rqalpha_buy_and_hold", hold_signal(asset)),
    ]
    for source_name, source_asset in ((f"{symbol.lower()}_asset", asset), ("qqq_underlying", qqq)):
        if source_asset is None or source_asset.empty:
            continue
        for window in (50, 100, 150, 180, 200, 220, 250):
            for enter in (1.00, 1.01, 1.02, 1.03):
                for exit_ in (0.97, 0.98, 1.00):
                    if exit_ > enter:
                        continue
                    name = f"{source_name}_ma{window}_band_e{enter:.2f}_x{exit_:.2f}"
                    raw = ma_band_signal(source_asset, window, enter, exit_, name)
                    candidates.append(
                        Candidate(
                            raw.name,
                            "trend_following_ma_band",
                            "quant_lab_safety_ma",
                            align_series(raw, asset.index),
                        )
                    )
        for fast, slow, sig in ((12, 26, 9), (20, 50, 9), (30, 90, 12)):
            name = f"{source_name}_macd_{fast}_{slow}_{sig}"
            raw = macd_signal(source_asset, fast, slow, sig, name)
            candidates.append(
                Candidate(
                    raw.name,
                    "technical_timing_strategy",
                    "rqalpha_macd_port",
                    align_series(raw, asset.index),
                )
            )
        for entry, exit_ in ((20, 10), (55, 20), (120, 60), (200, 100)):
            name = f"{source_name}_turtle_e{entry}_x{exit_}"
            raw = turtle_signal(source_asset, entry, exit_, name)
            candidates.append(
                Candidate(
                    raw.name,
                    "trend_following_strategy",
                    "rqalpha_turtle_port",
                    align_series(raw, asset.index),
                )
            )
        for window in (5, 10, 20, 40):
            for k in (0.3, 0.5, 0.7):
                name = f"{source_name}_dual_thrust_w{window}_k{k:.1f}"
                raw = dual_thrust_signal(source_asset, window, k, name)
                candidates.append(
                    Candidate(
                        raw.name,
                        "breakout_strategy",
                        "rqalpha_dual_thrust_port",
                        align_series(raw, asset.index),
                    )
                )
    for window in (7, 14, 21):
        for enter, exit_ in ((30, 55), (35, 60), (40, 65)):
            name = f"asset_rsi_oversold_w{window}_e{enter}_x{exit_}"
            raw = rsi_signal(asset, window, enter, exit_, name)
            candidates.append(Candidate(raw.name, "mean_reversion_timing", "quant_lab_local_factor", raw))
    if vix is not None and not vix.empty:
        vix_close = vix["close"].reindex(asset.index).ffill()
        for threshold in (20, 25, 30, 35, 40):
            raw = (vix_close < threshold).astype(float).rename(f"vix_lt_{threshold}")
            candidates.append(Candidate(raw.name, "volatility_regime", "cboe_vix_filter", raw))
        for enter, exit_ in ((18, 25), (20, 30), (22, 30), (25, 35), (30, 40)):
            name = f"vix_state_e{enter}_x{exit_}"
            raw = threshold_state_signal(vix_close, enter, exit_, name)
            candidates.append(Candidate(raw.name, "volatility_regime", "cboe_vix_filter", raw))
    combo_source = [
        c
        for c in candidates
        if c.family in {"trend_following_ma_band", "volatility_regime"}
        and (
            "ma180" in c.name
            or "ma200" in c.name
            or "ma220" in c.name
            or c.name.startswith("vix_")
        )
    ]
    ma_candidates = [c for c in combo_source if "ma" in c.name][:80]
    vix_candidates = [c for c in combo_source if c.name.startswith("vix_")]
    for ma in ma_candidates:
        for vf in vix_candidates:
            name = f"{ma.name}__{vf.name}"
            sig = and_signal(ma.signal, vf.signal, asset.index, name)
            candidates.append(Candidate(name, "combined_trend_vix", "quant_lab_plus_cboe", sig))
    return candidates


def append_rows(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    df = pd.DataFrame(rows)
    header = not path.exists()
    df.to_csv(path, mode="a", header=header, index=False, encoding="utf-8-sig")


def evaluate_candidates(
    symbol: str,
    data: Mapping[str, pd.DataFrame],
    candidates: Iterable[Candidate],
    eval_start: pd.Timestamp,
    test_start: pd.Timestamp,
    fee: float,
    risk_free: float,
    summary_path: Path,
    best_state: dict,
) -> int:
    asset = data[symbol]
    rows = []
    count = 0
    for candidate in candidates:
        try:
            row, desired, nav, position = evaluate_candidate(
                symbol,
                asset,
                candidate,
                eval_start,
                test_start,
                fee,
                risk_free,
            )
        except Exception as exc:
            row = {
                "symbol": symbol,
                "strategy": candidate.name,
                "family": candidate.family,
                "source": candidate.source,
                "score": -999.0,
                "error": f"{type(exc).__name__}: {exc}",
            }
            desired = nav = position = None
        rows.append(row)
        count += 1
        best = best_state.get(symbol)
        if desired is not None and (
            best is None or row.get("score", -999.0) > best["row"].get("score", -999.0)
        ):
            best_state[symbol] = {
                "row": row,
                "desired": desired,
                "nav": nav,
                "position": position,
            }
        if len(rows) >= 500:
            append_rows(summary_path, rows)
            rows = []
    append_rows(summary_path, rows)
    return count


def factor_ts_candidates(
    symbol: str,
    panel: pd.DataFrame,
    factor_name: str,
    source: str,
    asset_index: pd.Index,
) -> list[Candidate]:
    if symbol not in panel.columns:
        return []
    raw = panel[symbol].reindex(asset_index)
    out = []
    for window in (252,):
        rank = rolling_percentile_last(raw, window)
        for direction in ("high", "low"):
            good = rank if direction == "high" else 1.0 - rank
            for buy, sell in ((0.65, 0.45),):
                name = f"{factor_name}_ts_{direction}_w{window}_b{buy:.2f}_s{sell:.2f}"
                sig = hysteresis_from_goodness(good, buy, sell, name)
                out.append(
                    Candidate(
                        name,
                        "external_factor_timeseries",
                        source,
                        sig,
                        notes=f"factor={factor_name}",
                    )
                )
    return out


def factor_cs_candidates(
    symbol: str,
    panel: pd.DataFrame,
    factor_name: str,
    source: str,
    asset_index: pd.Index,
) -> list[Candidate]:
    if symbol not in panel.columns or panel.shape[1] < 4:
        return []
    panel = panel.reindex(asset_index)
    ranks = panel.rank(axis=1, pct=True)
    out = []
    for direction in ("high", "low"):
        good = ranks[symbol] if direction == "high" else 1.0 - ranks[symbol]
        for top_q in (0.35,):
            name = f"{factor_name}_cs_{direction}_top{top_q:.2f}"
            sig = (good >= 1.0 - top_q).astype(float).rename(name)
            out.append(
                Candidate(
                    name,
                    "external_factor_cross_section",
                    source,
                    sig,
                    notes=f"factor={factor_name}",
                )
            )
    return out


def group_external_factors() -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for name in list_external_panel_factors():
        library = EXTERNAL_PANEL_FACTOR_SPECS[name].library
        grouped.setdefault(library, []).append(name)
    return {key: sorted(value) for key, value in grouped.items()}


def run_external_factor_stage(
    run_dir: Path,
    data: Mapping[str, pd.DataFrame],
    eval_starts: Mapping[str, pd.Timestamp],
    test_start: pd.Timestamp,
    fee: float,
    risk_free: float,
    summary_path: Path,
    best_state: dict,
    chunk_size: int,
) -> tuple[dict, dict[str, dict[str, pd.Series]]]:
    grouped = group_external_factors()
    qlib_feature_store: dict[str, dict[str, pd.Series]] = {symbol: {} for symbol in TARGET_SYMBOLS}
    counts = {}
    for library, names in grouped.items():
        started = time.time()
        lib_counts = {"factors": len(names), "computed": 0, "candidates": 0, "failed": []}
        if library == "worldquant_alpha101":
            factor_data = {
                symbol: data[symbol]
                for symbol in ("TQQQ", "QLD", "QQQ", "SQQQ", "PSQ")
                if symbol in data and not data[symbol].empty
            }
            effective_chunk_size = min(chunk_size, 10)
        else:
            factor_data = data
            effective_chunk_size = chunk_size
        for start in range(0, len(names), effective_chunk_size):
            chunk = names[start : start + effective_chunk_size]
            try:
                panels = compute_external_price_volume_factor_panels(factor_data, chunk)
            except Exception as exc:
                lib_counts["failed"].append(
                    {"chunk": chunk, "error": f"{type(exc).__name__}: {exc}"}
                )
                continue
            lib_counts["computed"] += len(panels)
            for factor_name, panel in panels.items():
                source = EXTERNAL_PANEL_FACTOR_SPECS[factor_name].library
                if source == "alpha360_qlib":
                    for symbol in TARGET_SYMBOLS:
                        if symbol in panel.columns:
                            qlib_feature_store[symbol][factor_name] = panel[symbol]
                for symbol in TARGET_SYMBOLS:
                    asset_index = data[symbol].index
                    candidates = []
                    candidates.extend(
                        factor_ts_candidates(symbol, panel, factor_name, source, asset_index)
                    )
                    candidates.extend(
                        factor_cs_candidates(symbol, panel, factor_name, source, asset_index)
                    )
                    lib_counts["candidates"] += evaluate_candidates(
                        symbol,
                        data,
                        candidates,
                        eval_starts[symbol],
                        test_start,
                        fee,
                        risk_free,
                        summary_path,
                        best_state,
                    )
        lib_counts["elapsed_seconds"] = round(time.time() - started, 2)
        counts[library] = lib_counts
        checkpoint(
            run_dir,
            f"03_external_factors_{library}",
            f"External Factor Checkpoint - {library}",
            {
                "library": library,
                "counts": lib_counts,
                "current_best": {
                    s: best_state[s]["row"] for s in best_state if s in TARGET_SYMBOLS
                },
            },
            "Continue with the next external factor library or local factor stage.",
        )
    return counts, qlib_feature_store


def run_local_factor_stage(
    run_dir: Path,
    data: Mapping[str, pd.DataFrame],
    eval_starts: Mapping[str, pd.Timestamp],
    test_start: pd.Timestamp,
    fee: float,
    risk_free: float,
    summary_path: Path,
    best_state: dict,
) -> dict:
    usable = {k: v for k, v in data.items() if k != "_VIX" and not v.empty}
    panels = compute_safety_factor_panel(usable, factors=SAFETY_FACTORS.values())
    count = 0
    for factor_name, panel in panels.items():
        for symbol in TARGET_SYMBOLS:
            candidates = []
            candidates.extend(
                factor_ts_candidates(
                    symbol,
                    panel,
                    factor_name,
                    "quant_lab_safety_factors",
                    data[symbol].index,
                )
            )
            candidates.extend(
                factor_cs_candidates(
                    symbol,
                    panel,
                    factor_name,
                    "quant_lab_safety_factors",
                    data[symbol].index,
                )
            )
            count += evaluate_candidates(
                symbol,
                data,
                candidates,
                eval_starts[symbol],
                test_start,
                fee,
                risk_free,
                summary_path,
                best_state,
            )
    result = {"factor_count": len(panels), "candidate_count": count}
    checkpoint(
        run_dir,
        "04_local_factors",
        "Local Factor Checkpoint",
        {
            "counts": result,
            "current_best": {s: best_state[s]["row"] for s in best_state if s in TARGET_SYMBOLS},
        },
        "Evaluate Fama-French and ML template candidates.",
    )
    return result


def run_fama_french_stage(
    run_dir: Path,
    data: Mapping[str, pd.DataFrame],
    eval_starts: Mapping[str, pd.Timestamp],
    test_start: pd.Timestamp,
    fee: float,
    risk_free: float,
    summary_path: Path,
    best_state: dict,
) -> dict:
    base_index = data["QQQ"].index
    result = {"status": "ok", "candidate_count": 0, "latest_factor_date": None, "error": ""}
    try:
        factors = align_fama_french_to_index(
            base_index,
            frequency="daily",
            include_momentum=True,
        )
        if len(factors):
            result["latest_factor_date"] = factors.dropna(how="all").index.max().strftime("%Y-%m-%d")
        for symbol in TARGET_SYMBOLS:
            candidates = []
            idx = data[symbol].index
            aligned = factors.reindex(idx).ffill()
            for col in aligned.columns:
                series = aligned[col]
                for window in (20, 60, 120):
                    rolling_sum = series.rolling(window).sum()
                    rank = rolling_percentile_last(rolling_sum, 504)
                    for direction in ("high", "low"):
                        good = rank if direction == "high" else 1.0 - rank
                        name = f"fama_french_{col}_sum{window}_{direction}_pct"
                        sig = hysteresis_from_goodness(good, 0.60, 0.45, name)
                        candidates.append(Candidate(name, "asset_pricing_regime", "fama_french", sig))
            result["candidate_count"] += evaluate_candidates(
                symbol,
                data,
                candidates,
                eval_starts[symbol],
                test_start,
                fee,
                risk_free,
                summary_path,
                best_state,
            )
    except Exception as exc:
        result.update({"status": "failed", "error": f"{type(exc).__name__}: {exc}"})
    checkpoint(
        run_dir,
        "05_fama_french",
        "Fama-French Checkpoint",
        {
            "result": result,
            "current_best": {s: best_state[s]["row"] for s in best_state if s in TARGET_SYMBOLS},
        },
        "Evaluate ML template candidates based on Qlib Alpha360 features.",
    )
    return result


def make_ml_signal(
    asset: pd.DataFrame,
    features: Mapping[str, pd.Series],
    test_start: pd.Timestamp,
    horizon: int,
    threshold: float,
    name: str,
) -> tuple[pd.Series, dict]:
    from sklearn.ensemble import HistGradientBoostingClassifier

    if not features:
        raise ValueError("No features supplied")
    X = pd.DataFrame({key: value.reindex(asset.index) for key, value in features.items()})
    future_ret = asset["open"].shift(-(horizon + 1)).div(asset["open"].shift(-1)).sub(1)
    y = (future_ret > 0).astype(float)
    train_mask = (X.index < test_start) & y.notna()
    valid_cols = X.loc[train_mask].notna().mean()
    selected_cols = valid_cols[valid_cols > 0.65].index.tolist()
    if len(selected_cols) < 10:
        raise ValueError("Too few usable Alpha360 features")
    X = X[selected_cols].replace([np.inf, -np.inf], np.nan)
    train_X = X.loc[train_mask]
    train_y = y.loc[train_mask].astype(int)
    if train_y.nunique() < 2:
        raise ValueError("Training labels have one class")
    model = HistGradientBoostingClassifier(
        max_iter=180,
        learning_rate=0.04,
        max_leaf_nodes=15,
        l2_regularization=0.05,
        random_state=42,
    )
    model.fit(train_X, train_y)
    proba = pd.Series(model.predict_proba(X)[:, 1], index=X.index)
    signal = hysteresis_from_goodness(proba, threshold, max(0.50, threshold - 0.08), name)
    meta = {
        "selected_features": len(selected_cols),
        "train_rows": int(train_mask.sum()),
        "positive_rate": float(train_y.mean()),
        "threshold": threshold,
        "horizon": horizon,
    }
    return signal, meta


def run_ml_stage(
    run_dir: Path,
    data: Mapping[str, pd.DataFrame],
    qlib_feature_store: Mapping[str, Mapping[str, pd.Series]],
    eval_starts: Mapping[str, pd.Timestamp],
    test_start: pd.Timestamp,
    fee: float,
    risk_free: float,
    summary_path: Path,
    best_state: dict,
) -> dict:
    result = {"status": "ok", "candidate_count": 0, "errors": []}
    for symbol in TARGET_SYMBOLS:
        candidates = []
        for horizon in (5, 10, 20):
            for threshold in (0.52, 0.55, 0.58, 0.62):
                name = f"qlib_alpha360_histgb_h{horizon}_p{threshold:.2f}"
                try:
                    signal, meta = make_ml_signal(
                        data[symbol],
                        qlib_feature_store.get(symbol, {}),
                        test_start,
                        horizon,
                        threshold,
                        name,
                    )
                    candidates.append(
                        Candidate(
                            name,
                            "ml_factor_model",
                            "qlib_lightgbm_template_sklearn_fallback",
                            signal,
                            json.dumps(meta),
                        )
                    )
                except Exception as exc:
                    result["errors"].append(
                        {
                            "symbol": symbol,
                            "strategy": name,
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    )
        result["candidate_count"] += evaluate_candidates(
            symbol,
            data,
            candidates,
            eval_starts[symbol],
            test_start,
            fee,
            risk_free,
            summary_path,
            best_state,
        )
    checkpoint(
        run_dir,
        "06_ml_templates",
        "ML Template Checkpoint",
        {
            "result": result,
            "current_best": {s: best_state[s]["row"] for s in best_state if s in TARGET_SYMBOLS},
        },
        "Rank all candidates and write final report artifacts.",
    )
    return result


def summarize_best_outputs(
    run_dir: Path,
    data: Mapping[str, pd.DataFrame],
    summary_path: Path,
    best_state: dict,
    eval_starts: Mapping[str, pd.Timestamp],
    test_start: pd.Timestamp,
    fee: float,
    risk_free: float,
    source_counts: Mapping[str, object],
) -> dict:
    summary = pd.read_csv(summary_path)
    combined_path = run_dir / "combined_strategy_summary.csv"
    summary.sort_values(["symbol", "score"], ascending=[True, False]).to_csv(
        combined_path,
        index=False,
        encoding="utf-8-sig",
    )
    best_config = {}
    report_lines = [
        f"Run dir: {run_dir}",
        f"Fee: one-way {fee:.2%}; signal after close, rebalance next open; cash return 0.",
        (
            "Score: capped 30% test Calmar, 25% test Sharpe, 20% test annual return, "
            "15% full Calmar, 10% full Sharpe, with drawdown/trade/exposure/low-return penalties."
        ),
        "",
        "## Data Latest",
        "",
    ]
    data_status = pd.read_csv(run_dir / "latest_data_status.csv")
    for _, row in data_status.iterrows():
        report_lines.append(
            f"- {row['symbol']}: {row['merged_last']} rows={row['rows']} status={row['status']}"
        )
    report_lines += [
        "",
        "## Reusable Library Coverage",
        "",
        f"- External panel factors evaluated: {len(list_external_panel_factors())}",
        (
            "- JoinQuant API entries indexed, not called without credentials: "
            f"alpha101={len(list_joinquant_api_factors('alpha101'))}, "
            f"alpha191={len(list_joinquant_api_factors('alpha191'))}"
        ),
        f"- Reusable external resources cataloged: {len(reusable_external_resource_summary())}",
        f"- Strategy templates cataloged: {len(external_strategy_template_summary())}",
        f"- Source counts: `{json.dumps(json_ready(source_counts), ensure_ascii=False)}`",
    ]
    for symbol in TARGET_SYMBOLS:
        symbol_summary = summary[summary["symbol"] == symbol].sort_values(
            "score",
            ascending=False,
        )
        symbol_summary.to_csv(
            run_dir / f"{symbol}_strategy_summary.csv",
            index=False,
            encoding="utf-8-sig",
        )
        symbol_summary.head(30).to_csv(
            run_dir / f"{symbol}_top30.csv",
            index=False,
            encoding="utf-8-sig",
        )
        best = best_state[symbol]
        row = best["row"]
        desired = best["desired"]
        nav = best["nav"]
        position = best["position"]
        signal_df = pd.DataFrame(
            {
                "desired_after_close": desired.reindex(data[symbol].index),
                "executed_position": position.reindex(data[symbol].index),
                "nav": nav.reindex(data[symbol].index),
                "close": data[symbol]["close"],
                "open": data[symbol]["open"],
            }
        )
        signal_df.to_csv(run_dir / f"{symbol}_best_signal.csv", encoding="utf-8-sig")
        stats = trade_stats(data[symbol], position)
        trades = pd.DataFrame(stats.pop("trades"))
        if not trades.empty:
            trades["entry"] = trades["entry"].dt.strftime("%Y-%m-%d")
            trades["exit"] = trades["exit"].dt.strftime("%Y-%m-%d")
        trades.to_csv(run_dir / f"{symbol}_best_trades.csv", index=False, encoding="utf-8-sig")
        hold_row, _, _, _ = evaluate_candidate(
            symbol,
            data[symbol],
            Candidate("buy_hold", "baseline_strategy", "rqalpha_buy_and_hold", hold_signal(data[symbol])),
            eval_starts[symbol],
            test_start,
            fee,
            risk_free,
        )
        best_config[symbol] = {
            "best": row,
            "buy_hold": hold_row,
            "trade_stats": stats,
            "eval_start": eval_starts[symbol].strftime("%Y-%m-%d"),
            "test_start": test_start.strftime("%Y-%m-%d"),
            "fee_one_way": fee,
            "files": {
                "summary": str(run_dir / f"{symbol}_strategy_summary.csv"),
                "top30": str(run_dir / f"{symbol}_top30.csv"),
                "trades": str(run_dir / f"{symbol}_best_trades.csv"),
                "signal": str(run_dir / f"{symbol}_best_signal.csv"),
            },
        }
        vix_close = (
            data.get("_VIX", pd.DataFrame())
            .get("close", pd.Series(dtype=float))
            .reindex(data[symbol].index)
            .ffill()
        )
        qqq_close = (
            data.get("QQQ", pd.DataFrame())
            .get("close", pd.Series(dtype=float))
            .reindex(data[symbol].index)
            .ffill()
        )
        latest_vix = vix_close.iloc[-1] if len(vix_close) else np.nan
        latest_qqq = qqq_close.iloc[-1] if len(qqq_close) else np.nan
        report_lines += [
            "",
            f"## {symbol}",
            "",
            f"Best: {row['strategy']}",
            f"Family/source: {row['family']} / {row['source']}",
            (
                f"Latest {row['latest_signal_date']}: {row['next_open_action']} "
                f"close={row['latest_close']:.2f}, QQQ={latest_qqq:.2f}, VIX={latest_vix:.2f}"
            ),
            (
                "train: annual {annual}, total {total}, sharpe {sharpe:.3f}, "
                "maxDD {maxdd}, calmar {calmar:.3f}, exposure {exposure}, trades {trades}"
            ).format(
                annual=pct(row.get("train_annual_return")),
                total=pct(row.get("train_total_return")),
                sharpe=row.get("train_sharpe", np.nan),
                maxdd=pct(row.get("train_max_drawdown")),
                calmar=row.get("train_calmar", np.nan),
                exposure=pct(row.get("train_exposure")),
                trades=row.get("train_trades"),
            ),
            (
                "test: annual {annual}, total {total}, sharpe {sharpe:.3f}, "
                "maxDD {maxdd}, calmar {calmar:.3f}, exposure {exposure}, trades {trades}"
            ).format(
                annual=pct(row.get("test_annual_return")),
                total=pct(row.get("test_total_return")),
                sharpe=row.get("test_sharpe", np.nan),
                maxdd=pct(row.get("test_max_drawdown")),
                calmar=row.get("test_calmar", np.nan),
                exposure=pct(row.get("test_exposure")),
                trades=row.get("test_trades"),
            ),
            (
                "full: annual {annual}, total {total}, sharpe {sharpe:.3f}, "
                "maxDD {maxdd}, calmar {calmar:.3f}, exposure {exposure}, trades {trades}"
            ).format(
                annual=pct(row.get("full_annual_return")),
                total=pct(row.get("full_total_return")),
                sharpe=row.get("full_sharpe", np.nan),
                maxdd=pct(row.get("full_max_drawdown")),
                calmar=row.get("full_calmar", np.nan),
                exposure=pct(row.get("full_exposure")),
                trades=row.get("full_trades"),
            ),
            (
                "buy_hold full: annual {annual}, total {total}, sharpe {sharpe:.3f}, "
                "maxDD {maxdd}; test annual {test_ann}, test maxDD {test_dd}"
            ).format(
                annual=pct(hold_row.get("full_annual_return")),
                total=pct(hold_row.get("full_total_return")),
                sharpe=hold_row.get("full_sharpe", np.nan),
                maxdd=pct(hold_row.get("full_max_drawdown")),
                test_ann=pct(hold_row.get("test_annual_return")),
                test_dd=pct(hold_row.get("test_max_drawdown")),
            ),
            (
                f"trades: entries {stats['entries']}, closed {stats['closed_trades']}, "
                f"win_rate {pct(stats['trade_win_rate'])}, "
                f"avg {pct(stats['avg_trade_return'])}, "
                f"median {pct(stats['median_trade_return'])}"
            ),
            "",
            "Top 5:",
        ]
        for _, top in symbol_summary.head(5).iterrows():
            report_lines.append(
                (
                    f"- {top['strategy']} | score={top['score']:.4f} "
                    f"| test_ann={pct(top.get('test_annual_return'))} "
                    f"| test_dd={pct(top.get('test_max_drawdown'))} "
                    f"| source={top['source']}"
                )
            )
    write_json(run_dir / "best_config.json", best_config)
    report_path = run_dir / "report.md"
    report_lines += ["", "## Checkpoints", ""]
    for ckpt in sorted(run_dir.glob("checkpoint_*.md")):
        report_lines.append(f"- {ckpt.name}")
    report_lines.append("- checkpoint_07_final.md")
    report_lines += [
        "",
        "## Next Step",
        "",
        (
            "Review `best_config.json`, `*_top30.csv`, and `*_best_signal.csv`. "
            "For live use, rerun after the next US close and treat the output as research, "
            "not investment advice."
        ),
    ]
    report_path.write_text("\n".join(report_lines).rstrip() + "\n", encoding="utf-8")
    checkpoint(
        run_dir,
        "07_final",
        "Final Report Checkpoint",
        {
            "report": str(report_path),
            "best_config": str(run_dir / "best_config.json"),
            "combined_summary": str(combined_path),
            "best": {symbol: best_config[symbol]["best"] for symbol in TARGET_SYMBOLS},
        },
        "Use report.md and best_config.json as the durable recovery point.",
    )
    return best_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--today", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--test-start", default="2022-01-01")
    parser.add_argument("--eval-start", default="2005-01-01")
    parser.add_argument("--fee", type=float, default=0.001)
    parser.add_argument("--risk-free", type=float, default=0.02)
    parser.add_argument("--chunk-size", type=int, default=40)
    parser.add_argument("--run-name", default="")
    parser.add_argument("--context-symbols", nargs="*", default=list(CONTEXT_ETFS))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_name = args.run_name or f"full_us_{now_stamp()}"
    run_dir = OUTPUT_ROOT / run_name
    run_dir.mkdir(parents=True, exist_ok=True)
    checkpoint(
        run_dir,
        "00_plan",
        "Plan Checkpoint",
        {
            "targets": TARGET_SYMBOLS,
            "core_symbols": CORE_SYMBOLS,
            "context_symbols": args.context_symbols,
            "today": args.today,
            "test_start": args.test_start,
            "fee": args.fee,
            "external_panel_factor_count": len(list_external_panel_factors()),
            "strategy_template_count": len(external_strategy_template_summary()),
            "resource_count": len(reusable_external_resource_summary()),
        },
        "Update online US ETF/VIX data and persist merged local CSVs.",
    )
    data, _, _ = update_us_data(run_dir, args.today, args.context_symbols)
    missing_targets = [s for s in TARGET_SYMBOLS if s not in data or data[s].empty]
    if missing_targets:
        raise RuntimeError(f"Missing target data: {missing_targets}")
    summary_path = run_dir / "candidate_summary_stream.csv"
    if summary_path.exists():
        summary_path.unlink()
    eval_starts = {symbol: eval_start_for(data[symbol], args.eval_start) for symbol in TARGET_SYMBOLS}
    test_start = pd.Timestamp(args.test_start)
    best_state: dict = {}
    catalog_payload = {
        "resources": reusable_external_resource_summary(),
        "strategy_templates": external_strategy_template_summary(),
        "external_factor_libraries": {k: len(v) for k, v in group_external_factors().items()},
        "joinquant_api_entries": {
            "alpha101": len(list_joinquant_api_factors("alpha101")),
            "alpha191": len(list_joinquant_api_factors("alpha191")),
        },
        "eval_starts": {k: v.strftime("%Y-%m-%d") for k, v in eval_starts.items()},
    }
    write_json(run_dir / "reusable_resource_catalog_snapshot.json", catalog_payload)
    checkpoint(
        run_dir,
        "02_catalog",
        "Resource Catalog Checkpoint",
        catalog_payload,
        "Run template-derived strategies before all factor-library candidates.",
    )
    template_counts = {}
    for symbol in TARGET_SYMBOLS:
        candidates = build_template_candidates(symbol, data)
        template_counts[symbol] = evaluate_candidates(
            symbol,
            data,
            candidates,
            eval_starts[symbol],
            test_start,
            args.fee,
            args.risk_free,
            summary_path,
            best_state,
        )
    checkpoint(
        run_dir,
        "02_templates",
        "Template Strategy Checkpoint",
        {
            "candidate_counts": template_counts,
            "current_best": {s: best_state[s]["row"] for s in best_state},
        },
        "Run all executable external panel factor candidates.",
    )
    external_counts, qlib_feature_store = run_external_factor_stage(
        run_dir,
        data,
        eval_starts,
        test_start,
        args.fee,
        args.risk_free,
        summary_path,
        best_state,
        args.chunk_size,
    )
    local_counts = run_local_factor_stage(
        run_dir,
        data,
        eval_starts,
        test_start,
        args.fee,
        args.risk_free,
        summary_path,
        best_state,
    )
    ff_counts = run_fama_french_stage(
        run_dir,
        data,
        eval_starts,
        test_start,
        args.fee,
        args.risk_free,
        summary_path,
        best_state,
    )
    ml_counts = run_ml_stage(
        run_dir,
        data,
        qlib_feature_store,
        eval_starts,
        test_start,
        args.fee,
        args.risk_free,
        summary_path,
        best_state,
    )
    source_counts = {
        "template": template_counts,
        "external": external_counts,
        "local": local_counts,
        "fama_french": ff_counts,
        "ml": ml_counts,
    }
    summarize_best_outputs(
        run_dir,
        data,
        summary_path,
        best_state,
        eval_starts,
        test_start,
        args.fee,
        args.risk_free,
        source_counts,
    )
    print(run_dir)


if __name__ == "__main__":
    main()
