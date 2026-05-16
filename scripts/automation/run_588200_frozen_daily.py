"""Frozen daily replay for the approved 588200 strategy.

This wrapper refreshes public daily data, replays one fixed strategy id, and
writes latest signal/metrics. It does not run the long-run search script, rank
new parameters, expand the pool, trade, or connect to brokers.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import shutil
import sys
import time
from datetime import date, datetime, timedelta, time as dt_time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.factors.safety import SAFETY_FACTORS, compute_safety_factor_panel, cross_section_zscore
from src.strategies.etf_588200 import LongRunStrategySpec, build_longrun_signal_cache, longrun_signal_from_cache
from src.strategies.safety import backtest_binary_position, compute_performance_metrics


FROZEN_STRATEGY_ID = "factor_overlay__combo2__alpha_intraday_strength_60__alpha_td9_sell_pressure_4_9__mom60__vol20__vp95__fb55__fs45"
TARGET = "588200.SS"
COMBO_FACTOR = "combo2__alpha_intraday_strength_60__alpha_td9_sell_pressure_4_9"
ASTOCK_ROOT = ROOT / "data" / "external" / "legacy_quant" / "AStock"
START = "2022-10-26"
TRAIN_END = "2024-12-31"
COST_RATE = 0.001
RISK_FREE = 0.02
DOWNLOAD_START = "2019-01-01"
YFINANCE_ATTEMPTS = 3
YFINANCE_RETRY_SECONDS = 2.0
MAX_FALLBACK_STALE_DAYS = 7
A_SHARE_EOD_CONFIRMED_TIME = dt_time(15, 30)
A_SHARE_EOD_UNCERTAIN_END_TIME = dt_time(16, 30)
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
    parser = argparse.ArgumentParser(description="Replay fixed 588200 frozen daily strategy.")
    parser.add_argument("--output-dir", default="", help="Output directory for this job.")
    parser.add_argument("--dry-run", action="store_true", help="Print the replay plan without running.")
    parser.add_argument("--skip-download", action="store_true", help="Use local legacy AStock data instead of online refresh.")
    parser.add_argument("--json-out", default="", help="Optional JSON summary path.")
    parser.add_argument("--md-out", default="", help="Optional Markdown summary path.")
    return parser.parse_args()


def stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return float(value) if math.isfinite(float(value)) else None
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    return value


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(jsonable(payload), ensure_ascii=False, indent=2), encoding="utf-8")


def end_exclusive() -> str:
    return (date.today() + timedelta(days=1)).isoformat()


def end_inclusive_compact() -> str:
    return date.today().strftime("%Y%m%d")


def normalize_download_frame(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [col[0] if isinstance(col, tuple) else col for col in df.columns]
    mapping = {str(col).strip().lower().replace(" ", "_"): col for col in df.columns}
    aliases = {
        "open": ["open"],
        "high": ["high"],
        "low": ["low"],
        "close": ["close"],
        "volume": ["volume"],
    }
    out = pd.DataFrame(index=pd.to_datetime(df.index, errors="coerce"))
    for target, names in aliases.items():
        source = next((mapping[name] for name in names if name in mapping), None)
        if source is None:
            out[target] = np.nan
        else:
            out[target] = pd.to_numeric(df[source], errors="coerce")
    out = out.dropna(subset=["close"]).sort_index()
    out = out[~out.index.duplicated(keep="last")]
    return out[["open", "high", "low", "close", "volume"]].copy()


def download_yfinance(symbol: str, *, auto_adjust: bool = True) -> pd.DataFrame:
    import yfinance as yf

    raw = pd.DataFrame()
    for attempt in range(YFINANCE_ATTEMPTS):
        try:
            raw = yf.download(symbol, start=DOWNLOAD_START, end=end_exclusive(), auto_adjust=auto_adjust, progress=False, threads=False)
        except Exception:
            raw = pd.DataFrame()
        if raw is not None and not raw.empty:
            break
        if attempt + 1 < YFINANCE_ATTEMPTS:
            time.sleep(YFINANCE_RETRY_SECONDS)
    if raw is None or raw.empty:
        return pd.DataFrame()
    return normalize_download_frame(raw)


def latest_tradeable_price_yfinance(symbol: str, max_date: pd.Timestamp | None = None) -> dict[str, Any]:
    import yfinance as yf

    raw = pd.DataFrame()
    for attempt in range(YFINANCE_ATTEMPTS):
        try:
            raw = yf.download(symbol, start=DOWNLOAD_START, end=end_exclusive(), auto_adjust=False, progress=False, threads=False)
        except Exception:
            raw = pd.DataFrame()
        if raw is not None and not raw.empty:
            break
        if attempt + 1 < YFINANCE_ATTEMPTS:
            time.sleep(YFINANCE_RETRY_SECONDS)
    if raw is None or raw.empty:
        return {"price_is_tradeable": False, "price_validation_status": "YFINANCE_RAW_CLOSE_EMPTY", "notes": "yfinance returned no rows with auto_adjust=False."}
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = [col[0] if isinstance(col, tuple) else col for col in raw.columns]
    mapping = {str(col).strip().lower().replace(" ", "_"): col for col in raw.columns}
    close_col = mapping.get("close")
    if close_col is None:
        return {"price_is_tradeable": False, "price_validation_status": "YFINANCE_RAW_CLOSE_MISSING", "notes": "yfinance auto_adjust=False output has no Close column."}
    close = pd.to_numeric(raw[close_col], errors="coerce").dropna()
    close = close[close > 0]
    if max_date is not None:
        close = close.loc[pd.DatetimeIndex(close.index).normalize() <= pd.Timestamp(max_date).normalize()]
    if close.empty:
        return {"price_is_tradeable": False, "price_validation_status": "YFINANCE_RAW_CLOSE_INVALID", "notes": "yfinance Close column has no positive values."}
    latest_date = pd.Timestamp(close.index.max())
    return {
        "symbol": "588200",
        "download_symbol": symbol,
        "price_date": latest_date.strftime("%Y-%m-%d"),
        "tradeable_close": float(close.loc[latest_date]),
        "source": "yfinance",
        "source_field": "Close",
        "adjust_flag": "auto_adjust_false",
        "price_is_tradeable": True,
        "price_validation_status": "TRADEABLE_RAW_CLOSE",
        "notes": "yfinance download used auto_adjust=False; Close is treated as the raw market close for manual-review reference only.",
    }


def eod_completeness_for_ashare(latest_date: pd.Timestamp, *, now: datetime | None = None) -> dict[str, Any]:
    current = now or datetime.now()
    latest_day = pd.Timestamp(latest_date).date()
    today = current.date()
    current_time = current.time()
    if latest_day < today:
        return {
            "data_completeness": "EOD_CONFIRMED",
            "raw_latest_data_date": latest_day.isoformat(),
            "accepted_latest_data_date": latest_day.isoformat(),
            "expected_complete_date": latest_day.isoformat(),
            "checked_at": current.isoformat(timespec="seconds"),
            "rule": "historical_date_before_local_today",
            "reason": "Latest A-share bar is before local today and is treated as a complete historical EOD bar.",
        }
    if latest_day > today:
        accepted = today - timedelta(days=1)
        return {
            "data_completeness": "UNKNOWN_FALLBACK_PREVIOUS_EOD",
            "raw_latest_data_date": latest_day.isoformat(),
            "accepted_latest_data_date": accepted.isoformat(),
            "expected_complete_date": accepted.isoformat(),
            "checked_at": current.isoformat(timespec="seconds"),
            "rule": "future_dated_bar_rejected",
            "reason": "Latest A-share bar is after local today; rejecting it as not verifiable.",
        }
    previous_day = today - timedelta(days=1)
    if current_time < A_SHARE_EOD_CONFIRMED_TIME:
        return {
            "data_completeness": "INTRADAY_REJECTED",
            "raw_latest_data_date": latest_day.isoformat(),
            "accepted_latest_data_date": previous_day.isoformat(),
            "expected_complete_date": previous_day.isoformat(),
            "checked_at": current.isoformat(timespec="seconds"),
            "rule": "local_time_before_15_30",
            "reason": "Local time is before 15:30, so today's A-share bar is treated as intraday and rejected.",
        }
    if current_time < A_SHARE_EOD_UNCERTAIN_END_TIME:
        return {
            "data_completeness": "UNKNOWN_FALLBACK_PREVIOUS_EOD",
            "raw_latest_data_date": latest_day.isoformat(),
            "accepted_latest_data_date": previous_day.isoformat(),
            "expected_complete_date": previous_day.isoformat(),
            "checked_at": current.isoformat(timespec="seconds"),
            "rule": "local_time_between_15_30_and_16_30_without_explicit_eod_flag",
            "reason": "Local time is between 15:30 and 16:30, but the data source does not explicitly mark the bar as final EOD.",
        }
    return {
        "data_completeness": "EOD_CONFIRMED",
        "raw_latest_data_date": latest_day.isoformat(),
        "accepted_latest_data_date": latest_day.isoformat(),
        "expected_complete_date": latest_day.isoformat(),
        "checked_at": current.isoformat(timespec="seconds"),
        "rule": "local_time_after_16_30",
        "reason": "Local time is after 16:30; today's A-share bar is accepted as complete EOD.",
    }


def apply_ashare_eod_filter(
    target_asset: pd.DataFrame,
    stocks: dict[str, pd.DataFrame],
    status_rows: list[dict[str, Any]],
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame], dict[str, Any], list[dict[str, Any]]]:
    raw_latest = pd.Timestamp(target_asset.index.max())
    meta = eod_completeness_for_ashare(raw_latest)
    accepted_limit = pd.Timestamp(meta["accepted_latest_data_date"])
    filtered_target = target_asset.loc[target_asset.index <= accepted_limit].copy()
    if filtered_target.empty:
        meta["data_completeness"] = "UNKNOWN_FALLBACK_PREVIOUS_EOD"
        meta["reason"] = f"{meta['reason']} No target rows exist on or before accepted date {accepted_limit.date()}."
        return filtered_target, stocks, meta, status_rows
    accepted_actual = pd.Timestamp(filtered_target.index.max())
    meta["accepted_latest_data_date"] = accepted_actual.strftime("%Y-%m-%d")
    if accepted_actual.date() < accepted_limit.date():
        meta["reason"] = (
            f"{meta['reason']} Requested fallback date {accepted_limit.date()} was not present in the current data pull; "
            f"using latest available prior row {accepted_actual.date()}."
        )
    filtered_stocks = {code: frame.loc[frame.index <= accepted_actual].copy() for code, frame in stocks.items()}
    updated_rows: list[dict[str, Any]] = []
    for row in status_rows:
        item = dict(row)
        if item.get("symbol") == TARGET:
            item["raw_last_date"] = item.get("last_date", "")
            item["accepted_last_date"] = meta["accepted_latest_data_date"]
            item["data_completeness"] = meta["data_completeness"]
            item["eod_completeness_rule"] = meta["rule"]
            item["eod_completeness_reason"] = meta["reason"]
            item["eod_checked_at"] = meta["checked_at"]
        updated_rows.append(item)
    return filtered_target, filtered_stocks, meta, updated_rows


def download_akshare_qfq(symbol: str) -> pd.DataFrame:
    try:
        import akshare as ak
    except Exception:
        return pd.DataFrame()
    code = symbol.split(".")[0]
    try:
        raw = ak.stock_zh_a_hist(symbol=code, period="daily", start_date=DOWNLOAD_START.replace("-", ""), end_date=end_inclusive_compact(), adjust="qfq")
    except Exception:
        return pd.DataFrame()
    if raw is None or raw.empty:
        return pd.DataFrame()
    rename = {
        "日期": "date",
        "开盘": "open",
        "最高": "high",
        "最低": "low",
        "收盘": "close",
        "成交量": "volume",
    }
    raw = raw.rename(columns=rename)
    if "date" not in raw:
        return pd.DataFrame()
    raw["date"] = pd.to_datetime(raw["date"], errors="coerce")
    raw = raw.dropna(subset=["date"]).set_index("date").sort_index()
    for col in ["open", "high", "low", "close", "volume"]:
        raw[col] = pd.to_numeric(raw.get(col), errors="coerce")
    return raw[["open", "high", "low", "close", "volume"]].dropna(subset=["close"]).copy()


def latest_tradeable_price_akshare(symbol: str, max_date: pd.Timestamp | None = None) -> dict[str, Any]:
    try:
        import akshare as ak
    except Exception as exc:
        return {"price_is_tradeable": False, "price_validation_status": "AKSHARE_UNAVAILABLE", "notes": f"akshare import failed: {exc}"}
    code = symbol.split(".")[0]
    try:
        raw = ak.stock_zh_a_hist(symbol=code, period="daily", start_date=DOWNLOAD_START.replace("-", ""), end_date=end_inclusive_compact(), adjust="")
    except Exception as exc:
        return {"price_is_tradeable": False, "price_validation_status": "AKSHARE_RAW_CLOSE_FAILED", "notes": f"akshare raw close failed: {exc}"}
    if raw is None or raw.empty:
        return {"price_is_tradeable": False, "price_validation_status": "AKSHARE_RAW_CLOSE_EMPTY", "notes": "akshare raw close returned no rows."}
    rename = {"日期": "date", "收盘": "close"}
    raw = raw.rename(columns=rename)
    if "date" not in raw or "close" not in raw:
        return {"price_is_tradeable": False, "price_validation_status": "AKSHARE_RAW_CLOSE_COLUMNS_MISSING", "notes": "akshare raw output missing 日期/收盘 columns."}
    raw["date"] = pd.to_datetime(raw["date"], errors="coerce")
    raw["close"] = pd.to_numeric(raw["close"], errors="coerce")
    raw = raw.dropna(subset=["date", "close"])
    raw = raw.loc[raw["close"] > 0].sort_values("date")
    if max_date is not None:
        raw = raw.loc[raw["date"] <= pd.Timestamp(max_date)]
    if raw.empty:
        return {"price_is_tradeable": False, "price_validation_status": "AKSHARE_RAW_CLOSE_INVALID", "notes": "akshare raw close has no positive values."}
    latest = raw.iloc[-1]
    return {
        "symbol": "588200",
        "price_date": pd.Timestamp(latest["date"]).strftime("%Y-%m-%d"),
        "tradeable_close": float(latest["close"]),
        "source": "akshare",
        "source_field": "stock_zh_a_hist.收盘",
        "adjust_flag": "none",
        "price_is_tradeable": True,
        "price_validation_status": "TRADEABLE_RAW_CLOSE",
        "notes": "akshare stock_zh_a_hist adjust='' raw close; manual quote verification still required.",
    }


def get_tradeable_price(symbol: str, max_date: pd.Timestamp | None = None) -> dict[str, Any]:
    errors: list[str] = []
    for candidate in yfinance_symbol_candidates(symbol):
        try:
            yf_price = latest_tradeable_price_yfinance(candidate, max_date=max_date)
            if yf_price.get("price_is_tradeable"):
                if candidate != symbol:
                    yf_price["notes"] = f"{yf_price.get('notes', '')} Used yfinance fallback symbol {candidate}."
                return yf_price
            errors.append(f"{candidate}: {yf_price.get('notes') or yf_price.get('price_validation_status')}")
        except Exception as exc:
            errors.append(f"{candidate}: yfinance raw close failed: {type(exc).__name__}: {exc}")
    ak_price = latest_tradeable_price_akshare(symbol, max_date=max_date)
    if ak_price.get("price_is_tradeable"):
        if errors:
            ak_price["notes"] = f"{ak_price.get('notes', '')} yfinance fallback reason: {' | '.join(errors)}"
        return ak_price
    errors.append(str(ak_price.get("notes") or ak_price.get("price_validation_status")))
    return {
        "symbol": "588200",
        "price_date": "",
        "tradeable_close": None,
        "source": "unavailable",
        "source_field": "",
        "adjust_flag": "unknown",
        "price_is_tradeable": False,
        "price_validation_status": "TRADEABLE_RAW_CLOSE_UNAVAILABLE",
        "notes": " | ".join(errors),
    }


def yfinance_symbol_candidates(symbol: str) -> list[str]:
    if symbol == TARGET:
        return [TARGET, "588200.SH"]
    return [symbol]


def refresh_online_data() -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame], list[dict[str, Any]], list[str]]:
    symbols = [TARGET, *[f"{code}.SS" for code in CODES_588200]]
    target_data: dict[str, pd.DataFrame] = {}
    stocks: dict[str, pd.DataFrame] = {}
    status_rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    for symbol in symbols:
        source = "yfinance_auto_adjust_true"
        error = ""
        frame = pd.DataFrame()
        download_symbol = symbol
        for candidate in yfinance_symbol_candidates(symbol):
            try:
                frame = download_yfinance(candidate, auto_adjust=True)
            except Exception as exc:
                error = f"yfinance {candidate} {type(exc).__name__}: {exc}"
                frame = pd.DataFrame()
            if not frame.empty:
                download_symbol = candidate
                source = f"yfinance_auto_adjust_true:{candidate}"
                break
        if frame.empty:
            fallback = download_akshare_qfq(symbol)
            if not fallback.empty:
                frame = fallback
                source = "akshare_qfq_fallback"
                if error:
                    warnings.append(f"{symbol}: yfinance failed; used akshare qfq fallback.")
            else:
                if error:
                    warnings.append(f"{symbol}: yfinance failed and akshare qfq fallback unavailable: {error}")
                else:
                    warnings.append(f"{symbol}: yfinance returned no rows and akshare qfq fallback unavailable.")
        row = {
            "symbol": symbol,
            "download_symbol": download_symbol,
            "source": source if not frame.empty else "missing",
            "rows": int(len(frame)),
            "first_date": frame.index.min().strftime("%Y-%m-%d") if not frame.empty else "",
            "last_date": frame.index.max().strftime("%Y-%m-%d") if not frame.empty else "",
            "error": error,
        }
        status_rows.append(row)
        if frame.empty:
            continue
        if symbol == TARGET:
            target_data[symbol] = frame
        else:
            stocks[symbol.split(".")[0]] = frame
    return target_data, stocks, status_rows, warnings


def load_price_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df.columns = [str(col).strip().lower() for col in df.columns]
    date_col = next((col for col in df.columns if col in {"date", "datetime"}), df.columns[0])
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


def collect_etf_paths(astock_root: Path) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for root in [astock_root / "ETF" / "yf_etf_data", astock_root / "ETF"]:
        if not root.exists():
            continue
        for path in root.glob("*.csv"):
            code = normalize_code(path)
            if code not in paths or "yf_etf_data" in str(path):
                paths[code] = path
    return paths


def load_local_data() -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame], list[dict[str, Any]], list[str]]:
    etfs: dict[str, pd.DataFrame] = {}
    for code, path in sorted(collect_etf_paths(ASTOCK_ROOT).items()):
        try:
            frame = load_price_csv(path)
        except Exception:
            continue
        frame = frame[frame["open"].notna() & frame["open"].gt(0) & frame["close"].notna() & frame["close"].gt(0)]
        if len(frame) >= 250:
            etfs[code] = frame
    kc_dir = ASTOCK_ROOT / "yf_data" / "KC"
    stocks: dict[str, pd.DataFrame] = {}
    missing: list[str] = []
    for code in CODES_588200:
        candidates = [kc_dir / f"{code}.SS.csv", kc_dir / f"{code}.SH.csv", kc_dir / f"{code}.csv"]
        path = next((item for item in candidates if item.exists()), None)
        if path is None:
            missing.append(code)
            continue
        frame = load_price_csv(path)
        if frame["close"].notna().sum() < 180:
            missing.append(code)
            continue
        stocks[code] = frame
    status_rows = []
    for symbol, frame in {**etfs, **{f"{code}.SS": data for code, data in stocks.items()}}.items():
        status_rows.append(
            {
                "symbol": symbol,
                "source": "local_legacy_astock",
                "rows": int(len(frame)),
                "first_date": frame.index.min().strftime("%Y-%m-%d") if not frame.empty else "",
                "last_date": frame.index.max().strftime("%Y-%m-%d") if not frame.empty else "",
                "error": "",
            }
        )
    return ({TARGET: etfs.get(TARGET, pd.DataFrame())}, stocks, status_rows, [f"Local load missing stock codes: {', '.join(missing)}"] if missing else [])


def build_fixed_spec() -> LongRunStrategySpec:
    return LongRunStrategySpec(
        family="factor_overlay",
        name=FROZEN_STRATEGY_ID,
        mom_window=60,
        breadth_buy=0.65,
        breadth_sell=0.50,
        vol_window=20,
        vol_max=0.95,
        factor_signal=COMBO_FACTOR,
        factor_buy=0.55,
        factor_sell=0.45,
        require_pool_mom=False,
    )


def build_breadth_features(stocks: dict[str, pd.DataFrame]) -> pd.DataFrame:
    close = pd.DataFrame({code: df["close"] for code, df in stocks.items()}).sort_index()
    volume = pd.DataFrame({code: df["volume"] for code, df in stocks.items()}).reindex(close.index)
    ret20 = close.pct_change(20, fill_method=None)
    ret60 = close.pct_change(60, fill_method=None)
    amount = close * volume
    valid = close.notna()
    count = valid.sum(axis=1).where(lambda series: series >= 10)
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


def build_combo_factor_breadth(stocks: dict[str, pd.DataFrame]) -> pd.Series:
    required = ["alpha_intraday_strength_60", "alpha_td9_sell_pressure_4_9"]
    factors = [SAFETY_FACTORS[name] for name in required]
    panels = compute_safety_factor_panel(stocks, factors=factors)
    zscores = [cross_section_zscore(panels[name]) for name in required]
    combo_score = pd.concat([frame.stack(future_stack=True).rename(name) for frame, name in zip(zscores, required)], axis=1).mean(axis=1).unstack()
    count = combo_score.notna().sum(axis=1).where(lambda series: series >= 10)
    return ((combo_score > 0).sum(axis=1) / count).rename(COMBO_FACTOR)


def buy_hold_returns(asset: pd.DataFrame) -> pd.Series:
    open_px = asset["open"]
    return open_px.shift(-1).div(open_px).sub(1).replace([np.inf, -np.inf], np.nan).fillna(0.0)


def next_weekday(value: pd.Timestamp) -> str:
    current = value.date() + timedelta(days=1)
    while current.weekday() >= 5:
        current += timedelta(days=1)
    return current.isoformat()


def latest_action(asset: pd.DataFrame, desired: pd.Series, position: pd.Series) -> dict[str, Any]:
    latest = asset.index.max()
    desired_value = float(desired.reindex(asset.index).ffill().fillna(0.0).iloc[-1])
    position_value = float(position.reindex(asset.index).ffill().fillna(0.0).iloc[-1])
    if desired_value > 0.5 and position_value > 0.5:
        action = "HOLD_OR_KEEP_LONG"
    elif desired_value > 0.5:
        action = "BUY_NEXT_OPEN"
    elif position_value > 0.5:
        action = "SELL_NEXT_OPEN"
    else:
        action = "WAIT_OR_STAY_CASH"
    return {
        "latest_signal_date": latest.strftime("%Y-%m-%d"),
        "next_open_date": next_weekday(latest),
        "latest_close": float(asset.loc[latest, "close"]),
        "latest_desired_after_close": desired_value,
        "position_at_latest_open": position_value,
        "latest_action": action,
    }


def write_markdown(path: Path, payload: dict[str, Any]) -> None:
    result = payload.get("result", {})
    lines = [
        "# 588200 Frozen Daily Replay",
        "",
        f"- Status: `{payload.get('status')}`",
        f"- Frozen strategy id: `{FROZEN_STRATEGY_ID}`",
        f"- Output directory: `{payload.get('output_dir')}`",
        f"- Data download performed: `{payload.get('data_download_performed')}`",
        f"- Search performed: `False`",
        f"- Latest data date: `{result.get('latest_data_date')}`",
        f"- Data completeness: `{result.get('data_completeness', '')}`",
        f"- Raw latest data date: `{result.get('raw_latest_data_date', '')}`",
        f"- Accepted latest data date: `{result.get('accepted_latest_data_date', '')}`",
        f"- Latest action: `{result.get('latest_action')}`",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| CAGR | {'' if result.get('CAGR') is None else format(result.get('CAGR'), '.2%')} |",
        f"| Calmar | {'' if result.get('Calmar') is None else format(result.get('Calmar'), '.3f')} |",
        f"| Max Drawdown | {'' if result.get('Max Drawdown') is None else format(result.get('Max Drawdown'), '.2%')} |",
    ]
    if payload.get("warnings"):
        lines.extend(["", "## Warnings", ""])
        lines.extend([f"- {item}" for item in payload["warnings"]])
    if payload.get("errors"):
        lines.extend(["", "## Errors", ""])
        lines.extend([f"- {item}" for item in payload["errors"]])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_manifest(output_dir: Path) -> Path:
    rows = []
    for path in sorted(output_dir.rglob("*")):
        if path.is_file():
            stat = path.stat()
            rows.append({"path": str(path), "size_bytes": stat.st_size, "mtime": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds")})
    manifest_path = output_dir / "588200_artifacts_manifest.json"
    write_json(manifest_path, {"files": rows, "count": len(rows)})
    return manifest_path


def parse_date(value: Any) -> date | None:
    try:
        text = str(value or "").strip()
        return datetime.strptime(text, "%Y-%m-%d").date() if text else None
    except Exception:
        return None


def find_previous_successful_artifact(output_dir: Path) -> tuple[Path | None, dict[str, Any]]:
    candidates: list[Path] = []
    for root in [ROOT / "outputs" / "daily_quant_lab_runs", ROOT / "outputs" / "588200_latest_signal"]:
        if root.exists():
            candidates.extend(root.rglob("588200_job_summary.json"))
    candidates = sorted(
        [path for path in candidates if not output_dir.resolve() in path.resolve().parents],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for path in candidates:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        result = payload.get("result") if isinstance(payload, dict) else None
        if not isinstance(result, dict):
            continue
        status = str(payload.get("status") or result.get("status") or "").upper()
        latest = parse_date(result.get("latest_data_date"))
        if status in {"PASS", "PASS_WITH_FALLBACK"} and latest is not None and result.get("latest_action"):
            return path, payload
    return None, {}


def copy_previous_artifacts(previous_dir: Path, output_dir: Path) -> dict[str, str]:
    copied: dict[str, str] = {}
    for name in [
        "588200_latest_signal.csv",
        "588200_metrics.csv",
        "588200_tradeable_price.csv",
        "588200_tradeable_price.json",
    ]:
        source = previous_dir / name
        if source.exists():
            dest = output_dir / name
            shutil.copy2(source, dest)
            copied[name] = str(dest)
    return copied


def apply_previous_successful_fallback(payload: dict[str, Any], output_dir: Path, reason: str) -> bool:
    summary_path, previous = find_previous_successful_artifact(output_dir)
    if summary_path is None:
        return False
    previous_dir = summary_path.parent
    result = copy.deepcopy(previous.get("result", {}))
    latest = parse_date(result.get("latest_data_date"))
    stale_days = (date.today() - latest).days if latest else None
    stale = stale_days is None or stale_days > MAX_FALLBACK_STALE_DAYS
    copied = copy_previous_artifacts(previous_dir, output_dir)
    fallback_status = {
        "data_source_status": "FALLBACK_PREVIOUS_SUCCESSFUL_ARTIFACT",
        "fallback_artifact_path": str(summary_path),
        "fallback_artifact_run_dir": str(previous_dir),
        "fallback_latest_data_date": result.get("latest_data_date"),
        "fallback_stale_days": stale_days,
        "max_fallback_stale_days": MAX_FALLBACK_STALE_DAYS,
        "stale_data_flag": bool(stale),
        "copied_artifacts": copied,
        "fallback_reason": reason,
    }
    write_json(output_dir / "588200_fallback_status.json", fallback_status)
    if stale:
        make_blocked_result(
            payload,
            output_dir,
            status="BLOCKED_STALE_DATA",
            error_message=(
                f"{reason} Previous successful artifact is stale: "
                f"latest_data_date={result.get('latest_data_date')}, stale_days={stale_days}."
            ),
            extra=fallback_status,
        )
        return True
    result["status"] = "PASS_WITH_FALLBACK"
    result["output_dir"] = str(output_dir)
    if "588200_latest_signal.csv" in copied:
        result["signal_file"] = copied["588200_latest_signal.csv"]
    if "588200_tradeable_price.csv" in copied:
        result["tradeable_price_file"] = copied["588200_tradeable_price.csv"]
    tradeable_json = output_dir / "588200_tradeable_price.json"
    if tradeable_json.exists():
        try:
            result["tradeable_price"] = json.loads(tradeable_json.read_text(encoding="utf-8"))
        except Exception:
            pass
    result.update(fallback_status)
    payload["status"] = "PASS_WITH_FALLBACK"
    payload["result"] = result
    payload["warnings"].append(
        f"{reason} Used previous successful 588200 artifact from {summary_path}; latest_data_date={result.get('latest_data_date')}."
    )
    payload["fallback"] = fallback_status
    return True


def make_blocked_result(payload: dict[str, Any], output_dir: Path, *, status: str, error_message: str, extra: dict[str, Any] | None = None) -> None:
    tradeable_price = {
        "symbol": "588200",
        "price_date": "",
        "tradeable_close": None,
        "source": "unavailable",
        "source_field": "",
        "adjust_flag": "unknown",
        "price_is_tradeable": False,
        "price_validation_status": "DATA_REFRESH_FAILED" if status == "BLOCKED_DATA_MISSING" else status,
        "notes": error_message,
    }
    pd.DataFrame([tradeable_price]).to_csv(output_dir / "588200_tradeable_price.csv", index=False, encoding="utf-8-sig")
    write_json(output_dir / "588200_tradeable_price.json", tradeable_price)
    result = {
        "symbol": "588200",
        "frozen_strategy_id": FROZEN_STRATEGY_ID,
        "status": status,
        "latest_data_date": "",
        "latest_action": "UNKNOWN",
        "position": None,
        "signal": {
            "latest_signal_date": "",
            "next_open_date": "",
            "latest_close": None,
            "latest_desired_after_close": None,
            "position_at_latest_open": None,
            "latest_action": "UNKNOWN",
        },
        "metric_scope": "",
        "CAGR": None,
        "Calmar": None,
        "Max Drawdown": None,
        "stock_count": 0,
        "output_dir": str(output_dir),
        "signal_file": "",
        "tradeable_price_file": str(output_dir / "588200_tradeable_price.csv"),
        "tradeable_price": tradeable_price,
        "data_source_status": status,
        "stale_data_flag": status == "BLOCKED_STALE_DATA",
        "error_message": error_message,
    }
    if extra:
        result.update(extra)
    payload["status"] = status
    payload["result"] = result
    payload["errors"].append(error_message)


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir) if args.output_dir else ROOT / "outputs" / "588200_latest_signal" / f"latest_{stamp()}"
    output_dir.mkdir(parents=True, exist_ok=True)
    json_out = Path(args.json_out) if args.json_out else output_dir / "588200_job_summary.json"
    md_out = Path(args.md_out) if args.md_out else output_dir / "588200_job_summary.md"
    payload: dict[str, Any] = {
        "job": "588200",
        "status": "DRY_RUN" if args.dry_run else "RUNNING",
        "output_dir": str(output_dir),
        "frozen_strategy_id": FROZEN_STRATEGY_ID,
        "data_download_performed": False,
        "search_performed": False,
        "longrun_search_called": False,
        "result": {},
        "warnings": [],
        "errors": [],
    }
    if args.dry_run:
        write_json(json_out, payload)
        write_markdown(md_out, payload)
        write_manifest(output_dir)
        print(json.dumps(jsonable({"status": "DRY_RUN", "output_dir": output_dir}), indent=2))
        return 0

    try:
        if args.skip_download:
            target_data, stocks, status_rows, warnings = load_local_data()
            payload["warnings"].extend(warnings)
        else:
            target_data, stocks, status_rows, warnings = refresh_online_data()
            payload["warnings"].extend(warnings)
            payload["data_download_performed"] = True
        pd.DataFrame(status_rows).to_csv(output_dir / "588200_data_status.csv", index=False, encoding="utf-8-sig")

        target_asset = target_data.get(TARGET, pd.DataFrame())
        if target_asset.empty:
            reason = "Target 588200.SS data is missing after refresh."
            if not apply_previous_successful_fallback(payload, output_dir, reason):
                make_blocked_result(payload, output_dir, status="BLOCKED_DATA_MISSING", error_message=reason)
            manifest = write_manifest(output_dir)
            payload["artifacts_manifest"] = str(manifest)
            write_json(json_out, payload)
            write_markdown(md_out, payload)
            print(json.dumps(jsonable({"status": payload["status"], "output_dir": output_dir, "json": json_out}), indent=2))
            return 0
        if len(stocks) < 10:
            reason = f"Too few constituent stocks loaded after refresh: {len(stocks)}."
            if not apply_previous_successful_fallback(payload, output_dir, reason):
                make_blocked_result(payload, output_dir, status="BLOCKED_DATA_MISSING", error_message=reason)
            manifest = write_manifest(output_dir)
            payload["artifacts_manifest"] = str(manifest)
            write_json(json_out, payload)
            write_markdown(md_out, payload)
            print(json.dumps(jsonable({"status": payload["status"], "output_dir": output_dir, "json": json_out}), indent=2))
            return 0

        target_asset, stocks, eod_meta, status_rows = apply_ashare_eod_filter(target_asset, stocks, status_rows)
        payload["data_completeness"] = eod_meta
        pd.DataFrame(status_rows).to_csv(output_dir / "588200_data_status.csv", index=False, encoding="utf-8-sig")
        if target_asset.empty:
            reason = f"Target 588200.SS data is empty after A-share EOD completeness filter: {eod_meta.get('reason', '')}"
            if not apply_previous_successful_fallback(payload, output_dir, reason):
                make_blocked_result(payload, output_dir, status="BLOCKED_DATA_MISSING", error_message=reason, extra=eod_meta)
            manifest = write_manifest(output_dir)
            payload["artifacts_manifest"] = str(manifest)
            write_json(json_out, payload)
            write_markdown(md_out, payload)
            print(json.dumps(jsonable({"status": payload["status"], "output_dir": output_dir, "json": json_out}), indent=2))
            return 0

        latest = target_asset.index.max()
        start = pd.Timestamp(START)
        train_end = pd.Timestamp(TRAIN_END)
        test_start = train_end + pd.Timedelta(days=1)
        end = latest
        target_asset = target_asset.loc[:end].copy()
        stocks = {code: frame.loc[:end].copy() for code, frame in stocks.items()}

        breadth = build_breadth_features(stocks)
        combo_breadth = build_combo_factor_breadth(stocks)
        spec = build_fixed_spec()
        cache = build_longrun_signal_cache(target_asset, breadth, {COMBO_FACTOR: combo_breadth}, [spec])
        desired = longrun_signal_from_cache(cache, spec)
        nav, returns, position = backtest_binary_position(target_asset, desired, cost_rate=COST_RATE)
        hold_returns = buy_hold_returns(target_asset)

        metrics = {
            "train": compute_performance_metrics(returns, start, train_end, RISK_FREE),
            "test": compute_performance_metrics(returns, test_start, end, RISK_FREE),
            "full": compute_performance_metrics(returns, start, end, RISK_FREE),
        }
        hold_metrics = {
            "train": compute_performance_metrics(hold_returns, start, train_end, RISK_FREE),
            "test": compute_performance_metrics(hold_returns, test_start, end, RISK_FREE),
            "full": compute_performance_metrics(hold_returns, start, end, RISK_FREE),
        }
        signal = latest_action(target_asset, desired, position)
        tradeable_price = get_tradeable_price(TARGET, max_date=latest)
        if tradeable_price.get("price_is_tradeable") and tradeable_price.get("price_date") != signal.get("latest_signal_date"):
            payload["warnings"].append(
                f"588200 tradeable close date {tradeable_price.get('price_date')} differs from signal date {signal.get('latest_signal_date')}."
            )
        if not tradeable_price.get("price_is_tradeable"):
            payload["warnings"].append(f"588200 tradeable close unavailable: {tradeable_price.get('notes')}")
        pd.DataFrame([tradeable_price]).to_csv(output_dir / "588200_tradeable_price.csv", index=False, encoding="utf-8-sig")
        write_json(output_dir / "588200_tradeable_price.json", tradeable_price)

        signal_df = pd.DataFrame(
            {
                "open": target_asset["open"],
                "high": target_asset["high"],
                "low": target_asset["low"],
                "close": target_asset["close"],
                "volume": target_asset["volume"],
                "desired_after_close": desired,
                "position_next_open": position,
                "strategy_nav": nav,
                "strategy_return": returns,
                "buy_hold_nav": (1 + hold_returns).cumprod(),
                "breadth_ma60": breadth["breadth_ma60"].reindex(target_asset.index).ffill(),
                "pool_ret20_median": breadth["pool_ret20_median"].reindex(target_asset.index).ffill(),
                COMBO_FACTOR: combo_breadth.reindex(target_asset.index).ffill(),
            }
        )
        signal_path = output_dir / "588200_latest_signal.csv"
        signal_df.to_csv(signal_path, index=True, index_label="date", encoding="utf-8-sig")

        metric_row: dict[str, Any] = {
            "strategy": FROZEN_STRATEGY_ID,
            "latest_date": latest.strftime("%Y-%m-%d"),
            "latest_action": signal["latest_action"],
            "latest_desired_after_close": signal["latest_desired_after_close"],
            "stock_count": len(stocks),
            "cost_rate": COST_RATE,
            "data_completeness": eod_meta.get("data_completeness", ""),
            "raw_latest_data_date": eod_meta.get("raw_latest_data_date", ""),
            "accepted_latest_data_date": eod_meta.get("accepted_latest_data_date", ""),
            "eod_completeness_rule": eod_meta.get("rule", ""),
        }
        for scope, values in metrics.items():
            for key, value in values.items():
                metric_row[f"{scope}_{key}"] = value
        for scope, values in hold_metrics.items():
            for key, value in values.items():
                metric_row[f"bh_{scope}_{key}"] = value
        pd.DataFrame([metric_row]).to_csv(output_dir / "588200_metrics.csv", index=False, encoding="utf-8-sig")

        payload["status"] = "PASS"
        payload["result"] = {
            "symbol": "588200",
            "frozen_strategy_id": FROZEN_STRATEGY_ID,
            "status": "PASS",
            "latest_data_date": latest.strftime("%Y-%m-%d"),
            "latest_action": signal["latest_action"],
            "position": signal["position_at_latest_open"],
            "signal": signal,
            "data_completeness": eod_meta.get("data_completeness", ""),
            "raw_latest_data_date": eod_meta.get("raw_latest_data_date", ""),
            "accepted_latest_data_date": eod_meta.get("accepted_latest_data_date", ""),
            "eod_completeness_rule": eod_meta.get("rule", ""),
            "eod_completeness_reason": eod_meta.get("reason", ""),
            "eod_checked_at": eod_meta.get("checked_at", ""),
            "metric_scope": "test_start_to_latest",
            "CAGR": metrics["test"]["annual_return"],
            "Calmar": metrics["test"]["calmar"],
            "Max Drawdown": metrics["test"]["max_drawdown"],
            "train_metrics": metrics["train"],
            "test_metrics": metrics["test"],
            "full_metrics": metrics["full"],
            "buy_hold_metrics": hold_metrics,
            "stock_count": len(stocks),
            "output_dir": str(output_dir),
            "signal_file": str(signal_path),
            "tradeable_price_file": str(output_dir / "588200_tradeable_price.csv"),
            "tradeable_price": tradeable_price,
            "error_message": "",
        }
    except Exception as exc:
        payload["status"] = "FAIL"
        payload["errors"].append(f"{type(exc).__name__}: {exc}")
        payload["result"] = {
            "symbol": "588200",
            "frozen_strategy_id": FROZEN_STRATEGY_ID,
            "status": "FAIL",
            "output_dir": str(output_dir),
            "error_message": f"{type(exc).__name__}: {exc}",
        }

    manifest = write_manifest(output_dir)
    payload["artifacts_manifest"] = str(manifest)
    write_json(json_out, payload)
    write_markdown(md_out, payload)
    print(json.dumps(jsonable({"status": payload["status"], "output_dir": output_dir, "json": json_out}), indent=2))
    return 0 if payload["status"] in {"PASS", "PASS_WITH_FALLBACK", "BLOCKED_DATA_MISSING", "BLOCKED_STALE_DATA"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
