# 量化分析项目 ChatGPT 上下文总摘要

生成日期：2026-05-05  
用途：在新 ChatGPT 会话、Codex、WorkBuddy 中恢复 `量化分析` 项目的关键上下文。  
本地项目路径：`E:\dzhwork\quant\quant_lab`  
MeiStock 知识库路径：`E:\dzhwork\obsydian\quant_lab\MeiStock`  
GitHub 仓库：`dzhpingbo/quant_lab`

---

## 0. 总体说明

本摘要覆盖当前 `量化分析` 项目相关的长期对话，包括：

1. 美股选股策略最佳实践与 Qlib + vectorbt 落地；
2. Codex / ChatGPT / WorkBuddy 自动协作机制；
3. MeiStock 知识库沉淀；
4. US Stock Selection v8/v8.2/v9/v9.1/formal v9 研究链路；
5. Limited MVE2 / MVE1 数据审计；
6. A股 / 美股 ETF 趋势策略研究；
7. 银行 IRRBB 模型验证相关项目上下文。

本摘要不替代正式 run 输出、报告、Excel、zip、证据链文件。它用于新会话快速恢复上下文，避免长会话丢失。

---

## 1. 用户角色与偏好

用户从事风险模型验证，对模型验证、审计证据链、样本外检验、稳健性和可复现性要求高。用户不接受只给理论，不接受空泛建议，要求：

- 结论必须落到代码、文件、报告、zip、证据链；
- 不能隐藏失败、报错、warning、超时；
- 不能把研究候选包装成可交易结论；
- 重大 gate 必须人工审阅；
- Codex 适合执行，ChatGPT 适合研究总监式审阅；
- WorkBuddy 适合本地自动化搬运、整理和执行 UI 操作。

---

## 2. 美股选股策略最佳实践：核心目标

用户认为：相比单一策略，选股更重要。目标不是找历史涨幅最高的股票，而是找出：

> 在当前可获得数据、因子、模型和策略能力范围内，哪些美股标的或组合最容易被量化系统挖掘出高 Calmar、高 CAGR、低回撤、较低过拟合风险的策略。

研究范围：

- ETF / 指数产品：`QQQ, QLD, TQQQ, SPY, SSO, UPRO, IWM, SOXX, SMH, XLK, GLD, TLT, SHY`；
- 七巨头：`NVDA, MSFT, AAPL, GOOGL, AMZN, META, TSLA`；
- 科技成长股、半导体、AI、软件、云计算、网络安全、高波动主题股；
- 后续可扩 Nasdaq100、S&P500，但必须经过严格 gate。

核心框架：

- `Qlib`：数据、因子、AI 模型、横截面预测打分；
- `vectorbt` / `canonical_replay_engine`：组合回测、执行层验证、复算、压力测试；
- 项目已有大量因子，约 4000+。

核心指标：

- 主指标：Calmar；
- 硬性指标：CAGR、MaxDD、50bps/T+1、T+2、single-year share、top ticker share、remove top year/ticker、score provenance、price source、成本、滑点、执行日、eligibility。

---

## 3. 美股研究方法论演进

### 3.1 早期：单票策略搜索

最早的 Codex 任务是建立 `us_stock_selection` 模块：

- 多层 universe；
- 数据质量检查；
- 因子体系；
- 单标的 vectorbt 策略搜索；
- walk-forward；
- ranking；
- Excel / Markdown 报告。

很快发现：单票择时策略主要是 risk reducer，没有任何 test 策略 CAGR 战胜 buy-and-hold。因此研究主线从“单票技术择时策略搜索”转为：

```text
Qlib-first 横截面 AI 选股 / 打分 + vectorbt / canonical engine 严格验收
```

### 3.2 v4：Qlib-first 初步突破

v4 使用 fallback qlib-like panel，出现首次突破：

- 最佳 signal：`alpha158_like + ridge + forward_return_20d`；
- 最佳组合：`alpha158_like + ridge + forward_return_5d + safe_switch monthly Top1`；
- CAGR 约 `35.00%`，MaxDD 约 `-34.24%`，Calmar 约 `1.022`。

但不是 true Qlib provider，且 walk-forward 不稳，只能作为候选。

### 3.3 v5：true Qlib provider 与 v4 审计

true Qlib US provider 下载成功，路径：

```text
C:\Users\Administrator\.qlib\qlib_data\us_data
```

但官方样例 US 数据截止 `2020-11-10`，不能验证 2022-2026。v4 没发现明显未来函数，但稳定性不足，分类 `promising_but_unstable`。

### 3.4 v6：本地 Qlib bin provider 与真 Qlib workflow

构建本地 provider：

```text
C:\Users\Administrator\.qlib\qlib_data\us_data_local_2026
```

覆盖 `2020-01-02` 至 `2026-04-17`，导入 ticker 36 个。Alpha158/Alpha360 Handler、qrun、workflow-by-code 均成功。Top5/Top10 组合表现强，但严格 Handler retrain WF 在 Windows 超时，分类仍 `promising_but_unstable`。

### 3.5 v7：feature cache + fast walk-forward

创建 parquet feature cache，避免重复 Handler 重算。初版出现 mean Calmar 83.44，ChatGPT 判断异常，要求反向审计。

### 3.6 v7 long-window validation

用年度/两年 OOS 长窗口替代短窗口，最佳为：

```text
Alpha360 + ElasticNet + label_5d + top5_equal_monthly
```

结果：

- annual-like windows：7；
- mean CAGR：67.87%；
- winsorized Calmar mean：2.70；
- 50bps cost mean CAGR：48.20%；
- same-window vs QQQ CAGR / Calmar win rate 100%。

ChatGPT 判断：可以进入 v8，但不能扩池、不能交易化。

### 3.7 v8：paper-trading replay

v8 冻结 v7 最佳，做 pseudo-live / paper-trading replay。结果强，但 ElasticNet convergence warning rate = 1.0，single-year share = 52.6%，不允许 v9。Challenger 中 LGBModel、Ridge 表现强。

### 3.8 v8.1：主模型切换为 LGBModel / Ridge

LGBModel 分支：

- CAGR 80.40%；
- Calmar 2.05；
- MaxDD -39.30%；
- 50bps/T+1 CAGR 72.23%，Calmar 1.80；
- warning rate 0；
- top ticker share 14.15%；
- single-year share 65.78%，未过 gate。

Ridge 分支同样强，但 single-year share 56.58%。因此仍不许 v9。

### 3.9 v8.2：年度收益集中度压降

最佳组合：

```text
top5_ytdcap80p_derisk100p
```

含义：Top5 equal monthly + YTD return cap 80% + 触发后 100% derisk。主线：

```text
Alpha360 + LGBModel + label_5d
```

结果：

- CAGR 64.21%；
- Calmar 1.6340；
- MaxDD -39.30%；
- 50bps/T+1 CAGR 54.06%；
- 50bps/T+1 Calmar 1.3453；
- single-year share 49.68%；
- top ticker share 13.79%；
- remove top year 后 CAGR 52.16%，Calmar 1.3272；
- remove top ticker 后 CAGR 48.97%，Calmar 1.3265；
- 分类：`v9_ready_research_candidate`。

---

## 4. formal v9 相关最新状态

### 4.1 原 formal v9 失败

formal v9 初次执行后分类：`formal_v9_failed_due_to_eligibility`。

原因：Pool A reproduction 通过，但 Pool A + small growth 实际没有形成新增扩池，有效新增 growth ticker 数为 0。29 个候选被剔除，原因：

```text
missing_canonical_qlib_provider_bin; missing_formal_alpha360_lgb_score_source
```

### 4.2 score provenance 对齐审计

一次审计发现：

- classification = `score_provenance_mismatch`；
- score provenance 不一致；
- method/window 不一致；
- return reconstruction 不一致；
- baseline exception pollution 根因：PLTR / SNOW 是 baseline reproduction only ticker，污染了 reproduction/local replay 贡献；
- v9 原始结果废弃；
- unified replay 只能作为审计证据。

### 4.3 v8.2 canonical source-of-truth 重建

输出：

```text
E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\v82_canonical_rebuild_20260504_090549
```

结论：`formal_v82_valid_ready_for_formal_v9`。

v8.2 reported vs recomputed 一致：

- CAGR diff 2.84e-7；
- MaxDD diff -2.18e-8；
- Calmar diff 6.33e-7。

差异根因是 `price_source_mismatch`：v8.2 原始引擎使用 local Qlib provider bin `$close`，上一轮本地复算误用了 `data/unified_ohlcv/.../prices`。

formal_v82_baseline gate 通过。

### 4.4 v9.1 数据补齐

v9.1 已补齐 small-growth canonical provider 与 frozen score provenance：

```text
输出目录：E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014
provider：C:\Users\Administrator\.qlib\qlib_data\us_data_local_2026_v91_growth
```

结果：

- classification：`v9_1_ready_for_formal_v9_rerun`；
- Alpha360 cache 成功：96872 rows，360 features，64 instruments；
- LGBModel score provenance 成功：18 个 score month，1147 score rows，fit failed count = 0；
- 新增 growth ticker 数据补齐 28/29；
- 新增 eligible growth ticker 数 28；
- 23 个新增 ticker 曾进入 Top5 candidate；
- Pool A reproduction 仍完全对齐 v8.2 canonical；
- SQ 未补齐，保持 excluded/missing。

当前被批准的下一步：formal v9 rerun。不得进入 v10，不得交易化，不得扩 Nasdaq100/S&P500。

---

## 5. 当前冻结策略与 formal v9 rerun 要求

冻结策略：

```text
feature_set: Alpha360
model: LGBModel
label: label_5d
portfolio: top5_ytdcap80p_derisk100p
rebalance: monthly
execution: T+1
cost: 5bps
slippage: 5bps
max_weight: 20%
ytd_return_cap: 80%
derisk_after_trigger: 100%
price_source: v9.1 local Qlib provider bin $close
replay_engine: canonical_replay_engine
eligibility_rule: v8.2/v9.1 canonical dynamic eligibility rule
```

正式数据源：

```text
provider_uri: C:\Users\Administrator\.qlib\qlib_data\us_data_local_2026_v91_growth
feature_cache: E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_feature_cache\alpha360_feature_cache.parquet
score_provenance: E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_score_provenance\monthly_prediction_scores.parquet
```

formal v9 rerun 必须输出四组：

1. Pool A reproduction；
2. Pool A + small growth 主结果；
3. small growth only 观察项；
4. ex-high-vol 稳健观察项。

formal v9 gate：CAGR >=20%、Calmar >=1、50bps/T+1 仍过、single-year share <=50%、top ticker share <=30%、remove top year/ticker 后仍过、不依赖 COIN/MSTR/PLTR、无 score mismatch、无 price source mismatch、无 baseline pollution。

---

## 6. Codex / ChatGPT / WorkBuddy 自动化上下文

### 6.1 GitHub bridge 失败与替代方案

GitHub bridge 曾实现：Issue task、Reviewer/Worker 输出、GitHub Issue 写回，但用户反馈总是报错、链条复杂，不够稳定。

推荐替代：

```text
Codex Goal 自循环 + WorkBuddy UI bridge 做重大 gate 审阅
```

思路：

- Codex 平时自己跑工程迭代；
- 到 needs_human_review、v10_ready、异常结果、扩池、交易化前；
- WorkBuddy 自动把 REVIEW_PACKET 发给 ChatGPT；
- ChatGPT 输出 NEXT_CODEX_TASK；
- WorkBuddy 自动喂回 Codex。

### 6.2 Codex Goal 内容

已建议设置 Codex Goal，标题：

```text
quant_lab 美股 Qlib+vectorbt 策略能力范围选股研究
```

Goal 中必须包括当前路径、冻结策略、禁止事项、重大 gate、当前下一步 formal v9 rerun。

### 6.3 WorkBuddy 本地沉淀任务

用户要求将 ChatGPT 总结写入 MeiStock：

```text
E:\dzhwork\obsydian\quant_lab\MeiStock
```

用户上传的目录清单显示：

- `01_对话沉淀\ChatGPT` 为空；
- `01_对话沉淀\Codex` 已有多个 checkpoint；
- `02_项目文档\报告章节底稿` 已有大量 US_STOCK_SELECTION 文档；
- `06_证据链` 已有 57 个证据 CSV/JSON；
- `checkpoint` 已有 v8、v8.1、v8.2、v9_growth_pool 等子目录。

因此 WorkBuddy 不应重复写入 Codex 已有内容，应只补充 ChatGPT 视角总摘要、读取提示词、当前上下文和任务入口。

建议新增 MeiStock 文件：

```text
01_对话沉淀\ChatGPT\20260505_美股选股策略最佳实践_ChatGPT长会话总摘要.md
05_提示词库\20260505_新会话读取上下文提示词.md
00_项目总控\20260505_当前阶段与下一步_ChatGPT审阅版.md
04_文件地图\20260505_ChatGPT上下文文件地图.md
```

如果这些文件已存在且内容相同或更新，不要重复写入；如需更新，先备份旧文件。

---

## 7. 新会话读取提示词

用户可在新 ChatGPT 会话发送：

```text
请读取 GitHub 仓库 `dzhpingbo/quant_lab` 的以下上下文文件，并基于它恢复《美股选股策略最佳实践》与量化分析项目上下文：

1. `docs/chatgpt_bridge/context/quant_analysis_project_context_20260505.md`
2. `docs/chatgpt_bridge/context/us_stock_selection_best_practice_context_20260504.md`，如果存在
3. `docs/chatgpt_bridge/LATEST.md`，如果存在
4. `docs/chatgpt_bridge/latest_run_manifest.json`，如果存在
5. `RUN_SUMMARY.md`，如果存在
6. `NEXT_STEPS.md`，如果存在
7. `AGENTS.md`
8. `docs/US_STOCK_SELECTION_AUTORUN.md`

读取后请先输出：
- 当前研究阶段；
- 最近通过 gate 的策略；
- 当前冻结主线；
- 允许和禁止的下一步；
- 需要 Codex 执行的下一条任务。

不要要求我重新上传 zip，不要重新从头解释历史上下文。请直接基于 GitHub 中的上下文继续。
```

---

## 8. 其他量化分析项目上下文

### 8.1 A股 / ETF 趋势策略

历史研究包括 TQQQ、QLD、A股 ETF 等趋势策略。TQQQ 曾出现 `atr18_2p5+cd10+confirm_2d` 组合在某阶段表现强，但需警惕参数邻域运气和 spike-prone 风险。QLD 存在 Pareto frontier。用户重视 MDD<=35/40/45%、CAGR、Calmar。

### 8.2 Limited MVE2 / MVE1

已完成 limited MVE2 搜索和验证，相关输出已同步 MeiStock checkpoint：

- `limited_mve2_20260502_142702`；
- `limited_mve2_validation_20260502_183459`；
- `limited_mve2_validation_20260502_183555`。

用户明确要求：不得使用旧 qlib、旧 v8 cache、未审计数据；统一使用 audited adjusted OHLCV store。

### 8.3 量化框架选择

用户已多次讨论 qlib、vectorbt、backtrader、zipline、VN.py。当前主结论：

- Qlib 用于数据、因子、AI 建模、横截面打分；
- vectorbt 用于策略验证、组合回测、参数搜索、执行层模拟；
- 两者组合是当前项目主线。

---

## 9. IRRBB / 银行模型验证上下文简述

虽然当前会话主要是美股量化，但 `量化分析` 项目中也存在大量银行模型验证上下文：

1. IRRBB 无明确到期日存款稳定比例 / 期限分布模型验证；
2. 定期存款提前支取率 / 贷款提前还款率模型验证；
3. ARIMA/ARIMAX/MinBal、核心比例回归、复制投资组合；
4. 时间序列余额预测标准：MAPE、coverage95、stable breach；
5. 二值类时间序列标准：AUC/AR 下限、MSE vs π(1-π)、正例样本数、非缺失率、验证集样本数；
6. 报告要求：删除不适用章节、修订模式、2.4 验证结论、模型应用验证、第八章等；
7. 用户要求验证报告语言去 AI 味、章节一致、证据链可追溯。

若新会话涉及 IRRBB，需要优先读取项目里相关报告和用户上传文件，不要用本摘要替代原始资料。

---

## 10. 当前下一步

如果继续美股 formal v9：执行 formal v9 rerun，基于 v9.1 补齐后的 provider、Alpha360 cache、LGBModel score provenance 和 canonical replay engine，判断 Pool A + small growth 是否通过 v9 gate。执行后不得进入 v10，必须等待人工审阅。

如果先整理知识库：让 WorkBuddy 将本摘要和提示词写入 MeiStock，避免与 Codex 已有文件重复。
