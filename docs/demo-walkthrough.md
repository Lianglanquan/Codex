# 演示流程

## 演示场景

目标：演示“老板提需求 → ChatGPT 拆任务 → Codex 在 PR 中执行 → ChatGPT 通过 MCP 审核 → 返工/通过 → 给老板汇报”的完整链路。

本次最小真实场景选用文档改动：

- 老板需求：`“把 ChatGPT 接入说明写到极简，我不想看原理，只想知道最后怎么连。”`
- 目标文件：`docs/chatgpt-connect.md`
- 相关治理：`AGENTS.md`、`.github/pull_request_template.md`

## 1. 老板需求

```md
想要什么：给我一份一页内的 ChatGPT 接入说明
不喜欢什么：不要讲一堆 MCP 原理
底线是什么：连接成功后我能直接让 ChatGPT 看 PR 和 checks
```

## 2. ChatGPT 任务单示例

参考 [chatgpt-to-codex-task-template.md](/E:/Users/宁长久/Desktop/codex/templates/chatgpt-to-codex-task-template.md)。

```md
目标：
- 新增极简接入说明，面向非技术老板

范围：
- docs/chatgpt-connect.md
- 如有必要，补充 PR 模板中的验证提示

约束：
- 不讲协议细节
- 说明 developer mode 与 remote MCP server 连接
- 连接成功验证步骤必须清楚

验收标准：
- 全文一页内
- 读者可以独立完成连接与自检
- 失败时知道看哪里
```

## 3. Codex 执行结果

- Codex 修改 `docs/chatgpt-connect.md`
- 运行文档相关验证与基础仓库 checks
- 提交 PR，并在 PR 描述中写明“改了什么 / 为什么改 / 风险点 / 如何验证”

## 4. ChatGPT 通过 MCP 审核

建议的调用顺序：

1. `get_pr`
2. `list_changed_files`
3. `get_pr_diff`
4. `read_file(path="AGENTS.md")`
5. `read_file(path="docs/chatgpt-connect.md", ref="<pr-head>")`
6. `get_checks`
7. `review_pr`

## 5. 演示一次返工

首次审核发现：

- `docs/chatgpt-connect.md` 没有写“连接失败时看哪里”
- PR 描述缺少风险说明

ChatGPT 生成返工单：

```md
结论：暂不建议合并

需要返工：
1. 在 `docs/chatgpt-connect.md` 增加连接失败排查入口，至少覆盖服务地址、认证和日志位置。
2. 在 PR 描述补齐风险点，说明 developer mode 和写操作的安全边界。
3. 更新验证步骤，明确如何检查 `get_pr` / `get_checks` 工具已可见。
```

Codex 修复后重新推送，ChatGPT 再次调用 `get_pr_diff` 与 `get_checks` 审核。

## 6. ChatGPT 审核结果示例

参考 [chatgpt-review-template.md](/E:/Users/宁长久/Desktop/codex/templates/chatgpt-review-template.md)。

```md
本轮完成内容：
- 接入说明已压缩为老板可直接操作的最后一步
- 已补充连接成功验证和失败排查入口

未完成内容：
- 无

发现的问题：
- 无阻断项

风险等级：
- 低

是否建议合并：
- 建议合并
```

## 7. 最终老板汇报示例

```md
这轮已经把 ChatGPT 最后接入步骤做成一页说明，你只需要在 ChatGPT 里打开 developer mode、填入工程师给的 MCP 地址即可。

现在 ChatGPT 后续可以直接读取真实 PR、变更文件和 CI 结果来审核，不需要人工复制 diff。当前风险主要是 token 和权限配置，如果连接失败，工程师可以按运维手册排查。
```
