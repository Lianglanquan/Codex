# ChatGPT 怎么接上这个仓库

这份就是给老板看的。

你不用懂代码，也不用懂 GitHub Actions。照着下面点就行。

## 先说结论

连上以后，你就可以直接跟 ChatGPT 说：

- 看看这个仓库现在什么状态
- 看看这个 PR 改了什么
- 这次能不能过
- 不行的话你替我写返工意见

你不需要自己复制 diff，也不需要自己看 CI。

## 第一步：打开 ChatGPT 的开发者模式

1. 打开 ChatGPT 网页版。
2. 点左下角头像。
3. 点 `Settings`。
4. 找到 `Apps`。
5. 再点 `Advanced settings`。
6. 找到 `Developer mode`。
7. 把开关打开。

如果你看到的菜单名字是 `Apps & Connectors`，也一样，路径还是：

`Settings -> Apps & Connectors -> Advanced settings -> Developer mode`

看到开关变成开启状态，就算这一步做完。

## 第二步：把仓库工具接进 ChatGPT

这一步你只需要填工程师给你的地址。

1. 还在 ChatGPT 里。
2. 进入 `Apps` 或 `Apps & Connectors` 页面。
3. 点 `Create app`、`Add connector` 或类似按钮。
4. 选择 `Remote MCP server`。
5. 在地址栏里填工程师给你的地址。

示例：

```text
https://你的域名/mcp
```

6. 如果页面要求填认证信息，就填工程师给你的 token 或登录方式。
7. 点保存。

保存后，回到 ChatGPT 新建一个对话。

## 第三步：确认有没有连成功

新开一个对话后，直接让 ChatGPT 做这件事：

```text
读取仓库状态，并告诉我现在有哪些打开的 PR
```

如果连接成功，你会看到它能调用一组仓库工具，常见名字包括：

- `get_repo_status`
- `list_open_prs`
- `get_pr`
- `get_checks`
- `review_pr`

然后它会真的返回仓库里的信息，不是空话。

这就表示接通了。

## 第四步：接通后你怎么用

以后你直接像平时说话一样提要求：

- “这个页面太土了，改成熟一点，但别动后端。”
- “你看看这个 PR 能不能合。”
- “不行就直接给返工意见。”
- “只告诉我结果和风险，不要给我技术细节。”

ChatGPT 会去读真实仓库、真实 PR、真实 checks。

## 第五步：如果没连上，看哪里

你先只检查这 3 件事：

1. 地址是不是填对了。
2. 工程师给你的 token 是不是过期了。
3. 工程师部署的服务是不是还活着。

你可以让工程师打开这个地址看看：

```text
https://你的域名/healthz
```

如果返回 `{"status":"ok"}`，说明服务大概率还活着。

如果这里都不通，就让工程师去看这份：

[docs/ops-runbook.md](E:/Users/宁长久/Desktop/codex/docs/ops-runbook.md)

## 你只要记住这 2 句话

- 你以后只提要求，不用自己搬运技术信息。
- ChatGPT 以后是直接看仓库现场，不是听别人转述。
