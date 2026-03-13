from __future__ import annotations

import asyncio
from pathlib import Path

from orchestrator.hive.controller import HiveController
from orchestrator.hive.protocol import JobMode, JobRequest


def test_run_job_dry_run_creates_delivery_package(repo_root: Path) -> None:
    controller = HiveController(repo_root)
    record = asyncio.run(
        controller.run_job(
            JobRequest(
                boss_prompt="为服务增加 /healthz endpoint 并输出交付包",
                repo_path=str(repo_root),
                mode=JobMode.DRY_RUN,
            )
        )
    )

    assert record.status.value == "needs_human"
    assert record.delivery is not None
    assert Path(record.artifacts.delivery).exists()
    assert Path(record.artifacts.plan).exists()
    assert Path(record.artifacts.events).exists()
