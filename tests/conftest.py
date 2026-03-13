from __future__ import annotations

import shutil
from pathlib import Path
from uuid import uuid4

import pytest


@pytest.fixture
def repo_root() -> Path:
    base_dir = Path.cwd() / "runs" / "pytest-fixtures"
    base_dir.mkdir(parents=True, exist_ok=True)
    repo_root = base_dir / f"repo-{uuid4().hex}"
    repo_root.mkdir()
    (repo_root / "runs").mkdir()
    (repo_root / "AGENTS.md").write_text(
        "- INSTALL_CMD: python -m pip install -e .[dev] && npm --prefix apps/web install\n"
        "- TEST_CMD: python -m pytest\n"
        "- LINT_CMD: python scripts/python_syntax_check.py orchestrator apps/api tests\n"
        "- TYPECHECK_CMD: npm --prefix apps/web run typecheck\n",
        encoding="utf-8",
    )

    try:
        yield repo_root
    finally:
        shutil.rmtree(repo_root, ignore_errors=True)
