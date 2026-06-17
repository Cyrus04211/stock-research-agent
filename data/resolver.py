"""
数据解析与合并 — 从多数据源选取最可靠指标，并生成带来源标注的质量报告
"""
from __future__ import annotations

from data.utils import safe_float
from data.freshness import NARRATIVE_MAX_AGE_DAYS, narrative_cutoff_date


def _first_valid(*candidates: tuple[str, object]) -> tuple[object | None, str | None]:
    """按优先级返回第一个有效值及其来源"""
    for source, value in candidates:
        if value is None:
            continue
        if isinstance(value, str) and value in ("", "N/A", "nan", "None"):
            continue
        if isinstance(value, dict) and value.get("error"):
            continue
        return value, source
    return None, None


def resolve_key_metrics(data: dict) -> dict:
    """合并各数据源，生成带 source 字段的关键指标快照"""
    price_bundle = data.get("行情估值", {})
    yf_price = price_bundle.get("yf", {}) if isinstance(price_bundle.get("yf"), dict) else {}
    a_val = price_bundle.get("a_valuation", {}) if isinstance(price_bundle.get("a_valuation"), dict) else {}
    a_price = price_bundle.get("a_price", {}) if isinstance(price_bundle.get("a_price"), dict) else {}

    fin_bundle = data.get("财务报表", {})
    yf_fin = fin_bundle.get("yf", {}) if isinstance(fin_bundle.get("yf"), dict) else {}
    a_fin = fin_bundle.get("a_share", {}) if isinstance(fin_bundle.get("a_share"), dict) else {}
    a_ratios = a_fin.get("ratios", {}) if isinstance(a_fin.get("ratios"), dict) else {}
    yf_ratios = yf_fin.get("ratios", {}) if isinstance(yf_fin.get("ratios"), dict) else {}

    research = data.get("研报评级", {}) if isinstance(data.get("研报评级"), dict) else {}
    forecast = research.get("earnings_forecast", {}) if isinstance(research.get("earnings_forecast"), dict) else {}
    ownership = data.get("股东持仓", {}) if isinstance(data.get("股东持仓"), dict) else {}
    northbound = ownership.get("northbound", {}) if isinstance(ownership.get("northbound"), dict) else {}

    current_price, price_src = _first_valid(
        ("东方财富估值", a_val.get("current_price")),
        ("AKShare行情", a_price.get("current_price")),
        ("Yahoo Finance", yf_price.get("current_price")),
    )

    pe, pe_src = _first_valid(
        ("东方财富估值", a_val.get("pe_current")),
        ("Yahoo Finance", yf_price.get("pe_trailing")),
        ("研报一致预期", _research_pe(research)),
    )

    pb, pb_src = _first_valid(
        ("东方财富估值", a_val.get("pb_current")),
        ("Yahoo Finance", yf_price.get("pb")),
    )

    roe, roe_src = _first_valid(
        ("AKShare财务指标", a_ratios.get("roe")),
        ("Yahoo Finance", yf_ratios.get("roe")),
    )

    eps_2026 = None
    eps_keys = sorted(
        k for k in forecast
        if k.startswith("EPS_") and not k.endswith(("_min", "_max", "_analysts"))
    )
    if eps_keys:
        eps_2026 = safe_float(forecast.get(eps_keys[0]))

    implied_target = None
    if eps_2026 and pe:
        implied_target = round(eps_2026 * float(pe), 2)

    return {
        "current_price": safe_float(current_price),
        "current_price_source": price_src,
        "pe_trailing": safe_float(pe),
        "pe_source": pe_src,
        "pb": safe_float(pb),
        "pb_source": pb_src,
        "roe": safe_float(roe),
        "roe_source": roe_src,
        "market_cap": a_val.get("market_cap") or yf_price.get("market_cap"),
        "market_cap_source": "东方财富估值" if a_val.get("market_cap") else (
            "Yahoo Finance" if yf_price.get("market_cap") else None
        ),
        "eps_consensus": eps_2026,
        "eps_consensus_source": "东方财富研报中心" if eps_2026 else None,
        "implied_target_from_eps_pe": implied_target,
        "northbound_net_flow": northbound.get("net_flow"),
        "northbound_date": northbound.get("date"),
        "northbound_source": "东方财富北向持股" if northbound.get("net_flow") is not None else None,
        "report_date_financials": a_ratios.get("report_date"),
    }


def _research_pe(research: dict) -> float | None:
    forecast = research.get("earnings_forecast", {})
    if not isinstance(forecast, dict):
        return None
    for key, val in forecast.items():
        if key.startswith("PE_") and val is not None:
            return safe_float(val)
    recent = research.get("recent_reports", [])
    if recent and isinstance(recent[0], dict):
        for key, val in recent[0].items():
            if key.startswith("PE_"):
                return safe_float(val)
    return None


def build_data_quality_report(data: dict) -> dict:
    """汇总各模块拉取状态，供 LLM 与报告使用"""
    sections = {}
    ok_count = 0
    fail_count = 0

    for name, payload in data.items():
        if name in ("symbol", "market", "market_name", "key_metrics", "data_quality"):
            continue
        if not isinstance(payload, dict):
            continue

        status, detail = _section_status(payload)
        sections[name] = {"status": status, "detail": detail}
        if status == "ok":
            ok_count += 1
        elif status == "partial":
            ok_count += 1
            fail_count += 1
        else:
            fail_count += 1

    metrics = data.get("key_metrics", resolve_key_metrics(data))
    core_ready = all(
        metrics.get(k) is not None
        for k in ("current_price", "pe_trailing")
    )

    return {
        "sections": sections,
        "ok_sections": ok_count,
        "failed_or_partial_sections": fail_count,
        "core_metrics_ready": core_ready,
        "missing_core": [
            k for k in ("current_price", "pe_trailing", "pb", "roe")
            if metrics.get(k) is None
        ],
    }


def _section_status(payload: dict) -> tuple[str, str]:
    if payload.get("error"):
        return "fail", str(payload["error"])[:200]

    errors = []
    has_data = False
    for key, val in payload.items():
        if key == "error":
            continue
        if isinstance(val, dict) and val.get("error"):
            errors.append(f"{key}: {val['error'][:80]}")
        elif val not in (None, {}, [], ""):
            has_data = True

    if errors and has_data:
        return "partial", "; ".join(errors[:3])
    if errors:
        return "fail", "; ".join(errors[:3])
    if has_data:
        return "ok", "数据可用"
    return "fail", "无有效数据"


def enrich_data(data: dict) -> dict:
    """在 gather_all 之后调用: 注入 key_metrics 与 data_quality"""
    data["key_metrics"] = resolve_key_metrics(data)
    data["data_quality"] = build_data_quality_report(data)
    return data


def facts_summary_for_prompt(data: dict) -> str:
    """带来源标注的核心事实摘要，优先注入 LLM prompt"""
    m = data.get("key_metrics") or resolve_key_metrics(data)
    q = data.get("data_quality") or build_data_quality_report(data)
    research = data.get("研报评级", {})
    news = data.get("新闻公告", {})
    cutoff = narrative_cutoff_date(NARRATIVE_MAX_AGE_DAYS)
    lines = [
        "## 已验证核心事实（必须使用，并标注来源）",
        f"- 当前价: {m.get('current_price')} 元 [{m.get('current_price_source') or '缺失'}]",
        f"- PE(TTM): {m.get('pe_trailing')}x [{m.get('pe_source') or '缺失'}]",
        f"- PB: {m.get('pb')}x [{m.get('pb_source') or '缺失'}]",
        f"- ROE: {m.get('roe')}% [{m.get('roe_source') or '缺失'}]",
        f"- 一致预期 EPS: {m.get('eps_consensus')} [{m.get('eps_consensus_source') or '缺失'}]",
        f"- 北向资金(最近): {m.get('northbound_net_flow')} [{m.get('northbound_date')}] [{m.get('northbound_source') or '缺失'}]",
        "",
        f"## 非量化叙事数据时效（硬性规则：仅可使用 {cutoff} 及之后的消息）",
        f"- 政策: 新闻/公告/研报标题/评级叙事仅允许近 {NARRATIVE_MAX_AGE_DAYS} 日内数据",
        f"- 近7日研报: {len(research.get('recent_reports') or []) if isinstance(research, dict) else 0} 篇",
        f"- 近7日新闻/公告: "
        f"{len(news.get('headlines') or []) + len(news.get('announcements') or []) if isinstance(news, dict) else 0} 条",
        "",
        "## 数据质量",
        f"- 核心指标就绪: {'是' if q.get('core_metrics_ready') else '否'}",
        f"- 缺失核心字段: {', '.join(q.get('missing_core') or []) or '无'}",
        f"- 模块状态: {q.get('ok_sections')} 可用 / {q.get('failed_or_partial_sections')} 失败或部分失败",
        "",
        "## 分析纪律（必须遵守）",
        "1. 每个数值结论必须标注来源（如「东方财富估值」「研报一致预期」）",
        "2. 数据缺失时明确写「数据不可用」，禁止用「假设」「可能约」填补关键数字",
        "3. 推断必须基于已给数据，并写明推断逻辑；不得捏造财报、持仓、批价等未提供的数据",
        "4. 新闻标题、研报标题、公告：只能引用近7日内 raw JSON 中存在的条目；更早的一律不得引用",
        "5. 若近7日无新研报/新闻，叙事部分须明确写「近一周无新消息」，不得用旧闻充数",
    ]

    if isinstance(research, dict) and research.get("total_reports"):
        lines.insert(6, f"- 研报覆盖: {research['total_reports']} 篇 [东方财富研报中心]")

    return "\n".join(lines)
