"""
Stage 4: Alpha 论点构建 — 从共识裂缝中提炼可执行的非共识判断
"""
from llm import call_llm, ALPHA_THESIS_SYSTEM, ALPHA_THESIS_PROMPT


def run_alpha_thesis(
    consensus_map: str,
    variant_perception: str,
    data_text: str,
    model: str | None = None,
) -> str:
    """Stage 4: 构建 Alpha 论点"""

    prompt = ALPHA_THESIS_PROMPT.format(
        consensus_map=consensus_map,
        variant_perception=variant_perception,
        data_context=data_text,
    )

    return call_llm(
        system_prompt=ALPHA_THESIS_SYSTEM,
        user_prompt=prompt,
        model=model,
        temperature=0.5,
    )
