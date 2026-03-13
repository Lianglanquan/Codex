# Hive Codex MVP

Codex CLI-driven personal boss cockpit for the "boss mode" workflow: one goal in, one delivery package out.

## What is included

- `orchestrator/hive`: Python orchestrator for job lifecycle, worktree isolation, gates, audit logs, and delivery-package generation.
- `apps/api`: FastAPI entrypoint that exposes `POST /jobs`, `GET /jobs/{id}`, and `GET /jobs/{id}/events`.
- `apps/web`: Next.js boss UI shell for creating jobs and reading the resulting package.
- `.agents/skills`: repository skills for task analysis, minimal implementation, test writing, review, and delivery prep.
- `.codex/config.toml`: project-level Codex defaults for sandboxing and multi-agent settings.
- `docs/personal-boss-mode.md`: the personal-product brief and framework borrowing rules.
- `OWNER_PROFILE.example.md`: a template for encoding your own working style, priorities, and delegation rules.

## Product stance

This repository is not trying to be a generic agent platform.

- It borrows handoffs, guardrails, and tracing from OpenAI Agents SDK.
- It borrows Skills and `AGENTS.md` as the operating system for SOPs and rules.
- It borrows role modeling and task choreography from AutoGen, CrewAI, and MetaGPT.
- It borrows graph-like workflow discipline from LangGraph.
- It borrows real-repo execution discipline from SWE-agent.
- It borrows the "few clear agents, structured artifacts, minimal idle talk" principle from Anthropic's agent guidance.

It does **not** copy any single framework's UI, runtime worldview, or demo shape.

## Quick start

1. Create a Python environment and install dependencies:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e .[dev]
```

2. Set environment variables:

```bash
set OPENAI_API_KEY=sk-...
set CODEX_MCP_COMMAND=codex
set CODEX_MCP_ARGS=mcp-server
set CODEX_EXEC_COMMAND=codex.cmd
set NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```

3. Run the API:

```bash
uvicorn apps.api.main:app --reload
```

4. Run the web shell:

```bash
cd apps/web
npm install
npm run dev
```

5. Submit a job from CLI:

```bash
python -m orchestrator.hive.main run --repo . --job "为服务增加 /healthz 端点，必须通过测试并输出交付包"
```

## Runtime modes

- `auto`: Use the Agents SDK plus Codex MCP when `OPENAI_API_KEY` and `openai-agents` are available.
- `dry-run`: Generate the full artifact tree without invoking live agents. This is useful for validating the pipeline wiring.

If live runtime prerequisites are missing, the controller falls back to a dry-run package and records the reason in `deliver.json`.

## Notes

- `auto` mode first tries Agents SDK + Codex MCP when `OPENAI_API_KEY` is available.
- If no API key is present but Codex CLI is logged in, the orchestrator falls back to `codex exec` for live role execution.
- On Windows, `codex.cmd` from `%APPDATA%\npm` is more reliable than the packaged `codex.exe` alias.
