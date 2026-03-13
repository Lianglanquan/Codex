---
name: prepare-delivery
description: Assemble the final owner-facing delivery package from plan, implementation, test, gate, and review artifacts. Use when Codex needs to produce `deliver.json` and `DELIVER.md` with verification, risks, rollback, and remaining gaps.
---

# Prepare Delivery

Read the run artifacts and summarize facts only.

## Workflow

1. Load `plan.json`, `impl_report.json`, `test_report.json`, `gate_report.json`, and `review.json`.
2. Build a delivery summary that a non-technical owner can understand in under one minute.
3. Cite verification commands and log paths instead of paraphrasing them vaguely.
4. Include rollback, remaining gaps, and any scope expansion.
5. Write both `deliver.json` and `DELIVER.md`.

## Required Output

Return JSON with these fields:

- `task_id`
- `outcome`
- `summary`
- `changed_files`
- `verification`
- `gate_report_path`
- `reviewer_decision`
- `reviewer_blocker_count`
- `risks`
- `rollback`
- `remaining_gaps`
- `artifacts`

## Rules

- Never invent test results, file paths, or review decisions.
- If the run is incomplete, mark the outcome as `NEEDS_HUMAN`.
- Keep the summary concrete: changed surface, proof, risk, rollback.

