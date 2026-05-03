# quant_lab 项目级交接文档 - 2026-04-18

本文件是对当前 `quant_lab` 工作区的项目级汇总，面向新 Codex 用户或新账号接手。它只汇总已经落到本地文件系统里的证据，并明确标出哪些信息来自本地文件，哪些历史任务如果要复盘细节仍可能需要补充聊天上下文。

## 读取结论

- [本地文件] 项目根目录：`E:\dzhwork\quant\quant_lab`。
- [本地文件] 当前工作区不是 git 仓库，后续接手应以本地文件、报告、checkpoint、CSV 和脚本为事实来源。
- [本地扫描] 本次扫描目录包括：`docs`、`outputs`、`scripts`、`data\external_repos`、项目根目录 `external_repos`。
- [本地扫描] `data\external_repos` 不存在。真实外部仓库归档在 `external_repos`。
- [本地扫描] `rg.exe` 在本机 PowerShell 中执行失败，错误为 `Access is denied`。后续搜索可使用 `Get-ChildItem`、`Select-String` 或修复 `rg` 权限后再用。
- [本地文件] 旧数据镜像在 `data\external\legacy_quant`，映射文档是 `docs\data_migration_map.md`。
- [本地文件] 重要 Codex skill：`C:\Users\Administrator\.codex\skills\588200-pool\SKILL.md`。继续 588200Pool 相关研究时应优先读它。

## 本地证据范围

### 文档目录

[本地扫描] `docs` 下发现 14 个文档或提示词文件：

| 文件 | 用途 |
| --- | --- |
| `docs\588200_strategy_optimizer.md` | 早期 588200 股票池优化器推荐和使用方法 |
| `docs\588200pool_context_handoff_20260415.md` | 588200Pool 专项上下文交接 |
| `docs\codex_handoff_quant_lab_full_audit_20260418_175017.md` | 2026-04-18 全量审计交接，包含较完整历史脉络 |
| `docs\codex_handoff_strategy_factor_dual_framework_20260418_173351.md` | 策略库/因子库双框架交接 |
| `docs\codex_prompt_quant_lab_full_audit_20260418_175017.txt` | 上一版全量审计的新 Codex 提示词 |
| `docs\codex_prompt_strategy_factor_dual_framework_20260418_173351.txt` | 双框架任务的新 Codex 提示词 |
| `docs\codex_user_switch_handoff_20260418.md` | 美股和 TD9 相关用户切换交接 |
| `docs\codex_user_switch_prompt_20260418.txt` | 美股和 TD9 相关新 Codex 提示词 |
| `docs\data_migration_map.md` | D 盘历史数据到 quant_lab 的镜像路径映射 |
| `docs\dual_framework_strategy_reuse.md` | vectorbt 与 Qlib 双框架复用说明 |
| `docs\external_factor_adapters.md` | 外部因子适配器说明 |
| `docs\external_resource_reuse.md` | 外部资源复用层说明 |
| `docs\quant_lab_strategy_factor_upgrade_plan_20260412.md` | 策略安全层和因子库升级方案 |
| `docs\report_generation_standard.md` | 后续策略报告必须包含的解释规范 |

### 输出目录总览

[本地扫描] `outputs` 下发现 17 个一级输出主题，共计 802 个文件，其中 Markdown 121 个、JSON 134 个、CSV 512 个。按一级输出目录汇总如下：

| 输出目录 | 文件数 | 报告数 | checkpoint 数 | best_config 数 | summary CSV 数 | 最新写入 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `588200_generalized_strategy` | 28 | 5 | 1 | 5 | 6 | 2026-04-12 17:18 |
| `588200_generalized_strategy_smoke` | 6 | 1 | 1 | 1 | 2 | 2026-04-12 13:26 |
| `588200_longrun_factor_strategy` | 20 | 3 | 2 | 3 | 4 | 2026-04-13 12:06 |
| `588200_ma_crossover_strategy` | 6 | 1 | 1 | 1 | 2 | 2026-04-13 15:29 |
| `588200_safety_upgrade` | 10 | 2 | 0 | 2 | 2 | 2026-04-12 18:34 |
| `588200_sideways_filtered_strategy` | 8 | 1 | 1 | 1 | 2 | 2026-04-13 18:12 |
| `588200_strategy_optimization` | 10 | 1 | 0 | 2 | 2 | 2026-04-12 08:48 |
| `588200_td9_indicator_combo` | 11 | 0 | 2 | 1 | 3 | 2026-04-15 21:52 |
| `588200_td9_ma_simple` | 13 | 0 | 0 | 2 | 2 | 2026-04-15 23:51 |
| `factor_library_eval` | 12 | 4 | 0 | 0 | 4 | 2026-04-13 00:00 |
| `factor_library_imports` | 44 | 1 | 3 | 0 | 0 | 2026-04-16 22:05 |
| `us_leveraged_etf_full_strategy` | 199 | 1 | 64 | 1 | 7 | 2026-04-17 11:14 |
| `us_leveraged_etf_holding_strategy` | 26 | 2 | 0 | 2 | 6 | 2026-04-16 05:12 |
| `us_leveraged_etf_momentum_combo` | 124 | 4 | 36 | 2 | 3 | 2026-04-18 08:50 |
| `us_leveraged_etf_vectorbt_online_strategies` | 128 | 4 | 40 | 2 | 9 | 2026-04-18 00:21 |
| `us_leveraged_etf_walk_forward` | 7 | 1 | 4 | 0 | 1 | 2026-04-17 06:11 |
| `us_td9_all_assets` | 166 | 2 | 22 | 2 | 12 | 2026-04-18 09:59 |

### 脚本目录

[本地扫描] `scripts` 下发现 40 个脚本文件。按用途归类：

- 588200/588200Pool：`backtest_588200_real.py`、`full_backtest_588200.py`、`optimize_588200_strategy.py`、`research_588200_generalized_strategy.py`、`longrun_588200_factor_strategy_search.py`、`validate_588200_safety_upgrade.py`、`research_588200_ma_crossover_strategy.py`、`research_588200_sideways_filtered_strategy.py`、`research_588200_td9_indicator_combo.py`。
- 美股/杠杆 ETF/vectorbt：`research_us_leveraged_etf_full_strategy.py`、`walk_forward_us_leveraged_etf_stability.py`、`vbt_us_leverage_online.py`、`vbt_us_leverage_momentum_combo.py`、`vbt_us_td9_all_assets.py`。
- 因子库/框架复用：`build_factor_library.py`、`evaluate_factor_library.py`、`export_qlib_workflow_config.py`。
- 数据下载与诊断：`download_yfinance.py`、`download_688_kline.py`、`download_etf_data.py`、`download_etf_sina.py`、`download_etf_stable.py`、`download_etf_yfinance.py`、`explore_etf_sources.py`、`retry_sh_fails.py`、`scan_10y_stocks.py`、`scan_etf.py`、`diagnose_speed.py`、`diag_kline.py`、`check_fail_codes.py`。
- 测试/探测：`test_akshare.py`、`test_data_sources.py`、`test_etf_apis.py`、`test_fetch_3.py`、`test_sina_etf.py`、`test_xueqiu_api.py`、`test_xueqiu_conn.py`、`test_yf_batch.py`。
- 其他：`run_kc50_backtest.py`、`deploy.bat`、`deploy.sh`。

### 外部仓库和外部资源

- [本地扫描] `data\external_repos` 不存在。
- [本地扫描] 项目根目录存在 `external_repos`。
- [本地扫描] `external_repos\factor_libraries` 共 824 个文件，约 70.65 MB，最新写入 2026-04-16 21:40。
- [本地扫描] 主要归档目录包括：`alpha360_microsoft_qlib`、`worldquant_alpha101_sthsf`、`worldquant_alpha101_yli188`、`gtja_alpha191_selenama`、`fama_french`、`joinquant_jqdatasdk`、`joinquant_jqfactor_analyzer`、`ricequant_rqalpha`、`ricequant_rqalpha_mod_rqdata`、`barra_like_alphatrading`、`barra_msci`、`huatai_multifactor_framework_public_alt`、`crypto_factors`、`crypto_panda_public_alt`、`pead_earnings_trade_backtest`、`pead_harikumar_ganesh`、`tonglian_datayes_424`、`python_package_archives`。
- [本地文件] `external_repos\factor_libraries\FAILED_DOWNLOADS.md` 记录仍受限或失败的下载：DataYes/UQER 424、MSCI Barra 官方数据/模型、JoinQuant 完整平台因子数据、RiceQuant 完整平台因子数据、`rqalpha-mod-rqfactor`、华泰官方千因子/AI 热点模型、Crypto Factors CSV/TXT。
- [本地文件] `external_repos\karpathy_autoresearch\SOURCE.md` 说明 `karpathy/autoresearch` 未完整 clone，原因是 shell 对 GitHub 443 和 `raw.githubusercontent.com` 访问失败；本地只保存了来源说明和抽象方法论。

## 已落地历史任务

### 1. 数据迁移

- [本地文件] `docs\data_migration_map.md` 记录：`D:\dzhwork\quant` 已镜像到 `E:\dzhwork\quant\quant_lab\data\external\legacy_quant`，未删除或移动 D 盘原始文件。
- [本地文件] 验证口径：源目录与目标镜像均为 18,545 个文件，9.977 GB。
- [本地文件] 后续代码应优先使用 `configs\env\local.yaml` 的路径键，例如 `legacy_astock_daily` 和 `legacy_quant_root`。

### 2. 588200 股票池早期优化器

- [本地文件] 文档：`docs\588200_strategy_optimizer.md`。
- [本地文件] 脚本：`scripts\optimize_588200_strategy.py`。
- [本地文件] 输出：`outputs\588200_strategy_optimization\20260412_064816`。
- [本地文件] best_config：`best_config_20260412_064816.json`，策略为 `MA_TREND__M__top5__etf_ma60`。
- [本地文件] 规则摘要：月频调仓，588200 ETF 高于 60 日均线才持仓，成分股按 `0.7 * zscore(ma_trend_20_60) + 0.3 * zscore(liquidity20)` 选 Top 5 等权。
- [本地文件] 旧报告记录：训练期年化 30.05%、样本外年化 45.71%、全样本年化 35.56%，最近一次信号日 2026-03-31、执行日 2026-04-01、风控关闭、空仓。

### 3. 588200 泛化买卖策略

- [本地文件] 脚本：`scripts\research_588200_generalized_strategy.py`。
- [本地文件] 主要输出：`outputs\588200_generalized_strategy\full_20260412_132729`。
- [本地文件] 最新完整 best_config：`best_config_20260412_171821.json`。
- [本地文件] 推荐策略：`momentum_vol__ma60__bb65__bs50__mom60__vol20__vp95`。
- [本地文件] 候选数：2192。
- [本地文件] 最新 588200 信号日：2026-04-08，`next_action=EMPTY_OR_SELL_588200`，目标空仓。
- [本地文件] 对应报告和 summary：`report_20260412_171821.md`、`strategy_summary_20260412_171821.csv`、`strategy_summary_checkpoint.csv`。

### 4. 588200 长跑因子策略和多因子组合

- [本地文件] 脚本：`scripts\longrun_588200_factor_strategy_search.py`。
- [本地文件] 输出：`outputs\588200_longrun_factor_strategy\longrun_20260412_205752` 与 `outputs\588200_longrun_factor_strategy\combo_20260412_224013`。
- [本地文件] 单因子 best_config：`factor_overlay__alpha_reversal_20__mom60__vol20__vp95__fb50__fs40`，候选数 2962。
- [本地文件] 多因子/TD9 组合 best_config：`factor_overlay__alpha_td9_sell_pressure_4_9__mom60__vol20__vp95__fb60__fs50`，候选数 16066。
- [本地文件] 推荐组合配置：`recommended_combo_config_20260412_235335.json`，推荐 `factor_overlay__combo2__alpha_intraday_strength_60__alpha_td9_sell_pressure_4_9__mom60__vol20__vp95__fb55__fs45`。
- [本地文件] 推荐组合报告：`report_recommended_combo_20260412_235515.md`，记录完整长跑 222 个因子宽度信号、16066 个策略候选、`strategy_summary_checkpoint.csv` 已跑满。
- [本地文件] 切换点核查：`audit_switch_points_20260413.md` 明确实际执行逻辑为收盘后生成信号、下一交易日开盘执行。

### 5. 588200 安全升级、MA 交叉、横盘过滤

- [本地文件] 安全升级脚本：`scripts\validate_588200_safety_upgrade.py`。
- [本地文件] 安全升级输出：`outputs\588200_safety_upgrade\20260412_183204`。
- [本地文件] 安全增强策略：`safety_mv__mom20__bb65__bs50__vol20__vp95__sb60__ss50`；基准仍为 `baseline_prev_best__mom60__breadth65_50__vol20_vp95`；候选数 487。
- [本地文件] MA 交叉脚本：`scripts\research_588200_ma_crossover_strategy.py`。
- [本地文件] MA 输出：`outputs\588200_ma_crossover_strategy\ma_cross_20260413_152740`；best 为 `ma_cross_pool_vol__ma5_60__bb55__bs45__vol120__vp90__poolmom`，robust 为 `ma_cross_pool_vol__ma5_20__bb55__bs45__vol120__vp90__poolmom`，候选数 276。
- [本地文件] 横盘过滤脚本：`scripts\research_588200_sideways_filtered_strategy.py`。
- [本地文件] 横盘过滤输出：`outputs\588200_sideways_filtered_strategy\sideways_20260413_164557`；best 为 `sideways_filter__ma20_60__bb55__bs45__vol120__vp90__adx14_15_gap_20__poolmom`，robust 为 `sideways_filter__ma5_20__bb55__bs45__vol120__vp90__er20_20`，候选数 11988。
- [本地文件] 上述 2026-04-08 口径的 588200 最新信号均为 `EMPTY_OR_SELL_588200`。

### 6. 588200 TD9/神奇九转相关研究

- [本地文件] TD9 指标组合脚本：`scripts\research_588200_td9_indicator_combo.py`。
- [本地文件] TD9 指标组合输出：`outputs\588200_td9_indicator_combo\td9_combo_stage2_20260415_213550`。
- [本地文件] best_config：`td9_combo__alpha_td9_sell_pressure_4_9__mom120__td50_40__bb55_bs45__vol120_vp90__poolmom__none__vix_below_ma20`，候选数 18144。
- [本地文件] 最新 2026-04-08 信号为 `EMPTY_OR_SELL_588200`。
- [本地文件] 简化实时 TD9/MA 输出：`outputs\588200_td9_ma_simple\td9_ma_20260415_233546` 与 `outputs\588200_td9_ma_simple\td9_ma_fast_20260415_234750`。
- [本地文件] `td9_ma_20260415_233546\best_config.json` 数据最新到 2026-04-15，候选数 27300，eligible 10559，推荐 `td9_buy_ma__ma10_20__buy3_r20__exit6`，信号 `BUY_OR_HOLD_588200`。
- [本地文件] `td9_ma_fast_20260415_234750\best_config.json` 数据最新到 2026-04-15，候选数 21385，eligible 7211，推荐 `td9_buy_ma__ma13_20__buy2_r1__exit7`，信号 `EMPTY_OR_SELL_588200`。
- [本地文件] `td9_ma_fast_20260415_234750\complex_best_latest_state.json` 的复杂 TD9 组合信号为 2026-04-15 `EMPTY_OR_SELL_588200`；成分股加载 46 只，失败代码为 `688249`、`688361`、`688709`、`688584`，原因 `too_short`。

### 7. 因子库导入、适配和复用

- [本地文件] 关键文档：`docs\external_resource_reuse.md`、`docs\external_factor_adapters.md`、`docs\dual_framework_strategy_reuse.md`。
- [本地文件] 关键输出：`outputs\factor_library_imports`。
- [本地文件] 主要 checkpoint 和 snapshot：
  - `outputs\factor_library_imports\checkpoint_20260416_factor_libraries.md`
  - `outputs\factor_library_imports\adapter_checkpoint_20260416.md`
  - `outputs\factor_library_imports\final_report_20260416_173822.md`
  - `outputs\factor_library_imports\full_reuse_catalog_snapshot_20260416.json`
  - `outputs\factor_library_imports\full_reuse_catalog_snapshot_20260416.md`
  - `outputs\factor_library_imports\full_reuse_checkpoint_20260416.md`
  - `outputs\factor_library_imports\worldquant_source_alpha101_runtime_status_20260416.csv`
- [本地文件] 已复用能力：452 个直接外部 panel 因子名；其中 82 个 WorldQuant Alpha101 可执行名、360 个 Qlib Alpha360 可执行名、10 个 GTJA Alpha191 本地可执行名。
- [本地文件] 已登记但需要授权的能力：JoinQuant Alpha101 API 101 个、JoinQuant Alpha191 API 191 个。
- [本地文件] 外部资源记录 18 个，外部策略/模型模板记录 9 个。
- [本地文件] `docs\external_factor_adapters.md` 说明 vectorbt 引擎可通过 `factor_names` 使用外部价格/成交量因子。

### 8. 因子库评估

- [本地文件] 脚本：`scripts\evaluate_factor_library.py`。
- [本地文件] 输出：`outputs\factor_library_eval`。
- [本地文件] 落地报告：`report_20260412_183912.md`、`report_20260412_184046.md`、`report_20260412_210928.md`、`report_20260412_235545.md`。
- [本地文件] 关键 CSV：`factor_ic_summary_*.csv`、`factor_spearman_corr_*.csv`。
- [本地文件] 这些报告属于因子 IC 和相关性检验，不等同于可直接交易策略。

### 9. 美股杠杆 ETF 全策略搜索

- [本地文件] 脚本：`scripts\research_us_leveraged_etf_full_strategy.py`。
- [本地文件] 输出：`outputs\us_leveraged_etf_full_strategy\full_us_20260416_010500`。
- [本地文件] 报告：`report.md`；best_config：`best_config.json`。
- [本地文件] 数据最新口径：TQQQ、QLD、QQQ、VIX 等更新到 2026-04-15。
- [本地文件] 可复用库覆盖：外部 panel 因子 452，WQ 82，Qlib 360，GTJA 10，本地因子 38，Fama-French 84，ML 模板 24。
- [本地文件] TQQQ best：`qqq_underlying_dual_thrust_w40_k0.3`，2026-04-15 信号 `HOLD_OR_BUY`，test 年化 51.33%、test maxDD -31.04%，full 年化 12.71%、full maxDD -58.25%。
- [本地文件] QLD best：`alpha_ret_skew_60_cs_high_top0.35`，2026-04-15 信号 `SELL_NEXT_OPEN`，test 年化 37.95%、test maxDD -19.32%，full 年化 9.57%、full maxDD -63.13%。
- [历史任务需聊天上下文] 用户曾认为这一版美股结果偏弱，要求继续改进。该判断在 `docs\codex_user_switch_handoff_20260418.md` 有记录，但如果要复盘用户的风险偏好和“偏弱”的具体标准，可能仍需查看原聊天。

### 10. 美股杠杆 ETF 持有策略、walk-forward、在线策略、动量组合

- [本地文件] 持有策略输出：`outputs\us_leveraged_etf_holding_strategy`。
- [本地文件] 持有策略 best_config：
  - `us_hold_20260416_050620\best_config.json`：TQQQ 与 QLD 都为 `qqq_ma180_band_e1p02_x1p0`，动作为 `HOLD_OR_BUY`。
  - `us_hold_fast_20260416_051031\best_config.json`：TQQQ 为 `asset_ma220_band_e1p02_x0p98`，QLD 为 `asset_ma220_band_e1p03_x1p0`，动作为 `HOLD_OR_BUY`。
- [本地文件] walk-forward 脚本：`scripts\walk_forward_us_leveraged_etf_stability.py`。
- [本地文件] walk-forward 输出：`outputs\us_leveraged_etf_walk_forward\wf_us_20260417_5y`；summary CSV 为 `walk_forward_summary.csv`。
- [本地文件] walk-forward 关键结果：TQQQ DualThrust fixed 当前参数 stitched 年化 19.37%、Sharpe 0.687、maxDD -37.81%；QLD ReturnSkew fixed 当前参数 stitched 年化 17.74%、Sharpe 1.032、maxDD -19.32%。
- [本地文件] 在线策略脚本：`scripts\vbt_us_leverage_online.py`。
- [本地文件] 在线策略最新输出：`outputs\us_leveraged_etf_vectorbt_online_strategies\vbt_online_20260418_001937`。
- [本地文件] 在线策略 best：TQQQ `qqq_sma150_band0.005`，QLD `qqq_sma180_band0.005`，数据最新 2026-04-17，下一开盘动作均为 `HOLD_OR_KEEP_LONG`，请求执行日为 2026-04-20。
- [本地文件] 动量组合脚本：`scripts\vbt_us_leverage_momentum_combo.py`。
- [本地文件] 动量组合最新输出：`outputs\us_leveraged_etf_momentum_combo\momentum_combo_20260418_084322`。
- [本地文件] 动量组合 best：TQQQ `qqq_ema3_40_band0.0050`，QLD `asset_sma3_200_band0.0050`，数据最新 2026-04-17，下一开盘动作均为 `HOLD_OR_KEEP_LONG`，请求执行日为 2026-04-20。

### 11. 美股 TD9 全资产搜索

- [本地文件] 脚本：`scripts\vbt_us_td9_all_assets.py`。
- [本地文件] 输出：`outputs\us_td9_all_assets\td9_all_assets_20260418_094054` 与 `outputs\us_td9_all_assets\td9_all_assets_20260418_095256`。
- [本地文件] 两个 run 均覆盖 43 个 symbol：MAG7 7 个，基金/ETF/指数 36 个。
- [本地文件] `td9_all_assets_20260418_094054` 报告 top5：USA、GOF、OXLC、PDI、PTY，主要为 `macd_ma200_td9_exit_s7` 或 TD9 re-entry 变体。该 run 的 CEF 类标的长期收益数值非常高，后续必须单独复核分红、复权、数据拼接和 survivorship。
- [本地文件] `td9_all_assets_20260418_095256` 报告 top5：NVDA、`_VIX`、GOOGL、META、MAIN。QLD best 为 `qqq_ema3_120_b0.0025`，TQQQ best 为 `qqq_ema3_40_b0.0050`。
- [本地文件] `td9_all_assets_20260418_095256` 中 QLD：test 年化 27.25%、test maxDD -29.72%、test Sharpe 0.921、full 年化 22.07%、full maxDD -41.93%、full Sharpe 0.799。
- [本地文件] `td9_all_assets_20260418_095256` 中 TQQQ：test 年化 34.09%、test maxDD -41.90%、test Sharpe 0.851、full 年化 28.22%、full maxDD -52.27%、full Sharpe 0.770。
- [本地文件] 关键 CSV：`top5_overall.csv`、`qld_tqqq_best.csv`、`instrument_best_summary.csv`、`candidate_summary.csv`、`candidate_summary_checkpoint.csv`、`best_summary_checkpoint.csv`。

## 可直接接手的执行习惯

- [本地文件] 588200Pool 默认训练期通常是 2022-10-26 至 2024-12-31，样本外从 2025-01-01 开始。
- [本地文件] 588200 相关旧输出常用本地数据截止 2026-04-08；实时 TD9/MA 输出更新到 2026-04-15；美股相关输出更新到 2026-04-17。
- [本地文件] 交易执行假设多处报告明确为：收盘后生成信号，下一交易日开盘执行。
- [本地文件] 用户要求长跑必须使用后台进程、日志、checkpoint CSV/JSON/Markdown，并可分阶段恢复。
- [本地文件] 用户要求策略报告必须解释策略名称、指标含义、买点、卖点、执行假设、样本内/样本外结果、限制和使用方法。规范在 `docs\report_generation_standard.md`。
- [本地文件] Qlib 复用说明已存在，但旧交接记录显示当前 Python 环境可能没有安装 `qlib`；如要运行 Qlib 工作流，先检查 `python -c "import qlib"`。
- [本地文件] 旧交接记录显示测试通常需要 `$env:PYTHONPATH='.'`。

## 后续优先级建议

1. [本地文件] 先读本文件、`docs\codex_handoff_quant_lab_full_audit_20260418_175017.md`、`docs\codex_user_switch_handoff_20260418.md`，再决定是否需要打开旧聊天。
2. [本地文件] 若继续 588200Pool，先读 `C:\Users\Administrator\.codex\skills\588200-pool\SKILL.md` 与 `docs\588200pool_context_handoff_20260415.md`。
3. [本地文件] 若继续美股/杠杆 ETF，优先从 `outputs\us_leveraged_etf_vectorbt_online_strategies\vbt_online_20260418_001937`、`outputs\us_leveraged_etf_momentum_combo\momentum_combo_20260418_084322`、`outputs\us_td9_all_assets\td9_all_assets_20260418_095256` 读取。
4. [本地文件] 若要复用外部因子，先读 `docs\external_factor_adapters.md` 和 `outputs\factor_library_imports\full_reuse_catalog_snapshot_20260416.md`。
5. [本地推断] 任何看起来过高的 CEF/基金长期收益必须优先检查价格是否含复权、分红、合并、重复拼接和幸存者偏差。
6. [本地推断] 任何“最新信号”都应在实际使用前重新跑一次数据更新，因为现在文件中最新日期分别停在 2026-04-08、2026-04-15 或 2026-04-17。

## 可能仍需补充聊天上下文的历史任务

这些不是本地文件完全无法支持，而是如果要理解用户为什么做某个选择、为何否定某个结果、或原始目标的语气和优先级，旧聊天可能更完整。

- [需聊天上下文] 用户对“当前 backtest 不满意”的原始判断标准。旧交接文件记录了这个方向，但没有完整记录所有口头标准。
- [需聊天上下文] 用户对美股 QLD/TQQQ 初版结果“太弱”的具体阈值、可接受回撤和收益偏好。
- [需聊天上下文] 外部在线策略搜索时，各网页或论文被选入的过程性判断。报告保留了来源 URL 和用途，但未保留完整搜索过程。
- [需聊天上下文] 某些长跑中途超时、重启、用户追问和 Codex 解释的完整过程。checkpoint 和日志能恢复结果，但不能完整恢复对话背景。
- [需聊天上下文] 用户是否有真实交易意图、资金规模、税费、账户限制、滑点偏好、是否允许做空或融资等执行约束。本地报告只是研究口径，不构成投资建议。
- [需聊天上下文] 若要重现所有历史 Codex 操作命令的先后顺序，现有本地文件只能部分恢复，无法保证等价于完整聊天流水。

## 快速清单命令

在 PowerShell 中可以用这些命令复查本文件的来源：

```powershell
Get-ChildItem -Path docs -File | Select-Object Name,Length,LastWriteTime
Get-ChildItem -Path outputs -Directory | ForEach-Object {
  $files = Get-ChildItem -LiteralPath $_.FullName -Recurse -File
  [PSCustomObject]@{
    Output = $_.Name
    Files = $files.Count
    Reports = ($files | Where-Object {$_.Name -match 'report.*\.md$|final_report.*\.md$'}).Count
    Checkpoints = ($files | Where-Object {$_.Name -match 'checkpoint|Checkpoint'}).Count
    BestConfigs = ($files | Where-Object {$_.Name -match 'best_config|recommended.*config'}).Count
    SummaryCsv = ($files | Where-Object {$_.Name -match 'summary.*\.csv$|.*summary.*\.csv$|top5.*\.csv$|qld_tqqq_best\.csv$'}).Count
  }
}
Get-ChildItem -Path scripts -File | Select-Object Name,Length,LastWriteTime
Test-Path data\external_repos
Get-ChildItem -Path external_repos\factor_libraries -Directory | Select-Object Name,LastWriteTime
```

