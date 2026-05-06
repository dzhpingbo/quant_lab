# v8.2 frozen Pool A 与 v9 local replay 反向差异审计

## 结论

- Classification：`invalid_or_needs_human_review`
- requires_human_review：`True`
- allow_expand_universe：`False`
- allow_enter_v10：`False`
- allow_trade_execution：`False`

本轮发现明确评估窗口不一致：v9 local replay 的 `daily_nav.csv` 从 2020-01-02 开始，但 first non-zero weight date 为 2024-02-01；v8.2 frozen / v9 loaded reproduction 使用 2024-01-02 到 2026-04-17 的 575 天窗口。因此 v9 local official/full CAGR 不能与 v8.2 frozen CAGR 直接比较。

统一到 2024-01-02 后，v9 local replay 的 CAGR 会被重新年化到 575 天口径，但 Top5/Top10 仍未接近复现 v8.2 frozen 高收益；差异从“窗口口径错误”进一步落到 score provenance、feature/data source、loaded reproduction 非独立复算和 baseline-only exception 污染。

## 必答问题

1. v9 local replay official/full CAGR 是否因 2020-2023 零仓位期被计入而不可直接比较：是。full daily_count=1581，统一窗口 daily_count=575。
2. v8.2 frozen 高收益是否能在统一 2024-01-02 起算窗口由 v9 local replay 接近复现：不能。Top5 v8.2 CAGR=64.21% vs v9 local=37.35%；Top10 v8.2 CAGR=51.64% vs v9 local=31.70%。
3. PLTR/SNOW baseline-only exception 是否污染 Pool A 复现结论：是。见 `baseline_exception_audit.csv` 和 `candidate_replay_diff_by_ticker.csv`。
4. 是否发现未来函数、标签泄露、执行时点错误或测试集筛选证据：未发现已确认的未来函数/标签泄露证据；`time_alignment_audit.csv` 在上一轮为 pass。静态扫描发现 audit-forward 字段、历史结果加载、下载路径和执行时点逻辑需要继续人工复核，但本脚本未调用外部数据下载。
5. v8.2 frozen loaded reproduction 是否独立复算：不是。v9 loaded reproduction 来自 `load_v8_2_reproduction` 读取历史 v8.2 daily/holdings/metrics。

## 证据链

- v9 local Top5 official/full daily_count=1581，CAGR=12.23%；统一 2024-01-02 窗口 daily_count=575，CAGR=37.35%。
- v8.2 frozen Top5 统一窗口 CAGR=64.21%，Calmar=1.6340；v9 local Top5 统一窗口 CAGR=37.35%，Calmar=1.2375，仍未接近复现。
- v8.2 frozen Top10 统一窗口 CAGR=51.64%，Calmar=1.5313；v9 local Top10 统一窗口 CAGR=31.70%，Calmar=1.0825。
- v9 loaded reproduction 的 score_source 是 loaded_from_v8_2_reproduction，属于读取历史 v8.2 结果，不是独立复算。
- PLTR/SNOW 在 v9 数据质量中为 baseline-only exception，但仍出现在 Pool A reproduction 和本地 replay 持仓/贡献中。

## 风险评级

- 评估窗口风险：高。v9 local official/full CAGR 把 2020-2023 零仓位期纳入 annualization，不能与 v8.2 的 575 天口径直接比较。
- 方法口径风险：高。v8.2 frozen、v9 loaded reproduction、v9 local replay 的 score provenance 和 feature source 不一致。
- 复现风险：高。统一窗口后 v9 local replay 仍未在 CAGR/Calmar/MaxDD 阈值内接近 v8.2 frozen。
- baseline-only 污染风险：高。PLTR/SNOW 明确为 v9 baseline-only exception 且有选择/贡献记录。
- 静态扫描：194 条风险命中，其中 high=42；未据此确认未来函数或标签泄露。

## 关键输出

- Run：`E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\v82_v9_replay_diff_audit_20260503_232513`
- `audit_summary.json`
- `v82_v9_method_diff.csv`
- `candidate_replay_diff.csv`
- `active_window_metrics.csv`
- `monthly_selection_diff.csv`
- `candidate_replay_diff_by_ticker.csv`
- `data_lineage_audit.csv`
- `leakage_static_scan.csv`
- `baseline_exception_audit.csv`
- `reports/v82_v9_replay_diff_audit_summary.xlsx`

## 下一步建议

下一轮仍不得扩池、不得进入 v10、不得做任何执行接入。只允许同池、同策略、同 gate，在统一 2024-01-02 窗口下补一个真正 score-provenance 对齐的 replay：要么用 v8.1 score/rank audit trail 独立重算 v8.2 Top5/Top10，并与 v9 local 的 score/rank 逐月逐 ticker 对齐；要么证明 v8.2 原始 score 生成链可从本地 raw feature + model 完整复现。
