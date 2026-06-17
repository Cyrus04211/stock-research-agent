"""
预期差数据: 反向 DCF、隐含增长率、盈利惊喜历史、分析师预测偏差
"""
import yfinance as yf
from data.price import _detect_market, _to_yf_ticker, get_a_share_valuation
from data.utils import safe_float, retry_call


def get_expectations(symbol: str) -> dict:
    """获取预期差相关的全维度数据"""
    market = _detect_market(symbol)
    result = {}
    result["implied_growth"] = _reverse_dcf(symbol, market)
    result["earnings_surprise"] = _earnings_surprise_history(symbol, market)
    result["estimate_revisions"] = _estimate_revision_trend(symbol, market)
    return result


def _reverse_dcf(symbol: str, market: str) -> dict:
    """反向 DCF: yfinance 失败时对 A 股使用研报+估值数据回退"""
    yf_result = _reverse_dcf_yf(symbol)
    if not (isinstance(yf_result, dict) and yf_result.get("error")):
        return yf_result
    if market == "a":
        a_result = _reverse_dcf_a_share(symbol)
        if not (isinstance(a_result, dict) and a_result.get("error")):
            return a_result
    return yf_result


def _reverse_dcf_yf(symbol: str) -> dict:
    ticker_str = _to_yf_ticker(symbol)
    try:
        t = yf.Ticker(ticker_str)
        info = t.info or {}
        price = info.get("currentPrice") or info.get("regularMarketPrice")
        fcf = info.get("freeCashflow")
        shares = info.get("sharesOutstanding")

        if not all([price, fcf, shares]):
            return {"error": "缺少反向 DCF 所需数据", "source": "Yahoo Finance"}

        fcf_per_share = fcf / shares
        fcf_yield = fcf_per_share / price
        implied_g = _bisect_implied_growth(fcf_per_share, price)

        rev_growth = info.get("revenueGrowth")
        earn_growth = info.get("earningsGrowth")
        actual_rev_g = round(rev_growth * 100, 1) if rev_growth else None
        actual_earn_g = round(earn_growth * 100, 1) if earn_growth else None
        gap = round(implied_g - actual_earn_g, 1) if actual_earn_g is not None else None

        return {
            "source": "Yahoo Finance 反向 DCF",
            "current_price": price,
            "fcf_per_share": round(fcf_per_share, 2),
            "fcf_yield_pct": round(fcf_yield * 100, 2),
            "implied_fcf_growth_5y_pct": implied_g,
            "actual_revenue_growth_pct": actual_rev_g,
            "actual_earnings_growth_pct": actual_earn_g,
            "growth_expectation_gap_pct": gap,
            "method": "WACC=9%, 终值增长=2.5%, 预测期=5年",
        }
    except Exception as e:
        return {"error": str(e), "source": "Yahoo Finance"}


def _reverse_dcf_a_share(symbol: str) -> dict:
    """A 股回退: 用东方财富估值 + 研报一致预期 EPS 估算隐含增速"""
    try:
        import akshare as ak
        from data.research import get_research

        val = get_a_share_valuation(symbol)
        if val.get("error") or not val.get("current_price"):
            return {"error": "缺少 A 股估值数据", "source": "东方财富 stock_value_em"}

        research = get_research(symbol)
        forecast = research.get("earnings_forecast", {}) if isinstance(research, dict) else {}
        eps_keys = sorted(k for k in forecast if k.startswith("EPS_") and not k.endswith(("_min", "_max", "_analysts")))
        if len(eps_keys) < 2:
            pe = val.get("pe_current")
            return {
                "source": "东方财富估值 + 研报（简化）",
                "current_price": val.get("current_price"),
                "pe_ttm": pe,
                "note": "缺少多期 EPS 预测，仅提供 PE 锚点，未计算完整反向 DCF",
                "data_date": val.get("data_date"),
            }

        years_eps = [(k.replace("EPS_", ""), safe_float(forecast[k])) for k in eps_keys[:3]]
        years_eps = [(y, e) for y, e in years_eps if e]
        if len(years_eps) < 2:
            return {"error": "研报 EPS 数据不足", "source": "东方财富研报中心"}

        y1, e1 = years_eps[0]
        y2, e2 = years_eps[1]
        years_gap = max(int(y2) - int(y1), 1)
        forecast_cagr = round(((e2 / e1) ** (1 / years_gap) - 1) * 100, 1)

        price = val.get("current_price")
        pe = val.get("pe_current")
        trailing_eps = round(price / pe, 2) if price and pe else None

        return {
            "source": "东方财富估值 + 研报一致预期（A股回退）",
            "current_price": price,
            "pe_ttm": pe,
            "trailing_eps_implied": trailing_eps,
            "consensus_eps_forecast_cagr_pct": forecast_cagr,
            "forecast_years": years_eps,
            "interpretation": (
                f"当前 PE(TTM)={pe}x，研报一致预期 EPS CAGR≈{forecast_cagr}%"
                f"（{y1}→{y2}，来源: 东方财富研报中心）"
            ),
            "data_date": val.get("data_date"),
            "method": "PE 锚点 + 研报 EPS 复合增速（yfinance 不可用时的 A 股回退）",
        }
    except Exception as e:
        return {"error": str(e), "source": "A股回退计算"}


def _bisect_implied_growth(fcf_per_share: float, price: float) -> float:
    WACC, TERMINAL_G, YEARS = 0.09, 0.025, 5

    def implied_value(g: float) -> float:
        total = 0.0
        for t in range(1, YEARS + 1):
            total += fcf_per_share * (1 + g) ** t / (1 + WACC) ** t
        terminal_value = (
            fcf_per_share * (1 + g) ** YEARS * (1 + TERMINAL_G) / (WACC - TERMINAL_G)
        )
        total += terminal_value / (1 + WACC) ** YEARS
        return total

    lo, hi = -0.20, 0.40
    for _ in range(50):
        mid = (lo + hi) / 2
        if implied_value(mid) > price:
            lo = mid
        else:
            hi = mid
    return round((lo + hi) / 2 * 100, 1)


def _earnings_surprise_history(symbol: str, market: str) -> dict:
    ticker_str = _to_yf_ticker(symbol)
    try:
        t = yf.Ticker(ticker_str)
        earnings = t.earnings_dates
        if earnings is None or earnings.empty:
            if market == "a":
                return _earnings_surprise_a_share(symbol)
            return {"note": "无盈利惊喜历史数据", "source": "Yahoo Finance"}

        result = {"source": "Yahoo Finance earnings_dates", "quarters": [], "beat_count": 0, "miss_count": 0}
        beat_count = miss_count = 0

        for _, row in earnings.head(8).iterrows():
            surprise = row.get("Surprise(%)")
            if surprise is None:
                continue
            surprise_val = float(surprise)
            result["quarters"].append({
                "date": str(row.name),
                "eps_actual": safe_float(row.get("EPS Actual"), 4),
                "eps_estimate": safe_float(row.get("EPS Estimate"), 4),
                "surprise_pct": round(surprise_val, 1),
            })
            if surprise_val > 0:
                beat_count += 1
            else:
                miss_count += 1

        result["beat_count"] = beat_count
        result["miss_count"] = miss_count
        result["total_quarters"] = beat_count + miss_count
        result["pattern"] = _surprise_pattern(beat_count, miss_count)
        return result
    except Exception as e:
        if market == "a":
            a = _earnings_surprise_a_share(symbol)
            if not a.get("error"):
                return a
        return {"error": str(e), "source": "Yahoo Finance"}


def _earnings_surprise_a_share(symbol: str) -> dict:
    """A 股: 用季报 EPS 同比变化近似盈利趋势"""
    try:
        import akshare as ak
        from data.utils import to_akshare_em_symbol

        df = retry_call(
            lambda: ak.stock_profit_sheet_by_report_em(symbol=to_akshare_em_symbol(symbol))
        )
        if df.empty or "BASIC_EPS" not in df.columns:
            return {"note": "A股无标准化 beat/miss 数据", "source": "东方财富利润表"}

        q_df = df[df["REPORT_DATE_NAME"].astype(str).str.contains("季报", na=False)].copy()
        if q_df.empty:
            q_df = df.copy()
        q_df = q_df.sort_values("REPORT_DATE", ascending=False).head(8)

        quarters = []
        for _, row in q_df.iterrows():
            quarters.append({
                "period": str(row.get("REPORT_DATE", ""))[:10],
                "report_type": str(row.get("REPORT_DATE_NAME", "")),
                "eps": safe_float(row.get("BASIC_EPS"), 4),
                "net_profit_yoy_pct": safe_float(row.get("PARENT_NETPROFIT_YOY")),
            })

        return {
            "source": "东方财富利润表（季报 EPS，非分析师 surprise）",
            "quarters": quarters,
            "note": "A股缺少统一的 EPS beat/miss 口径，以下为已披露季报 EPS 及归母净利同比",
        }
    except Exception as e:
        return {"error": str(e), "source": "东方财富利润表"}


def _surprise_pattern(beat_count: int, miss_count: int) -> str:
    total = beat_count + miss_count
    if total == 0:
        return "无数据"
    if beat_count >= 6:
        return "系统性 BEAT"
    if miss_count >= 5:
        return "系统性 MISS"
    if beat_count >= miss_count:
        return f"轻微 BEAT 倾向 ({beat_count}/{total})"
    return f"轻微 MISS 倾向 ({miss_count}/{total})"


def _estimate_revision_trend(symbol: str, market: str) -> dict:
    yf_result = _estimate_revision_yf(symbol)
    if not (isinstance(yf_result, dict) and yf_result.get("error")):
        return yf_result
    if market == "a":
        return _estimate_revision_a_share(symbol)
    return yf_result


def _estimate_revision_yf(symbol: str) -> dict:
    ticker_str = _to_yf_ticker(symbol)
    try:
        t = yf.Ticker(ticker_str)
        info = t.info or {}
        result = {
            "source": "Yahoo Finance",
            "forward_eps": info.get("forwardEps"),
            "trailing_eps": info.get("trailingEps"),
            "earnings_growth": round(info["earningsGrowth"] * 100, 1) if info.get("earningsGrowth") else None,
            "revenue_growth": round(info["revenueGrowth"] * 100, 1) if info.get("revenueGrowth") else None,
            "analyst_count": info.get("numberOfAnalystOpinions"),
            "target_mean": info.get("targetMeanPrice"),
        }
        if result["forward_eps"] and result["trailing_eps"]:
            fwd_growth = (result["forward_eps"] / result["trailing_eps"] - 1) * 100
            result["implied_eps_growth_pct"] = round(fwd_growth, 1)
            result["revision_trend"] = _eps_growth_label(fwd_growth)
        return result
    except Exception as e:
        return {"error": str(e), "source": "Yahoo Finance"}


def _estimate_revision_a_share(symbol: str) -> dict:
    try:
        from data.research import get_research

        research = get_research(symbol)
        if research.get("error"):
            return {"error": research["error"], "source": "东方财富研报中心"}

        forecast = research.get("earnings_forecast", {})
        rating = research.get("rating_summary", {})
        recent = research.get("recent_reports", [])

        eps_keys = sorted(k for k in forecast if k.startswith("EPS_") and not k.endswith(("_min", "_max", "_analysts")))
        result = {
            "source": "东方财富研报中心",
            "total_reports": research.get("total_reports"),
            "rating_summary": rating,
            "consensus_eps": {k: forecast[k] for k in eps_keys},
        }

        if len(eps_keys) >= 2:
            e1 = safe_float(forecast[eps_keys[0]])
            e2 = safe_float(forecast[eps_keys[1]])
            if e1 and e2:
                y1 = eps_keys[0].replace("EPS_", "")
                y2 = eps_keys[1].replace("EPS_", "")
                years_gap = max(int(y2) - int(y1), 1)
                growth = ((e2 / e1) ** (1 / years_gap) - 1) * 100
                result["implied_eps_growth_pct"] = round(growth, 1)
                result["revision_trend"] = _eps_growth_label(growth)

        if recent:
            buy_count = sum(1 for r in recent if "买入" in str(r.get("rating", "")))
            result["recent_rating_bias"] = f"近10篇研报中 {buy_count} 篇为买入/增持倾向"

        return result
    except Exception as e:
        return {"error": str(e), "source": "东方财富研报中心"}


def _eps_growth_label(growth: float) -> str:
    if growth < 0:
        return "分析师预期 EPS 将下降"
    if growth < 5:
        return "分析师预期 EPS 低速增长"
    if growth < 15:
        return "分析师预期 EPS 稳健增长"
    return "分析师预期 EPS 高增长"
