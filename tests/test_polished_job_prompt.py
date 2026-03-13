from __future__ import annotations

from apps.polished_job_prompt import compose_boss_prompt


def test_compose_boss_prompt_joins_non_empty_sections() -> None:
    prompt = compose_boss_prompt(
        goal="修一个问题",
        background="这是背景",
        offload="不要让我盯过程",
        deliverable="只给我结论",
    )

    assert prompt == "\n".join(
        [
            "目标：修一个问题",
            "背景：这是背景",
            "老板不想亲自处理：不要让我盯过程",
            "希望最终只看到：只给我结论",
        ]
    )


def test_compose_boss_prompt_skips_blank_sections() -> None:
    prompt = compose_boss_prompt(
        goal="修一个问题",
        background="  ",
        offload="",
        deliverable=None,
    )

    assert prompt == "目标：修一个问题"
