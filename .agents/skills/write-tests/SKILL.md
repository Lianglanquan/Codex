---
name: write-tests
description: Add or adjust stable unit and regression tests for a targeted change. Use when Codex must cover new behavior, reproduce a bug, improve confidence on a risky diff, or report structured test evidence.
---

# Write Tests

Read `AGENTS.md`, the relevant implementation report, and nearby existing tests before writing anything.

## Workflow

1. Detect the existing test framework, directory layout, naming rules, and assertion style.
2. Design at least these test categories when applicable:
   - happy path
   - boundary values
   - invalid input or exception path
   - critical branch coverage
   - concurrency or timing behavior
   - regression case for the requested change
3. Implement the minimum stable tests needed to protect the change.
4. Run the repository test command from `AGENTS.md`. If it is missing, stop and report the gap.
5. Return structured evidence for commands, failures, and proposed follow-up tests.

## Required Output

Return JSON with these fields:

- `test_commands`
- `coverage_notes`
- `failures`
- `proposed_tests`

## Rules

- Do not modify production implementation files unless the task explicitly authorizes it.
- Avoid flaky timing assumptions and unnecessary snapshots.
- If a test cannot be made stable, explain why instead of hiding the instability.

