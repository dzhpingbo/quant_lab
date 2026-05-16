"""Build us_v82 frozen live monthly target holdings for daily packets.

This script is intentionally narrow:
- fixed strategy_id: top5_ytdcap80p_derisk100p
- fixed model/rule lineage: v8.1 Alpha360 LGBModel monthly replay + v8.2
  ytdcap80p_derisk100p overlay
- no strategy search, no v10, no pool expansion, no broker connection, no
  trading, and no order placement

The historical v8.2 formal audit is still the metrics source.  This script only
builds the current-month target-holding evidence needed by the trading packet.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import warnings
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from daily_trading_packet import qlib_reference_price, read_qlib_calendar, read_qlib_series
from quant_lab.us_stock_selection.canonical_replay_engine import CanonicalReplayConfig, v82_primary_variant
from quant_lab.us_stock_selection.v8_1_model_switch import MODEL_SPECS
from quant_lab.us_stock_selection.v8_paper_trading import make_model, trading_offset, tradable_universe
from quant_lab.us_stock_selection.v8_2_year_stability import apply_ex_ante_overlays, build_weights_from_audit


US_V82_STRATEGY_ID = "top5_ytdcap80p_derisk100p"
DEFAULT_PROVIDER_DIR = Path(r"C:\Users\Administrator\.qlib\qlib_data\us_data_local_2026_v91_growth")
DEFAULT_V81_RUN_DIR = ROOT / "outputs" / "us_stock_selection" / "run_20260502_210856"
DEFAULT_V81_LGB_DIR = DEFAULT_V81_RUN_DIR / "v8_1_model_switch" / "Alpha360_LGBModel"
DEFAULT_V81_CACHE_DIR = DEFAULT_V81_RUN_DIR / "v7_feature_cache"
FEATURE_COLUMNS = [f"f{i:04d}" for i in range(360)]


def fit_live_model(train: pd.DataFrame, pred_frame: pd.DataFrame, feature_cols: list[str], spec: Any) -> tuple[Any, dict[str, Any]]:
    """Fit the frozen monthly model with deterministic live-inference settings.

    This mirrors ``v8_paper_trading.fit_model`` but pins LightGBM to a
    deterministic single-thread setting for daily automation reproducibility.
    It does not change the frozen feature set, label, model family, or strategy
    parameters.
    """

    model = make_model(spec)
    try:
        estimator = model.steps[-1][1]
        if estimator.__class__.__name__ == "LGBMRegressor":
            estimator.set_params(n_jobs=1, deterministic=True, force_col_wise=True)
    except Exception:
        pass
    info = {"fit_warning_count": 0, "fit_warnings": "", "fit_status": "completed", "train_rows": int(len(train)), "predict_rows": int(len(pred_frame))}
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        model.fit(train[feature_cols], train[spec.label].astype(float))
    warning_texts = [str(item.message) for item in caught]
    info["fit_warning_count"] = len(warning_texts)
    info["fit_warnings"] = " | ".join(warning_texts[:5])
    if warning_texts:
        info["fit_status"] = "completed_with_warning"
    return model, info


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build us_v82 frozen live monthly target holdings.")
    parser.add_argument("--output-dir", default="", help="Output directory for live target evidence.")
    parser.add_argument("--provider-dir", default=str(DEFAULT_PROVIDER_DIR), help="Qlib provider directory.")
    parser.add_argument("--v8-1-lgb-dir", default=str(DEFAULT_V81_LGB_DIR), help="Frozen v8.1 LGB evidence directory.")
    parser.add_argument("--v8-1-cache-dir", default=str(DEFAULT_V81_CACHE_DIR), help="Frozen v8.1 feature-cache directory.")
    parser.add_argument("--dry-run", action="store_true", help="Print planned outputs without generating live evidence.")
    parser.add_argument("--strict", action="store_true", help="Return non-zero if live target cannot be built.")
    parser.add_argument("--json-out", default="", help="Optional JSON summary path.")
    parser.add_argument("--md-out", default="", help="Optional Markdown summary path.")
    parser.add_argument("--code-trace-dir", default="", help="Optional trace directory for CODE_TRACE.md.")
    return parser.parse_args()


def jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, (np.floating, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, dict):
        return {str(key): jsonable(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    return value


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(jsonable(payload), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def date_text(value: Any) -> str:
    if value is None:
        return ""
    try:
        parsed = pd.Timestamp(value)
    except Exception:
        return ""
    return "" if pd.isna(parsed) else parsed.date().isoformat()


def pct_id(value: float) -> str:
    return f"{int(round(float(value) * 100))}p"


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def provider_panel(provider_dir: Path, tickers: list[str], field: str, start: str, end: str) -> pd.DataFrame:
    calendar = read_qlib_calendar(provider_dir)
    if calendar.empty:
        return pd.DataFrame()
    index = calendar[(calendar >= pd.Timestamp(start)) & (calendar <= pd.Timestamp(end))]
    data = {ticker: read_qlib_series(provider_dir, ticker, field, calendar).reindex(index) for ticker in tickers}
    out = pd.DataFrame(data, index=index, dtype=float).sort_index().ffill()
    out.index.name = "date"
    return out


def shift_back(values: np.ndarray, periods: int) -> np.ndarray:
    out = np.full(values.shape, np.nan, dtype=float)
    if periods <= 0:
        return values.astype(float).copy()
    out[periods:, :] = values[:-periods, :]
    return out


def shift_forward(values: np.ndarray, periods: int) -> np.ndarray:
    out = np.full(values.shape, np.nan, dtype=float)
    if periods <= 0:
        return values.astype(float).copy()
    out[:-periods, :] = values[periods:, :]
    return out


def build_alpha360_like_frame(
    provider_dir: Path,
    tickers: list[str],
    start: str,
    end: str,
    fit_start: str = "2020-01-02",
    fit_end: str = "2022-12-31",
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Fast local Alpha360-compatible frame from qlib bin files.

    Qlib's Alpha360 Handler timed out on the refreshed v91 provider in this
    Windows environment.  This local builder mirrors Alpha360DL expressions and
    the default processors used by the frozen v8.1 cache: ProcessInf,
    ZScoreNorm(fit_start/fit_end), Fillna for features, and cross-sectional
    z-score labels.  The formal consistency check below still verifies the
    scoring/ranking code against the original frozen feature cache.
    """

    tickers = sorted({str(t).upper() for t in tickers})
    close = provider_panel(provider_dir, tickers, "close", start, end)
    open_ = provider_panel(provider_dir, tickers, "open", start, end).reindex(close.index).ffill()
    high = provider_panel(provider_dir, tickers, "high", start, end).reindex(close.index).ffill()
    low = provider_panel(provider_dir, tickers, "low", start, end).reindex(close.index).ffill()
    volume = provider_panel(provider_dir, tickers, "volume", start, end).reindex(close.index).ffill()
    if close.empty:
        raise ValueError(f"Provider close panel is empty: {provider_dir}")
    idx = pd.DatetimeIndex(close.index).normalize()
    matrices = {
        "close": close.to_numpy(dtype=float),
        "open": open_.to_numpy(dtype=float),
        "high": high.to_numpy(dtype=float),
        "low": low.to_numpy(dtype=float),
        "volume": volume.to_numpy(dtype=float),
    }
    close_arr = matrices["close"]
    volume_arr = matrices["volume"]
    feature_mats: list[np.ndarray] = []
    original_names: list[str] = []
    for name, field, denom in [
        ("CLOSE", "close", close_arr),
        ("OPEN", "open", close_arr),
        ("HIGH", "high", close_arr),
        ("LOW", "low", close_arr),
    ]:
        base = matrices[field]
        for lag in range(59, 0, -1):
            feature_mats.append(shift_back(base, lag) / denom)
            original_names.append(f"{name}{lag}")
        feature_mats.append(base / denom)
        original_names.append(f"{name}0")
    # The local provider has no vwap.day.bin.  The historical Alpha360 cache
    # has VWAP columns filled to zero after processors, so keep these empty and
    # let Fillna make them zero.
    for lag in range(59, 0, -1):
        feature_mats.append(np.full(close_arr.shape, np.nan, dtype=float))
        original_names.append(f"VWAP{lag}")
    feature_mats.append(np.full(close_arr.shape, np.nan, dtype=float))
    original_names.append("VWAP0")
    for lag in range(59, 0, -1):
        feature_mats.append(shift_back(volume_arr, lag) / (volume_arr + 1e-12))
        original_names.append(f"VOLUME{lag}")
    feature_mats.append(volume_arr / (volume_arr + 1e-12))
    original_names.append("VOLUME0")

    raw = np.stack(feature_mats, axis=2)
    raw = np.where(np.isinf(raw), np.nan, raw)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        date_feature_mean = np.nanmean(raw, axis=1)
    missing = np.where(np.isnan(raw))
    raw[missing] = date_feature_mean[missing[0], missing[2]]

    fit_mask = (idx >= pd.Timestamp(fit_start)) & (idx <= pd.Timestamp(fit_end))
    fit_values = raw[fit_mask, :, :].reshape(-1, raw.shape[2])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        mean_train = np.nanmean(fit_values, axis=0)
        std_train = np.nanstd(fit_values, axis=0)
    ignore = (std_train == 0) | np.isnan(std_train)
    std_train[ignore] = 1.0
    mean_train[ignore] = 0.0
    normed = (raw - mean_train.reshape(1, 1, -1)) / std_train.reshape(1, 1, -1)
    normed = np.nan_to_num(normed, nan=0.0, posinf=0.0, neginf=0.0)

    close_t1 = shift_forward(close_arr, 1)
    label_5d = shift_forward(close_arr, 6) / close_t1 - 1.0
    label_20d = shift_forward(close_arr, 21) / close_t1 - 1.0
    for label in (label_5d, label_20d):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            mean = np.nanmean(label, axis=1)
            std = np.nanstd(label, axis=1, ddof=1)
        std[(std == 0) | np.isnan(std)] = np.nan
        label[:, :] = (label - mean.reshape(-1, 1)) / std.reshape(-1, 1)

    dates = np.repeat(idx.to_numpy(), len(tickers))
    instruments = np.tile(np.asarray(tickers), len(idx))
    flat = normed.reshape(len(idx) * len(tickers), normed.shape[2])
    frame = pd.DataFrame(flat, columns=FEATURE_COLUMNS)
    frame.insert(0, "feature_set", "Alpha360")
    frame.insert(0, "instrument", instruments)
    frame.insert(0, "date", pd.to_datetime(dates))
    frame["label_5d"] = label_5d.reshape(len(idx) * len(tickers))
    frame["label_20d"] = label_20d.reshape(len(idx) * len(tickers))
    meta = {
        "feature_builder": "local_alpha360_compatible_bin_reader",
        "feature_columns": len(FEATURE_COLUMNS),
        "original_feature_columns": dict(zip(FEATURE_COLUMNS, original_names)),
        "date_start": date_text(idx.min()),
        "date_end": date_text(idx.max()),
        "instrument_count": len(tickers),
        "row_count": int(len(frame)),
        "fit_start": fit_start,
        "fit_end": fit_end,
        "vwap_note": "provider has no vwap.day.bin; VWAP columns are filled to zero like the frozen cache",
    }
    return frame, close, volume, meta


def latest_v82_audit_dir() -> Path | None:
    candidates = sorted(
        (ROOT / "outputs" / "us_stock_selection").glob("v82_frozen_formal_audit_*/formal_replay/formal_v82_baseline/formal_v82_score_rank_audit.csv"),
        key=lambda path: path.stat().st_mtime if path.exists() else 0,
        reverse=True,
    )
    return candidates[0].parents[2] if candidates else None


def last_trading_day_on_or_before(index: pd.DatetimeIndex, value: pd.Timestamp) -> pd.Timestamp | None:
    eligible = pd.DatetimeIndex(index).normalize()
    eligible = eligible[eligible <= value.normalize()]
    return pd.Timestamp(eligible.max()).normalize() if len(eligible) else None


def business_day_on_or_after(value: pd.Timestamp) -> pd.Timestamp:
    return pd.bdate_range(value.normalize(), periods=1)[0].normalize()


def previous_business_day(value: pd.Timestamp) -> pd.Timestamp:
    return pd.bdate_range(end=value.normalize() - pd.Timedelta(days=1), periods=1)[0].normalize()


def next_month_first_day(value: pd.Timestamp) -> pd.Timestamp:
    year = value.year + (1 if value.month == 12 else 0)
    month = 1 if value.month == 12 else value.month + 1
    return pd.Timestamp(year=year, month=month, day=1)


def month_end_decision_for_latest(index: pd.DatetimeIndex, latest_data_date: pd.Timestamp) -> pd.Timestamp | None:
    first_day = pd.Timestamp(year=latest_data_date.year, month=latest_data_date.month, day=1)
    first_trading = last_trading_day_on_or_before(index, first_day)
    if first_trading is None or first_trading < first_day:
        first_trading = business_day_on_or_after(first_day)
    # Once the current month has started, the active target is normally from
    # the previous month-end decision, executed T+1 at the start of this month.
    if latest_data_date >= first_trading:
        prev_month_end = first_day - pd.Timedelta(days=1)
        return last_trading_day_on_or_before(index, prev_month_end)
    prev_month_end = first_day - pd.Timedelta(days=1)
    prior_first = pd.Timestamp(year=prev_month_end.year, month=prev_month_end.month, day=1)
    return last_trading_day_on_or_before(index, prior_first - pd.Timedelta(days=1))


def next_rebalance_after_execution(execution_date: pd.Timestamp) -> tuple[pd.Timestamp, pd.Timestamp]:
    month_start = pd.Timestamp(year=execution_date.year, month=execution_date.month, day=1)
    current_month_end = pd.bdate_range(month_start, month_start + pd.offsets.MonthEnd(0))[-1].normalize()
    next_execution = business_day_on_or_after(current_month_end + pd.Timedelta(days=1))
    effective_end = previous_business_day(next_execution)
    return next_execution, effective_end


def compute_decision(
    *,
    frame: pd.DataFrame,
    close: pd.DataFrame,
    volume: pd.DataFrame,
    decision_date: pd.Timestamp,
    model_name: str = "LGBModel",
) -> dict[str, Any]:
    spec = MODEL_SPECS[model_name]
    local = frame.replace([np.inf, -np.inf], np.nan).copy()
    local["date"] = pd.to_datetime(local["date"])
    feature_date = local.loc[local["date"] <= decision_date, "date"].max()
    train_end = trading_offset(close.index, decision_date, -6)
    if pd.isna(feature_date) or pd.isna(train_end):
        raise ValueError(f"Cannot infer feature_date/train_end for decision_date={date_text(decision_date)}")
    train = local.loc[(local["date"] <= train_end) & local[spec.label].notna()].copy()
    pred_frame = local.loc[local["date"] == feature_date].copy()
    if len(train) < 500:
        raise ValueError(f"Insufficient train rows for live scoring: {len(train)}")
    if pred_frame.empty:
        raise ValueError(f"No prediction snapshot for feature_date={date_text(feature_date)}")
    model, fit_info = fit_live_model(train, pred_frame, FEATURE_COLUMNS, spec)
    pred = pred_frame.loc[:, ["date", "instrument"]].copy()
    pred["score"] = model.predict(pred_frame[FEATURE_COLUMNS])
    pred["instrument"] = pred["instrument"].astype(str).str.upper()
    dollar_volume = close.reindex(volume.index).ffill() * volume.reindex(close.index).ffill()
    tradable = tradable_universe(close, dollar_volume, pred["instrument"].tolist(), decision_date, 20_000_000.0)
    ranked = pred.loc[pred["instrument"].isin(tradable)].sort_values("score", ascending=False).copy()
    if ranked.empty:
        raise ValueError(f"No tradable ranked rows for decision_date={date_text(decision_date)}")
    ranked["raw_rank"] = np.arange(1, len(ranked) + 1)
    ranked["adjusted_rank"] = ranked["raw_rank"]
    ranked["selected_flag"] = ranked["adjusted_rank"].le(5)
    ranked["selected_rank"] = np.where(ranked["selected_flag"], ranked["adjusted_rank"], np.nan)
    selected = ranked.head(5).copy()
    execution_date = trading_offset(close.index, decision_date, 1)
    if pd.isna(execution_date):
        execution_date = business_day_on_or_after(decision_date + pd.Timedelta(days=1))
    score_snapshot = ranked.rename(columns={"instrument": "ticker", "score": "raw_score"}).copy()
    score_snapshot["adjusted_score"] = score_snapshot["raw_score"]
    score_snapshot["decision_date"] = date_text(decision_date)
    score_snapshot["feature_snapshot_date"] = date_text(feature_date)
    score_snapshot["execution_date"] = date_text(execution_date)
    score_snapshot["model_name"] = model_name
    score_snapshot["feature_set"] = spec.feature_set
    score_snapshot["label"] = spec.label
    score_snapshot["selection_rule"] = "top5_equal_monthly"
    return {
        "decision_date": pd.Timestamp(decision_date).normalize(),
        "feature_date": pd.Timestamp(feature_date).normalize(),
        "train_end": pd.Timestamp(train_end).normalize(),
        "execution_date": pd.Timestamp(execution_date).normalize(),
        "fit_info": fit_info,
        "train_rows": int(len(train)),
        "predict_rows": int(len(pred_frame)),
        "tradable_count": int(len(tradable)),
        "ranked": ranked,
        "selected": selected,
        "score_snapshot": score_snapshot,
    }


def formal_top5(score_audit: pd.DataFrame, decision_date: pd.Timestamp) -> list[str]:
    data = score_audit.copy()
    data["decision_date"] = pd.to_datetime(data["decision_date"], errors="coerce")
    local = data.loc[data["decision_date"].eq(decision_date)].copy()
    if local.empty:
        return []
    selected = local.loc[local.get("selected_flag", False).astype(str).str.lower().isin({"true", "1", "yes"})].copy()
    if selected.empty:
        selected = local.sort_values("adjusted_rank").head(5)
    rank_col = "selected_rank" if "selected_rank" in selected.columns and selected["selected_rank"].notna().any() else "adjusted_rank"
    selected[rank_col] = pd.to_numeric(selected[rank_col], errors="coerce")
    return selected.sort_values(rank_col)["ticker"].astype(str).str.upper().head(5).tolist()


def consistency_check(v8_1_lgb_dir: Path, v8_1_cache_dir: Path, provider_dir: Path) -> dict[str, Any]:
    score_path = v8_1_lgb_dir / "score_rank_audit_trail.csv"
    cache_path = v8_1_cache_dir / "alpha360_cache.parquet"
    score = read_csv(score_path)
    if score.empty or not cache_path.exists():
        return {
            "live_formal_consistency_check": "UNKNOWN",
            "reason": "missing frozen score audit or alpha360 cache",
            "source_score_audit": str(score_path),
            "source_feature_cache": str(cache_path),
        }
    score["decision_date"] = pd.to_datetime(score["decision_date"], errors="coerce")
    compared_decision = pd.Timestamp(score["decision_date"].dropna().max()).normalize()
    compared_month = compared_decision.to_period("M").strftime("%Y-%m")
    source_frame = pd.read_parquet(cache_path)
    source_frame["date"] = pd.to_datetime(source_frame["date"])
    tickers = sorted(source_frame["instrument"].dropna().astype(str).str.upper().unique().tolist())
    close = provider_panel(provider_dir, sorted(set(tickers) | {"SPY", "QQQ", "QLD", "TQQQ", "SHY"}), "close", "2020-01-01", date_text(compared_decision))
    volume = provider_panel(provider_dir, tickers, "volume", "2020-01-01", date_text(compared_decision)).reindex(close.index).ffill()
    result = compute_decision(frame=source_frame, close=close, volume=volume, decision_date=compared_decision)
    replay_top5 = result["selected"]["instrument"].astype(str).str.upper().tolist()
    expected_top5 = formal_top5(score, compared_decision)
    ticker_diff = sorted(set(replay_top5).symmetric_difference(expected_top5))
    rank_diff = [
        {"rank": idx + 1, "formal": expected_top5[idx] if idx < len(expected_top5) else "", "live_replay": replay_top5[idx] if idx < len(replay_top5) else ""}
        for idx in range(max(len(expected_top5), len(replay_top5)))
        if (expected_top5[idx] if idx < len(expected_top5) else "") != (replay_top5[idx] if idx < len(replay_top5) else "")
    ]
    status = "PASS" if expected_top5 == replay_top5 and len(expected_top5) == 5 else "FAIL"
    return {
        "live_formal_consistency_check": status,
        "compared_month": compared_month,
        "compared_decision_date": date_text(compared_decision),
        "formal_top5": expected_top5,
        "live_replay_top5": replay_top5,
        "ticker_diff": ticker_diff,
        "rank_diff": rank_diff,
        "score_diff": "not_materialized; LGB predictions match selected rank/order check",
        "source_score_audit": str(score_path),
        "source_feature_cache": str(cache_path),
        "train_rows": result["train_rows"],
        "predict_rows": result["predict_rows"],
        "tradable_count": result["tradable_count"],
    }


def build_code_trace(trace_dir: Path, output_dir: Path, provider_dir: Path, v8_1_lgb_dir: Path, v8_1_cache_dir: Path) -> str:
    trace_dir.mkdir(parents=True, exist_ok=True)
    trace_path = trace_dir / "CODE_TRACE.md"
    provider_calendar = read_qlib_calendar(provider_dir)
    latest_provider_date = date_text(provider_calendar.max()) if not provider_calendar.empty else ""
    score_path = v8_1_lgb_dir / "score_rank_audit_trail.csv"
    ledger_path = v8_1_lgb_dir / "monthly_decision_ledger.csv"
    nav_path = v8_1_lgb_dir / "daily_nav.csv"
    score = read_csv(score_path)
    ledger = read_csv(ledger_path)
    nav = read_csv(nav_path)
    latest_score_decision = ""
    if not score.empty and "decision_date" in score:
        latest_score_decision = date_text(pd.to_datetime(score["decision_date"], errors="coerce").max())
    latest_nav = ""
    if not nav.empty and "date" in nav:
        latest_nav = date_text(pd.to_datetime(nav["date"], errors="coerce").max())
    latest_execution = ""
    if not ledger.empty and "execution_date" in ledger:
        latest_execution = date_text(pd.to_datetime(ledger["execution_date"], errors="coerce").max())
    text = f"""# us_v82 Live Code Trace

- trace_time: `{datetime.now().isoformat(timespec='seconds')}`
- output_dir: `{output_dir}`
- provider_dir: `{provider_dir}`
- provider_latest_data_date: `{latest_provider_date}`

## Search Scope

Searched/read:
- `scripts/us_stock_selection/`
- `scripts/automation/`
- `quant_lab/us_stock_selection/`
- `outputs/us_stock_selection/v82_frozen_formal_audit_*`
- `outputs/daily_quant_lab_runs/`
- `{provider_dir}`

Keywords covered: `top5_ytdcap80p_derisk100p`, `ytdcap80p`, `derisk100p`, `top5`,
`monthly_holdings`, `decision_ledger`, `formal_v82_decision_ledger`,
`formal_v82_monthly_holdings`, `score`, `rank`, `target_weight`, `rebalance`,
`execution_date`, `effective_start`, `effective_end`, `provider`, `calendar`,
`ytd`, `cap80`, `drawdown`, `risk_off`, `risk_on`.

## Code Map

1. v8.2 frozen top5 main entry:
   - `scripts/us_stock_selection/51_run_v82_frozen_formal_audit.py`
   - calls `quant_lab/us_stock_selection/canonical_replay_engine.py::replay_formal_v82_baseline`.

2. strategy_id:
   - `quant_lab/us_stock_selection/canonical_replay_engine.py::PRIMARY_STRATEGY_ID`
   - value: `top5_ytdcap80p_derisk100p`.

3. score calculation:
   - historical source: `quant_lab/us_stock_selection/v8_paper_trading.py::run_paper_trading_replay`
   - calls `fit_model`, then `model.predict(pred_frame[feature_cols])`.
   - model spec comes from `quant_lab/us_stock_selection/v8_1_model_switch.py::MODEL_SPECS['LGBModel']`.

4. rank calculation:
   - `v8_paper_trading.py::run_paper_trading_replay`
   - `ranked = pred.loc[pred['instrument'].isin(tradable)].sort_values('score', ascending=False)`.
   - `selected = ranked.head(5)`.

5. ytdcap80p implementation:
   - `quant_lab/us_stock_selection/v8_2_year_stability.py::apply_ex_ante_overlays`
   - computes shifted YTD return of the base portfolio and applies `derisk_scale = 1 - derisk_ratio`
     when YTD return exceeds `0.80`.

6. derisk100p implementation:
   - same function, with `YearStabilityVariant.derisk_ratio = 1.0`.
   - constructed by `canonical_replay_engine.py::v82_primary_variant`.

7. monthly rebalance:
   - score replay dates: `v8_paper_trading.py::rebalance_dates(..., timing='month_end')`.
   - execution date: `v8_paper_trading.py::trading_offset(..., execution_delay=1)`.
   - v8.2 weights from audit: `v8_2_year_stability.py::build_weights_from_audit`.

8. formal_v82_decision_ledger.csv:
   - generated by `canonical_replay_engine.py::build_formal_decision_ledger`.
   - source: `{ledger_path}`.

9. formal_v82_monthly_holdings.csv:
   - generated by `canonical_replay_engine.py::replay_formal_v82_baseline`
   - from `weights.stack()` after `build_weights_from_audit` and `apply_ex_ante_overlays`.

10. why formal audit stopped:
   - frozen score audit latest decision_date: `{latest_score_decision}`
   - frozen ledger latest execution_date: `{latest_execution}`
   - frozen daily_nav latest date: `{latest_nav}`
   - provider latest date: `{latest_provider_date}`
   - therefore formal audit replay could only replay weights through the source score/nav window,
     not infer the 2026-05 current-month target.

11. provider latest data readability:
   - provider calendar and bin close/volume files are readable directly from qlib bin files.
   - Qlib Handler/D.features on the refreshed provider timed out in this Windows environment, so the
     live wrapper uses a direct bin reader plus Alpha360-compatible formulas and validates the
     scoring/ranking path against the frozen source cache.

12. missing/added step for 2026-05:
   - missing from old code: current-month Alpha360 LGB score snapshot and monthly decision row.
   - added here: `scripts/automation/run_us_v82_frozen_live_daily.py` builds that live snapshot,
     runs a formal consistency check on a known frozen month, then emits live target holdings only
     when current target effectiveness and consistency gates pass.

## Classification

Case B: code had formal audit and historical scoring logic, but no standalone live scoring entry.
The live entry now extracts/reuses the frozen monthly scoring/ranking/overlay logic without strategy
search or pool expansion.
"""
    trace_path.write_text(text, encoding="utf-8")
    return str(trace_path)


def build_payload(
    output_dir: Path,
    provider_dir: Path,
    v8_1_lgb_dir: Path,
    v8_1_cache_dir: Path,
    code_trace_dir: Path | None,
) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any], dict[str, Any]]:
    calendar = read_qlib_calendar(provider_dir)
    provider_latest = pd.Timestamp(calendar.max()).normalize() if not calendar.empty else pd.NaT
    score_path = v8_1_lgb_dir / "score_rank_audit_trail.csv"
    source_score = read_csv(score_path)
    if source_score.empty:
        raise FileNotFoundError(f"Frozen score/rank audit missing or empty: {score_path}")
    source_score["ticker"] = source_score["ticker"].astype(str).str.upper()
    tickers = sorted(source_score["ticker"].dropna().unique().tolist())
    trace_path = build_code_trace(code_trace_dir or output_dir, output_dir, provider_dir, v8_1_lgb_dir, v8_1_cache_dir)
    consistency = consistency_check(v8_1_lgb_dir, v8_1_cache_dir, provider_dir)

    if pd.isna(provider_latest):
        raise ValueError(f"Provider calendar missing or empty: {provider_dir}")
    live_decision = month_end_decision_for_latest(calendar, provider_latest)
    if live_decision is None:
        raise ValueError(f"Cannot infer live decision date from provider latest {date_text(provider_latest)}")
    start = "2020-01-02"
    frame, close, volume, feature_meta = build_alpha360_like_frame(provider_dir, tickers, start, date_text(provider_latest))
    decision = compute_decision(frame=frame, close=close, volume=volume, decision_date=live_decision)
    factor_snapshot = frame.loc[frame["date"].eq(decision["feature_date"])].copy()
    next_rebalance, effective_end = next_rebalance_after_execution(decision["execution_date"])

    score_snapshot = decision["score_snapshot"].copy()
    selected = decision["selected"].copy()
    selected_tickers = selected["instrument"].astype(str).str.upper().tolist()
    selected_scores = dict(zip(selected["instrument"].astype(str).str.upper(), selected["score"].astype(float)))

    live_audit = score_snapshot.rename(columns={"ticker": "ticker", "raw_score": "raw_score"}).copy()
    live_audit["decision_date"] = pd.to_datetime(live_audit["decision_date"])
    live_audit["candidate_flag"] = True
    live_audit["tradable_flag"] = True
    live_audit["selection_rule"] = "top5_equal_monthly"
    live_audit["adjusted_score"] = pd.to_numeric(live_audit["adjusted_score"], errors="coerce")
    live_audit["raw_score"] = pd.to_numeric(live_audit["raw_score"], errors="coerce")
    combined_audit = pd.concat([source_score, live_audit.reindex(columns=source_score.columns, fill_value=np.nan)], ignore_index=True, sort=False)
    close_for_overlay = provider_panel(provider_dir, sorted(set(tickers) | {"SPY", "QQQ", "QLD", "TQQQ", "SHY"}), "close", "2020-01-01", date_text(provider_latest))
    raw_weights = build_weights_from_audit(combined_audit, close_for_overlay, v82_primary_variant(CanonicalReplayConfig(provider_uri=provider_dir)))
    overlay = apply_ex_ante_overlays(close_for_overlay, raw_weights, v82_primary_variant(CanonicalReplayConfig(provider_uri=provider_dir)))
    weights = overlay["weights"]
    latest_weights = weights.loc[weights.index <= provider_latest].tail(1)
    exposure = float(latest_weights.drop(columns=["SHY"], errors="ignore").sum(axis=1).iloc[0]) if not latest_weights.empty else 0.0
    risk_off = exposure <= 1e-9
    consistency_status = str(consistency.get("live_formal_consistency_check", "UNKNOWN"))
    effective = decision["execution_date"] <= provider_latest <= effective_end
    live_ready = bool(effective and consistency_status == "PASS" and len(selected_tickers) == 5)
    live_status = "LIVE_TARGET_READY" if live_ready and not risk_off else "LIVE_TARGET_RISK_OFF" if live_ready and risk_off else "LIVE_TARGET_BLOCKED"
    blocking_reason = ""
    if consistency_status != "PASS":
        blocking_reason = f"live_formal_consistency_check={consistency_status}"
    elif not effective:
        blocking_reason = (
            f"target is not effective for provider latest date: start={date_text(decision['execution_date'])}, "
            f"end={date_text(effective_end)}, latest={date_text(provider_latest)}"
        )
    rows: list[dict[str, Any]] = []
    for rank, ticker in enumerate(selected_tickers, start=1):
        ref = qlib_reference_price(provider_dir, ticker, preferred_date=date_text(provider_latest))
        target_weight = 0.0 if risk_off else 0.20
        rows.append(
            {
                "asof_date": datetime.now().date().isoformat(),
                "latest_data_date": date_text(provider_latest),
                "strategy_id": US_V82_STRATEGY_ID,
                "live_status": live_status,
                "risk_state": "RISK_OFF" if risk_off else "RISK_ON",
                "derisk_triggered": bool(risk_off),
                "signal_source_date": date_text(decision["feature_date"]),
                "rebalance_decision_date": date_text(decision["decision_date"]),
                "target_holding_date": date_text(decision["execution_date"]),
                "target_effective_start_date": date_text(decision["execution_date"]),
                "target_effective_end_date": date_text(effective_end),
                "next_rebalance_date": date_text(next_rebalance),
                "ticker": ticker,
                "rank": rank,
                "score": selected_scores.get(ticker),
                "target_weight": target_weight,
                "selection_reason": "v8.2 frozen Alpha360 LGBModel score replay; top5_ytdcap80p_derisk100p",
                "source_provider_dir": str(provider_dir),
                "source_artifact": str(score_path),
                "is_live_target": bool(live_ready),
                "blocking_reason": blocking_reason,
                "reference_price_date": ref.get("reference_price_date"),
                "reference_price": ref.get("reference_price"),
                "reference_price_field": ref.get("reference_price_field"),
                "price_adjusted_flag": ref.get("price_adjusted_flag"),
                "signal_freshness_status": "EFFECTIVE_HOLDING" if live_ready else "BLOCKED_STALE_SIGNAL",
            }
        )
    diagnostics = {
        "provider_dir": str(provider_dir),
        "latest_data_date": date_text(provider_latest),
        "live_decision_date": date_text(live_decision),
        "feature_date": date_text(decision["feature_date"]),
        "train_end": date_text(decision["train_end"]),
        "execution_date": date_text(decision["execution_date"]),
        "target_effective_end_date": date_text(effective_end),
        "next_rebalance_date": date_text(next_rebalance),
        "train_rows": decision["train_rows"],
        "predict_rows": decision["predict_rows"],
        "tradable_count": decision["tradable_count"],
        "fit_info": decision["fit_info"],
        "feature_meta": feature_meta,
        "overlay_exposure_at_latest": exposure,
        "risk_off": risk_off,
        "code_trace_path": trace_path,
    }
    payload = {
        "status": "PASS" if live_ready else "FAIL",
        "final_status": "PASS" if live_ready else "FAIL",
        "live_status": live_status,
        "live_target_available": bool(live_ready),
        "strategy_id": US_V82_STRATEGY_ID,
        "provider_dir": str(provider_dir),
        "latest_data_date": date_text(provider_latest),
        "latest_decision_date": date_text(decision["decision_date"]),
        "signal_source_date": date_text(decision["feature_date"]),
        "target_effective_start_date": date_text(decision["execution_date"]),
        "target_effective_end_date": date_text(effective_end),
        "next_rebalance_date": date_text(next_rebalance),
        "risk_state": "RISK_OFF" if risk_off else "RISK_ON",
        "derisk_triggered": bool(risk_off),
        "top5_tickers": selected_tickers,
        "live_formal_consistency_check": consistency_status,
        "consistency_check_path": str(output_dir / "us_v82_live_consistency_check.json"),
        "source_score_audit": str(score_path),
        "source_decision_ledger": str(v8_1_lgb_dir / "monthly_decision_ledger.csv"),
        "source_feature_cache": str(v8_1_cache_dir / "alpha360_cache.parquet"),
        "source_formal_audit_dir": str(latest_v82_audit_dir() or ""),
        "errors": [] if live_ready else [blocking_reason or "live target failed safety gates"],
        "warnings": [
            "Live features are built with a local Alpha360-compatible bin reader because Qlib Handler timed out on the refreshed provider."
        ],
        "no_strategy_search": True,
        "no_v10": True,
        "no_pool_expansion": True,
        "no_broker": True,
        "output_dir": str(output_dir),
        "code_trace_path": trace_path,
    }
    return payload, pd.DataFrame(rows), score_snapshot, factor_snapshot, diagnostics, consistency


def write_markdown(path: Path, payload: dict[str, Any], rows: pd.DataFrame) -> None:
    lines = [
        "# us_v82 Frozen Live Monthly Decision",
        "",
        f"- Status: `{payload.get('final_status')}`",
        f"- Live status: `{payload.get('live_status')}`",
        f"- Strategy id: `{payload.get('strategy_id')}`",
        f"- Provider latest data date: `{payload.get('latest_data_date')}`",
        f"- Live decision date: `{payload.get('latest_decision_date')}`",
        f"- Signal source / feature date: `{payload.get('signal_source_date')}`",
        f"- Target effective start: `{payload.get('target_effective_start_date')}`",
        f"- Target effective end: `{payload.get('target_effective_end_date')}`",
        f"- Next rebalance date: `{payload.get('next_rebalance_date')}`",
        f"- Risk state: `{payload.get('risk_state')}`",
        f"- Derisk triggered: `{payload.get('derisk_triggered')}`",
        f"- Live target available: `{payload.get('live_target_available')}`",
        f"- live_formal_consistency_check: `{payload.get('live_formal_consistency_check')}`",
        "",
        "## Target Rows",
    ]
    if rows.empty:
        lines.append("- None")
    else:
        cols = ["ticker", "rank", "score", "target_weight", "is_live_target", "live_status", "blocking_reason"]
        lines.append("| " + " | ".join(cols) + " |")
        lines.append("| " + " | ".join(["---"] * len(cols)) + " |")
        for row in rows[cols].to_dict("records"):
            lines.append("| " + " | ".join(str(row.get(col, "")) for col in cols) + " |")
    if payload.get("errors"):
        lines.extend(["", "## Errors"])
        lines.extend([f"- {item}" for item in payload["errors"]])
    if payload.get("warnings"):
        lines.extend(["", "## Warnings"])
        lines.extend([f"- {item}" for item in payload["warnings"]])
    lines.extend(
        [
            "",
            "## Guardrails",
            "- No strategy search, v10, pool expansion, broker connection, trading, or order placement.",
            "- Formal audit holdings are never used as current executable targets.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_consistency_md(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# us_v82 Live/Formal Consistency Check",
        "",
        f"- live_formal_consistency_check: `{payload.get('live_formal_consistency_check')}`",
        f"- compared_month: `{payload.get('compared_month')}`",
        f"- compared_decision_date: `{payload.get('compared_decision_date')}`",
        f"- formal_top5: `{', '.join(payload.get('formal_top5', []))}`",
        f"- live_replay_top5: `{', '.join(payload.get('live_replay_top5', []))}`",
        f"- ticker_diff: `{payload.get('ticker_diff')}`",
        f"- rank_diff: `{payload.get('rank_diff')}`",
        "",
        "This checks the frozen scoring/ranking code path on a known formal month before allowing a current live target.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_manifest(output_dir: Path) -> Path:
    rows = []
    for path in sorted(output_dir.glob("us_v82_live_*")):
        if path.is_file():
            rows.append({"path": str(path), "size_bytes": path.stat().st_size, "mtime": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")})
    manifest_path = output_dir / "us_v82_live_manifest.json"
    write_json(manifest_path, {"files": rows, "count": len(rows)})
    return manifest_path


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir) if args.output_dir else ROOT / "outputs" / "us_stock_selection" / f"us_v82_live_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    output_dir.mkdir(parents=True, exist_ok=True)
    json_out = Path(args.json_out) if args.json_out else output_dir / "us_v82_live_target_holdings.json"
    md_out = Path(args.md_out) if args.md_out else output_dir / "us_v82_live_signal_summary.md"
    csv_out = output_dir / "us_v82_live_target_holdings.csv"

    if args.dry_run:
        payload = {
            "status": "DRY_RUN",
            "output_dir": str(output_dir),
            "provider_dir": args.provider_dir,
            "json_out": str(json_out),
            "md_out": str(md_out),
            "csv_out": str(csv_out),
            "strict": bool(args.strict),
        }
        write_json(json_out, payload)
        write_markdown(md_out, payload, pd.DataFrame())
        write_manifest(output_dir)
        print(json.dumps(jsonable(payload), ensure_ascii=False, indent=2))
        return 0

    payload, rows, scores, factor_snapshot, diagnostics, consistency = build_payload(
        output_dir,
        Path(args.provider_dir),
        Path(args.v8_1_lgb_dir),
        Path(args.v8_1_cache_dir),
        Path(args.code_trace_dir) if args.code_trace_dir else None,
    )
    rows.to_csv(csv_out, index=False, encoding="utf-8-sig")
    scores.to_csv(output_dir / "us_v82_live_score_snapshot.csv", index=False, encoding="utf-8-sig")
    factor_cols = ["date", "instrument", *FEATURE_COLUMNS, "label_5d", "label_20d"]
    factor_snapshot.loc[:, [col for col in factor_cols if col in factor_snapshot.columns]].to_csv(
        output_dir / "us_v82_live_factor_snapshot.csv",
        index=False,
        encoding="utf-8-sig",
    )
    write_json(json_out, payload)
    write_json(output_dir / "us_v82_live_diagnostics.json", diagnostics)
    write_json(output_dir / "us_v82_live_consistency_check.json", consistency)
    write_consistency_md(output_dir / "us_v82_live_consistency_check.md", consistency)
    write_markdown(md_out, payload, rows)
    code_trace_path = Path(str(payload.get("code_trace_path", "")))
    if code_trace_path.exists():
        (output_dir / "us_v82_live_code_trace.md").write_text(code_trace_path.read_text(encoding="utf-8"), encoding="utf-8")
    manifest = write_manifest(output_dir)
    payload["manifest"] = str(manifest)
    write_json(json_out, payload)
    print(
        json.dumps(
            jsonable(
                {
                    "status": payload.get("status"),
                    "live_status": payload.get("live_status"),
                    "output_dir": output_dir,
                    "live_target_available": payload.get("live_target_available"),
                    "top5_tickers": payload.get("top5_tickers"),
                    "live_formal_consistency_check": payload.get("live_formal_consistency_check"),
                }
            ),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if payload.get("live_target_available") or not args.strict else 2


if __name__ == "__main__":
    raise SystemExit(main())
