# RUN_SUMMARY

本轮目标：执行 formal v9；仅小幅科技成长池，不扩 Nasdaq100/S&P500，不进入 v10，不交易化。

新 run 目录：`E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\formal_v9_20260504_214812`
zip 路径：`E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\us_stock_selection_formal_v9_20260504_214812.zip`

核心结论：
- classification: `formal_v9_failed_due_to_eligibility`
- Pool A reproduction pass: `True`
- Formal v9 gate pass: `False`
- Performance gate pass: `True`
- Effective universe count: `36`
- Effective small-growth count: `0`
- Effective new growth count: `0`
- Excluded ticker count: `65`
- Allow enter v10: `False`

Pool A reproduction CAGR/Calmar/MaxDD：`0.6421262430680639` / `1.6339698829869318` / `-0.39298536022845376`
Pool A + growth CAGR/Calmar/MaxDD：`0.6421262430680639` / `1.6339698829869318` / `-0.39298536022845376`
Small growth only CAGR/Calmar/MaxDD：`0.0` / `0.0` / `0.0`
Ex-high-vol CAGR/Calmar/MaxDD：`0.6566465156253447` / `1.9533577446623147` / `-0.3361629570516086`

原因：Pool A reproduction passed, but no new small-growth ticker beyond Pool A had both canonical provider data and formal frozen score provenance, so the formal main universe degenerates to Pool A.

本轮没有扩 Nasdaq100/S&P500，没有进入 v10，没有下载行情，没有连接券商，没有自动 commit/push。
