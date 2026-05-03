# RUN_SUMMARY

本轮目标：执行 v8.2 year stability，不进入 v9，不扩 Nasdaq100/S&P500，不交易化。

新 run 目录：`E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\run_20260502_220641`

最佳组合：`top5_ytdcap80p_derisk100p`
最终分类：`v9_ready_research_candidate`
是否允许进入 v9：`True`

最佳组合核心指标：
- CAGR: `0.6421259587785142`
- Calmar: `1.6339692500103946`
- MaxDD: `-0.39298533847832773`
- 50bps/T+1 CAGR: `0.5406125968868938`
- 50bps/T+1 Calmar: `1.3453472351463647`
- single-year share: `0.49683866511988606`
- top ticker share: `0.13793940593213985`
- remove top year CAGR: `0.5215869085057856`
- remove top year Calmar: `1.3272426664196029`
- remove top ticker CAGR: `0.4896536228676063`
- remove top ticker Calmar: `1.3265095931979178`

结论：本轮只做研究级 replay。即使 allow_enter_v9=True，也不自动进入 v9；必须用户另行批准。
