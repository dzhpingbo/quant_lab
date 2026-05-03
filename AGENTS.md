# AGENTS.md — quant_lab Codex 执行规则

## 1. 总目标

本项目目标是建立 A股+美股量化研究系统。当前重点任务是：

- 美股：通过 Qlib + vectorbt 双框架，寻找“策略能力范围内”的最优标的和组合；
- 不是找历史涨幅最大的股票，而是找在当前数据、因子、模型和回测能力下，能稳定获得高 Calmar、高 CAGR、低回撤的标的/组合；
- 主指标：Calmar；
- 约束指标：CAGR、MaxDD、walk-forward 稳定性、过拟合风险、集中度、交易成本敏感性；
- 最低目标：test CAGR >= 20%，Calmar >= 1；
- 更高目标：在样本外跑赢 QQQ/QLD/TQQQ/SPY/Pool A 等权中的主要基准。

## 2. 工作方式

你必须按“研究循环”持续推进：

1. 读取最新 run 目录和报告；
2. 识别当前最大瓶颈；
3. 提出本轮目标；
4. 修改或新增代码；
5. 运行实验；
6. 生成输出、报告、zip；
7. 做验收判断；
8. 写入 NEXT_STEPS.md；
9. 如果没有达到停止条件，继续下一轮。

除非遇到无法绕过的环境问题，不要只停在“建议下一步”。

## 3. 当前最高优先级

当前最新成果：
- v6 run: outputs/us_stock_selection/run_20260425_191001
- local Qlib bin provider 成功；
- Alpha158/Alpha360 Handler 成功；
- qrun 成功；
- workflow-by-code 成功；
- 最佳稳健组合包括 Top5 dropout monthly、Top5 equal monthly、Top10 dropout monthly；
- 但严格 Handler retrain walk-forward 在 Windows 上两次 1800s 超时；
- 最终分类仍是 promising_but_unstable。

下一阶段最高优先级：

1. 解决严格重训 walk-forward 超时；
2. 不再追 Top1；
3. 主线为 Top5 dropout / Top10 dropout；
4. 使用 caching、precomputed features、缩小 universe、并行、分块，降低 Handler 重算成本；
5. 尽量完成 rolling/anchored retrain walk-forward；
6. 若 Windows 无法完成，生成 WSL/Linux 执行脚本和完整命令；
7. 在未完成严格 WF 前，不扩 Nasdaq100/S&P500。

## 4. 允许自主探索

你可以自主决定技术方案，包括但不限于：

- Qlib workflow-by-code；
- qrun yaml；
- 预计算 Alpha158/Alpha360 feature parquet；
- sklearn fallback；
- LightGBM/XGBoost/CatBoost/Ridge/ElasticNet；
- TopK、TopKDropout、vol targeting、safe switch、crash filter；
- multiprocessing/joblib；
- DuckDB/Parquet 缓存；
- WSL/Linux 脚本；
- 降低 universe 先跑 Top5/Top10 候选；
- 分阶段小样本 sanity check 后再全量运行。

## 5. 禁止事项

禁止：

1. 假装 Qlib 真训练成功；
2. 隐藏失败、超时或错误；
3. 只跑样本内；
4. 用未来数据；
5. 用 label 作为 feature；
6. 只输出收益最高结果，不输出失败结果；
7. 只做 Top1；
8. 没有 walk-forward 就宣称可交易；
9. 通过调 ranking 权重美化结果；
10. 删除旧 run 结果；
11. 破坏已有脚本的一键运行能力。

## 6. 每轮必须输出

每轮必须生成：

- 新 run 目录；
- logs/run.log；
- reports/*.md；
- reports/*.xlsx；
- ranking 或 benchmark 结果；
- zip 包；
- NEXT_STEPS.md；
- RUN_SUMMARY.md。

## 7. 每轮返回格式

每轮结束后必须返回：

1. 本轮目标；
2. 新 run 目录；
3. zip 路径；
4. 修改/新增文件；
5. 核心指标；
6. 是否达到 test CAGR >= 20% 且 Calmar >= 1；
7. 是否通过严格 walk-forward；
8. 过拟合风险；
9. 当前分类；
10. 下一轮自动计划。

## 8. 停止条件

只有满足以下任一条件才停止：

A. 达到 credible_research_candidate：
- local/true Qlib provider 成功；
- Qlib Handler 或 qrun 真工作流成功；
- Top5/Top10 组合 test CAGR >= 20%；
- Calmar >= 1；
- 严格 walk-forward 通过率可接受；
- 成本压力测试后仍可接受；
- 不依赖单一年份或单一股票；
- 无数据泄露。

B. 遇到无法绕过的环境限制：
- 必须明确给出原因；
- 给出 Windows/WSL/Linux 可执行解决步骤；
- 生成可继续执行脚本。

C. 连续 3 轮没有改进：
- 必须生成失败复盘；
- 明确建议是否停止该方向或换研究路线。
