"""v9 small tech-growth pool pre-research replay.

This module keeps the v8.2 strategy frozen:

- Alpha360 + LGBModel + label_5d
- monthly Top5 equal weight
- T+1 execution
- 5bps cost + 5bps slippage
- max single weight 20%
- YTD return cap 80%, derisk 100% after trigger

It does not expand Nasdaq100/S&P500, does not train a new model family, and
does not perform strategy search.  New growth tickers are audited and either
included in a bounded small-growth universe or explicitly excluded.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.pipeline import make_pipeline

from quant_lab.us_stock_selection.portfolio_robustifier import ticker_contributions
from quant_lab.us_stock_selection.qlib_signal_backtest import compute_portfolio_metrics, portfolio_returns
from quant_lab.us_stock_selection.utils import ensure_dir, nav_from_returns, save_dataframe, save_json
from quant_lab.us_stock_selection.v8_paper_trading import trading_offset
from quant_lab.us_stock_selection.v8_2_year_stability import concentration_share


START = pd.Timestamp("2024-01-01")
END = pd.Timestamp("2026-04-17")
TRAIN_START = pd.Timestamp("2020-01-02")
MIN_AVG_DOLLAR_VOLUME = 20_000_000.0
EXTREME_VOL_TICKERS = {"MSTR", "COIN", "PLTR", "AFRM", "ROKU"}


SMALL_GROWTH_CANDIDATES: dict[str, list[str]] = {
    "semiconductor": ["AVGO", "ARM", "ASML", "AMD", "MU", "INTC", "LRCX", "KLAC", "AMAT", "MRVL", "ON", "MPWR", "TSM"],
    "ai_software_cloud": ["ORCL", "CRM", "NOW", "ADBE", "SNOW", "DDOG", "NET", "MDB", "TEAM", "SHOP", "U", "APP", "PATH"],
    "cybersecurity": ["PANW", "CRWD", "ZS", "FTNT", "OKTA", "S"],
    "platform_internet": ["NFLX", "UBER", "ABNB", "DASH", "RBLX", "PINS", "SNAP", "SPOT"],
    "high_vol_theme": ["PLTR", "COIN", "MSTR", "ROKU", "SQ", "AFRM"],
}


@dataclass(frozen=True)
class UniverseSpec:
    universe_name: str
    tickers: list[str]
    top_k: int = 5
    method: str = "v9_local_alpha360_replay"


def run_v9_growth_pool(
    out_dir: Path | str,
    v8_2_run_dir: Path | str,
    v8_1_run_dir: Path | str,
    unified_store_dir: Path | str,
    logger: Any,
) -> dict[str, Any]:
    out = ensure_dir(out_dir)
    v8_2_dir = Path(v8_2_run_dir) / "v8_2_year_stability"
    v8_1_lgb_dir = Path(v8_1_run_dir) / "v8_1_model_switch" / "Alpha360_LGBModel"
    store = Path(unified_store_dir)
    audit_path = v8_1_lgb_dir / "score_rank_audit_trail.csv"
    if not audit_path.exists():
        raise FileNotFoundError(f"Missing v8.1 LGB audit trail: {audit_path}")
    pool_a_tickers = sorted(pd.read_csv(audit_path, usecols=["ticker"])["ticker"].astype(str).str.upper().unique().tolist())
    growth_table = build_growth_candidate_table(pool_a_tickers)
    save_dataframe(growth_table, out / "v9_requested_growth_universe.csv")

    requested = sorted(growth_table["ticker"].unique().tolist())
    price_data, download_audit = load_or_fetch_prices(requested, store, out / "downloaded_prices", logger)
    save_dataframe(download_audit, out / "v9_price_download_audit.csv")
    quality = audit_price_quality(growth_table, price_data)
    save_dataframe(quality, out / "v9_data_quality_audit.csv")
    excluded = quality.loc[~quality["v9_ready"]].copy()
    included = quality.loc[quality["v9_ready"]].copy()
    save_dataframe(excluded, out / "v9_excluded_tickers.csv")
    save_dataframe(included, out / "v9_effective_universe.csv")

    growth_ready = sorted(set(included.loc[included["source"] == "small_growth_candidate", "ticker"]) - set(pool_a_tickers))
    pool_ready = sorted(set(pool_a_tickers).intersection(set(included["ticker"])))
    combined = sorted(set(pool_ready).union(growth_ready))
    combined_no_extreme = [t for t in combined if t not in EXTREME_VOL_TICKERS]
    small_growth_only = sorted(growth_ready)

    universe_specs = [
        UniverseSpec("pool_a_v8_2_reproduction", pool_a_tickers, top_k=5, method="frozen_v8_2_score_audit"),
        UniverseSpec("pool_a_v8_2_reproduction_top10_control", pool_a_tickers, top_k=10, method="frozen_v8_2_score_audit"),
        UniverseSpec("pool_a_plus_small_growth", combined, top_k=5),
        UniverseSpec("pool_a_plus_small_growth_top10_control", combined, top_k=10),
        UniverseSpec("small_growth_only", small_growth_only, top_k=5),
        UniverseSpec("small_growth_only_top10_control", small_growth_only, top_k=10),
        UniverseSpec("pool_a_plus_small_growth_ex_extreme_vol", combined_no_extreme, top_k=5),
        UniverseSpec("pool_a_plus_small_growth_ex_extreme_vol_top10_control", combined_no_extreme, top_k=10),
    ]
    save_dataframe(
        pd.DataFrame(
            [
                {
                    "universe_name": spec.universe_name,
                    "top_k": spec.top_k,
                    "method": spec.method,
                    "ticker_count": len(spec.tickers),
                    "tickers": ",".join(spec.tickers),
                }
                for spec in universe_specs
            ]
        ),
        out / "v9_universe_definitions.csv",
    )

    local_tickers = sorted(set(combined).union({"SPY", "QQQ", "QLD", "TQQQ", "SHY"}))
    local_prices = {t: price_data[t] for t in local_tickers if t in price_data}
    close = build_panel(local_prices, "adj_close").loc[TRAIN_START:END].ffill()
    volume = build_panel(local_prices, "volume").loc[TRAIN_START:END].ffill()
    open_px = build_panel(local_prices, "open").loc[TRAIN_START:END].ffill()
    high = build_panel(local_prices, "high").loc[TRAIN_START:END].ffill()
    low = build_panel(local_prices, "low").loc[TRAIN_START:END].ffill()
    dollar_volume = close * volume
    logger.info(f"Building local Alpha360-compatible feature matrix for {len(local_tickers)} tickers.")
    features, feature_cols = build_local_alpha360_feature_frame(local_prices, tickers=local_tickers, start=TRAIN_START, end=END)
    save_dataframe(pd.DataFrame({"feature_column": feature_cols}), out / "v9_alpha360_feature_columns.csv")

    result_rows: list[dict[str, Any]] = []
    annual_rows: list[pd.DataFrame] = []
    ticker_rows: list[pd.DataFrame] = []
    holdings_rows: list[pd.DataFrame] = []
    trade_rows: list[pd.DataFrame] = []
    trigger_rows: list[pd.DataFrame] = []
    audit_rows: list[pd.DataFrame] = []
    daily_rows: list[pd.DataFrame] = []

    exact = load_v8_2_reproduction(v8_2_dir)
    for spec in universe_specs:
        logger.info(f"Running v9 universe {spec.universe_name} top{spec.top_k}, method={spec.method}")
        if spec.method == "frozen_v8_2_score_audit":
            exact_key = "top5_ytdcap80p_derisk100p" if spec.top_k == 5 else "top10_ytdcap80p_derisk100p"
            package = exact.get(exact_key)
            if package is None:
                logger.warning(f"Missing exact v8.2 strategy {exact_key}; skipping {spec.universe_name}.")
                continue
            row = dict(package["metrics"])
            row.update(
                {
                    "universe_name": spec.universe_name,
                    "ticker_count": len(spec.tickers),
                    "top_k": spec.top_k,
                    "method": spec.method,
                    "feature_set": "Alpha360",
                    "model": "LGBModel",
                    "label": "label_5d",
                    "portfolio": "top5_ytdcap80p_derisk100p" if spec.top_k == 5 else "top10_ytdcap80p_derisk100p_control",
                }
            )
            result_rows.append(row)
            annual_rows.append(package["annual"].assign(universe_name=spec.universe_name))
            ticker_rows.append(package["ticker_contribution"].assign(universe_name=spec.universe_name))
            holdings_rows.append(package["holdings"].assign(universe_name=spec.universe_name))
            trade_rows.append(build_trades_from_daily_weights(package["holdings"], close, spec.universe_name))
            trigger_rows.append(pd.DataFrame({"universe_name": [spec.universe_name], "trigger_date": [""], "note": ["loaded_from_v8_2_reproduction"]}))
            daily_rows.append(package["daily"].assign(universe_name=spec.universe_name))
            continue

        replay = run_local_lgb_replay(spec, features, feature_cols, close, dollar_volume)
        result_rows.append(replay["summary"])
        annual_rows.append(replay["annual"])
        ticker_rows.append(replay["ticker_contribution"])
        holdings_rows.append(replay["holdings"])
        trade_rows.append(replay["trades"])
        trigger_rows.append(replay["triggers"])
        audit_rows.append(replay["score_audit"])
        daily_rows.append(replay["daily"])

    results = pd.DataFrame(result_rows)
    if not results.empty:
        pool_row = results.loc[results["universe_name"] == "pool_a_v8_2_reproduction"].iloc[0].to_dict()
        results = add_gate_columns(results, pool_row)
        results = results.sort_values(["universe_name", "top_k"]).reset_index(drop=True)
    annual = pd.concat(annual_rows, ignore_index=True) if annual_rows else pd.DataFrame()
    ticker_contrib = pd.concat(ticker_rows, ignore_index=True) if ticker_rows else pd.DataFrame()
    holdings = pd.concat(holdings_rows, ignore_index=True) if holdings_rows else pd.DataFrame()
    trades = pd.concat(trade_rows, ignore_index=True) if trade_rows else pd.DataFrame()
    triggers = pd.concat(trigger_rows, ignore_index=True) if trigger_rows else pd.DataFrame()
    score_audit = pd.concat(audit_rows, ignore_index=True) if audit_rows else pd.DataFrame()
    daily = pd.concat(daily_rows, ignore_index=True) if daily_rows else pd.DataFrame()

    verdict = build_cycle_verdict(results, excluded, growth_ready)
    save_dataframe(results, out / "v9_growth_pool_results.csv")
    save_dataframe(annual, out / "v9_annual_return_table.csv")
    save_dataframe(ticker_contrib, out / "v9_ticker_contribution.csv")
    save_dataframe(holdings, out / "v9_monthly_holdings.csv")
    save_dataframe(trades, out / "v9_trades.csv")
    save_dataframe(triggers, out / "v9_ytd_cap_triggers.csv")
    save_dataframe(score_audit, out / "v9_score_rank_audit_trail.csv")
    save_dataframe(daily, out / "v9_daily_nav_by_universe.csv")
    save_json(verdict, out / "v9_cycle_verdict.json")
    return {
        "growth_table": growth_table,
        "quality": quality,
        "excluded": excluded,
        "included": included,
        "results": results,
        "annual": annual,
        "ticker_contribution": ticker_contrib,
        "holdings": holdings,
        "trades": trades,
        "triggers": triggers,
        "score_audit": score_audit,
        "daily": daily,
        "cycle_verdict": verdict,
    }


def build_growth_candidate_table(pool_a_tickers: list[str]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for ticker in pool_a_tickers:
        rows.append({"ticker": ticker, "category": "pool_a", "source": "pool_a", "is_pool_a": True, "is_small_growth_candidate": False})
    for category, tickers in SMALL_GROWTH_CANDIDATES.items():
        for ticker in tickers:
            rows.append(
                {
                    "ticker": ticker,
                    "category": category,
                    "source": "small_growth_candidate",
                    "is_pool_a": ticker in pool_a_tickers,
                    "is_small_growth_candidate": True,
                }
            )
    df = pd.DataFrame(rows).drop_duplicates("ticker", keep="first")
    # Preserve small-growth source when a duplicate appears after Pool A.
    small = {t for xs in SMALL_GROWTH_CANDIDATES.values() for t in xs}
    df.loc[df["ticker"].isin(small), "is_small_growth_candidate"] = True
    df.loc[df["ticker"].isin(small) & (df["source"] == "pool_a"), "source"] = "pool_a_and_small_growth_candidate"
    return df.sort_values(["source", "category", "ticker"]).reset_index(drop=True)


def load_or_fetch_prices(tickers: list[str], store: Path, download_dir: Path, logger: Any) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    ensure_dir(download_dir)
    rows: list[dict[str, Any]] = []
    out: dict[str, pd.DataFrame] = {}
    price_dir = store / "prices"
    for ticker in tickers:
        local = price_dir / f"{ticker}.parquet"
        if local.exists():
            try:
                df = pd.read_parquet(local)
                df["date"] = pd.to_datetime(df["date"])
                out[ticker] = normalize_price_frame(df, ticker, "unified_store")
                rows.append({"ticker": ticker, "source": "unified_store", "download_success": True, "error": "", "rows": len(out[ticker])})
                continue
            except Exception as exc:
                rows.append({"ticker": ticker, "source": "unified_store", "download_success": False, "error": str(exc), "rows": 0})
        try:
            df = fetch_yfinance(ticker)
            if df.empty:
                rows.append({"ticker": ticker, "source": "yfinance", "download_success": False, "error": "empty_download", "rows": 0})
                continue
            norm = normalize_price_frame(df, ticker, "yfinance_v9_download")
            norm.to_parquet(download_dir / f"{ticker}.parquet", index=False)
            out[ticker] = norm
            rows.append({"ticker": ticker, "source": "yfinance", "download_success": True, "error": "", "rows": len(norm)})
        except Exception as exc:
            logger.warning(f"yfinance download failed for {ticker}: {exc}")
            rows.append({"ticker": ticker, "source": "yfinance", "download_success": False, "error": str(exc), "rows": 0})
    return out, pd.DataFrame(rows)


def fetch_yfinance(ticker: str) -> pd.DataFrame:
    import yfinance as yf

    data = yf.download(ticker, start="1980-01-01", auto_adjust=False, actions=True, progress=False, threads=False)
    if data is None or data.empty:
        return pd.DataFrame()
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = [str(c[0]).lower().replace(" ", "_") for c in data.columns]
    else:
        data.columns = [str(c).lower().replace(" ", "_") for c in data.columns]
    data = data.reset_index().rename(columns={"Date": "date", "index": "date"})
    if "date" not in data.columns:
        data = data.rename(columns={data.columns[0]: "date"})
    return data


def normalize_price_frame(df: pd.DataFrame, ticker: str, source: str) -> pd.DataFrame:
    data = df.copy()
    data.columns = [str(c).lower().replace(" ", "_") for c in data.columns]
    if "adj_close" not in data.columns and "adj close" in data.columns:
        data["adj_close"] = data["adj close"]
    if "adj_close" not in data.columns and "adj_close_" in data.columns:
        data["adj_close"] = data["adj_close_"]
    for col in ["open", "high", "low", "close", "adj_close", "volume"]:
        if col not in data.columns:
            data[col] = np.nan
    data["date"] = pd.to_datetime(data["date"]).dt.tz_localize(None)
    data = data.sort_values("date").drop_duplicates("date", keep="last")
    data["ticker"] = ticker
    data["source"] = source
    return data.loc[:, ["date", "open", "high", "low", "close", "adj_close", "volume", "ticker", "source"]]


def audit_price_quality(growth_table: pd.DataFrame, price_data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, row in growth_table.iterrows():
        ticker = str(row["ticker"])
        df = price_data.get(ticker, pd.DataFrame())
        if df.empty:
            rows.append({**row.to_dict(), "v9_ready": False, "exclude_reason": "missing_price_data", "first_date": "", "last_date": "", "n_rows": 0})
            continue
        local = df.loc[(df["date"] >= TRAIN_START) & (df["date"] <= END)].copy()
        first = pd.to_datetime(df["date"]).min()
        last = pd.to_datetime(df["date"]).max()
        adj_missing = float(local["adj_close"].isna().mean()) if not local.empty else 1.0
        vol_missing = float(local["volume"].isna().mean()) if not local.empty else 1.0
        enough_history = first <= TRAIN_START
        latest_ok = last >= END
        enough_rows = len(local) >= 1000
        has_adj = bool(local["adj_close"].notna().any())
        has_volume = bool(local["volume"].notna().any())
        ready = bool(enough_history and latest_ok and enough_rows and has_adj and has_volume and adj_missing <= 0.05 and vol_missing <= 0.05)
        reasons = []
        if not enough_history:
            reasons.append("listed_after_2020_train_start")
        if not latest_ok:
            reasons.append("latest_data_before_v8_2_end")
        if not enough_rows:
            reasons.append("insufficient_rows_2020_2026")
        if not has_adj:
            reasons.append("missing_adj_close")
        if not has_volume:
            reasons.append("missing_volume")
        if adj_missing > 0.05:
            reasons.append("high_adj_close_missing_rate")
        if vol_missing > 0.05:
            reasons.append("high_volume_missing_rate")
        rows.append(
            {
                **row.to_dict(),
                "first_date": first.date().isoformat(),
                "last_date": last.date().isoformat(),
                "n_rows": int(len(local)),
                "adj_close_missing_rate": adj_missing,
                "volume_missing_rate": vol_missing,
                "v9_ready": ready,
                "exclude_reason": "" if ready else ";".join(reasons),
            }
        )
    return pd.DataFrame(rows)


def build_panel(price_data: dict[str, pd.DataFrame], field: str) -> pd.DataFrame:
    panels = {}
    for ticker, df in price_data.items():
        if field in df.columns:
            panels[ticker] = pd.Series(df[field].astype(float).to_numpy(), index=pd.to_datetime(df["date"]))
    if not panels:
        return pd.DataFrame()
    out = pd.DataFrame(panels).sort_index()
    out.index.name = "date"
    return out


def build_local_alpha360_feature_frame(price_data: dict[str, pd.DataFrame], tickers: list[str], start: pd.Timestamp, end: pd.Timestamp) -> tuple[pd.DataFrame, list[str]]:
    frames: list[pd.DataFrame] = []
    feature_cols = [f"f{i:04d}" for i in range(360)]
    for ticker in tickers:
        df = price_data.get(ticker)
        if df is None or df.empty:
            continue
        data = df.loc[(df["date"] >= start) & (df["date"] <= end)].copy().sort_values("date")
        if data.empty:
            continue
        ratio = (data["adj_close"].astype(float) / data["close"].replace(0, np.nan).astype(float)).replace([np.inf, -np.inf], np.nan).fillna(1.0)
        adj_close = data["adj_close"].astype(float)
        adj_open = data["open"].astype(float) * ratio
        adj_high = data["high"].astype(float) * ratio
        adj_low = data["low"].astype(float) * ratio
        volume = data["volume"].astype(float)
        daily_ret = adj_close.pct_change(fill_method=None)
        feats: dict[str, Any] = {}
        col_idx = 0
        for lag in range(60):
            base = adj_close.replace(0, np.nan)
            vol_base = volume.replace(0, np.nan)
            for series in [adj_close, adj_open, adj_high, adj_low]:
                feats[f"f{col_idx:04d}"] = (series.shift(lag) / base - 1.0).astype("float32")
                col_idx += 1
            feats[f"f{col_idx:04d}"] = (volume.shift(lag) / vol_base - 1.0).astype("float32")
            col_idx += 1
            feats[f"f{col_idx:04d}"] = daily_ret.shift(lag).astype("float32")
            col_idx += 1
        out = pd.DataFrame(feats)
        out.insert(0, "label_5d", (adj_close.shift(-6) / adj_close.shift(-1) - 1.0).astype("float32"))
        out.insert(0, "feature_set", "Alpha360")
        out.insert(0, "instrument", ticker)
        out.insert(0, "date", pd.to_datetime(data["date"]).to_numpy())
        frames.append(out)
    frame = pd.concat(frames, ignore_index=True).replace([np.inf, -np.inf], np.nan) if frames else pd.DataFrame()
    return frame, feature_cols


def run_local_lgb_replay(spec: UniverseSpec, features: pd.DataFrame, feature_cols: list[str], close: pd.DataFrame, dollar_volume: pd.DataFrame) -> dict[str, Any]:
    universe = [t for t in spec.tickers if t in close.columns]
    local_close = close.loc[:, close.columns.intersection(universe)].ffill()
    local_dv = dollar_volume.reindex(local_close.index).loc[:, local_close.columns].ffill()
    decision_dates = month_end_dates(local_close.index, START, END)
    weights = pd.DataFrame(np.nan, index=local_close.index, columns=local_close.columns, dtype=float)
    previous = pd.Series(0.0, index=local_close.columns)
    decision_rows: list[dict[str, Any]] = []
    holding_rows: list[dict[str, Any]] = []
    score_rows: list[pd.DataFrame] = []
    for decision_date in decision_dates:
        train_end = trading_offset(local_close.index, decision_date, -6)
        if pd.isna(train_end):
            continue
        feature_date = latest_feature_date(features, decision_date)
        if pd.isna(feature_date):
            continue
        train = features.loc[(features["instrument"].isin(universe)) & (features["date"] <= train_end) & features["label_5d"].notna()].copy()
        pred_frame = features.loc[(features["instrument"].isin(universe)) & (features["date"] == feature_date)].copy()
        if len(train) < 500 or pred_frame.empty:
            continue
        model = make_lgb_model()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model.fit(train[feature_cols], train["label_5d"].astype(float))
        pred = pred_frame.loc[:, ["date", "instrument"]].copy()
        pred["score"] = model.predict(pred_frame[feature_cols])
        tradable = tradable_universe(local_close, local_dv, pred["instrument"].astype(str).tolist(), decision_date)
        ranked = pred.loc[pred["instrument"].isin(tradable)].sort_values("score", ascending=False).reset_index(drop=True)
        selected = ranked.head(spec.top_k).copy()
        execution_date = trading_offset(local_close.index, decision_date, 1)
        if selected.empty or pd.isna(execution_date):
            continue
        current = pd.Series(0.0, index=local_close.columns)
        w = min(0.20, 1.0 / len(selected))
        current.loc[selected["instrument"].tolist()] = w
        if current.sum() > 0 and current.sum() < 0.999 and 0.20 >= 1.0 / len(selected):
            current = current / current.sum()
        weights.loc[execution_date] = current
        decision_rows.append(
            {
                "universe_name": spec.universe_name,
                "decision_date": date_str(decision_date),
                "feature_date": date_str(feature_date),
                "train_end_label_safe": date_str(train_end),
                "execution_date": date_str(execution_date),
                "selected_tickers": ",".join(selected["instrument"].tolist()),
                "selected_scores": ";".join(f"{r.instrument}:{r.score:.8f}" for r in selected.itertuples()),
                "tradable_count": int(len(tradable)),
                "train_rows": int(len(train)),
            }
        )
        for rank, row in enumerate(selected.itertuples(index=False), start=1):
            holding_rows.append(
                {
                    "universe_name": spec.universe_name,
                    "decision_date": date_str(decision_date),
                    "execution_date": date_str(execution_date),
                    "ticker": row.instrument,
                    "weight": float(current[row.instrument]),
                    "score": float(row.score),
                    "selected_rank": rank,
                }
            )
        audit = ranked.copy()
        audit["universe_name"] = spec.universe_name
        audit["decision_date"] = date_str(decision_date)
        audit["raw_rank"] = np.arange(1, len(audit) + 1)
        audit["selected_flag"] = audit["instrument"].isin(selected["instrument"])
        score_rows.append(audit.rename(columns={"instrument": "ticker", "score": "raw_score"}))
        previous = current

    weights = weights.ffill().fillna(0.0)
    overlay = apply_ytd_cap(weights, local_close, cap=0.80)
    weights = overlay["weights"]
    metrics, returns, turnover = evaluate(local_close, weights, cost_bps=5.0, slippage_bps=5.0)
    metrics_50, _, _ = evaluate(local_close, weights, cost_bps=50.0, slippage_bps=5.0)
    annual = yearly_returns(returns).assign(universe_name=spec.universe_name)
    contrib = ticker_contributions(local_close.loc[weights.index, weights.columns].ffill(), weights)
    top_ticker = str(contrib.iloc[0]["ticker"]) if not contrib.empty else ""
    top_ticker_share = float(contrib.iloc[0]["abs_share"]) if not contrib.empty else 0.0
    remove_ticker_metrics = remove_ticker_stress(local_close, weights, top_ticker)
    remove_year_metrics, top_year, top_year_share = remove_top_year_stress(returns, weights)
    summary = {
        "universe_name": spec.universe_name,
        "ticker_count": len(universe),
        "top_k": spec.top_k,
        "method": spec.method,
        "feature_set": "Alpha360",
        "model": "LGBModel",
        "label": "label_5d",
        "portfolio": "top5_ytdcap80p_derisk100p" if spec.top_k == 5 else "top10_ytdcap80p_derisk100p_control",
        "cost50_t1_cagr": metrics_50["cagr"],
        "cost50_t1_calmar": metrics_50["calmar"],
        "single_year_share": concentration_share(annual["year_return"]) if not annual.empty else 0.0,
        "top_contribution_year": top_year,
        "top_contribution_year_abs_share": top_year_share,
        "top_ticker": top_ticker,
        "top_ticker_share": top_ticker_share,
        "extreme_vol_contribution_share": float(contrib.loc[contrib["ticker"].isin(EXTREME_VOL_TICKERS), "abs_share"].sum()) if not contrib.empty else 0.0,
        "remove_top_year_cagr": remove_year_metrics.get("cagr", 0.0),
        "remove_top_year_calmar": remove_year_metrics.get("calmar", 0.0),
        "remove_top_ticker_cagr": remove_ticker_metrics.get("cagr", 0.0),
        "remove_top_ticker_calmar": remove_ticker_metrics.get("calmar", 0.0),
        "turnover": metrics.get("annual_turnover", 0.0),
        "exposure": overlay["avg_exposure"],
        "derisk_days_ratio": overlay["derisk_days_ratio"],
        **metrics,
    }
    daily = pd.DataFrame({"date": returns.index, "return": returns.values, "nav": nav_from_returns(returns).values, "turnover": turnover.values, "universe_name": spec.universe_name})
    holdings = weights.stack().rename("weight").reset_index()
    holdings.columns = ["date", "ticker", "weight"]
    holdings = holdings.loc[holdings["weight"].abs() > 1e-12].copy()
    holdings.insert(0, "universe_name", spec.universe_name)
    trades = build_trades_from_daily_weights(holdings, local_close, spec.universe_name)
    contrib.insert(0, "universe_name", spec.universe_name)
    score_audit = pd.concat(score_rows, ignore_index=True) if score_rows else pd.DataFrame()
    triggers = overlay["triggers"].assign(universe_name=spec.universe_name)
    return {
        "summary": summary,
        "annual": annual,
        "ticker_contribution": contrib,
        "holdings": holdings,
        "trades": trades,
        "triggers": triggers,
        "score_audit": score_audit,
        "daily": daily,
    }


def make_lgb_model():
    try:
        from lightgbm import LGBMRegressor

        return make_pipeline(
            SimpleImputer(strategy="median"),
            LGBMRegressor(
                n_estimators=80,
                learning_rate=0.05,
                num_leaves=31,
                subsample=0.85,
                colsample_bytree=0.85,
                random_state=42,
                n_jobs=4,
                verbosity=-1,
            ),
        )
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("LightGBM is required for v9 fixed LGBModel replay.") from exc


def apply_ytd_cap(weights: pd.DataFrame, close: pd.DataFrame, cap: float) -> dict[str, Any]:
    returns0, _ = portfolio_returns(close.loc[weights.index, weights.columns].ffill(), weights, cost_bps=0.0, slippage_bps=0.0)
    ytd = returns0.groupby(returns0.index.year).apply(lambda s: (1.0 + s).cumprod() - 1.0)
    if isinstance(ytd.index, pd.MultiIndex):
        ytd.index = ytd.index.get_level_values(-1)
    signal = ytd.shift(1).reindex(weights.index).fillna(0.0)
    scale = pd.Series(1.0, index=weights.index)
    scale.loc[signal > cap] = 0.0
    scaled = weights.mul(scale, axis=0).fillna(0.0)
    triggers = []
    for year, s in signal.groupby(signal.index.year):
        hit = s[s > cap]
        if not hit.empty:
            triggers.append({"year": int(year), "trigger_date": date_str(hit.index.min()), "cap": cap, "signal_value": float(hit.iloc[0])})
    exposure = scaled.sum(axis=1)
    return {"weights": scaled, "triggers": pd.DataFrame(triggers), "avg_exposure": float(exposure.mean()), "derisk_days_ratio": float((scale == 0.0).mean())}


def evaluate(close: pd.DataFrame, weights: pd.DataFrame, cost_bps: float, slippage_bps: float) -> tuple[dict[str, Any], pd.Series, pd.Series]:
    local_close = close.loc[weights.index.min() : weights.index.max(), weights.columns].ffill()
    weights = weights.reindex(local_close.index).ffill().fillna(0.0)
    returns, turnover = portfolio_returns(local_close, weights, cost_bps=cost_bps, slippage_bps=slippage_bps)
    return compute_portfolio_metrics(returns, turnover, weights), returns, turnover


def load_v8_2_reproduction(v8_2_dir: Path) -> dict[str, dict[str, pd.DataFrame | dict[str, Any]]]:
    results = pd.read_csv(v8_2_dir / "v8_2_year_stability_results.csv")
    daily = pd.read_csv(v8_2_dir / "v8_2_daily_nav_by_strategy.csv")
    holdings = pd.read_csv(v8_2_dir / "v8_2_monthly_holdings_by_strategy.csv")
    annual = pd.read_csv(v8_2_dir / "v8_2_annual_return_table.csv")
    contrib = pd.read_csv(v8_2_dir / "v8_2_ticker_contribution.csv")
    out: dict[str, dict[str, Any]] = {}
    for strategy_id in ["top5_ytdcap80p_derisk100p", "top10_ytdcap80p_derisk100p"]:
        row = results.loc[results["strategy_id"] == strategy_id]
        if row.empty:
            continue
        metrics = row.iloc[0].to_dict()
        out[strategy_id] = {
            "metrics": metrics,
            "daily": daily.loc[daily["strategy_id"] == strategy_id].drop(columns=["strategy_id"], errors="ignore"),
            "holdings": holdings.loc[holdings["strategy_id"] == strategy_id].drop(columns=["strategy_id"], errors="ignore"),
            "annual": annual.loc[annual["strategy_id"] == strategy_id].drop(columns=["strategy_id"], errors="ignore"),
            "ticker_contribution": contrib.loc[contrib["strategy_id"] == strategy_id].drop(columns=["strategy_id"], errors="ignore"),
        }
    return out


def add_gate_columns(results: pd.DataFrame, pool_row: dict[str, Any]) -> pd.DataFrame:
    drop_cols = [c for c in results.columns if c.startswith("gate_")] + ["v9_gate_pass", "classification"]
    out = results.drop(columns=[c for c in drop_cols if c in results.columns]).copy()
    pool_cagr = float(pool_row.get("cagr", 0.0))
    pool_calmar = float(pool_row.get("calmar", 0.0))
    gates = []
    for _, row in out.iterrows():
        is_target = row["universe_name"] == "pool_a_plus_small_growth" and int(row["top_k"]) == 5
        gate_map = {
            "gate_cagr_20": row.get("cagr", 0.0) >= 0.20,
            "gate_calmar_1": row.get("calmar", 0.0) >= 1.0,
            "gate_cost50_cagr_20": row.get("cost50_t1_cagr", 0.0) >= 0.20,
            "gate_cost50_calmar_1": row.get("cost50_t1_calmar", 0.0) >= 1.0,
            "gate_single_year_share_50": row.get("single_year_share", 1.0) <= 0.50,
            "gate_top_ticker_share_30": row.get("top_ticker_share", 1.0) <= 0.30,
            "gate_remove_top_year_cagr_20": row.get("remove_top_year_cagr", 0.0) >= 0.20,
            "gate_remove_top_year_calmar_1": row.get("remove_top_year_calmar", 0.0) >= 1.0,
            "gate_remove_top_ticker_cagr_20": row.get("remove_top_ticker_cagr", 0.0) >= 0.20,
            "gate_remove_top_ticker_calmar_1": row.get("remove_top_ticker_calmar", 0.0) >= 1.0,
            "gate_not_weaker_than_pool_a": row.get("cagr", 0.0) >= 0.80 * pool_cagr and row.get("calmar", 0.0) >= 0.80 * pool_calmar,
            "gate_not_extreme_vol_dependent": row.get("extreme_vol_contribution_share", 0.0) <= 0.40 and row.get("top_ticker_share", 0.0) <= 0.30,
        }
        allow = bool(is_target and all(gate_map.values()))
        gates.append({**gate_map, "gate_pass_count": int(sum(gate_map.values())), "v9_gate_pass": allow})
    gate_df = pd.DataFrame(gates)
    out = pd.concat([out.reset_index(drop=True), gate_df], axis=1)
    out["classification"] = np.where(out["v9_gate_pass"], "v10_ready_research_candidate", "not_v10_ready_growth_pool_sensitive")
    return out


def build_cycle_verdict(results: pd.DataFrame, excluded: pd.DataFrame, growth_ready: list[str]) -> dict[str, Any]:
    target = results.loc[(results["universe_name"] == "pool_a_plus_small_growth") & (results["top_k"] == 5)] if not results.empty else pd.DataFrame()
    row = target.iloc[0].to_dict() if not target.empty else {}
    allow = bool(row.get("v9_gate_pass", False))
    return {
        "stage": "v9_growth_pool_pre_research",
        "frozen_mainline": "Alpha360 + LGBModel + label_5d + top5_ytdcap80p_derisk100p",
        "allow_enter_v10": allow,
        "classification": "v10_ready_research_candidate" if allow else "not_v10_ready_growth_pool_sensitive",
        "pool_a_plus_small_growth_cagr": row.get("cagr"),
        "pool_a_plus_small_growth_calmar": row.get("calmar"),
        "pool_a_plus_small_growth_single_year_share": row.get("single_year_share"),
        "pool_a_plus_small_growth_top_ticker_share": row.get("top_ticker_share"),
        "effective_small_growth_count": len(growth_ready),
        "excluded_ticker_count": int(len(excluded)),
        "no_nasdaq100_expansion": True,
        "no_sp500_expansion": True,
        "no_full_market_expansion": True,
        "no_strategy_search": True,
        "no_trading_claim": True,
    }


def month_end_dates(index: pd.DatetimeIndex, start: pd.Timestamp, end: pd.Timestamp) -> list[pd.Timestamp]:
    idx = pd.DatetimeIndex(index).sort_values()
    idx = idx[(idx >= start) & (idx <= end)]
    positions = pd.Series(index=idx, data=np.arange(len(idx)))
    return [pd.Timestamp(idx[int(pos)]) for pos in positions.groupby(idx.to_period("M")).last().dropna().values]


def latest_feature_date(frame: pd.DataFrame, decision_date: pd.Timestamp) -> pd.Timestamp | pd.NaT:
    dates = pd.DatetimeIndex(frame.loc[frame["date"] <= decision_date, "date"].drop_duplicates().sort_values())
    return dates.max() if len(dates) else pd.NaT


def tradable_universe(close: pd.DataFrame, dollar_volume: pd.DataFrame, tickers: list[str], decision_date: pd.Timestamp) -> list[str]:
    out = []
    for ticker in tickers:
        if ticker not in close.columns:
            continue
        hist = dollar_volume[ticker].loc[:decision_date].tail(20)
        if len(hist) < 10 or float(hist.mean()) < MIN_AVG_DOLLAR_VOLUME:
            continue
        if pd.isna(close[ticker].loc[:decision_date].tail(1).iloc[0]):
            continue
        out.append(ticker)
    return out


def yearly_returns(returns: pd.Series) -> pd.DataFrame:
    s = returns.groupby(returns.index.year).apply(lambda x: float((1.0 + x).prod() - 1.0))
    return pd.DataFrame({"year": s.index.astype(int), "year_return": s.values})


def remove_ticker_stress(close: pd.DataFrame, weights: pd.DataFrame, ticker: str) -> dict[str, Any]:
    if not ticker or ticker not in weights.columns:
        return {}
    reduced = weights.copy()
    reduced[ticker] = 0.0
    return evaluate(close, reduced, cost_bps=5.0, slippage_bps=5.0)[0]


def remove_top_year_stress(returns: pd.Series, weights: pd.DataFrame) -> tuple[dict[str, Any], int | None, float]:
    yr = yearly_returns(returns)
    if yr.empty:
        return {}, None, 0.0
    top = yr.assign(abs_return=yr["year_return"].abs()).sort_values("abs_return", ascending=False).iloc[0]
    year = int(top["year"])
    local_returns = returns.loc[returns.index.year != year]
    local_weights = weights.loc[weights.index.year != year]
    if local_returns.empty:
        return {}, year, concentration_share(yr["year_return"])
    turnover = local_weights.diff().abs().sum(axis=1).fillna(local_weights.abs().sum(axis=1))
    return compute_portfolio_metrics(local_returns, turnover.reindex(local_returns.index).fillna(0.0), local_weights), year, concentration_share(yr["year_return"])


def build_trades_from_daily_weights(holdings: pd.DataFrame, close: pd.DataFrame, universe_name: str) -> pd.DataFrame:
    if holdings.empty:
        return pd.DataFrame()
    data = holdings.copy()
    data["date"] = pd.to_datetime(data["date"])
    weights = data.pivot_table(index="date", columns="ticker", values="weight", aggfunc="last").sort_index().fillna(0.0)
    all_idx = pd.DatetimeIndex(close.index.intersection(weights.index)).sort_values()
    weights = weights.reindex(all_idx).fillna(0.0)
    delta = weights.diff().fillna(weights)
    rows = []
    for date, row in delta.iterrows():
        for ticker, change in row[row.abs() > 1e-12].items():
            rows.append(
                {
                    "universe_name": universe_name,
                    "execution_date": date_str(date),
                    "ticker": ticker,
                    "delta_weight": float(change),
                    "target_weight": float(weights.loc[date, ticker]),
                    "price": float(close.loc[date, ticker]) if ticker in close.columns and date in close.index and pd.notna(close.loc[date, ticker]) else np.nan,
                }
            )
    return pd.DataFrame(rows)


def date_str(value: Any) -> str:
    return pd.Timestamp(value).date().isoformat() if pd.notna(value) else ""
