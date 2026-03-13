# Reviewer Rubric

## 阻断项

- 测试未执行或执行失败，且没有日志证据。
- lint 或 typecheck 失败，而项目已定义这些命令。
- diff 超出 plan 允许范围，或修改了禁区文件。
- 引入新生产依赖但未授权。
- 提交中包含密钥、token、密码或其他敏感信息。

## 评分项（0-5）

- Correctness：是否满足验收和边界条件。
- Tests：是否覆盖关键分支、异常路径与回归点。
- Security：是否引入注入、越权、敏感信息暴露或依赖风险。
- Maintainability：是否保持最小改动和清晰复杂度。
- Scope：是否遵守改动范围与禁区。
- Delivery：是否提供验证步骤、风险、回滚和已知问题。

## 输出要求

- 必须给出 `PASS` 或 `FAIL`。
- `FAIL` 必须提供可执行返工清单，每条都要带 `evidence` 和 `fix_guidance`。

