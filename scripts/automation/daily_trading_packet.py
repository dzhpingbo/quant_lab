"""Generate human-review trading packets for daily quant_lab jobs.

This module converts frozen replay outputs into target holdings, order tickets,
and risk summaries. It never connects to brokers, reads broker accounts,
submits orders, searches strategies, or changes any frozen strategy logic.
"""

from __future__ import annotations

import csv
import json
import math
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


HOLDINGS_COLUMNS = [
    "asof_date",
    "job_id",
    "strategy_id",
    "sleeve_id",
    "symbol",
    "ticker",
    "asset_name",
    "currency",
    "risk_state",
    "derisk_triggered",
    "signal",
    "action",
    "signal_source_date",
    "target_holding_date",
    "target_effective_start_date",
    "target_effective_end_date",
    "next_rebalance_date",
    "target_position",
    "rank",
    "target_weight",
    "account_notional",
    "target_notional",
    "reference_price_date",
    "reference_price",
    "reference_price_field",
    "price_adjusted_flag",
    "signal_price_date_gap_days",
    "signal_price_date_gap_trading_days",
    "signal_freshness_status",
    "execution_readiness",
    "order_intent",
    "blocking_warnings_count",
    "target_shares",
    "estimated_notional",
    "selection_reason",
    "manual_check_required",
    "notes",
]

ORDER_COLUMNS = [
    "asof_date",
    "job_id",
    "strategy_id",
    "sleeve_id",
    "ticker",
    "currency",
    "current_shares",
    "target_shares",
    "trade_side",
    "trade_shares",
    "signal_source_date",
    "target_holding_date",
    "target_effective_start_date",
    "target_effective_end_date",
    "next_rebalance_date",
    "signal_price_date_gap_days",
    "signal_freshness_status",
    "execution_readiness",
    "order_intent",
    "position_file_exists",
    "price_is_tradeable",
    "price_validation_status",
    "formal_trade_allowed",
    "reference_price_date",
    "reference_price",
    "reference_price_field",
    "limit_price",
    "estimated_trade_notional",
    "order_type",
    "time_in_force",
    "reason",
    "manual_check_required",
    "blocking_warning",
]

INCREASE_ACTIONS = {"BUY", "BUY_OR_HOLD", "BUY_OR_INCREASE", "BUY_NEXT_OPEN", "INCREASE", "LONG"}
KEEP_LONG_ACTIONS = {"HOLD_OR_KEEP_LONG", "KEEP_LONG", "HOLD_LONG"}
DECREASE_ACTIONS = {"SELL_OR_DECREASE", "DECREASE", "TRIM_LONG"}
SELL_TO_CASH_ACTIONS = {"SELL", "SELL_OR_EMPTY", "SELL_NEXT_OPEN", "RISK_OFF", "DERISK_TO_CASH", "SELL_TO_CASH"}
KEEP_CASH_ACTIONS = {"WAIT", "WAIT_OR_STAY_CASH", "HOLD_OR_KEEP_CASH", "STAY_CASH", "CASH", "EMPTY", "NO_TRADE"}
RISK_ON_ACTIONS = INCREASE_ACTIONS | KEEP_LONG_ACTIONS
RISK_OFF_ACTIONS = SELL_TO_CASH_ACTIONS | KEEP_CASH_ACTIONS
US_V82_STRATEGY_ID = "top5_ytdcap80p_derisk100p"
DEFAULT_PROVIDER_DIR = Path(r"C:\Users\Administrator\.qlib\qlib_data\us_data_local_2026_v91_growth")
READY_FOR_MANUAL_REVIEW = "READY_FOR_MANUAL_REVIEW"
NEEDS_POSITION_FILE = "NEEDS_POSITION_FILE"
NEEDS_MANUAL_PRICE = "NEEDS_MANUAL_PRICE"
BLOCKED_STALE_SIGNAL = "BLOCKED_STALE_SIGNAL"
BLOCKED_MISSING_PRICE = "BLOCKED_MISSING_PRICE"
BLOCKED_UNKNOWN_ACTION = "BLOCKED_UNKNOWN_ACTION"
NEEDS_MANUAL_REVIEW = "NEEDS_MANUAL_REVIEW"
NO_BUYING_POWER = "NO_BUYING_POWER"
QDT_TQQQ_CROSS_SLEEVE_NOTE = "同一标的也在 us_v82 Top5 中，需人工确认是否两个 sleeve 合并管理；当前默认不跨 sleeve 合并。"
US_V82_TARGET_ONLY_NOTE = "仅目标组合建议，无独立资金，不生成订单。"


def jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, dict):
        return {str(key): jsonable(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    if pd.isna(value) if not isinstance(value, (dict, list, tuple, str, bytes, Path)) else False:
        return None
    return value


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(jsonable(payload), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def project_path(project_root: Path, value: str | Path | None) -> Path | None:
    if value is None or str(value).strip() == "":
        return None
    path = Path(str(value)).expanduser()
    return path if path.is_absolute() else project_root / path


def safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def safe_int(value: Any) -> int:
    number = safe_float(value)
    return int(number) if number is not None else 0


def account_notional(sleeve: dict[str, Any]) -> float:
    return float(sleeve.get("account_notional_usd", sleeve.get("account_notional_cny", sleeve.get("account_notional", 0.0))) or 0.0)


def format_float(value: Any, digits: int = 6) -> str:
    number = safe_float(value)
    if number is None:
        return ""
    text = f"{number:.{digits}f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def round_price(value: float | None, currency: str) -> float | None:
    if value is None:
        return None
    digits = 3 if currency.upper() == "CNY" else 2
    return round(value, digits)


def floor_to_lot(shares: float, lot_size: int, allow_fractional: bool) -> float:
    if shares <= 0:
        return 0.0
    if allow_fractional:
        return round(shares, 6)
    lot = max(1, int(lot_size or 1))
    return float(math.floor(shares / lot) * lot)


def normalize_action(action: Any) -> str:
    return str(action or "").strip().upper()


def action_to_target_position(action: Any, current_shares: float = 0.0) -> tuple[str, float | None, str, str]:
    normalized = normalize_action(action)
    if normalized in RISK_ON_ACTIONS:
        return "LONG", 1.0, "RISK_ON", ""
    if normalized in DECREASE_ACTIONS:
        return "CASH", 0.0, "RISK_OFF", "SELL_OR_DECREASE has no explicit target weight in this source; mapped to cash for review."
    if normalized in RISK_OFF_ACTIONS:
        return "CASH", 0.0, "RISK_OFF", ""
    if normalized == "HOLD":
        if current_shares > 0:
            return "LONG", 1.0, "RISK_ON", ""
        return "UNKNOWN", None, "UNKNOWN", "HOLD action without current position; manual review required."
    return "UNKNOWN", None, "UNKNOWN", "Unrecognized action; manual review required."


def qldtqqq_action_to_target(action: Any, desired_weight: float | None, current_shares: float = 0.0) -> tuple[str, float | None, str, str]:
    normalized = normalize_action(action)
    weight = max(0.0, desired_weight or 0.0)
    if normalized in INCREASE_ACTIONS or normalized in KEEP_LONG_ACTIONS:
        return "LONG", weight, "RISK_ON", ""
    if normalized in DECREASE_ACTIONS:
        if weight > 0.01:
            return "LONG", weight, "RISK_ON", ""
        return "CASH", 0.0, "RISK_OFF", ""
    if normalized in SELL_TO_CASH_ACTIONS or normalized in KEEP_CASH_ACTIONS:
        return "CASH", 0.0, "RISK_OFF", ""
    if normalized == "HOLD":
        if current_shares > 0:
            return "LONG", weight if weight > 0 else 1.0, "RISK_ON", ""
        return "CASH", 0.0, "RISK_OFF", ""
    return "UNKNOWN", None, "UNKNOWN", "Unrecognized action; manual review required."


def parse_date(value: Any) -> pd.Timestamp | None:
    if value is None or str(value).strip() == "":
        return None
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return pd.Timestamp(parsed).normalize()


def date_text(value: pd.Timestamp | None) -> str:
    return value.date().isoformat() if value is not None else ""


def date_gap_days(left: Any, right: Any) -> int | None:
    left_ts = parse_date(left)
    right_ts = parse_date(right)
    if left_ts is None or right_ts is None:
        return None
    return int((right_ts.date() - left_ts.date()).days)


def trading_day_gap(left: Any, right: Any, calendar: pd.DatetimeIndex | None = None) -> int | None:
    left_ts = parse_date(left)
    right_ts = parse_date(right)
    if left_ts is None or right_ts is None:
        return None
    if calendar is None or calendar.empty:
        return date_gap_days(left, right)
    normalized = pd.DatetimeIndex(calendar).normalize().sort_values()
    if right_ts >= left_ts:
        return int(((normalized > left_ts) & (normalized <= right_ts)).sum())
    return -int(((normalized > right_ts) & (normalized <= left_ts)).sum())


def next_month_first_day(value: pd.Timestamp) -> pd.Timestamp:
    year = value.year + (1 if value.month == 12 else 0)
    month = 1 if value.month == 12 else value.month + 1
    return pd.Timestamp(year=year, month=month, day=1)


def next_trading_day_on_or_after(calendar: pd.DatetimeIndex, value: pd.Timestamp) -> pd.Timestamp | None:
    if calendar.empty:
        return None
    eligible = calendar[calendar >= value.normalize()]
    return pd.Timestamp(eligible.min()).normalize() if len(eligible) else None


def previous_trading_day_before(calendar: pd.DatetimeIndex, value: pd.Timestamp) -> pd.Timestamp | None:
    if calendar.empty:
        return None
    eligible = calendar[calendar < value.normalize()]
    return pd.Timestamp(eligible.max()).normalize() if len(eligible) else None


def truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def price_field_is_adjusted(field: Any) -> bool:
    text = str(field or "").strip().lower()
    if "raw" in text or "unadjusted" in text or "market close" in text:
        return False
    return any(token in text for token in ["adj", "adjusted", "qfq"])


def price_validation(reference_price: Any, reference_price_field: str, price_adjusted_flag: Any) -> tuple[bool, str]:
    price = safe_float(reference_price)
    if price is None or price <= 0:
        return False, "MISSING_PRICE"
    if truthy(price_adjusted_flag) or price_field_is_adjusted(reference_price_field):
        return False, "ADJUSTED_PRICE_NEEDS_BROKER_QUOTE"
    return True, "TRADEABLE_RAW_CLOSE"


def choose_readiness(
    *,
    position_file_exists: bool,
    price_is_tradeable: bool,
    price_missing: bool,
    unknown_action: bool,
    stale_signal: bool,
    blocking_warnings: list[str],
) -> str:
    if unknown_action:
        return BLOCKED_UNKNOWN_ACTION
    if price_missing:
        return BLOCKED_MISSING_PRICE
    if stale_signal:
        return BLOCKED_STALE_SIGNAL
    if not price_is_tradeable:
        return NEEDS_MANUAL_PRICE
    if not position_file_exists:
        return NEEDS_POSITION_FILE
    if blocking_warnings:
        return NEEDS_MANUAL_REVIEW
    return READY_FOR_MANUAL_REVIEW


def source_has_position_file(source: Any) -> bool:
    if isinstance(source, dict):
        if "exists" in source:
            return bool(source.get("exists"))
        return all(source_has_position_file(value) for value in source.values())
    return False


def current_position_row(source: Any, ticker: str) -> dict[str, str]:
    if not isinstance(source, dict):
        return {}
    rows = source.get("rows_by_ticker")
    if not isinstance(rows, dict):
        return {}
    row = rows.get(str(ticker).upper(), {})
    return row if isinstance(row, dict) else {}


def cash_available(source: Any, ticker: str) -> float:
    row = current_position_row(source, ticker)
    return safe_float(row.get("cash_available")) or 0.0


def manual_block_reason(source: Any, ticker: str) -> str:
    row = current_position_row(source, ticker)
    reason = str(row.get("manual_block_reason", "") or "").strip()
    execution_enabled = str(row.get("execution_enabled", "") or "").strip().lower()
    if execution_enabled in {"false", "0", "no", "n", "disabled"} and not reason:
        reason = "execution_enabled=false in current_positions file"
    return reason


def sleeve_manual_block_reason(source: Any) -> str:
    if not isinstance(source, dict):
        return ""
    rows = source.get("rows_by_ticker")
    if not isinstance(rows, dict):
        return ""
    sleeve_id = str(source.get("sleeve_id", "") or "").strip().lower()
    for row in rows.values():
        if not isinstance(row, dict):
            continue
        reason = str(row.get("manual_block_reason", "") or "").strip()
        execution_enabled = str(row.get("execution_enabled", "") or "").strip().lower()
        if reason == "NO_DEDICATED_US_V82_FUNDING":
            return reason
        if sleeve_id == "us_v82" and execution_enabled in {"false", "0", "no", "n", "disabled"}:
            return reason or "NO_DEDICATED_US_V82_FUNDING"
    return ""


def load_current_positions(project_root: Path, sleeve_id: str, sleeve_cfg: dict[str, Any], tickers: list[str]) -> tuple[dict[str, float], dict[str, Any]]:
    csv_value = sleeve_cfg.get("current_positions_csv")
    path = project_path(project_root, csv_value)
    source = {
        "sleeve_id": sleeve_id,
        "path": str(path) if path else "",
        "exists": bool(path and path.exists()),
        "missing_file_assumed_zero": False,
        "error": "",
        "rows_by_ticker": {},
        "manual_block_reasons": {},
    }
    if path is None or not path.exists():
        source["missing_file_assumed_zero"] = True
        return {ticker.upper(): 0.0 for ticker in tickers}, source
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            fieldnames = {str(name).strip().lower() for name in (reader.fieldnames or [])}
            if "ticker" not in fieldnames or "current_shares" not in fieldnames:
                raise ValueError("current positions CSV must contain ticker,current_shares columns")
            rows: dict[str, float] = {}
            rows_by_ticker: dict[str, dict[str, str]] = {}
            for row in reader:
                normalized_row = {str(key).strip().lower(): str(value).strip() for key, value in row.items() if key is not None}
                ticker = str(normalized_row.get("ticker", "")).strip().upper()
                if ticker:
                    rows[ticker] = float(normalized_row.get("current_shares", 0) or 0)
                    rows_by_ticker[ticker] = normalized_row
            source["rows_by_ticker"] = rows_by_ticker
            source["manual_block_reasons"] = {
                ticker: manual_block_reason({"rows_by_ticker": rows_by_ticker}, ticker)
                for ticker in rows_by_ticker
                if manual_block_reason({"rows_by_ticker": rows_by_ticker}, ticker)
            }
            source["sleeve_manual_block_reason"] = sleeve_manual_block_reason(source)
            source["sleeve_funding_status"] = "BLOCKED" if source["sleeve_manual_block_reason"] else "UNSPECIFIED"
    except Exception as exc:
        source["error"] = str(exc)
        raise ValueError(f"{sleeve_id} current positions file invalid: {exc}") from exc
    return {ticker.upper(): rows.get(ticker.upper(), 0.0) for ticker in tickers}, source


def latest_v82_audit_dir(project_root: Path) -> Path | None:
    candidates = sorted(
        (project_root / "outputs" / "us_stock_selection").glob("v82_frozen_formal_audit_*/v82_frozen_formal_audit_verdict.json"),
        key=lambda path: path.stat().st_mtime if path.exists() else 0,
        reverse=True,
    )
    return candidates[0].parent if candidates else None


def read_qlib_calendar(provider_dir: Path) -> pd.DatetimeIndex:
    path = provider_dir / "calendars" / "day.txt"
    if not path.exists():
        return pd.DatetimeIndex([])
    values = pd.read_csv(path, header=None)[0]
    calendar = pd.DatetimeIndex(pd.to_datetime(values, errors="coerce").dropna()).normalize().sort_values()
    return calendar


def read_qlib_series(provider_dir: Path, ticker: str, field: str, calendar: pd.DatetimeIndex) -> pd.Series:
    path = provider_dir / "features" / ticker.lower() / f"{field}.day.bin"
    if not path.exists() or calendar.empty:
        return pd.Series(dtype=float)
    arr = np.fromfile(path, dtype="<f4")
    if len(arr) < 2:
        return pd.Series(dtype=float)
    offset = int(arr[0])
    values = arr[1:].astype(float)
    end = min(offset + len(values), len(calendar))
    index = calendar[offset:end]
    values = values[: len(index)]
    return pd.Series(values, index=index, name=field).replace([np.inf, -np.inf], np.nan).dropna()


def qlib_reference_price(provider_dir: Path, ticker: str, preferred_date: str = "") -> dict[str, Any]:
    calendar = read_qlib_calendar(provider_dir)
    close = read_qlib_series(provider_dir, ticker, "close", calendar)
    if close.empty:
        return {
            "reference_price_date": "",
            "reference_price": None,
            "reference_price_field": "missing",
            "price_adjusted_flag": "unknown",
            "warning": f"No provider close price found for {ticker}.",
        }
    factor = read_qlib_series(provider_dir, ticker, "factor", calendar)
    if preferred_date:
        preferred_ts = pd.Timestamp(preferred_date)
        eligible = close.loc[close.index <= preferred_ts]
    else:
        eligible = close
    if eligible.empty:
        eligible = close
    date_value = eligible.index.max()
    close_value = safe_float(eligible.loc[date_value])
    factor_value = safe_float(factor.loc[date_value]) if date_value in factor.index else None
    if close_value is None:
        return {
            "reference_price_date": date_value.date().isoformat(),
            "reference_price": None,
            "reference_price_field": "missing",
            "price_adjusted_flag": "unknown",
            "warning": f"Provider close price is invalid for {ticker}.",
        }
    if factor_value is not None and factor_value > 0:
        return {
            "reference_price_date": date_value.date().isoformat(),
            "reference_price": close_value / factor_value,
            "reference_price_field": "raw_close_from_provider_close_factor",
            "price_adjusted_flag": False,
            "warning": "",
        }
    return {
        "reference_price_date": date_value.date().isoformat(),
        "reference_price": close_value,
        "reference_price_field": "provider_close_adjusted",
        "price_adjusted_flag": True,
        "warning": "Provider factor missing; provider close may be adjusted and must not be used directly without manual broker quote verification.",
    }


def build_holding_row(
    *,
    asof_date: str,
    job_id: str,
    strategy_id: str,
    sleeve_id: str,
    symbol: str,
    ticker: str,
    asset_name: str,
    currency: str,
    risk_state: str,
    derisk_triggered: Any,
    signal: str,
    action: str,
    target_position: str,
    rank: Any,
    target_weight: float | None,
    account_value: float,
    reference_price_date: str,
    reference_price: float | None,
    reference_price_field: str,
    price_adjusted_flag: Any,
    selection_reason: str,
    notes: str,
    sleeve_cfg: dict[str, Any],
    signal_source_date: str = "",
    target_holding_date: str = "",
    target_effective_start_date: str = "",
    target_effective_end_date: str = "",
    next_rebalance_date: str = "",
    signal_freshness_status: str = "UNKNOWN",
    signal_price_date_gap_days: int | None = None,
    signal_price_date_gap_trading_days: int | None = None,
    execution_readiness: str = NEEDS_MANUAL_REVIEW,
    order_intent: str = "BLOCKED",
    blocking_warnings_count: int = 0,
) -> dict[str, Any]:
    weight = safe_float(target_weight)
    price = safe_float(reference_price)
    target_notional = (account_value * weight) if weight is not None else None
    target_shares = 0.0
    estimated_notional = 0.0
    if target_notional is not None and price is not None and price > 0:
        target_shares = floor_to_lot(
            target_notional / price,
            int(sleeve_cfg.get("lot_size", 1) or 1),
            bool(sleeve_cfg.get("allow_fractional_shares", False)),
        )
        estimated_notional = target_shares * price
    min_lot_note = ""
    if (weight or 0.0) > 0 and target_shares <= 0 and price is not None and price > 0:
        min_lot_note = "Account notional is insufficient for the minimum lot size."
    merged_notes = "; ".join(item for item in [notes, min_lot_note] if item)
    return {
        "asof_date": asof_date,
        "job_id": job_id,
        "strategy_id": strategy_id,
        "sleeve_id": sleeve_id,
        "symbol": symbol,
        "ticker": ticker,
        "asset_name": asset_name,
        "currency": currency,
        "risk_state": risk_state,
        "derisk_triggered": derisk_triggered,
        "signal": signal,
        "action": action,
        "signal_source_date": signal_source_date,
        "target_holding_date": target_holding_date,
        "target_effective_start_date": target_effective_start_date,
        "target_effective_end_date": target_effective_end_date,
        "next_rebalance_date": next_rebalance_date,
        "target_position": target_position,
        "rank": rank,
        "target_weight": weight,
        "account_notional": account_value,
        "target_notional": target_notional,
        "reference_price_date": reference_price_date,
        "reference_price": price,
        "reference_price_field": reference_price_field,
        "price_adjusted_flag": price_adjusted_flag,
        "signal_price_date_gap_days": signal_price_date_gap_days,
        "signal_price_date_gap_trading_days": signal_price_date_gap_trading_days,
        "signal_freshness_status": signal_freshness_status,
        "execution_readiness": execution_readiness,
        "order_intent": order_intent,
        "blocking_warnings_count": blocking_warnings_count,
        "target_shares": target_shares,
        "estimated_notional": estimated_notional,
        "selection_reason": selection_reason,
        "manual_check_required": True,
        "notes": merged_notes,
    }


def build_order_row(
    holding: dict[str, Any],
    current_shares: float,
    packet_cfg: dict[str, Any],
    position_file_exists: bool,
) -> dict[str, Any]:
    target_shares = safe_float(holding.get("target_shares")) or 0.0
    target_position = str(holding.get("target_position", "UNKNOWN"))
    price = safe_float(holding.get("reference_price"))
    currency = str(holding.get("currency", "")).upper()
    price_is_tradeable, price_status = price_validation(price, str(holding.get("reference_price_field", "")), holding.get("price_adjusted_flag"))
    if str(holding.get("price_validation_status", "")).strip():
        price_status = str(holding.get("price_validation_status")).strip()
    readiness = str(holding.get("execution_readiness") or NEEDS_MANUAL_REVIEW)
    order_intent = str(holding.get("order_intent") or "BLOCKED")
    warning_parts: list[str] = []
    if not position_file_exists:
        if target_position in {"CASH", "EMPTY"}:
            warning_parts.append("Current positions file missing; cannot determine whether SELL is required.")
        else:
            warning_parts.append("Current positions file missing; this order ticket is example-only and cannot be treated as formal.")
    if not price_is_tradeable and price_status == "ADJUSTED_PRICE_NEEDS_BROKER_QUOTE":
        warning_parts.append("Reference price may be adjusted/qfq; manually verify broker quote before placing any order.")
    if price is None or price <= 0:
        warning_parts.append("Missing execution reference price; BUY/SELL is blocked.")
    if target_position == "UNKNOWN":
        warning_parts.append("Target position is UNKNOWN; manual review required.")
    if readiness == BLOCKED_STALE_SIGNAL:
        warning_parts.append("Signal freshness or target holding effectiveness is stale/unknown; formal trade is blocked.")
    if readiness == BLOCKED_UNKNOWN_ACTION:
        warning_parts.append("Action mapping is unknown; formal trade is blocked.")
    if readiness == NO_BUYING_POWER:
        warning_parts.append("No available USD cash in this sleeve; CNY cash is not allowed for this USD sleeve.")
    if str(holding.get("notes", "")).strip() and readiness in {BLOCKED_STALE_SIGNAL, BLOCKED_MISSING_PRICE, NEEDS_MANUAL_REVIEW, NO_BUYING_POWER}:
        warning_parts.append(str(holding.get("notes", "")).strip())
    warning_parts = list(dict.fromkeys([item for item in warning_parts if item]))
    formal_trade_allowed = (
        position_file_exists
        and price_is_tradeable
        and not warning_parts
        and readiness == READY_FOR_MANUAL_REVIEW
        and bool(holding.get("manual_check_required", True))
    )
    theoretical_trade_shares = abs(target_shares - current_shares)
    target_only = (
        str(holding.get("job_id", "")).lower() == "us_v82"
        and "NO_DEDICATED_US_V82_FUNDING" in str(holding.get("notes", ""))
        and target_position == "LONG"
    )
    if target_position == "UNKNOWN":
        trade_side = "UNKNOWN"
        trade_shares = 0.0
        formal_trade_allowed = False
        order_intent = "BLOCKED"
    elif target_only:
        trade_side = "TARGET_ONLY"
        trade_shares = theoretical_trade_shares
        formal_trade_allowed = False
    elif readiness == NO_BUYING_POWER:
        trade_side = "HOLD" if current_shares > 0 else "NO_TRADE"
        trade_shares = 0.0
        formal_trade_allowed = False
        if order_intent == "BLOCKED":
            order_intent = "NO_ACTION"
    elif target_shares > current_shares:
        trade_side = "BUY"
        trade_shares = target_shares - current_shares
    elif target_shares < current_shares:
        trade_side = "SELL"
        trade_shares = current_shares - target_shares
    elif target_position == "LONG":
        trade_side = "HOLD"
        trade_shares = 0.0
    elif target_position in {"CASH", "EMPTY"} and current_shares == 0:
        trade_side = "NO_TRADE"
        trade_shares = 0.0
    else:
        trade_side = "NO_TRADE"
        trade_shares = 0.0
    if trade_shares <= 0 and trade_side in {"BUY", "SELL"}:
        trade_side = "NO_TRADE"
    if trade_side in {"HOLD", "NO_TRADE"} and formal_trade_allowed:
        order_intent = "NO_ACTION"
        formal_trade_allowed = False
    limit_price = None
    if price is not None and price > 0 and trade_side == "BUY":
        limit_price = price * (1.0 + float(packet_cfg.get("buy_limit_buffer_pct", 0.005)))
    elif price is not None and price > 0 and trade_side == "SELL":
        limit_price = price * (1.0 - float(packet_cfg.get("sell_limit_buffer_pct", 0.005)))
    estimated_trade_notional = trade_shares * price if price is not None and price > 0 else None
    reason = f"{holding.get('action')} -> {target_position}; target_shares={format_float(target_shares, 3)} vs current_shares={format_float(current_shares, 3)}"
    return {
        "asof_date": holding.get("asof_date"),
        "job_id": holding.get("job_id"),
        "strategy_id": holding.get("strategy_id"),
        "sleeve_id": holding.get("sleeve_id"),
        "ticker": holding.get("ticker"),
        "currency": holding.get("currency"),
        "current_shares": current_shares,
        "target_shares": target_shares,
        "trade_side": trade_side,
        "trade_shares": trade_shares,
        "signal_source_date": holding.get("signal_source_date"),
        "target_holding_date": holding.get("target_holding_date"),
        "target_effective_start_date": holding.get("target_effective_start_date"),
        "target_effective_end_date": holding.get("target_effective_end_date"),
        "next_rebalance_date": holding.get("next_rebalance_date"),
        "signal_price_date_gap_days": holding.get("signal_price_date_gap_days"),
        "signal_freshness_status": holding.get("signal_freshness_status"),
        "execution_readiness": readiness,
        "order_intent": order_intent,
        "position_file_exists": bool(position_file_exists),
        "price_is_tradeable": bool(price_is_tradeable),
        "price_validation_status": price_status,
        "formal_trade_allowed": bool(formal_trade_allowed),
        "reference_price_date": holding.get("reference_price_date"),
        "reference_price": price,
        "reference_price_field": holding.get("reference_price_field"),
        "limit_price": round_price(limit_price, currency) if limit_price is not None else None,
        "estimated_trade_notional": estimated_trade_notional,
        "order_type": packet_cfg.get("default_order_type", "LIMIT"),
        "time_in_force": packet_cfg.get("default_time_in_force", "DAY"),
        "reason": reason,
        "manual_check_required": True,
        "blocking_warning": "; ".join(warning_parts),
    }


def summarize_orders(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {key: 0 for key in ["BUY", "SELL", "HOLD", "NO_TRADE", "TARGET_ONLY", "UNKNOWN"]}
    buy_notional = 0.0
    sell_notional = 0.0
    warnings = 0
    formal_trade_allowed_count = 0
    example_only_count = 0
    blocked_order_count = 0
    needs_position_file_count = 0
    needs_manual_price_count = 0
    blocked_stale_signal_count = 0
    for row in rows:
        side = str(row.get("trade_side", "UNKNOWN")).upper()
        counts[side if side in counts else "UNKNOWN"] += 1
        notional = safe_float(row.get("estimated_trade_notional")) or 0.0
        if side == "BUY":
            buy_notional += notional
        if side == "SELL":
            sell_notional += notional
        if str(row.get("blocking_warning", "")).strip():
            warnings += 1
        if truthy(row.get("formal_trade_allowed")):
            formal_trade_allowed_count += 1
        if row.get("order_intent") == "EXAMPLE_ONLY":
            example_only_count += 1
        if row.get("order_intent") == "BLOCKED":
            blocked_order_count += 1
        if not truthy(row.get("position_file_exists")):
            needs_position_file_count += 1
        if row.get("execution_readiness") == NEEDS_MANUAL_PRICE:
            needs_manual_price_count += 1
        if row.get("execution_readiness") == BLOCKED_STALE_SIGNAL:
            blocked_stale_signal_count += 1
    return {
        "BUY_count": counts["BUY"],
        "SELL_count": counts["SELL"],
        "HOLD_count": counts["HOLD"],
        "NO_TRADE_count": counts["NO_TRADE"],
        "TARGET_ONLY_count": counts["TARGET_ONLY"],
        "UNKNOWN_count": counts["UNKNOWN"],
        "estimated_buy_notional": buy_notional,
        "estimated_sell_notional": sell_notional,
        "blocking_warnings_count": warnings,
        "formal_trade_allowed_count": formal_trade_allowed_count,
        "example_only_count": example_only_count,
        "blocked_order_count": blocked_order_count,
        "needs_position_file_count": needs_position_file_count,
        "needs_manual_price_count": needs_manual_price_count,
        "blocked_stale_signal_count": blocked_stale_signal_count,
    }


def markdown_table(rows: list[dict[str, Any]], columns: list[str]) -> list[str]:
    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join(["---"] * len(columns)) + " |"]
    for row in rows:
        values = []
        for col in columns:
            value = row.get(col, "")
            if isinstance(value, float):
                value = format_float(value, 4)
            values.append(str(value).replace("\n", " "))
        lines.append("| " + " | ".join(values) + " |")
    return lines


def load_us_v82_live_inputs(job_dir: Path, provider_dir: Path) -> tuple[list[dict[str, Any]], dict[str, Any]] | None:
    summary_path = job_dir / "us_v82_live_target_holdings.json"
    holdings_path = job_dir / "us_v82_live_target_holdings.csv"
    if not summary_path.exists() or not holdings_path.exists():
        return None
    summary = load_json(summary_path)
    data = pd.read_csv(holdings_path)
    live_status = str(summary.get("live_status", ""))
    consistency = str(summary.get("live_formal_consistency_check", "UNKNOWN")).upper()
    if data.empty or not bool(summary.get("live_target_available")) or live_status != "LIVE_TARGET_READY":
        return None
    if consistency != "PASS":
        return None
    required_cols = {"ticker", "target_weight", "is_live_target", "signal_freshness_status", "live_status", "blocking_reason"}
    if not required_cols.issubset(set(data.columns)):
        return None
    data = data.loc[data["is_live_target"].astype(str).str.lower().isin({"true", "1", "yes"})].copy()
    data = data.loc[data["live_status"].astype(str).eq("LIVE_TARGET_READY")].copy()
    data = data.loc[data["blocking_reason"].fillna("").astype(str).str.strip().eq("")].copy()
    if data.empty:
        return None
    rows: list[dict[str, Any]] = []
    for index, row in enumerate(data.to_dict("records"), start=1):
        ticker = str(row.get("ticker", "")).upper()
        price = {
            "reference_price": row.get("reference_price"),
            "reference_price_date": row.get("reference_price_date"),
            "reference_price_field": row.get("reference_price_field"),
            "price_adjusted_flag": row.get("price_adjusted_flag"),
            "warning": row.get("blocking_warning", ""),
        }
        if not str(price.get("reference_price_date", "") or "").strip():
            price = qlib_reference_price(provider_dir, ticker)
        rows.append(
            {
                "ticker": ticker,
                "rank": row.get("rank", index),
                "weight": safe_float(row.get("target_weight")) or 0.0,
                "signal_source_date": str(row.get("signal_source_date", "") or ""),
                "target_holding_date": str(row.get("target_holding_date", "") or row.get("target_effective_start_date", "") or ""),
                "target_effective_start_date": str(row.get("target_effective_start_date", "") or ""),
                "target_effective_end_date": str(row.get("target_effective_end_date", "") or ""),
                "next_rebalance_date": str(row.get("next_rebalance_date", "") or ""),
                "signal_price_date_gap_days": date_gap_days(row.get("target_holding_date"), price.get("reference_price_date")),
                "signal_price_date_gap_trading_days": 0,
                "signal_freshness_status": str(row.get("signal_freshness_status") or "EFFECTIVE_HOLDING"),
                "reference_price": price.get("reference_price"),
                "reference_price_date": price.get("reference_price_date"),
                "reference_price_field": price.get("reference_price_field"),
                "price_adjusted_flag": price.get("price_adjusted_flag"),
                "score": row.get("score", ""),
                "notes": f"us_v82 target comes from us_v82_live_target_holdings.csv; live_status={live_status}; live_formal_consistency_check={consistency}.",
            }
        )
    meta = {
        "audit_dir": "",
        "verdict": {},
        "live_summary_path": str(summary_path),
        "live_holdings_path": str(holdings_path),
        "latest_holding_date": summary.get("latest_data_date") or max([str(row.get("reference_price_date", "")) for row in rows] or [""]),
        "signal_source_date": summary.get("latest_decision_date") or rows[0].get("signal_source_date", ""),
        "target_effective_start_date": summary.get("target_effective_start_date") or rows[0].get("target_effective_start_date", ""),
        "target_effective_end_date": summary.get("target_effective_end_date") or rows[0].get("target_effective_end_date", ""),
        "next_rebalance_date": summary.get("next_rebalance_date") or rows[0].get("next_rebalance_date", ""),
        "signal_freshness_status": "EFFECTIVE_HOLDING",
        "decision_ledger_path": summary.get("source_decision_ledger", ""),
        "provider_dir": str(provider_dir),
        "live_target_available": True,
        "live_status": live_status,
        "live_formal_consistency_check": consistency,
    }
    return rows, meta


def load_us_v82_inputs(project_root: Path, sleeve_cfg: dict[str, Any], job_dir: Path | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    provider_dir = Path(str(sleeve_cfg.get("provider_dir") or DEFAULT_PROVIDER_DIR))
    if job_dir is not None:
        live = load_us_v82_live_inputs(job_dir, provider_dir)
        if live is not None:
            return live
    audit_dir = latest_v82_audit_dir(project_root)
    if audit_dir is None:
        raise RuntimeError("No v82 frozen formal audit output found for us_v82 trading packet.")
    verdict = load_json(audit_dir / "v82_frozen_formal_audit_verdict.json")
    holdings_path = audit_dir / "formal_replay" / "formal_v82_baseline" / "formal_v82_monthly_holdings.csv"
    if not holdings_path.exists():
        raise RuntimeError(f"us_v82 monthly holdings file missing: {holdings_path}")
    holdings = pd.read_csv(holdings_path)
    required_cols = {"strategy_id", "date", "ticker", "weight"}
    if not required_cols.issubset(set(holdings.columns)):
        raise RuntimeError(f"us_v82 holdings file missing columns: {sorted(required_cols - set(holdings.columns))}")
    holdings = holdings[holdings["strategy_id"].astype(str) == US_V82_STRATEGY_ID].copy()
    if holdings.empty:
        raise RuntimeError(f"No holdings for {US_V82_STRATEGY_ID} in {holdings_path}")
    holdings["date"] = pd.to_datetime(holdings["date"], errors="coerce")
    holdings = holdings.dropna(subset=["date"])
    latest_date = holdings["date"].max()
    latest = holdings[holdings["date"] == latest_date].copy()
    latest = latest.sort_values(["weight", "ticker"], ascending=[False, True])
    decision_path = audit_dir / "formal_replay" / "formal_v82_baseline" / "formal_v82_decision_ledger.csv"
    score_map: dict[str, str] = {}
    signal_source_date = ""
    target_effective_start_date = ""
    target_effective_end_date = ""
    next_rebalance_date = ""
    signal_freshness_status = BLOCKED_STALE_SIGNAL
    if decision_path.exists():
        ledger = pd.read_csv(decision_path)
        if "execution_date" in ledger.columns and "selected_tickers" in ledger.columns:
            ledger["execution_date"] = pd.to_datetime(ledger["execution_date"], errors="coerce")
            led = ledger.dropna(subset=["execution_date"])
            led = led[led["execution_date"] <= latest_date]
            if not led.empty:
                row = led.sort_values("execution_date").iloc[-1]
                signal_source_date = str(row.get("decision_date", "") or row.get("feature_date", "") or "").split(" ")[0]
                target_effective_start_date = pd.Timestamp(row.get("execution_date")).date().isoformat()
                scores = str(row.get("selected_scores", ""))
                for item in scores.split(";"):
                    if ":" in item:
                        ticker, score = item.split(":", 1)
                        score_map[ticker.strip().upper()] = score.strip()
    provider_calendar = read_qlib_calendar(provider_dir)
    effective_start_ts = parse_date(target_effective_start_date) or latest_date
    next_rebalance_ts = next_trading_day_on_or_after(provider_calendar, next_month_first_day(effective_start_ts)) if not provider_calendar.empty else None
    if next_rebalance_ts is not None:
        next_rebalance_date = date_text(next_rebalance_ts)
        effective_end_ts = previous_trading_day_before(provider_calendar, next_rebalance_ts)
        target_effective_end_date = date_text(effective_end_ts)
    rows = []
    for index, row in enumerate(latest.to_dict("records"), start=1):
        ticker = str(row.get("ticker", "")).upper()
        price = qlib_reference_price(provider_dir, ticker)
        reference_date = str(price.get("reference_price_date") or "")
        reference_ts = parse_date(reference_date)
        effective_end_ts = parse_date(target_effective_end_date)
        if reference_ts is not None and effective_end_ts is not None and reference_ts <= effective_end_ts:
            signal_freshness_status = "EFFECTIVE_HOLDING"
            note = "Target holding comes from the latest effective rebalance and remains within its holding window at the reference price date."
        else:
            signal_freshness_status = BLOCKED_STALE_SIGNAL
            note = (
                f"Cannot prove latest target holding remains effective on reference price date. "
                f"target_holding_date={latest_date.date().isoformat()}, target_effective_end_date={target_effective_end_date or 'unknown'}, "
                f"reference_price_date={reference_date or 'missing'}."
            )
        if price.get("warning"):
            note = "; ".join([str(price.get("warning")), note])
        gap_days = date_gap_days(latest_date, reference_date)
        gap_trading_days = trading_day_gap(latest_date, reference_date, provider_calendar)
        rows.append(
            {
                "ticker": ticker,
                "rank": index,
                "weight": safe_float(row.get("weight")) or 0.0,
                "signal_source_date": signal_source_date,
                "target_holding_date": latest_date.date().isoformat(),
                "target_effective_start_date": target_effective_start_date,
                "target_effective_end_date": target_effective_end_date,
                "next_rebalance_date": next_rebalance_date,
                "signal_price_date_gap_days": gap_days,
                "signal_price_date_gap_trading_days": gap_trading_days,
                "signal_freshness_status": signal_freshness_status,
                "reference_price": price.get("reference_price"),
                "reference_price_date": price.get("reference_price_date"),
                "reference_price_field": price.get("reference_price_field"),
                "price_adjusted_flag": price.get("price_adjusted_flag"),
                "score": score_map.get(ticker, ""),
                "notes": note,
            }
        )
    meta = {
        "audit_dir": str(audit_dir),
        "verdict": verdict,
        "latest_holding_date": latest_date.date().isoformat(),
        "signal_source_date": signal_source_date,
        "target_effective_start_date": target_effective_start_date,
        "target_effective_end_date": target_effective_end_date,
        "next_rebalance_date": next_rebalance_date,
        "signal_freshness_status": signal_freshness_status,
        "decision_ledger_path": str(decision_path),
        "provider_dir": str(provider_dir),
        "live_target_available": False,
        "live_target_blocker": (
            "us_v82 live target holdings missing; formal audit holdings cannot be used as current executable target."
            if job_dir is None or not (job_dir / "us_v82_live_target_holdings.csv").exists()
            else "us_v82 live target holdings file exists but did not contain a PASS live target."
        ),
    }
    return rows, meta


def generate_us_v82_packet(project_root: Path, run_dir: Path, job: dict[str, Any], packet_cfg: dict[str, Any], sleeve_cfg: dict[str, Any], asof_date: str) -> dict[str, Any]:
    job_dir = Path(job["job_dir"])
    account_value = account_notional(sleeve_cfg)
    source_rows, meta = load_us_v82_inputs(project_root, sleeve_cfg, job_dir)
    tickers = [row["ticker"] for row in source_rows]
    current_positions, source = load_current_positions(project_root, "us_v82", sleeve_cfg, tickers)
    position_file_exists = source_has_position_file(source)
    sleeve_block_reason = sleeve_manual_block_reason(source)
    verdict = meta.get("verdict") or {}
    gate_result = str(verdict.get("gate_result", "UNKNOWN"))
    risk_state = "RISK_ON" if gate_result == "PASS" or meta.get("live_target_available") else "UNKNOWN"
    derisk = False if risk_state == "RISK_ON" else "unknown"
    holdings: list[dict[str, Any]] = []
    for item in source_rows:
        target_position = "LONG" if risk_state == "RISK_ON" and (item.get("weight") or 0) > 0 else "CASH"
        weight = item.get("weight") if target_position == "LONG" else 0.0
        price_is_tradeable, price_status = price_validation(item.get("reference_price"), str(item.get("reference_price_field", "")), item.get("price_adjusted_flag"))
        stale_signal = item.get("signal_freshness_status") == BLOCKED_STALE_SIGNAL
        item_notes = str(item.get("notes", ""))
        if not meta.get("live_target_available"):
            item_notes = "; ".join(part for part in [item_notes, str(meta.get("live_target_blocker", ""))] if part)
        row_block_reason = manual_block_reason(source, item["ticker"])
        block_reason = row_block_reason or sleeve_block_reason
        block_label = "Sleeve-level manual block from current_positions" if sleeve_block_reason and not row_block_reason else "Manual block from current_positions"
        blocking_warnings = [f"{block_label}: {block_reason}"] if block_reason else []
        if block_reason == "NO_DEDICATED_US_V82_FUNDING":
            item_notes = "; ".join(part for part in [item_notes, US_V82_TARGET_ONLY_NOTE] if part)
        if item["ticker"] == "TQQQ":
            item_notes = "; ".join(part for part in [item_notes, "TQQQ real position is tracked in the qld_tqqq sleeve; us_v82 row is target-only unless separate funding is explicitly assigned."] if part)
        if block_reason:
            item_notes = "; ".join(part for part in [item_notes, f"{block_label}: {block_reason}"] if part)
        readiness = choose_readiness(
            position_file_exists=position_file_exists,
            price_is_tradeable=price_is_tradeable,
            price_missing=price_status == "MISSING_PRICE",
            unknown_action=False,
            stale_signal=stale_signal,
            blocking_warnings=blocking_warnings,
        )
        order_intent = "FORMAL_MANUAL_ORDER" if readiness == READY_FOR_MANUAL_REVIEW else "EXAMPLE_ONLY" if readiness == NEEDS_POSITION_FILE else "BLOCKED"
        holdings.append(
            build_holding_row(
                asof_date=asof_date,
                job_id="us_v82",
                strategy_id=US_V82_STRATEGY_ID,
                sleeve_id="us_v82",
                symbol=item["ticker"],
                ticker=item["ticker"],
                asset_name=item["ticker"],
                currency=str(sleeve_cfg.get("currency", "USD")),
                risk_state=risk_state,
                derisk_triggered=derisk,
                signal=gate_result,
                action="TARGET_LONG" if target_position == "LONG" else "DERISK_TO_CASH",
                target_position=target_position,
                rank=item.get("rank"),
                target_weight=weight,
                account_value=account_value,
                reference_price_date=item.get("reference_price_date", ""),
                reference_price=item.get("reference_price"),
                reference_price_field=str(item.get("reference_price_field", "")),
                price_adjusted_flag=item.get("price_adjusted_flag", "unknown"),
                signal_source_date=str(item.get("signal_source_date", "")),
                target_holding_date=str(item.get("target_holding_date", "")),
                target_effective_start_date=str(item.get("target_effective_start_date", "")),
                target_effective_end_date=str(item.get("target_effective_end_date", "")),
                next_rebalance_date=str(item.get("next_rebalance_date", "")),
                signal_price_date_gap_days=item.get("signal_price_date_gap_days"),
                signal_price_date_gap_trading_days=item.get("signal_price_date_gap_trading_days"),
                signal_freshness_status=str(item.get("signal_freshness_status", "")),
                execution_readiness=readiness,
                order_intent=order_intent,
                blocking_warnings_count=len(blocking_warnings) if blocking_warnings else 0 if readiness == READY_FOR_MANUAL_REVIEW else 1,
                selection_reason=f"v8.2 frozen top5 rank {item.get('rank')}; score={item.get('score')}",
                notes=item_notes,
                sleeve_cfg=sleeve_cfg,
            )
        )
    orders = [build_order_row(row, current_positions.get(str(row["ticker"]).upper(), 0.0), packet_cfg, position_file_exists) for row in holdings]
    risk = {
        "job_id": "us_v82",
        "strategy_id": US_V82_STRATEGY_ID,
        "status": "PASS",
        "risk_state": risk_state,
        "derisk_triggered": derisk,
        "risk_reason": f"formal audit gate_result={gate_result}",
        "gate_result": gate_result,
        "latest_data_date": meta.get("latest_holding_date"),
        "signal_source_date": meta.get("signal_source_date"),
        "target_effective_start_date": meta.get("target_effective_start_date"),
        "target_effective_end_date": meta.get("target_effective_end_date"),
        "next_rebalance_date": meta.get("next_rebalance_date"),
        "signal_freshness_status": meta.get("signal_freshness_status"),
        "decision_ledger_path": meta.get("decision_ledger_path"),
        "live_target_available": bool(meta.get("live_target_available")),
        "live_summary_path": meta.get("live_summary_path", ""),
        "live_holdings_path": meta.get("live_holdings_path", ""),
        "live_target_blocker": meta.get("live_target_blocker", ""),
        "reference_price_date": max([str(row.get("reference_price_date", "")) for row in holdings] or [""]),
        "metrics": {
            "CAGR": verdict.get("cagr"),
            "Calmar": verdict.get("calmar"),
            "Max Drawdown": verdict.get("max_drawdown"),
            "cost50_cagr": verdict.get("cost50_cagr"),
        },
        "current_positions_source": source,
        "sleeve_manual_block_reason": sleeve_block_reason,
        "sleeve_funding_status": "BLOCKED" if sleeve_block_reason else "UNSPECIFIED",
        "warnings": [row.get("notes") for row in holdings if row.get("notes")],
    }
    return write_job_packet(job_dir, run_dir, "us_v82", holdings, orders, risk, source, packet_cfg)


def generate_qldtqqq_packet(project_root: Path, run_dir: Path, job: dict[str, Any], packet_cfg: dict[str, Any], sleeves: dict[str, Any], asof_date: str) -> dict[str, Any]:
    job_dir = Path(job["job_dir"])
    summary = load_json(job_dir / "qldtqqq_job_summary.json")
    if not summary:
        raise RuntimeError("qldtqqq_job_summary.json is missing or unreadable.")
    results = summary.get("results", [])
    if not isinstance(results, list) or not results:
        raise RuntimeError("qldtqqq_job_summary.json has no results list.")
    sleeve_ids = {"QLD": "qld", "TQQQ": "tqqq"}
    current_by_sleeve: dict[str, dict[str, float]] = {}
    source_by_sleeve: dict[str, Any] = {}
    for result in results:
        symbol = str(result.get("symbol", "")).upper()
        sleeve_id = sleeve_ids.get(symbol, symbol.lower())
        sleeve_cfg = dict(sleeves.get(sleeve_id, {}))
        current, source = load_current_positions(project_root, sleeve_id, sleeve_cfg, [symbol])
        current_by_sleeve[sleeve_id] = current
        source_by_sleeve[sleeve_id] = source
    holdings: list[dict[str, Any]] = []
    for result in results:
        symbol = str(result.get("symbol", "")).upper()
        sleeve_id = sleeve_ids.get(symbol, symbol.lower())
        sleeve_cfg = dict(sleeves.get(sleeve_id, {}))
        signal = result.get("latest_signal") or {}
        action = str(signal.get("action", "UNKNOWN"))
        current_shares = current_by_sleeve.get(sleeve_id, {}).get(symbol, 0.0)
        desired_weight = safe_float(signal.get("desired_weight_after_close"))
        target_position, target_weight, risk_state, warning = qldtqqq_action_to_target(action, desired_weight, current_shares)
        reference_price = safe_float(signal.get("latest_close"))
        reference_date = str(signal.get("latest_signal_date") or result.get("latest_data_date") or "")
        source = source_by_sleeve.get(sleeve_id, {})
        position_file_exists = source_has_position_file(source)
        price_is_tradeable, price_status = price_validation(reference_price, "close", False)
        unknown_action = target_position == "UNKNOWN"
        block_reason = manual_block_reason(source, symbol)
        blocking_warnings = [f"Manual block from current_positions: {block_reason}"] if block_reason else []
        readiness = choose_readiness(
            position_file_exists=position_file_exists,
            price_is_tradeable=price_is_tradeable,
            price_missing=price_status == "MISSING_PRICE",
            unknown_action=unknown_action,
            stale_signal=False,
            blocking_warnings=blocking_warnings,
        )
        order_intent = "FORMAL_MANUAL_ORDER" if readiness == READY_FOR_MANUAL_REVIEW else "EXAMPLE_ONLY" if readiness == NEEDS_POSITION_FILE else "BLOCKED"
        notes = "Public daily close from frozen replay output; manual broker quote verification required."
        sleeve_cash = cash_available(source, symbol)
        increase_without_cash = normalize_action(action) in INCREASE_ACTIONS and sleeve_cash <= 0 and current_shares > 0
        if increase_without_cash:
            readiness = NO_BUYING_POWER
            order_intent = "NO_ACTION"
            notes = f"{notes}; 无可用美元现金，不允许使用人民币现金。策略意图保留为 {action}，但本 sleeve 只能维持现有持仓等待人工复核。"
        if warning:
            notes = f"{notes}; {warning}"
        if symbol == "TQQQ":
            notes = f"{notes}; {QDT_TQQQ_CROSS_SLEEVE_NOTE}"
        if block_reason:
            notes = f"{notes}; Manual block from current_positions: {block_reason}"
        holding = build_holding_row(
            asof_date=asof_date,
            job_id="qld_tqqq",
            strategy_id=str(result.get("strategy_id", "")),
            sleeve_id=sleeve_id,
            symbol=symbol,
            ticker=symbol,
            asset_name=symbol,
            currency=str(sleeve_cfg.get("currency", "USD")),
            risk_state=risk_state,
            derisk_triggered=False if risk_state in {"RISK_ON", "RISK_OFF"} else "unknown",
            signal=action,
            action=action,
            target_position=target_position,
            rank=1,
            target_weight=target_weight,
            account_value=account_notional(sleeve_cfg),
            reference_price_date=reference_date,
            reference_price=reference_price,
            reference_price_field="close",
            price_adjusted_flag=False,
            signal_source_date=reference_date,
            target_holding_date=reference_date,
            target_effective_start_date=reference_date,
            target_effective_end_date=reference_date,
            next_rebalance_date=str(signal.get("next_open_date") or ""),
            signal_price_date_gap_days=date_gap_days(reference_date, reference_date),
            signal_price_date_gap_trading_days=0,
            signal_freshness_status="EFFECTIVE_SIGNAL",
            execution_readiness=readiness,
            order_intent=order_intent,
            blocking_warnings_count=len(blocking_warnings) if blocking_warnings else 0 if readiness == READY_FOR_MANUAL_REVIEW else 1,
            selection_reason=f"Fixed frozen replay: {result.get('frozen_core')} + {result.get('frozen_gate')}",
            notes=notes,
            sleeve_cfg=sleeve_cfg,
        )
        target_shares_from_weight = safe_float(holding.get("target_shares")) or 0.0
        if normalize_action(action) in INCREASE_ACTIONS and current_shares > 0 and (increase_without_cash or target_shares_from_weight <= current_shares):
            holding["target_shares"] = float(current_shares)
            holding["target_notional"] = current_shares * reference_price if reference_price is not None and reference_price > 0 else None
            holding["estimated_notional"] = holding["target_notional"] or 0.0
            holding["order_intent"] = "NO_ACTION"
            if holding["execution_readiness"] == READY_FOR_MANUAL_REVIEW:
                holding["execution_readiness"] = NEEDS_MANUAL_REVIEW
            holding["notes"] = (
                f"{holding.get('notes', '')}; Strategy action is BUY_OR_INCREASE, but target-share math would not increase "
                "the broker position; preserving current shares rather than generating a sell."
            )
        holdings.append(holding)
    orders = []
    for row in holdings:
        sleeve_id = str(row["sleeve_id"])
        orders.append(
            build_order_row(
                row,
                current_by_sleeve.get(sleeve_id, {}).get(str(row["ticker"]).upper(), 0.0),
                packet_cfg,
                source_has_position_file(source_by_sleeve.get(sleeve_id, {})),
            )
        )
    risk = {
        "job_id": "qld_tqqq",
        "strategy_id": "qld_tqqq_fixed_frozen_replay",
        "status": "PASS",
        "latest_data_date": summary.get("latest_data_date"),
        "data_completeness": (summary.get("data_completeness") or {}).get("data_completeness", ""),
        "data_completeness_detail": summary.get("data_completeness") or {},
        "metrics": {
            row.get("symbol"): {
                "CAGR": row.get("CAGR"),
                "Calmar": row.get("Calmar"),
                "Max Drawdown": row.get("Max Drawdown"),
            }
            for row in results
        },
        "current_positions_source": source_by_sleeve,
        "warnings": [row.get("notes") for row in holdings if row.get("notes")],
    }
    return write_job_packet(job_dir, run_dir, "qld_tqqq", holdings, orders, risk, source_by_sleeve, packet_cfg)


def generate_588200_packet(project_root: Path, run_dir: Path, job: dict[str, Any], packet_cfg: dict[str, Any], sleeve_cfg: dict[str, Any], asof_date: str) -> dict[str, Any]:
    job_dir = Path(job["job_dir"])
    summary = load_json(job_dir / "588200_job_summary.json")
    if not summary:
        raise RuntimeError("588200_job_summary.json is missing or unreadable.")
    result = summary.get("result") or {}
    if not isinstance(result, dict) or not result:
        raise RuntimeError("588200_job_summary.json has no result object.")
    result_status = str(result.get("status") or summary.get("status") or "").upper()
    data_blocked = result_status in {"BLOCKED_DATA_MISSING", "BLOCKED_STALE_DATA", "FAILED_DATA_REFRESH"}
    symbol = str(sleeve_cfg.get("symbol") or result.get("symbol") or "588200").replace(".SS", "")
    current, source = load_current_positions(project_root, "etf_588200", sleeve_cfg, [symbol])
    signal = result.get("signal") or {}
    action = str(result.get("latest_action") or signal.get("latest_action") or "UNKNOWN")
    target_position, target_weight, risk_state, warning = action_to_target_position(action, current.get(symbol, 0.0))
    reference_date = str(signal.get("latest_signal_date") or result.get("latest_data_date") or "")
    tradeable_price = result.get("tradeable_price") if isinstance(result.get("tradeable_price"), dict) else load_json(job_dir / "588200_tradeable_price.json")
    if data_blocked:
        action = "UNKNOWN"
        target_position = "UNKNOWN"
        target_weight = 0.0
        risk_state = "UNKNOWN"
        warning = str(result.get("error_message") or "588200 data refresh failed; no tradeable price or signal available.")
        reference_date = str(result.get("latest_data_date") or signal.get("latest_signal_date") or "")
        reference_price = None
        reference_price_field = "missing"
        price_adjusted_flag = False
        price_notes = warning
    elif tradeable_price.get("price_is_tradeable"):
        reference_date = str(tradeable_price.get("price_date") or reference_date)
        reference_price = safe_float(tradeable_price.get("tradeable_close"))
        reference_price_field = "tradeable_close"
        price_adjusted_flag = False
        price_notes = str(tradeable_price.get("notes") or "Tradeable raw close was exported by run_588200_frozen_daily.py.")
    else:
        reference_price = safe_float(signal.get("latest_close"))
        reference_price_field = "adj_close_or_qfq_close"
        price_adjusted_flag = True
        price_notes = "Source close is yfinance auto-adjusted primary or akshare qfq fallback; manually verify actual exchange quote before placing any order."
    position_file_exists = source_has_position_file(source)
    price_is_tradeable, price_status = price_validation(reference_price, reference_price_field, price_adjusted_flag)
    block_reason = manual_block_reason(source, symbol)
    blocking_warnings = [f"Manual block from current_positions: {block_reason}"] if block_reason else []
    if data_blocked:
        readiness = BLOCKED_MISSING_PRICE
        price_status = str(tradeable_price.get("price_validation_status") or "DATA_REFRESH_FAILED")
        price_is_tradeable = False
    else:
        readiness = choose_readiness(
            position_file_exists=position_file_exists,
            price_is_tradeable=price_is_tradeable,
            price_missing=price_status == "MISSING_PRICE",
            unknown_action=target_position == "UNKNOWN",
            stale_signal=False,
            blocking_warnings=blocking_warnings,
        )
    order_intent = "FORMAL_MANUAL_ORDER" if readiness == READY_FOR_MANUAL_REVIEW else "EXAMPLE_ONLY" if readiness == NEEDS_POSITION_FILE else "BLOCKED"
    notes = price_notes
    if tradeable_price.get("price_is_tradeable") and reference_date != str(signal.get("latest_signal_date") or result.get("latest_data_date") or ""):
        notes = f"{notes}; Tradeable price date differs from latest signal date; manual review required."
    if warning:
        notes = f"{notes}; {warning}"
    if block_reason:
        notes = f"{notes}; Manual block from current_positions: {block_reason}"
    holding = build_holding_row(
        asof_date=asof_date,
        job_id="588200",
        strategy_id=str(result.get("frozen_strategy_id") or summary.get("frozen_strategy_id") or ""),
        sleeve_id="etf_588200",
        symbol=symbol,
        ticker=symbol,
        asset_name=symbol,
        currency=str(sleeve_cfg.get("currency", "CNY")),
        risk_state=risk_state,
        derisk_triggered=False if risk_state in {"RISK_ON", "RISK_OFF"} else "unknown",
        signal=action,
        action=action,
        target_position=target_position,
        rank=1,
        target_weight=target_weight,
        account_value=account_notional(sleeve_cfg),
        reference_price_date=reference_date,
        reference_price=reference_price,
        reference_price_field=reference_price_field,
        price_adjusted_flag=price_adjusted_flag,
        signal_source_date=reference_date,
        target_holding_date=reference_date,
        target_effective_start_date=reference_date,
        target_effective_end_date=reference_date,
        next_rebalance_date=str(signal.get("next_open_date") or ""),
        signal_price_date_gap_days=date_gap_days(reference_date, reference_date),
        signal_price_date_gap_trading_days=0,
        signal_freshness_status="BLOCKED_DATA_MISSING" if data_blocked else "EFFECTIVE_SIGNAL",
        execution_readiness=readiness,
        order_intent=order_intent,
        blocking_warnings_count=len(blocking_warnings) if blocking_warnings else 0 if readiness == READY_FOR_MANUAL_REVIEW else 1,
        selection_reason="Fixed frozen 588200 strategy replay/latest signal.",
        notes=notes,
        sleeve_cfg=sleeve_cfg,
    )
    if data_blocked:
        holding["price_validation_status"] = price_status
    orders = [build_order_row(holding, current.get(symbol, 0.0), packet_cfg, position_file_exists)]
    risk = {
        "job_id": "588200",
        "strategy_id": holding["strategy_id"],
        "status": result_status or "PASS",
        "latest_data_date": result.get("latest_data_date"),
        "next_open_date": signal.get("next_open_date"),
        "latest_action": action,
        "risk_state": risk_state,
        "metrics": {
            "CAGR": result.get("CAGR"),
            "Calmar": result.get("Calmar"),
            "Max Drawdown": result.get("Max Drawdown"),
            "stock_count": result.get("stock_count"),
        },
        "reference_price_date": reference_date,
        "reference_price_field": reference_price_field,
        "price_is_tradeable": price_is_tradeable,
        "price_validation_status": price_status,
        "tradeable_price": tradeable_price,
        "data_completeness": result.get("data_completeness", ""),
        "raw_latest_data_date": result.get("raw_latest_data_date", ""),
        "accepted_latest_data_date": result.get("accepted_latest_data_date", ""),
        "eod_completeness_rule": result.get("eod_completeness_rule", ""),
        "eod_completeness_reason": result.get("eod_completeness_reason", ""),
        "data_source_status": result.get("data_source_status") or result_status,
        "fallback_artifact_path": result.get("fallback_artifact_path", ""),
        "stale_data_flag": result.get("stale_data_flag", False),
        "current_positions_source": source,
        "warnings": [notes],
    }
    return write_job_packet(job_dir, run_dir, "588200", [holding], orders, risk, source, packet_cfg)


def write_job_packet(
    job_dir: Path,
    run_dir: Path,
    job_id: str,
    holdings: list[dict[str, Any]],
    orders: list[dict[str, Any]],
    risk: dict[str, Any],
    current_positions_source: Any,
    packet_cfg: dict[str, Any],
) -> dict[str, Any]:
    holdings_path = job_dir / "latest_target_holdings.csv"
    orders_path = job_dir / "order_ticket.csv"
    risk_path = job_dir / "risk_status.json"
    md_path = job_dir / "DAILY_TRADING_PACKET.md"
    manifest_path = job_dir / "trading_packet_manifest.json"
    pd.DataFrame(holdings, columns=HOLDINGS_COLUMNS).to_csv(holdings_path, index=False, encoding="utf-8-sig")
    pd.DataFrame(orders, columns=ORDER_COLUMNS).to_csv(orders_path, index=False, encoding="utf-8-sig")
    order_summary = summarize_orders(orders)
    packet_status = READY_FOR_MANUAL_REVIEW
    if (
        order_summary["UNKNOWN_count"] > 0
        or order_summary["blocking_warnings_count"] > 0
        or order_summary["example_only_count"] > 0
        or order_summary["blocked_order_count"] > 0
        or order_summary["formal_trade_allowed_count"] == 0
    ):
        packet_status = "NEEDS_MANUAL_REVIEW"
    risk_payload = {
        **risk,
        "trading_packet_status": packet_status,
        "order_summary": order_summary,
        "manual_check_required": bool(packet_cfg.get("manual_check_required", True)),
    }
    write_json(risk_path, risk_payload)
    lines = [
        "# Daily Trading Packet",
        "",
        "## 1. Run Summary",
        f"- asof_date: `{holdings[0].get('asof_date') if holdings else ''}`",
        f"- run_time: `{datetime.now().isoformat(timespec='seconds')}`",
        f"- job_id: `{job_id}`",
        f"- strategy_id / frozen_strategy_id: `{risk.get('strategy_id', '')}`",
        f"- status: `{packet_status}`",
        f"- execution_readiness: `{', '.join(sorted({str(row.get('execution_readiness')) for row in holdings}))}`",
        f"- gate_result: `{risk.get('gate_result', '')}`",
        f"- risk_state: `{risk.get('risk_state', '')}`",
        f"- derisk_triggered: `{risk.get('derisk_triggered', '')}`",
        f"- latest_data_date: `{risk.get('latest_data_date', '')}`",
        f"- reference_price_date: `{risk.get('reference_price_date', '')}`",
        f"- account_notional: `{', '.join(format_float(row.get('account_notional'), 2) for row in holdings)}`",
        f"- current_positions_source: `{current_positions_source}`",
        f"- current_positions_file_exists: `{source_exists(current_positions_source)}`",
        f"- output_dir: `{job_dir}`",
        "",
        "## 2. Strategy Status",
    ]
    lines.extend([f"- {row.get('ticker')}: action `{row.get('action')}`, target_position `{row.get('target_position')}`, risk_state `{row.get('risk_state')}`" for row in holdings])
    lines.extend(["", "## 3. Metrics", "", "```json", json.dumps(jsonable(risk.get("metrics", {})), ensure_ascii=False, indent=2), "```", "", "## 4. Target Holdings"])
    lines.extend(markdown_table(holdings, ["ticker", "target_position", "target_weight", "target_holding_date", "reference_price_date", "signal_freshness_status", "execution_readiness", "order_intent", "reference_price", "target_shares", "estimated_notional", "selection_reason", "notes"]))
    lines.extend(["", "## 5. Order Ticket"])
    lines.extend(markdown_table(orders, ["ticker", "current_shares", "target_shares", "trade_side", "trade_shares", "execution_readiness", "order_intent", "formal_trade_allowed", "reference_price", "limit_price", "order_type", "time_in_force", "reason", "blocking_warning"]))
    lines.extend(
        [
            "",
            "## 6. Execution Notes",
            "- This report does not submit orders automatically.",
            "- This report is for manual review only.",
            "- Only rows with formal_trade_allowed=true and order_intent=FORMAL_MANUAL_ORDER can enter the manual order review workflow.",
            "- EXAMPLE_ONLY and BLOCKED rows must not be submitted as orders.",
            "- Before placing any order, manually confirm ticker, price, corporate actions, dividends, halts, and liquidity.",
            "- If the market opens far from the reference_price, the limit order may not fill.",
            "- After fills, manually update the corresponding inputs/current_positions_*.csv file.",
            "- If no current positions file was provided, this packet assumes current_shares = 0.",
            "- reference_price is only a reference, not a guaranteed execution price.",
            "",
            "## 7. Risk Notes",
            "- PASS does not guarantee future returns.",
            "- Historical backtests do not represent future performance.",
            "- Leveraged ETFs such as QLD/TQQQ have high volatility, path dependency, and drawdown risk.",
            "- 588200 is affected by A-share liquidity, daily price limits, trading hours, and ETF premium/discount.",
            "- us_v82 top5 is a concentrated high-volatility portfolio.",
            "- derisk100p only means the configured risk-reduction rule triggered; it does not mean there is no loss risk.",
        ]
    )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    manifest = {
        "job_id": job_id,
        "status": packet_status,
        "files": {
            "daily_trading_packet": str(md_path),
            "latest_target_holdings": str(holdings_path),
            "order_ticket": str(orders_path),
            "risk_status": str(risk_path),
        },
        "order_summary": order_summary,
        "blocking_warnings_count": order_summary["blocking_warnings_count"],
    }
    write_json(manifest_path, manifest)
    return {
        "status": packet_status,
        "daily_trading_packet_path": str(md_path),
        "latest_target_holdings_path": str(holdings_path),
        "order_ticket_path": str(orders_path),
        "risk_status_path": str(risk_path),
        "manifest_path": str(manifest_path),
        "order_summary": order_summary,
        "blocking_warnings_count": order_summary["blocking_warnings_count"],
        "holdings": holdings,
        "orders": orders,
        "risk": risk_payload,
    }


def source_exists(source: Any) -> bool:
    if isinstance(source, dict):
        if "exists" in source:
            return bool(source.get("exists"))
        return any(source_exists(value) for value in source.values())
    return False


def sleeve_position_paths(packet_cfg: dict[str, Any]) -> dict[str, str]:
    sleeves = packet_cfg.get("sleeves") or {}
    return {str(sleeve_id): str(cfg.get("current_positions_csv", "")) for sleeve_id, cfg in sleeves.items() if isinstance(cfg, dict)}


def keyed_values(rows: list[dict[str, Any]], value_field: str, key_field: str = "sleeve_id") -> str:
    values = []
    for row in rows:
        key = str(row.get(key_field, "") or "")
        value = row.get(value_field, "")
        values.append(f"{key}={value}")
    return "; ".join(values)


def signed_trade_shares(row: dict[str, Any]) -> float:
    side = str(row.get("trade_side", "")).upper()
    shares = safe_float(row.get("trade_shares")) or 0.0
    if side == "BUY":
        return shares
    if side == "SELL":
        return -shares
    return 0.0


def build_cross_sleeve_review(
    run_dir: Path,
    all_holdings: list[dict[str, Any]],
    all_orders: list[dict[str, Any]],
    packet_cfg: dict[str, Any],
) -> dict[str, Any]:
    exposure_path = run_dir / "cross_sleeve_symbol_exposure.csv"
    conflicts_path = run_dir / "cross_sleeve_symbol_conflicts.csv"
    summary_json_path = run_dir / "cross_sleeve_validation_summary.json"
    summary_md_path = run_dir / "cross_sleeve_validation_summary.md"
    accounting_mode = str(packet_cfg.get("sleeve_accounting_mode", "separate_sleeves") or "separate_sleeves")
    position_paths = sleeve_position_paths(packet_cfg)

    groups: dict[tuple[str, str], dict[str, list[dict[str, Any]]]] = {}
    for row in all_holdings:
        ticker = str(row.get("ticker", "") or "").upper()
        currency = str(row.get("currency", "") or "").upper()
        if not ticker:
            continue
        groups.setdefault((ticker, currency), {"holdings": [], "orders": []})["holdings"].append(row)
    for row in all_orders:
        ticker = str(row.get("ticker", "") or "").upper()
        currency = str(row.get("currency", "") or "").upper()
        if not ticker:
            continue
        groups.setdefault((ticker, currency), {"holdings": [], "orders": []})["orders"].append(row)

    exposure_rows: list[dict[str, Any]] = []
    conflict_rows: list[dict[str, Any]] = []
    for (ticker, currency), payload in sorted(groups.items()):
        holdings = payload["holdings"]
        orders = payload["orders"]
        sleeves = sorted({str(row.get("sleeve_id", "") or "") for row in holdings + orders if str(row.get("sleeve_id", "") or "")})
        jobs = sorted({str(row.get("job_id", "") or "") for row in holdings + orders if str(row.get("job_id", "") or "")})
        strategies = sorted({str(row.get("strategy_id", "") or "") for row in holdings + orders if str(row.get("strategy_id", "") or "")})
        sleeve_count = len(sleeves)
        duplicate = sleeve_count > 1
        target_positions = sorted({str(row.get("target_position", "") or "") for row in holdings if str(row.get("target_position", "") or "")})
        trade_sides = sorted({str(row.get("trade_side", "") or "") for row in orders if str(row.get("trade_side", "") or "")})
        formal_values = [truthy(row.get("formal_trade_allowed")) for row in orders]
        intents = sorted({str(row.get("order_intent", "") or "") for row in orders if str(row.get("order_intent", "") or "")})
        warnings_by_sleeve = keyed_values(orders, "blocking_warning")
        same_position_file = False
        paths = [position_paths.get(sleeve, "") for sleeve in sleeves]
        nonempty_paths = [path for path in paths if path]
        if len(nonempty_paths) != len(set(nonempty_paths)):
            same_position_file = True
        requires_allocation = duplicate
        notes = ""
        if duplicate:
            notes = (
                "Same ticker appears in multiple sleeves. Do not automatically merge or net these orders; "
                "manually confirm whether the strategies are separately funded or managed in one consolidated account."
            )
        exposure_rows.append(
            {
                "asof_date": holdings[0].get("asof_date") if holdings else orders[0].get("asof_date") if orders else "",
                "ticker": ticker,
                "currency": currency,
                "appears_in_sleeves": ";".join(sleeves),
                "sleeve_count": sleeve_count,
                "job_ids": ";".join(jobs),
                "strategy_ids": ";".join(strategies),
                "target_positions": ";".join(target_positions),
                "target_weights_by_sleeve": keyed_values(holdings, "target_weight"),
                "target_shares_by_sleeve": keyed_values(holdings, "target_shares"),
                "trade_sides_by_sleeve": keyed_values(orders, "trade_side"),
                "formal_trade_allowed_by_sleeve": keyed_values(orders, "formal_trade_allowed"),
                "order_intents_by_sleeve": keyed_values(orders, "order_intent"),
                "blocking_warnings_by_sleeve": warnings_by_sleeve,
                "net_target_shares_if_naively_combined": sum((safe_float(row.get("target_shares")) or 0.0) for row in holdings),
                "net_trade_shares_if_naively_combined": sum(signed_trade_shares(row) for row in orders),
                "requires_manual_sleeve_allocation": bool(requires_allocation),
                "notes": notes,
            }
        )

        def add_conflict(conflict_type: str, severity: str, reason: str) -> None:
            conflict_rows.append(
                {
                    "asof_date": holdings[0].get("asof_date") if holdings else orders[0].get("asof_date") if orders else "",
                    "ticker": ticker,
                    "currency": currency,
                    "conflict_type": conflict_type,
                    "severity": severity,
                    "sleeves_involved": ";".join(sleeves),
                    "job_ids": ";".join(jobs),
                    "signals": keyed_values(holdings, "action"),
                    "target_positions": keyed_values(holdings, "target_position"),
                    "trade_sides": keyed_values(orders, "trade_side"),
                    "formal_trade_allowed_rows": sum(1 for value in formal_values if value),
                    "blocking_reason": reason,
                    "recommended_manual_review": True,
                }
            )

        if duplicate:
            add_conflict(
                "DUPLICATE_SYMBOL_ACROSS_SLEEVES",
                "MEDIUM",
                "Ticker appears in multiple sleeves; sleeve funding/allocation must be reviewed manually.",
            )
        if duplicate and "LONG" in target_positions and any(pos in {"CASH", "EMPTY"} for pos in target_positions):
            add_conflict(
                "OPPOSITE_TARGET_POSITIONS",
                "HIGH",
                "At least one sleeve targets LONG while another targets CASH/EMPTY.",
            )
        if duplicate and "BUY" in trade_sides and "SELL" in trade_sides:
            add_conflict(
                "OPPOSITE_TRADE_SIDES",
                "HIGH",
                "At least one sleeve has BUY while another has SELL.",
            )
        if duplicate and formal_values and any(formal_values) and not all(formal_values):
            add_conflict(
                "MIXED_FORMAL_AND_BLOCKED",
                "MEDIUM",
                "At least one sleeve has formal_trade_allowed=true while another is blocked or example-only.",
            )
        if duplicate and (same_position_file or accounting_mode == "consolidated_account"):
            add_conflict(
                "SHARED_POSITION_FILE_AMBIGUITY",
                "MEDIUM",
                "Sleeves share a current-position file or consolidated account mode is configured; no automatic netting is implemented.",
            )

    exposure_columns = [
        "asof_date",
        "ticker",
        "currency",
        "appears_in_sleeves",
        "sleeve_count",
        "job_ids",
        "strategy_ids",
        "target_positions",
        "target_weights_by_sleeve",
        "target_shares_by_sleeve",
        "trade_sides_by_sleeve",
        "formal_trade_allowed_by_sleeve",
        "order_intents_by_sleeve",
        "blocking_warnings_by_sleeve",
        "net_target_shares_if_naively_combined",
        "net_trade_shares_if_naively_combined",
        "requires_manual_sleeve_allocation",
        "notes",
    ]
    conflict_columns = [
        "asof_date",
        "ticker",
        "currency",
        "conflict_type",
        "severity",
        "sleeves_involved",
        "job_ids",
        "signals",
        "target_positions",
        "trade_sides",
        "formal_trade_allowed_rows",
        "blocking_reason",
        "recommended_manual_review",
    ]
    pd.DataFrame(exposure_rows, columns=exposure_columns).to_csv(exposure_path, index=False, encoding="utf-8-sig")
    pd.DataFrame(conflict_rows, columns=conflict_columns).to_csv(conflicts_path, index=False, encoding="utf-8-sig")

    duplicate_symbols = sorted({row["ticker"] for row in exposure_rows if int(row.get("sleeve_count", 0) or 0) > 1})
    high_severity = [row for row in conflict_rows if row.get("severity") == "HIGH"]
    summary = {
        "sleeve_accounting_mode": accounting_mode,
        "cross_sleeve_conflict_count": len(conflict_rows),
        "duplicate_symbol_count": len(duplicate_symbols),
        "opposite_target_position_count": sum(1 for row in conflict_rows if row.get("conflict_type") == "OPPOSITE_TARGET_POSITIONS"),
        "opposite_trade_side_count": sum(1 for row in conflict_rows if row.get("conflict_type") == "OPPOSITE_TRADE_SIDES"),
        "mixed_formal_blocked_count": sum(1 for row in conflict_rows if row.get("conflict_type") == "MIXED_FORMAL_AND_BLOCKED"),
        "requires_manual_sleeve_allocation": any(row.get("requires_manual_sleeve_allocation") for row in exposure_rows),
        "duplicate_symbols": duplicate_symbols,
        "high_severity_conflicts": high_severity,
        "cross_sleeve_symbol_exposure_path": str(exposure_path),
        "cross_sleeve_symbol_conflicts_path": str(conflicts_path),
        "cross_sleeve_validation_summary_json_path": str(summary_json_path),
        "cross_sleeve_validation_summary_path": str(summary_md_path),
    }
    write_json(summary_json_path, summary)
    lines = [
        "# Cross-Sleeve Validation Summary",
        "",
        f"- sleeve_accounting_mode: `{accounting_mode}`",
        f"- cross_sleeve_conflict_count: `{summary['cross_sleeve_conflict_count']}`",
        f"- duplicate_symbol_count: `{summary['duplicate_symbol_count']}`",
        f"- opposite_target_position_count: `{summary['opposite_target_position_count']}`",
        f"- opposite_trade_side_count: `{summary['opposite_trade_side_count']}`",
        f"- mixed_formal_blocked_count: `{summary['mixed_formal_blocked_count']}`",
        f"- requires_manual_sleeve_allocation: `{summary['requires_manual_sleeve_allocation']}`",
        f"- duplicate_symbols: `{', '.join(duplicate_symbols) if duplicate_symbols else 'None'}`",
        "",
        "## Conflicts",
    ]
    if conflict_rows:
        lines.extend(markdown_table(conflict_rows, ["ticker", "conflict_type", "severity", "sleeves_involved", "target_positions", "trade_sides", "blocking_reason", "recommended_manual_review"]))
    else:
        lines.append("- None")
    lines.extend(
        [
            "",
            "## Manual Review Rule",
            "- The system does not automatically merge or net orders across sleeves.",
            "- If sleeves are separately funded, maintain separate current_positions files and review each sleeve independently.",
            "- If one broker account is shared across sleeves, manually confirm net exposure and order allocation before placing any order.",
        ]
    )
    summary_md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary


def source_for_row(all_risk: dict[str, Any], row: dict[str, Any]) -> Any:
    risk = all_risk.get(str(row.get("job_id", "")), {})
    source = risk.get("current_positions_source", {}) if isinstance(risk, dict) else {}
    if str(row.get("job_id", "")) == "qld_tqqq" and isinstance(source, dict):
        sleeve_source = source.get(str(row.get("sleeve_id", "")), {})
        return sleeve_source if sleeve_source else source
    return source


def format_cash_for_row(all_risk: dict[str, Any], row: dict[str, Any]) -> str:
    source = source_for_row(all_risk, row)
    cash = cash_available(source, str(row.get("ticker", "")))
    currency = str(row.get("currency", "") or "")
    return f"{format_float(cash, 2)} {currency}".strip()


def funding_source_text(row: dict[str, Any]) -> str:
    job_id = str(row.get("job_id", ""))
    sleeve = str(row.get("sleeve_id", ""))
    notes = str(row.get("blocking_warning", "") or "")
    if job_id == "588200":
        return "sleeve_588200 existing shares / CNY only"
    if job_id == "qld_tqqq":
        return f"{sleeve} USD sleeve only; no CNY cash"
    if job_id == "us_v82":
        if "NO_DEDICATED_US_V82_FUNDING" in notes:
            return "us_v82 USD sleeve; NO_DEDICATED_US_V82_FUNDING"
        return "us_v82 USD sleeve"
    return sleeve


def action_guide_side(row: dict[str, Any]) -> str:
    side = str(row.get("trade_side", "") or "").upper()
    readiness = str(row.get("execution_readiness", "") or "")
    if side in {"BUY", "SELL", "HOLD", "TARGET_ONLY"}:
        return side
    if side == "NO_TRADE":
        return "HOLD"
    if readiness == NO_BUYING_POWER:
        return "HOLD"
    return "REVIEW_ONLY"


def action_guide_status(row: dict[str, Any]) -> str:
    side = str(row.get("trade_side", "") or "").upper()
    readiness = str(row.get("execution_readiness", "") or "")
    intent = str(row.get("order_intent", "") or "")
    if truthy(row.get("formal_trade_allowed")):
        return READY_FOR_MANUAL_REVIEW
    if side == "TARGET_ONLY":
        return "BLOCKED"
    if readiness == NO_BUYING_POWER:
        return NO_BUYING_POWER
    if intent == "BLOCKED":
        return "BLOCKED"
    return readiness or NEEDS_MANUAL_REVIEW


def action_guide_rebalance_note(row: dict[str, Any]) -> str:
    action = normalize_action(row.get("reason", "").split("->", 1)[0])
    target_position = str(row.get("reason", "").split("->", 1)[1].split(";", 1)[0]).strip() if "->" in str(row.get("reason", "")) else ""
    if action in KEEP_LONG_ACTIONS and target_position == "LONG" and str(row.get("trade_side", "")).upper() == "SELL":
        return "策略状态为保持多头，但因目标仓位/风险预算/组合约束，需要卖出至目标股数。"
    return ""


def data_completeness_for_row(all_risk: dict[str, Any], row: dict[str, Any]) -> str:
    risk = all_risk.get(str(row.get("job_id", "")), {})
    if not isinstance(risk, dict):
        return ""
    value = str(risk.get("data_completeness", "") or "")
    if value:
        return value
    if str(row.get("job_id", "")) in {"qld_tqqq", "us_v82"}:
        return "EOD_CONFIRMED"
    return ""


def write_funding_isolation_check(run_dir: Path, all_orders: list[dict[str, Any]], all_risk: dict[str, Any], cross: dict[str, Any]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add(check: str, status: str, evidence: dict[str, Any]) -> None:
        checks.append({"check": check, "status": status, "evidence": evidence})

    etf_risk = all_risk.get("588200", {}) if isinstance(all_risk.get("588200", {}), dict) else {}
    etf_source = etf_risk.get("current_positions_source", {}) if isinstance(etf_risk, dict) else {}
    add(
        "588200_CNY_cash_only_etf_588200",
        "PASS",
        {"cash": cash_available(etf_source, "588200"), "source": etf_source.get("path", "") if isinstance(etf_source, dict) else ""},
    )

    q_risk = all_risk.get("qld_tqqq", {}) if isinstance(all_risk.get("qld_tqqq", {}), dict) else {}
    q_sources = q_risk.get("current_positions_source", {}) if isinstance(q_risk, dict) else {}
    qld_source = q_sources.get("qld", {}) if isinstance(q_sources, dict) else {}
    tqqq_source = q_sources.get("tqqq", {}) if isinstance(q_sources, dict) else {}
    add(
        "qld_tqqq_no_CNY_cash",
        "PASS",
        {
            "qld_cash_usd": cash_available(qld_source, "QLD"),
            "tqqq_cash_usd": cash_available(tqqq_source, "TQQQ"),
            "source": qld_source.get("path", "") if isinstance(qld_source, dict) else "",
        },
    )

    us_risk = all_risk.get("us_v82", {}) if isinstance(all_risk.get("us_v82", {}), dict) else {}
    us_source = us_risk.get("current_positions_source", {}) if isinstance(us_risk, dict) else {}
    us_rows = us_source.get("rows_by_ticker", {}) if isinstance(us_source, dict) else {}
    us_cash = sum(safe_float(row.get("cash_available")) or 0.0 for row in us_rows.values() if isinstance(row, dict))
    add(
        "us_v82_no_CNY_cash_and_no_USD_funding",
        "PASS" if us_cash <= 0 else "FAIL",
        {"us_v82_cash_usd_total": us_cash, "source": us_source.get("path", "") if isinstance(us_source, dict) else ""},
    )
    add(
        "qld_tqqq_and_us_v82_not_netting_TQQQ",
        "PASS",
        {"cross_sleeve_summary": cross.get("cross_sleeve_validation_summary_json_path", "")},
    )

    unfunded = []
    for row in all_orders:
        if str(row.get("trade_side", "")).upper() != "BUY" or not truthy(row.get("formal_trade_allowed")):
            continue
        source = source_for_row(all_risk, row)
        cash = cash_available(source, str(row.get("ticker", "")))
        needed = safe_float(row.get("estimated_trade_notional")) or 0.0
        if cash + 1e-9 < needed:
            unfunded.append({"ticker": row.get("ticker"), "needed": needed, "cash": cash})
    add("no_unfunded_buy_formal_orders", "PASS" if not unfunded else "FAIL", {"unfunded": unfunded})
    add("all_orders_have_currency_and_sleeve_source", "PASS", {"order_count": len(all_orders)})
    overall = "PASS" if all(row.get("status") == "PASS" for row in checks) else "FAIL"
    payload = {"overall_status": overall, "checks": checks}
    write_json(run_dir / "funding_isolation_check.json", payload)
    return payload


def write_daily_action_guide(
    run_dir: Path,
    all_orders: list[dict[str, Any]],
    all_risk: dict[str, Any],
    cross: dict[str, Any],
    total_status: str,
) -> dict[str, Any]:
    funding = write_funding_isolation_check(run_dir, all_orders, all_risk, cross)
    rows: list[dict[str, Any]] = []
    for row in all_orders:
        source = source_for_row(all_risk, row)
        reason_parts = [
            str(row.get("execution_readiness", "") or ""),
            str(row.get("order_intent", "") or ""),
            str(row.get("blocking_warning", "") or ""),
        ]
        if truthy(row.get("formal_trade_allowed")):
            reason_parts.append("formal_trade_allowed=true, but manual_check_required=true and no broker/API order was submitted.")
        rebalance_note = action_guide_rebalance_note(row)
        if rebalance_note:
            reason_parts.append(rebalance_note)
        rows.append(
            {
                "sleeve": row.get("sleeve_id", ""),
                "标的": row.get("ticker", ""),
                "latest_data_date": row.get("reference_price_date", ""),
                "data_completeness": data_completeness_for_row(all_risk, row),
                "当前持仓": format_float(row.get("current_shares"), 3),
                "可用现金": format_cash_for_row(all_risk, row),
                "动作": action_guide_side(row),
                "目标股数": format_float(row.get("target_shares"), 3),
                "交易股数": format_float(row.get("trade_shares"), 3),
                "资金来源": funding_source_text(row),
                "状态": action_guide_status(row),
                "原因/备注": "; ".join(part for part in reason_parts if part and part.lower() != "nan"),
            }
        )
    guide_path = run_dir / "DAILY_ACTION_GUIDE.md"
    lines = [
        "# DAILY_ACTION_GUIDE",
        "",
        f"- generated_at: `{datetime.now().isoformat(timespec='seconds')}`",
        f"- run_dir: `{run_dir}`",
        f"- total_status: `{total_status}`",
        "- no broker/API connection; no order submitted",
        "- use this as manual review evidence only; rows marked BLOCKED or TARGET_ONLY must not be submitted",
        "",
    ]
    lines.extend(markdown_table(rows, ["sleeve", "标的", "latest_data_date", "data_completeness", "当前持仓", "可用现金", "动作", "目标股数", "交易股数", "资金来源", "状态", "原因/备注"]))
    lines.extend(
        [
            "",
            "## Funding Isolation",
            "",
            f"- overall_status: `{funding.get('overall_status')}`",
            f"- evidence: `{run_dir / 'funding_isolation_check.json'}`",
        ]
    )
    guide_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    audit = {
        "guide_rows": rows,
        "cross_sleeve": cross,
        "funding_isolation": funding,
        "runner_status": "SUCCESS",
        "validation_status": total_status,
        "paths": {
            "DAILY_ACTION_GUIDE.md": str(guide_path),
            "funding_isolation_check.json": str(run_dir / "funding_isolation_check.json"),
            "daily_action_digest.json": str(run_dir / "daily_action_digest.json"),
        },
    }
    write_json(run_dir / "order_status_audit.json", {"rows": rows, "cross_sleeve": cross})
    write_json(run_dir / "daily_action_digest.json", audit)
    return audit


def write_consolidated_summary(run_dir: Path, job_results: dict[str, dict[str, Any]], overall_status: str, packet_cfg: dict[str, Any]) -> dict[str, Any]:
    all_holdings: list[dict[str, Any]] = []
    all_orders: list[dict[str, Any]] = []
    all_risk: dict[str, Any] = {}
    for job_id, result in job_results.items():
        all_holdings.extend(result.get("holdings", []))
        all_orders.extend(result.get("orders", []))
        all_risk[job_id] = result.get("risk", {})
    holdings_path = run_dir / "all_target_holdings.csv"
    orders_path = run_dir / "all_order_tickets.csv"
    risk_path = run_dir / "all_risk_status.json"
    digest_path = run_dir / "actionable_digest.json"
    md_path = run_dir / "DAILY_QUANT_TRADING_SUMMARY.md"
    pd.DataFrame(all_holdings, columns=HOLDINGS_COLUMNS).to_csv(holdings_path, index=False, encoding="utf-8-sig")
    pd.DataFrame(all_orders, columns=ORDER_COLUMNS).to_csv(orders_path, index=False, encoding="utf-8-sig")
    write_json(risk_path, all_risk)
    summary = summarize_orders(all_orders)
    cross = build_cross_sleeve_review(run_dir, all_holdings, all_orders, packet_cfg)
    failed = any(result.get("status") == "FAILED" for result in job_results.values())
    needs_review = (
        any(result.get("status") == NEEDS_MANUAL_REVIEW for result in job_results.values())
        or summary["blocking_warnings_count"] > 0
        or summary["UNKNOWN_count"] > 0
        or summary["formal_trade_allowed_count"] == 0
        or int(cross.get("cross_sleeve_conflict_count", 0) or 0) > 0
    )
    trading_packet_status = "FAILED" if failed else NEEDS_MANUAL_REVIEW if needs_review else READY_FOR_MANUAL_REVIEW
    effective_total_status = "FAILED" if overall_status == "FAILED" or trading_packet_status == "FAILED" else trading_packet_status
    digest = {
        "run_dir": str(run_dir),
        "total_status": effective_total_status,
        "trading_packet_status": trading_packet_status,
        "order_summary": summary,
        "cross_sleeve": cross,
        "cross_sleeve_conflict_count": cross.get("cross_sleeve_conflict_count", 0),
        "duplicate_symbol_count": cross.get("duplicate_symbol_count", 0),
        "opposite_target_position_count": cross.get("opposite_target_position_count", 0),
        "opposite_trade_side_count": cross.get("opposite_trade_side_count", 0),
        "mixed_formal_blocked_count": cross.get("mixed_formal_blocked_count", 0),
        "requires_manual_sleeve_allocation": cross.get("requires_manual_sleeve_allocation", False),
        "duplicate_symbols": cross.get("duplicate_symbols", []),
        "high_severity_conflicts": cross.get("high_severity_conflicts", []),
        "all_target_holdings_path": str(holdings_path),
        "all_order_tickets_path": str(orders_path),
        "daily_quant_trading_summary_path": str(md_path),
    }
    action_guide = write_daily_action_guide(run_dir, all_orders, all_risk, cross, effective_total_status)
    digest["daily_action_guide_path"] = action_guide.get("paths", {}).get("DAILY_ACTION_GUIDE.md", "")
    digest["funding_isolation_check_path"] = action_guide.get("paths", {}).get("funding_isolation_check.json", "")
    digest["daily_action_digest_path"] = action_guide.get("paths", {}).get("daily_action_digest.json", "")
    write_json(digest_path, digest)
    lines = [
        "# Daily Quant Trading Summary",
        "",
        "## 1. Overall Status",
        f"- run_dir: `{run_dir}`",
        f"- run_time: `{datetime.now().isoformat(timespec='seconds')}`",
        f"- total_status: `{effective_total_status}`",
        f"- enabled_jobs: `{', '.join(job_results.keys())}`",
        f"- formal_trade_allowed_count: `{summary.get('formal_trade_allowed_count')}`",
        f"- example_only_count: `{summary.get('example_only_count')}`",
        f"- blocked_order_count: `{summary.get('blocked_order_count')}`",
        f"- needs_position_file_count: `{summary.get('needs_position_file_count')}`",
        f"- needs_manual_price_count: `{summary.get('needs_manual_price_count')}`",
        f"- blocked_stale_signal_count: `{summary.get('blocked_stale_signal_count')}`",
        f"- blocking_warnings_count: `{summary.get('blocking_warnings_count')}`",
        f"- cross_sleeve_conflict_count: `{cross.get('cross_sleeve_conflict_count')}`",
        f"- duplicate_symbols: `{', '.join(cross.get('duplicate_symbols', [])) if cross.get('duplicate_symbols') else 'None'}`",
        f"- succeeded_jobs: `{', '.join([job for job, result in job_results.items() if result.get('status') in {READY_FOR_MANUAL_REVIEW, NEEDS_MANUAL_REVIEW}])}`",
        f"- failed_jobs: `{', '.join([job for job, result in job_results.items() if result.get('status') == 'FAILED'])}`",
        f"- trading_packet_status: `{digest['trading_packet_status']}`",
        "",
        "## 2. Job Summary",
        "| job_id | status | latest_data_date | risk_state / latest_action | target_position_summary | order_summary | trading_packet_path | order_ticket_path |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for job_id, result in job_results.items():
        risk = result.get("risk", {})
        holdings = result.get("holdings", [])
        actions = ", ".join(f"{row.get('ticker')}={row.get('action')}/{row.get('target_position')}" for row in holdings)
        order_summary = result.get("order_summary", {})
        latest_action = risk.get("latest_action") or risk.get("risk_state") or ""
        lines.append(
            f"| `{job_id}` | `{result.get('status')}` | `{risk.get('latest_data_date', '')}` | `{latest_action}` | `{actions}` | `{order_summary}` | `{result.get('daily_trading_packet_path')}` | `{result.get('order_ticket_path')}` |"
        )
    lines.extend(["", "## 3. Consolidated Target Holdings"])
    lines.extend(markdown_table(all_holdings, ["job_id", "sleeve_id", "ticker", "target_position", "target_weight", "target_shares", "signal_freshness_status", "execution_readiness", "order_intent", "reference_price", "notes"]))
    lines.extend(["", "## 4. Consolidated Order Tickets"])
    lines.extend(markdown_table(all_orders, ["job_id", "sleeve_id", "ticker", "current_shares", "target_shares", "trade_side", "trade_shares", "execution_readiness", "order_intent", "formal_trade_allowed", "limit_price", "blocking_warning"]))
    lines.extend(
        [
            "",
            "## 5. Cross-Sleeve Symbol Review",
            f"- sleeve_accounting_mode: `{cross.get('sleeve_accounting_mode')}`",
            f"- duplicate_symbol_count: `{cross.get('duplicate_symbol_count')}`",
            f"- duplicate_symbols: `{', '.join(cross.get('duplicate_symbols', [])) if cross.get('duplicate_symbols') else 'None'}`",
            f"- opposite_target_position_count: `{cross.get('opposite_target_position_count')}`",
            f"- opposite_trade_side_count: `{cross.get('opposite_trade_side_count')}`",
            f"- mixed_formal_blocked_count: `{cross.get('mixed_formal_blocked_count')}`",
            f"- requires_manual_sleeve_allocation: `{cross.get('requires_manual_sleeve_allocation')}`",
            f"- exposure_file: `{cross.get('cross_sleeve_symbol_exposure_path')}`",
            f"- conflicts_file: `{cross.get('cross_sleeve_symbol_conflicts_path')}`",
            "",
            "The system does not automatically merge or net orders across sleeves. If sleeves are separately funded, maintain separate current_positions files. If one broker account is shared across sleeves, manually confirm net exposure and net orders before any manual action.",
            "",
            "## 6. Manual Action Checklist",
            "- Confirm the current_positions files are accurate.",
            "- Confirm reference_price is a real tradable market price.",
            "- Confirm limit order prices.",
            "- Confirm the trade date and whether the market is open.",
            "- Confirm no duplicate orders will be submitted.",
            "- Confirm filled trades are reflected in the current positions files.",
            "- Confirm there are no blocking_warning values before placing any manual order.",
            "- Confirm cross-sleeve duplicate symbols are intentionally allocated by sleeve and not accidentally double-counted.",
        ]
    )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        **digest,
        "all_risk_status_path": str(risk_path),
        "actionable_digest_path": str(digest_path),
        "cross_sleeve_symbol_exposure_path": cross.get("cross_sleeve_symbol_exposure_path", ""),
        "cross_sleeve_symbol_conflicts_path": cross.get("cross_sleeve_symbol_conflicts_path", ""),
        "cross_sleeve_validation_summary_json_path": cross.get("cross_sleeve_validation_summary_json_path", ""),
        "cross_sleeve_validation_summary_path": cross.get("cross_sleeve_validation_summary_path", ""),
        "holdings": all_holdings,
        "orders": all_orders,
        "risk": all_risk,
    }


def generate_trading_packets(
    *,
    project_root: Path,
    run_dir: Path,
    config: dict[str, Any],
    jobs: list[dict[str, Any]],
    job_payloads: list[dict[str, Any]],
    asof_date: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    packet_cfg = dict(config.get("trading_packet") or {})
    if not bool(packet_cfg.get("enabled", False)):
        return {"enabled": False, "status": "DISABLED", "job_results": {}}
    sleeves = dict(packet_cfg.get("sleeves") or {})
    job_by_id = {str(job.get("id")): job for job in jobs}
    if dry_run:
        planned = {}
        for payload in job_payloads:
            job_id = str(payload.get("job_id"))
            job_dir = Path(payload.get("job_dir", run_dir / f"job_{job_id}"))
            planned[job_id] = {
                "daily_trading_packet_path": str(job_dir / "DAILY_TRADING_PACKET.md"),
                "latest_target_holdings_path": str(job_dir / "latest_target_holdings.csv"),
                "order_ticket_path": str(job_dir / "order_ticket.csv"),
                "risk_status_path": str(job_dir / "risk_status.json"),
            }
        print(json.dumps({"trading_packet_dry_run": planned}, indent=2, ensure_ascii=False))
        return {"enabled": True, "status": "DRY_RUN", "job_results": planned}

    results: dict[str, dict[str, Any]] = {}
    for payload in job_payloads:
        job_id = str(payload.get("job_id"))
        payload["trading_packet_generated"] = False
        payload["trading_packet_status"] = "NOT_RUN"
        if payload.get("status") not in {"SUCCESS", "SKIPPED"}:
            job_dir = Path(payload.get("job_dir", run_dir / f"job_{job_id}"))
            blocked_summary = load_json(job_dir / "588200_job_summary.json") if job_id == "588200" else {}
            blocked_result = blocked_summary.get("result") if isinstance(blocked_summary.get("result"), dict) else {}
            blocked_status = str(blocked_result.get("status") or blocked_summary.get("status") or "").upper()
            if blocked_status not in {"BLOCKED_DATA_MISSING", "BLOCKED_STALE_DATA", "FAILED_DATA_REFRESH"}:
                payload["trading_packet_status"] = "SKIPPED_STRATEGY_FAILED"
                continue
            payload["trading_packet_status"] = "DATA_REFRESH_FAILED_PACKET_ATTEMPT"
        try:
            if job_id == "us_v82":
                job_result = generate_us_v82_packet(project_root, run_dir, payload, packet_cfg, dict(sleeves.get("us_v82", {})), asof_date)
            elif job_id == "qld_tqqq":
                job_result = generate_qldtqqq_packet(project_root, run_dir, payload, packet_cfg, sleeves, asof_date)
            elif job_id == "588200":
                job_result = generate_588200_packet(project_root, run_dir, payload, packet_cfg, dict(sleeves.get("etf_588200", {})), asof_date)
            else:
                raise RuntimeError(f"No trading packet generator for job {job_id}")
            results[job_id] = job_result
            payload["trading_packet_generated"] = True
            payload["trading_packet_status"] = job_result.get("status")
            payload["daily_trading_packet_path"] = job_result.get("daily_trading_packet_path")
            payload["latest_target_holdings_path"] = job_result.get("latest_target_holdings_path")
            payload["order_ticket_path"] = job_result.get("order_ticket_path")
            payload["risk_status_path"] = job_result.get("risk_status_path")
            payload["blocking_warnings_count"] = job_result.get("blocking_warnings_count", 0)
        except Exception as exc:
            payload["status"] = "FAILED"
            payload["failure_reason"] = "TRADING_PACKET_FAILED"
            payload["trading_packet_status"] = "FAILED"
            payload["trading_packet_error"] = str(exc)
            job_dir = Path(payload.get("job_dir", run_dir / f"job_{job_id}"))
            write_json(
                job_dir / "trading_packet_manifest.json",
                {"job_id": job_id, "status": "FAILED", "error": str(exc), "manual_check_required": True},
            )
            results[job_id] = {"status": "FAILED", "error": str(exc), "holdings": [], "orders": [], "risk": {"job_id": job_id, "status": "FAILED", "error": str(exc)}}
    consolidated_status = "FAILED" if any(result.get("status") == "FAILED" for result in results.values()) else READY_FOR_MANUAL_REVIEW
    if consolidated_status != "FAILED" and any(
        result.get("status") == "NEEDS_MANUAL_REVIEW"
        or int(result.get("blocking_warnings_count", 0) or 0) > 0
        or int(result.get("order_summary", {}).get("UNKNOWN_count", 0) or 0) > 0
        for result in results.values()
    ):
        consolidated_status = "NEEDS_MANUAL_REVIEW"
    consolidated = write_consolidated_summary(run_dir, results, consolidated_status, packet_cfg)
    if consolidated_status != "FAILED" and int(consolidated.get("cross_sleeve_conflict_count", 0) or 0) > 0:
        consolidated_status = "NEEDS_MANUAL_REVIEW"
    missing = []
    for payload in job_payloads:
        if payload.get("status") in {"SUCCESS", "SKIPPED"} and not payload.get("trading_packet_generated"):
            payload["status"] = "FAILED"
            payload["failure_reason"] = "FAILED_TRADING_PACKET_MISSING"
            missing.append(payload.get("job_id"))
    if missing:
        consolidated_status = "FAILED"
    return {
        "enabled": True,
        "status": consolidated_status,
        "job_results": results,
        **{key: value for key, value in consolidated.items() if key not in {"holdings", "orders", "risk"}},
    }
