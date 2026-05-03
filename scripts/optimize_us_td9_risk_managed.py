"""Risk-managed TD9/factor strategy optimizer for the US all-asset run.

This script starts from the previous broad vectorbt candidate search, keeps a
small set of economically sensible seed signals per symbol, and applies risk
management overlays: market/asset risk gates, volatility targeting, fractional
position sizing, trailing stops, and drawdown kill switches.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sys
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


def import_td9_module():
    spec = importlib.util.spec_from_file_location("td9_all_assets", SCRIPTS / "vbt_us_td9_all_assets.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load vbt_us_td9_all_assets.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["td9_all_assets"] = module
    spec.loader.exec_module(module)
    return module


td9 = import_td9_module()

OUT_ROOT = ROOT / "outputs" / "us_td9_risk_managed"
CORE_CONTEXT = ("QQQ", "SPY", "_VIX", "TLT", "SHY", "GLD")
LEVERAGED = {"QLD", "TQQQ", "UPRO", "SSO", "SQQQ", "PSQ"}


@dataclass(frozen=True)
class RiskSpec:
    name: str
    gate: str
    vol_target: float
    max_weight: float
    kill_dd: float
    trail_stop: float
    cooldown: int = 20


def stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(td9.base.jready(data), ensure_ascii=False, indent=2), encoding="utf-8")


def checkpoint(run_dir: Path, stage: str, payload: Mapping[str, object]) -> None:
    write_json(run_dir / f"checkpoint_{stage}.json", {"stage": stage, "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "payload": dict(payload)})


def read_price(run_dir: Path, symbol: str) -> pd.DataFrame:
    path = run_dir / "updated_data" / f"{symbol}.csv"
    if path.exists():
        return td9.read_price_csv(path)
    return td9.read_price_csv(td9.LEGACY_DIR / f"{symbol}.csv")


def numeric_frame(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    for col in df.columns:
        if any(token in col for token in ("return", "drawdown", "sharpe", "calmar", "exposure", "trades", "score", "years")):
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def seed_score(df: pd.DataFrame) -> pd.Series:
    return (
        0.24 * np.clip(df["test_calmar"], -1, 3) / 3
        + 0.20 * np.clip(df["test_sharpe"], -1, 2.5) / 2.5
        + 0.18 * np.clip(df["test_annual_return"], -0.1, 0.6) / 0.6
        + 0.16 * np.clip(df["full_calmar"], -1, 2) / 2
        + 0.12 * np.clip(df["full_sharpe"], -1, 2) / 2
        + 0.10 * np.clip(df["full_annual_return"], -0.1, 0.5) / 0.5
    )


def select_seed_strategies(candidate_summary: pd.DataFrame, top_n: int) -> pd.DataFrame:
    df = candidate_summary.dropna(
        subset=[
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
        ]
    ).copy()
    df = df[
        (df["test_annual_return"] > 0)
        & (df["full_annual_return"] > 0)
        & (df["full_exposure"] >= 0.10)
        & (df["full_trades"] >= 3)
    ].copy()
    df["seed_score"] = seed_score(df)
    mandatory = [
        "qqq_ema3_120_b0.0025",
        "asset_ma200_band_e1.01_x0.99",
        "asset_sma3_180_b0.0000",
        "factor_score_td9_e10_x7",
        "qqq_ema3_120_td9_exit_s9",
    ]
    rows = []
    for symbol, group in df.groupby("symbol"):
        chosen = group.sort_values("seed_score", ascending=False).head(top_n)
        forced = group[group["strategy"].isin(mandatory)]
        rows.append(pd.concat([chosen, forced], ignore_index=True).drop_duplicates("strategy"))
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def make_gates(asset: pd.DataFrame, context: Mapping[str, pd.DataFrame]) -> dict[str, pd.Series]:
    idx = asset.index
    qqq = td9.base.align(context["QQQ"], idx)
    spy = td9.base.align(context["SPY"], idx)
    vix = td9.base.align(context["_VIX"], idx)
    asset_close = asset["close"].astype(float)
    gates = {
        "none": pd.Series(1.0, index=idx),
        "market": (
            (qqq["close"] > qqq["close"].rolling(200).mean())
            & (spy["close"] > spy["close"].rolling(200).mean())
            & (vix["close"] < 35)
        ).astype(float),
        "market_strict": (
            (qqq["close"] > qqq["close"].rolling(150).mean())
            & (spy["close"] > spy["close"].rolling(200).mean())
            & (vix["close"] < 30)
        ).astype(float),
        "asset": ((asset_close > asset_close.rolling(200).mean()) & (vix["close"] < 35)).astype(float),
    }
    return gates


def weighted_backtest(
    asset: pd.DataFrame,
    desired: pd.Series,
    gate: pd.Series,
    spec: RiskSpec,
    cost: float,
) -> dict[str, pd.Series]:
    idx = asset.index
    open_price = asset["open"].astype(float).ffill()
    close = asset["close"].astype(float).ffill()
    raw = desired.reindex(idx).ffill().fillna(0.0).clip(0, 1)
    raw = raw * gate.reindex(idx).ffill().fillna(0.0).clip(0, 1)
    vol = close.pct_change(fill_method=None).rolling(20).std() * math.sqrt(252)
    vol_scale = spec.vol_target / vol.replace(0, np.nan)
    raw = raw * vol_scale.clip(0, spec.max_weight).fillna(0.0)

    weights = []
    held = False
    peak_price = np.nan
    stop_cooldown = 0
    for dt, weight in raw.items():
        price = close.loc[dt]
        if stop_cooldown > 0:
            stop_cooldown -= 1
        if weight > 0 and stop_cooldown == 0:
            if not held:
                held = True
                peak_price = price
            peak_price = max(peak_price, price)
            if price <= peak_price * (1 - spec.trail_stop):
                held = False
                peak_price = np.nan
                stop_cooldown = spec.cooldown
                weights.append(0.0)
                continue
            weights.append(float(weight))
        else:
            held = False
            peak_price = np.nan
            weights.append(0.0)

    desired_weight = pd.Series(weights, index=idx, name="desired_weight")
    returns = []
    position = []
    nav = 1.0
    peak_nav = 1.0
    kill_cooldown = 0
    prev_weight = 0.0
    prev_open = np.nan
    for dt, wanted in desired_weight.items():
        opn = open_price.loc[dt]
        if pd.isna(prev_open):
            period_ret = 0.0
        else:
            period_ret = prev_weight * (opn / prev_open - 1.0)
        if kill_cooldown > 0:
            wanted = 0.0
            kill_cooldown -= 1
        trade = abs(float(wanted) - prev_weight)
        period_ret -= trade * cost
        nav *= 1.0 + period_ret
        peak_nav = max(peak_nav, nav)
        if nav / peak_nav - 1.0 <= -spec.kill_dd:
            wanted = 0.0
            kill_cooldown = spec.cooldown
        returns.append(period_ret)
        position.append(float(wanted))
        prev_weight = float(wanted)
        prev_open = opn

    position_s = pd.Series(position, index=idx, name="position_weight")
    returns_s = pd.Series(returns, index=idx, name="returns")
    desired_executed = position_s > 0.01
    prev = desired_executed.shift(1).fillna(False).astype(bool)
    entries = desired_executed & ~prev
    exits = ~desired_executed & prev
    return {
        "returns": returns_s,
        "position": position_s,
        "value": (1.0 + returns_s.fillna(0.0)).cumprod(),
        "desired": desired_weight,
        "entries": entries,
        "exits": exits,
    }


def metrics_from(result: Mapping[str, pd.Series], start: str | None = None, end: str | None = None) -> dict:
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
    downside = ret[ret < 0]
    dd = nav / nav.cummax() - 1.0
    max_dd = float(dd.min())
    return {
        "total_return": total,
        "annual_return": ann,
        "sharpe": float(ret.mean() / sd * math.sqrt(252)) if sd > 0 else np.nan,
        "sortino": float(ret.mean() / downside.std(ddof=0) * math.sqrt(252)) if len(downside) and downside.std(ddof=0) > 0 else np.nan,
        "max_drawdown": max_dd,
        "calmar": float(ann / abs(max_dd)) if max_dd < 0 and not pd.isna(ann) else np.nan,
        "exposure": float(pos.reindex(ret.index).fillna(0.0).mean()),
        "trades": int(entries.reindex(ret.index).fillna(False).sum()),
        "years": years,
    }


def robust_score(row: Mapping[str, float], symbol: str) -> float:
    required = ("test_annual_return", "test_sharpe", "test_calmar", "full_annual_return", "full_sharpe", "full_calmar")
    if any(pd.isna(row.get(k, np.nan)) for k in required):
        return -999.0
    val = (
        0.30 * float(np.clip(row["test_calmar"], -1, 2.5))
        + 0.22 * float(np.clip(row["test_sharpe"], -1, 2.0))
        + 0.16 * float(np.clip(row["test_annual_return"], -0.1, 0.45))
        + 0.14 * float(np.clip(row["full_calmar"], -1, 2.0))
        + 0.10 * float(np.clip(row["full_sharpe"], -1, 2.0))
        + 0.08 * float(np.clip(row["full_annual_return"], -0.1, 0.35))
    )
    full_dd = abs(float(row.get("full_max_drawdown", 0.0)))
    test_dd = abs(float(row.get("test_max_drawdown", 0.0)))
    target_dd = 0.24 if symbol not in LEVERAGED else 0.28
    hard_dd = 0.34 if symbol not in LEVERAGED else 0.38
    if test_dd > target_dd:
        val -= 1.2 * (test_dd - target_dd)
    if full_dd > hard_dd:
        val -= 1.8 * (full_dd - hard_dd)
    exposure = float(row.get("full_exposure", 0.0) or 0.0)
    if exposure < 0.12:
        val -= 0.6
    if row.get("full_annual_return", 0.0) <= 0:
        val -= 1.0
    if row.get("test_annual_return", 0.0) <= 0:
        val -= 1.0
    return float(val)


def risk_specs(symbol: str) -> list[RiskSpec]:
    if symbol in LEVERAGED:
        return [
            RiskSpec("mkt_vt20_w100_k18_t18", "market", 0.20, 1.0, 0.18, 0.18),
            RiskSpec("mkt_vt25_w100_k18_t18", "market", 0.25, 1.0, 0.18, 0.18),
            RiskSpec("mkt_vt30_w100_k18_t18", "market", 0.30, 1.0, 0.18, 0.18),
            RiskSpec("mkt_vt30_w080_k18_t18", "market", 0.30, 0.8, 0.18, 0.18),
            RiskSpec("strict_vt25_w100_k15_t15", "market_strict", 0.25, 1.0, 0.15, 0.15),
        ]
    return [
        RiskSpec("mkt_vt12_w100_k15_t12", "market", 0.12, 1.0, 0.15, 0.12),
        RiskSpec("mkt_vt16_w100_k18_t15", "market", 0.16, 1.0, 0.18, 0.15),
        RiskSpec("mkt_vt20_w100_k20_t18", "market", 0.20, 1.0, 0.20, 0.18),
        RiskSpec("asset_vt16_w100_k18_t15", "asset", 0.16, 1.0, 0.18, 0.15),
        RiskSpec("strict_vt16_w100_k15_t12", "market_strict", 0.16, 1.0, 0.15, 0.12),
    ]


def latest_action(result: Mapping[str, pd.Series]) -> str:
    latest_weight = float(result["position"].iloc[-1])
    desired_weight = float(result["desired"].iloc[-1])
    if desired_weight > 0.01 and latest_weight <= 0.01:
        return "BUY_NEXT_OPEN"
    if desired_weight <= 0.01 and latest_weight > 0.01:
        return "SELL_NEXT_OPEN"
    if desired_weight > 0.01:
        return "HOLD_OR_KEEP_LONG"
    return "STAY_CASH"


def save_symbol_details(run_dir: Path, symbol: str, asset: pd.DataFrame, best: dict, result: Mapping[str, pd.Series]) -> None:
    out = pd.DataFrame(
        {
            "open": asset["open"],
            "close": asset["close"],
            "desired_weight_after_close": result["desired"],
            "position_weight_at_open": result["position"],
            "entry_at_open": result["entries"].astype(int),
            "exit_at_open": result["exits"].astype(int),
            "portfolio_value": result["value"],
            "portfolio_return": result["returns"],
        }
    )
    out.to_csv(run_dir / f"{symbol}_risk_signal_nav.csv", encoding="utf-8-sig")


def pct(value: object) -> str:
    if value is None or pd.isna(value):
        return "nan"
    return f"{float(value) * 100:.2f}%"


def md_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_No rows._"
    show = df.copy()
    for col in show.columns:
        if any(token in col for token in ("return", "drawdown", "exposure", "excess")):
            show[col] = show[col].map(pct)
        elif col in {"score", "test_sharpe", "test_calmar", "full_sharpe", "full_calmar"}:
            show[col] = show[col].map(lambda x: "nan" if pd.isna(x) else f"{float(x):.3f}")
    cols = list(show.columns)
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for _, row in show.iterrows():
        lines.append("| " + " | ".join(str(row[col]).replace("|", "\\|").replace("\n", " ") for col in cols) + " |")
    return "\n".join(lines)


def write_report(run_dir: Path, top5: pd.DataFrame, qld_tqqq: pd.DataFrame, summary: Mapping[str, object]) -> None:
    cols = [
        "symbol",
        "strategy",
        "risk_spec",
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
        "latest_action",
    ]
    lines = [
        "# US TD9 risk-managed optimization report",
        "",
        f"- Run directory: `{run_dir}`",
        f"- Base run: `{summary.get('base_run')}`",
        f"- Symbols evaluated: {summary.get('symbols')}",
        f"- Seed strategies: {summary.get('seed_rows')}",
        f"- Risk-managed candidates: {summary.get('candidate_rows')}",
        "- Cost model: one-way 0.20% = 0.10% fee + 0.10% slippage assumption.",
        "- Risk overlays: QQQ/SPY/VIX or asset risk gate, volatility targeting, fractional weight cap, trailing stop, drawdown kill switch.",
        "- Execution convention: signal after close, target weight at next open.",
        "",
        "## Top 5 Tradable",
        "",
        md_table(top5[cols]),
        "",
        "## QLD And TQQQ",
        "",
        md_table(qld_tqqq[cols]),
        "",
        "## Strategy Meaning",
        "",
    ]
    for _, row in pd.concat([top5, qld_tqqq], ignore_index=True).drop_duplicates(["symbol", "strategy", "risk_spec"]).iterrows():
        lines.append(f"- `{row['symbol']}` `{row['strategy']}` + `{row['risk_spec']}`: {row['notes']}")
        lines.append(
            f"  Buy when the base signal is long and the risk gate is open; position is capped by volatility target. "
            f"Sell or reduce to cash when the base signal exits, risk gate closes, trailing stop fires, or portfolio drawdown kill switch fires. "
            f"Latest action: `{row['latest_action']}`."
        )
    lines += [
        "",
        "## Limitations",
        "",
        "- This is research only, not investment advice.",
        "- The optimizer deliberately reuses a small seed set from the prior broad search to reduce data snooping, but it is still historical optimization.",
        "- Some fund/CEF data are local-only through 2026-04-02; high-liquidity ETF and MAG7 rows are mostly current through 2026-04-17.",
        "- Weighted backtest includes a simple slippage assumption, not historical bid/ask spread by asset.",
    ]
    (run_dir / "report.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-run", default=str(ROOT / "outputs" / "us_td9_all_assets" / "td9_all_assets_20260419_210058"))
    parser.add_argument("--train-end", default="2020-12-31")
    parser.add_argument("--test-start", default="2021-01-01")
    parser.add_argument("--top-seeds", type=int, default=6)
    parser.add_argument("--cost", type=float, default=0.002)
    args = parser.parse_args()

    base_run = Path(args.base_run)
    run_dir = OUT_ROOT / f"risk_managed_{stamp()}"
    run_dir.mkdir(parents=True, exist_ok=True)
    checkpoint(run_dir, "00_start", {"base_run": str(base_run), "cost": args.cost})

    universe = pd.read_csv(base_run / "universe.csv")
    candidate_summary = numeric_frame(base_run / "candidate_summary.csv")
    seeds = select_seed_strategies(candidate_summary, args.top_seeds)
    seeds.to_csv(run_dir / "seed_strategies.csv", index=False, encoding="utf-8-sig")
    checkpoint(run_dir, "01_seeds", {"universe_rows": len(universe), "seed_rows": len(seeds), "seed_symbols": seeds["symbol"].nunique()})

    all_symbols = universe["symbol"].tolist()
    data = {symbol: read_price(base_run, symbol) for symbol in all_symbols}
    context = {symbol: data[symbol] for symbol in CORE_CONTEXT if symbol in data and not data[symbol].empty}
    missing_context = [symbol for symbol in CORE_CONTEXT if symbol not in context]
    if missing_context:
        raise RuntimeError(f"Missing context data: {missing_context}")
    market_turning = td9.load_market_turning_bundle(base_run)

    rows = []
    best_rows = []
    best_results: dict[str, tuple[pd.DataFrame, dict, dict]] = {}
    seed_by_symbol = {symbol: frame for symbol, frame in seeds.groupby("symbol")}
    hold_rows = candidate_summary[candidate_summary["strategy"] == "buy_hold"][
        ["symbol", "full_annual_return", "full_max_drawdown", "test_annual_return", "test_max_drawdown"]
    ].drop_duplicates("symbol")
    hold_lookup = hold_rows.set_index("symbol").to_dict("index")

    for i, symbol in enumerate(all_symbols, 1):
        asset = data[symbol]
        if asset.empty or symbol not in seed_by_symbol:
            continue
        try:
            candidates = {candidate.name: candidate for candidate in td9.build_candidates(symbol, asset, context, market_turning)}
            gates = make_gates(asset, context)
            symbol_best = None
            symbol_best_payload = None
            for _, seed in seed_by_symbol[symbol].iterrows():
                strategy = seed["strategy"]
                candidate = candidates.get(strategy)
                if candidate is None:
                    continue
                for spec in risk_specs(symbol):
                    result = weighted_backtest(asset, candidate.signal, gates[spec.gate], spec, args.cost)
                    train = metrics_from(result, None, args.train_end)
                    test = metrics_from(result, args.test_start, None)
                    full = metrics_from(result, None, None)
                    row = {
                        "symbol": symbol,
                        "group": seed.get("group", ""),
                        "strategy": strategy,
                        "family": seed.get("family", ""),
                        "source": seed.get("source", ""),
                        "risk_spec": spec.name,
                        "risk_gate": spec.gate,
                        "vol_target": spec.vol_target,
                        "max_weight": spec.max_weight,
                        "kill_dd": spec.kill_dd,
                        "trail_stop": spec.trail_stop,
                        "latest_date": asset.index.max().strftime("%Y-%m-%d"),
                        "latest_close": float(asset["close"].iloc[-1]),
                        "latest_action": latest_action(result),
                        "latest_weight": float(result["position"].iloc[-1]),
                        "notes": seed.get("notes", ""),
                    }
                    for prefix, metrics in (("train", train), ("test", test), ("full", full)):
                        for key, value in metrics.items():
                            row[f"{prefix}_{key}"] = value
                    row["score"] = robust_score(row, symbol)
                    hold = hold_lookup.get(symbol, {})
                    row["buy_hold_full_annual_return"] = hold.get("full_annual_return", np.nan)
                    row["buy_hold_full_max_drawdown"] = hold.get("full_max_drawdown", np.nan)
                    row["full_annual_excess_vs_buy_hold"] = row["full_annual_return"] - row["buy_hold_full_annual_return"]
                    rows.append(row)
                    if symbol_best is None or row["score"] > symbol_best["score"]:
                        symbol_best = row
                        symbol_best_payload = (asset, row, result)
            if symbol_best is not None:
                best_rows.append(symbol_best)
                best_results[symbol] = symbol_best_payload
        except Exception as exc:
            best_rows.append({"symbol": symbol, "score": -999.0, "error": f"{type(exc).__name__}: {exc}"})
        if i % 25 == 0:
            pd.DataFrame(rows).to_csv(run_dir / "candidate_summary_checkpoint.csv", index=False, encoding="utf-8-sig")
            pd.DataFrame(best_rows).to_csv(run_dir / "instrument_best_checkpoint.csv", index=False, encoding="utf-8-sig")

    cand_df = pd.DataFrame(rows).sort_values("score", ascending=False)
    best_df = pd.DataFrame(best_rows).sort_values("score", ascending=False)
    cand_df.to_csv(run_dir / "candidate_summary.csv", index=False, encoding="utf-8-sig")
    best_df.to_csv(run_dir / "instrument_best_summary.csv", index=False, encoding="utf-8-sig")

    top5 = best_df[best_df["symbol"] != "_VIX"].head(5).copy()
    qld_tqqq = best_df[best_df["symbol"].isin(["QLD", "TQQQ"])].sort_values("symbol").copy()
    top5.to_csv(run_dir / "top5_tradable.csv", index=False, encoding="utf-8-sig")
    qld_tqqq.to_csv(run_dir / "qld_tqqq_best.csv", index=False, encoding="utf-8-sig")

    for symbol in list(dict.fromkeys(top5["symbol"].tolist() + ["QLD", "TQQQ"])):
        payload = best_results.get(symbol)
        if payload is not None:
            save_symbol_details(run_dir, symbol, payload[0], payload[1], payload[2])

    summary = {
        "base_run": str(base_run),
        "symbols": len(all_symbols),
        "seed_rows": len(seeds),
        "candidate_rows": len(cand_df),
        "top5": top5.head(5).to_dict("records"),
        "qld_tqqq": qld_tqqq.to_dict("records"),
    }
    write_report(run_dir, top5, qld_tqqq, summary)
    write_json(run_dir / "best_config.json", summary)
    checkpoint(run_dir, "02_final", summary)
    print(run_dir)


if __name__ == "__main__":
    main()
