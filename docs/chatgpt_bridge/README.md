# ChatGPT-Codex Bridge

这是 Codex 与 ChatGPT 的审阅中转目录。

Codex 每轮 `us_stock_selection` 运行结束后，会把精简审阅包发布到这里，避免用户手工上传 zip 或复制长文本。

## 使用方式

ChatGPT 每次只需要读取：

`docs/chatgpt_bridge/LATEST.md`

`LATEST.md` 会指向最新 run 的 `REVIEW_PACKET.md`。`REVIEW_PACKET.md` 是首要审阅文件，里面包含：

- run 目录和 zip 路径；
- 本轮目标；
- 新增/修改文件；
- 核心结果和指标；
- gate / verdict；
- 已知限制；
- Codex 建议的下一步；
- 关键表格摘要；
- 重要 CSV 文件路径。

## small_tables

每个 bridge run 下的 `small_tables/` 保存关键 CSV 的精简版：

- `benchmark.csv`
- `attribution.csv`
- `stress_test.csv`
- `yearly_return.csv`
- `holdings_summary.csv`

如果原始 CSV 超过大小阈值，发布器只导出摘要、head/tail 或聚合结果。

## 大文件策略

大文件仍留在本地 `outputs/`，不进入 GitHub：

- zip；
- parquet；
- pkl / joblib / bin；
- h5 / feather；
- 原始行情和模型文件。

## 给 ChatGPT 的固定话术

请审阅 GitHub quant_lab 仓库 `docs/chatgpt_bridge/LATEST.md` 指向的最新 run，重点检查 `REVIEW_PACKET.md`、`final_verdict.json` 和 `small_tables/` 下的关键 CSV 摘要。
