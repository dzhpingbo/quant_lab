# US Stock Selection Strategy Usage Guide

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
