# ChatGPT 经理 + Codex 执行仓库规则

本仓库不是普通开发仓库。

目标是让老板只提业务目标，由 ChatGPT 负责拆解、审核和返工决策，由 Codex 在同一仓库、同一 PR、同一组 checks 上执行与修复。GitHub 是唯一真相源，所有审核必须基于真实 diff、真实文件、真实 CI 结果，不能依赖人工转述。

## 项目技术栈

- Python 3.10+
- FastAPI + Pydantic
- Next.js 16 + React 19 + TypeScript 5
- PySide6 / CustomTkinter 桌面原型
- GitHub Actions 作为默认 CI/checks 承载面

## 核心角色

- 老板：只表达业务目标、底线、不满和验收感觉。
- ChatGPT：经理、任务拆解者、审核者、返工决策者，只通过 MCP 读取仓库与 GitHub 现场。
- Codex：执行者，负责修改代码、补测试、运行验证、更新 PR。
- GitHub：唯一真相源，承载分支、PR、评论、checks、review。

## 必备命令

- `INSTALL_CMD`: `python -m pip install -e .[dev] && npm --prefix apps/web install`
- `TEST_CMD`: `python -m pytest`
- `LINT_CMD`: `python scripts/python_syntax_check.py orchestrator apps/api tests`
- `TYPECHECK_CMD`: `npm --prefix apps/web run typecheck`
- `BUILD_CMD`: `npm --prefix apps/web run build`

## 开发规范

- 默认最小改动，禁止无关大规模重构、批量重命名或全仓格式化。
- 改动前先阅读相关文件与已有测试，不允许凭想象重写模块。
- 新增功能必须补测试，或者在 PR 描述和交付包中明确写明无法补测试的原因、替代验证方式和残余风险。
- 不允许跳过 `lint`、`build`、`tests`。若某项在仓库内本来不存在，必须在 PR 描述与交付包中说明缺失及建议，不得伪造通过记录。
- 不允许引入与现有栈冲突的新框架；新增生产依赖必须在工单中被明确授权，并在 PR 中说明收益、替代方案和风险。
- 不允许删除、绕过或弱化鉴权、权限、审计、密钥边界、访问限制或安全校验逻辑。
- 任何面向老板、ChatGPT 或 Codex 的模板与工单都应优先复用仓库内现有文件，避免散落到聊天记录中。

## 代码风格

- Python：保持类型标注、清晰函数边界、显式错误处理，避免隐式全局状态。
- TypeScript/React：优先现有应用目录结构，不引入新的状态管理框架，不做无关抽象。
- 配置与自动化文件：命名要稳定、意图明确、可让 ChatGPT 直接引用。
- 注释只解释非显然约束、边界和协议，不写空洞注释。

## 测试要求

- 代码改动优先添加或更新最贴近变更面的回归测试。
- 文档或模板改动可不补单测，但必须在交付中说明验证方式。
- API / orchestration / MCP 改动至少要有对应 Python 测试。
- UI 改动至少要说明桌面端与移动端验证方式；如无自动化 UI 测试，需给出手动验证步骤。

## UI 改动要求

- UI 改动必须兼容桌面端和移动端。
- 必须保留或提升可读性、层级和关键操作可达性。
- 不允许为了“更高级”而牺牲现有业务路径、文案清晰度或表单可用性。
- PR 描述中必须写明 UI 影响面、断点验证方式和已知视觉风险。

## 安全边界

- 默认只读访问外部系统；写操作只开放完成当前任务所需的最小集合。
- 不允许把 secrets、token、密码、cookie、私钥、内部链接或生产数据写入仓库。
- 不允许执行任意 shell 作为 MCP 工具能力对外暴露。
- 不允许访问当前仓库之外的 GitHub 仓库，除非配置明确允许且工单授权。
- 任何 GitHub 自动化都必须限制在 PR 或 issue comment 上下文内运行，并限制触发者权限。

## 禁止事项

- 禁止修改 `.codex/` 与 `.agents/`，除非任务明确要求维护这两个目录。
- 禁止绕过 AGENTS 规则直接让老板理解代码、命令行、分支管理或 CI 细节。
- 禁止在没有日志证据的前提下声称“已验证”。
- 禁止脱离 GitHub diff/PR/checks 做主观式审核结论。
- 禁止未经说明地修改超过任务范围的文件；若确需扩容，必须在 `plan.json` 写明理由，并在 `deliver.json` 标记 `scope_expanded`。

## 标准工作方式

- 所有改动必须走分支和 PR。
- 所有任务尽量在 PR 评论中追加，让 ChatGPT 和 Codex 都能复用同一上下文。
- ChatGPT 审核必须对照：老板目标、`AGENTS.md`、PR 描述、变更文件、checks、测试结果。
- Codex 产出必须附带可验证交付包：变更摘要、验证命令与结果、风险、回滚、已知问题。

## Review 标准

ChatGPT 与 Codex review 默认检查以下项目：

- 需求完成度：是否完成老板目标与验收标准。
- 代码质量：是否最小改动、结构清晰、无明显错误路径。
- UI/UX 质量：桌面端与移动端是否兼容，交互与视觉是否符合任务要求。
- 风险与回归：是否引入权限、安全、兼容性或范围外影响。
- 测试与可上线性：`lint`、`build`、`tests`、`typecheck` 是否有真实结果与日志证据。
- 交付质量：PR 描述、模板、回滚方案、已知问题是否完整。

## PR 质量门槛

每个 PR 必须满足：

- 标题与描述可让 ChatGPT 单独理解任务背景。
- 明确写出“改了什么 / 为什么改 / 风险点 / 如何验证”。
- 引用老板目标或对应 issue。
- 附带真实 checks 结果，且不允许通过“暂时忽略失败”来交付。
- 若有 UI 改动，写明移动端与桌面端验证结论。
- 若无测试改动，写明理由与替代验证方案。

## 返工触发条件

出现以下任一情况，默认 `request changes`：

- 需求未完成或偏离老板目标。
- `lint`、`build`、`tests`、`typecheck` 任一失败或未提供日志证据。
- 新增功能没有测试，也没有合理的缺口说明。
- 修改了权限、鉴权或安全边界且未得到明确授权。
- UI 改动没有说明移动端/桌面端兼容情况。
- PR 描述缺少“改了什么、为什么改、风险点、如何验证”。
- diff 明显超出工单范围，且没有在 `plan.json` / `deliver.json` 标记扩容。

## Definition of Done

- `TEST_CMD` 通过并保留日志证据。
- `LINT_CMD`、`TYPECHECK_CMD`、`BUILD_CMD` 按仓库定义执行，并记录结果。
- Reviewer 明确给出 `PASS` 或可执行的 `FAIL` 返工清单。
- 交付包包含：验证步骤、风险、回滚、已知问题。

## 变更范围控制

- 默认修改文件数 `<= 8`，新增文件数 `<= 3`。
- 若超出，必须在 `plan.json` 写明理由，并在 `deliver.json` 标记 `scope_expanded`。
