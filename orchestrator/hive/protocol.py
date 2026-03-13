from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class JobMode(str, Enum):
    AUTO = "auto"
    DRY_RUN = "dry-run"


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PASS = "pass"
    NEEDS_HUMAN = "needs_human"
    FAIL = "fail"


class Outcome(str, Enum):
    PASS = "PASS"
    NEEDS_HUMAN = "NEEDS_HUMAN"
    FAIL = "FAIL"


class ScopeConstraint(BaseModel):
    max_files: int = 8
    allow_globs: list[str] = Field(
        default_factory=lambda: [
            "src/**",
            "tests/**",
            "orchestrator/**",
            "apps/**",
            ".codex/**",
            ".agents/**",
            "README.md",
            "AGENTS.md",
            "reviewer_rubric.md",
            "pyproject.toml",
        ]
    )
    max_added_lines: int = 800
    max_deleted_lines: int = 400
    no_new_deps: bool = True
    no_mass_format: bool = True


class WorkItem(BaseModel):
    id: str
    owner: Literal["manager", "architect", "executor", "tester", "reviewer", "summarizer"]
    goal: str
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    scope: ScopeConstraint | None = None


class RiskNote(BaseModel):
    risk: str
    mitigation: str


class Plan(BaseModel):
    task_id: str
    summary: str
    acceptance: list[str]
    work_items: list[WorkItem]
    risk_notes: list[RiskNote]
    commands: dict[str, str] = Field(default_factory=dict)


class Reference(BaseModel):
    title: str
    url_or_citation: str
    why_it_matters: str


class ArchitectReport(BaseModel):
    approach: list[str]
    touched_files: list[str]
    edge_cases: list[str]
    risks: list[str]
    references: list[Reference] = Field(default_factory=list)


class ChangedFile(BaseModel):
    path: str
    reason: str


class CommandRun(BaseModel):
    cmd: str
    result: str


class ImplementationReport(BaseModel):
    changed_files: list[ChangedFile]
    key_diff_summary: list[str]
    commands_ran: list[CommandRun]
    notes_for_tester: list[str]
    rollback: str


class TestCommandResult(BaseModel):
    cmd: str
    exit_code: int
    summary: str
    log_path: str


class TestFailure(BaseModel):
    symptom: str
    likely_root_cause: str
    suggested_fix: str


class ProposedTest(BaseModel):
    file: str
    case: str
    purpose: str


class TestReport(BaseModel):
    test_commands: list[TestCommandResult]
    coverage_notes: list[str]
    failures: list[TestFailure]
    proposed_tests: list[ProposedTest]


class ReviewBlocker(BaseModel):
    id: str
    description: str
    evidence: str
    fix_guidance: str


class RubricScores(BaseModel):
    correctness: int = Field(ge=0, le=5)
    tests: int = Field(ge=0, le=5)
    security: int = Field(ge=0, le=5)
    maintainability: int = Field(ge=0, le=5)
    scope: int = Field(ge=0, le=5)
    docs: int = Field(ge=0, le=5)


class ReviewReport(BaseModel):
    decision: Literal["PASS", "FAIL"]
    blockers: list[ReviewBlocker]
    rubric_scores: RubricScores
    regression_risks: list[str]
    required_followups: list[str]


class GateCheck(BaseModel):
    gate: str
    status: Literal["passed", "failed", "skipped"]
    summary: str
    exit_code: int | None = None
    log_path: str | None = None


class DiffStats(BaseModel):
    changed_files: list[str] = Field(default_factory=list)
    added_lines: int = 0
    deleted_lines: int = 0


class GateReport(BaseModel):
    overall_pass: bool
    checks: list[GateCheck]
    diff_stats: DiffStats = Field(default_factory=DiffStats)


class VerificationStep(BaseModel):
    name: str
    command: str
    result: str
    log_path: str | None = None


class DeliveryArtifact(BaseModel):
    name: str
    path: str


class Deliverable(BaseModel):
    task_id: str
    outcome: Outcome
    summary: str
    changed_files: list[ChangedFile]
    verification: list[VerificationStep]
    gate_report_path: str
    reviewer_decision: str
    reviewer_blocker_count: int
    risks: list[str]
    rollback: str
    remaining_gaps: list[str]
    artifacts: list[DeliveryArtifact]
    scope_expanded: bool = False


class ArtifactPaths(BaseModel):
    run_dir: str
    job: str
    plan: str
    architect: str | None = None
    implementation: str | None = None
    tests: str | None = None
    review: str | None = None
    gates: str | None = None
    delivery: str | None = None
    patch: str | None = None
    events: str | None = None


class JobRequest(BaseModel):
    boss_prompt: str
    repo_path: str
    acceptance: list[str] = Field(default_factory=list)
    mode: JobMode = JobMode.AUTO
    owner_profile: str | None = None


class JobRecord(BaseModel):
    job_id: str
    boss_prompt: str
    repo_path: str
    status: JobStatus
    mode: JobMode
    created_at: str
    updated_at: str
    acceptance: list[str]
    runtime_notes: list[str] = Field(default_factory=list)
    artifacts: ArtifactPaths
    delivery: Deliverable | None = None
