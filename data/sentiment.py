"""
情绪极端信号: 做空比例、内部人集群交易、机构持仓方向、社交舆情

Alpha 的关键来源之一: 当情绪达到极端时，市场往往过度定价了已知信息。
极度恐惧 → 潜在买入机会；极度贪婪 → 潜在卖出信号。
"""
import yfinance as yf
from data.price import _detect_market, _to_yf_ticker


def get_sentiment(symbol: str) -> dict:
    """获取情绪极端信号的全维度数据"""
    market = _detect_market(symbol)
    result = {}
    result["short_interest"] = _short_interest(symbol)
    result["insider_cluster"] = _insider_cluster(symbol, market)
    result["institutional_flow"] = _institutional_flow(symbol)
    result["sentiment_extremes"] = _sentiment_extremes(symbol)
    return result


def _short_interest(symbol: str) -> dict:
    """做空数据: 空头占比及其趋势含义"""
    ticker_str = _to_yf_ticker(symbol)
    try:
        t = yf.Ticker(ticker_str)
        info = t.info or {}

        short_pct = info.get("shortPercentOfFloat")
        short_ratio = info.get("shortRatio")

        result = {
            "short_pct_of_float": round(short_pct * 100, 1) if short_pct else None,
            "short_ratio_days": round(short_ratio, 1) if short_ratio else None,
        }

        # 判断极端程度
        if short_pct is not None:
            if short_pct > 0.20:
                result["signal"] = (
                    f"⚠️ 高度做空 ({round(short_pct*100,1)}%) — "
                    "可能是拥挤的空头拥挤交易，也可能是基本面确实有严重问题。"
                    "如果基本面出现意外利好，空头回补可能引发暴力反弹。"
                )
            elif short_pct > 0.10:
                result["signal"] = (
                    f"中度做空 ({round(short_pct*100,1)}%) — 市场存在一定分歧"
                )
            elif short_pct > 0.03:
                result["signal"] = f"正常偏低 ({round(short_pct*100,1)}%) — 无明显做空压力"
            else:
                result["signal"] = f"极低 ({round(short_pct*100,1)}%) — 市场共识偏多，无空头拥挤风险"

        return result
    except Exception as e:
        return {"error": str(e)}


def _insider_cluster(symbol: str, market: str) -> dict:
    """
    内部人交易集群信号
    关键: 连续多人同向操作（集群）的信号强度 >> 单一内部人交易
    """
    result = {}
    try:
        t = yf.Ticker(_to_yf_ticker(symbol))
        info = t.info or {}
        insider_pct = info.get("heldPercentInsiders")
        result["insider_ownership_pct"] = round(insider_pct * 100, 1) if insider_pct else None
    except Exception:
        pass

    # 对于美股，用 EdgarTools 获取 Form 4 详细信息
    if market == "us":
        try:
            from edgar import Company, set_identity
            set_identity("stock.analysis@example.com")
            company = Company(symbol)
            form4s = company.get_filings(form="4").latest(20)

            if form4s:
                buys = []
                sells = []
                for f4 in form4s[:20]:
                    try:
                        obj = f4.obj()
                        if hasattr(obj, "transactions") and obj.transactions is not None:
                            for _, txn in obj.transactions.iterrows():
                                txn_type = str(txn.get("transactionType", "")).upper()
                                shares = float(txn.get("shares", 0) or 0)
                                if "PURCHASE" in txn_type or "BUY" in txn_type:
                                    buys.append({
                                        "date": str(f4.filing_date),
                                        "insider": str(txn.get("reportingOwner", {}).get("name", txn.get("reportingOwnerName", ""))),
                                        "shares": shares,
                                    })
                                elif "SALE" in txn_type or "SELL" in txn_type:
                                    sells.append({
                                        "date": str(f4.filing_date),
                                        "insider": str(txn.get("reportingOwner", {}).get("name", txn.get("reportingOwnerName", ""))),
                                        "shares": shares,
                                    })
                    except Exception:
                        pass

                result["recent_buys"] = buys[:5]
                result["recent_sells"] = sells[:5]
                result["buy_count"] = len(buys)
                result["sell_count"] = len(sells)

                # 集群信号判断
                if len(buys) >= 3 and len(sells) == 0:
                    result["cluster_signal"] = "🟢 买入集群 — 多个内部人近期密集买入，零卖出。这是强烈的看多信号"
                elif len(buys) > len(sells) and len(buys) >= 2:
                    result["cluster_signal"] = "🟡 偏多 — 买入多于卖出，但非集群"
                elif len(sells) >= 4 and len(buys) == 0:
                    result["cluster_signal"] = "🔴 卖出集群 — 多个内部人近期密集卖出，零买入。需高度警惕"
                elif len(sells) > len(buys) and len(sells) >= 3:
                    result["cluster_signal"] = "🟠 偏空 — 卖出多于买入"
                else:
                    result["cluster_signal"] = "⚪ 无显著集群信号"
        except Exception as e:
            result["edgar_error"] = str(e)

    # A 股: 从 AKShare 获取股东变化
    if market == "a":
        try:
            import akshare as ak
            from data.utils import to_akshare_gdfx_symbol, retry_call

            df = retry_call(lambda: ak.stock_gdfx_top_10_em(symbol=to_akshare_gdfx_symbol(symbol)))
            if not df.empty:
                changes = []
                for _, row in df.head(10).iterrows():
                    change = str(row.get("增减", ""))
                    if "增" in change or "新进" in change:
                        changes.append(f"{row.get('股东名称', '')}: {change}")
                if changes:
                    result["shareholder_changes"] = changes
                    result["cluster_signal"] = f"🟡 有 {len(changes)} 个股东增持/新进 [东方财富 stock_gdfx_top_10_em]"
                else:
                    result["cluster_signal"] = "⚪ 十大股东无明显增持信号 [东方财富 stock_gdfx_top_10_em]"
        except Exception as e:
            result["akshare_error"] = str(e)[:120]

    return result


def _institutional_flow(symbol: str) -> dict:
    """机构持仓方向和趋势"""
    ticker_str = _to_yf_ticker(symbol)
    try:
        t = yf.Ticker(ticker_str)
        info = t.info or {}

        inst_pct = info.get("heldPercentInstitutions")
        result = {
            "institutional_ownership_pct": round(inst_pct * 100, 1) if inst_pct else None,
        }

        # 获取机构持仓列表（最新报告）
        holders = t.institutional_holders
        if holders is not None and not holders.empty:
            result["top_institutions"] = []
            for _, row in holders.head(10).iterrows():
                result["top_institutions"].append({
                    "holder": str(row.get("Holder", "")),
                    "shares": str(row.get("Shares", "")),
                    "value": str(row.get("Value", "")),
                    "pct_out": str(row.get("pctOut", "")),
                    "date": str(row.get("DateReported", row.get("Date", ""))),
                })

        # 操作建议
        if inst_pct is not None:
            if inst_pct > 0.80:
                result["signal"] = f"机构高度持仓 ({round(inst_pct*100,1)}%) — 拥挤但代表专业认可"
            elif inst_pct > 0.50:
                result["signal"] = f"机构正常持仓 ({round(inst_pct*100,1)}%)"
            else:
                result["signal"] = f"机构低配 ({round(inst_pct*100,1)}%) — 可能有未被发现的价值或未被认可的风险"

        return result
    except Exception as e:
        return {"error": str(e)}


def _sentiment_extremes(symbol: str) -> dict:
    """综合情绪极端判断"""
    market = _detect_market(symbol)
    ticker_str = _to_yf_ticker(symbol)
    try:
        t = yf.Ticker(ticker_str)
        info = t.info or {}

        result = {"source": "Yahoo Finance"}

        price = info.get("currentPrice")
        low_52w = info.get("fiftyTwoWeekLow")
        high_52w = info.get("fiftyTwoWeekHigh")

        if all([price, low_52w, high_52w]):
            price_position = (price - low_52w) / (high_52w - low_52w) * 100
            result["price_sentiment"] = _price_sentiment_label(price_position)
            result["price_position_pct"] = round(price_position, 1)

        beta = info.get("beta")
        if beta is not None:
            result["beta"] = round(beta, 2)

        if result.get("price_sentiment"):
            return result
    except Exception:
        result = {}

    if market == "a":
        a_ext = _sentiment_extremes_a_share(symbol)
        if a_ext:
            result.update(a_ext)
    return result or {"note": "情绪数据不可用"}


def _sentiment_extremes_a_share(symbol: str) -> dict:
    """A 股: 用 PE 历史分位近似估值极端"""
    try:
        from data.price import get_a_share_valuation

        val = get_a_share_valuation(symbol)
        if val.get("error"):
            return {}
        pe_pct = val.get("pe_percentile")
        result = {"source": "东方财富 stock_value_em PE 分位"}
        if pe_pct is not None:
            if pe_pct > 85:
                result["valuation_sentiment"] = f"🔴 估值偏高 — PE 处于近5年 {pe_pct}% 分位"
            elif pe_pct < 15:
                result["valuation_sentiment"] = f"🔵 估值偏低 — PE 处于近5年 {pe_pct}% 分位"
            else:
                result["valuation_sentiment"] = f"⚪ 估值中性 — PE 处于近5年 {pe_pct}% 分位"
            result["pe_percentile_5y"] = pe_pct
        if val.get("current_price"):
            result["current_price"] = val["current_price"]
            result["data_date"] = val.get("data_date")
        return result
    except Exception:
        return {}


def _price_sentiment_label(price_position: float) -> str:
    if price_position < 15:
        return "🔵 极度恐惧 — 股价接近 52 周低点"
    if price_position < 30:
        return "🔵 偏恐惧 — 股价处于 52 周低位区间"
    if price_position > 85:
        return "🔴 极度贪婪 — 股价接近 52 周高点"
    if price_position > 70:
        return "🔴 偏贪婪 — 股价处于 52 周高位区间"
    return "⚪ 中性 — 股价处于 52 周中间区间"
