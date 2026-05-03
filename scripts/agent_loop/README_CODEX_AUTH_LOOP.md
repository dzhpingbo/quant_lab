# Codex Auth Loop

本方案不需要 OpenAI API Key，也不直接调用 OpenAI API。

它使用本机 Codex CLI 的 ChatGPT 登录态，通过 `codex exec` 分别调用两个本地角色：

- Reviewer：只审阅最新 run，生成下一轮任务书；
- Worker：只执行 Reviewer 生成的任务书。

当前默认 bridge 模式是 `github_issue`：GitHub Issue 是 ChatGPT / Reviewer / Worker / Codex 的任务与状态中心，本地 `docs/chatgpt_bridge/` 只作为缓存和归档。用户不需要手工复制 Codex 返回结果，也不需要手工复制 ChatGPT 生成的下一轮提示词。

## 首次登录

如果当前 Codex 仍是 API Key 模式，请先执行：

```powershell
codex logout
```

然后执行：

```powershell
codex
```

按提示用 ChatGPT 账号登录。登录成功后，`codex exec` 应该可以复用本地登录态，不需要 `OPENAI_API_KEY`。

如果本机 Codex CLI 参数不同，脚本会先检查：

```powershell
codex --help
codex exec --help
```

并按本机 help 自动适配 `--full-auto`、`--sandbox`、`--cd`、`--skip-git-repo-check`、`-o/--output-last-message` 等参数。

## GitHub 自动交互模式

默认配置：

```yaml
bridge:
  mode: github_issue
  local_cache_dir: docs/chatgpt_bridge
  github:
    enabled: true
    repo: auto_detect
    issue_number: null
    issue_title: Codex Agent Loop Control
    create_issue_if_missing: true
    use_gh_cli: true
    allow_commit_state_files: false
    allow_push: false
    state_dir: docs/chatgpt_bridge/github_state
```

初始化前请确认：

```powershell
gh --version
gh auth status
git remote -v
```

如果 `gh auth status` 未登录，执行：

```powershell
gh auth login
```

如果无法自动识别 repo，请确认当前目录是 git 仓库，并且 `origin` 指向 GitHub：

```powershell
git remote add origin https://github.com/<owner>/<repo>.git
```

loop 会查找或创建标题为 `Codex Agent Loop Control` 的控制 Issue。任务可以写在 Issue body 或评论中的 `## CURRENT_TASK` 区块；Reviewer 会把 `REVIEWER_DECISION` 和 `NEXT_CODEX_TASK` 写回 Issue；Worker 会从 Issue 读取 `NEXT_CODEX_TASK`，执行后把 `WORKER_STATUS`、`RUN_OUTPUTS`、`SAFETY_GATE_RESULT`、`ROUND_ARCHIVE` 写回 Issue。

本地结构化备份会写入：

```text
docs/chatgpt_bridge/github_state/
  CURRENT_TASK.md
  REVIEWER_DECISION.json
  NEXT_CODEX_TASK.md
  CODEX_RUN_STATUS.json
  ROUND_SUMMARY.md
```

默认不会 commit，也不会 push。只有显式设置 `allow_commit_state_files: true` 才会提交状态文件；只有显式设置 `allow_push: true` 才可能 push。

## 启动命令

Dry-run，不调用 Reviewer/Worker：

```powershell
python scripts/agent_loop/run_codex_auth_loop.py --config scripts/agent_loop/loop_config_auth.yaml --dry-run
```

只跑一轮：

```powershell
python scripts/agent_loop/run_codex_auth_loop.py --config scripts/agent_loop/loop_config_auth.yaml --max-rounds 1
```

完全无人值守循环：

```powershell
python scripts/agent_loop/run_codex_auth_loop.py --config scripts/agent_loop/loop_config_auth.yaml --max-rounds 10
```

Windows 批处理：

```powershell
scripts\agent_loop\run_codex_auth_loop.bat
```

## 查看 Reviewer 输出

- `docs/chatgpt_bridge/reviewer_outbox/REVIEWER_DECISION.json`
- `docs/chatgpt_bridge/reviewer_outbox/REVIEWER_NOTES.md`
- `docs/chatgpt_bridge/reviewer_outbox/NEXT_CODEX_TASK.md`
- `docs/chatgpt_bridge/reviewer_outbox/REVIEWER_LAST_MESSAGE.md`

## 查看 Worker 输出

- `docs/chatgpt_bridge/codex_inbox/TASK.md`
- `docs/chatgpt_bridge/codex_outbox/CODEX_LAST_MESSAGE.md`
- `docs/chatgpt_bridge/codex_outbox/CODEX_RUN_STATUS.json`

## 手动停止

在终端按 `Ctrl+C`。下一次可重新运行脚本；bridge 会保留上一轮 outbox/inbox，并把每轮快照归档到：

`docs/chatgpt_bridge/rounds/round_XXX/`

## 自动停止条件

自动循环必须停止于：

1. Reviewer decision = `NEED_HUMAN`；
2. Reviewer decision = `STOP`；
3. Worker 连续失败达到限制；
4. Reviewer 输出无效 JSON；
5. 发现数据泄露风险；
6. 发现交易化或券商 API；
7. 准备扩 Nasdaq100/S&P500；
8. 准备进入真实交易；
9. 超过 `max_rounds`。

命中 `NEED_HUMAN` 时，loop 必须写 GitHub Issue 评论说明命中规则和待人工处理事项，Worker 不会执行。

## 风险声明

- Reviewer 和 Worker 都是 Codex，研究判断不等同于 ChatGPT 人工审阅；
- 重大 gate、扩池、进入 v10 或任何交易化相关动作仍建议人工审查；
- 本方案不允许交易化，不允许券商 API，不允许真实交易；
- 本方案不会读取、打印或保存 GitHub token，也不会要求用户把 token 写入配置文件；
- GitHub Issue 评论是允许的 bridge 通道，但默认禁止自动 push。
