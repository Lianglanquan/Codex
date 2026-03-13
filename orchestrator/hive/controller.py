from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path

from .audit import AuditLogger
from .codex_exec_runtime import CodexExecRuntime, CodexExecUnavailableError
from .gates import GateRunner, load_project_commands
from .protocol import (
    ArchitectReport,
    ArtifactPaths,
    Deliverable,
    DeliveryArtifact,
    GateCheck,
    GateReport,
    ImplementationReport,
    JobMode,
    JobRecord,
    JobRequest,
    JobStatus,
    Outcome,
    Plan,
    ProposedTest,
    ReviewBlocker,
    ReviewReport,
    RiskNote,
    RubricScores,
    ScopeConstraint,
    TestCommandResult,
    TestReport,
    VerificationStep,
    WorkItem,
)
from .roles import (
    ARCHITECT_INSTRUCTIONS,
    EXECUTOR_INSTRUCTIONS,
    REVIEWER_INSTRUCTIONS,
    SUMMARIZER_INSTRUCTIONS,
    TESTER_INSTRUCTIONS,
    build_architect_prompt,
    build_executor_prompt,
    build_reviewer_prompt,
    build_summarizer_prompt,
    build_tester_prompt,
)
from .sdk_runtime import AgentsSdkRuntime, ApprovalInterruptedError, RuntimeUnavailableError
from .worktrees import WorktreeManager


class HiveController:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()
        self.runs_root = self.repo_root / "runs"
        self.runs_root.mkdir(parents=True, exist_ok=True)

    async def run_job(self, request: JobRequest) -> JobRecord:
        owner_profile = request.owner_profile or self._load_owner_profile()
        if owner_profile:
            request = request.model_copy(update={"owner_profile": owner_profile})
        now = datetime.now(timezone.utc).astimezone()
        timestamp = now.strftime("%Y%m%d_%H%M%S")
        job_id = f"job-{timestamp}"
        run_dir = self.runs_root / f"{timestamp}_{job_id}"
        run_dir.mkdir(parents=True, exist_ok=True)
        audit = AuditLogger(run_dir)

        created_at = now.isoformat(timespec="seconds")
        artifacts = ArtifactPaths(
            run_dir=str(run_dir),
            job=str(run_dir / "job.json"),
            plan=str(run_dir / "plan.json"),
            events=str(run_dir / "events.ndjson"),
        )
        record = JobRecord(
            job_id=job_id,
            boss_prompt=request.boss_prompt,
            repo_path=request.repo_path,
            status=JobStatus.RUNNING,
            mode=request.mode,
            created_at=created_at,
            updated_at=created_at,
            acceptance=self._derive_acceptance(request),
            artifacts=artifacts,
        )
        self._persist_job(audit, record)
        audit.emit(
            "job.started",
            job_id=job_id,
            input_hash=self._hash_prompt(request.boss_prompt),
            mode=request.mode.value,
        )

        commands = load_project_commands(self.repo_root / "AGENTS.md")
        plan = self._build_plan(job_id, record.acceptance, request.boss_prompt, commands)
        audit.write_json(Path(record.artifacts.plan), plan)
        audit.emit("plan.created", job_id=job_id, path=record.artifacts.plan)

        worktree_manager = WorktreeManager(self.repo_root, run_dir, audit)
        worktrees = worktree_manager.prepare()
        record.artifacts.patch = str(worktree_manager.capture_patch(worktrees["exec"]))

        architect_path = run_dir / "architect_report.json"
        impl_path = run_dir / "impl_report.json"
        test_path = run_dir / "test_report.json"
        gate_path = run_dir / "gate_report.json"
        review_path = run_dir / "review.json"
        delivery_path = run_dir / "deliver.json"
        delivery_md_path = run_dir / "DELIVER.md"

        record.artifacts.architect = str(architect_path)
        record.artifacts.implementation = str(impl_path)
        record.artifacts.tests = str(test_path)
        record.artifacts.gates = str(gate_path)
        record.artifacts.review = str(review_path)
        record.artifacts.delivery = str(delivery_path)

        agents_runtime_error = AgentsSdkRuntime.availability_reason()
        codex_exec_error = CodexExecRuntime.availability_reason()
        runtime_name = None
        if request.mode == JobMode.AUTO and agents_runtime_error is None:
            runtime_name = "agents-sdk"
        elif request.mode == JobMode.AUTO and codex_exec_error is None:
            runtime_name = "codex-exec"

        if runtime_name is None:
            if agents_runtime_error:
                record.runtime_notes.append(f"agents-sdk: {agents_runtime_error}")
            if codex_exec_error:
                record.runtime_notes.append(f"codex-exec: {codex_exec_error}")
            self._write_dry_run_logs(run_dir, record.runtime_notes)
            architect_report = self._dry_architect_report(plan)
            impl_report = self._dry_impl_report()
            test_report = self._dry_test_report(run_dir)
            gate_report = self._dry_gate_report(record.runtime_notes, run_dir)
            review_report = self._dry_review_report(record.runtime_notes)
            delivery = self._dry_delivery(plan, impl_report, gate_report, review_report, run_dir)
        elif runtime_name == "codex-exec":
            audit.emit("runtime.selected", job_id=job_id, runtime=runtime_name)
            try:
                runtime = CodexExecRuntime(run_dir)
                architect_report = runtime.run_role(
                    name="Architect",
                    instructions=ARCHITECT_INSTRUCTIONS,
                    input_text=build_architect_prompt(
                        job=request,
                        plan=plan,
                        run_dir=str(run_dir),
                        exec_cwd=str(worktrees["exec"]),
                    ),
                    output_type=ArchitectReport,
                    cwd=worktrees["exec"],
                )
                impl_report = runtime.run_role(
                    name="Executor",
                    instructions=EXECUTOR_INSTRUCTIONS,
                    input_text=build_executor_prompt(
                        job=request,
                        plan=plan,
                        architect_report=architect_report,
                        exec_cwd=str(worktrees["exec"]),
                    ),
                    output_type=ImplementationReport,
                    cwd=worktrees["exec"],
                )
                changed_files = [item.path for item in impl_report.changed_files]
                worktrees = self._sync_or_coalesce_worktrees(
                    worktree_manager=worktree_manager,
                    worktrees=worktrees,
                    changed_files=changed_files,
                    record=record,
                    audit=audit,
                )
                record.artifacts.patch = str(worktree_manager.capture_patch_for_files(worktrees["exec"], changed_files))
                test_report = runtime.run_role(
                    name="Tester",
                    instructions=TESTER_INSTRUCTIONS,
                    input_text=build_tester_prompt(
                        job=request,
                        plan=plan,
                        implementation_report=impl_report,
                        test_cwd=str(worktrees["test"]),
                        commands=commands,
                    ),
                    output_type=TestReport,
                    cwd=worktrees["test"],
                )
                gate_report = GateRunner(self.repo_root).run(plan, worktrees["test"], run_dir / "logs", commands)
                review_report = runtime.run_role(
                    name="Reviewer",
                    instructions=REVIEWER_INSTRUCTIONS,
                    input_text=build_reviewer_prompt(
                        job=request,
                        plan=plan,
                        implementation_report=impl_report,
                        test_report=test_report,
                        gate_report=gate_report,
                    ),
                    output_type=ReviewReport,
                    cwd=worktrees["review"],
                )
                delivery = runtime.run_role(
                    name="Summarizer",
                    instructions=SUMMARIZER_INSTRUCTIONS,
                    input_text=build_summarizer_prompt(
                        job=request,
                        plan=plan,
                        implementation_report=impl_report,
                        test_report=test_report,
                        gate_report=gate_report,
                        review_report=review_report,
                        delivery_paths={
                            "plan": record.artifacts.plan,
                            "implementation": record.artifacts.implementation or "",
                            "tests": record.artifacts.tests or "",
                            "gates": record.artifacts.gates or "",
                            "review": record.artifacts.review or "",
                            "patch": record.artifacts.patch or "",
                        },
                    ),
                    output_type=Deliverable,
                    cwd=run_dir,
                )
            except CodexExecUnavailableError as exc:
                record.runtime_notes.append(str(exc))
                self._write_dry_run_logs(run_dir, record.runtime_notes)
                architect_report = self._dry_architect_report(plan)
                impl_report = self._dry_impl_report()
                test_report = self._dry_test_report(run_dir)
                gate_report = self._dry_gate_report(record.runtime_notes, run_dir)
                review_report = self._dry_review_report(record.runtime_notes)
                delivery = self._dry_delivery(plan, impl_report, gate_report, review_report, run_dir)
        else:
            audit.emit("runtime.selected", job_id=job_id, runtime=runtime_name)
            try:
                async with AgentsSdkRuntime() as runtime:
                    architect_report = await runtime.run_role(
                        name="Architect",
                        instructions=ARCHITECT_INSTRUCTIONS,
                        input_text=build_architect_prompt(
                            job=request,
                            plan=plan,
                            run_dir=str(run_dir),
                            exec_cwd=str(worktrees["exec"]),
                        ),
                        output_type=ArchitectReport,
                    )
                    impl_report = await runtime.run_role(
                        name="Executor",
                        instructions=EXECUTOR_INSTRUCTIONS,
                        input_text=build_executor_prompt(
                            job=request,
                            plan=plan,
                            architect_report=architect_report,
                            exec_cwd=str(worktrees["exec"]),
                        ),
                        output_type=ImplementationReport,
                    )
                    changed_files = [item.path for item in impl_report.changed_files]
                    worktrees = self._sync_or_coalesce_worktrees(
                        worktree_manager=worktree_manager,
                        worktrees=worktrees,
                        changed_files=changed_files,
                        record=record,
                        audit=audit,
                    )
                    record.artifacts.patch = str(
                        worktree_manager.capture_patch_for_files(worktrees["exec"], changed_files)
                    )
                    test_report = await runtime.run_role(
                        name="Tester",
                        instructions=TESTER_INSTRUCTIONS,
                        input_text=build_tester_prompt(
                            job=request,
                            plan=plan,
                            implementation_report=impl_report,
                            test_cwd=str(worktrees["test"]),
                            commands=commands,
                        ),
                        output_type=TestReport,
                    )
                    gate_report = GateRunner(self.repo_root).run(plan, worktrees["test"], run_dir / "logs", commands)
                    review_report = await runtime.run_role(
                        name="Reviewer",
                        instructions=REVIEWER_INSTRUCTIONS,
                        input_text=build_reviewer_prompt(
                            job=request,
                            plan=plan,
                            implementation_report=impl_report,
                            test_report=test_report,
                            gate_report=gate_report,
                        ),
                        output_type=ReviewReport,
                    )
                    delivery = await runtime.run_role(
                        name="Summarizer",
                        instructions=SUMMARIZER_INSTRUCTIONS,
                        input_text=build_summarizer_prompt(
                            job=request,
                            plan=plan,
                            implementation_report=impl_report,
                            test_report=test_report,
                            gate_report=gate_report,
                            review_report=review_report,
                            delivery_paths={
                                "plan": record.artifacts.plan,
                                "implementation": record.artifacts.implementation or "",
                                "tests": record.artifacts.tests or "",
                                "gates": record.artifacts.gates or "",
                                "review": record.artifacts.review or "",
                                "patch": record.artifacts.patch or "",
                            },
                        ),
                        output_type=Deliverable,
                    )
            except (RuntimeUnavailableError, ApprovalInterruptedError) as exc:
                record.runtime_notes.append(str(exc))
                self._write_dry_run_logs(run_dir, record.runtime_notes)
                architect_report = self._dry_architect_report(plan)
                impl_report = self._dry_impl_report()
                test_report = self._dry_test_report(run_dir)
                gate_report = self._dry_gate_report(record.runtime_notes, run_dir)
                review_report = self._dry_review_report(record.runtime_notes)
                delivery = self._dry_delivery(plan, impl_report, gate_report, review_report, run_dir)

        audit.write_json(architect_path, architect_report)
        audit.write_json(impl_path, impl_report)
        audit.write_json(test_path, test_report)
        audit.write_json(gate_path, gate_report)
        audit.write_json(review_path, review_report)
        audit.write_json(delivery_path, delivery)
        audit.write_text(delivery_md_path, self._render_delivery_markdown(delivery))

        record.delivery = delivery
        record.status = self._map_outcome_to_status(delivery.outcome)
        record.updated_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        self._persist_job(audit, record)
        audit.emit("job.completed", job_id=job_id, status=record.status.value)
        return record

    def get_job(self, job_id: str) -> JobRecord:
        for job_file in self.runs_root.glob(f"*_{job_id}/job.json"):
            return JobRecord.model_validate_json(job_file.read_text(encoding="utf-8"))
        raise FileNotFoundError(f"Job {job_id} was not found")

    def get_job_events_path(self, job_id: str) -> Path:
        for path in self.runs_root.glob(f"*_{job_id}/events.ndjson"):
            return path
        raise FileNotFoundError(f"Event stream for {job_id} was not found")

    def _persist_job(self, audit: AuditLogger, record: JobRecord) -> None:
        audit.write_json(Path(record.artifacts.job), record)

    def _sync_or_coalesce_worktrees(
        self,
        *,
        worktree_manager: WorktreeManager,
        worktrees: dict[str, Path],
        changed_files: list[str],
        record: JobRecord,
        audit: AuditLogger,
    ) -> dict[str, Path]:
        if not changed_files:
            return worktrees
        try:
            worktree_manager.sync_changed_files(
                changed_files,
                worktrees["exec"],
                [worktrees["test"], worktrees["review"]],
            )
            return worktrees
        except PermissionError as exc:
            note = (
                "Windows file lock prevented worktree sync; tester and reviewer were coalesced onto "
                f"the executor workspace: {exc}"
            )
            record.runtime_notes.append(note)
            audit.emit("worktree.sync_fallback", reason=str(exc))
            return {
                **worktrees,
                "test": worktrees["exec"],
                "review": worktrees["exec"],
            }

    def _derive_acceptance(self, request: JobRequest) -> list[str]:
        if request.acceptance:
            return request.acceptance
        segments = re.split(r"[;\n]+", request.boss_prompt)
        items = [segment.strip(" -\t") for segment in segments if segment.strip()]
        return items[:4] if items else [request.boss_prompt]

    def _load_owner_profile(self) -> str | None:
        for candidate in ("OWNER_PROFILE.md", "OWNER_PROFILE.txt"):
            path = self.repo_root / candidate
            if path.exists():
                return path.read_text(encoding="utf-8")
        return None

    def _build_plan(
        self,
        job_id: str,
        acceptance: list[str],
        boss_prompt: str,
        commands: dict[str, str],
    ) -> Plan:
        summary = acceptance[0] if acceptance else boss_prompt[:120]
        scope = ScopeConstraint()
        return Plan(
            task_id=job_id,
            summary=summary,
            acceptance=acceptance,
            work_items=[
                WorkItem(
                    id="WI-1",
                    owner="architect",
                    goal="拆解任务并标出受影响文件、边界和风险",
                    inputs=["boss_prompt", "AGENTS.md"],
                    outputs=["architect_report.json"],
                ),
                WorkItem(
                    id="WI-2",
                    owner="executor",
                    goal="在 scope 内完成最小必要改动",
                    inputs=["plan.json", "architect_report.json"],
                    outputs=["impl_report.json", "patch.diff"],
                    scope=scope,
                ),
                WorkItem(
                    id="WI-3",
                    owner="tester",
                    goal="执行测试与补齐关键回归建议",
                    inputs=["impl_report.json", "AGENTS.md"],
                    outputs=["test_report.json", "logs/*"],
                ),
                WorkItem(
                    id="WI-4",
                    owner="reviewer",
                    goal="按 rubric 审查并给出 PASS 或 FAIL",
                    inputs=["impl_report.json", "test_report.json", "gate_report.json"],
                    outputs=["review.json"],
                ),
                WorkItem(
                    id="WI-5",
                    owner="summarizer",
                    goal="打包交付物并生成老板可读结果",
                    inputs=["review.json", "gate_report.json", "impl_report.json"],
                    outputs=["deliver.json", "DELIVER.md"],
                ),
            ],
            risk_notes=[
                RiskNote(
                    risk="Windows 原生环境下的 Codex 自动化可能遇到沙箱或审批限制",
                    mitigation="优先在 WSL 工作区运行，或将 job 退化为 dry-run",
                ),
                RiskNote(
                    risk="项目未初始化为 Git 仓库时，diff-scope 与 worktree 隔离会退化",
                    mitigation="初始化 Git 后再启用真实 worktree；否则使用副本目录",
                ),
            ],
            commands=commands,
        )

    def _dry_architect_report(self, plan: Plan) -> ArchitectReport:
        return ArchitectReport(
            approach=[
                "方案 A：使用 Agents SDK + Codex MCP 按角色执行。",
                "方案 B：当前环境缺少运行前提时退化为 dry-run，只生成完整工件骨架。",
            ],
            touched_files=[
                "orchestrator/hive/controller.py",
                "orchestrator/hive/gates.py",
                "apps/api/main.py",
                "apps/web/app/page.tsx",
            ],
            edge_cases=[
                "无 Git 仓库时 worktree 退化为目录副本。",
                "缺少 OPENAI_API_KEY 时自动降级为 dry-run。",
                "AGENTS.md 未定义命令时 gates 以 skipped 记录。",
            ],
            risks=[note.risk for note in plan.risk_notes],
            references=[],
        )

    @staticmethod
    def _dry_impl_report() -> ImplementationReport:
        return ImplementationReport(
            changed_files=[],
            key_diff_summary=[
                "Dry-run mode generated pipeline artifacts but did not ask Codex to edit source code.",
            ],
            commands_ran=[],
            notes_for_tester=[
                "Install dependencies and rerun in auto mode to exercise live Codex execution.",
            ],
            rollback="Delete the generated run directory to discard the dry-run artifact set.",
        )

    @staticmethod
    def _dry_test_report(run_dir: Path) -> TestReport:
        return TestReport(
            test_commands=[
                TestCommandResult(
                    cmd="dry-run",
                    exit_code=0,
                    summary="No live test command executed in dry-run mode",
                    log_path=str(run_dir / "logs" / "test.log"),
                )
            ],
            coverage_notes=["Coverage not measured in dry-run mode."],
            failures=[],
            proposed_tests=[
                ProposedTest(
                    file="apps/api/main.py",
                    case="POST /jobs returns a delivery package",
                    purpose="Validate the boss-mode API contract.",
                )
            ],
        )

    @staticmethod
    def _dry_gate_report(runtime_notes: list[str], run_dir: Path) -> GateReport:
        summary = runtime_notes[0] if runtime_notes else "Live runtime disabled"
        return GateReport(
            overall_pass=False,
            checks=[
                GateCheck(
                    gate="runtime",
                    status="failed",
                    summary=summary,
                    log_path=str(run_dir / "events.ndjson"),
                )
            ],
        )

    @staticmethod
    def _dry_review_report(runtime_notes: list[str]) -> ReviewReport:
        evidence = runtime_notes[0] if runtime_notes else "No live runtime prerequisites"
        return ReviewReport(
            decision="FAIL",
            blockers=[
                ReviewBlocker(
                    id="B-1",
                    description="Live Codex execution did not run",
                    evidence=evidence,
                    fix_guidance="Install openai-agents, set OPENAI_API_KEY, and rerun with mode=auto.",
                )
            ],
            rubric_scores=RubricScores(
                correctness=1,
                tests=1,
                security=3,
                maintainability=3,
                scope=5,
                docs=4,
            ),
            regression_risks=["No repository change was validated against real tests."],
            required_followups=["Rerun in auto mode after configuring Codex MCP and API credentials."],
        )

    @staticmethod
    def _write_dry_run_logs(run_dir: Path, runtime_notes: list[str]) -> None:
        logs_dir = run_dir / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        summary = runtime_notes[0] if runtime_notes else "Live runtime disabled"
        (logs_dir / "test.log").write_text(f"dry-run: {summary}\n", encoding="utf-8")

    @staticmethod
    def _dry_delivery(
        plan: Plan,
        impl_report: ImplementationReport,
        gate_report: GateReport,
        review_report: ReviewReport,
        run_dir: Path,
    ) -> Deliverable:
        return Deliverable(
            task_id=plan.task_id,
            outcome=Outcome.NEEDS_HUMAN,
            summary="Pipeline scaffold is ready, but live multi-agent execution requires environment setup.",
            changed_files=impl_report.changed_files,
            verification=[
                VerificationStep(
                    name="Runtime prerequisites",
                    command="pip install -e . && set OPENAI_API_KEY=... && codex mcp-server",
                    result="manual action required",
                    log_path=str(run_dir / "events.ndjson"),
                )
            ],
            gate_report_path=str(run_dir / "gate_report.json"),
            reviewer_decision=review_report.decision,
            reviewer_blocker_count=len(review_report.blockers),
            risks=["Live execution, testing, and review were not performed in dry-run mode."],
            rollback="Remove the generated run directory and re-run after setup.",
            remaining_gaps=review_report.required_followups,
            artifacts=[
                DeliveryArtifact(name="plan", path=str(run_dir / "plan.json")),
                DeliveryArtifact(name="implementation", path=str(run_dir / "impl_report.json")),
                DeliveryArtifact(name="tests", path=str(run_dir / "test_report.json")),
                DeliveryArtifact(name="review", path=str(run_dir / "review.json")),
                DeliveryArtifact(name="gates", path=str(run_dir / "gate_report.json")),
                DeliveryArtifact(name="delivery", path=str(run_dir / "deliver.json")),
            ],
        )

    @staticmethod
    def _render_delivery_markdown(delivery: Deliverable) -> str:
        lines = [
            f"# Delivery Package: {delivery.task_id}",
            "",
            f"- Outcome: {delivery.outcome.value}",
            f"- Summary: {delivery.summary}",
            f"- Reviewer: {delivery.reviewer_decision} ({delivery.reviewer_blocker_count} blockers)",
            f"- Gate report: {delivery.gate_report_path}",
            "",
            "## Verification",
        ]
        for step in delivery.verification:
            lines.append(f"- {step.name}: `{step.command}` -> {step.result}")
        lines.extend(["", "## Risks"])
        for risk in delivery.risks:
            lines.append(f"- {risk}")
        lines.extend(["", "## Rollback", f"- {delivery.rollback}", "", "## Artifacts"])
        for artifact in delivery.artifacts:
            lines.append(f"- {artifact.name}: {artifact.path}")
        if delivery.remaining_gaps:
            lines.extend(["", "## Remaining Gaps"])
            for gap in delivery.remaining_gaps:
                lines.append(f"- {gap}")
        return "\n".join(lines) + "\n"

    @staticmethod
    def _hash_prompt(prompt: str) -> str:
        return hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:12]

    @staticmethod
    def _map_outcome_to_status(outcome: Outcome) -> JobStatus:
        if outcome == Outcome.PASS:
            return JobStatus.PASS
        if outcome == Outcome.NEEDS_HUMAN:
            return JobStatus.NEEDS_HUMAN
        return JobStatus.FAIL
