"""
股东与持仓: 十大股东、机构持仓、内部人交易、北向资金
"""
from data.price import _detect_market
from data.utils import to_akshare_gdfx_symbol, retry_call, safe_float


def get_ownership(symbol: str) -> dict:
    """获取股东结构、机构持仓等数据"""
    market = _detect_market(symbol)
    if market == "a":
        return _get_ownership_a(symbol)
    return _get_ownership_us(symbol)


def _get_ownership_a(symbol: str) -> dict:
    """A 股: 十大股东、机构持仓、北向资金"""
    result = {"source": "东方财富 AKShare"}
    try:
        import akshare as ak

        # 十大股东（新接口）
        try:
            gdfx_symbol = to_akshare_gdfx_symbol(symbol)
            df = retry_call(lambda: ak.stock_gdfx_top_10_em(symbol=gdfx_symbol))
            if not df.empty:
                result["top10_holders"] = []
                for _, row in df.head(10).iterrows():
                    result["top10_holders"].append({
                        "rank": str(row.get("名次", "")),
                        "name": str(row.get("股东名称", "")),
                        "share_type": str(row.get("股份类型", "")),
                        "shares": str(row.get("持股数", "")),
                        "ratio": str(row.get("占总股本持股比例", "")),
                        "change": str(row.get("增减", "")),
                        "change_pct": str(row.get("变动比率", "")),
                    })
        except Exception as e:
            result["top10_holders_error"] = str(e)[:120]

        # 北向资金持股明细
        try:
            df_nb = retry_call(lambda: ak.stock_hsgt_individual_em(symbol=symbol))
            if not df_nb.empty and "持股日期" in df_nb.columns:
                df_nb = df_nb.sort_values("持股日期")
                latest = df_nb.iloc[-1]
                recent5 = df_nb.tail(5)
                net_flow = safe_float(latest.get("今日增持资金"))
                data_date = str(latest.get("持股日期", ""))
                result["northbound"] = {
                    "source": "东方财富 stock_hsgt_individual_em",
                    "date": data_date,
                    "net_flow": net_flow,
                    "net_shares": safe_float(latest.get("今日增持股数")),
                    "holding_pct": safe_float(latest.get("持股数量占A股百分比")),
                    "close_price": safe_float(latest.get("当日收盘价")),
                    "net_flow_5d": safe_float(recent5["今日增持资金"].sum()) if "今日增持资金" in recent5 else None,
                    "unit": "人民币元",
                    "data_staleness_note": (
                        "北向持股明细接口最新日期为 "
                        f"{data_date}，分析时请标注数据时效"
                        if data_date and data_date < "2025-01-01"
                        else None
                    ),
                }
        except Exception as e:
            result["northbound_error"] = str(e)[:120]

        # 限售解禁
        try:
            df_restricted = retry_call(lambda: ak.stock_restricted_release_queue_em(symbol=symbol))
            if not df_restricted.empty:
                result["restricted_shares"] = []
                for _, row in df_restricted.head(5).iterrows():
                    result["restricted_shares"].append({
                        "date": str(row.iloc[0]) if len(row) > 0 else "",
                        "shares": str(row.iloc[2]) if len(row) > 2 else "",
                        "ratio": str(row.iloc[3]) if len(row) > 3 else "",
                    })
        except Exception:
            pass

    except Exception as e:
        result["error"] = str(e)

    return result


def _get_ownership_us(symbol: str) -> dict:
    """美股: 机构持仓 + 内部人交易（通过 EdgarTools）"""
    result = {}
    try:
        from edgar import Company, set_identity
        set_identity("stock.analysis@example.com")
        company = Company(symbol)

        # 内部人交易 (Form 4)
        try:
            form4s = company.get_filings(form="4").latest(10)
            if form4s:
                result["insider_transactions"] = []
                for f4 in form4s[:10]:
                    try:
                        obj = f4.obj()
                        if hasattr(obj, "transactions") and obj.transactions is not None:
                            for _, txn in obj.transactions.head(10).iterrows():
                                result["insider_transactions"].append({
                                    "date": str(txn.get("transactionDate", f4.filing_date)),
                                    "insider": str(txn.get("reportingOwner", {}).get("name", "")) if isinstance(txn.get("reportingOwner"), dict) else "",
                                    "transaction_type": str(txn.get("transactionType", "")),
                                    "shares": str(txn.get("shares", "")),
                                    "price": str(txn.get("pricePerShare", "")),
                                    "value": str(txn.get("value", "")),
                                    "remaining": str(txn.get("sharesOwnedFollowingTransaction", "")),
                                })
                    except Exception:
                        pass
        except Exception:
            pass

        # 机构持仓 (Form 13F, 通过 yfinance)
        try:
            import yfinance as yf
            ticker_str = symbol
            t = yf.Ticker(ticker_str)
            holders = t.institutional_holders
            if holders is not None and not holders.empty:
                result["institutional_holders"] = []
                for _, row in holders.head(10).iterrows():
                    result["institutional_holders"].append({
                        "holder": str(row.get("Holder", "")),
                        "shares": str(row.get("Shares", "")),
                        "value": str(row.get("Value", "")),
                        "pct_out": str(row.get("pctOut", "")),
                        "date": str(row.get("DateReported", row.get("Date", ""))),
                    })
        except Exception:
            pass

        # 内部人持仓比例
        try:
            t = yf.Ticker(symbol)
            info = t.info or {}
            result["insider_pct"] = round(float(info["heldPercentInsiders"]) * 100, 1) if info.get("heldPercentInsiders") else None
            result["institution_pct"] = round(float(info["heldPercentInstitutions"]) * 100, 1) if info.get("heldPercentInstitutions") else None
        except Exception:
            pass

    except Exception as e:
        result["error"] = str(e)

    return result
