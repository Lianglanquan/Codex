from __future__ import annotations


def compose_boss_prompt(
    *,
    goal: str,
    background: str | None = None,
    offload: str | None = None,
    deliverable: str | None = None,
) -> str:
    sections = [f"目标：{goal.strip()}"]
    if background and background.strip():
        sections.append(f"背景：{background.strip()}")
    if offload and offload.strip():
        sections.append(f"老板不想亲自处理：{offload.strip()}")
    if deliverable and deliverable.strip():
        sections.append(f"希望最终只看到：{deliverable.strip()}")
    return "\n".join(sections)
