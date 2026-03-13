# 运维手册：照着做就能把 MCP 跑起来

这份是给工程师看的。

目标只有一个：

把这个仓库的 MCP 服务跑起来，让 ChatGPT 能直接读 GitHub 仓库、PR、checks 和测试结果。

## 一、你最后要达到什么效果

做到下面 3 件事就算完成：

1. 你能打开 `http://127.0.0.1:8080/healthz`
2. 页面返回 `{"status":"ok"}`
3. ChatGPT 里能看到 `get_pr`、`get_checks`、`review_pr` 这些工具

## 二、先准备什么

你至少要准备这两个值：

- `GITHUB_TOKEN`
- `GITHUB_REPOSITORY`

含义很简单：

- `GITHUB_TOKEN`：让 MCP 去读 GitHub 用的钥匙
- `GITHUB_REPOSITORY`：你要读哪个仓库，格式像 `owner/repo`

例子：

```text
GITHUB_REPOSITORY=openai/codex-action
```

建议再准备这个：

- `MCP_ALLOWED_REPOS`

它的意思是：只允许 MCP 读哪些仓库。
如果你只想让它读一个仓库，就填和 `GITHUB_REPOSITORY` 一样的值。

## 三、本地启动，最省事的方法

### 方法 A：Windows 直接启动

1. 打开 PowerShell
2. 进入仓库目录
3. 先装依赖

```powershell
python -m pip install -e .[dev]
```

4. 设置环境变量

```powershell
$env:GITHUB_TOKEN="你的 GitHub Token"
$env:GITHUB_REPOSITORY="owner/repo"
$env:MCP_ALLOWED_REPOS="owner/repo"
```

5. 直接启动

```powershell
.\scripts\start_mcp_server.ps1
```

6. 浏览器打开：

```text
http://127.0.0.1:8080/healthz
```

看到：

```json
{"status":"ok"}
```

就说明服务起来了。

### 方法 B：手动命令启动

如果你不想用脚本，就手动执行：

```powershell
python -m pip install -e .[dev]
$env:GITHUB_TOKEN="你的 GitHub Token"
$env:GITHUB_REPOSITORY="owner/repo"
$env:MCP_ALLOWED_REPOS="owner/repo"
python -m uvicorn server:app --app-dir mcp-server --host 0.0.0.0 --port 8080
```

## 四、如果你要部署到服务器

最简单的办法是 Docker。

### 第一步：构建镜像

在仓库根目录执行：

```bash
docker build -f mcp-server/Dockerfile -t repo-governance-mcp .
```

### 第二步：启动容器

```bash
docker run -p 8080:8080 \
  -e GITHUB_TOKEN=你的Token \
  -e GITHUB_REPOSITORY=owner/repo \
  -e MCP_ALLOWED_REPOS=owner/repo \
  repo-governance-mcp
```

### 第三步：检查是否活着

打开：

```text
http://服务器地址:8080/healthz
```

返回 `{"status":"ok"}` 就对了。

### 第四步：如果要给 ChatGPT 用

你最终给 ChatGPT 的地址应该是：

```text
https://你的域名/mcp
```

不是 `/healthz`，是 `/mcp`。

`/healthz` 只是给你自己检查服务是不是活着。

## 五、GitHub 那边要点哪里

### 1. 配 OpenAI key 给 Codex review 用

1. 打开 GitHub 仓库主页
2. 点 `Settings`
3. 点左侧 `Secrets and variables`
4. 点 `Actions`
5. 点 `New repository secret`
6. 名字填：

```text
OPENAI_API_KEY
```

7. 值填你的 OpenAI API Key
8. 保存

### 2. 确认 Actions 没被关掉

1. 打开仓库主页
2. 点上方 `Actions`
3. 如果 GitHub 提示要启用，就点启用

你应该能看到这些工作流：

- `CI`
- `Codex Review`
- `Codex Task`

### 3. 建议把 PR 保护打开

1. 打开仓库主页
2. 点 `Settings`
3. 点左侧 `Branches`
4. 给主分支加保护规则
5. 勾选必须通过这些检查：
   - `lint`
   - `typecheck`
   - `build`
   - `test`

## 六、ChatGPT 那边怎么接

老板只要看这份：

[docs/chatgpt-connect.md](E:/Users/宁长久/Desktop/codex/docs/chatgpt-connect.md)

老板不需要看你这份运维手册。

## 七、出问题先看哪里

### 情况 1：`/healthz` 打不开

先查这几个：

1. 服务是不是根本没启动
2. 端口是不是被占了
3. 防火墙有没有拦住
4. 你是不是把地址写错了

### 情况 2：服务活着，但 ChatGPT 看不到工具

先查这几个：

1. ChatGPT 的 developer mode 开没开
2. 接的是不是 `/mcp`
3. 认证信息是不是填错了
4. MCP 地址是不是 HTTPS

### 情况 3：能连上，但读不到仓库

先查这几个：

1. `GITHUB_TOKEN` 对不对
2. `GITHUB_REPOSITORY` 对不对
3. `MCP_ALLOWED_REPOS` 有没有把这个仓库放进去

### 情况 4：能读仓库，但拿不到 CI / checks

先查这几个：

1. GitHub Actions 有没有真的跑起来
2. PR 是不是在真实仓库里，不是在你本地目录里想象出来的
3. `.github/workflows/ci.yml` 有没有被推上去
4. test job 有没有上传 `ci-test-summary` artifact

## 八、日志怎么看

最简单的看法：

- 你在哪个窗口启动的服务，日志就在哪个窗口里
- 报错先看最后 20 行

重点看这几类词：

- `401` / `403`：一般是 token 或权限问题
- `404`：一般是仓库名、PR 编号、文件路径写错了
- `429`：一般是 GitHub API 调太快了

## 九、哪些变量是干嘛的

- `GITHUB_TOKEN`：GitHub 钥匙，没有它就读不了仓库
- `GITHUB_REPOSITORY`：默认仓库名
- `MCP_ALLOWED_REPOS`：允许读哪些仓库
- `MCP_ENABLE_WRITE`：要不要允许回写 PR 评论，默认不要开
- `PORT`：服务端口，默认 `8080`

## 十、要回滚怎么办

如果你想先停掉这套系统，最直接的做法是：

1. 先停 MCP 服务
2. 在 GitHub 里把新加的 workflow 关掉
3. 如果已经推上仓库，就提一个回滚 PR，把这些文件回退：
   - `.github/workflows/ci.yml`
   - `.github/workflows/codex-review.yml`
   - `.github/workflows/codex-task.yml`
   - `mcp-server/`
   - `docs/` 里这套说明文档

如果只是怕误写评论，就不用全停：

- 把 `MCP_ENABLE_WRITE=false`

这样它就只读，不写。
