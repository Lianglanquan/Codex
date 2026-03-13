# MCP 服务怎么用

这是给工程师看的简版说明。

如果你只想最快跑起来，看下面这段就够了。

## 最快启动

### Windows PowerShell

1. 先进入仓库目录
2. 安装依赖

```powershell
python -m pip install -e .[dev]
```

3. 设置 GitHub 相关变量

```powershell
$env:GITHUB_TOKEN="你的 GitHub Token"
$env:GITHUB_REPOSITORY="owner/repo"
$env:MCP_ALLOWED_REPOS="owner/repo"
```

4. 启动

```powershell
.\scripts\start_mcp_server.ps1
```

5. 打开浏览器访问：

```text
http://127.0.0.1:8080/healthz
```

如果看到：

```json
{"status":"ok"}
```

说明服务已经活了。

## Docker 启动

### 1. 构建镜像

```bash
docker build -f mcp-server/Dockerfile -t repo-governance-mcp .
```

### 2. 启动容器

```bash
docker run -p 8080:8080 \
  -e GITHUB_TOKEN=你的Token \
  -e GITHUB_REPOSITORY=owner/repo \
  -e MCP_ALLOWED_REPOS=owner/repo \
  repo-governance-mcp
```

### 3. 检查服务

打开：

```text
http://127.0.0.1:8080/healthz
```

## ChatGPT 该填哪个地址

给 ChatGPT 的是：

```text
https://你的域名/mcp
```

不是 `/healthz`。

## 这个服务能干什么

它会给 ChatGPT 一组工具，让 ChatGPT 能直接读 GitHub 现场，比如：

- `get_repo_status`
- `list_open_prs`
- `get_pr`
- `get_pr_diff`
- `list_changed_files`
- `read_file`
- `get_checks`
- `get_test_summary`
- `review_pr`
- `request_changes`
- `list_recent_commits`
- `get_issue`
- `post_pr_comment`

## 默认安全规则

- 默认只读
- 默认不写 PR 评论
- 只有你显式开了 `MCP_ENABLE_WRITE=true` 才允许写评论
- 只允许读你在 `MCP_ALLOWED_REPOS` 里写过的仓库
- 不允许执行任意 shell

## 详细排障

看这里：

[docs/ops-runbook.md](E:/Users/宁长久/Desktop/codex/docs/ops-runbook.md)
