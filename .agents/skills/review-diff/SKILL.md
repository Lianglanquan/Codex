---
name: review-diff
description: Review a diff, test evidence, and gate results against the repository rubric. Use when Codex must return a structured PASS or FAIL decision with blockers, scores, and follow-up work instead of style commentary.
---

# Review Diff

Read `reviewer_rubric.md`, `gate_report.json`, `impl_report.json`, `test_report.json`, and the patch summary before deciding.

## Workflow

1. Check blocking conditions first: failed tests, failed lint or typecheck, scope violations, dependency violations, and leaked secrets.
2. Review correctness, tests, security, maintainability, scope, and delivery evidence.
3. Convert each real issue into a blocker with concrete evidence and a fix path.
4. Return a binary decision. Do not soften blockers into suggestions.

## Required Output

Return JSON with these fields:

- `decision`
- `blockers`
- `rubric_scores`
- `regression_risks`
- `required_followups`

## Rules

- Base every blocker on evidence, not preference.
- Do not block on naming or style unless it causes a concrete maintenance or correctness problem.
- If every blocking condition is cleared, return `PASS`.

