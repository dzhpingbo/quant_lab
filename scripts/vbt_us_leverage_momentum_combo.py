"""Momentum-factor combo search for TQQQ/QLD with vectorbt."""

from __future__ import annotations

import argparse
import json
import math
import os
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


OUT_ROOT = ROOT / "outputs" / "us_leveraged_etf_momentum_combo"
TARGETS = ("TQQQ", "QLD")
CONTEXT = ("SPY", "TLT", "SHY", "GLD", "IWM", "XLK", "SOXX", "SQQQ", "PSQ")

SOURCES = [
    {
        "name": "ProShares TQQQ",
        "url": "https://www.proshares.com/our-etfs/leveraged-and-inverse/tqqq",
        "use": "3x daily Nasdaq-100 exposure; drawdown and volatility filters are mandatory in scoring.",
    },
    {
        "name": "ProShares QLD",
        "url": "https://www.proshares.com/our-etfs/leveraged-and-inverse/qld",
        "use": "2x daily Nasdaq-100 exposure; tested separately because lower leverage changes the optimal trend horizon.",
    },
    {
        "name": "Leverage for the Long Run",
        "url": "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2741701",
        "use": "Tests leverage with trend following / moving-average risk management.",
    },
    {
        "name": "Faber Tactical Asset Allocation",
        "url": "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=962461",
        "use": "Motivates long-horizon moving-average timing as a baseline.",
    },
    {
        "name": "StockCharts MACD",
        "url": "https://school.stockcharts.com/doku.php?id=technical_indicators:moving_average_convergence_divergence_macd",
        "use": "MACD/EMA crossovers are included as momentum confirmation factors.",
    },
    {
        "name": "StockCharts ADX",
        "url": "https://school.stockcharts.com/doku.php?id=technical_indicators:average_directional_index_adx",
        "use": "ADX/+DI filters are used to require trend strength before holding leverage.",
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
    base.checkpoint(run_dir, stage, title, payload, next_step)


base.full_mod.checkpoint = checkpoint
base.full_mod.write_json = write_json


def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    diff = close.diff()
    up = diff.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    down = (-diff.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up.div(down.replace(0, np.nan)))


def adx_parts(frame: pd.DataFrame, n: int = 14) -> tuple[pd.Series, pd.Series, pd.Series]:
    high, low, close = frame["high"], frame["low"], frame["close"]
    plus_dm = (high.diff()).where((high.diff() > -low.diff()) & (high.diff() > 0), 0.0)
    minus_dm = (-low.diff()).where((-low.diff() > high.diff()) & (-low.diff() > 0), 0.0)
    tr = pd.concat([(high - low), (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / n, adjust=False).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1 / n, adjust=False).mean() / atr.replace(0, np.nan)
    minus_di = 100 * minus_dm.ewm(alpha=1 / n, adjust=False).mean() / atr.replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx = dx.ewm(alpha=1 / n, adjust=False).mean()
    return adx, plus_di, minus_di


def state(series: pd.Series, enter: float, exit_: float, name: str) -> pd.Series:
    held = False
    out = []
    for value in series.astype(float):
        if np.isnan(value):
            out.append(1.0 if held else 0.0)
            continue
        if not held and value >= enter:
            held = True
        elif held and value <= exit_:
            held = False
        out.append(1.0 if held else 0.0)
    return pd.Series(out, index=series.index, name=name)


def bool_state(cond: pd.Series, name: str) -> pd.Series:
    return cond.fillna(False).astype(float).rename(name)


def combine_and(parts: list[pd.Series], name: str) -> pd.Series:
    if not parts:
        raise ValueError("empty parts")
    out = parts[0].astype(bool)
    for part in parts[1:]:
        out = out & part.reindex(out.index).fillna(False).astype(bool)
    return out.astype(float).rename(name)


def weekly_ffill(cond: pd.Series, name: str) -> pd.Series:
    wk = cond.resample("W-FRI").last().reindex(cond.index, method="ffill")
    return wk.fillna(False).astype(float).rename(name)


def apply_cooldown(signal: pd.Series, cooldown: int, name: str) -> pd.Series:
    values = signal.fillna(0.0).to_numpy(dtype=float)
    out = np.zeros(len(values))
    block = 0
    prev = 0.0
    for i, value in enumerate(values):
        if prev > 0.5 and value <= 0.5:
            block = cooldown
        if block > 0 and value > 0.5:
            out[i] = 0.0
            block -= 1
        else:
            out[i] = value
            if block > 0:
                block -= 1
        prev = out[i]
    return pd.Series(out, index=signal.index, name=name)


def apply_trailing_stop(asset: pd.DataFrame, raw: pd.Series, stop: float, name: str) -> pd.Series:
    held = False
    peak = np.nan
    out = []
    for dt, want in raw.fillna(0.0).items():
        close = float(asset.loc[dt, "close"])
        if not held and want > 0.5:
            held = True
            peak = close
        elif held:
            peak = max(peak, close)
            if close <= peak * (1 - stop) or want <= 0.5:
                held = False
                peak = np.nan
        out.append(1.0 if held else 0.0)
    return pd.Series(out, index=raw.index, name=name)


def should_add_trailing_variant(candidate: Candidate) -> bool:
    name = candidate.name
    if candidate.family in {"multi_factor_momentum_score", "roc_stack_vol_filter", "macd_trend_combo", "ma_adx_momentum"}:
        return True
    if candidate.family == "ma_cross_momentum":
        return (
            ("_sma5_" in name or "_ema5_" in name or "_sma10_" in name or "_ema10_" in name or "_sma20_" in name)
            and ("_60_" in name or "_100_" in name or "_150_" in name or "_200_" in name)
            and ("band0.0050" in name or "band0.0100" in name)
        )
    if candidate.family in {"triple_ma_momentum", "breakout_momentum", "relative_momentum_risk_on"}:
        return True
    return False


def build_score_features(src: pd.DataFrame, qqq: pd.DataFrame, vix: pd.DataFrame) -> dict[str, pd.Series]:
    close = src["close"]
    macd = ema(close, 12) - ema(close, 26)
    macd_sig = ema(macd, 9)
    adx14, plus_di, minus_di = adx_parts(src, 14)
    vol20 = close.pct_change().rolling(20).std() * math.sqrt(252)
    vol_pct = vol20.rolling(252, min_periods=80).rank(pct=True)
    feats = {
        "ma5_20": sma(close, 5) > sma(close, 20),
        "ma10_50": sma(close, 10) > sma(close, 50),
        "ma20_60": sma(close, 20) > sma(close, 60),
        "ma50_150": sma(close, 50) > sma(close, 150),
        "close_ma100": close > sma(close, 100),
        "close_ma200": close > sma(close, 200),
        "ema12_26": ema(close, 12) > ema(close, 26),
        "macd_hist": macd > macd_sig,
        "roc20": close.pct_change(20) > 0,
        "roc60": close.pct_change(60) > 0,
        "roc120": close.pct_change(120) > 0,
        "rsi50": rsi(close, 14) > 50,
        "rsi_cap": rsi(close, 14) < 78,
        "adx_up": (adx14 > 15) & (plus_di > minus_di),
        "low_vol": vol_pct < 0.80,
        "qqq_ma200": qqq["close"] > sma(qqq["close"], 200),
        "qqq_roc60": qqq["close"].pct_change(60) > 0,
    }
    if "close" in vix:
        feats["vix25"] = vix["close"] < 25
        feats["vix30"] = vix["close"] < 30
    return feats


def build_candidates(target: str, data: Mapping[str, pd.DataFrame]) -> list[Candidate]:
    asset = data[target]
    index = asset.index
    qqq = base.align(data["QQQ"], index)
    spy = base.align(data.get("SPY", qqq), index)
    vix = base.align(data.get("_VIX", pd.DataFrame(index=index)), index)
    tlt = base.align(data.get("TLT", pd.DataFrame(index=index)), index)
    shy = base.align(data.get("SHY", pd.DataFrame(index=index)), index)
    asset = base.align(asset, index)
    candidates: list[Candidate] = []

    source_frames = [("asset", asset), ("qqq", qqq)]
    fasts = (3, 5, 8, 10, 13, 20, 30, 50)
    slows = (20, 40, 50, 60, 80, 100, 120, 150, 180, 200)
    for src_name, src in source_frames:
        close = src["close"]
        for ma_type in ("sma", "ema"):
            ma_func = sma if ma_type == "sma" else ema
            for fast in fasts:
                for slow in slows:
                    if fast >= slow:
                        continue
                    ratio = ma_func(close, fast) / ma_func(close, slow) - 1.0
                    for band in (0.0, 0.0025, 0.005, 0.01):
                        name = f"{src_name}_{ma_type}{fast}_{slow}_band{band:.4f}"
                        signal = state(ratio, band, -band, name)
                        candidates.append(Candidate(name, "ma_cross_momentum", "online_ma_crossover", signal, f"{src_name.upper()} {ma_type.upper()}{fast} crosses {ma_type.upper()}{slow}; includes whipsaw band {band:.2%}."))

        for f, m, s in ((5, 20, 60), (5, 30, 120), (10, 30, 100), (10, 50, 150), (20, 60, 180), (30, 80, 200)):
            name = f"{src_name}_triple_sma{f}_{m}_{s}"
            signal = combine_and([sma(close, f) > sma(close, m), sma(close, m) > sma(close, s)], name)
            candidates.append(Candidate(name, "triple_ma_momentum", "online_ma_crossover", signal, f"Layered trend: SMA{f} > SMA{m} > SMA{s}."))

        macd = ema(close, 12) - ema(close, 26)
        sig = ema(macd, 9)
        for long_ma in (100, 150, 200):
            name = f"{src_name}_macd_trend_ma{long_ma}"
            signal = combine_and([macd > sig, close > sma(close, long_ma), qqq["close"] > sma(qqq["close"], long_ma)], name)
            candidates.append(Candidate(name, "macd_trend_combo", "stockcharts_macd_plus_trend", signal, f"MACD bullish plus {src_name.upper()} and QQQ above SMA{long_ma}."))

        adx14, plus_di, minus_di = adx_parts(src, 14)
        for slow in (60, 100, 150, 200):
            for adx_min in (12, 15, 18, 22):
                name = f"{src_name}_sma5_{slow}_adx{adx_min}"
                signal = combine_and([sma(close, 5) > sma(close, slow), plus_di > minus_di, adx14 > adx_min], name)
                candidates.append(Candidate(name, "ma_adx_momentum", "stockcharts_adx_plus_ma", signal, f"SMA5>SMA{slow}, +DI>-DI, ADX>{adx_min}."))

    for src_name, src in source_frames:
        feats = build_score_features(src, qqq, vix)
        for threshold in (7, 8, 9, 10, 11, 12):
            for exit_threshold in (threshold - 2, threshold - 3):
                score = sum(series.astype(float) for series in feats.values())
                name = f"{src_name}_score_e{threshold}_x{exit_threshold}"
                signal = state(score, threshold, exit_threshold, name)
                candidates.append(Candidate(name, "multi_factor_momentum_score", "deep_momentum_combo", signal, f"Multi-factor momentum score enter >= {threshold}, exit <= {exit_threshold}; features={len(feats)}."))
                for cooldown in (3, 5, 10):
                    cname = f"{name}_cool{cooldown}"
                    candidates.append(Candidate(cname, "multi_factor_momentum_score_cooldown", "deep_momentum_combo", apply_cooldown(signal, cooldown, cname), f"Same score strategy with {cooldown}-day cooldown after exit."))

    for src_name, src in source_frames:
        close = src["close"]
        for weights in ((0.4, 0.35, 0.25), (0.2, 0.4, 0.4), (0.5, 0.3, 0.2)):
            mom = weights[0] * close.pct_change(20) + weights[1] * close.pct_change(60) + weights[2] * close.pct_change(120)
            vol = close.pct_change().rolling(20).std() * math.sqrt(252)
            for long_ma in (100, 150, 200):
                for vol_cap in (0.45, 0.55, 0.70, 0.90):
                    name = f"{src_name}_roc_stack_{int(weights[0]*10)}{int(weights[1]*10)}{int(weights[2]*10)}_ma{long_ma}_vol{int(vol_cap*100)}"
                    cond = (mom > 0) & (close > sma(close, long_ma)) & (vol < vol_cap) & (qqq["close"].pct_change(60) > 0)
                    candidates.append(Candidate(name, "roc_stack_vol_filter", "cross_period_momentum", bool_state(cond, name), f"Weighted ROC20/60/120 > 0, above SMA{long_ma}, vol<{vol_cap:.0%}, QQQ ROC60>0."))

    for long_ma in (100, 150, 180, 200):
        for vix_limit in (20, 22, 25, 28, 30, 35):
            if "close" not in vix:
                continue
            name = f"qqq_sma5_{long_ma}_vix{vix_limit}"
            signal = combine_and([sma(qqq["close"], 5) > sma(qqq["close"], long_ma), qqq["close"].pct_change(20) > 0, vix["close"] < vix_limit], name)
            candidates.append(Candidate(name, "qqq_short_long_vix", "leveraged_etf_momentum_vix", signal, f"QQQ SMA5>SMA{long_ma}, 20d momentum positive, VIX<{vix_limit}."))

    for ret_window in (63, 126, 189):
        for long_ma in (150, 200):
            name = f"qqq_vs_safe_ret{ret_window}_ma{long_ma}"
            safe = pd.concat([shy["close"].pct_change(ret_window), tlt["close"].pct_change(ret_window)], axis=1).max(axis=1)
            cond = (qqq["close"].pct_change(ret_window) > safe) & (qqq["close"] > sma(qqq["close"], long_ma))
            candidates.append(Candidate(name, "relative_momentum_risk_on", "relative_momentum", bool_state(cond, name), f"Hold when QQQ {ret_window}d momentum beats SHY/TLT and QQQ>SMA{long_ma}."))

    for src_name, src in source_frames:
        close = src["close"]
        for entry in (20, 40, 60, 80):
            for exit_ in (10, 20, 30):
                if exit_ >= entry:
                    continue
                high = src["high"].rolling(entry).max().shift(1)
                low = src["low"].rolling(exit_).min().shift(1)
                raw = state(pd.Series(np.where(close > high, 1.0, np.where(close < low, -1.0, np.nan)), index=index), 1, -1, f"{src_name}_breakout_{entry}_{exit_}")
                name = f"{src_name}_breakout_{entry}_{exit_}_roc"
                signal = combine_and([raw > 0.5, close.pct_change(20) > 0, qqq["close"] > sma(qqq["close"], 100)], name)
                candidates.append(Candidate(name, "breakout_momentum", "turtle_plus_momentum", signal, f"{entry}d breakout, {exit_}d exit, positive ROC20 and QQQ above SMA100."))

    expanded: list[Candidate] = []
    for c in candidates:
        sig = c.signal.reindex(index).ffill().fillna(0.0).clip(0, 1)
        expanded.append(Candidate(c.name, c.family, c.source, sig, c.notes))
        if should_add_trailing_variant(c):
            for stop in ((0.12, 0.18) if target == "TQQQ" else (0.08, 0.12)):
                sname = f"{c.name}_trail{int(stop * 100)}"
                expanded.append(Candidate(sname, c.family + "_trail_stop", c.source, apply_trailing_stop(asset, sig, stop, sname), c.notes + f" Trailing stop {stop:.0%}."))

    deduped: dict[str, Candidate] = {}
    for c in expanded:
        deduped[c.name] = c
    return list(deduped.values())


def score_row(row: Mapping[str, float], target: str) -> float:
    required = ("test_annual_return", "test_sharpe", "test_calmar", "full_annual_return", "full_sharpe", "full_calmar", "full_max_drawdown")
    if any(pd.isna(row.get(k, np.nan)) for k in required):
        return -999.0
    val = (
        0.27 * float(np.clip(row["test_calmar"], -4, 4))
        + 0.20 * float(np.clip(row["test_sharpe"], -3, 3))
        + 0.18 * float(np.clip(row["test_annual_return"], -1, 1.5))
        + 0.17 * float(np.clip(row["full_calmar"], -3, 3))
        + 0.10 * float(np.clip(row["full_sharpe"], -3, 3))
        + 0.08 * float(np.clip(row["full_annual_return"], -1, 1.2))
    )
    test_dd = float(row.get("test_max_drawdown", 0))
    full_dd = float(row.get("full_max_drawdown", 0))
    dd_soft = -0.32 if target == "QLD" else -0.42
    dd_hard = -0.43 if target == "QLD" else -0.50
    if test_dd < dd_soft:
        val -= 2.4 * (abs(test_dd) - abs(dd_soft))
    if full_dd < dd_hard:
        val -= 4.0 * (abs(full_dd) - abs(dd_hard))
    if row.get("full_annual_return", 0) < (0.18 if target == "QLD" else 0.28):
        val -= 0.25
    if row.get("full_exposure", 0) < 0.18:
        val -= 0.20
    if row.get("full_trades", 0) < 4:
        val -= 0.20
    return float(val)


def evaluate_target(target: str, data: Mapping[str, pd.DataFrame], run_dir: Path, train_end: str, test_start: str, next_open_date: str, fees: float) -> dict:
    asset = data[target]
    candidates = build_candidates(target, data)
    checkpoint(
        run_dir,
        f"02_candidates_{target}",
        f"{target} Momentum Candidate Checkpoint",
        {"target": target, "candidate_count": len(candidates), "families": sorted({c.family for c in candidates})},
        "Run vectorbt on all momentum-factor candidates.",
    )
    rows, results = [], {}
    for i, c in enumerate(candidates, 1):
        try:
            result = base.run_vbt(asset, c.signal, fees)
            train = base.metrics_from(result, None, train_end)
            test = base.metrics_from(result, test_start, None)
            full = base.metrics_from(result, None, None)
            row = {"target": target, "strategy": c.name, "family": c.family, "source": c.source, "notes": c.notes, "error": "", "latest_date": asset.index[-1].strftime("%Y-%m-%d")}
            for prefix, metrics in (("train", train), ("test", test), ("full", full)):
                for key, value in metrics.items():
                    row[f"{prefix}_{key}"] = value
            row["score"] = score_row(row, target)
            results[c.name] = result
        except Exception as exc:
            row = {"target": target, "strategy": c.name, "family": c.family, "source": c.source, "notes": c.notes, "error": f"{type(exc).__name__}: {exc}", "score": -999.0}
        rows.append(row)
        if i % 200 == 0:
            pd.DataFrame(rows).sort_values("score", ascending=False).to_csv(run_dir / f"{target}_partial_rank.csv", index=False, encoding="utf-8-sig")
    rank = pd.DataFrame(rows).sort_values("score", ascending=False)
    rank.to_csv(run_dir / f"{target}_strategy_rank.csv", index=False, encoding="utf-8-sig")
    rank.head(100).to_csv(run_dir / f"{target}_top100.csv", index=False, encoding="utf-8-sig")
    best = rank.iloc[0].to_dict()
    result = results[best["strategy"]]
    ops, trades = base.operations(target, asset, result, best["strategy"])
    ops.to_csv(run_dir / f"{target}_operation_points.csv", index=False, encoding="utf-8-sig")
    trades.to_csv(run_dir / f"{target}_trades.csv", index=False, encoding="utf-8-sig")
    sig = pd.DataFrame({
        "open": asset["open"],
        "close": asset["close"],
        "desired_after_close": result["desired"].astype(int),
        "position_at_open": result["position"].astype(int),
        "entry_at_open": result["entries"].astype(int),
        "exit_at_open": result["exits"].astype(int),
        "portfolio_value": result["value"],
        "portfolio_return": result["returns"],
    })
    sig.to_csv(run_dir / f"{target}_best_signal_nav.csv", encoding="utf-8-sig")
    action = base.next_action(target, asset, result, next_open_date)
    checkpoint(
        run_dir,
        f"03_best_{target}",
        f"{target} Momentum Best Checkpoint",
        {"best": best, "next_open_action": action, "operation_points_file": str(run_dir / f"{target}_operation_points.csv"), "trades_file": str(run_dir / f"{target}_trades.csv")},
        "Write the final momentum combo report.",
    )
    return {"target": target, "rank": rank, "best": best, "next_action": action, "operations": ops, "trades": trades, "signal_nav": sig}


def write_report(run_dir: Path, summaries: list[dict], status: pd.DataFrame, train_end: str, test_start: str, next_open_date: str, fees: float) -> None:
    rows = []
    for item in summaries:
        b, a = item["best"], item["next_action"]
        rows.append({
            "target": item["target"],
            "strategy": b["strategy"],
            "family": b["family"],
            "score": b["score"],
            "test_annual_return": b["test_annual_return"],
            "test_max_drawdown": b["test_max_drawdown"],
            "test_sharpe": b["test_sharpe"],
            "test_calmar": b["test_calmar"],
            "full_annual_return": b["full_annual_return"],
            "full_max_drawdown": b["full_max_drawdown"],
            "full_sharpe": b["full_sharpe"],
            "full_calmar": b["full_calmar"],
            "full_exposure": b["full_exposure"],
            "full_trades": b["full_trades"],
            "next_open_action": a["action"],
            "latest_signal_date": a["latest_signal_date"],
        })
    combined = pd.DataFrame(rows)
    combined.to_csv(run_dir / "best_strategy_summary.csv", index=False, encoding="utf-8-sig")
    lines = [
        "# TQQQ/QLD Momentum-Factor Combo VectorBT Report",
        "",
        f"- Run directory: `{run_dir}`",
        f"- Train ends: `{train_end}`; test starts: `{test_start}`",
        "- Execution: signal after close, trade at next open.",
        f"- One-way fee/slippage: `{fees:.4%}`",
        f"- Requested next open: `{next_open_date}`",
        "",
        "## Research Sources",
        "",
    ]
    for src in SOURCES:
        lines.append(f"- [{src['name']}]({src['url']}): {src['use']}")
    lines += ["", "## Data Status", "", base.md_table(status), "", "## Best Summary", "", base.md_table(combined)]
    for item in summaries:
        t, b, a = item["target"], item["best"], item["next_action"]
        lines += [
            "",
            f"## {t}",
            "",
            f"- Best strategy: `{b['strategy']}`",
            f"- Family/source: `{b['family']}` / `{b['source']}`",
            f"- Rule: {b.get('notes', '')}",
            f"- Test annual/maxDD/sharpe/calmar: {base.pct(b['test_annual_return'])} / {base.pct(b['test_max_drawdown'])} / {b['test_sharpe']:.3f} / {b['test_calmar']:.3f}",
            f"- Full annual/maxDD/sharpe/calmar: {base.pct(b['full_annual_return'])} / {base.pct(b['full_max_drawdown'])} / {b['full_sharpe']:.3f} / {b['full_calmar']:.3f}",
            f"- Exposure/trades: {base.pct(b['full_exposure'])} / {int(b['full_trades'])}",
            f"- Next open action: `{a['action']}` on `{a['next_open_date']}`, based on `{a['latest_signal_date']}`.",
            f"- Latest open/close: {a['latest_open']:.4f} / {a['latest_close']:.4f}",
            f"- Files: `{t}_strategy_rank.csv`, `{t}_top100.csv`, `{t}_operation_points.csv`, `{t}_trades.csv`, `{t}_best_signal_nav.csv`",
            "",
            "Recent operations:",
            "",
            base.md_table(item["operations"].tail(20)) if not item["operations"].empty else "_No operations._",
            "",
            "Recent trades:",
            "",
            base.md_table(item["trades"].tail(20)) if not item["trades"].empty else "_No trades._",
        ]
    (run_dir / "report.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    write_json(run_dir / "best_config.json", {"run_dir": str(run_dir), "train_end": train_end, "test_start": test_start, "next_open_date": next_open_date, "fees": fees, "sources": SOURCES, "best": rows})
    checkpoint(run_dir, "04_final_report", "Momentum Final Report Checkpoint", {"report": str(run_dir / "report.md"), "best_config": str(run_dir / "best_config.json"), "best_summary": rows}, "Review report and CSV trade points.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--today", default="2026-04-21")
    parser.add_argument("--train-end", default="2020-12-31")
    parser.add_argument("--test-start", default="2021-01-01")
    parser.add_argument("--next-open-date", default="2026-04-20")
    parser.add_argument("--fees", type=float, default=0.001)
    args = parser.parse_args()

    run_dir = OUT_ROOT / f"momentum_combo_{stamp()}"
    run_dir.mkdir(parents=True, exist_ok=True)
    checkpoint(run_dir, "00_sources", "Momentum Research Source Checkpoint", {"sources": SOURCES, "vectorbt_version": vbt.__version__}, "Update data and build momentum-factor candidates.")
    data, status, _ = base.full_mod.update_us_data(run_dir, today=args.today, context_symbols=CONTEXT)
    usable = {k: v for k, v in data.items() if v is not None and not v.empty}
    latest = min(v.index.max() for v in usable.values())
    for key in list(usable):
        usable[key] = usable[key].loc[usable[key].index <= latest].copy()
    summaries = [evaluate_target(t, usable, run_dir, args.train_end, args.test_start, args.next_open_date, args.fees) for t in TARGETS]
    write_report(run_dir, summaries, status, args.train_end, args.test_start, args.next_open_date, args.fees)
    print(run_dir)


if __name__ == "__main__":
    main()
