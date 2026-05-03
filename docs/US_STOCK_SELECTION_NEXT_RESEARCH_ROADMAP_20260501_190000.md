# US Stock Selection Next Research Roadmap

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
