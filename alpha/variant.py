"""
Stage 3: 变体认知搜索 — 魔鬼代言人寻找共识裂缝
"""
from llm import call_llm, VARIANT_PERCEPTION_SYSTEM, VARIANT_PERCEPTION_PROMPT


def run_variant_perception(
    consensus_map: str, data_text: str, model: str | None = None
) -> str:
    """Stage 3: 挑战共识，寻找认知偏差"""

    prompt = VARIANT_PERCEPTION_PROMPT.format(
        consensus_map=consensus_map,
        data_context=data_text,
    )

    return call_llm(
        system_prompt=VARIANT_PERCEPTION_SYSTEM,
        user_prompt=prompt,
        model=model,
        temperature=0.7,  # 更高温度鼓励创造性反证
    )
