# 588200Pool 上下文交接摘要

生成时间：2026-04-15

用途：压缩前面长会话的核心信息。后续继续 588200Pool 量化研究时，优先读取本文件和本地 skill `C:\Users\Administrator\.codex\skills\588200-pool\SKILL.md`，不要依赖聊天历史。

## 1. 项目与数据默认值

- 项目根目录：`E:\dzhwork\quant\quant_lab`
- 默认数据根目录：`E:\dzhwork\quant\quant_lab\data\external\legacy_quant`
- 目标 ETF：`588200.SS`
- 默认训练期：`2022-10-26` 到 `2024-12-31`
- 默认样本外：`2025-01-01` 到当前本地目标数据末尾；目前主要结果用到 `2026-04-08`
- 交易假设：收盘后生成信号，下一个交易日开盘执行；不要把信号日收盘价当成实际成交价
- 588200Pool 当前加载：46 只成分股，缺失代码 `688249, 688361, 688709, 688584`
- 相似 ETF 样本：18 只
- 最新 TD9 组合脚本日志里，VIX 最新日期为 `2026-04-02`

## 2. 已经落地的能力

- `src/factors/safety.py`
  - 已加入 TD9/神奇九转相关安全因子：
    - `alpha_td9_buy_setup_4_9`
    - `alpha_td9_sell_pressure_4_9`
  - 已加入安全因子族，例如低波动、下行波动、流动性、尾部风险等。

- `scripts/longrun_588200_factor_strategy_search.py`
  - 已支持单因子和多因子组合。
  - 组合逻辑：对成分股横截面 z-score，2 因子或 3 因子取平均，统计组合分数大于 0 的成分股占比作为“组合因子宽度”。
  - 已支持断点 CSV 和长跑日志。

- `src/strategies/safety.py`
  - 已加入 `MovingAverageCrossoverSpec` 和 `moving_average_crossover_signal`。
  - 已加入 `RegimeFilteredMASpec` 和 `regime_filtered_ma_signal`。
  - 横盘过滤指标包括 ADX、Kaufman Efficiency Ratio、Choppiness Index、MA gap / ATR、最小持仓、冷却期。

- 已新增脚本：
  - `scripts/research_588200_ma_crossover_strategy.py`
  - `scripts/research_588200_sideways_filtered_strategy.py`
  - `scripts/research_588200_td9_indicator_combo.py`

- 已新增本地 skill：
  - `C:\Users\Administrator\.codex\skills\588200-pool\SKILL.md`
  - 以后用户说“跑588200Pool量化策略”时，应按 skill 的规范执行：后台长跑、日志、断点、训练池/样本外池/588200 三重验证、详细解释买卖点。

- AutoResearch 项目处理：
  - 目标仓库：`https://github.com/karpathy/autoresearch`
  - shell 环境无法 `git clone`，报 GitHub 443 连接失败；raw 下载也无法解析 `raw.githubusercontent.com`。
  - 已建立来源说明：`E:\dzhwork\quant\quant_lab\external_repos\karpathy_autoresearch\SOURCE.md`
  - 已吸收其核心思想：固定评估框架、固定预算、日志化实验、保留改进、丢弃失败实验。

## 3. 已完成的主要回测结果

### 3.1 早期基准

旧基准策略：

`baseline_prev_best__mom60__bb65__bs50__vol20__vp95`

588200 样本外：

- 年化收益：37.13%
- Sharpe：1.085
- 最大回撤：-13.84%

同区间买入持有 588200：

- 年化收益：54.21%
- Sharpe：1.314
- 最大回撤：-20.40%

### 3.2 多因子 + TD9 稳健推荐

输出目录：

`E:\dzhwork\quant\quant_lab\outputs\588200_longrun_factor_strategy\combo_20260412_224013`

主报告：

`E:\dzhwork\quant\quant_lab\outputs\588200_longrun_factor_strategy\combo_20260412_224013\report_recommended_combo_20260412_235515.md`

推荐策略：

`factor_overlay__combo2__alpha_intraday_strength_60__alpha_td9_sell_pressure_4_9__mom60__vol20__vp95__fb55__fs45`

含义：

- 588200 自身 60 日动量为正。
- 成分股 MA60 宽度达到买入阈值。
- 588200 20 日波动率分位不处于极端高波动。
- 成分股组合因子宽度达到阈值，组合因子由：
  - `alpha_intraday_strength_60`：60 日内收盘价相对当日高低区间的位置，越高代表日内承接越强。
  - `alpha_td9_sell_pressure_4_9`：TD9 卖压的反向安全表达，越高代表九转卖压越轻。

588200 样本外：

- 年化收益：49.71%
- Sharpe：1.752
- 最大回撤：-11.59%
- 仓位占比：28.38%
- 最新信号日期：`2026-04-08`
- 最新动作：`EMPTY_OR_SELL_588200`

### 3.3 所有已完成策略族里的“样本外最强但过拟合风险高”候选

策略：

`factor_overlay__combo3__alpha_pv_corr_20__alpha_reversal_20__safe_liquidity_amihud_60__mom120__vol120__vp90__fb50__fs40__poolmom`

588200 样本外：

- 年化收益：83.50%
- Sharpe：2.928
- 最大回撤：-12.62%
- 仓位占比：30.03%

问题：

- 训练池中位 Sharpe 为负，588200 训练期也弱。
- 这是“样本外 588200 排名第一”的攻击型候选，不应直接当成稳健主推策略。

### 3.4 所有已完成策略族里的当前稳健冠军

这是目前更适合作为主推的稳健候选，因为它同时满足训练池、样本外池、588200 训练期、588200 样本外都为正。

策略：

`factor_overlay__combo2__alpha_pv_corr_20__safe_low_vol_60__mom120__vol120__vp90__fb50__fs40__poolmom`

含义：

- `mom120`：588200 自身 120 日动量为正才考虑买入。
- `vol120__vp90`：588200 120 日波动率分位不能高于 90%。
- `poolmom`：成分股池 20 日收益中位数必须为正。
- `fb50__fs40`：组合因子宽度大于等于 50% 买入；跌到 40% 或更低卖出。
- 组合因子：
  - `alpha_pv_corr_20`：20 日价量相关的反向表达，越高表示不利价量共振越轻。
  - `safe_low_vol_60`：60 日低波动安全因子，越高表示波动越低。

588200 样本外：

- 年化收益：61.83%
- Sharpe：2.529
- 最大回撤：-12.62%
- 仓位占比：27.72%

稳健性：

- 训练池中位 Sharpe：0.449
- 样本外池中位 Sharpe：2.546
- 588200 训练期 Sharpe：0.549

下一次若要给“最终最优策略”，应优先重新生成这条策略的完整信号、交易明细和详细中文说明报告。

### 3.5 均线交叉动量策略族

输出目录：

`E:\dzhwork\quant\quant_lab\outputs\588200_ma_crossover_strategy\ma_cross_20260413_152740`

最强样本外策略：

`ma_cross_pool_vol__ma5_60__bb55__bs45__vol120__vp90__poolmom`

含义：

- 5 日均线大于 60 日均线。
- 成分股 MA60 宽度买入阈值 55%，卖出阈值 45%。
- 588200 120 日波动率分位不高于 90%。
- 成分股池 20 日收益中位数为正。

588200 样本外：

- 年化收益：65.09%
- Sharpe：2.095
- 最大回撤：-12.62%
- 仓位占比：37.29%

问题：

- 训练池表现较弱，适合作为“动量策略里样本外最强”，不适合作为唯一稳健结论。

### 3.6 横盘过滤趋势策略族

输出目录：

`E:\dzhwork\quant\quant_lab\outputs\588200_sideways_filtered_strategy\sideways_20260413_164557`

最强样本外策略：

`sideways_filter__ma20_60__bb55__bs45__vol120__vp90__adx14_15_gap_20__poolmom`

含义：

- 20 日均线大于 60 日均线。
- 成分股 MA60 宽度买入 55%，卖出 45%。
- 588200 120 日波动率分位不高于 90%。
- ADX(14) 不低于 15，用于过滤弱趋势/横盘状态。
- MA gap / ATR 不低于 0.20，避免均线刚贴在一起时频繁假突破。
- 成分股池 20 日收益中位数为正。

588200 样本外：

- 年化收益：64.53%
- Sharpe：2.109
- 最大回撤：-12.62%
- 仓位占比：32.67%
- 样本外交易：4 笔
- 样本外 gross losing trades：0 笔

问题：

- 训练期收益和训练池表现为负，更像“2025-2026 588200 特别适配”的事后最优。
- 稳健候选为：
  - `sideways_filter__ma5_20__bb55__bs45__vol120__vp90__er20_20`

## 4. 当前未完成/正在运行的任务

### 4.1 TD9 indicator combo 长跑

目录：

`E:\dzhwork\quant\quant_lab\outputs\588200_td9_indicator_combo`

已看到两个运行目录：

- `td9_combo_20260415_212607`
  - `strategy_summary_checkpoint.csv` 已有 500 行。
  - 日志显示总候选数 `18144`，已 checkpoint 到 `500/18144`。
  - stderr 为空。

- `td9_combo_stage2_20260415_213550`
  - 当前后台进程仍在跑。
  - 进程 ID：`51664`
  - 命令：`scripts\research_588200_td9_indicator_combo.py --start 2022-10-26 --train-end 2024-12-31 --end 2026-04-08 --run-dir E:\dzhwork\quant\quant_lab\outputs\588200_td9_indicator_combo\td9_combo_stage2_20260415_213550 --checkpoint-every 250`
  - 最新已读 stdout：Stage 1 target-only scan 已完成 `18144/18144`。
  - 当前进入 Stage 2：`pool robustness scan for 1610 candidates`
  - 当前没有最终报告，不应把这个任务当作完成。

监控命令：

```powershell
Set-Location E:\dzhwork\quant\quant_lab

Get-CimInstance Win32_Process -Filter "name = 'python.exe'" |
  Where-Object { $_.CommandLine -like '*research_588200_td9_indicator_combo.py*' } |
  Select-Object ProcessId,CommandLine | Format-List

Get-Content "E:\dzhwork\quant\quant_lab\outputs\588200_td9_indicator_combo\td9_combo_stage2_20260415_213550\td9_combo.stdout.log" -Tail 80
Get-Content "E:\dzhwork\quant\quant_lab\outputs\588200_td9_indicator_combo\td9_combo_stage2_20260415_213550\td9_combo.stderr.log" -Tail 80
```

完成后需要做：

1. 读取最终 `strategy_summary*.csv`。
2. 与当前稳健冠军 `factor_overlay__combo2__alpha_pv_corr_20__safe_low_vol_60__mom120__vol120__vp90__fb50__fs40__poolmom` 比较。
3. 输出最终报告，必须包含指标释义、买点、卖点、训练期/样本外/全样本、买入持有对照、最新信号和实际交易切换点。

## 5. 重要教训和报告规范

- 不再只写策略 ID，必须解释每个指标含义。
- 买点和卖点必须分开写清楚。
- 所有交易明细必须区分：
  - 信号日
  - 执行日
  - 信号日收盘价
  - 下一个交易日开盘执行价
- 不能只看 588200 样本外第一名，因为 588200 历史短、单标的易过拟合。
- 最终推荐优先级：
  1. 稳健冠军：训练池、样本外池、588200 训练期、588200 样本外都为正。
  2. 588200 样本外冠军：可以展示，但要标注过拟合风险。
  3. 纯策略族冠军：如“均线交叉最强”“横盘过滤最强”，只能在对应策略族内解释。
- 每份 `report*.md` 都要遵守 `docs/report_generation_standard.md` 和 skill 中的 Report Checklist。

## 6. 推荐下一步

下一次继续时，不要重新翻旧聊天。直接按以下顺序：

1. 读本文件。
2. 读 `C:\Users\Administrator\.codex\skills\588200-pool\SKILL.md`。
3. 检查 TD9 stage2 后台进程和日志。
4. 如果 TD9 stage2 已完成，汇总其结果。
5. 如果 TD9 stage2 未完成，继续监控或按脚本支持情况 resume。
6. 以“当前稳健冠军”和“TD9 新结果冠军”做最终对照。
7. 生成一份新的详细中文报告。

建议用户下一条提示词：

```text
请读取 docs/588200pool_context_handoff_20260415.md 和 588200-pool skill，检查 TD9 长跑是否完成；如果完成，请汇总并和当前稳健冠军比较，生成最终 588200Pool 最优策略报告。
```
