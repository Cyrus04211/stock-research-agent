"""
Stage 2: 共识诊断 — 反向解构市场在定价什么故事
"""
from llm import call_llm, CONSENSUS_DIAGNOSIS_SYSTEM, CONSENSUS_DIAGNOSIS_PROMPT
from data.resolver import resolve_key_metrics, facts_summary_for_prompt


def run_consensus_diagnosis(data: dict, data_text: str, model: str | None = None) -> str:
    """Stage 2: 诊断市场共识"""
    metrics = data.get("key_metrics") or resolve_key_metrics(data)
    facts = facts_summary_for_prompt(data)

    def _fmt(val, suffix=""):
        if val is None:
            return "数据不可用"
        return f"{val}{suffix}"

    prompt = CONSENSUS_DIAGNOSIS_PROMPT.format(
        symbol=data.get("symbol", ""),
        facts_summary=facts,
        current_price=_fmt(metrics.get("current_price")),
        pe=_fmt(metrics.get("pe_trailing")),
        pb=_fmt(metrics.get("pb")),
        data_context=data_text,
    )

    return call_llm(
        system_prompt=CONSENSUS_DIAGNOSIS_SYSTEM,
        user_prompt=prompt,
        model=model,
        temperature=0.5,
    )
