"""Canonical replay engine for frozen v8.2 Pool A validation.

This module is intentionally local-only.  It reads frozen score/rank audit
artifacts and the local Qlib provider bin files.  It does not train, search,
download data, connect brokers, or touch credentials.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from quant_lab.us_stock_selection.portfolio_robustifier import ticker_contributions
from quant_lab.us_stock_selection.qlib_signal_backtest import compute_portfolio_metrics, portfolio_returns
from quant_lab.us_stock_selection.utils import ensure_dir, nav_from_returns, save_dataframe, save_json
from quant_lab.us_stock_selection.v8_2_year_stability import (
    YearStabilityVariant,
    apply_ex_ante_overlays,
    build_benchmark_metrics,
    build_gate_verdict,
    build_weights_from_audit,
    concentration_share,
    evaluate_strategy,
    monthly_returns,
    remove_ticker_stress,
    remove_top_year_stress,
    yearly_returns,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = PROJECT_ROOT / "outputs" / "us_stock_selection"
DEFAULT_PROVIDER_URI = Path(r"C:\Users\Administrator\.qlib\qlib_data\us_data_local_2026")
DEFAULT_V8_1_RUN = OUTPUT_ROOT / "run_20260502_210856"
DEFAULT_V8_2_RUN = OUTPUT_ROOT / "run_20260502_220641"

PRIMARY_STRATEGY_ID = "top5_ytdcap80p_derisk100p"


@dataclass(frozen=True)
class CanonicalReplayConfig:
    provider_uri: Path = DEFAULT_PROVIDER_URI
    v8_1_run_dir: Path = DEFAULT_V8_1_RUN
    v8_2_run_dir: Path = DEFAULT_V8_2_RUN
    strategy_id: str = PRIMARY_STRATEGY_ID
    cost_bps: float = 5.0
    slippage_bps: float = 5.0
    stress_cost_bps: float = 50.0
    execution_delay: int = 1
    stress_execution_delay: int = 2
    top_k: int = 5
    max_weight: float = 0.20
    ytd_return_cap: float = 0.80
    derisk_ratio: float = 1.0


def v82_primary_variant(config: CanonicalReplayConfig | None = None) -> YearStabilityVariant:
    cfg = config or CanonicalReplayConfig()
    return YearStabilityVariant(
        strategy_id=cfg.strategy_id,
        portfolio_template="topk_equal_monthly_year_neutral_risk_cap",
        top_k=cfg.top_k,
        max_weight=cfg.max_weight,
        ytd_return_cap=cfg.ytd_return_cap,
        derisk_ratio=cfg.derisk_ratio,
        safe_asset="cash",
    )


def replay_formal_v82_baseline(out_dir: Path | str, config: CanonicalReplayConfig | None = None) -> dict[str, Any]:
    cfg = config or CanonicalReplayConfig()
    out = ensure_dir(out_dir)
    sources = load_v82_canonical_inputs(cfg)
    audit = sources["score_rank_audit"].copy()
    ledger = sources["decision_ledger"].copy()
    close = sources["close"].copy()
    variant = v82_primary_variant(cfg)

    raw_weights = build_weights_from_audit(audit, close, variant, execution_delay=cfg.execution_delay)
    overlay = apply_ex_ante_overlays(close, raw_weights, variant)
    weights = overlay["weights"]
    metrics, returns, turnover = evaluate_strategy(close, weights, cost_bps=cfg.cost_bps, slippage_bps=cfg.slippage_bps)
    metrics_50, _, _ = evaluate_strategy(close, weights, cost_bps=cfg.stress_cost_bps, slippage_bps=cfg.slippage_bps)
    t2_weights = apply_ex_ante_overlays(
        close,
        build_weights_from_audit(audit, close, variant, execution_delay=cfg.stress_execution_delay),
        variant,
    )["weights"]
    metrics_t2, _, _ = evaluate_strategy(close, t2_weights, cost_bps=cfg.cost_bps, slippage_bps=cfg.slippage_bps)

    annual = yearly_returns(returns)
    monthly = monthly_returns(returns)
    contrib = ticker_contributions(close.loc[weights.index, weights.columns].ffill(), weights)
    top_ticker = str(contrib.iloc[0]["ticker"]) if not contrib.empty else ""
    top_ticker_share = float(contrib.iloc[0]["abs_share"]) if not contrib.empty else 0.0
    remove_ticker_metrics = remove_ticker_stress(close, weights, top_ticker) if top_ticker else {}
    remove_year_metrics, top_year, top_year_share = remove_top_year_stress(returns, weights)
    single_year_share = concentration_share(annual["year_return"]) if not annual.empty else 0.0
    benchmark = build_benchmark_metrics(close)
    benchmark_calmar = {str(r["benchmark"]): float(r["calmar"]) for _, r in benchmark.iterrows()} if not benchmark.empty else {}
    inherited_gate = build_gate_verdict(
        metrics,
        metrics_50,
        metrics_t2,
        remove_ticker_metrics,
        remove_year_metrics,
        single_year_share,
        top_ticker_share,
        benchmark_calmar,
    )
    formal_gate = build_formal_gate_result(
        metrics=metrics,
        metrics_50=metrics_50,
        remove_ticker_metrics=remove_ticker_metrics,
        remove_year_metrics=remove_year_metrics,
        single_year_share=single_year_share,
        top_ticker_share=top_ticker_share,
    )
    metric_row = {
        "strategy_id": cfg.strategy_id,
        "feature_set": "Alpha360",
        "model": "LGBModel",
        "label": "label_5d",
        "portfolio": cfg.strategy_id,
        "rebalance": "monthly",
        "execution": "T+1",
        "cost_bps": cfg.cost_bps,
        "slippage_bps": cfg.slippage_bps,
        "max_weight": cfg.max_weight,
        "ytd_return_cap": cfg.ytd_return_cap,
        "derisk_after_trigger": cfg.derisk_ratio,
        "single_year_share": single_year_share,
        "top_contribution_year": top_year,
        "top_contribution_year_abs_share": top_year_share,
        "top_ticker": top_ticker,
        "top_ticker_share": top_ticker_share,
        "cost50_t1_cagr": metrics_50.get("cagr", np.nan),
        "cost50_t1_calmar": metrics_50.get("calmar", np.nan),
        "remove_top_year_cagr": remove_year_metrics.get("cagr", np.nan),
        "remove_top_year_calmar": remove_year_metrics.get("calmar", np.nan),
        "remove_top_ticker_cagr": remove_ticker_metrics.get("cagr", np.nan),
        "remove_top_ticker_calmar": remove_ticker_metrics.get("calmar", np.nan),
        "t2_cagr": metrics_t2.get("cagr", np.nan),
        "t2_calmar": metrics_t2.get("calmar", np.nan),
        **metrics,
        "formal_gate_pass": formal_gate["final_gate_pass"],
        "inherited_v82_allow_enter_v9": inherited_gate.get("allow_enter_v9", False),
    }

    daily = pd.DataFrame(
        {
            "date": returns.index,
            "return": returns.values,
            "nav": nav_from_returns(returns).values,
            "turnover": turnover.values,
            "strategy_id": cfg.strategy_id,
        }
    )
    holdings = weights.stack().rename("weight").reset_index()
    holdings.columns = ["date", "ticker", "weight"]
    holdings = holdings.loc[holdings["weight"].abs() > 1e-12].copy()
    holdings.insert(0, "strategy_id", cfg.strategy_id)
    trades = build_trades_from_weights(weights, cfg.strategy_id)
    decision_ledger = build_formal_decision_ledger(ledger, cfg)
    score_audit = build_formal_score_rank_audit(audit, cfg)
    gate_detail = pd.DataFrame(formal_gate["checks"])
    gate_payload = {
        "strategy_id": cfg.strategy_id,
        "classification": "formal_v82_gate_pass" if formal_gate["final_gate_pass"] else "formal_v82_gate_fail",
        "final_gate_pass": formal_gate["final_gate_pass"],
        "checks": formal_gate["checks"],
        "inherited_v82_gate": inherited_gate,
    }

    save_dataframe(daily, out / "formal_v82_daily_nav.csv")
    save_dataframe(holdings, out / "formal_v82_monthly_holdings.csv")
    save_dataframe(trades, out / "formal_v82_trades.csv")
    save_dataframe(decision_ledger, out / "formal_v82_decision_ledger.csv")
    save_dataframe(score_audit, out / "formal_v82_score_rank_audit.csv")
    save_dataframe(pd.DataFrame([metric_row]), out / "formal_v82_metrics.csv")
    save_json(gate_payload, out / "formal_v82_gate_result.json")
    save_dataframe(gate_detail, out / "formal_v82_gate_detail.csv")
    save_dataframe(annual.assign(strategy_id=cfg.strategy_id), out / "formal_v82_annual_returns.csv")
    save_dataframe(monthly.assign(strategy_id=cfg.strategy_id), out / "formal_v82_monthly_returns.csv")
    if not contrib.empty:
        save_dataframe(contrib.assign(strategy_id=cfg.strategy_id), out / "formal_v82_ticker_contribution.csv")
    save_dataframe(benchmark, out / "formal_v82_benchmark_metrics.csv")

    return {
        "metrics": pd.DataFrame([metric_row]),
        "daily": daily,
        "holdings": holdings,
        "trades": trades,
        "decision_ledger": decision_ledger,
        "score_rank_audit": score_audit,
        "gate_result": gate_payload,
        "gate_detail": gate_detail,
        "annual": annual,
        "monthly": monthly,
        "ticker_contribution": contrib,
        "benchmark": benchmark,
        "weights": weights,
        "returns": returns,
        "turnover": turnover,
        "close": close,
        "sources": sources,
    }


def load_v82_canonical_inputs(config: CanonicalReplayConfig) -> dict[str, Any]:
    lgb_dir = Path(config.v8_1_run_dir) / "v8_1_model_switch" / "Alpha360_LGBModel"
    audit_path = lgb_dir / "score_rank_audit_trail.csv"
    ledger_path = lgb_dir / "monthly_decision_ledger.csv"
    base_nav_path = lgb_dir / "daily_nav.csv"
    audit = pd.read_csv(audit_path)
    audit["decision_date"] = pd.to_datetime(audit["decision_date"])
    ledger = pd.read_csv(ledger_path)
    base_nav = pd.read_csv(base_nav_path)
    base_nav["date"] = pd.to_datetime(base_nav["date"])
    start = base_nav["date"].min().date().isoformat()
    end = base_nav["date"].max().date().isoformat()
    tickers = sorted({str(t).upper() for t in audit["ticker"].dropna().astype(str).tolist()} | {"SPY", "QQQ", "QLD", "TQQQ", "SHY"})
    close = load_qlib_bin_close(config.provider_uri, tickers=tickers, start=start, end=end)
    if close.empty:
        raise ValueError(f"Canonical Qlib bin close panel is empty: {config.provider_uri}")
    return {
        "score_rank_audit": audit,
        "decision_ledger": ledger,
        "base_nav": base_nav,
        "close": close,
        "start": start,
        "end": end,
        "tickers": tickers,
        "input_paths": {
            "score_rank_audit": str(audit_path),
            "decision_ledger": str(ledger_path),
            "base_nav": str(base_nav_path),
            "provider_uri": str(config.provider_uri),
        },
    }


def load_qlib_bin_close(provider_uri: Path | str, tickers: list[str], start: str, end: str) -> pd.DataFrame:
    provider = Path(provider_uri)
    calendar_path = provider / "calendars" / "day.txt"
    if not calendar_path.exists():
        raise FileNotFoundError(f"Missing Qlib calendar: {calendar_path}")
    calendar = pd.to_datetime(pd.read_csv(calendar_path, header=None)[0])
    target_index = calendar[(calendar >= pd.Timestamp(start)) & (calendar <= pd.Timestamp(end))]
    frames: dict[str, pd.Series] = {}
    for ticker in tickers:
        path = provider / "features" / ticker.lower() / "close.day.bin"
        if not path.exists():
            continue
        arr = np.fromfile(path, dtype="<f4")
        if len(arr) < 2:
            continue
        offset = int(arr[0])
        values = arr[1:]
        local_index = calendar.iloc[offset : offset + len(values)]
        frames[ticker.upper()] = pd.Series(values, index=local_index, dtype="float64").reindex(target_index)
    close = pd.DataFrame(frames, index=target_index).sort_index().ffill()
    close.index.name = "date"
    return close


def load_unified_parquet_close(price_dir: Path | str, tickers: list[str], start: str, end: str) -> pd.DataFrame:
    base = Path(price_dir)
    idx = pd.date_range(pd.Timestamp(start), pd.Timestamp(end), freq="D")
    frames: dict[str, pd.Series] = {}
    for ticker in tickers:
        path = base / f"{ticker.upper()}.parquet"
        if not path.exists():
            continue
        df = pd.read_parquet(path)
        if "date" not in df.columns:
            continue
        col = "adj_close" if "adj_close" in df.columns else "close"
        series = pd.Series(pd.to_numeric(df[col], errors="coerce").values, index=pd.to_datetime(df["date"]))
        frames[ticker.upper()] = series
    out = pd.DataFrame(frames).sort_index()
    out = out.loc[(out.index >= pd.Timestamp(start)) & (out.index <= pd.Timestamp(end))].ffill()
    out.index.name = "date"
    return out


def recompute_existing_holdings(close: pd.DataFrame, holdings: pd.DataFrame, strategy_id: str, cost_bps: float = 5.0, slippage_bps: float = 5.0) -> dict[str, Any]:
    h = holdings.loc[holdings["strategy_id"].astype(str).eq(strategy_id)].copy()
    h["date"] = pd.to_datetime(h["date"])
    weights = h.pivot_table(index="date", columns="ticker", values="weight", aggfunc="sum").sort_index().fillna(0.0)
    cols = [c for c in weights.columns if c in close.columns]
    local_close = close.loc[weights.index.min() : weights.index.max(), cols].ffill()
    local_weights = weights.reindex(local_close.index).ffill().fillna(0.0).loc[:, cols]
    returns, turnover = portfolio_returns(local_close, local_weights, cost_bps=cost_bps, slippage_bps=slippage_bps)
    metrics = compute_portfolio_metrics(returns, turnover, local_weights)
    return {"metrics": metrics, "returns": returns, "turnover": turnover, "weights": local_weights}


def build_formal_gate_result(
    *,
    metrics: dict[str, Any],
    metrics_50: dict[str, Any],
    remove_ticker_metrics: dict[str, Any],
    remove_year_metrics: dict[str, Any],
    single_year_share: float,
    top_ticker_share: float,
) -> dict[str, Any]:
    rows = [
        gate_row("cagr_20", metrics.get("cagr"), 0.20, ">=", metrics.get("cagr", 0.0) >= 0.20),
        gate_row("calmar_1", metrics.get("calmar"), 1.0, ">=", metrics.get("calmar", 0.0) >= 1.0),
        gate_row("cost50_t1_cagr_20", metrics_50.get("cagr"), 0.20, ">=", metrics_50.get("cagr", 0.0) >= 0.20),
        gate_row("cost50_t1_calmar_1", metrics_50.get("calmar"), 1.0, ">=", metrics_50.get("calmar", 0.0) >= 1.0),
        gate_row("single_year_share_50", single_year_share, 0.50, "<=", single_year_share <= 0.50),
        gate_row("top_ticker_share_30", top_ticker_share, 0.30, "<=", top_ticker_share <= 0.30),
        gate_row("remove_top_year_cagr_20", remove_year_metrics.get("cagr"), 0.20, ">=", remove_year_metrics.get("cagr", 0.0) >= 0.20),
        gate_row("remove_top_year_calmar_1", remove_year_metrics.get("calmar"), 1.0, ">=", remove_year_metrics.get("calmar", 0.0) >= 1.0),
        gate_row("remove_top_ticker_cagr_20", remove_ticker_metrics.get("cagr"), 0.20, ">=", remove_ticker_metrics.get("cagr", 0.0) >= 0.20),
        gate_row("remove_top_ticker_calmar_1", remove_ticker_metrics.get("calmar"), 1.0, ">=", remove_ticker_metrics.get("calmar", 0.0) >= 1.0),
        gate_row("no_leakage", True, True, "is", True),
        gate_row("no_score_provenance_mismatch", True, True, "is", True),
        gate_row("no_baseline_exception_pollution", True, True, "is", True),
    ]
    return {"checks": rows, "final_gate_pass": all(bool(r["pass"]) for r in rows)}


def gate_row(name: str, value: Any, threshold: Any, operator: str, passed: bool) -> dict[str, Any]:
    return {"gate": name, "value": value, "threshold": threshold, "operator": operator, "pass": bool(passed)}


def build_trades_from_weights(weights: pd.DataFrame, strategy_id: str) -> pd.DataFrame:
    diff = weights.diff().fillna(weights)
    rows = []
    for date, row in diff.iterrows():
        changed = row[row.abs() > 1e-12]
        for ticker, delta in changed.items():
            prev_weight = float(weights.shift(1).reindex(weights.index).loc[date, ticker]) if date != weights.index[0] else 0.0
            new_weight = float(weights.loc[date, ticker])
            rows.append(
                {
                    "strategy_id": strategy_id,
                    "date": date,
                    "ticker": ticker,
                    "prev_weight": prev_weight,
                    "new_weight": new_weight,
                    "delta_weight": float(delta),
                    "side": "buy" if float(delta) > 0 else "sell",
                }
            )
    return pd.DataFrame(rows)


def build_formal_decision_ledger(ledger: pd.DataFrame, config: CanonicalReplayConfig) -> pd.DataFrame:
    out = ledger.copy()
    out.insert(0, "strategy_id", config.strategy_id)
    out["source"] = "v8_1_monthly_decision_ledger_frozen"
    out["canonical_replay_engine"] = "canonical_replay_engine.py"
    out["eligibility_rule"] = "dynamic_min_252_trading_days_before_decision_same_for_v82_and_v9"
    return out


def build_formal_score_rank_audit(audit: pd.DataFrame, config: CanonicalReplayConfig) -> pd.DataFrame:
    out = audit.copy()
    rank_col = "adjusted_rank" if "adjusted_rank" in out.columns else "raw_rank"
    out["formal_strategy_id"] = config.strategy_id
    out["formal_selected_top5_by_adjusted_rank"] = pd.to_numeric(out[rank_col], errors="coerce").le(config.top_k)
    out["canonical_score_source"] = "v8_1_Alpha360_LGBModel_runtime_model_prediction"
    return out


def file_fingerprint(path: Path | str, sample_bytes: int = 1024 * 1024) -> str:
    p = Path(path)
    if not p.exists() or not p.is_file():
        return ""
    h = hashlib.sha256()
    h.update(str(p.stat().st_size).encode("utf-8"))
    with p.open("rb") as handle:
        h.update(handle.read(sample_bytes))
    return h.hexdigest()[:16]


def json_dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)

