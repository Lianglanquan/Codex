---
name: analyze-task
description: Break down a boss prompt into acceptance criteria, scope, impacted files, risks, and work items. Use when Codex needs to turn a feature request, bug report, or delivery request into a structured `plan.json` before implementation.
---

# Analyze Task

Read `AGENTS.md` and `reviewer_rubric.md` before proposing any plan.

## Workflow

1. Extract the request into explicit acceptance criteria, constraints, and non-goals.
2. Inspect the repository with fast read-only commands such as `rg --files` and `rg <symbol>`.
3. Map the likely impacted files and call paths. Prefer concrete paths over subsystem names.
4. Identify edge cases, regression risks, and any missing command or environment prerequisite.
5. Produce a plan that is small enough to review and strict enough to gate.

## Required Output

Return JSON with these fields:

- `summary`
- `acceptance`
- `work_items`
- `risk_notes`
- `commands`

## Rules

- Keep the executor scope narrow and explicit.
- If project commands are missing, record the gap instead of inventing commands.
- If the request implies a scope expansion, state it in the risk notes before implementation begins.

