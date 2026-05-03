# US Stock Selection Autorun Roadmap

## 当前阶段

当前阶段是 v7：严格 walk-forward 可执行化。

v6 已完成：
- local Qlib bin provider 成功；
- Alpha158/Alpha360 Handler 成功；
- qrun 成功；
- workflow-by-code 成功；
- Top5 dropout monthly、Top5 equal monthly、Top10 dropout monthly 表现显著优于基准；
- 但严格 Handler retrain WF 在 Windows 上超时；
- 当前分类：promising_but_unstable。

## v7 目标：解决严格 walk-forward 超时

### 核心任务

1. 不再每个 WF 窗口重复完整 Handler 重算；
2. 预计算并缓存 Alpha158/Alpha360 特征；
3. 将 Qlib Handler 输出转成 parquet；
4. 每个 WF 窗口直接从 parquet 切片；
5. 用 LightGBM/Ridge/ElasticNet 重训；
6. 输出 rolling/anchored WF；
7. 优先验证 Top5 dropout / Top10 dropout。

### v7 必须新增

模块：
- quant_lab/us_stock_selection/feature_cache.py
- quant_lab/us_stock_selection/fast_walk_forward.py
- quant_lab/us_stock_selection/v7_reporting.py

脚本：
- scripts/us_stock_selection/25_build_feature_cache.py
- scripts/us_stock_selection/26_run_fast_walk_forward.py
- scripts/us_stock_selection/27_run_v7_fast_wf.py

输出：
- v7_feature_cache/
- v7_fast_walk_forward/
- v7_reports/

### v7 技术要求

1. Alpha158/Alpha360 只算一次；
2. 存 parquet；
3. parquet 包含：
   - date
   - instrument
   - features
   - labels
4. WF 窗口从 parquet 切片；
5. 不重复 qlib Handler 初始化；
6. 先用小 universe sanity check；
7. 再跑 Pool A 全量；
8. 每个窗口限制运行时间；
9. 超时要保存部分结果；
10. 支持 resume。

### v7 验收

通过条件：
- 至少完成 anchored expanding WF；
- 至少完成 rolling 2Y train + 6M test；
- 至少完成 Top5 dropout 和 Top10 dropout；
- 输出每个窗口 CAGR、MaxDD、Calmar；
- WF 平均 CAGR >= 15% 为可继续研究；
- WF 平均 CAGR >= 20% 且 Calmar >= 1 为强候选。

## v8 目标：若 v7 通过，做稳健组合优化

1. vol targeting；
2. max weight；
3. TopKDropout；
4. risk parity；
5. turnover penalty；
6. crash filter；
7. QQQ/SPY/TLT/SHY regime switch；
8. 成本 5/10/20/50 bps。

## v9 目标：若 v8 通过，扩科技成长池

只扩：
- 半导体；
- AI 软件；
- 云计算；
- 网络安全；
- 高流动性成长股。

暂不扩全 Nasdaq100。

## v10 目标：若 v9 通过，再扩 Nasdaq100

扩池前必须：
- v7/v8 稳定；
- 无泄露；
- WF 可接受；
- 成本可接受。

## 永久原则

1. Qlib 负责因子、模型、信号；
2. vectorbt 负责组合验收；
3. 不再以单票择时为主线；
4. 不再以 Top1 为主线；
5. 主线是 Top5/Top10 稳健组合；
6. 所有结论必须区分：
   - research candidate；
   - promising but unstable；
   - likely overfit；
   - invalid；
   - tradable candidate。
