"""Validate daily trading packet safety gates.

The validator checks that generated order tickets are safe for human review.
It does not trade, connect brokers, read accounts, submit orders, search
strategies, commit, push, delete, or clean files.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = PROJECT_ROOT / "outputs" / "daily_quant_lab_runs"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate daily quant trading packet safety gates.")
    parser.add_argument("--run-dir", default="", help="Run directory to validate.")
    parser.add_argument("--latest", action="store_true", help="Validate the latest daily run directory with order tickets.")
    parser.add_argument("--strict", action="store_true", help="Return non-zero on validation rule violations.")
    return parser.parse_args()


def jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
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


def latest_run_dir() -> Path:
    candidates = sorted(
        [path for path in OUTPUT_ROOT.glob("20*") if path.is_dir() and (path / "all_order_tickets.csv").exists()],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise FileNotFoundError(f"No daily run with all_order_tickets.csv found under {OUTPUT_ROOT}")
    return candidates[0]


def truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def has_text(value: Any) -> bool:
    try:
        if pd.isna(value):
            return False
    except Exception:
        pass
    return str(value or "").strip() != ""


def field_is_adjusted(field: Any) -> bool:
    text = str(field or "").strip().lower()
    if "raw" in text or "unadjusted" in text or "market close" in text:
        return False
    return any(token in text for token in ["adj", "adjusted", "qfq"])


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def validate_order_row(row: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    warning = str(row.get("blocking_warning", "") or "").strip()
    formal = truthy(row.get("formal_trade_allowed"))
    price_adjusted = field_is_adjusted(row.get("reference_price_field"))
    position_exists = truthy(row.get("position_file_exists"))
    trade_side = str(row.get("trade_side", "")).upper()
    intent = str(row.get("order_intent", ""))
    readiness = str(row.get("execution_readiness", ""))
    freshness = str(row.get("signal_freshness_status", ""))
    manual_check = truthy(row.get("manual_check_required"))
    price_is_tradeable = truthy(row.get("price_is_tradeable"))
    reference_price = pd.to_numeric(pd.Series([row.get("reference_price")]), errors="coerce").iloc[0]
    reference_date = pd.to_datetime(row.get("reference_price_date"), errors="coerce")
    effective_start = pd.to_datetime(row.get("target_effective_start_date"), errors="coerce")
    effective_end = pd.to_datetime(row.get("target_effective_end_date"), errors="coerce")
    limit_price = pd.to_numeric(pd.Series([row.get("limit_price")]), errors="coerce").iloc[0]

    if warning and formal:
        errors.append("blocking_warning is non-empty but formal_trade_allowed is true")
    if price_adjusted and formal:
        errors.append("reference_price_field is adjusted/qfq but formal_trade_allowed is true")
    if not position_exists and formal:
        errors.append("current positions file is missing but formal_trade_allowed is true")
    if readiness == "BLOCKED_STALE_SIGNAL" and formal:
        errors.append("stale signal is formal_trade_allowed")
    if str(row.get("job_id", "")) == "us_v82" and formal:
        if pd.notna(effective_start) and pd.notna(reference_date) and reference_date < effective_start:
            errors.append("us_v82 reference_price_date is before target_effective_start_date but formal_trade_allowed is true")
        if pd.notna(effective_end) and pd.notna(reference_date) and effective_end < reference_date:
            errors.append("us_v82 target_effective_end_date is before reference_price_date but formal_trade_allowed is true")
    if str(row.get("job_id", "")) == "588200" and field_is_adjusted(row.get("reference_price_field")) and not price_is_tradeable and formal:
        errors.append("588200 adjusted/qfq reference price cannot be formal_trade_allowed")
    if trade_side in {"BUY", "SELL"} and not formal and intent == "FORMAL_MANUAL_ORDER":
        errors.append("BUY/SELL with formal_trade_allowed=false cannot be FORMAL_MANUAL_ORDER")
    if formal:
        if intent != "FORMAL_MANUAL_ORDER":
            errors.append("formal_trade_allowed requires order_intent=FORMAL_MANUAL_ORDER")
        if not position_exists:
            errors.append("formal_trade_allowed requires current positions file")
        if pd.isna(reference_price) or float(reference_price) <= 0:
            errors.append("formal_trade_allowed requires a positive reference_price")
        if not price_is_tradeable:
            errors.append("formal_trade_allowed requires price_is_tradeable")
        if warning:
            errors.append("formal_trade_allowed requires empty blocking_warning")
        if readiness not in {"READY_FOR_MANUAL_REVIEW"}:
            errors.append("formal_trade_allowed requires READY_FOR_MANUAL_REVIEW")
        if freshness not in {"EFFECTIVE_SIGNAL", "EFFECTIVE_HOLDING"}:
            errors.append("formal_trade_allowed requires EFFECTIVE_SIGNAL or EFFECTIVE_HOLDING")
        if not manual_check:
            errors.append("formal_trade_allowed requires manual_check_required")
        if trade_side not in {"BUY", "SELL", "HOLD", "NO_TRADE"}:
            errors.append("formal_trade_allowed has an invalid trade_side")
        if trade_side in {"BUY", "SELL"} and (pd.isna(limit_price) or float(limit_price) <= 0):
            errors.append("formal BUY/SELL requires a positive limit_price")
    return errors


def validate_run_dir(run_dir: Path, strict: bool = False) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    orders_path = run_dir / "all_order_tickets.csv"
    holdings_path = run_dir / "all_target_holdings.csv"
    orders = read_csv(orders_path)
    holdings = read_csv(holdings_path)
    errors: list[dict[str, Any]] = []
    warnings: list[str] = []

    if orders.empty:
        errors.append({"scope": "run", "message": f"Missing or empty all_order_tickets.csv: {orders_path}"})
    if holdings.empty:
        errors.append({"scope": "run", "message": f"Missing or empty all_target_holdings.csv: {holdings_path}"})

    for job_dir in sorted(run_dir.glob("job_*")):
        if not job_dir.is_dir():
            continue
        for required in ["DAILY_TRADING_PACKET.md", "order_ticket.csv", "latest_target_holdings.csv", "risk_status.json", "trading_packet_manifest.json"]:
            if not (job_dir / required).exists():
                errors.append({"scope": job_dir.name, "message": f"missing {required}"})
        if job_dir.name == "job_us_v82":
            live_summary = job_dir / "us_v82_live_target_holdings.json"
            live_holdings = job_dir / "us_v82_live_target_holdings.csv"
            us_orders = orders.loc[orders.get("job_id", pd.Series(dtype=object)).astype(str).eq("us_v82")] if not orders.empty and "job_id" in orders else pd.DataFrame()
            us_formal = int(us_orders.get("formal_trade_allowed", pd.Series(dtype=object)).map(truthy).sum()) if not us_orders.empty and "formal_trade_allowed" in us_orders else 0
            if us_formal > 0:
                if not live_summary.exists() or not live_holdings.exists():
                    errors.append({"scope": job_dir.name, "message": "us_v82 has formal_trade_allowed rows but live target holdings files are missing"})
                else:
                    try:
                        live_payload = json.loads(live_summary.read_text(encoding="utf-8"))
                    except Exception as exc:
                        errors.append({"scope": job_dir.name, "message": f"us_v82 live target summary unreadable: {exc}"})
                    else:
                        if not bool(live_payload.get("live_target_available")):
                            errors.append({"scope": job_dir.name, "message": "us_v82 has formal_trade_allowed rows but live_target_available is false"})
                        if str(live_payload.get("live_status", "")) != "LIVE_TARGET_READY":
                            errors.append({"scope": job_dir.name, "message": "us_v82 has formal_trade_allowed rows but live_status is not LIVE_TARGET_READY"})
                        if str(live_payload.get("live_formal_consistency_check", "UNKNOWN")).upper() != "PASS":
                            errors.append({"scope": job_dir.name, "message": "us_v82 has formal_trade_allowed rows but live_formal_consistency_check is not PASS"})
                    live_df = read_csv(live_holdings)
                    if live_df.empty:
                        errors.append({"scope": job_dir.name, "message": "us_v82 live holdings file is empty"})
                    elif us_formal > 0:
                        if "is_live_target" not in live_df.columns or not live_df["is_live_target"].astype(str).str.lower().isin({"true", "1", "yes"}).all():
                            errors.append({"scope": job_dir.name, "message": "us_v82 formal rows require all live holdings to be marked is_live_target=true"})
                        if "live_status" not in live_df.columns or not live_df["live_status"].astype(str).eq("LIVE_TARGET_READY").all():
                            errors.append({"scope": job_dir.name, "message": "us_v82 formal rows require live holdings live_status=LIVE_TARGET_READY"})
                        if "blocking_reason" not in live_df.columns or live_df["blocking_reason"].fillna("").astype(str).str.strip().ne("").any():
                            errors.append({"scope": job_dir.name, "message": "us_v82 formal rows require empty live holding blocking_reason"})

    for index, row in enumerate(orders.fillna("").to_dict("records")):
        row_errors = validate_order_row(row)
        for message in row_errors:
            errors.append({"scope": "order_ticket", "row_index": index, "ticker": row.get("ticker"), "message": message})

    formal_count = int(orders.get("formal_trade_allowed", pd.Series(dtype=object)).map(truthy).sum()) if not orders.empty and "formal_trade_allowed" in orders else 0
    example_only_count = int((orders.get("order_intent", pd.Series(dtype=object)) == "EXAMPLE_ONLY").sum()) if not orders.empty and "order_intent" in orders else 0
    blocked_count = int((orders.get("order_intent", pd.Series(dtype=object)) == "BLOCKED").sum()) if not orders.empty and "order_intent" in orders else 0
    needs_position_count = int(orders.get("position_file_exists", pd.Series(dtype=object)).map(lambda x: not truthy(x)).sum()) if not orders.empty and "position_file_exists" in orders else 0
    needs_manual_price_count = int((orders.get("execution_readiness", pd.Series(dtype=object)) == "NEEDS_MANUAL_PRICE").sum()) if not orders.empty and "execution_readiness" in orders else 0
    blocked_stale_count = int((orders.get("execution_readiness", pd.Series(dtype=object)) == "BLOCKED_STALE_SIGNAL").sum()) if not orders.empty and "execution_readiness" in orders else 0
    blocking_warning_count = int(orders.get("blocking_warning", pd.Series(dtype=object)).map(has_text).sum()) if not orders.empty and "blocking_warning" in orders else 0
    adjusted_price_warning_count = int(orders.get("reference_price_field", pd.Series(dtype=object)).map(field_is_adjusted).sum()) if not orders.empty and "reference_price_field" in orders else 0
    cross_path = run_dir / "cross_sleeve_validation_summary.json"
    cross_payload: dict[str, Any] = {}
    if cross_path.exists():
        try:
            raw_cross = json.loads(cross_path.read_text(encoding="utf-8"))
            cross_payload = raw_cross if isinstance(raw_cross, dict) else {}
        except Exception as exc:
            errors.append({"scope": "cross_sleeve", "message": f"cross_sleeve_validation_summary.json unreadable: {exc}"})
    cross_conflict_count = int(cross_payload.get("cross_sleeve_conflict_count", 0) or 0)
    duplicate_symbol_count = int(cross_payload.get("duplicate_symbol_count", 0) or 0)
    opposite_target_position_count = int(cross_payload.get("opposite_target_position_count", 0) or 0)
    opposite_trade_side_count = int(cross_payload.get("opposite_trade_side_count", 0) or 0)
    mixed_formal_blocked_count = int(cross_payload.get("mixed_formal_blocked_count", 0) or 0)
    requires_manual_sleeve_allocation = bool(cross_payload.get("requires_manual_sleeve_allocation", False))
    duplicate_symbols = list(cross_payload.get("duplicate_symbols", []) or [])
    high_severity_conflicts = list(cross_payload.get("high_severity_conflicts", []) or [])
    if cross_conflict_count > 0:
        warnings.append(
            "Cross-sleeve symbol conflicts require manual review; orders are not automatically merged or netted across sleeves."
        )
    if any(str(symbol).upper() == "TQQQ" for symbol in duplicate_symbols):
        warnings.append("TQQQ appears across multiple sleeves and requires manual sleeve allocation review.")

    validation_status = "FAILED" if errors else "READY_FOR_MANUAL_REVIEW" if formal_count > 0 and blocking_warning_count == 0 and cross_conflict_count == 0 else "NEEDS_MANUAL_REVIEW"
    if strict and validation_status == "FAILED":
        warnings.append("Strict mode: validation rule violations require a non-zero exit.")
    payload = {
        "run_dir": str(run_dir),
        "validated_at": datetime.now().isoformat(timespec="seconds"),
        "validation_status": validation_status,
        "strict": bool(strict),
        "formal_trade_allowed_count": formal_count,
        "example_only_count": example_only_count,
        "blocked_order_count": blocked_count,
        "needs_position_file_count": needs_position_count,
        "needs_manual_price_count": needs_manual_price_count,
        "blocked_stale_signal_count": blocked_stale_count,
        "blocking_warnings_count": blocking_warning_count,
        "adjusted_price_warning_count": adjusted_price_warning_count,
        "cross_sleeve_conflict_count": cross_conflict_count,
        "duplicate_symbol_count": duplicate_symbol_count,
        "opposite_target_position_count": opposite_target_position_count,
        "opposite_trade_side_count": opposite_trade_side_count,
        "mixed_formal_blocked_count": mixed_formal_blocked_count,
        "requires_manual_sleeve_allocation": requires_manual_sleeve_allocation,
        "duplicate_symbols": duplicate_symbols,
        "high_severity_conflicts": high_severity_conflicts,
        "cross_sleeve_validation_summary_path": str(cross_path) if cross_path.exists() else "",
        "errors": errors,
        "warnings": warnings,
    }
    write_json(run_dir / "validation_summary.json", payload)
    write_markdown(run_dir / "validation_summary.md", payload)
    return payload


def write_markdown(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# Trading Packet Validation Summary",
        "",
        f"- run_dir: `{payload.get('run_dir')}`",
        f"- validation_status: `{payload.get('validation_status')}`",
        f"- strict: `{payload.get('strict')}`",
        f"- formal_trade_allowed_count: `{payload.get('formal_trade_allowed_count')}`",
        f"- example_only_count: `{payload.get('example_only_count')}`",
        f"- blocked_order_count: `{payload.get('blocked_order_count')}`",
        f"- needs_position_file_count: `{payload.get('needs_position_file_count')}`",
        f"- needs_manual_price_count: `{payload.get('needs_manual_price_count')}`",
        f"- blocked_stale_signal_count: `{payload.get('blocked_stale_signal_count')}`",
        f"- blocking_warnings_count: `{payload.get('blocking_warnings_count')}`",
        f"- adjusted_price_warning_count: `{payload.get('adjusted_price_warning_count')}`",
        f"- cross_sleeve_conflict_count: `{payload.get('cross_sleeve_conflict_count')}`",
        f"- duplicate_symbol_count: `{payload.get('duplicate_symbol_count')}`",
        f"- opposite_target_position_count: `{payload.get('opposite_target_position_count')}`",
        f"- opposite_trade_side_count: `{payload.get('opposite_trade_side_count')}`",
        f"- mixed_formal_blocked_count: `{payload.get('mixed_formal_blocked_count')}`",
        f"- requires_manual_sleeve_allocation: `{payload.get('requires_manual_sleeve_allocation')}`",
        f"- duplicate_symbols: `{', '.join(payload.get('duplicate_symbols') or []) if payload.get('duplicate_symbols') else 'None'}`",
        "",
        "## Errors",
    ]
    if payload.get("errors"):
        lines.extend([f"- {item}" for item in payload["errors"]])
    else:
        lines.append("- None")
    lines.extend(["", "## Warnings"])
    if payload.get("warnings"):
        lines.extend([f"- {item}" for item in payload["warnings"]])
    else:
        lines.append("- None")
    lines.extend(
        [
            "",
            "## Safety Interpretation",
            "- `formal_trade_allowed_count > 0` only means the row may enter manual review; it is not automatic trading approval.",
            "- `EXAMPLE_ONLY` rows are assumptions, usually caused by missing current positions files.",
            "- `BLOCKED` rows must not be submitted until their blocker is resolved.",
            "- Any non-empty `blocking_warning` prevents formal manual order use.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    if args.latest:
        run_dir = latest_run_dir()
    elif args.run_dir:
        run_dir = Path(args.run_dir)
    else:
        raise SystemExit("--run-dir or --latest is required")
    payload = validate_run_dir(run_dir, strict=bool(args.strict))
    print(json.dumps(jsonable(payload), ensure_ascii=False, indent=2))
    return 1 if args.strict and payload.get("validation_status") == "FAILED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
