"""
Stage 5: 压力测试 — 风险管理者试图摧毁 Alpha 论点（含因子风险分解视角）
"""
from llm import call_llm, STRESS_TEST_SYSTEM, STRESS_TEST_PROMPT
from data.barra import factor_risk_decomposition, factor_exposure_text


def run_stress_test(
    alpha_thesis: str, data_text: str, model: str | None = None
) -> str:
    """Stage 5: 对 Alpha 论点进行毁灭性压力测试"""

    # 从 data_text 所属的 data 中提取 Barra 因子数据
    # 注: factor_risk_decomposition 需要 factors dict，这里构建一个从 data 提取的版本
    # 实际调用时 factors 已在 data["_barra_factors"] 中

    prompt = STRESS_TEST_PROMPT.format(
        alpha_thesis=alpha_thesis,
        data_context=data_text,
    )

    return call_llm(
        system_prompt=STRESS_TEST_SYSTEM,
        user_prompt=prompt,
        model=model,
        temperature=0.4,
    )


def run_stress_test_with_barra(
    alpha_thesis: str,
    data_text: str,
    barra_factors: dict,
    model: str | None = None,
) -> str:
    """Stage 5 增强版: 含因子风险分解的压力测试"""

    # 因子风险分解
    risk_decomp = factor_risk_decomposition(barra_factors)
    factor_summary = factor_exposure_text(barra_factors)

    # 构建因子风险段
    factor_risk_text = _format_factor_risk_section(risk_decomp, factor_summary)

    prompt = STRESS_TEST_PROMPT.format(
        alpha_thesis=alpha_thesis,
        data_context=data_text,
    )

    # 在 prompt 末尾注入因子风险分解
    enhanced_prompt = prompt + factor_risk_text

    return call_llm(
        system_prompt=STRESS_TEST_SYSTEM,
        user_prompt=enhanced_prompt,
        model=model,
        temperature=0.4,
    )


def _format_factor_risk_section(risk_decomp: dict, factor_summary: str) -> str:
    """格式化因子风险分解追加到压力测试 prompt"""
    lines = [
        "",
        "---",
        "## 补充数据: Barra 因子风险分解",
        "",
        f"总波动率: {risk_decomp.get('total_volatility_pct', 'N/A')}%",
        f"Beta: {risk_decomp.get('beta', 'N/A')}",
        f"系统性风险占比: {risk_decomp.get('systematic_risk_share_pct', 'N/A')}%",
        f"特质风险占比: {risk_decomp.get('idiosyncratic_risk_share_pct', 'N/A')}%",
        f"解读: {risk_decomp.get('interpretation', 'N/A')}",
    ]

    if risk_decomp.get("factor_concentration"):
        fc = risk_decomp["factor_concentration"]
        lines.append(f"\n因子集中度风险: {fc.get('risk_implication', '')}")
        for df in fc.get("dominant_factors", []):
            lines.append(f"  - {df['factor']}: {df['tilt']} (强度 {df['strength']})")

    if risk_decomp.get("crowding_warnings"):
        lines.append("\n因子拥挤警示:")
        for w in risk_decomp["crowding_warnings"]:
            lines.append(f"  - {w}")

    lines.append("")
    lines.append("请在压力测试中额外考虑以上因子风险分解，包括:")
    lines.append("1. 因子的系统性风险在何种宏观情景下会集中释放？")
    lines.append("2. 因子拥挤度是否构成了隐藏风险（即使基本面判断正确，因子轮动也可能造成亏损）？")
    lines.append("3. 该股票的特质风险占比是否足够高，使得基本面分析的价值不会被系统性风险淹没？")

    return "\n".join(lines)
