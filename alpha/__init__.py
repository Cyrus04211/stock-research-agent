"""
Alpha 分析引擎 — 6 阶段对抗式推理

流程: Barra 因子定位 -> 共识诊断 -> 变体认知 -> Alpha 论点（双向） -> 压力测试(含因子风险分解) -> 投资决策合成
每个后续阶段都可以引用和挑战前序阶段的结论。
"""
from rich.console import Console
from alpha.factor_analysis import run_barra_factor_analysis
from alpha.consensus import run_consensus_diagnosis
from alpha.variant import run_variant_perception
from alpha.thesis import run_alpha_thesis
from alpha.stress_test import run_stress_test_with_barra as run_stress_test
from alpha.bet_sizing import run_investment_decision

console = Console()


def run_alpha_pipeline(
    data: dict,
    data_text: str,
    model: str | None = None,
    verbose: bool = True,
) -> dict:
    """
    执行完整的 6 阶段 Alpha 推理管线。
    返回各阶段的输出 dict。
    """
    symbol = data.get("symbol", "Unknown")
    results = {"symbol": symbol}

    # Stage 1: Barra 因子定位
    if verbose:
        console.print("\n[bold cyan]Stage 1/6: Barra 因子定位 — 量化风格暴露分析[/bold cyan]")
    try:
        factor_positioning = run_barra_factor_analysis(data, data_text, model)
        results["factor_positioning"] = factor_positioning
        if verbose:
            console.print("  [green]OK[/green] 因子定位报告已生成")
    except Exception as e:
        results["factor_positioning"] = f"[错误] {e}"
        if verbose:
            console.print(f"  [red]FAIL[/red] 因子定位分析失败: {e}")

    # Stage 2: 共识诊断
    if verbose:
        console.print("\n[bold yellow]Stage 2/6: 共识诊断 — 市场在定价什么？[/bold yellow]")
    try:
        consensus_map = run_consensus_diagnosis(data, data_text, model)
        results["consensus_map"] = consensus_map
        if verbose:
            console.print("  [green]OK[/green] 共识地图已生成")
    except Exception as e:
        results["consensus_map"] = f"[错误] {e}"
        if verbose:
            console.print(f"  [red]FAIL[/red] 共识诊断失败: {e}")

    # Stage 3: 变体认知
    if verbose:
        console.print("\n[bold yellow]Stage 3/6: 变体认知 — 寻找共识裂缝[/bold yellow]")
    try:
        variant_perception = run_variant_perception(
            results["consensus_map"], data_text, model
        )
        results["variant_perception"] = variant_perception
        if verbose:
            console.print("  [green]OK[/green] 认知偏差清单已生成")
    except Exception as e:
        results["variant_perception"] = f"[错误] {e}"
        if verbose:
            console.print(f"  [red]FAIL[/red] 变体认知失败: {e}")

    # Stage 4: Alpha 论点
    if verbose:
        console.print("\n[bold yellow]Stage 4/6: Alpha 论点 — 构建非共识判断[/bold yellow]")
    try:
        alpha_thesis = run_alpha_thesis(
            results["consensus_map"],
            results["variant_perception"],
            data_text,
            model,
        )
        results["alpha_thesis"] = alpha_thesis
        if verbose:
            console.print("  [green]OK[/green] Alpha 论点已构建")
    except Exception as e:
        results["alpha_thesis"] = f"[错误] {e}"
        if verbose:
            console.print(f"  [red]FAIL[/red] Alpha 论点构建失败: {e}")

    # Stage 5: 压力测试（含因子风险分解视角）
    if verbose:
        console.print("\n[bold yellow]Stage 5/6: 压力测试 — 检验 Alpha 论点（含因子风险分解）[/bold yellow]")
    try:
        stress_test = run_stress_test(
            results["alpha_thesis"],
            data_text,
            barra_factors=data.get("_barra_factors", {}),
            model=model,
        )
        results["stress_test"] = stress_test
        if verbose:
            console.print("  [green]OK[/green] 风险地图已生成（含因子分解）")
    except Exception as e:
        results["stress_test"] = f"[错误] {e}"
        if verbose:
            console.print(f"  [red]FAIL[/red] 压力测试失败: {e}")

    # Stage 6: 投资决策
    if verbose:
        console.print("\n[bold yellow]Stage 6/6: 投资决策 — 综合判断[/bold yellow]")
    try:
        investment_decision = run_investment_decision(
            results["alpha_thesis"],
            results["stress_test"],
            results["consensus_map"],
            data_text,
            model,
        )
        results["investment_decision"] = investment_decision
        if verbose:
            console.print("  [green]OK[/green] 投资决策书已生成")
    except Exception as e:
        results["investment_decision"] = f"[错误] {e}"
        if verbose:
            console.print(f"  [red]FAIL[/red] 投资决策失败: {e}")

    return results
