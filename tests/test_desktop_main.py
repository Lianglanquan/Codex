from __future__ import annotations

from pathlib import Path

from apps.desktop.main import (
    format_artifact_evidence,
    format_boss_summary,
    format_chat_reply,
    format_job_record,
    inspect_project,
    load_app_state,
    remember_recent_repo,
)
from orchestrator.hive.protocol import (
    ArtifactPaths,
    Deliverable,
    DeliveryArtifact,
    JobMode,
    JobRecord,
    JobStatus,
    Outcome,
    VerificationStep,
)


def test_format_job_record_includes_delivery_and_runtime_notes() -> None:
    record = JobRecord(
        job_id="job-1",
        boss_prompt="目标：验证格式化",
        repo_path="E:/repo",
        status=JobStatus.NEEDS_HUMAN,
        mode=JobMode.DRY_RUN,
        created_at="2026-03-10T10:00:00+08:00",
        updated_at="2026-03-10T10:01:00+08:00",
        acceptance=["目标：验证格式化"],
        runtime_notes=["agents-sdk: OPENAI_API_KEY is not set"],
        artifacts=ArtifactPaths(
            run_dir="E:/repo/runs/job-1",
            job="E:/repo/runs/job-1/job.json",
            plan="E:/repo/runs/job-1/plan.json",
            delivery="E:/repo/runs/job-1/deliver.json",
        ),
        delivery=Deliverable(
            task_id="job-1",
            outcome=Outcome.NEEDS_HUMAN,
            summary="需要补环境后再跑 live",
            changed_files=[],
            verification=[],
            gate_report_path="E:/repo/runs/job-1/gate_report.json",
            reviewer_decision="FAIL",
            reviewer_blocker_count=1,
            risks=["live 未执行"],
            rollback="删除 run 目录",
            remaining_gaps=["配置 API key"],
            artifacts=[],
        ),
    )

    text = format_job_record(record)

    assert "任务号: job-1" in text
    assert "结论: 需要补环境后再跑 live" in text
    assert "交付包: E:/repo/runs/job-1/deliver.json" in text
    assert "- 配置 API key" in text
    assert "- agents-sdk: OPENAI_API_KEY is not set" in text


def test_format_boss_summary_and_artifact_evidence_include_owner_facing_details() -> None:
    record = JobRecord(
        job_id="job-2",
        boss_prompt="目标：修好 healthz",
        repo_path="E:/repo",
        status=JobStatus.PASS,
        mode=JobMode.AUTO,
        created_at="2026-03-10T10:00:00+08:00",
        updated_at="2026-03-10T10:05:00+08:00",
        acceptance=["目标：修好 healthz"],
        artifacts=ArtifactPaths(
            run_dir="E:/repo/runs/job-2",
            job="E:/repo/runs/job-2/job.json",
            plan="E:/repo/runs/job-2/plan.json",
            delivery="E:/repo/runs/job-2/deliver.json",
            patch="E:/repo/runs/job-2/patch.diff",
        ),
        delivery=Deliverable(
            task_id="job-2",
            outcome=Outcome.PASS,
            summary="healthz 接口已完成并通过验证",
            changed_files=[],
            verification=[
                VerificationStep(
                    name="tests",
                    command="python -m pytest",
                    result="passed",
                    log_path="E:/repo/runs/job-2/logs/test.log",
                )
            ],
            gate_report_path="E:/repo/runs/job-2/gate_report.json",
            reviewer_decision="PASS",
            reviewer_blocker_count=0,
            risks=["需要关注线上环境变量"],
            rollback="git revert",
            remaining_gaps=[],
            artifacts=[DeliveryArtifact(name="deliver", path="E:/repo/runs/job-2/deliver.json")],
        ),
    )

    summary = format_boss_summary(record)
    evidence = format_artifact_evidence(record)

    assert "healthz 接口已完成并通过验证" in summary
    assert "Reviewer: PASS / blockers=0" in summary
    assert "Patch: E:/repo/runs/job-2/patch.diff" in evidence
    assert "python -m pytest -> passed" in evidence


def test_format_chat_reply_focuses_on_conclusion_and_risks() -> None:
    record = JobRecord(
        job_id="job-3",
        boss_prompt="目标：整理交付",
        repo_path="E:/repo",
        status=JobStatus.NEEDS_HUMAN,
        mode=JobMode.DRY_RUN,
        created_at="2026-03-10T10:00:00+08:00",
        updated_at="2026-03-10T10:05:00+08:00",
        acceptance=["目标：整理交付"],
        artifacts=ArtifactPaths(
            run_dir="E:/repo/runs/job-3",
            job="E:/repo/runs/job-3/job.json",
            plan="E:/repo/runs/job-3/plan.json",
        ),
        delivery=Deliverable(
            task_id="job-3",
            outcome=Outcome.NEEDS_HUMAN,
            summary="交付骨架已生成，但 live 运行还缺环境",
            changed_files=[],
            verification=[],
            gate_report_path="E:/repo/runs/job-3/gate_report.json",
            reviewer_decision="FAIL",
            reviewer_blocker_count=1,
            risks=["还没有跑真实 live 流程"],
            rollback="删除 run 目录",
            remaining_gaps=["配置 API key"],
            artifacts=[],
        ),
    )

    text = format_chat_reply(record)

    assert "交付骨架已生成" in text
    assert "Reviewer: FAIL / blockers=1" in text
    assert "- 还没有跑真实 live 流程" in text
    assert "- 配置 API key" in text


def test_remember_recent_repo_deduplicates_and_limits() -> None:
    repos = remember_recent_repo(
        ["E:/b", "E:/c", "E:/d", "E:/e", "E:/f"],
        Path("E:/c"),
        limit=4,
    )

    assert repos[0].lower().endswith("e:/c".replace("/", "\\").lower()) or repos[0].lower().endswith("e:/c")
    assert len(repos) == 4
    assert len(set(repos)) == len(repos)


def test_load_app_state_defaults_and_inspect_project(tmp_path: Path) -> None:
    state = load_app_state(tmp_path / "missing.json")
    assert state.recent_repos

    (tmp_path / "AGENTS.md").write_text("- TEST_CMD: python -m pytest\n- LINT_CMD: python lint.py\n", encoding="utf-8")
    (tmp_path / "OWNER_PROFILE.md").write_text("# owner", encoding="utf-8")
    run_dir = tmp_path / "runs" / "20260310_job-1"
    run_dir.mkdir(parents=True)

    snapshot = inspect_project(tmp_path)

    assert snapshot.has_agents is True
    assert snapshot.has_owner_profile is True
    assert "Tests" in snapshot.command_labels
    assert snapshot.latest_run_dir == str(run_dir)
