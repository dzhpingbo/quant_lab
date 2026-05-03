"""TD9 + multi-factor strategy search for US mega caps, ETFs/funds, and indices.

The script uses local quant_lab price data, updates a curated available US
universe with yfinance in batches, and evaluates TD9 overlays with vectorbt.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import warnings
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Mapping

import numpy as np
import pandas as pd

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

import vbt_us_leverage_online as base
import vbt_us_leverage_momentum_combo as mom


LEGACY_DIR = ROOT / "data" / "external" / "legacy_quant" / "NSDQStock" / "19800101_20260404"
OUT_ROOT = ROOT / "outputs" / "us_td9_all_assets"
CACHE_DIR = OUT_ROOT / "_cache"

MAG7 = ("AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "TSLA")
CORE_CONTEXT = ("QQQ", "SPY", "_VIX", "TLT", "SHY", "GLD", "IWM", "XLK", "SOXX", "RSP", "UUP", "SQQQ", "PSQ")

ETF_FUND_INDEX_CANDIDATES = (
    "_VIX",
    "SPY", "QQQ", "DIA", "IWM", "VTI", "VOO", "IVV", "SPLG", "RSP",
    "QLD", "TQQQ", "SQQQ", "PSQ", "QID", "UPRO", "SSO", "SPXU", "SH",
    "UDOW", "SDOW", "URTY", "SRTY", "TNA", "TZA",
    "XLK", "XLF", "XLE", "XLY", "XLP", "XLU", "XLI", "XLB", "XLV", "XLRE", "XLC",
    "VGT", "VUG", "VTV", "VYM", "SCHD", "SCHG", "SCHX", "SCHA", "IWF", "IWD",
    "IWB", "IWR", "IWS", "IJH", "IJR", "VB", "VO", "VV", "MTUM", "QUAL", "USMV",
    "SMH", "SOXX", "SOXL", "SOXS", "XSD", "IGV", "FDN", "ARKK", "ARKW", "ARKG", "ARKF", "ARKQ",
    "TLT", "IEF", "SHY", "BIL", "SGOV", "AGG", "BND", "LQD", "HYG", "JNK", "TIP",
    "GLD", "IAU", "SLV", "GDX", "GDXJ", "USO", "UNG", "DBA", "DBC", "UUP",
    "EEM", "EFA", "VEA", "VWO", "IEFA", "IEMG", "FXI", "KWEB", "EWJ", "EWZ", "EWT", "INDA", "EWY",
    "XBI", "IBB", "IHI", "ITA", "XAR", "KRE", "KBE", "XRT", "IYR", "VNQ", "REM",
    "PFF", "MUB", "EMB", "BKLN", "CWB", "PDBC", "BITO", "GBTC", "IBIT", "ETHE",
    "JEPI", "JEPQ", "DIVO", "NOBL", "DGRO", "VIG", "SPYD", "SPHD",
    "ADX", "AIO", "ASA", "BME", "BMEZ", "BST", "BSTZ", "CET", "ETY", "EXG", "GAB",
    "GOF", "HQH", "HTD", "MAIN", "OXLC", "PDI", "PDO", "PTY", "USA", "UTF", "UTG",
)

NASDAQ_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
    "Accept": "application/json,text/plain,*/*",
    "Referer": "https://www.nasdaq.com/",
}

FUND_LIKE_INDUSTRIES = {
    "Investment Managers",
    "Trusts Except Educational Religious and Charitable",
    "Finance/Investors Services",
    "Finance Companies",
    "Finance: Consumer Services",
    "Diversified Financial Services",
}

FUND_LIKE_EXCLUDE_TERMS = (
    "preferred",
    "warrant",
    "right",
    "notes due",
    "senior notes",
    "subordinated notes",
    "strats",
    "certificates",
    "funding company",
    "capital trust ii",
)

SOURCES = [
    {
        "name": "Local reusable factor catalog",
        "url": "outputs/factor_library_imports/full_reuse_catalog_snapshot_20260416.json",
        "use": "452 executable external panel factor names are registered locally; this run uses the same factor-combination contract and focuses on price/volume/TD9 tactical factors for US assets.",
    },
    {
        "name": "TD9 local safety factors",
        "url": "src/factors/safety.py",
        "use": "alpha_td9_buy_setup_4_9 and alpha_td9_sell_pressure_4_9 are used as explicit entry/exit overlays.",
    },
    {
        "name": "588200 TD9 combo research",
        "url": "docs/quant_lab_strategy_factor_upgrade_plan_20260412.md",
        "use": "Prior local research found TD9 works better as a combination filter with trend/low-risk factors than as a stand-alone button.",
    },
    {
        "name": "Momentum combo search",
        "url": "scripts/vbt_us_leverage_momentum_combo.py",
        "use": "Reuses EMA/SMA cross, MACD/ADX, ROC stack, VIX, and multi-factor score families.",
    },
    {
        "name": "Reusable strategy template catalog",
        "url": "scripts/research_us_leveraged_etf_full_strategy.py",
        "use": "Ports compact MA-band, Turtle, Dual Thrust, and RSI timing templates, then searches TD9 overlays on top.",
    },
    {
        "name": "QLD/TQQQ turning-point lab",
        "url": "scripts/qldtqqq_turning_point_lab.py",
        "use": "Reuses TD9, VIX percentile/spike, Bollinger, RSI, breadth, fear/greed, valuation proxy, and walk-forward ML bottom/top probabilities as market turning overlays.",
    },
]


@dataclass(frozen=True)
class Candidate:
    name: str
    family: str
    source: str
    signal: pd.Series
    notes: str


def stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(base.jready(data), ensure_ascii=False, indent=2), encoding="utf-8")


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
            lines += [f"### {key}", "", "```json", json.dumps(base.jready(value), ensure_ascii=False, indent=2), "```", ""]
        else:
            lines.append(f"- {key}: {value}")
    (run_dir / f"checkpoint_{stage}.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def read_price_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    cols = {str(c).strip().lower(): c for c in df.columns}
    if "date" not in cols:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    dates = pd.to_datetime(df[cols["date"]], errors="coerce", utc=True).dt.tz_convert(None).dt.normalize()
    out = pd.DataFrame(index=dates)
    for col in ("open", "high", "low", "close", "volume"):
        source = cols.get(col)
        out[col] = pd.to_numeric(df[source], errors="coerce").to_numpy() if source is not None else np.nan
    out.index.name = "date"
    out = out.dropna(subset=["close"]).sort_index()
    out = out[~out.index.duplicated(keep="last")]
    return out[["open", "high", "low", "close", "volume"]]


def write_price_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    out = frame[["close", "high", "low", "open", "volume"]].copy()
    out.index.name = "date"
    out.to_csv(path, encoding="utf-8")


def existing_symbols(symbols: tuple[str, ...] | list[str]) -> list[str]:
    out = []
    for sym in symbols:
        if (LEGACY_DIR / f"{sym}.csv").exists():
            out.append(sym)
    return list(dict.fromkeys(out))


def local_symbol_set() -> set[str]:
    return {path.stem.upper() for path in LEGACY_DIR.glob("*.csv")}


def normalize_symbol(symbol: object) -> str:
    return str(symbol or "").strip().upper().replace("/", "-")


def nasdaq_rows(payload: object) -> list[dict]:
    if not isinstance(payload, dict):
        return []
    data = payload.get("data") or {}
    if isinstance(data, dict):
        if isinstance(data.get("rows"), list):
            return data["rows"]
        nested = data.get("data") or {}
        if isinstance(nested, dict) and isinstance(nested.get("rows"), list):
            return nested["rows"]
        records = data.get("records") or {}
        if isinstance(records, dict):
            rec_data = records.get("data") or {}
            if isinstance(rec_data, dict) and isinstance(rec_data.get("rows"), list):
                return rec_data["rows"]
    return []


def fetch_nasdaq_rows(url: str, timeout: int = 45) -> list[dict]:
    import requests

    response = requests.get(url, headers=NASDAQ_HEADERS, timeout=timeout)
    response.raise_for_status()
    return nasdaq_rows(response.json())


def is_fund_like_stock(row: Mapping[str, object]) -> bool:
    name = str(row.get("name") or row.get("companyName") or "")
    low = name.lower()
    if any(term in low for term in FUND_LIKE_EXCLUDE_TERMS):
        return False
    explicit = bool(re.search(r"\b(etf|etn|fund|bdc)\b", low))
    explicit = explicit or "closed-end" in low or "closed end" in low
    if explicit:
        return True
    sector = str(row.get("sector") or "")
    industry = str(row.get("industry") or "")
    return sector == "Finance" and industry in FUND_LIKE_INDUSTRIES and bool(re.search(r"\btrust\b", low))


def load_asset_metadata(refresh: bool) -> list[dict]:
    cache_path = CACHE_DIR / "us_fund_etf_index_universe_metadata.json"
    cached_rows: list[dict] = []
    if cache_path.exists() and not refresh:
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            rows = cached.get("rows", [])
            if isinstance(rows, list) and rows:
                return rows
        except Exception:
            pass
    elif cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            rows = cached.get("rows", [])
            if isinstance(rows, list):
                cached_rows = [row for row in rows if isinstance(row, dict)]
        except Exception:
            cached_rows = []

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    local = local_symbol_set()
    rows_by_symbol: dict[str, dict] = {normalize_symbol(row.get("symbol")): row for row in cached_rows if normalize_symbol(row.get("symbol")) in local}
    source_errors = []

    try:
        etf_rows = fetch_nasdaq_rows("https://api.nasdaq.com/api/screener/etf?tableonly=true&limit=10000&download=true")
        for row in etf_rows:
            sym = normalize_symbol(row.get("symbol"))
            if sym in local:
                rows_by_symbol[sym] = {
                    "symbol": sym,
                    "asset_type": "etf",
                    "name": row.get("companyName") or row.get("name") or "",
                    "source": "nasdaq_etf_screener",
                }
    except Exception as exc:
        source_errors.append({"source": "nasdaq_etf_screener", "error": f"{type(exc).__name__}: {exc}"})

    for exchange in ("nasdaq", "nyse", "amex"):
        url = f"https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=10000&exchange={exchange}&download=true"
        try:
            stock_rows = fetch_nasdaq_rows(url)
        except Exception as exc:
            source_errors.append({"source": f"nasdaq_stock_screener_{exchange}", "error": f"{type(exc).__name__}: {exc}"})
            continue
        for row in stock_rows:
            sym = normalize_symbol(row.get("symbol"))
            if sym not in local or sym in rows_by_symbol or not is_fund_like_stock(row):
                continue
            rows_by_symbol[sym] = {
                "symbol": sym,
                "asset_type": "fund",
                "name": row.get("name") or row.get("companyName") or "",
                "source": f"nasdaq_stock_screener_{exchange}",
                "sector": row.get("sector") or "",
                "industry": row.get("industry") or "",
            }

    for sym in existing_symbols(list(ETF_FUND_INDEX_CANDIDATES)):
        rows_by_symbol.setdefault(
            sym,
            {
                "symbol": sym,
                "asset_type": "curated_fund_etf_index",
                "name": "",
                "source": "local_curated_us_asset_list",
            },
        )

    for sym in sorted(s for s in local if s.startswith("_")):
        rows_by_symbol[sym] = {
            "symbol": sym,
            "asset_type": "index",
            "name": sym,
            "source": "local_index_file",
        }

    rows = sorted(rows_by_symbol.values(), key=lambda x: (str(x.get("asset_type")), str(x.get("symbol"))))
    if rows:
        write_json(
            cache_path,
            {
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "row_count": len(rows),
                "source_errors": source_errors,
                "rows": rows,
            },
        )
    elif cache_path.exists():
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        rows = cached.get("rows", [])
    return rows


def build_universe(max_symbols: int, refresh_metadata: bool = False) -> pd.DataFrame:
    rows = []
    selected: dict[str, dict] = {}
    for sym in MAG7:
        if (LEGACY_DIR / f"{sym}.csv").exists():
            selected[sym] = {"symbol": sym, "group": "mag7", "asset_type": "equity", "name": sym, "source": "mag7"}
    for row in load_asset_metadata(refresh_metadata):
        sym = normalize_symbol(row.get("symbol"))
        if not sym or not (LEGACY_DIR / f"{sym}.csv").exists():
            continue
        group = "index" if sym.startswith("_") or row.get("asset_type") == "index" else "fund_etf_index"
        selected.setdefault(
            sym,
            {
                "symbol": sym,
                "group": group,
                "asset_type": row.get("asset_type") or group,
                "name": row.get("name") or sym,
                "source": row.get("source") or "metadata",
            },
        )
    for sym in existing_symbols(list(CORE_CONTEXT)):
        selected.setdefault(sym, {"symbol": sym, "group": "fund_etf_index", "asset_type": "context", "name": sym, "source": "core_context"})

    for sym, meta in selected.items():
        frame = read_price_csv(LEGACY_DIR / f"{sym}.csv")
        if frame.empty or len(frame) < 252:
            continue
        rows.append(
            {
                "symbol": sym,
                "group": meta["group"],
                "asset_type": meta.get("asset_type", ""),
                "name": meta.get("name", ""),
                "source": meta.get("source", ""),
                "local_start": frame.index.min().strftime("%Y-%m-%d"),
                "local_last": frame.index.max().strftime("%Y-%m-%d"),
                "rows": len(frame),
                "local_close": float(frame["close"].iloc[-1]),
            }
        )
    df = pd.DataFrame(rows).sort_values(["group", "asset_type", "symbol"])
    if max_symbols and len(df) > max_symbols:
        must = set(MAG7) | set(CORE_CONTEXT) | {"QLD", "TQQQ"}
        keep = df[df["symbol"].isin(must)]
        remaining = max(0, max_symbols - len(keep))
        rest = df[~df["symbol"].isin(must)].sort_values(["rows", "symbol"], ascending=[False, True]).head(remaining)
        df = pd.concat([keep, rest], ignore_index=True)
    return df.reset_index(drop=True)


def fetch_yfinance_batch(symbols: list[str], start: str, end: str) -> dict[str, pd.DataFrame]:
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        os.environ.setdefault(key, "http://127.0.0.1:7897")
    import yfinance as yf

    yf_symbols = ["^VIX" if s == "_VIX" else s for s in symbols]
    raw = yf.download(yf_symbols, start=start, end=end, auto_adjust=True, group_by="ticker", progress=False, threads=True, timeout=45)
    out: dict[str, pd.DataFrame] = {}
    if raw is None or raw.empty:
        return out
    for sym, yf_sym in zip(symbols, yf_symbols):
        try:
            if isinstance(raw.columns, pd.MultiIndex):
                sub = raw[yf_sym].copy()
            else:
                sub = raw.copy()
            sub = sub.rename(columns={str(c): str(c).lower().replace(" ", "_") for c in sub.columns})
            if "adj_close" in sub.columns and "close" not in sub.columns:
                sub = sub.rename(columns={"adj_close": "close"})
            if "close" not in sub.columns:
                continue
            for col in ("open", "high", "low"):
                if col not in sub.columns:
                    sub[col] = sub["close"]
            if "volume" not in sub.columns:
                sub["volume"] = 0.0
            sub.index = pd.to_datetime(sub.index).tz_localize(None).normalize()
            sub.index.name = "date"
            sub = sub[["open", "high", "low", "close", "volume"]].dropna(subset=["close"]).sort_index()
            if not sub.empty:
                out[sym] = sub
        except Exception:
            continue
    return out


def update_data(run_dir: Path, universe: pd.DataFrame, today: str, chunk_size: int) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    symbols = universe["symbol"].tolist()
    data: dict[str, pd.DataFrame] = {}
    rows = []
    updated_dir = run_dir / "updated_data"
    online_all: dict[str, pd.DataFrame] = {}
    universe_meta = universe.set_index("symbol")
    exclusive_end = pd.Timestamp(today)
    for i in range(0, len(symbols), chunk_size):
        chunk = symbols[i : i + chunk_size]
        try:
            online_all.update(fetch_yfinance_batch(chunk, "2000-01-01", today))
        except Exception as exc:
            rows.append({"symbol": ",".join(chunk), "status": "batch_failed", "error": f"{type(exc).__name__}: {exc}"})
    for sym in symbols:
        local = read_price_csv(LEGACY_DIR / f"{sym}.csv")
        online = online_all.get(sym, pd.DataFrame())
        frames = [x for x in (local, online) if x is not None and not x.empty]
        merged = pd.concat(frames).sort_index() if frames else local
        merged = merged[~merged.index.duplicated(keep="last")]
        merged = merged.dropna(subset=["close"])
        merged = merged[merged.index < exclusive_end]
        if not merged.empty:
            write_price_csv(updated_dir / f"{sym}.csv", merged)
            if sym in set(MAG7) | set(CORE_CONTEXT) | {"QLD", "TQQQ"}:
                write_price_csv(LEGACY_DIR / f"{sym}.csv", merged)
        data[sym] = merged
        rows.append(
            {
                "symbol": sym,
                "status": "ok_yfinance" if sym in online_all else "local_only",
                "local_last": local.index.max().strftime("%Y-%m-%d") if not local.empty else "",
                "online_last": online.index.max().strftime("%Y-%m-%d") if not online.empty else "",
                "merged_last": merged.index.max().strftime("%Y-%m-%d") if not merged.empty else "",
                "rows": len(merged),
                "group": universe_meta.loc[sym, "group"],
                "asset_type": universe_meta.loc[sym, "asset_type"] if "asset_type" in universe_meta else "",
                "name": universe_meta.loc[sym, "name"] if "name" in universe_meta else "",
            }
        )
    status = pd.DataFrame(rows)
    status.to_csv(run_dir / "latest_data_status.csv", index=False, encoding="utf-8-sig")
    return data, status


def td_counts(close: pd.Series, lookback: int = 4, setup: int = 9) -> tuple[pd.Series, pd.Series]:
    buy = close < close.shift(lookback)
    sell = close > close.shift(lookback)
    buy_count = []
    sell_count = []
    b = s = 0
    for bv, sv in zip(buy.fillna(False), sell.fillna(False)):
        b = min(setup, b + 1) if bv else 0
        s = min(setup, s + 1) if sv else 0
        buy_count.append(b)
        sell_count.append(s)
    return pd.Series(buy_count, index=close.index), pd.Series(sell_count, index=close.index)


def factor_score(asset: pd.DataFrame, qqq: pd.DataFrame, vix: pd.DataFrame) -> pd.Series:
    feats = mom.build_score_features(asset, qqq, vix)
    buy_td, sell_td = td_counts(asset["close"])
    feats["td_buy_progress"] = buy_td >= 4
    feats["td_sell_not_extreme"] = sell_td < 8
    return sum(x.astype(float) for x in feats.values())


def state_between(score: pd.Series, enter: float, exit_: float, name: str) -> pd.Series:
    return mom.state(score, enter, exit_, name)


def ma_band_signal(close: pd.Series, window: int, enter: float, exit_: float, name: str) -> pd.Series:
    basis = close.rolling(window).mean()
    held = False
    out = []
    for price, ma_value in zip(close.astype(float), basis.astype(float)):
        if np.isnan(price) or np.isnan(ma_value):
            out.append(1.0 if held else 0.0)
            continue
        if not held and price >= ma_value * enter:
            held = True
        elif held and price <= ma_value * exit_:
            held = False
        out.append(1.0 if held else 0.0)
    return pd.Series(out, index=close.index, name=name)


def rsi_signal(close: pd.Series, window: int, enter: float, exit_: float, name: str) -> pd.Series:
    rsi = mom.rsi(close, window)
    held = False
    out = []
    for value in rsi.astype(float):
        if np.isnan(value):
            out.append(1.0 if held else 0.0)
            continue
        if not held and value <= enter:
            held = True
        elif held and value >= exit_:
            held = False
        out.append(1.0 if held else 0.0)
    return pd.Series(out, index=close.index, name=name)


def turtle_signal(asset: pd.DataFrame, entry: int, exit_: int, name: str) -> pd.Series:
    entry_high = asset["high"].rolling(entry).max().shift(1)
    exit_low = asset["low"].rolling(exit_).min().shift(1)
    held = False
    out = []
    for close_value, high_value, low_value in zip(asset["close"], entry_high, exit_low):
        if not held and pd.notna(high_value) and close_value > high_value:
            held = True
        elif held and pd.notna(low_value) and close_value < low_value:
            held = False
        out.append(1.0 if held else 0.0)
    return pd.Series(out, index=asset.index, name=name)


def dual_thrust_signal(asset: pd.DataFrame, window: int, k: float, name: str) -> pd.Series:
    hh = asset["high"].rolling(window).max().shift(1)
    lc = asset["close"].rolling(window).min().shift(1)
    hc = asset["close"].rolling(window).max().shift(1)
    ll = asset["low"].rolling(window).min().shift(1)
    rng = pd.concat([hh - lc, hc - ll], axis=1).max(axis=1)
    upper = asset["open"] + k * rng
    lower = asset["open"] - k * rng
    held = False
    out = []
    for close_value, upper_value, lower_value in zip(asset["close"], upper, lower):
        if not held and pd.notna(upper_value) and close_value > upper_value:
            held = True
        elif held and pd.notna(lower_value) and close_value < lower_value:
            held = False
        out.append(1.0 if held else 0.0)
    return pd.Series(out, index=asset.index, name=name)


def td9_pullback_signal(asset: pd.DataFrame, trend: pd.Series, enter_count: int, exit_sell: int, name: str) -> pd.Series:
    buy_td, sell_td = td_counts(asset["close"])
    held = False
    out = []
    for dt in asset.index:
        trend_ok = bool(trend.get(dt, False))
        if not held and trend_ok and buy_td.loc[dt] >= enter_count:
            held = True
        elif held and ((sell_td.loc[dt] >= exit_sell) or (not trend_ok)):
            held = False
        out.append(1.0 if held else 0.0)
    return pd.Series(out, index=asset.index, name=name)


def td9_exit_overlay(base_sig: pd.Series, asset: pd.DataFrame, sell_count: int, name: str) -> pd.Series:
    _buy_td, sell_td = td_counts(asset["close"])
    held = False
    out = []
    for dt, want in base_sig.fillna(0.0).items():
        if not held and want > 0.5:
            held = True
        elif held and (want <= 0.5 or sell_td.loc[dt] >= sell_count):
            held = False
        out.append(1.0 if held else 0.0)
    return pd.Series(out, index=base_sig.index, name=name)


def td9_reentry_overlay(base_sig: pd.Series, asset: pd.DataFrame, buy_count: int, name: str) -> pd.Series:
    buy_td, sell_td = td_counts(asset["close"])
    held = False
    out = []
    for dt, want in base_sig.fillna(0.0).items():
        if not held and want > 0.5 and (buy_td.loc[dt] >= buy_count or buy_td.loc[dt] == 0):
            held = True
        elif held and (want <= 0.5 or sell_td.loc[dt] >= 9):
            held = False
        out.append(1.0 if held else 0.0)
    return pd.Series(out, index=base_sig.index, name=name)


def _import_turning_lab():
    import qldtqqq_turning_point_lab as qtp

    return qtp


def build_market_turning_bundle(data: Mapping[str, pd.DataFrame], run_dir: Path) -> dict[str, object]:
    """Build reusable QQQ market turning features and walk-forward ML probabilities."""

    qtp = _import_turning_lab()
    index = data["QQQ"].index
    labels, events = qtp.label_turning_points(data["QQQ"])
    features, scores, meta = qtp.build_feature_frame(data, index, run_dir)
    cols = qtp.feature_columns(features)
    probs, folds = qtp.walk_forward_probabilities(features, labels, cols, run_dir)
    labels.to_csv(run_dir / "turning_labels.csv", encoding="utf-8-sig")
    events.to_csv(run_dir / "turning_events.csv", index=False, encoding="utf-8-sig")
    features.to_csv(run_dir / "turning_features.csv", encoding="utf-8-sig")
    scores.to_csv(run_dir / "turning_scores.csv", encoding="utf-8-sig")
    write_json(
        run_dir / "turning_feature_meta.json",
        {
            "features": cols,
            "feature_count": len(cols),
            "event_count": len(events),
            "source_meta": meta,
            "model_folds": folds.to_dict("records"),
        },
    )
    return {"features": features, "scores": scores, "probs": probs, "events": events, "folds": folds, "meta": meta}


def load_market_turning_bundle(run_dir: Path) -> dict[str, object] | None:
    features_path = run_dir / "turning_features.csv"
    scores_path = run_dir / "turning_scores.csv"
    probs_path = run_dir / "walk_forward_probabilities.csv"
    if not (features_path.exists() and scores_path.exists() and probs_path.exists()):
        return None
    features = pd.read_csv(features_path, index_col=0, parse_dates=True)
    scores = pd.read_csv(scores_path, index_col=0, parse_dates=True)
    probs = pd.read_csv(probs_path, index_col=0, parse_dates=True)
    return {"features": features, "scores": scores, "probs": probs}


def add_market_turning_candidates(
    add,
    index: pd.Index,
    asset: pd.DataFrame,
    market_turning: Mapping[str, object] | None,
) -> None:
    if not market_turning:
        return
    try:
        qtp = _import_turning_lab()
        features = market_turning["features"].reindex(index).ffill()
        scores = market_turning["scores"].reindex(index).ffill()
        probs = market_turning["probs"].reindex(index).ffill().fillna(0.0)
        qtp_candidates = qtp.build_candidates(index, features, scores, probs)
    except Exception as exc:
        print(f"[WARN] market turning candidates skipped: {type(exc).__name__}: {exc}")
        return

    close = asset["close"].astype(float)
    asset_trend = close > close.rolling(200).mean()
    asset_fast_trend = close.rolling(20).mean() > close.rolling(60).mean()
    asset_panic = close / close.rolling(60).max() - 1.0 <= -0.12

    # Keep the strongest, economically distinct turning families so the search
    # benefits from ML/rule signals without letting parameter count explode.
    allow_families = {
        "trend_core_turning_trim",
        "ml_turning_prob",
        "hybrid_ml_rule",
        "trend_backbone_top_exit",
        "panic_rebound_sleeve",
        "multi_strategy_ensemble",
    }
    family_seen: dict[str, int] = {}
    for candidate in qtp_candidates:
        if candidate.family not in allow_families:
            continue
        family_seen[candidate.family] = family_seen.get(candidate.family, 0) + 1
        if family_seen[candidate.family] > 12:
            continue
        raw = candidate.signal.reindex(index).ffill().fillna(0.0).clip(0, 1)
        name = f"market_turn_{candidate.name}"
        add(
            name,
            f"market_{candidate.family}",
            "qldtqqq_turning_point_lab",
            raw,
            "QQQ market turning model reused across assets: " + candidate.notes,
        )
        gated = raw.where(asset_trend.reindex(index).fillna(False) | asset_panic.reindex(index).fillna(False), 0.0)
        add(
            f"{name}_assetgate",
            f"asset_gated_{candidate.family}",
            "qldtqqq_turning_point_lab",
            gated,
            "Same market turning signal, but only active when the asset is in a MA200 uptrend or already in a deep pullback.",
        )
        if candidate.family in {"panic_rebound_sleeve", "hybrid_ml_rule", "multi_strategy_ensemble"}:
            fast = raw.where(asset_fast_trend.reindex(index).fillna(False) | asset_panic.reindex(index).fillna(False), 0.0)
            add(
                f"{name}_fastgate",
                f"asset_fast_gated_{candidate.family}",
                "qldtqqq_turning_point_lab",
                fast,
                "Same market turning signal, gated by asset MA20/MA60 trend or deep-pullback rebound condition.",
            )


def build_candidates(
    symbol: str,
    asset: pd.DataFrame,
    context: Mapping[str, pd.DataFrame],
    market_turning: Mapping[str, object] | None = None,
) -> list[Candidate]:
    index = asset.index
    qqq = base.align(context["QQQ"], index)
    spy = base.align(context["SPY"], index)
    vix = base.align(context["_VIX"], index)
    tlt = base.align(context["TLT"], index)
    shy = base.align(context["SHY"], index)
    close = asset["close"]
    qclose = qqq["close"]
    candidates: list[Candidate] = []

    def add(name: str, family: str, source: str, sig: pd.Series, notes: str) -> None:
        candidates.append(Candidate(name, family, source, sig.reindex(index).ffill().fillna(0.0).clip(0, 1), notes))

    # Baseline and strong momentum families from previous US research.
    add("buy_hold", "baseline", "local", pd.Series(1.0, index=index), "Always hold the asset.")
    for fast, slow, band in ((3, 40, 0.005), (3, 120, 0.0025), (3, 180, 0.0), (5, 60, 0.005), (5, 100, 0.005), (10, 60, 0.005), (20, 200, 0.01)):
        ratio = mom.ema(qclose, fast) / mom.ema(qclose, slow) - 1.0
        add(f"qqq_ema{fast}_{slow}_b{band:.4f}", "qqq_ema_cross", "momentum_combo", mom.state(ratio, band, -band, f"qqq_ema{fast}_{slow}_b{band:.4f}"), f"QQQ EMA{fast}/EMA{slow} with {band:.2%} hysteresis.")
        ratio2 = mom.sma(close, fast) / mom.sma(close, slow) - 1.0
        add(f"asset_sma{fast}_{slow}_b{band:.4f}", "asset_sma_cross", "momentum_combo", mom.state(ratio2, band, -band, f"asset_sma{fast}_{slow}_b{band:.4f}"), f"Asset SMA{fast}/SMA{slow} with {band:.2%} hysteresis.")

    macd = mom.ema(close, 12) - mom.ema(close, 26)
    macd_sig = mom.ema(macd, 9)
    add("macd_ma200_vix30", "macd_trend_vix", "strategy_library", mom.combine_and([macd > macd_sig, close > mom.sma(close, 200), qclose > mom.sma(qclose, 200), vix["close"] < 30], "macd_ma200_vix30"), "MACD bullish, asset/QQQ above MA200, VIX<30.")
    add("roc_stack_vol", "roc_stack_vol_filter", "factor_library_proxy", mom.bool_state((0.4 * close.pct_change(20) + 0.35 * close.pct_change(60) + 0.25 * close.pct_change(120) > 0) & (close > mom.sma(close, 150)) & (close.pct_change().rolling(20).std() * math.sqrt(252) < 0.65), "roc_stack_vol"), "ROC20/60/120 stack plus MA150 and realized-vol filter.")
    rel_safe = pd.concat([shy["close"].pct_change(126), tlt["close"].pct_change(126)], axis=1).max(axis=1)
    add("relative_mom_safe", "relative_momentum", "factor_library_proxy", mom.bool_state((qclose.pct_change(126) > rel_safe) & (qclose > mom.sma(qclose, 150)), "relative_mom_safe"), "QQQ 126d momentum beats SHY/TLT and QQQ above MA150.")

    # Compact ports from the reusable strategy template catalog.
    template_sigs: dict[str, pd.Series] = {}
    for source_name, source_close in (("asset", close), ("qqq", qclose)):
        for window, enter_mult, exit_mult in ((100, 1.00, 0.98), (150, 1.00, 0.98), (200, 1.00, 0.98), (200, 1.01, 0.99)):
            name = f"{source_name}_ma{window}_band_e{enter_mult:.2f}_x{exit_mult:.2f}"
            raw = ma_band_signal(source_close, window, enter_mult, exit_mult, name)
            add(name, "trend_ma_band", "strategy_template_catalog", raw, f"Hold when {source_name} close is above MA{window} entry band {enter_mult:.2f}; exit below {exit_mult:.2f}.")
            if window == 200 and enter_mult == 1.00:
                template_sigs[name] = raw
    for entry, exit_ in ((20, 10), (55, 20), (120, 60)):
        name = f"asset_turtle_e{entry}_x{exit_}"
        raw = turtle_signal(asset, entry, exit_, name)
        add(name, "turtle_breakout", "rqalpha_turtle_template", raw, f"Buy an asset breakout above the prior {entry}-day high; exit below the prior {exit_}-day low.")
        if entry in (55, 120):
            template_sigs[name] = raw
    for window, k in ((20, 0.3), (20, 0.5), (40, 0.5)):
        name = f"asset_dual_thrust_w{window}_k{k:.1f}"
        raw = dual_thrust_signal(asset, window, k, name)
        add(name, "dual_thrust_breakout", "rqalpha_dual_thrust_template", raw, f"Stateful Dual Thrust breakout using {window}-day range and k={k:.1f}.")
        if k == 0.5:
            template_sigs[name] = raw
    for window, enter_rsi, exit_rsi in ((7, 25, 55), (14, 30, 60), (21, 35, 65)):
        name = f"asset_rsi{window}_e{enter_rsi}_x{exit_rsi}"
        raw = rsi_signal(close, window, enter_rsi, exit_rsi, name)
        add(name, "rsi_mean_reversion", "quant_lab_local_factor", raw, f"Buy after RSI{window} <= {enter_rsi}; exit after RSI >= {exit_rsi}.")

    # Multi-factor score uses local factor-library motifs plus TD9.
    score = factor_score(asset, qqq, vix)
    for enter, exit_ in ((9, 6), (10, 7), (11, 9), (12, 10)):
        raw = state_between(score, enter, exit_, f"factor_score_td9_e{enter}_x{exit_}")
        add(raw.name, "factor_score_td9", "factor_library_td9", raw, f"Price/volume/TD9 score enter >= {enter}, exit <= {exit_}.")
        add(raw.name + "_cool3", "factor_score_td9_cooldown", "factor_library_td9", mom.apply_cooldown(raw, 3, raw.name + "_cool3"), f"Same factor score with 3-day cooldown after exit.")

    trend_sigs = {
        "qqq_ema3_120": mom.state(mom.ema(qclose, 3) / mom.ema(qclose, 120) - 1.0, 0.0025, -0.0025, "qqq_ema3_120"),
        "asset_sma3_200": mom.state(mom.sma(close, 3) / mom.sma(close, 200) - 1.0, 0.005, -0.005, "asset_sma3_200"),
        "macd_ma200": mom.combine_and([macd > macd_sig, close > mom.sma(close, 200)], "macd_ma200"),
    }
    for trend_name, trend_sig in trend_sigs.items():
        for buy_count in (6, 8):
            for sell_count in (8, 9):
                name = f"td9_pullback_{trend_name}_b{buy_count}_s{sell_count}"
                add(name, "td9_pullback_trend", "td9_strategy_library", td9_pullback_signal(asset, trend_sig > 0.5, buy_count, sell_count, name), f"Enter on TD9 buy setup >= {buy_count} while {trend_name} is bullish; exit on TD9 sell setup >= {sell_count} or trend break.")
        for sell_count in (8, 9):
            name = f"{trend_name}_td9_exit_s{sell_count}"
            add(name, "td9_exit_overlay", "td9_strategy_library", td9_exit_overlay(trend_sig, asset, sell_count, name), f"Use {trend_name} entries, exit early when TD9 sell setup >= {sell_count}.")
        name = f"{trend_name}_td9_reentry_b6"
        add(name, "td9_reentry_overlay", "td9_strategy_library", td9_reentry_overlay(trend_sig, asset, 6, name), f"Use {trend_name}, prefer re-entry when TD9 buy setup >= 6 or no TD9 down count.")

    for trend_name, trend_sig in template_sigs.items():
        if "rsi" in trend_name:
            continue
        for sell_count in (8, 9):
            name = f"td9_pullback_{trend_name}_b6_s{sell_count}"
            add(name, "td9_pullback_template", "td9_plus_strategy_template", td9_pullback_signal(asset, trend_sig > 0.5, 6, sell_count, name), f"Enter on TD9 buy setup >= 6 while {trend_name} is bullish; exit on TD9 sell setup >= {sell_count} or trend break.")
        name = f"{trend_name}_td9_exit_s8"
        add(name, "td9_exit_template", "td9_plus_strategy_template", td9_exit_overlay(trend_sig, asset, 8, name), f"Use {trend_name} entries, exit early when TD9 sell setup >= 8.")
        name = f"{trend_name}_td9_reentry_b6"
        add(name, "td9_reentry_template", "td9_plus_strategy_template", td9_reentry_overlay(trend_sig, asset, 6, name), f"Use {trend_name}, prefer re-entry when TD9 buy setup >= 6 or no TD9 down count.")

    # Cross-market risk-on filters.
    for vix_limit in (22, 25, 30, 35):
        name = f"qqq_ema3_120_vix{vix_limit}_td9safe"
        base_sig = mom.combine_and([mom.ema(qclose, 3) > mom.ema(qclose, 120), vix["close"] < vix_limit, spy["close"] > mom.sma(spy["close"], 200)], name)
        add(name, "cross_market_td9_safe", "strategy_library", td9_exit_overlay(base_sig, asset, 8, name), f"QQQ EMA3>EMA120, SPY>MA200, VIX<{vix_limit}; TD9 sell>=8 exits.")

    add_market_turning_candidates(add, index, asset, market_turning)

    deduped: dict[str, Candidate] = {}
    for c in candidates:
        deduped[c.name] = c
    return list(deduped.values())


def metric_score(row: Mapping[str, float], group: str) -> float:
    required = ("test_annual_return", "test_sharpe", "test_calmar", "full_annual_return", "full_sharpe", "full_calmar")
    if any(pd.isna(row.get(k, np.nan)) for k in required):
        return -999.0
    val = (
        0.28 * float(np.clip(row["test_calmar"], -4, 4))
        + 0.20 * float(np.clip(row["test_sharpe"], -3, 3))
        + 0.16 * float(np.clip(row["test_annual_return"], -1, 1.5))
        + 0.18 * float(np.clip(row["full_calmar"], -4, 4))
        + 0.10 * float(np.clip(row["full_sharpe"], -3, 3))
        + 0.08 * float(np.clip(row["full_annual_return"], -1, 1.5))
    )
    full_dd = float(row.get("full_max_drawdown", 0.0))
    test_dd = float(row.get("test_max_drawdown", 0.0))
    if group == "mag7":
        soft, hard = -0.42, -0.55
    else:
        soft, hard = -0.35, -0.48
    if test_dd < soft:
        val -= 1.8 * (abs(test_dd) - abs(soft))
    if full_dd < hard:
        val -= 2.5 * (abs(full_dd) - abs(hard))
    if row.get("full_trades", 0) < 3:
        val -= 0.25
    exposure = float(row.get("full_exposure", 0) or 0)
    test_ann = float(row.get("test_annual_return", 0) or 0)
    full_ann = float(row.get("full_annual_return", 0) or 0)
    if exposure < 0.15:
        val -= 1.6 * (0.15 - exposure)
    if exposure < 0.05:
        val -= 0.55
    if test_ann < 0.05:
        val -= 0.6 * (0.05 - test_ann)
    if full_ann < 0.04:
        val -= 0.4 * (0.04 - full_ann)
    return float(val)


def evaluate_symbol(
    symbol: str,
    group: str,
    data: Mapping[str, pd.DataFrame],
    common_context: Mapping[str, pd.DataFrame],
    market_turning: Mapping[str, object] | None,
    train_end: str,
    test_start: str,
    fees: float,
) -> tuple[dict, dict]:
    asset = data[symbol].copy()
    if asset.empty or len(asset) < 300:
        raise ValueError(f"insufficient data for {symbol}")
    context = {k: base.align(v, asset.index) for k, v in common_context.items()}
    candidates = build_candidates(symbol, asset, context, market_turning)
    rows = []
    best_result = None
    best_candidate = None
    for candidate in candidates:
        try:
            result = base.run_vbt(asset, candidate.signal, fees)
            train = base.metrics_from(result, None, train_end)
            test = base.metrics_from(result, test_start, None)
            full = base.metrics_from(result, None, None)
            latest_desired = int(bool(result["desired"].iloc[-1]))
            latest_position = int(bool(result["position"].iloc[-1]))
            if latest_desired > latest_position:
                latest_action = "BUY_NEXT_OPEN"
            elif latest_desired < latest_position:
                latest_action = "SELL_NEXT_OPEN"
            else:
                latest_action = "HOLD_OR_KEEP_LONG" if latest_desired else "STAY_CASH"
            row = {
                "symbol": symbol,
                "group": group,
                "strategy": candidate.name,
                "family": candidate.family,
                "source": candidate.source,
                "notes": candidate.notes,
                "start": asset.index.min().strftime("%Y-%m-%d"),
                "latest_date": asset.index.max().strftime("%Y-%m-%d"),
                "latest_close": float(asset["close"].iloc[-1]),
                "latest_desired_position": latest_desired,
                "current_position_at_latest_open": latest_position,
                "latest_action": latest_action,
            }
            for prefix, metrics in (("train", train), ("test", test), ("full", full)):
                for key, value in metrics.items():
                    row[f"{prefix}_{key}"] = value
            row["score"] = metric_score(row, group)
            rows.append(row)
            if best_candidate is None or row["score"] > best_candidate["score"]:
                best_candidate = row
                best_result = result
        except Exception as exc:
            rows.append({"symbol": symbol, "group": group, "strategy": candidate.name, "family": candidate.family, "source": candidate.source, "notes": candidate.notes, "error": f"{type(exc).__name__}: {exc}", "score": -999.0})
    if best_candidate is None or best_result is None:
        raise ValueError(f"no valid candidate for {symbol}")
    return best_candidate, {"result": best_result, "candidate_rows": rows, "asset": asset}


def save_symbol_details(run_dir: Path, symbol: str, best: dict, detail: dict, next_open_date: str) -> dict:
    asset = detail["asset"]
    result = detail["result"]
    ops, trades = base.operations(symbol, asset, result, best["strategy"])
    ops.to_csv(run_dir / f"{symbol}_operation_points.csv", index=False, encoding="utf-8-sig")
    trades.to_csv(run_dir / f"{symbol}_trades.csv", index=False, encoding="utf-8-sig")
    sig = pd.DataFrame(
        {
            "open": asset["open"],
            "close": asset["close"],
            "desired_after_close": result["desired"].astype(int),
            "position_at_open": result["position"].astype(int),
            "entry_at_open": result["entries"].astype(int),
            "exit_at_open": result["exits"].astype(int),
            "portfolio_value": result["value"],
            "portfolio_return": result["returns"],
        }
    )
    sig.to_csv(run_dir / f"{symbol}_signal_nav.csv", encoding="utf-8-sig")
    action = base.next_action(symbol, asset, result, next_open_date)
    return {"operations": ops, "trades": trades, "signal_nav": sig, "next_action": action}


def fmt_pct(value: object) -> str:
    if value is None or pd.isna(value):
        return "nan"
    return f"{float(value) * 100:.2f}%"


def detail_lines(frame: pd.DataFrame, title: str) -> list[str]:
    lines = ["", f"## {title}", ""]
    if frame.empty:
        lines.append("- No rows.")
        return lines
    for _, row in frame.iterrows():
        action = row.get("latest_action", "")
        lines += [
            f"### {row['symbol']} - {row['strategy']}",
            "",
            f"- Family/source: `{row.get('family', '')}` / `{row.get('source', '')}`",
            f"- Rule: {row.get('notes', '')}",
            f"- Latest signal date: {row.get('latest_date', '')}; latest close: {row.get('latest_close', '')}; next-open action: `{action}`",
            (
                f"- Test: annual {fmt_pct(row.get('test_annual_return'))}, "
                f"maxDD {fmt_pct(row.get('test_max_drawdown'))}, "
                f"Sharpe {row.get('test_sharpe', np.nan):.3f}, "
                f"Calmar {row.get('test_calmar', np.nan):.3f}"
            ),
            (
                f"- Full: annual {fmt_pct(row.get('full_annual_return'))}, "
                f"maxDD {fmt_pct(row.get('full_max_drawdown'))}, "
                f"Sharpe {row.get('full_sharpe', np.nan):.3f}, "
                f"Calmar {row.get('full_calmar', np.nan):.3f}, "
                f"exposure {fmt_pct(row.get('full_exposure'))}, trades {row.get('full_trades', '')}"
            ),
            (
                f"- Buy-and-hold full comparison: annual {fmt_pct(row.get('buy_hold_full_annual_return'))}, "
                f"maxDD {fmt_pct(row.get('buy_hold_full_max_drawdown'))}, "
                f"annual excess {fmt_pct(row.get('full_annual_excess_vs_buy_hold'))}"
            ),
            "",
        ]
    return lines


def write_report(run_dir: Path, best_df: pd.DataFrame, top5: pd.DataFrame, qld_tqqq: pd.DataFrame, universe: pd.DataFrame, status: pd.DataFrame) -> None:
    lines = [
        "# US TD9 + Factor/Strategy Combination VectorBT Report",
        "",
        f"- Run directory: `{run_dir}`",
        "- Execution convention: signal after close, trade at next open.",
        "- Candidate families: EMA/SMA cross, MA band, MACD trend, Turtle, Dual Thrust, RSI, ROC stack, relative momentum, multi-factor score, TD9 pullback, TD9 exit overlay, TD9 re-entry overlay, VIX/SPY risk filters.",
        "",
        "## Sources And Reuse Surface",
        "",
    ]
    for source in SOURCES:
        lines.append(f"- [{source['name']}]({source['url']}): {source['use']}")
    lines += [
        "",
        "## Universe",
        "",
        f"- Symbols evaluated: {len(best_df)}",
        f"- Universe rows before data filtering: {len(universe)}",
        f"- MAG7 symbols evaluated: {', '.join([s for s in MAG7 if s in set(best_df['symbol'])])}",
        f"- Fund/ETF/index symbols evaluated: {int((best_df['group'] != 'mag7').sum())}",
        f"- Asset types: `{json.dumps(base.jready(universe['asset_type'].value_counts().to_dict() if 'asset_type' in universe else {}), ensure_ascii=False)}`",
        "",
        "## Top 5 Overall",
        "",
        base.md_table(top5),
        "",
        *detail_lines(top5, "Top 5 Strategy Details"),
        "## QLD And TQQQ",
        "",
        base.md_table(qld_tqqq),
        "",
        *detail_lines(qld_tqqq, "QLD And TQQQ Strategy Details"),
        "## Data Status Sample",
        "",
        base.md_table(status.head(30)),
        "",
        "## All Best Results",
        "",
        base.md_table(best_df.sort_values("score", ascending=False).head(50)),
    ]
    (run_dir / "report.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--today", default=pd.Timestamp.today().strftime("%Y-%m-%d"))
    parser.add_argument("--train-end", default="2020-12-31")
    parser.add_argument("--test-start", default="2021-01-01")
    parser.add_argument("--next-open-date", default=(pd.Timestamp.today() + pd.Timedelta(days=1)).strftime("%Y-%m-%d"))
    parser.add_argument("--fees", type=float, default=0.001)
    parser.add_argument("--max-symbols", type=int, default=0)
    parser.add_argument("--chunk-size", type=int, default=45)
    parser.add_argument("--refresh-metadata", action="store_true")
    args = parser.parse_args()

    run_dir = OUT_ROOT / f"td9_all_assets_{stamp()}"
    run_dir.mkdir(parents=True, exist_ok=True)
    checkpoint(run_dir, "00_start", "TD9 All Assets Start Checkpoint", {"sources": SOURCES, "vectorbt_version": vbt.__version__}, "Build universe and update price data.")
    universe = build_universe(args.max_symbols, args.refresh_metadata)
    universe.to_csv(run_dir / "universe.csv", index=False, encoding="utf-8-sig")
    checkpoint(
        run_dir,
        "01_universe",
        "Universe Checkpoint",
        {
            "symbol_count": len(universe),
            "groups": universe["group"].value_counts().to_dict(),
            "asset_types": universe["asset_type"].value_counts().to_dict() if "asset_type" in universe else {},
            "symbols": universe["symbol"].tolist(),
        },
        "Update yfinance data for the selected available universe.",
    )
    data, status = update_data(run_dir, universe, args.today, args.chunk_size)
    checkpoint(run_dir, "02_data", "Data Update Checkpoint", {"latest": status[["symbol", "group", "asset_type", "status", "merged_last", "rows"]].to_dict("records")}, "Evaluate TD9 + factor strategy grid with vectorbt.")

    context = {k: data[k] for k in CORE_CONTEXT if k in data and not data[k].empty}
    market_turning = build_market_turning_bundle(data, run_dir)
    checkpoint(
        run_dir,
        "02b_turning_models",
        "Market Turning Feature/Model Checkpoint",
        {
            "feature_count": len(market_turning["features"].columns) if "features" in market_turning else "",
            "events": len(market_turning.get("events", [])),
            "fold_rows": len(market_turning.get("folds", [])),
            "source_meta": market_turning.get("meta", {}),
        },
        "Evaluate TD9 + factor + market-turning strategy grid with vectorbt.",
    )
    candidate_rows = []
    best_rows = []
    for i, row in universe.iterrows():
        symbol = row["symbol"]
        group = row["group"]
        if symbol not in data or data[symbol].empty:
            continue
        try:
            best, detail = evaluate_symbol(symbol, group, data, context, market_turning, args.train_end, args.test_start, args.fees)
            best_rows.append(best)
            candidate_rows.extend(detail["candidate_rows"])
        except Exception as exc:
            best_rows.append({"symbol": symbol, "group": group, "strategy": "", "family": "", "notes": "", "error": f"{type(exc).__name__}: {exc}", "score": -999.0})
        if (i + 1) % 10 == 0:
            pd.DataFrame(best_rows).to_csv(run_dir / "best_summary_checkpoint.csv", index=False, encoding="utf-8-sig")
            pd.DataFrame(candidate_rows).to_csv(run_dir / "candidate_summary_checkpoint.csv", index=False, encoding="utf-8-sig")

    best_df = pd.DataFrame(best_rows).sort_values("score", ascending=False)
    cand_df = pd.DataFrame(candidate_rows)
    if not cand_df.empty and "strategy" in cand_df:
        hold_cols = [
            "symbol",
            "full_annual_return",
            "full_max_drawdown",
            "full_sharpe",
            "test_annual_return",
            "test_max_drawdown",
        ]
        hold_df = cand_df[cand_df["strategy"] == "buy_hold"][hold_cols].drop_duplicates("symbol")
        hold_df = hold_df.rename(columns={col: f"buy_hold_{col}" for col in hold_cols if col != "symbol"})
        best_df = best_df.merge(hold_df, on="symbol", how="left")
        best_df["full_annual_excess_vs_buy_hold"] = best_df["full_annual_return"] - best_df["buy_hold_full_annual_return"]
        best_df["test_annual_excess_vs_buy_hold"] = best_df["test_annual_return"] - best_df["buy_hold_test_annual_return"]
    best_df.to_csv(run_dir / "instrument_best_summary.csv", index=False, encoding="utf-8-sig")
    cand_df.to_csv(run_dir / "candidate_summary.csv", index=False, encoding="utf-8-sig")

    detail_summaries = {}
    symbols_to_save = list(dict.fromkeys(best_df.head(5)["symbol"].tolist() + ["QLD", "TQQQ"]))
    for symbol in symbols_to_save:
        if symbol not in data or data[symbol].empty:
            continue
        best_row = best_df[best_df["symbol"] == symbol]
        if best_row.empty or best_row.iloc[0]["score"] <= -900:
            continue
        best, detail = evaluate_symbol(symbol, best_row.iloc[0]["group"], data, context, market_turning, args.train_end, args.test_start, args.fees)
        detail_summaries[symbol] = save_symbol_details(run_dir, symbol, best, detail, args.next_open_date)

    top_cols = [
        "symbol",
        "group",
        "strategy",
        "family",
        "score",
        "test_annual_return",
        "test_max_drawdown",
        "test_sharpe",
        "test_calmar",
        "full_annual_return",
        "full_max_drawdown",
        "full_sharpe",
        "full_calmar",
        "full_exposure",
        "full_trades",
        "buy_hold_full_annual_return",
        "buy_hold_full_max_drawdown",
        "full_annual_excess_vs_buy_hold",
        "latest_date",
        "latest_close",
        "latest_action",
        "notes",
    ]
    top_cols = [col for col in top_cols if col in best_df.columns]
    top5 = best_df[top_cols].head(5).copy()
    top5.to_csv(run_dir / "top5_overall.csv", index=False, encoding="utf-8-sig")
    qld_tqqq = best_df[best_df["symbol"].isin(["QLD", "TQQQ"])][top_cols].copy()
    qld_tqqq.to_csv(run_dir / "qld_tqqq_best.csv", index=False, encoding="utf-8-sig")
    write_report(run_dir, best_df[top_cols].copy(), top5, qld_tqqq, universe, status)
    write_json(run_dir / "best_config.json", {"run_dir": str(run_dir), "top5": top5.to_dict("records"), "qld_tqqq": qld_tqqq.to_dict("records"), "sources": SOURCES})
    checkpoint(run_dir, "03_final", "Final Checkpoint", {"report": str(run_dir / "report.md"), "top5": top5.to_dict("records"), "qld_tqqq": qld_tqqq.to_dict("records")}, "Review report and per-symbol trade CSVs.")
    print(run_dir)


if __name__ == "__main__":
    main()
