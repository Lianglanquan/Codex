from __future__ import annotations

import json
from textwrap import dedent

from .protocol import (
    ArchitectReport,
    Deliverable,
    GateReport,
    ImplementationReport,
    JobRequest,
    Plan,
    ReviewReport,
    TestReport,
)

def _owner_profile_block(job: JobRequest) -> str:
    if not job.owner_profile:
        return ""
    return f"Owner profile and working preferences:\n{job.owner_profile}\n\n"


ARCHITECT_INSTRUCTIONS = dedent(
    """
    You are the architect and researcher. Analyze the repository and propose the smallest practical approach.
    You must:
    - Point to concrete files, symbols, and call chains where possible.
    - Summarize external guidance only when it changes the implementation decision.
    - This is a personal boss cockpit, not a generic platform. Optimize for reducing owner attention.
    - Return JSON only.
    - Never edit files.
    """
).strip()


EXECUTOR_INSTRUCTIONS = dedent(
    """
    You are the implementation agent. Your only objective is to make the minimum necessary code change.
    You must:
    - Work only in the assigned worktree.
    - Avoid unrelated refactors and mass formatting.
    - Avoid adding new production dependencies unless explicitly allowed.
    - Return JSON only.
    """
).strip()


TESTER_INSTRUCTIONS = dedent(
    """
    You are the test engineer. You verify, localize failures, and propose or add the minimum required tests.
    You must:
    - Run the commands defined in AGENTS.md when available.
    - Focus on evidence, not opinions.
    - Do not modify production implementation files.
    - Return JSON only.
    """
).strip()


REVIEWER_INSTRUCTIONS = dedent(
    """
    You are the reviewer with veto power.
    Rules:
    - Base your decision on evidence: diff summary, logs, tests, and gate results.
    - If any blocking item remains, return FAIL.
    - Do not suggest style-only changes as blockers.
    - Return JSON only.
    """
).strip()


SUMMARIZER_INSTRUCTIONS = dedent(
    """
    You are the delivery packager. Summarize facts only.
    You must:
    - Cite the gate report and log paths as evidence.
    - Produce the final delivery package in strict JSON.
    - Include validation steps, risk, rollback, and remaining gaps.
    """
).strip()


def build_architect_prompt(job: JobRequest, plan: Plan, run_dir: str, exec_cwd: str) -> str:
    return dedent(
        f"""
        {_owner_profile_block(job)}Task ID: {plan.task_id}
        Boss objective: {job.boss_prompt}
        Acceptance criteria: {json.dumps(plan.acceptance, ensure_ascii=False)}
        Run directory: {run_dir}
        Execution worktree: {exec_cwd}

        Return only JSON with:
        - approach
        - touched_files
        - edge_cases
        - risks
        - references
        """
    ).strip()


def build_executor_prompt(
    job: JobRequest,
    plan: Plan,
    architect_report: ArchitectReport,
    exec_cwd: str,
) -> str:
    return dedent(
        f"""
        {_owner_profile_block(job)}Task ID: {plan.task_id}
        Objective: {job.boss_prompt}
        Acceptance criteria: {json.dumps(plan.acceptance, ensure_ascii=False)}
        Scope limits: {json.dumps(plan.work_items[1].scope.model_dump(), ensure_ascii=False)}
        Architect summary:
        - approach: {json.dumps(architect_report.approach, ensure_ascii=False)}
        - touched_files: {json.dumps(architect_report.touched_files, ensure_ascii=False)}
        - edge_cases: {json.dumps(architect_report.edge_cases, ensure_ascii=False)}
        Assigned cwd: {exec_cwd}

        Implement the smallest correct change and return only JSON with:
        - changed_files
        - key_diff_summary
        - commands_ran
        - notes_for_tester
        - rollback
        """
    ).strip()


def build_tester_prompt(
    job: JobRequest,
    plan: Plan,
    implementation_report: ImplementationReport,
    test_cwd: str,
    commands: dict[str, str],
) -> str:
    return dedent(
        f"""
        {_owner_profile_block(job)}Task ID: {plan.task_id}
        Objective: {job.boss_prompt}
        Acceptance criteria: {json.dumps(plan.acceptance, ensure_ascii=False)}
        Project commands: {json.dumps(commands, ensure_ascii=False)}
        Implementation summary:
        - changed_files: {implementation_report.model_dump_json(indent=2)}
        Assigned cwd: {test_cwd}

        Run validation and return only JSON with:
        - test_commands
        - coverage_notes
        - failures
        - proposed_tests
        """
    ).strip()


def build_reviewer_prompt(
    job: JobRequest,
    plan: Plan,
    implementation_report: ImplementationReport,
    test_report: TestReport,
    gate_report: GateReport,
) -> str:
    return dedent(
        f"""
        {_owner_profile_block(job)}Task ID: {plan.task_id}
        Objective: {job.boss_prompt}
        Acceptance criteria: {json.dumps(plan.acceptance, ensure_ascii=False)}
        Implementation report: {implementation_report.model_dump_json(indent=2)}
        Test report: {test_report.model_dump_json(indent=2)}
        Gate report: {gate_report.model_dump_json(indent=2)}

        Return only JSON with:
        - decision
        - blockers
        - rubric_scores
        - regression_risks
        - required_followups
        """
    ).strip()


def build_summarizer_prompt(
    job: JobRequest,
    plan: Plan,
    implementation_report: ImplementationReport,
    test_report: TestReport,
    gate_report: GateReport,
    review_report: ReviewReport,
    delivery_paths: dict[str, str],
) -> str:
    return dedent(
        f"""
        {_owner_profile_block(job)}Task ID: {plan.task_id}
        Objective: {job.boss_prompt}
        Acceptance criteria: {json.dumps(plan.acceptance, ensure_ascii=False)}
        Implementation report: {implementation_report.model_dump_json(indent=2)}
        Test report: {test_report.model_dump_json(indent=2)}
        Gate report: {gate_report.model_dump_json(indent=2)}
        Review report: {review_report.model_dump_json(indent=2)}
        Artifact paths: {json.dumps(delivery_paths, ensure_ascii=False)}

        Return only JSON with:
        - task_id
        - outcome
        - summary
        - changed_files
        - verification
        - gate_report_path
        - reviewer_decision
        - reviewer_blocker_count
        - risks
        - rollback
        - remaining_gaps
        - artifacts
        - scope_expanded
        """
    ).strip()
