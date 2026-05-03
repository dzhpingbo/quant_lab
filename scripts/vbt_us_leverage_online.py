"""VectorBT search for online-inspired TQQQ/QLD timing strategies."""

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

import vectorbt as vbt

import research_us_leveraged_etf_full_strategy as full_mod

warnings.filterwarnings("ignore", category=FutureWarning)


OUT_ROOT = ROOT / "outputs" / "us_leveraged_etf_vectorbt_online_strategies"
TARGETS = ("TQQQ", "QLD")
CONTEXT = ("SPY", "TLT", "SHY", "GLD", "IWM", "XLK", "SOXX", "SQQQ", "PSQ")

ONLINE_SOURCES = [
    {
        "name": "ProShares TQQQ",
        "url": "https://www.proshares.com/our-etfs/leveraged-and-inverse/tqqq",
        "use": "TQQQ is a daily 3x Nasdaq-100 fund, so rules need drawdown controls.",
    },
    {
        "name": "ProShares QLD",
        "url": "https://www.proshares.com/our-etfs/leveraged-and-inverse/qld",
        "use": "QLD is a daily 2x Nasdaq-100 fund, tested separately from TQQQ.",
    },
    {
        "name": "Leverage for the Long Run",
        "url": "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2741701",
        "use": "Motivates pairing leveraged equity exposure with long-run trend filters.",
    },
    {
        "name": "CMT summary of Leverage for the Long Run",
        "url": "https://content.cmtassociation.org/a/leverage-for-the-long-run",
        "use": "Motivates risk-on/risk-off leverage instead of permanent leverage.",
    },
    {
        "name": "Alvarez UPRO/TQQQ leveraged ETF strategy",
        "url": "https://alvarezquanttrading.com/blog/upro-tqqq-leveraged-etf-strategy/",
        "use": "Motivates monthly risk-on/risk-off variants for leveraged ETFs.",
    },
    {
        "name": "Faber tactical asset allocation",
        "url": "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=962461",
        "use": "Motivates the 10-month/200-day moving-average baseline.",
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


def jclean(value):
    if value is None:
        return None
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    return value


def jready(obj):
    if isinstance(obj, dict):
        return {str(k): jready(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [jready(v) for v in obj]
    if isinstance(obj, tuple):
        return [jready(v) for v in obj]
    return jclean(obj)


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(jready(data), ensure_ascii=False, indent=2), encoding="utf-8")


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
            lines += [f"### {key}", "", "```json", json.dumps(jready(value), ensure_ascii=False, indent=2), "```", ""]
        else:
            lines.append(f"- {key}: {value}")
    (run_dir / f"checkpoint_{stage}.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


full_mod.checkpoint = checkpoint
full_mod.write_json = write_json


def pct(value) -> str:
    return "nan" if value is None or pd.isna(value) else f"{float(value) * 100:.2f}%"


def md_table(df: pd.DataFrame) -> str:
    if df is None or df.empty:
        return "_Empty._"
    small = df.copy()
    for col in small.columns:
        small[col] = small[col].map(lambda x: "" if pd.isna(x) else str(x).replace("|", "/"))
    header = "| " + " | ".join(map(str, small.columns)) + " |"
    sep = "| " + " | ".join(["---"] * len(small.columns)) + " |"
    rows = ["| " + " | ".join(row) + " |" for row in small.astype(str).to_numpy()]
    return "\n".join([header, sep, *rows])


def align(frame: pd.DataFrame, index: pd.Index) -> pd.DataFrame:
    return frame.reindex(index).ffill()


def direct(cond: pd.Series, name: str) -> pd.Series:
    return cond.fillna(False).astype(float).rename(name)


def band_signal(close: pd.Series, basis: pd.Series, enter: float, exit_: float, name: str) -> pd.Series:
    held = False
    out = []
    for c, b in zip(close.astype(float), basis.astype(float)):
        if np.isnan(c) or np.isnan(b):
            out.append(1.0 if held else 0.0)
            continue
        if (not held) and c >= b * enter:
            held = True
        elif held and c <= b * exit_:
            held = False
        out.append(1.0 if held else 0.0)
    return pd.Series(out, index=close.index, name=name)


def monthly(raw: pd.Series, name: str) -> pd.Series:
    months = pd.Series(raw.index, index=raw.index).dt.to_period("M")
    month_end = months.ne(months.shift(-1))
    return raw.where(month_end).ffill().fillna(0.0).astype(float).rename(name)


def run_vbt(asset: pd.DataFrame, signal: pd.Series, fees: float) -> dict:
    index = asset.index
    price = asset["open"].astype(float).ffill()
    desired = signal.reindex(index).ffill().fillna(0.0).astype(float) > 0.5
    position = desired.shift(1).fillna(False).astype(bool)
    prev = position.shift(1).fillna(False).astype(bool)
    entries = position & ~prev
    exits = ~position & prev
    pf = vbt.Portfolio.from_signals(
        price,
        entries=entries,
        exits=exits,
        init_cash=1.0,
        fees=fees,
        direction="longonly",
        freq="1D",
    )
    return {
        "value": pd.Series(np.asarray(pf.value()).reshape(-1), index=index),
        "returns": pd.Series(np.asarray(pf.returns()).reshape(-1), index=index),
        "desired": desired,
        "position": position,
        "entries": entries,
        "exits": exits,
    }


def metrics_from(result: dict, start: str | None = None, end: str | None = None) -> dict:
    ret = result["returns"].copy()
    pos = result["position"].copy()
    entries = result["entries"].copy()
    if start:
        mask = ret.index >= pd.Timestamp(start)
        ret, pos, entries = ret.loc[mask], pos.loc[mask], entries.loc[mask]
    if end:
        mask = ret.index <= pd.Timestamp(end)
        ret, pos, entries = ret.loc[mask], pos.loc[mask], entries.loc[mask]
    ret = ret.dropna()
    if ret.empty:
        return {"total_return": np.nan, "annual_return": np.nan, "sharpe": np.nan, "sortino": np.nan, "max_drawdown": np.nan, "calmar": np.nan, "exposure": np.nan, "trades": 0, "years": 0.0}
    nav = (1.0 + ret.fillna(0.0)).cumprod()
    nav.iloc[0] = 1.0
    years = len(ret) / 252.0
    total = float(nav.iloc[-1] - 1.0)
    ann = (1 + total) ** (1 / years) - 1 if years > 0 and total > -1 else np.nan
    sd = float(ret.std(ddof=0))
    sharpe = float(ret.mean() / sd * math.sqrt(252)) if sd > 0 else np.nan
    downside = ret[ret < 0]
    sortino = float(ret.mean() / downside.std(ddof=0) * math.sqrt(252)) if len(downside) and downside.std(ddof=0) > 0 else np.nan
    dd = nav / nav.cummax() - 1.0
    max_dd = float(dd.min())
    calmar = float(ann / abs(max_dd)) if max_dd < 0 and not pd.isna(ann) else np.nan
    return {
        "total_return": total,
        "annual_return": ann,
        "sharpe": sharpe,
        "sortino": sortino,
        "max_drawdown": max_dd,
        "calmar": calmar,
        "exposure": float(pos.reindex(ret.index).fillna(False).mean()),
        "trades": int(entries.reindex(ret.index).fillna(False).sum()),
        "years": years,
    }


def score(row: Mapping[str, float], target: str) -> float:
    needed = ("test_annual_return", "test_sharpe", "test_calmar", "full_annual_return", "full_calmar", "full_max_drawdown")
    if any(pd.isna(row.get(k, np.nan)) for k in needed):
        return -999.0
    val = (
        0.32 * float(np.clip(row["test_calmar"], -3, 3))
        + 0.22 * float(np.clip(row["full_calmar"], -2, 2.5))
        + 0.18 * float(np.clip(row["test_sharpe"], -3, 3))
        + 0.12 * float(np.clip(row["full_sharpe"], -3, 3))
        + 0.10 * float(np.clip(row["test_annual_return"], -1, 1.2))
        + 0.06 * float(np.clip(row["full_annual_return"], -1, 1))
    )
    dd_limit = -0.38 if target == "TQQQ" else -0.28
    hard_limit = -0.50 if target == "TQQQ" else -0.38
    if row.get("test_max_drawdown", 0) < dd_limit:
        val -= 2.2 * (abs(row["test_max_drawdown"]) - abs(dd_limit))
    if row.get("full_max_drawdown", 0) < hard_limit:
        val -= 1.2 * (abs(row["full_max_drawdown"]) - abs(hard_limit))
    if row.get("full_exposure", 0) < 0.18:
        val -= 0.35
    if row.get("full_exposure", 0) < 0.40:
        val -= 0.22
    if row.get("full_annual_return", 0) < 0.15:
        val -= 0.35
    if row.get("full_trades", 0) < 2:
        val -= 0.25
    return float(val)


def risk_score_signal(data: Mapping[str, pd.DataFrame], index: pd.Index, vix_limit: float, min_score: int, use_monthly: bool, name: str) -> pd.Series:
    qqq = align(data["QQQ"], index)
    spy = align(data.get("SPY", qqq), index)
    vix = align(data.get("_VIX", pd.DataFrame(index=index)), index)
    tlt = align(data.get("TLT", pd.DataFrame(index=index)), index)
    shy = align(data.get("SHY", pd.DataFrame(index=index)), index)
    s = pd.Series(0.0, index=index)
    s += (qqq["close"] > qqq["close"].rolling(200).mean()).astype(float)
    s += (spy["close"] > spy["close"].rolling(200).mean()).astype(float)
    if "close" in vix:
        s += (vix["close"] <= vix_limit).astype(float)
    s += (qqq["close"].pct_change(63) > 0).astype(float)
    if "close" in tlt and "close" in shy:
        s += (tlt["close"].pct_change(63) >= shy["close"].pct_change(63)).astype(float)
    raw = direct(s >= min_score, name)
    return monthly(raw, name) if use_monthly else raw


def build_candidates(target: str, data: Mapping[str, pd.DataFrame]) -> list[Candidate]:
    asset = data[target]
    index = asset.index
    qqq = align(data["QQQ"], index)
    spy = align(data.get("SPY", qqq), index)
    vix = align(data.get("_VIX", pd.DataFrame(index=index)), index)
    asset = align(asset, index)
    out: list[Candidate] = [
        Candidate("buy_hold", "baseline", "local_baseline", pd.Series(1.0, index=index), "Always hold target ETF.")
    ]

    sources = [
        ("qqq", qqq, "online_200dma_qld_tqqq"),
        ("spy", spy, "online_lflr_spy_filter"),
        ("asset", asset, "local_asset_trend"),
    ]
    for src_name, src, src_ref in sources:
        for window in (100, 125, 150, 180, 200, 220, 250):
            ma = src["close"].rolling(window).mean()
            name = f"{src_name}_sma{window}"
            out.append(Candidate(name, "trend_sma", src_ref, direct(src["close"] > ma, name), f"Hold when {src_name.upper()} close is above SMA{window}."))
            for b in (0.005, 0.01, 0.02, 0.03):
                name = f"{src_name}_sma{window}_band{b:.3f}"
                out.append(Candidate(name, "trend_sma_hysteresis", src_ref, band_signal(src["close"], ma, 1 + b, 1 - b, name), f"Buy above SMA{window}+{b:.1%}, sell below SMA{window}-{b:.1%}."))

    for fast, slow in ((20, 100), (30, 150), (50, 150), (50, 200), (80, 200), (100, 200)):
        name = f"qqq_sma{fast}_{slow}"
        out.append(Candidate(name, "trend_fast_slow", "online_200dma_qld_tqqq", direct(qqq["close"].rolling(fast).mean() > qqq["close"].rolling(slow).mean(), name), f"Hold when QQQ SMA{fast} is above SMA{slow}."))

    if "close" in vix:
        for window in (100, 150, 180, 200, 220, 250):
            ma = qqq["close"].rolling(window).mean()
            for limit in (18, 20, 22, 25, 28, 30, 35):
                cond = (qqq["close"] > ma) & (vix["close"] <= limit)
                name = f"qqq_sma{window}_vix{limit}"
                out.append(Candidate(name, "trend_vix_gate", "online_lflr_vix_gate", direct(cond, name), f"Hold when QQQ > SMA{window} and VIX <= {limit}."))
                name = f"qqq_sma{window}_vix{limit}_monthly"
                out.append(Candidate(name, "monthly_trend_vix_gate", "alvarez_style_monthly_risk_on", monthly(direct(cond, name), name), f"Month-end update: QQQ > SMA{window} and VIX <= {limit}."))

    for min_s in (3, 4, 5):
        for limit in (22, 25, 30, 35):
            for use_monthly in (False, True):
                name = f"risk_score{min_s}_vix{limit}" + ("_monthly" if use_monthly else "")
                out.append(Candidate(name, "risk_score", "alvarez_lflr_style_risk_score", risk_score_signal(data, index, limit, min_s, use_monthly, name), "Score: QQQ trend, SPY trend, VIX gate, QQQ 63d momentum, TLT-vs-SHY momentum."))

    for src_name, src in (("qqq", qqq), ("asset", asset)):
        for window, k in ((20, 0.3), (20, 0.5), (40, 0.3), (40, 0.5), (60, 0.3)):
            name = f"{src_name}_dual_thrust_w{window}_k{k:.1f}"
            out.append(Candidate(name, "breakout_dual_thrust", "rqalpha_dual_thrust_template", full_mod.dual_thrust_signal(src, window, k, name), "Stateful Dual Thrust breakout."))
        for entry, exit_ in ((20, 10), (40, 20), (55, 20), (80, 30)):
            name = f"{src_name}_turtle_e{entry}_x{exit_}"
            out.append(Candidate(name, "breakout_turtle", "turtle_breakout_template", full_mod.turtle_signal(src, entry, exit_, name), "Classic breakout hold-above-channel rule."))
        for fast, slow, sig in ((12, 26, 9), (20, 50, 10), (30, 80, 15)):
            name = f"{src_name}_macd_{fast}_{slow}_{sig}"
            out.append(Candidate(name, "trend_macd", "local_momentum_template", full_mod.macd_signal(src, fast, slow, sig, name), "Hold when MACD is above trigger."))

    for window in (2, 3, 5, 10, 14):
        for enter, exit_ in ((20, 55), (25, 55), (30, 60), (35, 65), (40, 70)):
            name = f"asset_rsi{window}_e{enter}_x{exit_}"
            out.append(Candidate(name, "mean_reversion_rsi", "local_rsi_template", full_mod.rsi_signal(asset, window, enter, exit_, name), f"Buy after RSI{window} <= {enter}, exit after RSI >= {exit_}."))

    deduped = {}
    for c in out:
        sig = c.signal.reindex(index).ffill().fillna(0.0).clip(0, 1)
        deduped[c.name] = Candidate(c.name, c.family, c.source, sig, c.notes)
    return list(deduped.values())


def operations(target: str, asset: pd.DataFrame, result: dict, strategy: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    for date in asset.index:
        if bool(result["entries"].get(date, False)):
            rows.append({"target": target, "strategy": strategy, "date": date.strftime("%Y-%m-%d"), "action": "BUY_OPEN", "open": float(asset.loc[date, "open"]), "close": float(asset.loc[date, "close"]), "position_after_open": 1})
        if bool(result["exits"].get(date, False)):
            rows.append({"target": target, "strategy": strategy, "date": date.strftime("%Y-%m-%d"), "action": "SELL_OPEN", "open": float(asset.loc[date, "open"]), "close": float(asset.loc[date, "close"]), "position_after_open": 0})
    ops = pd.DataFrame(rows)
    pairs, entry = [], None
    for row in rows:
        if row["action"] == "BUY_OPEN":
            entry = row
        elif row["action"] == "SELL_OPEN" and entry is not None:
            pairs.append({"target": target, "strategy": strategy, "entry_date": entry["date"], "entry_open": entry["open"], "exit_date": row["date"], "exit_open": row["open"], "trade_return": row["open"] / entry["open"] - 1.0, "holding_days": (pd.Timestamp(row["date"]) - pd.Timestamp(entry["date"])).days})
            entry = None
    if entry is not None:
        last = asset.index[-1]
        pairs.append({"target": target, "strategy": strategy, "entry_date": entry["date"], "entry_open": entry["open"], "exit_date": "", "exit_open": np.nan, "trade_return": asset.loc[last, "close"] / entry["open"] - 1.0, "holding_days": (last - pd.Timestamp(entry["date"])).days})
    return ops, pd.DataFrame(pairs)


def next_action(target: str, asset: pd.DataFrame, result: dict, next_open_date: str) -> dict:
    last = asset.index[-1]
    desired = bool(result["desired"].iloc[-1])
    current = bool(result["position"].iloc[-1])
    if desired and not current:
        action = "BUY_NEXT_OPEN"
    elif desired and current:
        action = "HOLD_OR_KEEP_LONG"
    elif (not desired) and current:
        action = "SELL_NEXT_OPEN"
    else:
        action = "STAY_CASH"
    return {"target": target, "latest_signal_date": last.strftime("%Y-%m-%d"), "next_open_date": next_open_date, "current_position_at_latest_open": int(current), "desired_position_next_open": int(desired), "action": action, "latest_open": float(asset.loc[last, "open"]), "latest_close": float(asset.loc[last, "close"])}


def evaluate_target(target: str, data: Mapping[str, pd.DataFrame], run_dir: Path, train_end: str, test_start: str, next_open_date: str, fees: float) -> dict:
    asset = data[target]
    candidates = build_candidates(target, data)
    checkpoint(run_dir, f"02_candidates_{target}", f"{target} Candidate Checkpoint", {"target": target, "candidate_count": len(candidates), "families": sorted({c.family for c in candidates})}, "Run vectorbt on every candidate and rank by return/drawdown robustness.")
    rows, results = [], {}
    for i, c in enumerate(candidates, 1):
        try:
            result = run_vbt(asset, c.signal, fees)
            train, test, full = metrics_from(result, None, train_end), metrics_from(result, test_start, None), metrics_from(result, None, None)
            row = {"target": target, "strategy": c.name, "family": c.family, "source": c.source, "notes": c.notes, "error": "", "latest_date": asset.index[-1].strftime("%Y-%m-%d")}
            for prefix, met in (("train", train), ("test", test), ("full", full)):
                for key, value in met.items():
                    row[f"{prefix}_{key}"] = value
            row["score"] = score(row, target)
            results[c.name] = result
        except Exception as exc:
            row = {"target": target, "strategy": c.name, "family": c.family, "source": c.source, "notes": c.notes, "error": f"{type(exc).__name__}: {exc}", "score": -999.0}
        rows.append(row)
        if i % 40 == 0:
            pd.DataFrame(rows).sort_values("score", ascending=False).to_csv(run_dir / f"{target}_partial_rank.csv", index=False, encoding="utf-8-sig")
    rank = pd.DataFrame(rows).sort_values("score", ascending=False)
    rank.to_csv(run_dir / f"{target}_strategy_rank.csv", index=False, encoding="utf-8-sig")
    rank.head(50).to_csv(run_dir / f"{target}_top50.csv", index=False, encoding="utf-8-sig")
    best = rank.iloc[0].to_dict()
    result = results[best["strategy"]]
    ops, trades = operations(target, asset, result, best["strategy"])
    ops.to_csv(run_dir / f"{target}_operation_points.csv", index=False, encoding="utf-8-sig")
    trades.to_csv(run_dir / f"{target}_trades.csv", index=False, encoding="utf-8-sig")
    sig = pd.DataFrame({"open": asset["open"], "close": asset["close"], "desired_after_close": result["desired"].astype(int), "position_at_open": result["position"].astype(int), "entry_at_open": result["entries"].astype(int), "exit_at_open": result["exits"].astype(int), "portfolio_value": result["value"], "portfolio_return": result["returns"]})
    sig.to_csv(run_dir / f"{target}_best_signal_nav.csv", encoding="utf-8-sig")
    action = next_action(target, asset, result, next_open_date)
    checkpoint(run_dir, f"03_best_{target}", f"{target} Best Strategy Checkpoint", {"best": best, "next_open_action": action, "operation_points_file": str(run_dir / f"{target}_operation_points.csv"), "trades_file": str(run_dir / f"{target}_trades.csv")}, "Write combined final report.")
    return {"target": target, "rank": rank, "best": best, "next_action": action, "operations": ops, "trades": trades, "signal_nav": sig}


def write_report(run_dir: Path, summaries: list[dict], data_status: pd.DataFrame, train_end: str, test_start: str, next_open_date: str, fees: float) -> None:
    best_rows = []
    for item in summaries:
        b, a = item["best"], item["next_action"]
        best_rows.append({"target": item["target"], "strategy": b["strategy"], "family": b["family"], "score": b["score"], "test_annual_return": b["test_annual_return"], "test_max_drawdown": b["test_max_drawdown"], "test_sharpe": b["test_sharpe"], "test_calmar": b["test_calmar"], "full_annual_return": b["full_annual_return"], "full_max_drawdown": b["full_max_drawdown"], "full_sharpe": b["full_sharpe"], "full_calmar": b["full_calmar"], "full_exposure": b["full_exposure"], "full_trades": b["full_trades"], "next_open_action": a["action"], "latest_signal_date": a["latest_signal_date"]})
    combined = pd.DataFrame(best_rows)
    combined.to_csv(run_dir / "best_strategy_summary.csv", index=False, encoding="utf-8-sig")
    lines = [
        "# QQQ/QLD/TQQQ Online-Inspired VectorBT Strategy Report",
        "",
        f"- Run directory: `{run_dir}`",
        f"- Train ends: `{train_end}`; test starts: `{test_start}`",
        "- Execution: signal after close, trade at next open.",
        f"- One-way fee/slippage: `{fees:.4%}`",
        f"- Requested next open: `{next_open_date}`",
        "",
        "## Sources",
        "",
    ]
    for src in ONLINE_SOURCES:
        lines.append(f"- [{src['name']}]({src['url']}): {src['use']}")
    lines += ["", "## Data Status", "", md_table(data_status), "", "## Best Summary", "", md_table(combined)]
    for item in summaries:
        t, b, a = item["target"], item["best"], item["next_action"]
        lines += [
            "",
            f"## {t}",
            "",
            f"- Best strategy: `{b['strategy']}`",
            f"- Family/source: `{b['family']}` / `{b['source']}`",
            f"- Rule: {b.get('notes', '')}",
            f"- Test annual/maxDD/sharpe/calmar: {pct(b['test_annual_return'])} / {pct(b['test_max_drawdown'])} / {b['test_sharpe']:.3f} / {b['test_calmar']:.3f}",
            f"- Full annual/maxDD/sharpe/calmar: {pct(b['full_annual_return'])} / {pct(b['full_max_drawdown'])} / {b['full_sharpe']:.3f} / {b['full_calmar']:.3f}",
            f"- Exposure/trades: {pct(b['full_exposure'])} / {int(b['full_trades'])}",
            f"- Next open action: `{a['action']}` on `{a['next_open_date']}`, based on latest signal date `{a['latest_signal_date']}`.",
            f"- Latest open/close: {a['latest_open']:.4f} / {a['latest_close']:.4f}",
            f"- Files: `{t}_strategy_rank.csv`, `{t}_operation_points.csv`, `{t}_trades.csv`, `{t}_best_signal_nav.csv`",
            "",
            "Recent operations:",
            "",
        ]
        lines.append(md_table(item["operations"].tail(20)) if not item["operations"].empty else "_No operations._")
        lines += ["", "Recent trades:", ""]
        lines.append(md_table(item["trades"].tail(20)) if not item["trades"].empty else "_No trades._")
    (run_dir / "report.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    write_json(run_dir / "best_config.json", {"run_dir": str(run_dir), "train_end": train_end, "test_start": test_start, "next_open_date": next_open_date, "fees": fees, "sources": ONLINE_SOURCES, "best": best_rows})
    checkpoint(run_dir, "04_final_report", "Final Report Checkpoint", {"report": str(run_dir / "report.md"), "best_config": str(run_dir / "best_config.json"), "best_summary": best_rows}, "Review report and per-target CSVs for execution details.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--today", default="2026-04-21", help="Exclusive end date for downloads. 2026-04-21 attempts to include Apr 20 if available; latest common completed date is used.")
    parser.add_argument("--train-end", default="2020-12-31")
    parser.add_argument("--test-start", default="2021-01-01")
    parser.add_argument("--next-open-date", default="2026-04-20")
    parser.add_argument("--fees", type=float, default=0.001)
    args = parser.parse_args()
    run_dir = OUT_ROOT / f"vbt_online_{stamp()}"
    run_dir.mkdir(parents=True, exist_ok=True)
    checkpoint(run_dir, "00_online_sources", "Online Strategy Source Checkpoint", {"sources": ONLINE_SOURCES, "vectorbt_version": vbt.__version__}, "Update US ETF/VIX data and generate candidate strategies.")
    data, status, _ = full_mod.update_us_data(run_dir, today=args.today, context_symbols=CONTEXT)
    usable = {k: v for k, v in data.items() if v is not None and not v.empty}
    latest = min(v.index.max() for v in usable.values())
    for key in list(usable):
        usable[key] = usable[key].loc[usable[key].index <= latest].copy()
    summaries = [evaluate_target(t, usable, run_dir, args.train_end, args.test_start, args.next_open_date, args.fees) for t in TARGETS]
    write_report(run_dir, summaries, status, args.train_end, args.test_start, args.next_open_date, args.fees)
    print(run_dir)


if __name__ == "__main__":
    main()
