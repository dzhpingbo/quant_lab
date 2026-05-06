"""v9/v8.2 reverse audit package.

This module audits the frozen v8.2 / v9 small growth-pool handoff.  It does
not expand the universe, does not search strategy parameters, and does not
produce any trading/execution integration.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from quant_lab.us_stock_selection.portfolio_robustifier import ticker_contributions
from quant_lab.us_stock_selection.qlib_signal_backtest import compute_portfolio_metrics, portfolio_returns
from quant_lab.us_stock_selection.utils import ensure_dir, nav_from_returns, save_dataframe, save_json
from quant_lab.us_stock_selection.v8_2_year_stability import concentration_share
from quant_lab.us_stock_selection.v8_paper_trading import trading_offset
from quant_lab.us_stock_selection.v9_growth_pool import (
    END,
    START,
    TRAIN_START,
    apply_ytd_cap,
    build_local_alpha360_feature_frame,
    build_panel,
    date_str,
    evaluate,
    latest_feature_date,
    make_lgb_model,
    month_end_dates,
    normalize_price_frame,
    remove_ticker_stress,
    remove_top_year_stress,
    tradable_universe,
    yearly_returns,
)


CORE_CAGR_GATE = 0.20
CORE_CALMAR_GATE = 1.0
POOL_A_TOP5 = "top5_ytdcap80p_derisk100p"
POOL_A_TOP10 = "top10_ytdcap80p_derisk100p"
REQUIRED_INPUTS = [
    "AGENTS.md",
    "docs/US_STOCK_SELECTION_AUTORUN.md",
    "NEXT_STEPS.md",
    "RUN_SUMMARY.md",
    "docs/chatgpt_bridge/LATEST.md",
    "docs/chatgpt_bridge/latest_run_manifest.json",
    "docs/chatgpt_bridge/runs/run_20260502_222407/REVIEW_PACKET.md",
    "docs/chatgpt_bridge/runs/run_20260502_222407/selected_report.md",
    "docs/chatgpt_bridge/runs/run_20260502_222407/final_verdict.json",
]


@dataclass(frozen=True)
class ScorePackage:
    name: str
    score_frames: dict[pd.Timestamp, pd.DataFrame]
    time_audit: pd.DataFrame


def run_v9_reverse_audit(
    out_dir: Path | str,
    v9_run_dir: Path | str,
    v8_2_run_dir: Path | str,
    v8_1_run_dir: Path | str,
    unified_store_dir: Path | str,
    project_root: Path | str,
    logger: Any,
) -> dict[str, Any]:
    """Run the bounded reverse audit and write all required CSV outputs."""

    out = ensure_dir(out_dir)
    root = Path(project_root)
    v9_run = Path(v9_run_dir)
    v8_2_run = Path(v8_2_run_dir)
    v8_1_run = Path(v8_1_run_dir)
    store = Path(unified_store_dir)

    logger.info("Reading required v9/v8.2/v8.1 inputs for reverse audit.")
    source_manifest = build_source_manifest(root, v9_run, v8_2_run, v8_1_run)
    save_dataframe(source_manifest, out / "source_manifest.csv")

    v9_dir = v9_run / "v9_growth_pool"
    v8_2_dir = v8_2_run / "v8_2_year_stability"
    v8_1_lgb_dir = v8_1_run / "v8_1_model_switch" / "Alpha360_LGBModel"

    v9_tables = read_v9_growth_tables(v9_dir)
    v8_2_tables = read_v8_2_tables(v8_2_dir)
    v8_1_tables = read_v8_1_tables(v8_1_lgb_dir)
    pool_a_tickers = parse_pool_a_tickers(v9_tables["universe_definitions"])
    logger.info(f"Pool A reverse audit universe has {len(pool_a_tickers)} tickers.")

    price_tickers = sorted(set(pool_a_tickers) | {"SPY", "QQQ", "QLD", "TQQQ", "SHY"})
    price_data, price_audit = load_existing_prices(
        tickers=price_tickers,
        unified_store_dir=store,
        fallback_download_dir=v9_dir / "downloaded_prices",
    )
    save_dataframe(price_audit, out / "price_source_audit.csv")
    missing = price_audit.loc[~price_audit["load_success"], "ticker"].astype(str).tolist()
    if missing:
        raise FileNotFoundError(f"Missing local price data for reverse audit tickers: {missing}")

    close = build_panel(price_data, "adj_close").loc[TRAIN_START:END].ffill()
    volume = build_panel(price_data, "volume").loc[TRAIN_START:END].ffill()
    dollar_volume = close * volume
    feature_price_data = {t: price_data[t] for t in price_tickers if t in price_data}
    logger.info("Building local Alpha360-compatible features for Pool A reverse audit.")
    features, feature_cols = build_local_alpha360_feature_frame(feature_price_data, price_tickers, TRAIN_START, END)
    save_dataframe(pd.DataFrame({"feature_column": feature_cols}), out / "v9_reverse_audit_feature_columns.csv")

    normal_pkg = fit_monthly_scores(
        name="normal_label",
        universe=pool_a_tickers,
        features=features,
        feature_cols=feature_cols,
        close=close,
        label_mode="normal",
        logger=logger,
    )
    shuffled_pkg = fit_monthly_scores(
        name="shuffled_label_within_train_window",
        universe=pool_a_tickers,
        features=features,
        feature_cols=feature_cols,
        close=close,
        label_mode="shuffled",
        logger=logger,
    )

    local_top5 = replay_from_scores(
        universe_name="pool_a_v9_local_replay_top5",
        score_frames=normal_pkg.score_frames,
        top_k=5,
        close=close,
        dollar_volume=dollar_volume,
        execution_delay=1,
    )
    local_top10 = replay_from_scores(
        universe_name="pool_a_v9_local_replay_top10",
        score_frames=normal_pkg.score_frames,
        top_k=10,
        close=close,
        dollar_volume=dollar_volume,
        execution_delay=1,
    )
    local_results = pd.DataFrame([local_top5["summary"], local_top10["summary"]])
    save_dataframe(local_results, out / "v9_local_pool_a_results.csv")

    time_alignment = pd.concat(
        [
            normal_pkg.time_audit.assign(universe_name="pool_a_v9_local_replay"),
            upstream_time_alignment(v8_1_tables["monthly_decision_ledger"], feature_cols).assign(
                universe_name="pool_a_v8_1_upstream_score_audit"
            ),
        ],
        ignore_index=True,
        sort=False,
    )
    time_alignment = finalize_time_alignment(time_alignment)
    save_dataframe(time_alignment, out / "time_alignment_audit.csv")

    pool_a_replay_audit = build_pool_a_replay_audit(v9_tables, v8_2_tables, local_top5, local_top10)
    save_dataframe(pool_a_replay_audit, out / "pool_a_replay_audit.csv")

    negative_controls = run_negative_controls(
        normal_pkg=normal_pkg,
        shuffled_pkg=shuffled_pkg,
        close=close,
        dollar_volume=dollar_volume,
        primary_metrics=local_top5["summary"],
        frozen_metrics=frozen_strategy_row(v8_2_tables["results"], POOL_A_TOP5),
    )
    save_dataframe(negative_controls, out / "negative_controls.csv")

    execution_sensitivity = build_execution_timing_sensitivity(
        normal_pkg=normal_pkg,
        close=close,
        dollar_volume=dollar_volume,
    )
    save_dataframe(execution_sensitivity, out / "execution_timing_sensitivity.csv")

    benchmark = build_benchmark(close.loc[START:END, close.columns.intersection(price_tickers)], pool_a_tickers)
    save_dataframe(benchmark, out / "benchmark.csv")

    stress = build_stress_test(local_top5, close, v8_2_tables)
    save_dataframe(stress, out / "stress_test.csv")

    universe_policy = build_universe_policy_audit(v9_tables, pool_a_tickers)
    save_dataframe(universe_policy, out / "universe_policy_audit.csv")

    yearly = build_yearly_return_table(local_top5, local_top10, v8_2_tables, benchmark)
    save_dataframe(yearly, out / "yearly_return.csv")
    attribution = build_attribution_table(local_top5, local_top10, v8_2_tables)
    save_dataframe(attribution, out / "attribution.csv")

    daily = pd.concat([local_top5["daily"], local_top10["daily"]], ignore_index=True)
    holdings = pd.concat([local_top5["holdings"], local_top10["holdings"]], ignore_index=True)
    score_audit = build_score_rank_audit_table(normal_pkg.score_frames)
    save_dataframe(daily, out / "daily_nav.csv")
    save_dataframe(holdings, out / "monthly_holdings.csv")
    save_dataframe(score_audit, out / "score_rank_audit.csv")

    verdict = build_reverse_audit_verdict(
        source_manifest=source_manifest,
        time_alignment=time_alignment,
        pool_a_replay_audit=pool_a_replay_audit,
        negative_controls=negative_controls,
        benchmark=benchmark,
        stress=stress,
        universe_policy=universe_policy,
    )
    save_json(verdict, out / "v9_reverse_audit_verdict.json")
    return {
        "source_manifest": source_manifest,
        "price_audit": price_audit,
        "time_alignment": time_alignment,
        "pool_a_replay_audit": pool_a_replay_audit,
        "negative_controls": negative_controls,
        "execution_timing_sensitivity": execution_sensitivity,
        "benchmark": benchmark,
        "stress_test": stress,
        "universe_policy_audit": universe_policy,
        "yearly_return": yearly,
        "attribution": attribution,
        "local_results": local_results,
        "daily": daily,
        "holdings": holdings,
        "score_audit": score_audit,
        "verdict": verdict,
    }


def build_source_manifest(root: Path, v9_run: Path, v8_2_run: Path, v8_1_run: Path) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for rel in REQUIRED_INPUTS:
        path = root / rel
        rows.append({"source": rel, "path": str(path), "exists": path.exists(), "required": True})
    for path in sorted((v9_run / "v9_growth_pool").glob("*.csv")):
        rows.append({"source": f"v9_growth_pool/{path.name}", "path": str(path), "exists": path.exists(), "required": True})
    for rel in [
        "v8_2_year_stability/v8_2_year_stability_results.csv",
        "v8_2_year_stability/v8_2_annual_return_table.csv",
        "v8_2_year_stability/v8_2_ticker_contribution.csv",
        "v8_2_year_stability/v8_2_execution_stress_results.csv",
        "v8_2_year_stability/v8_2_benchmark_comparison.csv",
        "v8_2_year_stability/v8_2_daily_nav_by_strategy.csv",
        "v8_2_year_stability/v8_2_monthly_holdings_by_strategy.csv",
    ]:
        path = v8_2_run / rel
        rows.append({"source": f"v8.2/{rel}", "path": str(path), "exists": path.exists(), "required": True})
    for rel in [
        "v8_1_model_switch/Alpha360_LGBModel/score_rank_audit_trail.csv",
        "v8_1_model_switch/Alpha360_LGBModel/monthly_decision_ledger.csv",
        "v8_1_model_switch/Alpha360_LGBModel/monthly_holdings.csv",
        "v8_1_model_switch/Alpha360_LGBModel/daily_nav.csv",
    ]:
        path = v8_1_run / rel
        rows.append({"source": f"v8.1/{rel}", "path": str(path), "exists": path.exists(), "required": True})
    out = pd.DataFrame(rows)
    out["read_status"] = np.where(out["exists"], "read", "missing")
    return out


def read_v9_growth_tables(v9_dir: Path) -> dict[str, pd.DataFrame]:
    names = {
        "results": "v9_growth_pool_results.csv",
        "annual": "v9_annual_return_table.csv",
        "daily": "v9_daily_nav_by_universe.csv",
        "quality": "v9_data_quality_audit.csv",
        "effective": "v9_effective_universe.csv",
        "excluded": "v9_excluded_tickers.csv",
        "price_download": "v9_price_download_audit.csv",
        "universe_definitions": "v9_universe_definitions.csv",
        "contribution": "v9_ticker_contribution.csv",
        "holdings": "v9_monthly_holdings.csv",
        "score_audit": "v9_score_rank_audit_trail.csv",
        "trades": "v9_trades.csv",
    }
    return {key: pd.read_csv(v9_dir / filename) for key, filename in names.items()}


def read_v8_2_tables(v8_2_dir: Path) -> dict[str, pd.DataFrame]:
    names = {
        "results": "v8_2_year_stability_results.csv",
        "annual": "v8_2_annual_return_table.csv",
        "daily": "v8_2_daily_nav_by_strategy.csv",
        "holdings": "v8_2_monthly_holdings_by_strategy.csv",
        "contribution": "v8_2_ticker_contribution.csv",
        "stress": "v8_2_execution_stress_results.csv",
        "benchmark": "v8_2_benchmark_comparison.csv",
    }
    return {key: pd.read_csv(v8_2_dir / filename) for key, filename in names.items()}


def read_v8_1_tables(v8_1_lgb_dir: Path) -> dict[str, pd.DataFrame]:
    names = {
        "score_audit": "score_rank_audit_trail.csv",
        "monthly_decision_ledger": "monthly_decision_ledger.csv",
        "monthly_holdings": "monthly_holdings.csv",
        "daily": "daily_nav.csv",
    }
    return {key: pd.read_csv(v8_1_lgb_dir / filename) for key, filename in names.items()}


def parse_pool_a_tickers(universe_definitions: pd.DataFrame) -> list[str]:
    row = universe_definitions.loc[universe_definitions["universe_name"] == "pool_a_v8_2_reproduction"]
    if row.empty:
        raise ValueError("pool_a_v8_2_reproduction not found in v9_universe_definitions.csv")
    raw = str(row.iloc[0]["tickers"])
    tickers = [item.strip().upper() for item in raw.split(",") if item.strip()]
    if not tickers:
        raise ValueError("Pool A ticker list is empty.")
    return sorted(dict.fromkeys(tickers))


def load_existing_prices(
    tickers: list[str],
    unified_store_dir: Path,
    fallback_download_dir: Path,
) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    rows: list[dict[str, Any]] = []
    out: dict[str, pd.DataFrame] = {}
    for ticker in tickers:
        candidates = [
            (unified_store_dir / "prices" / f"{ticker}.parquet", "unified_store"),
            (fallback_download_dir / f"{ticker}.parquet", "v9_downloaded_prices"),
        ]
        loaded = False
        errors: list[str] = []
        for path, source in candidates:
            if not path.exists():
                continue
            try:
                frame = pd.read_parquet(path)
                if "date" not in frame.columns and frame.index.name:
                    frame = frame.reset_index()
                norm = normalize_price_frame(frame, ticker, source)
                out[ticker] = norm
                rows.append(
                    {
                        "ticker": ticker,
                        "source": source,
                        "path": str(path),
                        "load_success": True,
                        "rows": len(norm),
                        "first_date": date_str(norm["date"].min()),
                        "last_date": date_str(norm["date"].max()),
                        "error": "",
                    }
                )
                loaded = True
                break
            except Exception as exc:  # pragma: no cover - corrupt local file path
                errors.append(f"{path}: {exc}")
        if not loaded:
            rows.append(
                {
                    "ticker": ticker,
                    "source": "",
                    "path": "",
                    "load_success": False,
                    "rows": 0,
                    "first_date": "",
                    "last_date": "",
                    "error": "; ".join(errors) if errors else "not_found_in_local_store_or_v9_downloads",
                }
            )
    return out, pd.DataFrame(rows)


def fit_monthly_scores(
    name: str,
    universe: list[str],
    features: pd.DataFrame,
    feature_cols: list[str],
    close: pd.DataFrame,
    label_mode: str,
    logger: Any,
) -> ScorePackage:
    score_frames: dict[pd.Timestamp, pd.DataFrame] = {}
    audit_rows: list[dict[str, Any]] = []
    label_cols_in_features = [c for c in feature_cols if "label" in str(c).lower()]
    decision_dates = month_end_dates(close.index, START, END)
    rng = np.random.default_rng(42)
    for decision_date in decision_dates:
        train_end = trading_offset(close.index, decision_date, -6)
        feature_date = latest_feature_date(features, decision_date)
        execution_date = trading_offset(close.index, decision_date, 1)
        if pd.isna(train_end) or pd.isna(feature_date) or pd.isna(execution_date):
            continue
        train = features.loc[
            (features["instrument"].isin(universe))
            & (features["date"] <= train_end)
            & features["label_5d"].notna()
        ].copy()
        pred_frame = features.loc[(features["instrument"].isin(universe)) & (features["date"] == feature_date)].copy()
        train_max_feature_date = pd.to_datetime(train["date"]).max() if not train.empty else pd.NaT
        label_window_end = trading_offset(close.index, train_max_feature_date, 6) if pd.notna(train_max_feature_date) else pd.NaT
        audit_rows.append(
            {
                "score_package": name,
                "decision_date": date_str(decision_date),
                "feature_date": date_str(feature_date),
                "train_end_label_safe": date_str(train_end),
                "train_max_feature_date": date_str(train_max_feature_date),
                "label_window_end": date_str(label_window_end),
                "execution_date": date_str(execution_date),
                "train_rows": int(len(train)),
                "predict_rows": int(len(pred_frame)),
                "label_cols_in_feature_cols": ",".join(label_cols_in_features),
            }
        )
        if len(train) < 500 or pred_frame.empty:
            continue
        y = train["label_5d"].astype(float).to_numpy()
        if label_mode == "shuffled":
            y = rng.permutation(y)
        model = make_lgb_model()
        logger.info(f"Fitting reverse-audit {name} model for decision {date_str(decision_date)}.")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model.fit(train[feature_cols], y)
        pred = pred_frame.loc[:, ["date", "instrument"]].copy()
        pred["ticker"] = pred["instrument"].astype(str).str.upper()
        pred["score"] = model.predict(pred_frame[feature_cols])
        pred["decision_date"] = pd.Timestamp(decision_date)
        pred["feature_date"] = pd.Timestamp(feature_date)
        score_frames[pd.Timestamp(decision_date)] = pred.loc[:, ["decision_date", "feature_date", "ticker", "score"]]
    return ScorePackage(name=name, score_frames=score_frames, time_audit=pd.DataFrame(audit_rows))


def replay_from_scores(
    universe_name: str,
    score_frames: dict[pd.Timestamp, pd.DataFrame],
    top_k: int,
    close: pd.DataFrame,
    dollar_volume: pd.DataFrame,
    execution_delay: int,
) -> dict[str, Any]:
    universe = sorted({str(t).upper() for frame in score_frames.values() for t in frame["ticker"].dropna().astype(str)})
    local_close = close.loc[:, close.columns.intersection(universe)].ffill()
    local_dv = dollar_volume.reindex(local_close.index).loc[:, local_close.columns].ffill()
    weights = pd.DataFrame(np.nan, index=local_close.index, columns=local_close.columns, dtype=float)
    holding_rows: list[dict[str, Any]] = []
    current = pd.Series(0.0, index=local_close.columns, dtype=float)
    for decision_date in sorted(score_frames):
        frame = score_frames[decision_date].copy()
        tradable = tradable_universe(local_close, local_dv, frame["ticker"].astype(str).tolist(), decision_date)
        ranked = frame.loc[frame["ticker"].isin(tradable)].sort_values("score", ascending=False).drop_duplicates("ticker")
        selected = ranked.head(top_k).copy()
        execution_date = trading_offset(local_close.index, decision_date, execution_delay)
        if selected.empty or pd.isna(execution_date):
            continue
        current = pd.Series(0.0, index=local_close.columns, dtype=float)
        selected_tickers = [t for t in selected["ticker"].astype(str).tolist() if t in current.index]
        if selected_tickers:
            raw_weight = min(0.20, 1.0 / float(len(selected_tickers)))
            current.loc[selected_tickers] = raw_weight
            if current.sum() > 0 and current.sum() < 0.999 and 0.20 >= 1.0 / float(len(selected_tickers)):
                current = current / current.sum()
        weights.loc[execution_date] = current
        for rank, row in enumerate(selected.itertuples(index=False), start=1):
            holding_rows.append(
                {
                    "universe_name": universe_name,
                    "decision_date": date_str(decision_date),
                    "execution_date": date_str(execution_date),
                    "ticker": row.ticker,
                    "weight": float(current.get(row.ticker, 0.0)),
                    "score": float(row.score),
                    "selected_rank": rank,
                }
            )
    weights = weights.ffill().fillna(0.0)
    overlay = apply_ytd_cap(weights, local_close, cap=0.80)
    weights = overlay["weights"]
    metrics, returns, turnover = evaluate(local_close, weights, cost_bps=5.0, slippage_bps=5.0)
    metrics_50, _, _ = evaluate(local_close, weights, cost_bps=50.0, slippage_bps=5.0)
    annual = yearly_returns(returns).assign(universe_name=universe_name)
    contrib = ticker_contributions(local_close.loc[weights.index, weights.columns].ffill(), weights)
    top_ticker = str(contrib.iloc[0]["ticker"]) if not contrib.empty else ""
    top_ticker_share = float(contrib.iloc[0]["abs_share"]) if not contrib.empty else 0.0
    remove_ticker_metrics = remove_ticker_stress(local_close, weights, top_ticker)
    remove_year_metrics, top_year, top_year_share = remove_top_year_stress(returns, weights)
    summary = {
        "universe_name": universe_name,
        "ticker_count": len(universe),
        "top_k": int(top_k),
        "method": "v9_local_alpha360_replay_reverse_audit",
        "feature_set": "Alpha360",
        "model": "LGBModel",
        "label": "label_5d",
        "portfolio": "top5_ytdcap80p_derisk100p" if top_k == 5 else "top10_ytdcap80p_derisk100p_control",
        "cost50_t1_cagr": metrics_50.get("cagr", 0.0),
        "cost50_t1_calmar": metrics_50.get("calmar", 0.0),
        "single_year_share": concentration_share(annual["year_return"]) if not annual.empty else 0.0,
        "top_contribution_year": top_year,
        "top_contribution_year_abs_share": top_year_share,
        "top_ticker": top_ticker,
        "top_ticker_share": top_ticker_share,
        "remove_top_year_cagr": remove_year_metrics.get("cagr", 0.0),
        "remove_top_year_calmar": remove_year_metrics.get("calmar", 0.0),
        "remove_top_ticker_cagr": remove_ticker_metrics.get("cagr", 0.0),
        "remove_top_ticker_calmar": remove_ticker_metrics.get("calmar", 0.0),
        "turnover": metrics.get("annual_turnover", 0.0),
        "exposure": overlay["avg_exposure"],
        "derisk_days_ratio": overlay["derisk_days_ratio"],
        **metrics,
    }
    daily = pd.DataFrame(
        {
            "date": returns.index,
            "return": returns.values,
            "nav": nav_from_returns(returns).values,
            "turnover": turnover.values,
            "universe_name": universe_name,
        }
    )
    holdings = weights.stack().rename("weight").reset_index()
    holdings.columns = ["date", "ticker", "weight"]
    holdings = holdings.loc[holdings["weight"].abs() > 1e-12].copy()
    holdings.insert(0, "universe_name", universe_name)
    if not contrib.empty:
        contrib.insert(0, "universe_name", universe_name)
    return {
        "summary": summary,
        "annual": annual,
        "ticker_contribution": contrib,
        "holdings": holdings,
        "decision_holdings": pd.DataFrame(holding_rows),
        "weights": weights,
        "returns": returns,
        "turnover": turnover,
        "daily": daily,
        "close": local_close,
    }


def upstream_time_alignment(ledger: pd.DataFrame, feature_cols: list[str]) -> pd.DataFrame:
    if ledger.empty:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    label_cols_in_features = [c for c in feature_cols if "label" in str(c).lower()]
    for row in ledger.to_dict("records"):
        decision = pd.Timestamp(row.get("decision_date"))
        feature_date = pd.Timestamp(row.get("feature_date"))
        train_end = pd.Timestamp(row.get("train_end_label_safe"))
        execution = pd.Timestamp(row.get("execution_date"))
        rows.append(
            {
                "score_package": "v8_1_monthly_decision_ledger",
                "decision_date": date_str(decision),
                "feature_date": date_str(feature_date),
                "train_end_label_safe": date_str(train_end),
                "train_max_feature_date": date_str(train_end),
                "label_window_end": date_str(decision),
                "execution_date": date_str(execution),
                "train_rows": int(row.get("train_rows", 0) or 0),
                "predict_rows": int(row.get("predict_rows", 0) or 0),
                "label_cols_in_feature_cols": ",".join(label_cols_in_features),
            }
        )
    return pd.DataFrame(rows)


def finalize_time_alignment(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in ["decision_date", "feature_date", "train_end_label_safe", "train_max_feature_date", "label_window_end", "execution_date"]:
        out[col] = pd.to_datetime(out[col], errors="coerce")
    out["feature_date_lte_decision"] = out["feature_date"] <= out["decision_date"]
    out["execution_gt_decision"] = out["execution_date"] > out["decision_date"]
    out["train_feature_date_lte_train_end_label_safe"] = out["train_max_feature_date"] <= out["train_end_label_safe"]
    out["label_window_end_lte_decision"] = out["label_window_end"] <= out["decision_date"]
    out["label_cols_not_in_feature_cols"] = out["label_cols_in_feature_cols"].fillna("").astype(str).str.len() == 0
    issue_cols = [
        ("feature_date_lte_decision", "feature_date_after_decision"),
        ("execution_gt_decision", "execution_not_after_decision"),
        ("train_feature_date_lte_train_end_label_safe", "train_feature_after_label_safe_end"),
        ("label_window_end_lte_decision", "label_window_crosses_decision"),
        ("label_cols_not_in_feature_cols", "label_column_in_feature_cols"),
    ]
    issues = []
    for _, row in out.iterrows():
        local = [name for col, name in issue_cols if not bool(row.get(col, False))]
        issues.append(";".join(local))
    out["pass"] = [not bool(item) for item in issues]
    out["issue"] = issues
    for col in ["decision_date", "feature_date", "train_end_label_safe", "train_max_feature_date", "label_window_end", "execution_date"]:
        out[col] = out[col].dt.date.astype(str)
        out.loc[out[col] == "NaT", col] = ""
    return out


def build_pool_a_replay_audit(
    v9_tables: dict[str, pd.DataFrame],
    v8_2_tables: dict[str, pd.DataFrame],
    local_top5: dict[str, Any],
    local_top10: dict[str, Any],
) -> pd.DataFrame:
    rows = []
    for strategy_id, local in [(POOL_A_TOP5, local_top5), (POOL_A_TOP10, local_top10)]:
        frozen = frozen_strategy_row(v8_2_tables["results"], strategy_id)
        loaded_name = "pool_a_v8_2_reproduction" if strategy_id == POOL_A_TOP5 else "pool_a_v8_2_reproduction_top10_control"
        loaded = universe_row(v9_tables["results"], loaded_name)
        local_summary = local["summary"]
        annual_diff = annual_diff_json(v8_2_tables["annual"], local["annual"], strategy_id)
        cagr_diff = float(local_summary.get("cagr", 0.0) - frozen.get("cagr", 0.0))
        calmar_diff = float(local_summary.get("calmar", 0.0) - frozen.get("calmar", 0.0))
        maxdd_diff = float(local_summary.get("max_drawdown", 0.0) - frozen.get("max_drawdown", 0.0))
        turnover_diff = float(local_summary.get("annual_turnover", local_summary.get("turnover", 0.0)) - frozen.get("annual_turnover", 0.0))
        top_ticker_match = str(local_summary.get("top_ticker", "")) == str(frozen.get("top_ticker", ""))
        metric_close = (
            abs(cagr_diff) <= 0.05
            and abs(calmar_diff) <= 0.20
            and abs(maxdd_diff) <= 0.05
            and abs(turnover_diff) <= 3.0
            and top_ticker_match
        )
        rows.append(
            {
                "strategy_id": strategy_id,
                "top_k": int(local_summary.get("top_k", 0)),
                "v8_2_frozen_cagr": frozen.get("cagr"),
                "v9_loaded_reproduction_cagr": loaded.get("cagr"),
                "v9_local_replay_cagr": local_summary.get("cagr"),
                "cagr_diff_local_minus_frozen": cagr_diff,
                "v8_2_frozen_calmar": frozen.get("calmar"),
                "v9_loaded_reproduction_calmar": loaded.get("calmar"),
                "v9_local_replay_calmar": local_summary.get("calmar"),
                "calmar_diff_local_minus_frozen": calmar_diff,
                "v8_2_frozen_max_drawdown": frozen.get("max_drawdown"),
                "v9_local_replay_max_drawdown": local_summary.get("max_drawdown"),
                "max_drawdown_diff_local_minus_frozen": maxdd_diff,
                "v8_2_frozen_turnover": frozen.get("annual_turnover"),
                "v9_local_replay_turnover": local_summary.get("annual_turnover"),
                "turnover_diff_local_minus_frozen": turnover_diff,
                "v8_2_frozen_top_ticker": frozen.get("top_ticker"),
                "v9_local_replay_top_ticker": local_summary.get("top_ticker"),
                "top_ticker_match": top_ticker_match,
                "yearly_return_diff": annual_diff,
                "pass": bool(metric_close),
                "explanation": (
                    "local replay matches frozen v8.2 within audit tolerances"
                    if metric_close
                    else "material difference between v8.2 frozen loaded reproduction and independent v9 local replay; "
                    "likely due to local Alpha360 approximation/data-source or upstream score provenance and requires human review"
                ),
            }
        )
    return pd.DataFrame(rows)


def annual_diff_json(v8_2_annual: pd.DataFrame, local_annual: pd.DataFrame, strategy_id: str) -> str:
    frozen = v8_2_annual.loc[v8_2_annual["strategy_id"] == strategy_id, ["year", "year_return"]].copy()
    local = local_annual.loc[:, ["year", "year_return"]].copy()
    joined = frozen.merge(local, on="year", how="outer", suffixes=("_v8_2_frozen", "_v9_local"))
    joined["diff"] = joined["year_return_v9_local"].astype(float) - joined["year_return_v8_2_frozen"].astype(float)
    return joined.sort_values("year").to_json(orient="records", force_ascii=True)


def run_negative_controls(
    normal_pkg: ScorePackage,
    shuffled_pkg: ScorePackage,
    close: pd.DataFrame,
    dollar_volume: pd.DataFrame,
    primary_metrics: dict[str, Any],
    frozen_metrics: dict[str, Any],
) -> pd.DataFrame:
    controls: list[tuple[str, dict[pd.Timestamp, pd.DataFrame], str]] = []
    controls.append(("shuffled_label_within_train_window", shuffled_pkg.score_frames, "model refit after shuffling labels within each train window"))
    controls.append(("inverted_score_rank", transform_score_frames(normal_pkg.score_frames, "invert"), "rank scores ascending by negating original score"))
    controls.append(("one_month_stale_score", stale_score_frames(normal_pkg.score_frames), "use prior month score snapshot at current decision"))
    controls.append(("random_score_fixed_seed", random_score_frames(normal_pkg.score_frames, seed=42), "fixed-seed random score per decision/ticker"))

    rows: list[dict[str, Any]] = []
    primary_passes = bool(primary_metrics.get("cagr", 0.0) >= CORE_CAGR_GATE and primary_metrics.get("calmar", 0.0) >= CORE_CALMAR_GATE)
    for name, frames, note in controls:
        replay = replay_from_scores(
            universe_name=f"negative_control_{name}",
            score_frames=frames,
            top_k=5,
            close=close,
            dollar_volume=dollar_volume,
            execution_delay=1,
        )
        m = replay["summary"]
        passes_core = bool(m.get("cagr", 0.0) >= CORE_CAGR_GATE and m.get("calmar", 0.0) >= CORE_CALMAR_GATE)
        close_to_primary = bool(
            primary_passes
            and m.get("cagr", 0.0) >= 0.80 * float(primary_metrics.get("cagr", 0.0))
            and m.get("calmar", 0.0) >= 0.80 * float(primary_metrics.get("calmar", 0.0))
        )
        close_to_frozen = bool(
            m.get("cagr", 0.0) >= 0.80 * float(frozen_metrics.get("cagr", 0.0))
            and m.get("calmar", 0.0) >= 0.80 * float(frozen_metrics.get("calmar", 0.0))
        )
        rows.append(
            {
                "control_name": name,
                "note": note,
                "cagr": m.get("cagr"),
                "calmar": m.get("calmar"),
                "max_drawdown": m.get("max_drawdown"),
                "annual_turnover": m.get("annual_turnover"),
                "top_ticker": m.get("top_ticker"),
                "top_ticker_share": m.get("top_ticker_share"),
                "passes_core_gate": passes_core,
                "close_to_v9_local_primary": close_to_primary,
                "close_to_v8_2_frozen_pool_a": close_to_frozen,
                "leakage_or_backtest_bug_suspected": bool(passes_core or close_to_primary or close_to_frozen),
            }
        )
    return pd.DataFrame(rows)


def transform_score_frames(score_frames: dict[pd.Timestamp, pd.DataFrame], mode: str) -> dict[pd.Timestamp, pd.DataFrame]:
    out: dict[pd.Timestamp, pd.DataFrame] = {}
    for date, frame in score_frames.items():
        local = frame.copy()
        if mode == "invert":
            local["score"] = -pd.to_numeric(local["score"], errors="coerce")
        out[date] = local
    return out


def stale_score_frames(score_frames: dict[pd.Timestamp, pd.DataFrame]) -> dict[pd.Timestamp, pd.DataFrame]:
    out: dict[pd.Timestamp, pd.DataFrame] = {}
    previous: pd.DataFrame | None = None
    for date in sorted(score_frames):
        if previous is not None:
            local = previous.copy()
            local["decision_date"] = pd.Timestamp(date)
            out[pd.Timestamp(date)] = local
        previous = score_frames[date].copy()
    return out


def random_score_frames(score_frames: dict[pd.Timestamp, pd.DataFrame], seed: int) -> dict[pd.Timestamp, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    out: dict[pd.Timestamp, pd.DataFrame] = {}
    for date in sorted(score_frames):
        local = score_frames[date].copy()
        local["score"] = rng.normal(size=len(local))
        out[pd.Timestamp(date)] = local
    return out


def build_execution_timing_sensitivity(
    normal_pkg: ScorePackage,
    close: pd.DataFrame,
    dollar_volume: pd.DataFrame,
) -> pd.DataFrame:
    original = replay_from_scores(
        "execution_original_implementation",
        normal_pkg.score_frames,
        top_k=5,
        close=close,
        dollar_volume=dollar_volume,
        execution_delay=1,
    )
    decision_next = replay_from_scores(
        "execution_decision_close_to_next_close",
        normal_pkg.score_frames,
        top_k=5,
        close=close,
        dollar_volume=dollar_volume,
        execution_delay=0,
    )
    following = replay_from_scores(
        "execution_close_to_following_close",
        normal_pkg.score_frames,
        top_k=5,
        close=close,
        dollar_volume=dollar_volume,
        execution_delay=1,
    )
    no_shift_metrics, no_shift_returns, no_shift_turnover = evaluate_no_shift(
        original["close"],
        original["weights"],
        cost_bps=5.0,
        slippage_bps=5.0,
    )
    rows = [
        timing_row(
            "original implementation",
            original["summary"],
            "weights assigned on T+1 execution_date; portfolio_returns shifts weights one bar, so realized exposure starts from T+1 close to T+2 close",
            False,
        ),
        timing_row(
            "decision close to next close",
            decision_next["summary"],
            "diagnostic delay=0: decision-date weights shifted one bar, approximating T close to T+1 close",
            False,
        ),
        timing_row(
            "execution close to following close",
            following["summary"],
            "explicit T+1 close execution then following close return capture; matches original implementation",
            False,
        ),
        timing_row(
            "no-shift diagnostic only",
            {**no_shift_metrics, "annual_turnover": no_shift_metrics.get("annual_turnover", 0.0)},
            "invalid diagnostic: applies new execution-date weights to same close-to-close return without one-bar shift",
            True,
        ),
    ]
    rows[-1]["diagnostic_nav_end"] = float(nav_from_returns(no_shift_returns).iloc[-1]) if not no_shift_returns.empty else 1.0
    rows[-1]["diagnostic_turnover_sum"] = float(no_shift_turnover.sum()) if not no_shift_turnover.empty else 0.0
    return pd.DataFrame(rows)


def timing_row(name: str, metrics: dict[str, Any], interpretation: str, diagnostic_only: bool) -> dict[str, Any]:
    return {
        "timing_case": name,
        "implementation_interpretation": interpretation,
        "diagnostic_only": bool(diagnostic_only),
        "cagr": metrics.get("cagr"),
        "calmar": metrics.get("calmar"),
        "max_drawdown": metrics.get("max_drawdown"),
        "annual_turnover": metrics.get("annual_turnover"),
        "exposure": metrics.get("exposure"),
        "core_gate_pass": bool(metrics.get("cagr", 0.0) >= CORE_CAGR_GATE and metrics.get("calmar", 0.0) >= CORE_CALMAR_GATE),
    }


def evaluate_no_shift(close: pd.DataFrame, weights: pd.DataFrame, cost_bps: float, slippage_bps: float) -> tuple[dict[str, Any], pd.Series, pd.Series]:
    local_close = close.loc[weights.index.min() : weights.index.max(), weights.columns].ffill()
    local_weights = weights.reindex(local_close.index).ffill().fillna(0.0)
    asset_returns = local_close.pct_change(fill_method=None).fillna(0.0)
    gross = (local_weights * asset_returns).sum(axis=1)
    turnover = local_weights.diff().abs().sum(axis=1).fillna(local_weights.abs().sum(axis=1))
    cost = turnover * ((cost_bps + slippage_bps) / 10000.0)
    returns = (gross - cost).fillna(0.0)
    return compute_portfolio_metrics(returns, turnover, local_weights), returns, turnover


def build_benchmark(close: pd.DataFrame, pool_a_tickers: list[str]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    local = close.loc[START:END].ffill()
    for ticker in ["QQQ", "QLD", "TQQQ", "SPY"]:
        if ticker not in local.columns:
            continue
        returns = local[ticker].pct_change(fill_method=None).fillna(0.0)
        weights = pd.DataFrame({ticker: 1.0}, index=returns.index)
        turnover = pd.Series(0.0, index=returns.index)
        rows.append({"benchmark": f"{ticker} buy hold", "ticker_count": 1, **compute_portfolio_metrics(returns, turnover, weights)})
    pool_cols = [t for t in pool_a_tickers if t in local.columns]
    weights = pd.DataFrame(np.nan, index=local.index, columns=pool_cols, dtype=float)
    for date in month_end_dates(local.index, START, END):
        available = local.loc[date, pool_cols].dropna().index.astype(str).tolist()
        if available:
            weights.loc[date, available] = 1.0 / float(len(available))
    weights = weights.ffill().fillna(0.0)
    returns, turnover = portfolio_returns(local.loc[:, pool_cols], weights, cost_bps=5.0, slippage_bps=5.0)
    rows.append({"benchmark": "Pool A equal weight monthly", "ticker_count": len(pool_cols), **compute_portfolio_metrics(returns, turnover, weights)})
    return pd.DataFrame(rows)


def build_stress_test(local_top5: dict[str, Any], close: pd.DataFrame, v8_2_tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    weights = local_top5["weights"]
    local_close = local_top5["close"]
    for bps in [5, 10, 20, 50]:
        m, _, _ = evaluate(local_close, weights, cost_bps=float(bps), slippage_bps=float(bps))
        rows.append({"strategy_scope": "v9_local_pool_a_top5", "stress_type": "cost_slippage_bps", "cost_bps": bps, "slippage_bps": bps, **m})
    top_ticker = str(local_top5["summary"].get("top_ticker", ""))
    if top_ticker:
        m = remove_ticker_stress(local_close, weights, top_ticker)
        rows.append({"strategy_scope": "v9_local_pool_a_top5", "stress_type": "remove_top_ticker", "removed": top_ticker, **m})
    m_year, year, share = remove_top_year_stress(local_top5["returns"], weights)
    rows.append({"strategy_scope": "v9_local_pool_a_top5", "stress_type": "remove_top_contribution_year", "removed": year, "single_year_contribution_share": share, **m_year})
    rows.append(
        {
            "strategy_scope": "v9_local_pool_a_top5",
            "stress_type": "concentration_turnover_exposure",
            "top_ticker": local_top5["summary"].get("top_ticker"),
            "top_ticker_contribution_share": local_top5["summary"].get("top_ticker_share"),
            "single_year_contribution_share": local_top5["summary"].get("single_year_share"),
            "annual_turnover": local_top5["summary"].get("annual_turnover"),
            "exposure": local_top5["summary"].get("exposure"),
            "cagr": local_top5["summary"].get("cagr"),
            "calmar": local_top5["summary"].get("calmar"),
            "max_drawdown": local_top5["summary"].get("max_drawdown"),
        }
    )
    frozen_stress = v8_2_tables["stress"].loc[
        (v8_2_tables["stress"]["strategy_id"] == POOL_A_TOP5)
        & (v8_2_tables["stress"]["stress_type"].isin(["cost_bps", "execution_delay"]))
    ].copy()
    if not frozen_stress.empty:
        frozen_stress.insert(0, "strategy_scope", "v8_2_frozen_pool_a_top5")
        rows.extend(frozen_stress.head(20).to_dict("records"))
    return pd.DataFrame(rows)


def build_universe_policy_audit(v9_tables: dict[str, pd.DataFrame], pool_a_tickers: list[str]) -> pd.DataFrame:
    quality = v9_tables["quality"].copy()
    downloads = v9_tables["price_download"].copy()
    source_map = downloads.set_index("ticker")["source"].astype(str).to_dict() if not downloads.empty else {}
    mixed_sources = len(set(downloads.get("source", pd.Series(dtype=str)).dropna().astype(str))) > 1
    rows: list[dict[str, Any]] = []
    for _, row in quality.iterrows():
        ticker = str(row.get("ticker", "")).upper()
        in_pool = ticker in set(pool_a_tickers)
        v9_ready = bool(row.get("v9_ready", False))
        source = str(row.get("source", ""))
        baseline_only = bool(in_pool and not v9_ready)
        eligible_new = bool(v9_ready and (not in_pool) and "small_growth" in source)
        issue = []
        if baseline_only:
            issue.append("excluded_by_v9_data_quality_but_present_in_pool_a_reproduction")
        if in_pool and ticker in {"PLTR", "SNOW"}:
            issue.append("explicit_pltr_snow_pool_a_reproduction_exception")
        if "small_growth" in source and not in_pool:
            issue.append("manual_small_growth_candidate_static_selection_bias")
        if mixed_sources:
            issue.append("mixed_unified_store_yfinance_source_risk")
        rows.append(
            {
                "ticker": ticker,
                "source": source,
                "price_source": source_map.get(ticker, ""),
                "in_pool_a_reproduction": in_pool,
                "v9_ready": v9_ready,
                "v9_exclude_reason": row.get("exclude_reason", ""),
                "baseline_reproduction_only": baseline_only,
                "eligible_for_new_expansion": eligible_new,
                "static_manual_universe_bias": "static hand-built Pool A / small growth universe; not a broad investable universe sample",
                "mixed_unified_store_yfinance_data_source_risk": bool(mixed_sources),
                "policy_issue": ";".join(issue),
            }
        )
    return pd.DataFrame(rows).sort_values(["baseline_reproduction_only", "ticker"], ascending=[False, True])


def build_yearly_return_table(
    local_top5: dict[str, Any],
    local_top10: dict[str, Any],
    v8_2_tables: dict[str, pd.DataFrame],
    benchmark: pd.DataFrame,
) -> pd.DataFrame:
    rows = [
        local_top5["annual"].assign(series="v9_local_pool_a_top5"),
        local_top10["annual"].assign(series="v9_local_pool_a_top10"),
    ]
    frozen = v8_2_tables["annual"].loc[v8_2_tables["annual"]["strategy_id"].isin([POOL_A_TOP5, POOL_A_TOP10])].copy()
    if not frozen.empty:
        frozen["series"] = "v8_2_frozen_" + frozen["strategy_id"].astype(str)
        frozen = frozen.rename(columns={"strategy_id": "source_strategy_id"})
        rows.append(frozen)
    return pd.concat(rows, ignore_index=True, sort=False)


def build_attribution_table(local_top5: dict[str, Any], local_top10: dict[str, Any], v8_2_tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = [
        local_top5["ticker_contribution"].assign(series="v9_local_pool_a_top5"),
        local_top10["ticker_contribution"].assign(series="v9_local_pool_a_top10"),
    ]
    frozen = v8_2_tables["contribution"].loc[v8_2_tables["contribution"]["strategy_id"].isin([POOL_A_TOP5, POOL_A_TOP10])].copy()
    if not frozen.empty:
        frozen["series"] = "v8_2_frozen_" + frozen["strategy_id"].astype(str)
        rows.append(frozen)
    return pd.concat(rows, ignore_index=True, sort=False)


def build_score_rank_audit_table(score_frames: dict[pd.Timestamp, pd.DataFrame]) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for decision_date, frame in score_frames.items():
        local = frame.copy().sort_values("score", ascending=False)
        local["raw_rank"] = np.arange(1, len(local) + 1)
        local["decision_date"] = date_str(decision_date)
        local["feature_date"] = pd.to_datetime(local["feature_date"]).dt.date.astype(str)
        rows.append(local)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def build_reverse_audit_verdict(
    source_manifest: pd.DataFrame,
    time_alignment: pd.DataFrame,
    pool_a_replay_audit: pd.DataFrame,
    negative_controls: pd.DataFrame,
    benchmark: pd.DataFrame,
    stress: pd.DataFrame,
    universe_policy: pd.DataFrame,
) -> dict[str, Any]:
    sources_ok = bool(source_manifest["exists"].all())
    time_ok = bool(time_alignment["pass"].all()) if not time_alignment.empty else False
    pool_ok = bool(pool_a_replay_audit["pass"].all()) if not pool_a_replay_audit.empty else False
    neg_suspected = bool(negative_controls.get("leakage_or_backtest_bug_suspected", pd.Series(dtype=bool)).fillna(False).any())
    benchmark_ok = bool(not benchmark.empty and not stress.empty)
    data_policy_exception = bool(universe_policy["baseline_reproduction_only"].fillna(False).any()) if not universe_policy.empty else False
    requires_human = bool((not sources_ok) or (not time_ok) or (not pool_ok) or neg_suspected or data_policy_exception)
    classification = "invalid_or_needs_human_review" if requires_human else "not_v10_ready_growth_pool_sensitive"
    return {
        "stage": "v9_reverse_audit_no_expansion",
        "allow_enter_v10": False,
        "allow_expand_nasdaq100": False,
        "allow_expand_sp500": False,
        "allow_trade_execution": False,
        "classification": classification,
        "leakage_or_backtest_bug_suspected": bool(neg_suspected or (not time_ok)),
        "requires_human_review": requires_human,
        "required_sources_read": sources_ok,
        "time_alignment_pass": time_ok,
        "pool_a_replay_pass": pool_ok,
        "negative_controls_pass": not neg_suspected,
        "benchmark_stress_completed": benchmark_ok,
        "data_policy_exception_found": data_policy_exception,
        "no_nasdaq100_expansion": True,
        "no_sp500_expansion": True,
        "no_full_market_expansion": True,
        "no_v10": True,
        "no_strategy_search": True,
        "no_broker_api": True,
        "no_trade_execution": True,
        "reason": build_verdict_reason(time_ok, pool_ok, neg_suspected, data_policy_exception, benchmark_ok),
    }


def build_verdict_reason(time_ok: bool, pool_ok: bool, neg_suspected: bool, data_policy_exception: bool, benchmark_ok: bool) -> str:
    issues: list[str] = []
    if not time_ok:
        issues.append("time alignment or label-window audit failed")
    if not pool_ok:
        issues.append("v8.2 frozen Pool A result was not independently reproduced by v9 local replay")
    if neg_suspected:
        issues.append("negative control passed or approached primary/frozen performance")
    if data_policy_exception:
        issues.append("PLTR/SNOW or other v9-excluded tickers remain in baseline reproduction only")
    if not benchmark_ok:
        issues.append("benchmark/stress output missing")
    return "; ".join(issues) if issues else "reverse audit passed within configured evidence boundaries"


def frozen_strategy_row(results: pd.DataFrame, strategy_id: str) -> dict[str, Any]:
    row = results.loc[results["strategy_id"] == strategy_id]
    return row.iloc[0].to_dict() if not row.empty else {}


def universe_row(results: pd.DataFrame, universe_name: str) -> dict[str, Any]:
    row = results.loc[results["universe_name"] == universe_name]
    return row.iloc[0].to_dict() if not row.empty else {}
