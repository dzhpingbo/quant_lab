# RUN_SUMMARY

本轮目标：执行 formal v9；仅小幅科技成长池，不扩 Nasdaq100/S&P500，不进入 v10，不交易化。

新 run 目录：`E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\formal_v9_20260505_224016`
zip 路径：`E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\us_stock_selection_formal_v9_20260505_224016.zip`

核心结论：
- classification: `formal_v9_failed_due_to_concentration`
- Pool A reproduction pass: `True`
- Formal v9 gate pass: `False`
- Performance gate pass: `False`
- Effective universe count: `64`
- Effective small-growth count: `45`
- Effective new growth count: `28`
- Excluded ticker count: `1`
- Allow enter v10: `False`

Pool A reproduction CAGR/Calmar/MaxDD：`0.23222486228552475` / `0.5584103684950428` / `-0.41586774778446167`
Pool A + growth CAGR/Calmar/MaxDD：`0.07977910174833758` / `0.1866013926654182` / `-0.4275375473289412`
Small growth only CAGR/Calmar/MaxDD：`0.06344030769851905` / `0.1439953649418388` / `-0.4405718734359487`
Ex-high-vol CAGR/Calmar/MaxDD：`-0.05862532569319279` / `-0.15263030265773103` / `-0.38410017324448575`

原因：Formal v9.1 score replay is too concentrated or depends too much on MSTR/COIN/PLTR.

本轮没有扩 Nasdaq100/S&P500，没有进入 v10，没有下载行情，没有连接券商，没有自动 commit/push。
