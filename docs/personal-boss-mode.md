# Personal Boss Mode

This system is for one owner, not for a generic agent marketplace.

## Product objective

Turn mature multi-agent ideas into a personal operating system that removes the owner from repetitive coordination, chasing, checking, and packaging work.

The owner should mostly provide:

- the goal
- the context
- the parts they do not want to personally handle
- the format of the final answer

The system should absorb:

- task decomposition
- role assignment
- execution
- validation
- review and rework
- delivery packaging

## Borrowed principles

Keep these ideas:

- OpenAI Agents SDK: handoffs, guardrails, tracing
- Codex Skills and `AGENTS.md`: SOPs, rules, commands, forbidden zones
- AutoGen, CrewAI, MetaGPT: role-based collaboration and company-style division of labor
- LangGraph: explicit state flow instead of free-form group chat
- SWE-agent: real repository work, validation loops, evidence over vibes
- Anthropic agent guidance: fewer agents, clearer boundaries, structured artifacts

Do not copy these things:

- any framework's default UI
- any framework's full dependency worldview
- any framework's fixed company org chart
- any generic "build-your-own-agent-platform" product shape

## Design rules

1. Optimize for owner attention saved, not framework purity.
2. Let agents exchange artifacts, not long conversations.
3. Keep the number of roles small and sharp.
4. Make every pass or fail decision evidence-based.
5. Prefer one final delivery package over a pile of intermediate chatter.
6. Treat personal preferences as first-class input through `OWNER_PROFILE.md`.

