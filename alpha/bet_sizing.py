"""
Stage 6: 投资决策合成 — 投委会主席综合所有分析，做出最终投资判断
"""
from llm import call_llm, INVESTMENT_DECISION_SYSTEM, INVESTMENT_DECISION_PROMPT


def run_investment_decision(
    alpha_thesis: str,
    stress_test: str,
    consensus_map: str,
    data_text: str,
    model: str | None = None,
) -> str:
    """Stage 6: 综合 Alpha 论点 + 风险检验 + 基本面，做出投资决策"""

    prompt = INVESTMENT_DECISION_PROMPT.format(
        alpha_thesis=alpha_thesis,
        stress_test=stress_test,
        consensus_map=consensus_map,
        data_context=data_text,
    )

    return call_llm(
        system_prompt=INVESTMENT_DECISION_SYSTEM,
        user_prompt=prompt,
        model=model,
        temperature=0.4,
    )
