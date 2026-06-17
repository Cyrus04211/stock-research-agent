"""
行业与同业对比: 行业分类、同业公司估值对比
"""
from data.price import _detect_market, _to_yf_ticker
import yfinance as yf


def get_peers(symbol: str) -> dict:
    """获取同业对比数据"""
    market = _detect_market(symbol)
    result = {}

    # yfinance 获取行业信息和同业
    ticker_str = _to_yf_ticker(symbol)
    try:
        t = yf.Ticker(ticker_str)
        info = t.info or {}

        result["sector"] = info.get("sector", "")
        result["industry"] = info.get("industry", "")
        result["full_time_employees"] = info.get("fullTimeEmployees")

        # 同业推荐列表
        sec_info = {}
        for key in info:
            if "sector" in key.lower() or "industry" in key.lower():
                sec_info[key] = info[key]

    except Exception:
        pass

    # 美股: 用 finqual 做可比公司分析
    if market == "us":
        try:
            from finqual import CCA
            cca = CCA(symbol)
            peers_df = cca.get_c()
            if not peers_df.empty:
                result["comparable_companies"] = []
                for _, row in peers_df.head(8).iterrows():
                    result["comparable_companies"].append({
                        "ticker": str(row.get("Ticker", row.name)),
                        "name": str(row.get("Company Name", "")),
                        "market_cap": str(row.get("Market Cap", "")),
                        "pe_ratio": str(row.get("P/E Ratio", "")),
                        "revenue_growth": str(row.get("Revenue Growth", "")),
                    })
        except ImportError:
            pass
        except Exception:
            pass

    # A 股: 用 AKShare 获取同行业公司
    if market == "a":
        try:
            import akshare as ak
            # 获取行业板块成分股
            df_board = ak.stock_board_industry_cons_em(symbol=result.get("industry", ""))
            if not df_board.empty:
                result["industry_peers"] = []
                for _, row in df_board.head(8).iterrows():
                    result["industry_peers"].append({
                        "code": str(row.get("代码", "")),
                        "name": str(row.get("名称", "")),
                        "price": str(row.get("最新价", "")),
                        "change": str(row.get("涨跌幅", "")),
                        "pe": str(row.get("市盈率", "")),
                    })
        except Exception:
            pass

    return result
