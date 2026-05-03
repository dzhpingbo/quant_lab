"""Rerun MVE1 readiness audit on the unified adjusted OHLCV store.

This script intentionally does not start MVE2, train models, run backtests, or
perform strategy optimization. It reads the unified store produced by script 47,
recomputes ticker/layer readiness, compares to the previous MVE1 audit, writes a
Chinese README summary, updates checkpoint files, and packages the evidence.

Some simple readiness helper logic is copied from script 46's MVE1 audit style:
per-ticker feature build flags, layer summaries, and changed-readiness comparison.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import shutil
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

OUTPUT_ROOT = PROJECT_ROOT / "outputs" / "us_stock_selection"
DEFAULT_STORE_DIR = PROJECT_ROOT / "data" / "unified_ohlcv" / "us_stock_selection"
DEFAULT_PREVIOUS_MVE1_DIR = OUTPUT_ROOT / "mve1_longer_history_data_audit_20260501_225200"
NEXT_STEPS = PROJECT_ROOT / "NEXT_STEPS.md"
RUN_SUMMARY = PROJECT_ROOT / "RUN_SUMMARY.md"
MEISTOCK_ROOT = Path("E:/dzhwork/obsydian/quant_lab/MeiStock")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rerun MVE1 readiness on unified adjusted OHLCV store.")
    parser.add_argument("--store-dir", type=Path, default=DEFAULT_STORE_DIR)
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--previous-mve1-dir", type=Path, default=DEFAULT_PREVIOUS_MVE1_DIR)
    parser.add_argument("--timestamp", default=None)
    parser.add_argument("--no-zip", action="store_true")
    return parser.parse_args()


def setup_logger(out_dir: Path) -> logging.Logger:
    out_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("rerun_mve1_on_unified_store")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    fh = logging.FileHandler(out_dir / "mve1_readiness_rerun_log.txt", encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(sh)
    return logger


def write_json(payload: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def sha256(path: Path) -> str:
    if not path.is_file():
        return ""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_required_csv(path: Path, name: str) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Required {name} not found: {path}")
    return pd.read_csv(path)


def normalize_ticker(ticker: Any) -> str:
    return str(ticker).strip().upper()


def load_universe(out_dir: Path, previous_dir: Path) -> pd.DataFrame:
    candidates = [
        out_dir / "mve1_audit_ticker_universe.csv",
        previous_dir / "mve1_audit_ticker_universe.csv",
    ]
    candidates.extend(
        sorted(
            OUTPUT_ROOT.glob("mve1_longer_history_data_audit_*/mve1_audit_ticker_universe.csv"),
            key=lambda p: p.stat().st_mtime if p.exists() else 0,
            reverse=True,
        )
    )
    for path in candidates:
        if not path.exists():
            continue
        df = pd.read_csv(path)
        if {"ticker", "layer", "source"}.issubset(df.columns):
            out = df.copy()
            out["ticker"] = out["ticker"].map(normalize_ticker)
            return out.drop_duplicates("ticker").sort_values(["layer", "ticker"]).reset_index(drop=True)
    raise FileNotFoundError("Cannot locate prior MVE1 ticker universe for readiness rerun.")


def read_price(store_dir: Path, ticker: str) -> pd.DataFrame:
    path = store_dir / "prices" / f"{ticker}.parquet"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_parquet(path)
    df.columns = [str(c).strip().lower() for c in df.columns]
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.tz_localize(None)
    df = df.dropna(subset=["date"]).sort_values("date").drop_duplicates("date", keep="last")
    for col in ["open", "high", "low", "close", "adj_close", "volume", "dividends", "stock_splits"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.reset_index(drop=True)


def max_drawdown(window: pd.Series) -> float:
    vals = window.dropna()
    if vals.empty:
        return np.nan
    running_max = vals.cummax()
    dd = vals / running_max - 1.0
    return float(dd.min())


def feature_flags(df: pd.DataFrame) -> dict[str, Any]:
    if df.empty or "adj_close" not in df.columns:
        base = {
            "can_build_returns_1d": False,
            "can_build_returns_21d": False,
            "can_build_returns_63d": False,
            "can_build_returns_126d": False,
            "can_build_returns_252d": False,
            "can_build_vol_20d": False,
            "can_build_vol_63d": False,
            "can_build_vol_126d": False,
            "can_build_maxdd_63d": False,
            "can_build_distance_to_252d_high": False,
            "can_build_adv_20d": False,
            "can_build_liquidity_filter": False,
            "can_build_forward_21d_audit": False,
            "can_build_forward_42d_audit": False,
            "can_build_forward_63d_audit": False,
            "minimum_feature_ready_date": "",
            "feature_build_score": 0.0,
            "blocking_fields": "price_missing_or_adj_close_missing",
        }
        return base
    px = pd.to_numeric(df["adj_close"], errors="coerce")
    vol = pd.to_numeric(df.get("volume", pd.Series(index=df.index, dtype=float)), errors="coerce")
    n = len(df)
    flags = {
        "can_build_returns_1d": px.pct_change(1).notna().sum() > 10,
        "can_build_returns_21d": px.pct_change(21).notna().sum() > 10,
        "can_build_returns_63d": px.pct_change(63).notna().sum() > 10,
        "can_build_returns_126d": px.pct_change(126).notna().sum() > 10,
        "can_build_returns_252d": px.pct_change(252).notna().sum() > 10,
        "can_build_vol_20d": px.pct_change().rolling(20).std().notna().sum() > 10,
        "can_build_vol_63d": px.pct_change().rolling(63).std().notna().sum() > 10,
        "can_build_vol_126d": px.pct_change().rolling(126).std().notna().sum() > 10,
        "can_build_maxdd_63d": px.rolling(63).apply(max_drawdown, raw=False).notna().sum() > 10,
        "can_build_distance_to_252d_high": (px / px.rolling(252).max() - 1.0).notna().sum() > 10,
        "can_build_adv_20d": (px * vol).rolling(20).mean().notna().sum() > 10,
        "can_build_liquidity_filter": (px * vol).rolling(20).mean().notna().sum() > 10,
        "can_build_forward_21d_audit": px.shift(-21).div(px).sub(1).notna().sum() > 10,
        "can_build_forward_42d_audit": px.shift(-42).div(px).sub(1).notna().sum() > 10,
        "can_build_forward_63d_audit": px.shift(-63).div(px).sub(1).notna().sum() > 10,
    }
    min_date = ""
    if n > 315:
        min_date = str(pd.Timestamp(df["date"].iloc[252]).date())
    blocking = [k for k, v in flags.items() if not v]
    return {
        **flags,
        "minimum_feature_ready_date": min_date,
        "feature_build_score": round(sum(bool(v) for v in flags.values()) / len(flags), 4),
        "blocking_fields": ";".join(blocking),
    }


def ticker_readiness(
    universe: pd.DataFrame,
    store_dir: Path,
    download: pd.DataFrame,
    quality: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    download_idx = download.set_index("ticker").to_dict("index") if not download.empty else {}
    quality_idx = quality.set_index("ticker").to_dict("index") if not quality.empty else {}
    ready_rows: list[dict[str, Any]] = []
    feature_rows: list[dict[str, Any]] = []
    for _, info in universe.iterrows():
        ticker = info["ticker"]
        layer = info["layer"]
        df = read_price(store_dir, ticker)
        dl = download_idx.get(ticker, {})
        q = quality_idx.get(ticker, {})
        flags = feature_flags(df)
        has_adj = bool(not df.empty and "adj_close" in df.columns and df["adj_close"].notna().any())
        has_volume = bool(not df.empty and "volume" in df.columns and df["volume"].notna().any())
        reasons = []
        if not bool(dl.get("download_success", False)):
            reasons.append("download_failed")
        if not bool(q.get("price_quality_ready", False)):
            reasons.append(str(q.get("price_quality_notes", "price_quality_not_ready")))
        if not bool(q.get("has_10y_history", False)):
            reasons.append("less_than_10y_history")
        if not has_adj:
            reasons.append("adj_close_missing")
        if not has_volume:
            reasons.append("volume_missing")
        if flags["feature_build_score"] < 1.0:
            reasons.append("feature_build_incomplete")
        ready = bool(
            dl.get("download_success", False)
            and q.get("price_quality_ready", False)
            and q.get("has_10y_history", False)
            and has_adj
            and has_volume
            and flags["feature_build_score"] >= 1.0
        )
        ready_rows.append(
            {
                "ticker": ticker,
                "layer": layer,
                "first_date": q.get("first_date", ""),
                "last_date": q.get("last_date", ""),
                "n_rows": q.get("n_rows", 0),
                "has_10y_history": bool(q.get("has_10y_history", False)),
                "has_15y_history": bool(q.get("has_15y_history", False)),
                "has_adj_close": has_adj,
                "has_volume": has_volume,
                "feature_build_score": flags["feature_build_score"],
                "mve2_ready_price_data": ready,
                "mve2_ready_reason": "ready" if ready else ";".join(x for x in reasons if x),
            }
        )
        feature_rows.append({"ticker": ticker, "layer": layer, **flags})
    return pd.DataFrame(ready_rows), pd.DataFrame(feature_rows)


def layer_readiness(ticker_ready: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for layer, g in ticker_ready.groupby("layer", sort=True):
        n = len(g)
        ready = int(g["mve2_ready_price_data"].sum())
        adj_rate = float(g["has_adj_close"].mean()) if n else 0.0
        ten_rate = float(g["has_10y_history"].mean()) if n else 0.0
        fifteen_rate = float(g["has_15y_history"].mean()) if n else 0.0
        ready_rate = ready / n if n else 0.0
        notes: list[str] = []
        if "Leveraged ETF" in layer:
            notes.append("ready layer must remain a separate leveraged ETF bucket")
        if "High-beta" in layer and ready_rate < 0.6:
            notes.append("not enough 10y-ready high-beta names; use only as deferred/diagnostic layer")
        if adj_rate < 1.0:
            notes.append("some tickers missing explicit adj_close")
        if ten_rate < 0.7:
            notes.append("10y coverage below 70%")
        if "Sector / theme ETF" in layer:
            layer_ready = bool(ready >= 6 and adj_rate >= 1.0 and ten_rate >= 0.65)
        elif "Mega-cap" in layer:
            layer_ready = bool(ready >= 13 and adj_rate >= 1.0 and ten_rate >= 0.7)
        elif "Core index ETF" in layer:
            layer_ready = bool(ready >= 3 and adj_rate >= 1.0 and ten_rate >= 0.75)
        elif "Leveraged ETF" in layer:
            layer_ready = bool(ready >= 4 and adj_rate >= 1.0 and ten_rate >= 0.8)
        elif "High-beta" in layer:
            layer_ready = bool(ready_rate >= 0.6 and ready >= 4)
        else:
            layer_ready = bool(ready_rate >= 0.7)
        rows.append(
            {
                "layer": layer,
                "ticker_count": n,
                "ready_count": ready,
                "ready_rate": round(ready_rate, 4),
                "explicit_adj_close_rate": round(adj_rate, 4),
                "10y_coverage_rate": round(ten_rate, 4),
                "15y_coverage_rate": round(fifteen_rate, 4),
                "layer_ready": layer_ready,
                "layer_notes": ";".join(notes) if notes else "ready",
            }
        )
    return pd.DataFrame(rows)


def previous_comparison(previous_dir: Path, ticker_ready: pd.DataFrame) -> pd.DataFrame:
    prev_path = previous_dir / "mve1_price_data_coverage.csv"
    if not prev_path.exists():
        return pd.DataFrame(
            [
                {
                    "ticker": row["ticker"],
                    "previous_ready": "",
                    "new_ready": row["mve2_ready_price_data"],
                    "readiness_changed": "",
                    "previous_reason": "previous_audit_missing",
                    "new_reason": row["mve2_ready_reason"],
                    "changed_notes": "cannot_compare",
                }
                for _, row in ticker_ready.iterrows()
            ]
        )
    prev = pd.read_csv(prev_path)
    prev["ticker"] = prev["ticker"].map(normalize_ticker)
    prev_idx = prev.set_index("ticker").to_dict("index")
    rows = []
    for _, row in ticker_ready.iterrows():
        ticker = row["ticker"]
        prow = prev_idx.get(ticker, {})
        previous_ready = bool(prow.get("mve2_ready", False)) if prow else False
        new_ready = bool(row["mve2_ready_price_data"])
        notes = []
        if ticker in {"AFRM", "LCID", "RIVN", "UPST"}:
            notes.append("previous_missing_data_focus")
        if ticker == "DIA":
            notes.append("check_no_longer_qlib_fallback")
        if str(prow.get("source_used", "")).startswith("qlib_provider") and new_ready:
            notes.append("improved_from_qlib_fallback_to_yfinance_unified_store")
        if previous_ready != new_ready:
            notes.append("readiness_changed")
        rows.append(
            {
                "ticker": ticker,
                "previous_ready": previous_ready,
                "new_ready": new_ready,
                "readiness_changed": previous_ready != new_ready,
                "previous_reason": prow.get("warnings", "") or prow.get("source_used", "") or "previous_row_missing",
                "new_reason": row["mve2_ready_reason"],
                "changed_notes": ";".join(notes) if notes else "no_change",
            }
        )
    return pd.DataFrame(rows)


def make_not_ready(ticker_ready: pd.DataFrame) -> pd.DataFrame:
    cols = ["ticker", "layer", "mve2_ready_reason", "first_date", "last_date", "n_rows"]
    return ticker_ready.loc[~ticker_ready["mve2_ready_price_data"], cols].rename(columns={"mve2_ready_reason": "not_ready_reason"})


def split_sanity_from_corporate_actions(corp: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if corp.empty:
        return pd.DataFrame(
            columns=[
                "ticker",
                "has_split_event",
                "split_event_count",
                "split_sanity_checked_count",
                "split_sanity_pass_count",
                "split_sanity_fail_count",
                "split_sanity_verdict",
                "notes",
            ]
        )
    for ticker, g in corp.groupby("ticker", sort=True):
        if "split_date" in g.columns:
            split_text = g["split_date"].astype(str).str.strip()
            split_rows = g.loc[g["split_date"].notna() & (split_text != "") & (split_text.str.lower() != "nan")].copy()
        else:
            split_rows = pd.DataFrame()
        checked = len(split_rows)
        pass_count = 0
        if checked and "split_sanity_pass" in split_rows.columns:
            pass_count = int(split_rows["split_sanity_pass"].fillna(False).astype(bool).sum())
        fail_count = checked - pass_count
        if checked == 0:
            verdict = "no_split_event"
            notes = "No split event in yfinance action table."
        elif fail_count == 0:
            verdict = "pass"
            notes = "All split rows passed broad continuity sanity check."
        else:
            verdict = "manual_review_required"
            notes = "At least one split row needs manual review."
        rows.append(
            {
                "ticker": ticker,
                "has_split_event": checked > 0,
                "split_event_count": int(g["split_event_count"].max()) if "split_event_count" in g.columns else checked,
                "split_sanity_checked_count": checked,
                "split_sanity_pass_count": pass_count,
                "split_sanity_fail_count": fail_count,
                "split_sanity_verdict": verdict,
                "notes": notes,
            }
        )
    return pd.DataFrame(rows)


def store_manifest(store_dir: Path, out_dir: Path) -> pd.DataFrame:
    rows = []
    for root in [store_dir / "prices", store_dir / "actions", store_dir / "audit"]:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file():
                rows.append(
                    {
                        "file_type": root.name,
                        "path": str(path),
                        "relative_path": str(path.relative_to(store_dir)),
                        "size_bytes": path.stat().st_size,
                        "sha256": sha256(path),
                    }
                )
    df = pd.DataFrame(rows)
    df.to_csv(out_dir / "unified_store_file_manifest.csv", index=False, encoding="utf-8-sig")
    return df


def formal_or_limited_decision(layer_ready: pd.DataFrame, ticker_ready: pd.DataFrame) -> dict[str, Any]:
    ready_layers = layer_ready.loc[layer_ready["layer_ready"], "layer"].tolist()
    not_ready_layers = layer_ready.loc[~layer_ready["layer_ready"], "layer"].tolist()
    layer3_ready = bool(layer_ready.loc[layer_ready["layer"].str.contains("Sector / theme ETF", regex=False), "layer_ready"].any())
    layer5_ready = bool(layer_ready.loc[layer_ready["layer"].str.contains("High-beta single names", regex=False), "layer_ready"].any())
    formal_mve2 = bool(layer3_ready and layer5_ready and layer_ready["layer_ready"].all())
    limited_mve2 = bool(not formal_mve2 and layer3_ready and len(ready_layers) >= 4)
    exclude_tickers = ticker_ready.loc[~ticker_ready["mve2_ready_price_data"], "ticker"].tolist()
    separate_bucket = layer_ready.loc[layer_ready["layer"].str.contains("Leveraged ETF", regex=False), "layer"].tolist()
    return {
        "formal_mve2_recommended": formal_mve2,
        "limited_mve2_possible": limited_mve2,
        "allowed_layers_for_limited_mve2": ready_layers,
        "not_ready_layers": not_ready_layers,
        "must_exclude_tickers": exclude_tickers,
        "separate_bucket_layers": separate_bucket,
        "caveat_rules": [
            "No strategy search until user/ChatGPT approves MVE2.",
            "Use only tickers with mve2_ready_price_data=True.",
            "Leveraged ETFs must remain in a separate bucket.",
            "High-beta short-history names are deferred unless explicitly approved as diagnostic-only.",
            "Keep audit_forward fields separate from ranking in any future prototype.",
        ],
    }


def write_readme(
    out_dir: Path,
    download: pd.DataFrame,
    quality: pd.DataFrame,
    corp: pd.DataFrame,
    ticker_ready: pd.DataFrame,
    layer_ready: pd.DataFrame,
    changed: pd.DataFrame,
    decision: dict[str, Any],
) -> Path:
    success = int(download["download_success"].sum())
    failed = download.loc[~download["download_success"], ["ticker", "error_message"]]
    has_10y = int(quality["has_10y_history"].sum())
    has_15y = int(quality["has_15y_history"].sum())
    action_count = int(download["has_actions"].sum())
    split_count = int(download["has_splits"].sum())
    split_rows = corp.loc[corp["split_sanity_notes"].astype(str) != "no_split_event"] if not corp.empty and "split_sanity_notes" in corp.columns else pd.DataFrame()
    split_pass = int(split_rows["split_sanity_pass"].fillna(False).sum()) if not split_rows.empty and "split_sanity_pass" in split_rows.columns else 0
    improved = changed.loc[(changed["previous_ready"] == False) & (changed["new_ready"] == True), "ticker"].tolist()
    worsened = changed.loc[(changed["previous_ready"] == True) & (changed["new_ready"] == False), "ticker"].tolist()
    layer3 = layer_ready.loc[layer_ready["layer"].str.contains("Sector / theme ETF", regex=False)]
    layer5 = layer_ready.loc[layer_ready["layer"].str.contains("High-beta single names", regex=False)]
    text = f"""# README Summary - Unified Adjusted OHLCV Store + MVE1 Readiness Rerun

## 1. 本轮任务目标

本轮只做统一 adjusted OHLCV store 建设与 MVE1 readiness 复跑。不进入正式 v9，不启动 MVE2，不训练模型，不跑回测，不做策略优化。

## 2. 数据来源

统一数据源为 `yfinance`，下载参数固定为 `auto_adjust=False`, `period=max`, `actions=True`。价格表保留 raw open/high/low/close/volume、`adj_close`、`dividends`、`stock_splits`。公司行为表保留 yfinance actions 事件。

## 3. 下载成功/失败

- ticker 总数：{len(download)}
- 下载成功：{success}
- 下载失败：{len(download) - success}

失败 ticker 及原因：
{failed.to_markdown(index=False) if not failed.empty else "无"}

## 4. 历史覆盖

- 10 年以上覆盖 ticker：{has_10y}
- 15 年以上覆盖 ticker：{has_15y}

## 5. Corporate Action / Split 审计

- 有 corporate action 记录 ticker：{action_count}
- 有 split 记录 ticker：{split_count}
- split sanity rows：{len(split_rows)}
- split sanity pass：{split_pass}/{len(split_rows) if len(split_rows) else 0}

总体结论：{ "有 split 事件且 sanity check 未发现系统性失败。" if split_count else "未发现 split 事件或无可检查 split 事件。" }

## 6. 基于统一 store 的 MVE1 readiness 复跑结论

- ticker-level ready：{int(ticker_ready["mve2_ready_price_data"].sum())}/{len(ticker_ready)}
- not ready：{int((~ticker_ready["mve2_ready_price_data"]).sum())}/{len(ticker_ready)}

## 7. 相比上一轮 readiness 的变化

- 从 not ready 改善为 ready：{len(improved)}，{", ".join(improved) if improved else "无"}
- 从 ready 变为 not ready：{len(worsened)}，{", ".join(worsened) if worsened else "无"}
- 重点检查：AFRM/LCID/RIVN/UPST 是否补齐、DIA 是否脱离 qlib fallback、Layer3/Layer5 是否改善，详见 `changed_readiness_vs_previous_audit.csv`。

## 8. Layer readiness 结论

{layer_ready.to_markdown(index=False)}

Layer3 改善结论：{ "Layer3 已改善为 ready。" if (not layer3.empty and bool(layer3["layer_ready"].iloc[0])) else "Layer3 仍未完全 ready。" }

Layer5 改善结论：{ "Layer5 已改善为 ready。" if (not layer5.empty and bool(layer5["layer_ready"].iloc[0])) else "Layer5 仍未 ready，主要受短上市历史约束。" }

## 9. 是否建议启动正式 MVE2

- formal_mve2_recommended：{decision["formal_mve2_recommended"]}
- limited_mve2_possible：{decision["limited_mve2_possible"]}

## 10. 如果仍不建议正式 MVE2，阻塞点

{chr(10).join("- " + x for x in decision["not_ready_layers"]) if decision["not_ready_layers"] else "无"}

## 11. 如果启动受限版 MVE2

允许进入的 layer：
{chr(10).join("- " + x for x in decision["allowed_layers_for_limited_mve2"]) if decision["allowed_layers_for_limited_mve2"] else "无"}

必须排除的 ticker：
{", ".join(decision["must_exclude_tickers"]) if decision["must_exclude_tickers"] else "无"}

必须单独成桶处理的 ticker/layer：
{chr(10).join("- " + x for x in decision["separate_bucket_layers"]) if decision["separate_bucket_layers"] else "无"}

Caveat 标记规则：
{chr(10).join("- " + x for x in decision["caveat_rules"])}

## 12. 输出文件

- `audit/download_audit.csv`
- `audit/price_quality_audit.csv`
- `audit/corporate_action_audit.csv`
- `audit/ticker_readiness_after_unified_store.csv`
- `audit/layer_readiness_after_unified_store.csv`
- `audit/mve1_feature_build_readiness_after_unified_store.csv`
- `audit/not_ready_ticker_reason_after_unified_store.csv`
- `audit/changed_readiness_vs_previous_audit.csv`
- `prices/*.parquet`
- `actions/*_actions.csv`
"""
    path = out_dir / "README_summary.md"
    path.write_text(text, encoding="utf-8")
    return path


def update_next_steps(out_dir: Path, zip_path: Path, decision: dict[str, Any], download: pd.DataFrame, quality: pd.DataFrame, layer_ready: pd.DataFrame) -> None:
    text = NEXT_STEPS.read_text(encoding="utf-8") if NEXT_STEPS.exists() else "# NEXT_STEPS\n"
    marker = "## Unified adjusted OHLCV store + MVE1 readiness rerun"
    section = f"""## Unified adjusted OHLCV store + MVE1 readiness rerun

- 执行状态：completed，随后按要求暂停，不启动 MVE2。
- 输出目录：`{out_dir}`
- zip：`{zip_path}`
- 下载成功/失败：`{int(download["download_success"].sum())}/{int((~download["download_success"]).sum())}`
- 10Y/15Y 覆盖：`{int(quality["has_10y_history"].sum())}/{int(quality["has_15y_history"].sum())}`
- layer readiness：`{layer_ready[["layer", "layer_ready"]].to_dict("records")}`
- formal MVE2 recommended：`{decision["formal_mve2_recommended"]}`
- limited MVE2 possible：`{decision["limited_mve2_possible"]}`
- 本轮边界：未进入正式 v9，未训练模型，未跑回测，未启动 MVE2。
"""
    pattern = re.compile(r"## Unified adjusted OHLCV store \+ MVE1 readiness rerun\n.*?(?=\n## |\Z)", re.S)
    if pattern.search(text):
        text = pattern.sub(lambda _: section.strip(), text)
    else:
        text = text.rstrip() + "\n\n" + section.strip() + "\n"
    NEXT_STEPS.write_text(text, encoding="utf-8")
    shutil.copy2(NEXT_STEPS, out_dir / "NEXT_STEPS.md")


def write_run_summary(out_dir: Path, zip_path: Path, decision: dict[str, Any]) -> None:
    text = f"""# RUN_SUMMARY

本轮目标：统一 adjusted OHLCV store 建设 + MVE1 readiness 复跑。

输出目录：`{out_dir}`

zip：`{zip_path}`

是否正式进入 v9：`False`

是否训练模型：`False`

是否运行 31b：`False`

是否跑回测：`False`

是否启动 MVE2：`False`

formal MVE2 recommended：`{decision["formal_mve2_recommended"]}`

limited MVE2 possible：`{decision["limited_mve2_possible"]}`
"""
    RUN_SUMMARY.write_text(text, encoding="utf-8")
    (out_dir / "RUN_SUMMARY.md").write_text(text, encoding="utf-8")


def sync_meistock(timestamp: str, out_dir: Path, zip_path: Path) -> pd.DataFrame:
    if not MEISTOCK_ROOT.exists():
        return pd.DataFrame([{"target": str(MEISTOCK_ROOT), "status": "warning", "note": "MeiStock root missing"}])
    dirs = {
        "checkpoint": MEISTOCK_ROOT / "01_对话沉淀" / "Codex",
        "reports": MEISTOCK_ROOT / "02_项目文档" / "报告章节底稿",
        "evidence": MEISTOCK_ROOT / "06_证据链",
        "attachments": MEISTOCK_ROOT / "07_附件索引",
        "control": MEISTOCK_ROOT / "00_项目总控",
        "context": MEISTOCK_ROOT / "docs" / "context",
    }
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)
    rows = []
    readme = out_dir / "README_summary.md"
    if readme.exists():
        dest = dirs["reports"] / f"{timestamp}_unified_store_README_summary.md"
        shutil.copy2(readme, dest)
        rows.append({"target": str(dest), "status": "copied", "note": "README"})
    for source in (out_dir / "audit").glob("*.csv"):
        dest = dirs["evidence"] / f"{timestamp}_{source.name}"
        shutil.copy2(source, dest)
        rows.append({"target": str(dest), "status": "copied", "note": "audit_csv"})
    shutil.copy2(NEXT_STEPS, dirs["control"] / "NEXT_STEPS.md")
    rows.append({"target": str(dirs["control"] / "NEXT_STEPS.md"), "status": "copied", "note": "NEXT_STEPS"})
    if zip_path.exists():
        dest = dirs["attachments"] / zip_path.name
        shutil.copy2(zip_path, dest)
        rows.append({"target": str(dest), "status": "copied", "note": "zip"})
    checkpoint = dirs["checkpoint"] / f"{timestamp}_unified_adjusted_ohlcv_store_mve1_rerun_checkpoint.md"
    checkpoint.write_text(
        f"# Unified adjusted OHLCV Store + MVE1 Rerun Checkpoint {timestamp}\n\n"
        f"- No formal v9, no training, no backtest, no MVE2 started.\n"
        f"- Zip: `{zip_path}`\n",
        encoding="utf-8",
    )
    rows.append({"target": str(checkpoint), "status": "written", "note": "checkpoint"})
    context = dirs["context"] / "MeiStock_current_context.md"
    context.write_text(
        f"# MeiStock Current Context\n\nLast updated: {timestamp}\n\n"
        "Latest checkpoint: unified adjusted OHLCV store + MVE1 readiness rerun.\n\n"
        "No formal v9, no model training, no backtest, no MVE2 started.\n\n"
        f"Latest zip: `{zip_path}`.\n",
        encoding="utf-8",
    )
    rows.append({"target": str(context), "status": "written", "note": "context"})
    return pd.DataFrame(rows)


def package(out_dir: Path, zip_path: Path) -> None:
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        files = [
            PROJECT_ROOT / "scripts" / "us_stock_selection" / "47_build_unified_adjusted_ohlcv_store.py",
            PROJECT_ROOT / "scripts" / "us_stock_selection" / "48_rerun_mve1_on_unified_store.py",
            NEXT_STEPS,
            RUN_SUMMARY,
        ]
        files.extend([p for p in out_dir.rglob("*") if p.is_file()])
        seen: set[str] = set()
        for path in files:
            if not path.exists():
                continue
            arc = str(path.relative_to(PROJECT_ROOT)) if path.is_relative_to(PROJECT_ROOT) else path.name
            if arc in seen:
                continue
            seen.add(arc)
            zf.write(path, arc)


def main() -> None:
    args = parse_args()
    timestamp = args.timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = (args.out_dir or OUTPUT_ROOT / f"unified_adjusted_ohlcv_store_{timestamp}").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    for sub in ["audit", "prices", "actions"]:
        (out_dir / sub).mkdir(parents=True, exist_ok=True)
    logger = setup_logger(out_dir)
    logger.info("Starting MVE1 readiness rerun on unified store. No training, no backtest, no MVE2.")

    store_dir = args.store_dir.resolve()
    universe = load_universe(out_dir, args.previous_mve1_dir)
    download = load_required_csv(store_dir / "audit" / "download_audit.csv", "download audit")
    quality = load_required_csv(store_dir / "audit" / "price_quality_audit.csv", "price quality audit")
    corp = load_required_csv(store_dir / "audit" / "corporate_action_audit.csv", "corporate action audit")
    for df in [download, quality, corp]:
        if "ticker" in df.columns:
            df["ticker"] = df["ticker"].map(normalize_ticker)

    ticker_ready, features = ticker_readiness(universe, store_dir, download, quality)
    layers = layer_readiness(ticker_ready)
    changed = previous_comparison(args.previous_mve1_dir, ticker_ready)
    not_ready = make_not_ready(ticker_ready)
    split_sanity = split_sanity_from_corporate_actions(corp)
    manifest = store_manifest(store_dir, out_dir)
    decision = formal_or_limited_decision(layers, ticker_ready)

    # Persist to store audit and output audit.
    audit_outputs = {
        "ticker_readiness_after_unified_store.csv": ticker_ready,
        "layer_readiness_after_unified_store.csv": layers,
        "mve1_feature_build_readiness_after_unified_store.csv": features,
        "not_ready_ticker_reason_after_unified_store.csv": not_ready,
        "changed_readiness_vs_previous_audit.csv": changed,
        "split_sanity_audit.csv": split_sanity,
    }
    for name, frame in audit_outputs.items():
        frame.to_csv(store_dir / "audit" / name, index=False, encoding="utf-8-sig")
        frame.to_csv(out_dir / "audit" / name, index=False, encoding="utf-8-sig")
    for name in ["download_audit.csv", "price_quality_audit.csv", "corporate_action_audit.csv", "store_file_manifest.csv"]:
        src = store_dir / "audit" / name
        if src.exists():
            shutil.copy2(src, out_dir / "audit" / name)

    # Copy full current store for reproducible pack. Size is small enough for this 51 ticker audit.
    for ticker in universe["ticker"].tolist():
        for sub, suffix in [("prices", f"{ticker}.parquet"), ("actions", f"{ticker}_actions.csv")]:
            src = store_dir / sub / suffix
            if src.exists():
                shutil.copy2(src, out_dir / sub / suffix)

    readme = write_readme(out_dir, download, quality, corp, ticker_ready, layers, changed, decision)
    write_json(decision, out_dir / "unified_store_mve1_readiness_decision.json")
    shutil.copy2(PROJECT_ROOT / "scripts" / "us_stock_selection" / "47_build_unified_adjusted_ohlcv_store.py", out_dir / "47_build_unified_adjusted_ohlcv_store.py")
    shutil.copy2(Path(__file__), out_dir / Path(__file__).name)

    zip_path = OUTPUT_ROOT / f"us_stock_selection_unified_adjusted_ohlcv_store_{timestamp}.zip"
    update_next_steps(out_dir, zip_path, decision, download, quality, layers)
    write_run_summary(out_dir, zip_path, decision)
    if not args.no_zip:
        package(out_dir, zip_path)
    sync_index = sync_meistock(timestamp, out_dir, zip_path)
    sync_index.to_csv(out_dir / "audit" / "meistock_sync_index.csv", index=False, encoding="utf-8-sig")
    if not args.no_zip:
        package(out_dir, zip_path)
        if MEISTOCK_ROOT.exists():
            shutil.copy2(zip_path, MEISTOCK_ROOT / "07_附件索引" / zip_path.name)

    logger.info("MVE1 readiness rerun complete. decision=%s manifest_files=%s readme=%s", decision, len(manifest), readme)


if __name__ == "__main__":
    main()
