from __future__ import annotations

import fnmatch
import re
import subprocess
from pathlib import Path

from .protocol import DiffStats, GateCheck, GateReport, Plan


COMMAND_PATTERN = re.compile(r"^\s*-\s*(INSTALL_CMD|TEST_CMD|LINT_CMD|TYPECHECK_CMD)\s*:\s*(.+?)\s*$", re.MULTILINE)


def load_project_commands(agents_path: Path) -> dict[str, str]:
    if not agents_path.exists():
        return {}
    text = agents_path.read_text(encoding="utf-8")
    return {match.group(1): match.group(2) for match in COMMAND_PATTERN.finditer(text)}


class GateRunner:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root

    def run(self, plan: Plan, cwd: Path, logs_dir: Path, commands: dict[str, str]) -> GateReport:
        logs_dir.mkdir(parents=True, exist_ok=True)
        checks: list[GateCheck] = []
        for gate_name, command_key in (
            ("tests", "TEST_CMD"),
            ("lint", "LINT_CMD"),
            ("typecheck", "TYPECHECK_CMD"),
        ):
            checks.append(self._run_command_gate(gate_name, command_key, cwd, logs_dir, commands))

        diff_check, diff_stats = self._run_diff_scope_gate(plan, cwd)
        checks.append(diff_check)
        overall_pass = all(check.status != "failed" for check in checks)
        return GateReport(overall_pass=overall_pass, checks=checks, diff_stats=diff_stats)

    def _run_command_gate(
        self,
        gate_name: str,
        command_key: str,
        cwd: Path,
        logs_dir: Path,
        commands: dict[str, str],
    ) -> GateCheck:
        command = commands.get(command_key)
        if not command:
            return GateCheck(
                gate=gate_name,
                status="skipped",
                summary=f"{command_key} not defined in AGENTS.md",
            )

        log_path = logs_dir / f"{gate_name}.log"
        result = subprocess.run(
            command,
            cwd=cwd,
            shell=True,
            capture_output=True,
            text=True,
            check=False,
        )
        output = (result.stdout or "") + ("\n" if result.stdout and result.stderr else "") + (result.stderr or "")
        log_path.write_text(output, encoding="utf-8")
        status = "passed" if result.returncode == 0 else "failed"
        summary = f"{command_key} exited with {result.returncode}"
        return GateCheck(
            gate=gate_name,
            status=status,
            summary=summary,
            exit_code=result.returncode,
            log_path=str(log_path),
        )

    def _run_diff_scope_gate(self, plan: Plan, cwd: Path) -> tuple[GateCheck, DiffStats]:
        scope = next(
            (item.scope for item in plan.work_items if item.owner == "executor" and item.scope is not None),
            None,
        )
        if scope is None:
            return (
                GateCheck(gate="diff-scope", status="skipped", summary="No scope constraints defined"),
                DiffStats(),
            )

        if not self._is_git_checkout(cwd):
            return (
                GateCheck(
                    gate="diff-scope",
                    status="skipped",
                    summary="Workspace is not a git checkout; diff scope skipped",
                ),
                DiffStats(),
            )

        names_result = subprocess.run(
            ["git", "-C", str(cwd), "diff", "--name-only"],
            capture_output=True,
            text=True,
            check=False,
        )
        numstat_result = subprocess.run(
            ["git", "-C", str(cwd), "diff", "--numstat"],
            capture_output=True,
            text=True,
            check=False,
        )

        changed_files = [line.strip() for line in names_result.stdout.splitlines() if line.strip()]
        added_lines = 0
        deleted_lines = 0
        for line in numstat_result.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            try:
                added_lines += int(parts[0]) if parts[0].isdigit() else 0
                deleted_lines += int(parts[1]) if parts[1].isdigit() else 0
            except ValueError:
                continue

        within_files = len(changed_files) <= scope.max_files
        within_paths = all(self._matches_allowed_globs(path, scope.allow_globs) for path in changed_files)
        within_added = added_lines <= scope.max_added_lines
        within_deleted = deleted_lines <= scope.max_deleted_lines
        passed = within_files and within_paths and within_added and within_deleted
        summary = (
            f"files={len(changed_files)}/{scope.max_files}, "
            f"added={added_lines}/{scope.max_added_lines}, "
            f"deleted={deleted_lines}/{scope.max_deleted_lines}"
        )
        return (
            GateCheck(
                gate="diff-scope",
                status="passed" if passed else "failed",
                summary=summary,
            ),
            DiffStats(
                changed_files=changed_files,
                added_lines=added_lines,
                deleted_lines=deleted_lines,
            ),
        )

    @staticmethod
    def _matches_allowed_globs(path: str, allow_globs: list[str]) -> bool:
        return any(fnmatch.fnmatch(path, pattern) for pattern in allow_globs)

    @staticmethod
    def _is_git_checkout(path: Path) -> bool:
        result = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0 and result.stdout.strip() == "true"

