from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any


class CodexExecUnavailableError(RuntimeError):
    """Raised when Codex CLI cannot be used for exec-mode automation."""


def resolve_codex_exec_command() -> str | None:
    env_command = os.getenv("CODEX_EXEC_COMMAND")
    if env_command:
        return env_command

    appdata = os.getenv("APPDATA")
    if appdata:
        candidate = Path(appdata) / "npm" / "codex.cmd"
        if candidate.exists():
            return str(candidate)

    for candidate in ("codex.cmd", "codex"):
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    return None


class CodexExecRuntime:
    def __init__(self, run_dir: Path, model: str | None = None) -> None:
        self.run_dir = run_dir
        self.logs_dir = run_dir / "logs"
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.model = model or os.getenv("HIVE_MODEL", "gpt-5.4")
        self.command = resolve_codex_exec_command()
        self.codex_home = self._prepare_codex_home()

    @classmethod
    def availability_reason(cls) -> str | None:
        command = resolve_codex_exec_command()
        if not command:
            return "Codex CLI is not installed"
        return cls._availability_probe(command)

    @classmethod
    def _availability_probe(cls, command: str) -> str | None:
        try:
            status = subprocess.run(
                [command, "login", "status"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=20,
            )
        except subprocess.TimeoutExpired:
            return "Codex CLI login probe timed out"
        if status.returncode != 0:
            return "Codex CLI is not logged in"
        login_output = (status.stdout or "") + (status.stderr or "")
        if "Logged in" not in login_output:
            return "Codex CLI login status is unavailable"
        return None

    def run_role(
        self,
        *,
        name: str,
        instructions: str,
        input_text: str,
        output_type: type[Any],
        cwd: Path,
    ) -> Any:
        if not self.command:
            raise CodexExecUnavailableError("Codex CLI is not installed")

        schema_path = self.run_dir / f"{name.lower()}_schema.json"
        message_path = self.run_dir / f"{name.lower()}_message.json"
        events_path = self.logs_dir / f"{name.lower()}_events.jsonl"
        stderr_path = self.logs_dir / f"{name.lower()}_stderr.log"

        schema_path.write_text(
            json.dumps(self._normalize_schema(output_type.model_json_schema()), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        prompt = (
            f"{instructions}\n\n"
            "Return only a JSON object that matches the output schema exactly. "
            "Do not wrap the JSON in markdown fences.\n\n"
            f"{input_text}"
        )

        result = subprocess.run(
            [
                self.command,
                "-c",
                "mcp_servers={}",
                "-m",
                self.model,
                "--dangerously-bypass-approvals-and-sandbox",
                "exec",
                "--skip-git-repo-check",
                "--ephemeral",
                "--json",
                "--output-schema",
                str(schema_path),
                "-o",
                str(message_path),
                prompt,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=1800,
            cwd=str(cwd),
            env=self._build_env(),
        )

        events_path.write_text(result.stdout or "", encoding="utf-8")
        stderr_path.write_text(result.stderr or "", encoding="utf-8")
        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            raise CodexExecUnavailableError(f"{name} exec failed: {stderr or f'exit code {result.returncode}'}")

        if not message_path.exists():
            raise CodexExecUnavailableError(f"{name} exec completed without a final message")

        payload = self._load_json_message(message_path.read_text(encoding="utf-8"))
        return output_type.model_validate(payload)

    @staticmethod
    def _load_json_message(raw: str) -> dict[str, Any]:
        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.DOTALL).strip()
        return json.loads(text)

    def _prepare_codex_home(self) -> Path:
        codex_home = Path(tempfile.gettempdir()) / "hive-codex" / self.run_dir.name / "codex-home"
        codex_home.mkdir(parents=True, exist_ok=True)

        global_home = Path.home() / ".codex"
        for filename in ("auth.json", "version.json"):
            source = global_home / filename
            destination = codex_home / filename
            if source.exists() and not destination.exists():
                shutil.copy2(source, destination)

        config_path = codex_home / "config.toml"
        if not config_path.exists():
            config_path.write_text(
                f'model = "{self.model}"\n'
                'model_reasoning_effort = "medium"\n'
                '\n'
                '[windows]\n'
                'sandbox = "unelevated"\n',
                encoding="utf-8",
            )

        return codex_home

    def _build_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env["CODEX_HOME"] = str(self.codex_home)
        return env

    @classmethod
    def _normalize_schema(cls, schema: Any) -> Any:
        if isinstance(schema, dict):
            normalized = {key: cls._normalize_schema(value) for key, value in schema.items()}
            if normalized.get("type") == "object" and "additionalProperties" not in normalized:
                normalized["additionalProperties"] = False
            if normalized.get("type") == "object" and isinstance(normalized.get("properties"), dict):
                normalized["required"] = list(normalized["properties"].keys())
            return normalized
        if isinstance(schema, list):
            return [cls._normalize_schema(item) for item in schema]
        return schema
