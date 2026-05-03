"""Generate the v8/v8.2 final closeout and strategy decision pack.

This is a closeout-only script. It does not run v9, expand the universe,
train a model, run 31b, add parameters, tune reranking, or run a new backtest.
It reads existing evidence packages and writes final decision artifacts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import shutil
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

OUTPUT_ROOT = PROJECT_ROOT / "outputs" / "us_stock_selection"
DOCS_DIR = PROJECT_ROOT / "docs"
MEISTOCK_ROOT = Path("E:/dzhwork/obsydian/quant_lab/MeiStock")

FINAL_VALIDATION_DIR = OUTPUT_ROOT / "v8_2_0p05_final_validation_20260501_183000"
BASELINE_RUN_DIR = OUTPUT_ROOT / "run_20260426_095958"


EVIDENCE_PACKAGES = [
    {
        "package_name": "v8_baseline_run",
        "path": str(BASELINE_RUN_DIR),
        "package_type": "run_dir",
        "purpose": "v8 baseline paper trading output and current return-priority reference.",
        "role_in_decision": "Defines current best strategy metrics and baseline holdings/NAV.",
    },
    {
        "package_name": "v8_final_closeout",
        "path": str(OUTPUT_ROOT / "us_stock_selection_quant_lab_v8_final_closeout_20260426.zip"),
        "package_type": "zip",
        "purpose": "Original v8 closeout evidence and final baseline status at v8 milestone.",
        "role_in_decision": "Confirms v8 baseline as credible but execution-sensitive.",
    },
    {
        "package_name": "v8_1_cycle05_market_regime_overlay_plateau",
        "path": str(OUTPUT_ROOT / "us_stock_selection_quant_lab_v8_1_cycle05_market_regime_overlay_20260429_070013.zip"),
        "package_type": "zip",
        "purpose": "v8.1 overlay plateau run.",
        "role_in_decision": "Supports stopping the v8.1 overlay branch.",
    },
    {
        "package_name": "v8_2_stock_selection_layer_diagnostic",
        "path": str(OUTPUT_ROOT / "us_stock_selection_quant_lab_v8_2_stock_selection_layer_diagnostic_20260430_225000.zip"),
        "package_type": "zip",
        "purpose": "Stock selection layer diagnostic before full audit replay.",
        "role_in_decision": "Showed old v8 outputs were selected-only and unsafe for ex-ante reranking.",
    },
    {
        "package_name": "v8_2_bounded_audit_replay",
        "path": str(OUTPUT_ROOT / "us_stock_selection_quant_lab_v8_2_bounded_audit_replay_20260501_113100.zip"),
        "package_type": "zip",
        "purpose": "Full candidate score/rank audit replay.",
        "role_in_decision": "Created complete decision_date x candidate trail and reproduced baseline selection.",
    },
    {
        "package_name": "v8_2_gate_aware_reranking_replay",
        "path": str(OUTPUT_ROOT / "us_stock_selection_quant_lab_v8_2_gate_aware_reranking_replay_20260501_132100.zip"),
        "package_type": "zip",
        "purpose": "Bounded gate-aware reranking replay.",
        "role_in_decision": "Found no accepted/strong reranking candidate; highlighted high-beta penalty as diagnostic.",
    },
    {
        "package_name": "v8_2_high_beta_penalty_robustness",
        "path": str(OUTPUT_ROOT / "us_stock_selection_quant_lab_v8_2_high_beta_penalty_robustness_20260501_164800.zip"),
        "package_type": "zip",
        "purpose": "Targeted high-beta penalty robustness review.",
        "role_in_decision": "Identified high_beta_penalty_0p05 as accepted risk-control candidate.",
    },
    {
        "package_name": "v8_2_0p05_final_validation",
        "path": str(OUTPUT_ROOT / "us_stock_selection_quant_lab_v8_2_0p05_final_validation_20260501_183000.zip"),
        "package_type": "zip",
        "purpose": "Final validation pack for high_beta_penalty_0p05.",
        "role_in_decision": "Classified 0p05 as risk_control_variant, not baseline replacement.",
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate v8/v8.2 final closeout decision pack.")
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--timestamp", default=None)
    return parser.parse_args()


def setup_logger(out_dir: Path) -> logging.Logger:
    log_dir = out_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("v8_v8_2_final_closeout")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    fh = logging.FileHandler(log_dir / "run.log", encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(sh)
    return logger


def write_json(data: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(clean_json(data), indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")


def clean_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): clean_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [clean_json(v) for v in value]
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    return value


def sha256(path: Path) -> str:
    if not path.is_file():
        return ""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def zip_entry_count(path: Path) -> int | None:
    if not path.is_file() or path.suffix.lower() != ".zip":
        return None
    with zipfile.ZipFile(path, "r") as zf:
        return len(zf.infolist())


def build_evidence_index() -> pd.DataFrame:
    rows = []
    for item in EVIDENCE_PACKAGES:
        path = Path(item["path"])
        rows.append(
            {
                **item,
                "exists": path.exists(),
                "size_bytes": path.stat().st_size if path.is_file() else "",
                "last_write_time": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds") if path.exists() else "",
                "sha256": sha256(path),
                "zip_entry_count": zip_entry_count(path),
                "index_note": "read/indexed for closeout; not re-run",
            }
        )
    return pd.DataFrame(rows)


def read_metrics() -> tuple[pd.Series, pd.Series, dict[str, Any]]:
    metrics_path = FINAL_VALIDATION_DIR / "v8_2_0p05_reproduction_metrics.csv"
    verdict_path = FINAL_VALIDATION_DIR / "v8_2_0p05_final_verdict.json"
    metrics = pd.read_csv(metrics_path)
    baseline = metrics.loc[metrics["rerank_candidate"] == "baseline_original_rank"].iloc[0]
    p05 = metrics.loc[metrics["rerank_candidate"] == "high_beta_penalty_0p05"].iloc[0]
    verdict = json.loads(verdict_path.read_text(encoding="utf-8"))
    return baseline, p05, verdict


def build_strategy_comparison(baseline: pd.Series, p05: pd.Series) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "strategy_name": "v8_baseline_return_priority",
                "classification": "current_best_return_priority",
                "CAGR": float(baseline["cagr"]),
                "cost_50bps_CAGR": float(baseline["cost50_cagr"]),
                "Calmar": float(baseline["calmar"]),
                "MaxDD": float(baseline["max_drawdown"]),
                "weakest_12m_Calmar": float(baseline["weakest_12m_Calmar"]),
                "weakest_12m_50bps_CAGR": float(baseline["weakest_12m_50bps_CAGR"]),
                "avg_high_beta_weight": float(baseline["avg_high_beta_weight_share"]),
                "max_high_beta_weight": float(baseline["max_high_beta_weight_share"]),
                "top1_positive_month_share": float(baseline["top1_positive_month_share"]),
                "top3_positive_month_share": float(baseline["top3_positive_month_share"]),
                "top5_positive_month_share": float(baseline["top5_positive_month_share"]),
                "remove_top5_month_CAGR": float(baseline["remove_top5_month_cagr"]),
                "cost_sensitivity_comment": "Stronger cost-adjusted CAGR than 0p05; still execution-sensitive.",
                "concentration_risk_comment": "Higher high-beta exposure; MSTR/TQQQ/QLD/SOXL contribution must be monitored.",
                "recommended_usage": "Return-priority research baseline; current best, not a live trading recommendation.",
                "replace_v8_best": False,
                "allow_enter_v9": False,
            },
            {
                "strategy_name": "v8_2_high_beta_penalty_0p05_risk_control",
                "classification": "risk_control_variant",
                "CAGR": float(p05["cagr"]),
                "cost_50bps_CAGR": float(p05["cost50_cagr"]),
                "Calmar": float(p05["calmar"]),
                "MaxDD": float(p05["max_drawdown"]),
                "weakest_12m_Calmar": float(p05["weakest_12m_Calmar"]),
                "weakest_12m_50bps_CAGR": float(p05["weakest_12m_50bps_CAGR"]),
                "avg_high_beta_weight": float(p05["avg_high_beta_weight_share"]),
                "max_high_beta_weight": float(p05["max_high_beta_weight_share"]),
                "top1_positive_month_share": float(p05["top1_positive_month_share"]),
                "top3_positive_month_share": float(p05["top3_positive_month_share"]),
                "top5_positive_month_share": float(p05["top5_positive_month_share"]),
                "remove_top5_month_CAGR": float(p05["remove_top5_month_cagr"]),
                "cost_sensitivity_comment": "50bps CAGR barely clears 0.4487 threshold; 75/100bps stress weakens quickly.",
                "concentration_risk_comment": "High-beta exposure lower, but top5 positive month share is higher than baseline.",
                "recommended_usage": "Risk-control variant for human review; not return-optimal and not a baseline replacement.",
                "replace_v8_best": False,
                "allow_enter_v9": False,
            },
        ]
    )


def build_final_decision(evidence: pd.DataFrame) -> dict[str, Any]:
    return {
        "final_best_strategy": "v8_baseline_return_priority",
        "risk_control_variant": "v8_2_high_beta_penalty_0p05",
        "replace_best": False,
        "allow_enter_v9": False,
        "v8_baseline_status": {
            "classification": "current_best_return_priority",
            "verdict": "credible_but_execution_sensitive",
            "role": "current best / return-priority version",
        },
        "v8_2_0p05_status": {
            "classification": "risk_control_variant",
            "replace_v8_best": False,
            "role": "risk-control backup for human review, not return-priority best",
        },
        "stopped_research_branches": [
            "v8_1_market_regime_overlay_plateau",
            "v8_2_gate_aware_reranking_parameter_tuning",
            "additional high-beta penalty tuning",
        ],
        "evidence_packages": evidence.to_dict(orient="records"),
        "key_reasons_for_not_replacing_baseline": [
            "0p05 full-period CAGR and Calmar are below v8 baseline.",
            "0p05 50bps CAGR safety margin over 0.4487 is only about 0.00285.",
            "0p05 top5 positive month share is 0.6108, above baseline 0.5410.",
            "0p05 remove-top5-month CAGR is only about 0.0220 versus baseline 0.1395.",
            "0p05 weakens quickly under 75bps/100bps cost stress.",
        ],
        "key_reasons_for_accepting_0p05_as_risk_control_variant": [
            "Reproduction passed against prior robustness outputs.",
            "No audit_forward fields are used in ranking.",
            "50bps CAGR, Calmar, MaxDD, weakest-12M Calmar and weakest-12M 50bps CAGR pass the risk-control gates.",
            "Average high-beta weight falls from 14.58% to 7.15%; max high-beta weight falls from 60% to 20%.",
            "MSTR/TQQQ/QLD selected counts decline meaningfully.",
        ],
        "next_research_stage": [
            "longer history data",
            "universe redesign as a new project",
            "stock selection model rebuild",
            "full candidate ranking objective redesign",
            "strict validation framework upgrade",
            "frozen-strategy paper trading",
        ],
        "next_stage_requires_user_approval": True,
        "do_not_continue": [
            "do not continue v8.1 overlay",
            "do not continue v8.2 reranking tuning",
            "do not enter v9 automatically",
            "do not expand universe automatically",
        ],
    }


def md_table(df: pd.DataFrame, max_rows: int = 20, columns: list[str] | None = None) -> str:
    sub = df.copy()
    if columns:
        sub = sub[[c for c in columns if c in sub.columns]]
    if len(sub) > max_rows:
        sub = sub.head(max_rows)
    return sub.to_markdown(index=False)


def write_docs(
    timestamp: str,
    out_dir: Path,
    zip_path: Path,
    comparison: pd.DataFrame,
    decision: dict[str, Any],
    evidence: pd.DataFrame,
) -> list[Path]:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    closeout_path = DOCS_DIR / f"US_STOCK_SELECTION_V8_V8_2_FINAL_CLOSEOUT_{timestamp}.md"
    exec_path = DOCS_DIR / f"US_STOCK_SELECTION_V8_V8_2_FINAL_EXEC_SUMMARY_{timestamp}.md"
    usage_path = DOCS_DIR / f"US_STOCK_SELECTION_STRATEGY_USAGE_GUIDE_{timestamp}.md"
    roadmap_path = DOCS_DIR / f"US_STOCK_SELECTION_NEXT_RESEARCH_ROADMAP_{timestamp}.md"
    evidence_md_path = DOCS_DIR / f"US_STOCK_SELECTION_EVIDENCE_PACKAGE_INDEX_{timestamp}.md"

    closeout = f"""# US Stock Selection v8 / v8.2 Final Closeout

## 1. 研究背景

本轮为最终收口归档，不进入 v9，不扩 universe，不训练新模型，不运行 31b，不新增参数，不继续 overlay/reranking 微调。

## 2. v8 Baseline 最终结论

v8 baseline 是当前 best / return-priority version，classification 为 `current_best_return_priority`，verdict 为 `credible_but_execution_sensitive`。

## 3. v8.1 Overlay 路线为什么停止

v8.1 overlay 多轮尝试进入 plateau，未形成可替代 v8 baseline 的稳健收益/回撤改善，因此停止继续 overlay 路线。

## 4. v8.2 Stock Selection Diagnostic 发现

诊断发现原 v8 输出只保留 selected-only 信息，缺少完整 candidate score/rank 留痕，不能安全做 ex-ante reranking。

## 5. Bounded Audit Replay 为什么重要

bounded audit replay 生成完整 decision_date x candidate score/rank audit trail，并复现 baseline selection，为后续有限 reranking 提供了不含未来函数的审计基础。

## 6. Gate-Aware Reranking 发现

预注册 gate-aware reranking 未产生 accepted/strong candidate，但 high-beta penalty 显示弱窗口改善信号。

## 7. 0p05 为什么可作为 Risk-Control Variant

0p05 复现通过，无未来函数，降低 high-beta 暴露，改善 weakest 12M；avg high-beta weight 从 14.58% 降至 7.15%，max high-beta weight 从 60% 降至 20%。

## 8. 为什么 0p05 不替代 v8 Baseline

0p05 full-period CAGR/Calmar 低于 baseline，50bps CAGR 安全边际很薄，top5 positive month share 更高，remove top5 month 后基本失效，不满足 replace baseline 条件。

## 9. 两套策略口径对比

{md_table(comparison)}

## 10. 当前最终建议

- 当前 best：`v8_baseline_return_priority`
- 风险控制备选：`v8_2_high_beta_penalty_0p05`
- 不自动替代 best
- 不进入 v9
- 不继续 overlay/reranking 微调

## 11. 不允许进入 v9 的原因

当前主要问题不是需要进入 v9，而是历史窗口偏短、universe 设计偏窄、ranking objective 与 validation framework 需要重构。进入 v9 前必须另行立项并重新设计研究框架。

## 12. 后续研究路线图

下一阶段应回到底层研究：更长历史数据、universe 分层设计、stock selection model 重构、严格 walk-forward/regime split、冻结策略 paper trading。

## 13. Evidence Package Index

{md_table(evidence, max_rows=20, columns=['package_name','package_type','exists','purpose','role_in_decision'])}

## 14. Output

- Output directory: `{out_dir}`
- Zip: `{zip_path}`
"""

    exec_summary = f"""# US Stock Selection v8 / v8.2 Final Exec Summary

- 当前 best：`v8_baseline_return_priority`
- 风险控制备选：`v8_2_high_beta_penalty_0p05`
- 是否替代 best：`False`
- 是否进入 v9：`False`
- 是否继续 overlay/reranking 微调：`False`
- 是否自动扩 universe：`False`

## 快速结论

v8 baseline 仍是收益优先版本；0p05 是 risk-control variant，不是收益最优策略。后续如继续，应新立项：更长历史、更合理 universe、stock selection model 重构与更严格 validation framework。

## 对比

{md_table(comparison)}
"""

    usage = """# US Stock Selection Strategy Usage Guide

## 1. v8 Baseline 适用场景

- 追求收益优先。
- 能接受更高 high-beta 暴露。
- 能接受 MSTR/TQQQ/QLD/SOXL 等高 beta 标的贡献。
- 能持续关注执行敏感性、成本压力和月份集中度。

## 2. 0p05 Risk-Control Variant 适用场景

- 希望降低 high-beta 暴露。
- 希望改善 weakest 12M 表现。
- 愿意牺牲部分 CAGR / Calmar。
- 明确知道它不是收益最优策略。

## 3. 不建议使用的场景

- 成本显著高于 50bps。
- 无法接受 top-month concentration。
- 需要强稳健、低集中度、长周期实盘版本。
- 想直接进入 v9 或扩池但尚未重建验证框架。

## 4. 重要声明

这些仍是研究回测结果，不是正式实盘建议。需要更长历史、更多市场周期、独立 walk-forward 和未来 paper trading 验证。
"""

    roadmap = """# US Stock Selection Next Research Roadmap

## Priority 1: 更长历史数据

当前 2024-2026 窗口过短，需要更多完整 bull/bear/rate regime。目标是降低偶然月份贡献和 top-month dependence。

## Priority 2: 扩展/重构 Universe 设计

不能直接粗暴扩 Nasdaq100/S&P500。应先设计 universe 分层：

- Mega-cap tech
- Nasdaq100 liquid subset
- sector/theme ETF
- leveraged ETF separate bucket
- high-beta single names

同时需要容量、流动性、历史长度过滤。

## Priority 3: Stock Selection Model 重构

- 从 selected-only 转为 full candidate ranking。
- 引入 concentration-aware objective。
- 引入 risk-adjusted target。
- 引入 multi-horizon labels。
- 引入 walk-forward model selection。

## Priority 4: 严格 Validation Framework

- purged / embargoed walk-forward。
- leave-one-year-out。
- rolling 12M。
- top-month stress。
- ticker concentration。
- cost stress。
- PBO/DSR，如可实现。

## Priority 5: Paper Trading

用冻结策略做未来样本，不再用历史反复调参。
"""

    evidence_md = f"""# US Stock Selection Evidence Package Index

{md_table(evidence, max_rows=50)}
"""

    for path, text in [
        (closeout_path, closeout),
        (exec_path, exec_summary),
        (usage_path, usage),
        (roadmap_path, roadmap),
        (evidence_md_path, evidence_md),
    ]:
        path.write_text(text, encoding="utf-8")
        reports = out_dir / "reports"
        reports.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, reports / path.name)
    return [closeout_path, exec_path, usage_path, roadmap_path, evidence_md_path]


def update_next_steps(out_dir: Path, zip_path: Path) -> None:
    path = PROJECT_ROOT / "NEXT_STEPS.md"
    text = path.read_text(encoding="utf-8") if path.exists() else "# NEXT_STEPS\n"
    header = "## us stock selection v8/v8.2 final closeout and strategy decision pack"
    section = f"""

{header}

- 执行状态：completed，随后按要求暂停，不自动进入新研究。
- 输出目录：`{out_dir}`
- zip：`{zip_path}`
- 已完成：`v8 baseline`, `v8 closeout`, `v8.1 overlay plateau`, `v8.2 stock selection diagnostic`, `bounded audit replay`, `gate-aware reranking`, `0p05 final validation`, `final closeout`
- 当前最终结论：`v8 baseline = current best`
- 风险控制备选：`0p05 = risk-control variant`
- 是否替代 best：`False`
- 是否允许进入 v9：`False`
- 是否继续 overlay/reranking tuning：`False`
- 后续如继续必须新立项：`longer history`, `universe redesign`, `stock selection model rebuild`, `validation framework upgrade`
- 本轮边界：未进入 v9，未扩 universe，未训练新模型，未运行 31b，未新增参数，未做新回测。
"""
    pattern = re.compile(r"\n\n## us stock selection v8/v8\.2 final closeout and strategy decision pack\n.*?(?=\n\n## |\Z)", re.S)
    text = pattern.sub(lambda _: section, text) if pattern.search(text) else text.rstrip() + section
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def write_run_summary(out_dir: Path, zip_path: Path) -> None:
    text = f"""# RUN_SUMMARY

本轮目标：us stock selection v8/v8.2 final closeout and strategy decision pack。

新 run 目录：`{out_dir}`

zip：`{zip_path}`

最终 best：`v8_baseline_return_priority`

risk-control variant：`v8_2_high_beta_penalty_0p05`

是否替代 v8 baseline：`False`

是否进入 v9：`False`

是否扩 universe：`False`

是否训练新模型：`False`

是否运行 31b：`False`

是否新增参数/新回测：`False`

是否继续 overlay/reranking：`False`

后续：暂停；如继续，需新立项 longer history / universe redesign / stock selection model rebuild / validation framework upgrade。
"""
    (PROJECT_ROOT / "RUN_SUMMARY.md").write_text(text, encoding="utf-8")
    (out_dir / "RUN_SUMMARY.md").write_text(text, encoding="utf-8")


def sync_meistock(
    timestamp: str,
    out_dir: Path,
    zip_path: Path,
    docs: list[Path],
    comparison: pd.DataFrame,
    decision: dict[str, Any],
) -> pd.DataFrame:
    rows = []
    if not MEISTOCK_ROOT.exists():
        return pd.DataFrame(
            [{"target": str(MEISTOCK_ROOT), "status": "warning", "note": "MeiStock root does not exist; skipped sync"}]
        )
    targets = {
        "checkpoint": MEISTOCK_ROOT / "01_对话沉淀" / "Codex",
        "reports": MEISTOCK_ROOT / "02_项目文档" / "报告章节底稿",
        "decision": MEISTOCK_ROOT / "03_决策日志",
        "map": MEISTOCK_ROOT / "04_文件地图",
        "evidence": MEISTOCK_ROOT / "06_证据链",
        "attachments": MEISTOCK_ROOT / "07_附件索引",
        "control": MEISTOCK_ROOT / "00_项目总控",
        "context": MEISTOCK_ROOT / "docs" / "context",
    }
    for target in targets.values():
        target.mkdir(parents=True, exist_ok=True)
    for doc in docs:
        dest = targets["reports"] / doc.name
        shutil.copy2(doc, dest)
        rows.append({"target": str(dest), "status": "copied", "note": "report"})
    for source in [
        out_dir / "us_stock_selection_final_strategy_comparison.csv",
        out_dir / "us_stock_selection_final_decision.json",
        out_dir / "us_stock_selection_evidence_package_index.csv",
        out_dir / "us_stock_selection_meistock_sync_index.csv",
    ]:
        if source.exists():
            dest = targets["evidence"] / f"{timestamp}_{source.name}"
            shutil.copy2(source, dest)
            rows.append({"target": str(dest), "status": "copied", "note": "evidence"})
    shutil.copy2(PROJECT_ROOT / "NEXT_STEPS.md", targets["control"] / "NEXT_STEPS.md")
    rows.append({"target": str(targets["control"] / "NEXT_STEPS.md"), "status": "copied", "note": "control"})
    if zip_path.exists():
        dest = targets["attachments"] / zip_path.name
        shutil.copy2(zip_path, dest)
        rows.append({"target": str(dest), "status": "copied", "note": "zip"})
    summary = f"""# US Stock Selection Final Strategy Decision {timestamp}

- Final best: `v8_baseline_return_priority`
- Risk-control variant: `v8_2_high_beta_penalty_0p05`
- Replace best: `False`
- Allow enter v9: `False`
- Continue overlay/reranking tuning: `False`
- Next stage requires new approval: `True`
"""
    decision_path = targets["decision"] / f"{timestamp}_us_stock_selection_final_strategy_decision.md"
    decision_path.write_text(summary, encoding="utf-8")
    rows.append({"target": str(decision_path), "status": "written", "note": "strategy conclusion summary"})
    roadmap_index = f"""# US Stock Selection Next Roadmap Index {timestamp}

路线图已归档：更长历史、universe redesign、stock selection model rebuild、strict validation framework、paper trading。

Main zip: `{zip_path}`
"""
    roadmap_index_path = targets["map"] / f"{timestamp}_us_stock_selection_next_research_roadmap_index.md"
    roadmap_index_path.write_text(roadmap_index, encoding="utf-8")
    rows.append({"target": str(roadmap_index_path), "status": "written", "note": "roadmap index"})
    checkpoint = f"""# Codex Checkpoint - US Stock Selection v8/v8.2 Final Closeout {timestamp}

- Final best: `v8_baseline_return_priority`
- Risk-control variant: `v8_2_high_beta_penalty_0p05`
- Replace v8 best: `False`
- Allow enter v9: `False`
- Do not continue overlay/reranking tuning.
- Zip: `{zip_path}`
"""
    checkpoint_path = targets["checkpoint"] / f"{timestamp}_us_stock_selection_v8_v8_2_final_closeout_checkpoint.md"
    checkpoint_path.write_text(checkpoint, encoding="utf-8")
    rows.append({"target": str(checkpoint_path), "status": "written", "note": "checkpoint"})
    context = f"""# MeiStock Current Context

Last updated: {timestamp}

Latest checkpoint: US stock selection v8/v8.2 final closeout.

Final best: `v8_baseline_return_priority`.

Risk-control variant: `v8_2_high_beta_penalty_0p05`.

No v9, no universe expansion, no model training, no 31b, no additional tuning. Next stage requires separate user/ChatGPT approval.

Latest zip: `{zip_path}`.
"""
    context_path = targets["context"] / "MeiStock_current_context.md"
    context_path.write_text(context, encoding="utf-8")
    rows.append({"target": str(context_path), "status": "written", "note": "context"})
    return pd.DataFrame(rows)


def package_outputs(out_dir: Path, docs: list[Path], zip_path: Path) -> None:
    files = [
        PROJECT_ROOT / "scripts" / "us_stock_selection" / "44_generate_v8_v8_2_final_closeout.py",
        PROJECT_ROOT / "NEXT_STEPS.md",
        PROJECT_ROOT / "RUN_SUMMARY.md",
        *docs,
    ]
    files.extend([p for p in out_dir.rglob("*") if p.is_file()])
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        seen: set[str] = set()
        for path in files:
            if not path.exists():
                continue
            arc = str(path.relative_to(PROJECT_ROOT)) if path.is_relative_to(PROJECT_ROOT) else path.name
            if arc in seen:
                continue
            seen.add(arc)
            zf.write(path, arc)


def main() -> None:
    args = parse_args()
    timestamp = args.timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = (args.out_dir or OUTPUT_ROOT / f"v8_v8_2_final_closeout_{timestamp}").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    logger = setup_logger(out_dir)
    logger.info("Starting v8/v8.2 final closeout pack. No backtest, no tuning.")

    baseline, p05, final_validation_verdict = read_metrics()
    evidence = build_evidence_index()
    comparison = build_strategy_comparison(baseline, p05)
    decision = build_final_decision(evidence)
    decision["source_final_validation_verdict"] = final_validation_verdict

    comparison.to_csv(out_dir / "us_stock_selection_final_strategy_comparison.csv", index=False, encoding="utf-8-sig")
    evidence.to_csv(out_dir / "us_stock_selection_evidence_package_index.csv", index=False, encoding="utf-8-sig")
    write_json(decision, out_dir / "us_stock_selection_final_decision.json")

    zip_path = OUTPUT_ROOT / f"us_stock_selection_quant_lab_v8_v8_2_final_closeout_{timestamp}.zip"
    docs = write_docs(timestamp, out_dir, zip_path, comparison, decision, evidence)
    update_next_steps(out_dir, zip_path)
    write_run_summary(out_dir, zip_path)
    package_outputs(out_dir, docs, zip_path)
    sync_index = sync_meistock(timestamp, out_dir, zip_path, docs, comparison, decision)
    sync_index.to_csv(out_dir / "us_stock_selection_meistock_sync_index.csv", index=False, encoding="utf-8-sig")
    package_outputs(out_dir, docs, zip_path)
    if MEISTOCK_ROOT.exists() and zip_path.exists():
        dest = MEISTOCK_ROOT / "07_附件索引" / zip_path.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(zip_path, dest)
    logger.info("Packaged final closeout zip: %s", zip_path)


if __name__ == "__main__":
    main()
