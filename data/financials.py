"""
财务报表数据: 利润表、资产负债表、现金流量表 + 关键财务比率
"""
import pandas as pd
import yfinance as yf
from data.price import _detect_market, _to_yf_ticker
from data.utils import safe_float, to_akshare_em_symbol, retry_call


def get_financials_yf(symbol: str) -> dict:
    """通过 yfinance 获取全球股票的财务报表和财务指标"""
    ticker_str = _to_yf_ticker(symbol)
    try:
        t = yf.Ticker(ticker_str)
        info = t.info or {}

        # 利润表关键项
        income = {
            "total_revenue": info.get("totalRevenue"),
            "revenue_per_share": info.get("revenuePerShare"),
            "gross_margins": round(float(info["grossMargins"]) * 100, 1) if info.get("grossMargins") else None,
            "operating_margins": round(float(info["operatingMargins"]) * 100, 1) if info.get("operatingMargins") else None,
            "profit_margins": round(float(info["profitMargins"]) * 100, 1) if info.get("profitMargins") else None,
            "ebitda": info.get("ebitda"),
            "ebitda_margins": round(float(info["ebitdaMargins"]) * 100, 1) if info.get("ebitdaMargins") else None,
            "net_income": info.get("netIncomeToCommon"),
            "diluted_eps": info.get("trailingEps"),
            "forward_eps": info.get("forwardEps"),
        }

        # 资产负债表关键项
        balance = {
            "total_assets": info.get("totalAssets"),
            "total_debt": info.get("totalDebt"),
            "total_cash": info.get("totalCash"),
            "cash_per_share": info.get("totalCashPerShare"),
            "current_ratio": info.get("currentRatio"),
            "debt_to_equity": round(float(info["debtToEquity"]), 1) if info.get("debtToEquity") else None,
            "book_value_per_share": info.get("bookValue"),
            "tangible_book_value": info.get("tangibleBookValue"),
        }

        # 现金流
        cashflow = {
            "free_cashflow": info.get("freeCashflow"),
            "operating_cashflow": info.get("operatingCashflow"),
        }

        # 关键比率
        ratios = {
            "roe": round(float(info["returnOnEquity"]) * 100, 1) if info.get("returnOnEquity") else None,
            "roa": round(float(info["returnOnAssets"]) * 100, 1) if info.get("returnOnAssets") else None,
            "roic": round(float(info["returnOnCapitalEmployed"]) * 100, 1) if info.get("returnOnCapitalEmployed") else None,
            "earnings_quarterly_growth": round(float(info["earningsQuarterlyGrowth"]) * 100, 1) if info.get("earningsQuarterlyGrowth") else None,
            "revenue_quarterly_growth": round(float(info["revenueQuarterlyGrowth"]) * 100, 1) if info.get("revenueQuarterlyGrowth") else None,
            "payout_ratio": round(float(info["payoutRatio"]) * 100, 1) if info.get("payoutRatio") else None,
            "gross_margins": income["gross_margins"],
            "operating_margins": income["operating_margins"],
            "net_margins": income["profit_margins"],
        }

        return {
            "income": {k: v for k, v in income.items() if v is not None},
            "balance": {k: v for k, v in balance.items() if v is not None},
            "cashflow": {k: v for k, v in cashflow.items() if v is not None},
            "ratios": {k: v for k, v in ratios.items() if v is not None},
        }
    except Exception as e:
        return {"error": str(e)}


def get_financials_a_share(symbol: str) -> dict:
    """A 股专属: 通过 AKShare 获取三大报表和财务指标"""
    result = {}
    try:
        import akshare as ak

        # 财务指标 (ROE/ROA/毛利率/净利率等)
        try:
            df_indicator = retry_call(
                lambda: ak.stock_financial_analysis_indicator(symbol=symbol, start_year="2020")
            )
            if not df_indicator.empty:
                latest = df_indicator.iloc[-1]
                result["ratios"] = {
                    "source": "AKShare stock_financial_analysis_indicator",
                    "report_date": str(latest.get("日期", "")),
                    "roe": _pick_float(latest, ["净资产收益率(%)", "净资产收益率", "加权净资产收益率(%)"]),
                    "roa": _pick_float(latest, ["总资产净利润率(%)", "总资产报酬率(%)", "总资产报酬率"]),
                    "gross_margin": _pick_float(latest, ["销售毛利率(%)", "销售毛利率"]),
                    "net_margin": _pick_float(latest, ["销售净利率(%)", "销售净利率"]),
                    "eps": _pick_float(latest, ["基本每股收益(元)", "摊薄每股收益(元)", "加权每股收益(元)"]),
                    "bvps": _pick_float(latest, ["每股净资产_调整后(元)", "每股净资产_调整前(元)"]),
                    "current_ratio": _pick_float(latest, ["流动比率", "流动比率(%)"]),
                    "quick_ratio": _pick_float(latest, ["速动比率", "速动比率(%)"]),
                    "debt_ratio": _pick_float(latest, ["资产负债率(%)", "资产负债率"]),
                    "inventory_turnover": _pick_float(latest, ["存货周转率(次)", "存货周转率"]),
                    "receivable_turnover": _pick_float(latest, ["应收账款周转率(次)", "应收账款周转率"]),
                }
        except Exception:
            pass

        # 利润表（东方财富新接口: 行=报告期）
        try:
            em_symbol = to_akshare_em_symbol(symbol)
            df_profit = retry_call(lambda: ak.stock_profit_sheet_by_report_em(symbol=em_symbol))
            if not df_profit.empty:
                result["income_recent"] = _parse_em_period_sheet(
                    df_profit,
                    {
                        "营业总收入": "TOTAL_OPERATE_INCOME",
                        "净利润": "NETPROFIT",
                        "归母净利润": "PARENT_NETPROFIT",
                        "扣非归母净利润": "DEDUCT_PARENT_NETPROFIT",
                        "基本每股收益": "BASIC_EPS",
                    },
                )
        except Exception:
            pass

        # 资产负债表
        try:
            em_symbol = to_akshare_em_symbol(symbol)
            df_balance = retry_call(lambda: ak.stock_balance_sheet_by_report_em(symbol=em_symbol))
            if not df_balance.empty:
                result["balance_recent"] = _parse_em_period_sheet(
                    df_balance,
                    {
                        "资产总计": "TOTAL_ASSETS",
                        "负债合计": "TOTAL_LIABILITIES",
                        "货币资金": "MONETARYFUNDS",
                        "存货": "INVENTORY",
                        "应收账款": "ACCOUNTS_RECE",
                        "归母股东权益": "TOTAL_PARENT_EQUITY",
                    },
                )
        except Exception:
            pass

        # 现金流
        try:
            em_symbol = to_akshare_em_symbol(symbol)
            df_cf = retry_call(lambda: ak.stock_cash_flow_sheet_by_report_em(symbol=em_symbol))
            if not df_cf.empty:
                result["cashflow_recent"] = _parse_em_period_sheet(
                    df_cf,
                    {
                        "经营活动现金流量净额": "NETCASH_OPERATE",
                        "投资活动现金流量净额": "NETCASH_INVEST",
                        "筹资活动现金流量净额": "NETCASH_FINANCE",
                        "期末现金及现金等价物": "END_CCE",
                    },
                )
        except Exception:
            pass

        return result
    except Exception as e:
        return {"error": str(e)}


def _pick_float(row, keys: list) -> float | None:
    for key in keys:
        if key in row.index:
            val = safe_float(row.get(key))
            if val is not None:
                return val
    return None


def _parse_em_period_sheet(df: pd.DataFrame, field_map: dict) -> dict:
    """解析东方财富按报告期排列的财务报表"""
    if df.empty or "REPORT_DATE" not in df.columns:
        return {}
    sorted_df = df.sort_values("REPORT_DATE", ascending=False)
    result = {}
    for label, col in field_map.items():
        if col not in sorted_df.columns:
            continue
        periods = []
        for _, row in sorted_df.head(4).iterrows():
            val = safe_float(row.get(col))
            if val is None:
                continue
            periods.append({
                "period": str(row.get("REPORT_DATE", ""))[:10],
                "value": val,
            })
        if periods:
            result[label] = periods
    return result


def _safe_float(val) -> float | None:
    return safe_float(val)


def _parse_financial_sheet(df, sheet_name: str) -> dict:
    """解析 AKShare 返回的财务报表 DataFrame -> 最近三期摘要"""
    try:
        # 挑选最近 3 期报告中最重要的行
        key_rows = _get_key_items(sheet_name)
        result = {}
        for _, row in df.iterrows():
            item_name = str(row.iloc[0]) if len(row) > 0 else ""
            if item_name in key_rows:
                values = [str(v) for v in row.iloc[1:]]
                result[item_name] = values[:4]  # 最近4期
        return result
    except Exception:
        return {}


def _to_akshare_symbol(symbol: str) -> str:
    """将普通代码转换为 AKShare 需要的格式: 6xxxxx -> SH6xxxxx, 0xxxxx/3xxxxx -> SZ0xxxxx"""
    if symbol.startswith("6"):
        return f"SH{symbol}"
    return f"SZ{symbol}"


def _get_key_items(sheet_name: str) -> list:
    """各报表的关键科目"""
    items = {
        "利润表": ["营业总收入", "营业收入", "营业总成本", "营业成本", "研发费用", "销售费用",
                 "管理费用", "财务费用", "投资收益", "营业利润", "利润总额", "所得税费用",
                 "净利润", "归属于母公司股东的净利润", "扣除非经常性损益后的净利润",
                 "基本每股收益", "稀释每股收益"],
        "资产负债表": ["资产总计", "流动资产合计", "货币资金", "应收账款", "存货",
                    "非流动资产合计", "固定资产", "在建工程", "无形资产",
                    "商誉", "长期股权投资",
                    "负债合计", "流动负债合计", "短期借款", "应付账款",
                    "非流动负债合计", "长期借款", "应付债券",
                    "归属于母公司股东权益合计", "实收资本（或股本）", "未分配利润",
                    "少数股东权益"],
        "现金流量表": ["经营活动现金流入小计", "经营活动现金流出小计",
                    "经营活动产生的现金流量净额",
                    "投资活动现金流入小计", "投资活动现金流出小计",
                    "投资活动产生的现金流量净额",
                    "筹资活动现金流入小计", "筹资活动现金流出小计",
                    "筹资活动产生的现金流量净额",
                    "现金及现金等价物净增加额", "期末现金及现金等价物余额"],
    }
    return items.get(sheet_name, [])
