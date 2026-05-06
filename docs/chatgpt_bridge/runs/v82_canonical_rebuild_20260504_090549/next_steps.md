# NEXT_STEPS

当前状态：`formal_v82_valid_ready_for_formal_v9`。

下一步只允许：
- 审阅 `formal_v82_baseline/` 与 `formal_v9_precheck/`。
- 若批准 formal v9，必须单独开启下一轮，并显式允许执行 formal v9。
- formal v9 必须使用 canonical replay engine、同一 eligibility rule、同一 gate。

禁止：
- 不扩 Nasdaq100/S&P500/全市场。
- 不进入 v10。
- 不交易化，不连接券商，不下单。
- 不复用 v9 original metrics 或 unified replay 作为正式结果。
