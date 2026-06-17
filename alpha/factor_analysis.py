"""
Stage 1: Barra 因子定位分析 — 在因子空间中找到股票的风格位置
"""
from llm import call_llm, BARRA_FACTOR_SYSTEM, BARRA_FACTOR_PROMPT
from data.barra import compute_barra_factors, factor_exposure_text
from data.resolver import resolve_key_metrics, facts_summary_for_prompt


def run_barra_factor_analysis(data: dict, data_text: str, model: str | None = None) -> str:
    """Stage 1: 量化因子定位 + LLM 解读"""
    # 计算因子暴露
    factors = compute_barra_factors(data)
    factor_text = factor_exposure_text(factors)

    # 注入到 data 中供后续阶段使用
    data["_barra_factors"] = factors
    data["_barra_factor_text"] = factor_text

    metrics = data.get("key_metrics") or resolve_key_metrics(data)
    facts = facts_summary_for_prompt(data)

    prompt = BARRA_FACTOR_PROMPT.format(
        symbol=data.get("symbol", ""),
        facts_summary=facts,
        factor_exposure_text=factor_text,
        data_context=data_text,
    )

    return call_llm(
        system_prompt=BARRA_FACTOR_SYSTEM,
        user_prompt=prompt,
        model=model,
        temperature=0.4,
    )
