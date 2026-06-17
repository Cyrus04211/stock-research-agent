"""
数据层 — 统一入口，并行拉取全维度数据
"""
import concurrent.futures
import json
from data.price import get_price_data, get_a_share_valuation, get_a_share_price, _detect_market
from data.financials import get_financials_yf, get_financials_a_share
from data.research import get_research
from data.news import get_news
from data.ownership import get_ownership
from data.peers import get_peers
from data.macro import get_macro
from data.expectations import get_expectations
from data.sentiment import get_sentiment
from data.resolver import enrich_data, facts_summary_for_prompt
from data.barra import compute_barra_factors
from rich.console import Console

console = Console()


def gather_all(symbol: str, verbose: bool = True) -> dict:
    """
    并行拉取所有维度的数据，返回聚合的 dict
    """
    market = _detect_market(symbol)
    market_name = {"a": "A股", "hk": "港股", "us": "美股"}.get(market, market)

    if verbose:
        console.print(f"\n[bold cyan]正在为 [yellow]{symbol}[/yellow] ({market_name}) 拉取全维度数据...[/bold cyan]\n")

    results = {
        "symbol": symbol,
        "market": market,
        "market_name": market_name,
    }

    tasks = {
        "行情估值": lambda: _fetch_price_bundle(symbol, market),
        "财务报表": lambda: _fetch_financials_bundle(symbol, market),
        "研报评级": lambda: get_research(symbol),
        "新闻公告": lambda: get_news(symbol),
        "股东持仓": lambda: get_ownership(symbol),
        "同业对比": lambda: get_peers(symbol),
        "宏观背景": lambda: get_macro(symbol),
        "预期差数据": lambda: get_expectations(symbol),
        "情绪极端信号": lambda: get_sentiment(symbol),
    }

    with concurrent.futures.ThreadPoolExecutor(max_workers=9) as executor:
        futures = {executor.submit(fn): name for name, fn in tasks.items()}
        for future in concurrent.futures.as_completed(futures):
            name = futures[future]
            try:
                data = future.result(timeout=30)
                results[name] = data
                status = "FAIL" if isinstance(data, dict) and data.get("error") else "OK"
                if verbose:
                    console.print(f"  [{status}] {name}")
            except Exception as e:
                results[name] = {"error": str(e)}
                if verbose:
                    console.print(f"  [FAIL] {name}: {e}")

    enrich_data(results)
    # 计算 Barra 风格因子暴露
    results["_barra_factors"] = compute_barra_factors(results)
    if verbose:
        q = results.get("data_quality", {})
        m = results.get("key_metrics", {})
        core = "就绪" if q.get("core_metrics_ready") else "不完整"
        console.print(
            f"\n[dim]核心指标: {core} | "
            f"价格={m.get('current_price')} [{m.get('current_price_source')}] | "
            f"PE={m.get('pe_trailing')} [{m.get('pe_source')}][/dim]"
        )
    return results


def _fetch_price_bundle(symbol: str, market: str) -> dict:
    result = {}
    result["yf"] = get_price_data(symbol)
    if market == "a":
        result["a_valuation"] = get_a_share_valuation(symbol)
        result["a_price"] = get_a_share_price(symbol)
    return result


def _fetch_financials_bundle(symbol: str, market: str) -> dict:
    result = {}
    result["yf"] = get_financials_yf(symbol)
    if market == "a":
        result["a_share"] = get_financials_a_share(symbol)
    return result


def data_to_text(data: dict) -> str:
    """将聚合数据转为 LLM 可读的文本"""
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


def data_for_prompt(data: dict) -> str:
    """为 LLM prompt 准备数据文本，限制长度避免超 token"""
    if "key_metrics" not in data:
        enrich_data(data)
    facts = facts_summary_for_prompt(data)
    text = data_to_text(data)
    combined = f"{facts}\n\n## 原始数据 JSON\n{text}"
    if len(combined) > 28000:
        combined = (
            f"{facts}\n\n## 原始数据 JSON\n{text[:24000]}"
            "\n...[数据过长已截断，核心指标见上方已验证事实]"
        )
    return combined
