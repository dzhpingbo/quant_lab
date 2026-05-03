"""Strict post-process report for the US TD9 risk-managed optimizer.

The optimizer intentionally produces a broad risk-managed candidate table. This
script applies a stricter delivery filter that addresses the main review issues:
fresh data, enough history, positive train/test/full performance, reasonable
exposure, controlled drawdown, positive excess versus buy-and-hold, and annual
return greater than full-period max drawdown magnitude.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT_ROOT = ROOT / "outputs" / "us_td9_risk_managed"
BASE_RUN = ROOT / "outputs" / "us_td9_all_assets" / "td9_all_assets_20260419_210058"
MAG7 = {"AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "TSLA"}


def latest_run_dir() -> Path:
    runs = [p for p in OUT_ROOT.glob("risk_managed_*") if p.is_dir()]
    if not runs:
        raise FileNotFoundError(f"No risk_managed_* directories found under {OUT_ROOT}")
    return max(runs, key=lambda p: p.stat().st_mtime)


def numeric_frame(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    for col in df.columns:
        if col in {"symbol", "group", "strategy", "family", "source", "risk_spec", "risk_gate", "latest_date", "latest_action", "notes"}:
            continue
        converted = pd.to_numeric(df[col], errors="coerce")
        non_missing = df[col].notna()
        if not non_missing.any() or converted[non_missing].notna().mean() >= 0.80:
            df[col] = converted
    return df


def pct(value: object) -> str:
    if value is None or pd.isna(value):
        return "nan"
    return f"{float(value) * 100:.2f}%"


def num(value: object) -> str:
    if value is None or pd.isna(value):
        return "nan"
    return f"{float(value):.3f}"


def pp(value: object) -> str:
    if value is None or pd.isna(value):
        return "nan"
    return f"{float(value):.2f}pp"


def md_table(df: pd.DataFrame, pct_cols: set[str] | None = None, num_cols: set[str] | None = None, pp_cols: set[str] | None = None) -> str:
    if df.empty:
        return "_No rows._"
    pct_cols = pct_cols or set()
    num_cols = num_cols or set()
    pp_cols = pp_cols or set()
    show = df.copy()
    for col in show.columns:
        if col in pct_cols:
            show[col] = show[col].map(pct)
        elif col in num_cols:
            show[col] = show[col].map(num)
        elif col in pp_cols:
            show[col] = show[col].map(pp)
    lines = ["| " + " | ".join(show.columns) + " |", "| " + " | ".join(["---"] * len(show.columns)) + " |"]
    for _, row in show.iterrows():
        lines.append("| " + " | ".join(str(row[col]).replace("|", "\\|").replace("\n", " ") for col in show.columns) + " |")
    return "\n".join(lines)


def strict_filter(df: pd.DataFrame, latest_min: str) -> pd.DataFrame:
    needed = [
        "train_years",
        "test_years",
        "full_years",
        "train_annual_return",
        "test_annual_return",
        "full_annual_return",
        "train_sharpe",
        "test_sharpe",
        "full_sharpe",
        "test_max_drawdown",
        "full_max_drawdown",
        "full_exposure",
        "full_trades",
        "full_annual_excess_vs_buy_hold",
    ]
    work = df.dropna(subset=needed).copy()
    return work[
        (work["latest_date"] >= latest_min)
        & (work["train_years"] >= 5)
        & (work["test_years"] >= 5)
        & (work["full_years"] >= 8)
        & (work["train_annual_return"] > 0)
        & (work["test_annual_return"] >= 0.05)
        & (work["full_annual_return"] >= 0.05)
        & (work["train_sharpe"] >= 0.70)
        & (work["test_sharpe"] >= 1.00)
        & (work["full_sharpe"] >= 0.80)
        & (work["test_max_drawdown"] >= -0.18)
        & (work["full_max_drawdown"] >= -0.18)
        & (work["full_exposure"].between(0.12, 0.75))
        & (work["full_trades"].between(8, 180))
        & (work["full_annual_return"] >= work["full_max_drawdown"].abs())
        & (work["full_annual_excess_vs_buy_hold"] > 0)
    ].copy()


def best_by_symbol(df: pd.DataFrame) -> pd.DataFrame:
    return df.sort_values(["score", "full_annual_excess_vs_buy_hold"], ascending=False).drop_duplicates("symbol").reset_index(drop=True)


def compare_qld_tqqq(base_run: Path, new_best: pd.DataFrame) -> pd.DataFrame:
    old_best = numeric_frame(base_run / "instrument_best_summary.csv")
    rows = []
    for symbol in ["QLD", "TQQQ"]:
        old = old_best[old_best["symbol"] == symbol]
        new = new_best[new_best["symbol"] == symbol]
        if old.empty or new.empty:
            continue
        old_row = old.iloc[0]
        new_row = new.iloc[0]
        old_dd = float(old_row["full_max_drawdown"])
        new_dd = float(new_row["full_max_drawdown"])
        rows.append(
            {
                "symbol": symbol,
                "old_strategy": old_row["strategy"],
                "old_full_annual_return": old_row["full_annual_return"],
                "old_full_max_drawdown": old_row["full_max_drawdown"],
                "old_full_sharpe": old_row["full_sharpe"],
                "old_full_calmar": old_row["full_calmar"],
                "new_strategy": new_row["strategy"],
                "new_risk_spec": new_row["risk_spec"],
                "new_full_annual_return": new_row["full_annual_return"],
                "new_full_max_drawdown": new_row["full_max_drawdown"],
                "new_full_sharpe": new_row["full_sharpe"],
                "new_full_calmar": new_row["full_calmar"],
                "new_latest_action": new_row["latest_action"],
                "annual_return_change_pp": (float(new_row["full_annual_return"]) - float(old_row["full_annual_return"])) * 100.0,
                "drawdown_reduction_pp": (abs(old_dd) - abs(new_dd)) * 100.0,
                "calmar_change": float(new_row["full_calmar"]) - float(old_row["full_calmar"]),
            }
        )
    return pd.DataFrame(rows)


def write_report(run_dir: Path, base_run: Path, strict: pd.DataFrame, strict_best: pd.DataFrame, compare: pd.DataFrame) -> None:
    candidate_rows = len(pd.read_csv(run_dir / "candidate_summary.csv", usecols=["symbol"]))
    old_candidate_rows = len(pd.read_csv(base_run / "candidate_summary.csv", usecols=["symbol"]))
    best = numeric_frame(run_dir / "instrument_best_summary.csv")
    latest_counts = best["latest_date"].value_counts().to_dict()
    stale_counts = {k: v for k, v in latest_counts.items() if str(k) < str(best["latest_date"].max())}
    mag7_best = best[best["symbol"].isin(MAG7)].sort_values("score", ascending=False)

    top_cols = [
        "symbol",
        "strategy",
        "risk_spec",
        "score",
        "test_annual_return",
        "test_max_drawdown",
        "test_sharpe",
        "full_annual_return",
        "full_max_drawdown",
        "full_sharpe",
        "full_calmar",
        "full_exposure",
        "buy_hold_full_annual_return",
        "full_annual_excess_vs_buy_hold",
        "latest_action",
        "notes",
    ]
    cmp_pct_cols = {
        "old_full_annual_return",
        "old_full_max_drawdown",
        "new_full_annual_return",
        "new_full_max_drawdown",
    }
    lines = [
        "# US TD9 Risk-Managed Final Delivery",
        "",
        "## Handoff State",
        "",
        f"- Base broad run: `{base_run}`",
        f"- Risk-managed run: `{run_dir}`",
        f"- Broad candidates before risk management: {old_candidate_rows}",
        f"- Risk-managed candidates: {candidate_rows}",
        f"- Best-result symbols in risk-managed run: {len(best)}",
        f"- Latest-date distribution: `{latest_counts}`",
        "",
        "## Strict Delivery Filter",
        "",
        "- Latest data date must be at least 2026-04-17.",
        "- Train >= 5 years, test >= 5 years, full >= 8 years.",
        "- Train/test/full annual returns must be positive, with test/full annual return at least 5%.",
        "- Test/full drawdown must be no worse than -18%.",
        "- Full annual return must be greater than full max drawdown magnitude.",
        "- Full-period excess annual return versus buy-and-hold must be positive.",
        "- Full exposure must be between 12% and 75%; full trades between 8 and 180.",
        f"- Strict survivors: {len(strict)} candidate rows across {strict['symbol'].nunique() if not strict.empty else 0} symbols.",
        "",
        "## Strict Top 5 By Symbol",
        "",
        md_table(
            strict_best.head(5)[top_cols],
            pct_cols={
                "test_annual_return",
                "test_max_drawdown",
                "full_annual_return",
                "full_max_drawdown",
                "full_exposure",
                "buy_hold_full_annual_return",
                "full_annual_excess_vs_buy_hold",
            },
            num_cols={"score", "test_sharpe", "full_sharpe", "full_calmar"},
        ),
        "",
        "## MAG7 Risk-Managed Diagnostic",
        "",
        "- This section shows each MAG7 symbol's best risk-managed candidate before the strict positive-excess filter.",
        "- A MAG7 row should not be treated as final top-5 unless it also appears in the strict survivor set.",
        "",
        md_table(
            mag7_best[top_cols],
            pct_cols={
                "test_annual_return",
                "test_max_drawdown",
                "full_annual_return",
                "full_max_drawdown",
                "full_exposure",
                "buy_hold_full_annual_return",
                "full_annual_excess_vs_buy_hold",
            },
            num_cols={"score", "test_sharpe", "full_sharpe", "full_calmar"},
        ),
        "",
        "## QLD And TQQQ Before/After",
        "",
        md_table(
            compare,
            pct_cols=cmp_pct_cols,
            num_cols={"old_full_sharpe", "old_full_calmar", "new_full_sharpe", "new_full_calmar", "calmar_change"},
            pp_cols={"annual_return_change_pp", "drawdown_reduction_pp"},
        ),
        "",
        "## Readout",
        "",
        "- The broad run did find positive recent momentum, but its original ranking tolerated high full-period drawdowns and some low-exposure artifacts.",
        "- The risk-managed run reduces drawdown by adding market/asset gates, volatility targeting, trailing stops, and drawdown kill switches with 0.20% one-way cost.",
        "- QLD and TQQQ are now drawdown-first versions: annual return is lower than buy-and-hold, but max drawdown and Calmar improve materially.",
        "- The strict tradable recommendation from this pass is the highest strict top-5 row above, not the old broad-search first rank.",
        "",
        "## Output Files",
        "",
        f"- `{run_dir / 'strict_robust_candidates.csv'}`",
        f"- `{run_dir / 'strict_robust_best_by_symbol.csv'}`",
        f"- `{run_dir / 'strict_robust_top5.csv'}`",
        f"- `{run_dir / 'qld_tqqq_before_after.csv'}`",
        f"- `{run_dir / 'final_delivery_report.md'}`",
        "",
        "## Limitations",
        "",
        "- Research only, not investment advice.",
        "- Results are still historical and can overfit; this report narrows the selection rather than proving future alpha.",
        "- Costs include a simple 0.20% one-way assumption, not asset-specific historical bid/ask spreads.",
        f"- Latest-date distribution for best-result rows: `{latest_counts}`.",
        f"- Rows older than the newest best-result date: `{stale_counts}`.",
    ]
    (run_dir / "final_delivery_report.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", default="", help="Risk-managed run directory. Defaults to the newest risk_managed_* output.")
    parser.add_argument("--base-run", default=str(BASE_RUN), help="Base broad-search run directory.")
    parser.add_argument("--latest-min", default="2026-04-17")
    args = parser.parse_args()

    run_dir = Path(args.run_dir) if args.run_dir else latest_run_dir()
    base_run = Path(args.base_run)
    candidates = numeric_frame(run_dir / "candidate_summary.csv")
    best = numeric_frame(run_dir / "instrument_best_summary.csv")

    strict = strict_filter(candidates, args.latest_min).sort_values(["score", "full_annual_excess_vs_buy_hold"], ascending=False)
    strict_best = best_by_symbol(strict)
    strict_top5 = strict_best.head(5).copy()
    compare = compare_qld_tqqq(base_run, best)

    strict.to_csv(run_dir / "strict_robust_candidates.csv", index=False, encoding="utf-8-sig")
    strict_best.to_csv(run_dir / "strict_robust_best_by_symbol.csv", index=False, encoding="utf-8-sig")
    strict_top5.to_csv(run_dir / "strict_robust_top5.csv", index=False, encoding="utf-8-sig")
    compare.to_csv(run_dir / "qld_tqqq_before_after.csv", index=False, encoding="utf-8-sig")
    write_report(run_dir, base_run, strict, strict_best, compare)
    print(run_dir / "final_delivery_report.md")


if __name__ == "__main__":
    main()
