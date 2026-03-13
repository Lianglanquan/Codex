from __future__ import annotations

import os
import shlex
from typing import Any


class RuntimeUnavailableError(RuntimeError):
    """Raised when live agent execution is not available."""


class ApprovalInterruptedError(RuntimeError):
    """Raised when Codex requires approval in a non-interactive run."""


class AgentsSdkRuntime:
    def __init__(self, model: str | None = None) -> None:
        self.model = model or os.getenv("HIVE_MODEL", "gpt-5.3-codex")
        self._server_cm: Any | None = None
        self._server: Any | None = None
        self._Agent: Any | None = None
        self._Runner: Any | None = None
        self._set_default_openai_api: Any | None = None

    @classmethod
    def availability_reason(cls) -> str | None:
        try:
            import agents  # noqa: F401
        except ImportError:
            return "openai-agents is not installed"
        if not os.getenv("OPENAI_API_KEY"):
            return "OPENAI_API_KEY is not set"
        return None

    async def __aenter__(self) -> "AgentsSdkRuntime":
        reason = self.availability_reason()
        if reason:
            raise RuntimeUnavailableError(reason)

        from agents import Agent, Runner, set_default_openai_api
        from agents.mcp import MCPServerStdio

        self._Agent = Agent
        self._Runner = Runner
        self._set_default_openai_api = set_default_openai_api

        command = os.getenv("CODEX_MCP_COMMAND", "codex")
        args = shlex.split(os.getenv("CODEX_MCP_ARGS", "mcp-server"))
        self._set_default_openai_api(os.getenv("OPENAI_API_KEY"))
        self._server_cm = MCPServerStdio(
            name="Codex CLI",
            params={"command": command, "args": args},
            client_session_timeout_seconds=360000,
        )
        self._server = await self._server_cm.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._server_cm is not None:
            await self._server_cm.__aexit__(exc_type, exc, tb)

    async def run_role(
        self,
        *,
        name: str,
        instructions: str,
        input_text: str,
        output_type: type[Any],
        max_turns: int = 12,
    ) -> Any:
        if self._server is None or self._Agent is None or self._Runner is None:
            raise RuntimeUnavailableError("Agents SDK runtime is not initialized")

        agent = self._Agent(
            name=name,
            instructions=instructions,
            model=self.model,
            output_type=output_type,
            mcp_servers=[self._server],
        )
        result = await self._Runner.run(agent, input=input_text, max_turns=max_turns)
        if getattr(result, "interruptions", None):
            raise ApprovalInterruptedError("Codex requested approval during live execution")
        if result.final_output is None:
            raise RuntimeUnavailableError("Agent run completed without a final structured output")
        return result.final_output
