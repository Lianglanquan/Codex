from __future__ import annotations

import difflib
import filecmp
import os
import shutil
import subprocess
import time
from pathlib import Path

from .audit import AuditLogger


class WorktreeManager:
    def __init__(self, repo_root: Path, run_dir: Path, audit: AuditLogger) -> None:
        self.repo_root = repo_root
        self.run_dir = run_dir
        self.audit = audit
        self.worktree_root = run_dir / "worktrees"

    def prepare(self) -> dict[str, Path]:
        self.worktree_root.mkdir(parents=True, exist_ok=True)
        if self._can_use_git_worktrees():
            return self._prepare_git_worktrees()
        return self._prepare_workspace_copies()

    def capture_patch(self, exec_cwd: Path) -> Path:
        return self.capture_patch_for_files(exec_cwd, [])

    def capture_patch_for_files(self, exec_cwd: Path, changed_files: list[str]) -> Path:
        patch_path = self.run_dir / "patch.diff"
        if self._is_git_checkout(exec_cwd):
            result = subprocess.run(
                ["git", "-C", str(exec_cwd), "diff", "--no-ext-diff", "--binary"],
                capture_output=True,
                text=True,
                check=False,
            )
            patch_path.write_text(result.stdout, encoding="utf-8")
            return patch_path
        if changed_files:
            patch_text = self._build_unified_diff(self.repo_root, exec_cwd, changed_files)
            patch_path.write_text(
                patch_text or "# patch capture unavailable: no textual diff found for changed files.\n",
                encoding="utf-8",
            )
            return patch_path
        patch_path.write_text(
            "# patch capture unavailable: source workspace is not a usable git worktree.\n",
            encoding="utf-8",
        )
        return patch_path

    def sync_changed_files(self, changed_files: list[str], source: Path, targets: list[Path]) -> None:
        for rel_path in changed_files:
            source_path = source / rel_path
            for target_root in targets:
                target_path = target_root / rel_path
                if source_path.exists():
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    self._copy_with_retry(source_path, target_path)
                elif target_path.exists():
                    target_path.unlink()
        for target_root in targets:
            self.audit.emit(
                "worktree.synced",
                source=str(source),
                target=str(target_root),
                file_count=len(changed_files),
            )

    def _can_use_git_worktrees(self) -> bool:
        if not self._is_git_checkout(self.repo_root):
            return False
        head_check = subprocess.run(
            ["git", "-C", str(self.repo_root), "rev-parse", "--verify", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        return head_check.returncode == 0

    def _prepare_git_worktrees(self) -> dict[str, Path]:
        mapping = {
            "exec": self.worktree_root / "WT-exec",
            "test": self.worktree_root / "WT-test",
            "review": self.worktree_root / "WT-review",
        }
        job_slug = self.run_dir.name.replace("_", "-")
        for key, path in mapping.items():
            branch = f"codex/{job_slug}-{key}"
            result = subprocess.run(
                [
                    "git",
                    "-C",
                    str(self.repo_root),
                    "worktree",
                    "add",
                    "-b",
                    branch,
                    str(path),
                    "HEAD",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                self.audit.emit(
                    "worktree.failed",
                    name=key,
                    path=str(path),
                    stderr=result.stderr.strip(),
                )
                return self._prepare_workspace_copies()
            self.audit.emit("worktree.created", name=key, path=str(path), mode="git-worktree")
        return mapping

    def _prepare_workspace_copies(self) -> dict[str, Path]:
        mapping = {
            "exec": self.worktree_root / "WT-exec",
            "test": self.worktree_root / "WT-test",
            "review": self.worktree_root / "WT-review",
        }
        for key, path in mapping.items():
            self._copy_repo(self.repo_root, path)
            self._link_shared_dependencies(self.repo_root, path)
            self.audit.emit("worktree.created", name=key, path=str(path), mode="workspace-copy")
        return mapping

    def _copy_repo(self, source: Path, destination: Path) -> None:
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(
            source,
            destination,
            ignore=shutil.ignore_patterns(
                ".git",
                ".venv",
                "node_modules",
                ".next",
                ".next-build*",
                ".pytest_cache",
                ".pytest_tmp",
                "runs",
                "__pycache__",
                "*.egg-info",
                "tsconfig.tsbuildinfo",
            ),
        )

    def _link_shared_dependencies(self, source: Path, destination: Path) -> None:
        candidates = [
            (source / "apps" / "web" / "node_modules", destination / "apps" / "web" / "node_modules"),
        ]
        for source_path, destination_path in candidates:
            if not source_path.exists() or destination_path.exists():
                continue
            destination_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                if os.name == "nt":
                    subprocess.run(
                        ["cmd", "/c", "mklink", "/J", str(destination_path), str(source_path)],
                        capture_output=True,
                        text=True,
                        check=True,
                    )
                else:
                    destination_path.symlink_to(source_path, target_is_directory=True)
            except Exception:
                # If linking fails, leave the worktree copy usable for Python-only flows.
                continue

    @staticmethod
    def _is_git_checkout(path: Path) -> bool:
        result = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0 and result.stdout.strip() == "true"

    @staticmethod
    def _copy_with_retry(source_path: Path, target_path: Path, attempts: int = 8, delay_seconds: float = 0.5) -> None:
        last_error: PermissionError | None = None
        for _ in range(attempts):
            try:
                shutil.copy2(source_path, target_path)
                return
            except PermissionError as exc:
                last_error = exc
                time.sleep(delay_seconds)
        if last_error is not None:
            raise last_error

    @staticmethod
    def _build_unified_diff(reference_root: Path, candidate_root: Path, changed_files: list[str]) -> str:
        chunks: list[str] = []
        for rel_path in changed_files:
            left_path = reference_root / rel_path
            right_path = candidate_root / rel_path

            if left_path.exists() and right_path.exists():
                if filecmp.cmp(left_path, right_path, shallow=False):
                    continue
                left_lines = left_path.read_text(encoding="utf-8", errors="ignore").splitlines()
                right_lines = right_path.read_text(encoding="utf-8", errors="ignore").splitlines()
            elif right_path.exists():
                left_lines = []
                right_lines = right_path.read_text(encoding="utf-8", errors="ignore").splitlines()
            elif left_path.exists():
                left_lines = left_path.read_text(encoding="utf-8", errors="ignore").splitlines()
                right_lines = []
            else:
                continue

            diff = difflib.unified_diff(
                left_lines,
                right_lines,
                fromfile=str(left_path),
                tofile=str(right_path),
                lineterm="",
            )
            chunk = "\n".join(diff).strip()
            if chunk:
                chunks.append(chunk)

        return "\n\n".join(chunks) + ("\n" if chunks else "")
