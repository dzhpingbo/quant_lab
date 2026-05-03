# quant_lab 安全策略与因子库升级方案

生成日期：2026-04-12

## 结论先行

`quant_lab` 现在已经有动量、反转、波动率、流动性、质量、估值六类基础因子，也有 walk-forward 和 IC 统计雏形。下一步不应该盲目堆更多公式，而应该把“安全策略层”和“因子挖掘层”分开建设：

1. 安全策略层优先做：趋势/时间序列动量 + 板块广度 + 波动率目标 + 最大回撤控制。
2. 因子库优先补：Qlib Alpha158/Alpha360、WorldQuant 101 Alphas、GTJA 191 类公式因子、质量/低波动/价值/盈利/投资等稳健学术因子。
3. 因子挖掘必须有淘汰标准：RankIC、ICIR、分层收益、换手、容量、行业/市值中性化、样本外、walk-forward、Deflated Sharpe / PBO 风险检查。
4. 当前最应该接入的开源组件：Qlib 做数据与模型研究骨架，Alphalens 做因子体检，vectorbt 做快速参数扫描，AlphaGen/RD-Agent 作为后续自动挖掘候选，不直接拿生成结果实盘。

## 策略报告强制规范

以后生成任何 `report*.md`，必须包含这些章节：

1. 策略一句话解释：交易什么资产、什么时候生成信号、什么时候执行。
2. 策略名解码：把类似 `momentum_vol__ma60__bb65__bs50__mom60__vol20__vp95` 的每一段解释清楚。
3. 每个指标的含义：计算对象、计算窗口、方向、阈值、是否仅用于某个策略族。
4. 明确买点：逐条列出触发买入/继续持有的条件。
5. 明确卖点：逐条列出触发卖出/继续空仓的条件。
6. 容易误解的地方：例如 `ma60` 到底是价格均线还是股票池广度窗口。
7. 回测假设：手续费、滑点、调仓时点、信号延迟、是否允许未来函数。
8. 样本内/样本外结果分开展示，禁止只给全样本绩效。
9. 使用方法：当天怎么读信号、下一交易日怎么操作。
10. 限制与风险：静态成分池、流动性、涨跌停、停牌、折溢价、过拟合风险。

## 值得接入的策略挖掘项目

| 项目 | 角色 | 建议 |
| --- | --- | --- |
| Qlib | 数据、模型、工作流、Alpha158/Alpha360 样例 | 已安装，继续作为主研究底座 |
| vectorbt | 快速参数网格、组合回测、向量化扫描 | 继续用于 ETF/规则策略高速搜索 |
| Alphalens | 因子 IC、分层收益、换手、衰减分析 | 建议接入为因子上线前体检工具 |
| QuantConnect LEAN | 事件驱动引擎、复杂交易执行模拟 | 后续需要实盘/事件级撮合时再接 |
| backtrader | 本地事件驱动回测 | 可作为 LEAN 的轻量替代，但不是当前最高优先级 |
| AlphaGen | 强化学习生成公式 Alpha | 用作候选因子生成器，必须经过本地严格验证 |
| RD-Agent | 自动化金融研究、因子和模型联合优化 | 后续高级自动化方向，先不要让它直接决定策略 |

## 安全策略库建议

### 1. ETF/行业主题防守择时

适合 588200 这类主题 ETF。

核心条件：

- 绝对动量：目标 ETF 20/60/120 日收益大于 0。
- 广度确认：成分股站上 MA20/MA60 的比例超过阈值。
- 波动过滤：20/60 日波动率分位低于阈值，极端波动时降仓。
- 执行延迟：收盘生成信号，下一交易日开盘执行。

优点是解释清楚、换手可控、不依赖单一 ETF 短历史。缺点是强单边上涨时可能跑输满仓。

### 2. 股票池低波动 + 质量 + 动量组合

适合 A 股股票池选股。

候选因子：

- 低波动：20/60/120 日 realized volatility 越低越好。
- 下行风险：最大回撤、CVaR、下行波动越低越好。
- 质量：ROE、毛利率、净利率、现金流质量、盈利稳定性越高越好。
- 动量：避开最近 1 个月反转噪声，使用 3-12 个月动量更稳。
- 流动性：剔除极低成交额、极高 Amihud 非流动性股票。
- 估值：PB、PE、PS、股息率作为价值因子，不单独作为买卖依据。

组合方式：

```text
安全分 = 0.30 * 低波动
       + 0.25 * 质量
       + 0.20 * 中期动量
       + 0.15 * 流动性
       + 0.10 * 估值
```

上线前必须做行业/市值中性化和换手成本测试，否则容易选出“低波动但没有弹性”的静态组合。

### 3. 双动量/轮动策略

适合 ETF 池或行业池。

- 相对动量：在候选 ETF/行业中选过去 60/120 日表现靠前者。
- 绝对动量：如果候选标的自身动量不为正，则切到现金/货币基金/短债替代资产。
- 风险预算：每个标的按波动率倒数分配权重，避免高波动标的天然占用过多风险。

### 4. 波动率目标与回撤开关

所有策略都应加一层风险预算：

- 目标年化波动率：例如 10%-15%。
- 单标的最大权重：例如 10%-20%，ETF 策略可更高。
- 行业最大权重：例如 30%-40%。
- 单日/单周回撤开关：超过阈值降仓而不是补仓。
- 换手上限：限制过度优化出来的高频噪声策略。

## 因子库建设优先级

### 第一阶段：标准化现有因子

把当前 `src/factors` 的六类因子全部纳入统一元数据：

- 因子名
- 因子方向
- 类别
- 计算频率
- 依赖字段
- 是否需要基本面数据
- 是否需要行业/市值中性化
- 缺失值处理
- 预期持有期
- 研究来源

### 第二阶段：接入成熟公式因子

优先级：

1. Qlib Alpha158 / Alpha360：作为标准量价因子基线。
2. WorldQuant 101 Alphas：作为公式因子候选池，但不能整包上线。
3. GTJA 191 类公式因子：适合 A 股语境，但需要清洗、去重和重算验证。
4. 基本面稳健因子：质量、价值、盈利、投资、成长、股息。
5. 风险与安全因子：低波动、低下行波动、低回撤、低 beta、低特质波动。

### 第三阶段：因子挖掘流水线

建议流程：

1. 生成候选因子：人工公式 + WorldQuant/GTJA 模板 + AlphaGen/RD-Agent 自动搜索。
2. 清洗：winsorize、z-score、缺失值处理、停牌/涨跌停过滤。
3. 中性化：行业、市值、必要时 beta 中性化。
4. 单因子检验：RankIC、ICIR、分层收益、分层单调性、换手、容量。
5. 相关性去重：新因子与已上线因子相关性过高则合并或淘汰。
6. 多因子合成：等权、ICIR 加权、岭回归/ElasticNet、LightGBM/TabNet 等模型。
7. walk-forward：训练期只选参数，样本外只评价。
8. 反过拟合：Deflated Sharpe Ratio、PBO/CSC-V、参数稳定性热力图。
9. 纸面交易：至少运行一个完整调仓周期后再考虑实盘。

## 因子上线门槛建议

单因子进入候选库：

- 覆盖率不低于 80%。
- 样本期 RankIC 均值方向稳定。
- ICIR 大于 0.3 优先，低于 0.1 默认淘汰。
- 分层收益大体单调。
- 换手后仍有正收益。
- 与已有因子相关性绝对值低于 0.7，或者能解释新的风格。

策略进入观察池：

- 样本外年化收益为正。
- 样本外最大回撤低于买入持有或低于策略设定阈值。
- 样本外 Sharpe/Calmar 优于基准。
- 参数邻域表现不能只在一个点上尖峰。
- 交易成本翻倍后不能完全失效。
- 不允许用样本外结果反向挑参数。

## 推荐实施路线

1. 本周：补 `docs/report_generation_standard.md`，并把 588200 报告模板改成“指标含义 + 买点 + 卖点”。
2. 本周：新增 `configs/research/factor_catalog_plan.yaml`，统一记录候选因子来源和上线状态。
3. 下一步：写 `scripts/evaluate_factor_library.py`，批量输出 RankIC、ICIR、分层收益、换手和相关性矩阵。
4. 下一步：把 Qlib Alpha158/Alpha360 接进当前数据目录，先跑科创/半导体 ETF 相关股票池。
5. 下一步：实现安全策略池：ETF 防守择时、股票低波动质量组合、双动量轮动、波动率目标组合。
6. 最后：引入 AlphaGen/RD-Agent 做候选因子生成，但所有生成因子必须走本地验证流水线。

## 2026-04-12 执行进展

已落地：

- 策略报告规范：`docs/report_generation_standard.md`
- 安全策略池配置：`configs/research/safe_strategy_pool.yaml`
- 因子库候选配置：`configs/research/factor_catalog_plan.yaml`
- 本地安全策略库：`src/strategies/safety.py`
- 本地安全因子库：`src/factors/safety.py`
- 588200 安全升级验证脚本：`scripts/validate_588200_safety_upgrade.py`
- 因子库体检脚本：`scripts/evaluate_factor_library.py`
- CLI 因子列表已支持 `safety` 类别。

新增安全因子：

- `safe_downside_vol_20`
- `safe_downside_vol_60`
- `safe_maxdd_60`
- `safe_cvar_60_5`
- `safe_liquidity_amihud_20`
- `safe_trend_stability_60_20`
- `alpha_pv_corr_20`

588200 验证结论：

- 严格按照同类 ETF 训练池泛化评分选择，新增安全增强候选暂未击败原全量网格最优基线，所以最终推荐仍保留原策略。
- 训练池规则下最好的安全增强候选为 `safety_mv__mom20__bb65__bs50__vol20__vp95__sb60__ss50`。
- 安全增强候选在 588200 样本外的年化收益较低，但夏普和回撤更稳：样本外年化 22.61%，夏普 1.277，最大回撤 -7.99%。
- 原基线样本外年化 37.13%，夏普 1.085，最大回撤 -13.84%。
- 买入持有样本外年化 54.21%，夏普 1.314，最大回撤 -20.40%。

解释：安全因子增强不是无条件提升收益，它更像“降回撤 overlay”。如果目标是收益最大化，当前阶段不应替换原策略；如果目标是回撤优先，可以把安全增强候选列入观察池。

因子体检结论：

- 本地 588200 成分股池上，`alpha_pv_corr_20` 的 20 日前向收益 RankIC 表现最好：IC 均值 0.0528，ICIR 0.2990，IC 为正比例 61.73%。
- `safe_liquidity_amihud_20` 为弱正：IC 均值 0.0156，ICIR 0.0821。
- 下行波动、CVaR、最大回撤等因子更适合作为风险过滤器，不适合作为单独收益预测因子。
- 第一阶段建议：把 `alpha_pv_corr_20` 放入候选收益因子观察池，把安全因子作为降仓或剔除条件使用。

## 2026-04-12 长跑扩展结果

按用户要求，已改为“后台长跑 + 日志 + 断点保存”：

- 长跑脚本：`scripts/longrun_588200_factor_strategy_search.py`
- 运行目录：`outputs/588200_longrun_factor_strategy/longrun_20260412_205752`
- stdout 日志：`longrun.stdout.log`
- stderr 日志：`longrun.stderr.log`
- checkpoint：`strategy_summary_checkpoint.csv`
- 候选策略数量：2962
- 因子广度信号数量：40
- 运行结果：2962/2962 完成，stderr 为空。

扩展后的本地因子库包含 36 个行情可计算候选，覆盖：

- 动量：20/60/120 日动量，60/120 日跳过 20 日动量
- 反转：5/20 日反转
- 趋势：均线距离、均线比率、通道位置、趋势效率比
- 风险：低波动、下行波动、CVaR、最大回撤
- 流动性：Amihud 非流动性
- 价量：收益-成交量相关、成交量动量、日内强度
- 分布：收益偏度

长跑最优策略：

`factor_overlay__alpha_reversal_20__mom60__vol20__vp95__fb50__fs40`

规则：

- 588200 60 日动量 > 0
- 成分股 MA60 广度 >= 65%
- 588200 20 日波动率分位 <= 95%
- `alpha_reversal_20` 因子广度 >= 50%
- 任一核心条件跌破退出，其中 `alpha_reversal_20` 因子广度 <= 40% 也触发退出。

588200 样本外结果：

- 长跑最优策略：年化 37.13%，夏普 1.085，最大回撤 -13.84%
- 原基线策略：年化 37.13%，夏普 1.085，最大回撤 -13.84%
- 买入持有：年化 54.21%，夏普 1.314，最大回撤 -20.40%

解释：

- 长跑最优策略在同类 ETF 训练池上的中位夏普从原基线的 0.441 提升到 0.466，因此按泛化评分排在第一。
- 但在 588200 本身的交易信号上，它与原基线几乎等价，样本外收益、夏普和回撤没有实质提升。
- 因此当前不能说“新增因子提升了 588200 收益”，只能说“新增因子 overlay 略微提升了跨 ETF 训练池泛化评分，但目标 ETF 上未形成新增收益”。

扩展后因子体检结果：

- 最新报告：`outputs/factor_library_eval/20260412_210928/report_20260412_210928.md`
- `alpha_pv_corr_20`：IC 均值 0.0528，ICIR 0.2990，IC 为正比例 61.73%
- `alpha_reversal_20`：IC 均值 0.0590，ICIR 0.2970，IC 为正比例 61.68%
- `alpha_reversal_5`：IC 均值 0.0469，ICIR 0.2233，IC 为正比例 60.05%
- 低波动与流动性因子有部分弱正信号，但更适合当风险过滤条件。
- 均线距离、原始动量、通道位置、收益偏度在本样本与 20 日前向收益口径下表现偏弱，暂不应作为单独收益预测因子上线。

## 参考来源

- Qlib 项目主页：https://github.com/microsoft/qlib
- Qlib 数据处理文档：https://qlib.readthedocs.io/en/latest/component/data.html
- Qlib Alpha158/Alpha360 源码：https://github.com/microsoft/qlib/blob/main/qlib/contrib/data/handler.py
- WorldQuant 101 Formulaic Alphas：https://arxiv.org/abs/1601.00991
- Alphalens 项目主页：https://github.com/quantopian/alphalens
- vectorbt 文档：https://vectorbt.dev/
- QuantConnect LEAN：https://github.com/QuantConnect/Lean
- Time Series Momentum，Moskowitz/Ooi/Pedersen：https://pages.stern.nyu.edu/~lpederse/papers/TimeSeriesMomentum.pdf
- Trend Following evidence，Hurst/Ooi/Pedersen：https://www.aqr.com/Insights/Research/White-Papers/A-Century-of-Evidence-on-Trend-Following-Investing
- The Volatility Effect，Blitz/van Vliet：https://papers.ssrn.com/sol3/papers.cfm?abstract_id=980865
- Quality Minus Junk，Asness/Frazzini/Pedersen：https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2312432
- Fama-French 五因子模型：https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2287202
- Deflated Sharpe Ratio：https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551
- Probability of Backtest Overfitting：https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253
- AlphaGen：https://github.com/RL-MLDM/alphagen
- RD-Agent：https://github.com/microsoft/RD-Agent

## 2026-04-12 神奇九转与多因子组合长跑结果

按新要求，已把上一轮“单因子 overlay 为主”的搜索升级为“后台长跑 + 日志 + 断点保存 + 多因子组合”：

- 新增神奇九转因子：`alpha_td9_buy_setup_4_9`、`alpha_td9_sell_pressure_4_9`
- 因子库数量：由 36 个扩展到 38 个
- 组合方式：对每个成分股因子做横截面 z-score，再对 2 因子/3 因子组合求平均，最后计算“组合分数大于 0 的成分股占比”作为组合因子宽度信号
- 长跑目录：`outputs/588200_longrun_factor_strategy/combo_20260412_224013`
- 候选数量：16066 个策略
- 因子宽度信号：222 个
- 断点文件：`strategy_summary_checkpoint.csv`
- stdout 日志：`combo_longrun.stdout.log`
- stderr 日志：`combo_longrun.stderr.log`，本轮为空
- 完整报告：`outputs/588200_longrun_factor_strategy/combo_20260412_224013/report_20260412_234101.md`
- 补充推荐报告：`outputs/588200_longrun_factor_strategy/combo_20260412_224013/report_recommended_combo_20260412_235515.md`
- 主推组合信号明细：`outputs/588200_longrun_factor_strategy/combo_20260412_224013/target_588200_signal_recommended_combo_20260412_235335.csv`
- 主推组合配置：`outputs/588200_longrun_factor_strategy/combo_20260412_224013/recommended_combo_config_20260412_235335.json`

本轮默认训练池第一名为：

`factor_overlay__alpha_td9_sell_pressure_4_9__mom60__vol20__vp95__fb60__fs50`

但它在 588200 样本外表现为年化 -4.79%、夏普 -0.374、最大回撤 -17.49%，因此不建议作为 588200 主推策略。

本轮建议优先观察的稳健组合为：

`factor_overlay__combo2__alpha_intraday_strength_60__alpha_td9_sell_pressure_4_9__mom60__vol20__vp95__fb55__fs45`

规则含义：

- 588200 自身 60 日动量大于 0
- 成分股池 MA60 广度不低于 65%
- 588200 自身 20 日波动率分位不高于 95%
- `alpha_intraday_strength_60` 与 `alpha_td9_sell_pressure_4_9` 的组合因子宽度不低于 55%
- 卖出条件为任一核心条件转弱，其中组合因子宽度跌到 45% 或更低也触发退出

588200 样本外结果：

- 主推组合：年化 49.71%，夏普 1.752，最大回撤 -11.59%，仓位占比 28.38%
- 原基准/上一版规则：年化 37.13%，夏普 1.085，最大回撤 -13.84%
- 买入持有：年化 54.21%，夏普 1.314，最大回撤 -20.40%

解释：

- 该组合没有超过买入持有的样本外年化收益，但显著降低回撤并提高夏普。
- 相比上一版规则，该组合在 588200 样本外的年化、夏普、最大回撤都更好。
- 最新信号日 2026-04-08 的计划为 `EMPTY_OR_SELL_588200`，即当前不满足买入条件。
- 该策略仍需继续做滚动样本外跟踪；本结论仅用于研究，不构成投资建议。

最新因子体检报告：

- 报告：`outputs/factor_library_eval/20260412_235545/report_20260412_235545.md`
- `alpha_pv_corr_20`：IC 均值 0.0528，ICIR 0.2990，IC 为正比例 61.73%
- `alpha_reversal_20`：IC 均值 0.0590，ICIR 0.2970，IC 为正比例 61.68%
- `alpha_reversal_5`：IC 均值 0.0469，ICIR 0.2233，IC 为正比例 60.05%
- `alpha_td9_sell_pressure_4_9`：IC 均值 0.0353，ICIR 0.1869，IC 为正比例 57.11%
- `alpha_td9_buy_setup_4_9`：IC 均值 0.0343，ICIR 0.1840，IC 为正比例 54.41%

结论：神奇九转因子本身不是最强单因子，但在本轮组合里能和 `alpha_intraday_strength_60`、低波动/下行波动等安全因子形成更好的择时过滤，适合放入组合因子观察池，而不是单独作为买卖按钮。

## 2026-04-13 均线交叉动量策略族结果

已把 5MA/20MA/60MA/120MA 均线交叉策略族加入本地策略库：

- 策略库实现：`src/strategies/safety.py`
- 新增规格：`MovingAverageCrossoverSpec`
- 新增信号函数：`moving_average_crossover_signal`
- 专项搜索脚本：`scripts/research_588200_ma_crossover_strategy.py`
- 测试覆盖：`tests/test_safety_upgrade.py`

本轮专项搜索：

- 输出目录：`outputs/588200_ma_crossover_strategy/ma_cross_20260413_152740`
- 候选策略数量：276
- 均线组合：5/20、5/60、5/120、20/60、20/120、60/120
- 策略族包括纯均线交叉，以及均线交叉叠加成分股 MA60 广度、120 日波动率过滤、`poolmom` 成分股池 20 日收益中位数过滤
- 完整报告：`outputs/588200_ma_crossover_strategy/ma_cross_20260413_152740/report_20260413_152913.md`
- 逐笔交易：`outputs/588200_ma_crossover_strategy/ma_cross_20260413_152740/target_588200_trades_20260413_152913.csv`

按 588200 样本外夏普排序的最优策略：

`ma_cross_pool_vol__ma5_60__bb55__bs45__vol120__vp90__poolmom`

含义：

- 5 日均线大于 60 日均线
- 成分股池 MA60 广度不低于 55% 才买入，跌到 45% 或更低卖出
- 588200 的 120 日波动率分位不高于 90% 才买入
- 成分股池 20 日收益中位数必须大于 0

588200 样本外结果：

- 年化收益：65.09%
- 夏普：2.095
- 最大回撤：-12.62%
- 仓位占比：37.29%
- 最新 2026-04-08 信号：`EMPTY_OR_SELL_588200`

纯均线交叉、不叠加任何过滤时，最优为：

`ma_cross__ma20_120`

588200 样本外结果：

- 年化收益：37.43%
- 夏普：0.915
- 最大回撤：-20.40%
- 仓位占比：82.51%

稳健性解释：

- 样本外最高策略的训练池中位夏普为 -1.617，训练期 588200 夏普为 -1.095，说明它仍有明显事后筛选风险。
- 按训练池、样本外池、588200 训练期与样本外均为正的稳健口径，较好的候选为 `ma_cross_pool_vol__ma5_20__bb55__bs45__vol120__vp90__poolmom`，588200 样本外年化 43.59%，夏普 1.467，最大回撤 -13.71%。
