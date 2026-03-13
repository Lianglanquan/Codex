---
name: implement-minimal-change
description: Implement the smallest correct code change inside an approved scope. Use when Codex has a plan, an allowed file set, and needs to edit code without refactoring unrelated areas or adding dependencies.
---

# Implement Minimal Change

Read `AGENTS.md`, `plan.json`, and any architect notes before editing files.

## Workflow

1. Confirm the allowed files, file-count limit, and dependency policy.
2. Change the minimum number of files needed to satisfy the acceptance criteria.
3. Avoid mass formatting, opportunistic refactors, and cleanup that is unrelated to the task.
4. Run targeted validation when it is cheap and safe.
5. Emit a structured implementation report immediately after editing.

## Required Output

Return JSON with these fields:

- `changed_files`
- `key_diff_summary`
- `commands_ran`
- `notes_for_tester`
- `rollback`

## Rules

- Stop and report if the task cannot be completed inside scope.
- Do not modify `.agents/` or `.codex/` unless the task explicitly targets those paths.
- Prefer fewer changed lines over cleaner rewrites.
