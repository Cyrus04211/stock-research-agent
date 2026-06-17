#!/usr/bin/env python3
"""
个股深度分析工具 — 基于 6 阶段对抗式推理（含 Barra 因子分析）

用法:
    python agent.py 600519          # A 股
    python agent.py AAPL            # 美股
    python agent.py 0700            # 港股
    python agent.py 600519 --json   # 仅输出聚合数据
    python agent.py 600519 --save   # 保存报告

流程:
    Barra 因子定位 -> 拉取全维度数据 -> 共识诊断 -> 变体认知 -> Alpha 论点（双向） -> 压力测试(含因子风险分解) -> 投资决策
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from config import check_config
from data import gather_all, data_for_prompt, data_to_text, _detect_market
from alpha import run_alpha_pipeline
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

console = Console()
OUTPUT_DIR = Path(__file__).parent / "output"


def parse_args():
    parser = argparse.ArgumentParser(description="个股深度分析工具")
    parser.add_argument("symbol", help="股票代码 (A股如600519, 美股如AAPL, 港股如0700)")
    parser.add_argument("--json", action="store_true", help="仅输出聚合数据 JSON，不调用 LLM")
    parser.add_argument("--save", action="store_true", help="将报告保存到 output/ 目录")
    parser.add_argument("--model", type=str, default=None, help="覆盖默认模型")
    return parser.parse_args()


def main():
    args = parse_args()
    symbol = args.symbol.upper().strip()
    market = _detect_market(symbol)

    console.print(Panel.fit(
        f"[bold white]个股深度分析[/bold white]\n"
        f"股票: [yellow]{symbol}[/yellow]  |  市场: {market.upper()}  |  "
        f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        f"[dim]6 阶段对抗式推理: Barra 因子定位 -> 共识诊断 -> 变体认知 -> Alpha 论点(双向) -> 压力测试(含因子风险分解) -> 投资决策[/dim]",
        border_style="cyan"
    ))

    # 检查配置
    if not args.json:
        ok = check_config()
        if not ok:
            console.print("\n[red]请先配置 DeepSeek API Key:[/red]")
            console.print("  方式 1: 创建 .env 文件，写入 DEEPSEEK_API_KEY=sk-xxx")
            console.print("  方式 2: export DEEPSEEK_API_KEY=sk-xxx")
            console.print("  方式 3: 使用 --json 模式仅输出数据\n")
            sys.exit(1)

    # 第一步: 拉取全维度数据（含 Barra 因子计算）
    data = gather_all(symbol, verbose=not args.json)

    if args.json:
        console.print_json(data_to_text(data))
        return

    data_text = data_for_prompt(data)

    # 第二步: 6 阶段 Alpha 推理管线
    console.print(f"\n[bold cyan]启动 6 阶段对抗式推理...[/bold cyan]")
    console.print("[dim]Stage 1 (Barra 因子定位) 用量化因子框架定位股票风格，后续 5 阶段对抗式推理彼此挑战[/dim]")

    try:
        pipeline_results = run_alpha_pipeline(
            data=data,
            data_text=data_text,
            model=args.model,
            verbose=True,
        )
    except Exception as e:
        console.print(f"[red]推理管线执行失败: {e}[/red]")
        sys.exit(1)

    # 第三步: 组装并输出报告
    report = _assemble_report(symbol, market, data, pipeline_results)

    console.print("\n" + "=" * 80)
    console.print(Markdown(report))
    console.print("=" * 80)

    # 保存
    if args.save:
        OUTPUT_DIR.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        filename = OUTPUT_DIR / f"{symbol}_{timestamp}.md"
        header = (
            f"# 个股深度分析 | {symbol}\n\n"
            f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"**分析方法**: 6 阶段对抗式推理（含 Barra 多因子分析）\n\n"
            f"---\n\n"
        )
        filename.write_text(header + report, encoding="utf-8")
        console.print(f"\n[green]报告已保存至: {filename}[/green]")

    console.print(
        f"\n[dim]免责声明: 本报告由 AI 通过对抗式推理生成，数据来自公开来源。"
        f"所有分析仅代表一种分析视角，不构成投资建议。投资有风险，决策需谨慎。[/dim]"
    )


def _assemble_report(
    symbol: str, market: str, data: dict, results: dict
) -> str:
    """组装最终报告（含 Barra 因子章节）"""
    from data.resolver import resolve_key_metrics, build_data_quality_report
    from data.barra import factor_exposure_text

    metrics = data.get("key_metrics") or resolve_key_metrics(data)
    quality = data.get("data_quality") or build_data_quality_report(data)
    market_name = {"a": "A股", "hk": "港股", "us": "美股"}.get(market, market)

    def _fmt(val, suffix=""):
        if val is None:
            return "数据不可用"
        return f"{val}{suffix}"

    sources_lines = _build_sources_appendix(data, metrics, quality)

    # Barra 因子暴露摘要（从数据中提取，不依赖 LLM）
    barra_factors = data.get("_barra_factors", {})
    factor_summary = factor_exposure_text(barra_factors) if barra_factors else "因子数据不可用"

    # 构建核心结论速览
    dashboard = _build_dashboard(metrics, barra_factors, results)

    report = f"""# 个股深度分析 | {symbol} | {market_name}

**分析时间**: {datetime.now().strftime('%Y-%m-%d %H:%M')}
**当前价格**: {_fmt(metrics.get('current_price'), ' 元')} [{metrics.get('current_price_source') or '--'}]
**PE(TTM)**: {_fmt(metrics.get('pe_trailing'), 'x')} [{metrics.get('pe_source') or '--'}]
**PB**: {_fmt(metrics.get('pb'), 'x')} [{metrics.get('pb_source') or '--'}]
**ROE**: {_fmt(metrics.get('roe'), '%')} [{metrics.get('roe_source') or '--'}]
**分析方法**: 6 阶段对抗式推理（含 Barra 多因子分析）

---

{dashboard}

---

## 一、Barra 风格因子定位

{results.get("factor_positioning", "[未生成]")}

---

## 二、市场共识诊断

{results.get("consensus_map", "[未生成]")}

---

## 三、认知偏差分析

{results.get("variant_perception", "[未生成]")}

---

## 四、投资论点（核心章节）

{results.get("alpha_thesis", "[未生成]")}

---

## 五、压力测试（含因子风险分解视角）

{results.get("stress_test", "[未生成]")}

---

## 六、投资决策

{results.get("investment_decision", "[未生成]")}

---

## 附录A：Barra 因子暴露原始数据

{factor_summary}

---

## 附录B：数据来源与数据质量

{sources_lines}

---

*免责声明: 本报告由 AI 通过对抗式推理自动生成，数据来自公开来源。不构成投资建议。*
*生成日期: {datetime.now().strftime('%Y-%m-%d')}*
"""
    return report


def _build_dashboard(metrics: dict, barra_factors: dict, results: dict) -> str:
    """构建核心结论速览表格"""
    import re

    lines = ["## 核心结论速览", ""]

    # 因子风格标签（从 Barra 数据提取，不依赖 LLM）
    summary = barra_factors.get("_summary", {}) if barra_factors else {}
    dominant = summary.get("dominant_tilts", [])
    if dominant:
        tags = [d["tilt"] for d in dominant[:4]]
        style_tag = " + ".join(tags)
    else:
        active = summary.get("active_tilts", [])
        if active:
            top = sorted(active, key=lambda x: x["strength"], reverse=True)[:3]
            tags = [t["tilt"] for t in top]
            style_tag = " + ".join(tags)
        else:
            style_tag = "因子数据不可用"

    # 因子集中风险
    dominant_factors = [d for d in dominant if d["strength"] >= 8]
    factor_risk = ""
    if dominant_factors:
        factor_risk = "、".join(d["tilt"] for d in dominant_factors[:2])
        factor_risk = f"因子集中风险: {factor_risk}"

    # 尝试从投资决策中解析评级
    decision_text = results.get("investment_decision", "")
    rating = "见投资决策章节"
    rating_match = re.search(r"评级[：:]\s*(.+?)(?:$|\n)", decision_text)
    if rating_match:
        raw = rating_match.group(1).strip()
        # 清理 markdown 加粗标记
        raw = raw.replace("**", "").strip()
        if len(raw) < 30:
            rating = raw

    # 尝试解析主导方向
    direction = ""
    thesis_text = results.get("alpha_thesis", "")
    dir_match = re.search(r"主导方向[：:]\s*(.+?)(?:$|\n)", thesis_text)
    if dir_match:
        direction = dir_match.group(1).strip().replace("**", "")
        if len(direction) > 20:
            direction = direction[:20]

    lines.append("| 维度 | 结论 |")
    lines.append("|------|------|")
    lines.append(f"| 因子风格 | {style_tag} |")
    if factor_risk:
        lines.append(f"| 因子风险 | {factor_risk} |")
    if direction:
        lines.append(f"| Alpha 方向 | {direction} |")
    lines.append(f"| 投资评级 | **{rating}** |")
    lines.append("")

    return "\n".join(lines)


def _build_sources_appendix(data: dict, metrics: dict, quality: dict) -> str:
    """生成数据来源附录"""
    lines = ["| 指标/模块 | 数值或状态 | 来源 |", "|---|---|---|"]
    lines.append(f"| 当前价 | {metrics.get('current_price', '--')} | {metrics.get('current_price_source', '--')} |")
    lines.append(f"| PE(TTM) | {metrics.get('pe_trailing', '--')} | {metrics.get('pe_source', '--')} |")
    lines.append(f"| PB | {metrics.get('pb', '--')} | {metrics.get('pb_source', '--')} |")
    lines.append(f"| ROE | {metrics.get('roe', '--')} | {metrics.get('roe_source', '--')} |")
    lines.append(f"| 一致预期 EPS | {metrics.get('eps_consensus', '--')} | {metrics.get('eps_consensus_source', '--')} |")
    lines.append(f"| 北向资金 | {metrics.get('northbound_net_flow', '--')} | {metrics.get('northbound_source', '--')} |")

    sections = quality.get("sections", {})
    for name, info in sections.items():
        status = info.get("status", "--")
        detail = info.get("detail", "")[:60]
        lines.append(f"| {name} | {status} | {detail} |")

    missing = quality.get("missing_core") or []
    if missing:
        lines.append(f"\n**缺失核心字段**: {', '.join(missing)}")

    research = data.get("研报评级", {})
    news = data.get("新闻公告", {})
    if isinstance(research, dict) and research.get("freshness"):
        f = research["freshness"]
        lines.append(
            f"\n**叙事时效**: 研报近7日 {f.get('fresh_count', 0)} 篇"
            f"（丢弃 {f.get('stale_dropped', 0)} 篇旧研报）"
        )
    if isinstance(news, dict) and news.get("freshness"):
        f = news["freshness"]
        lines.append(
            f"**叙事时效**: 新闻/公告近7日 {f.get('fresh_count', 0)} 条"
            f"（截止 {f.get('cutoff_date')}）"
        )

    return "\n".join(lines)


if __name__ == "__main__":
    main()
