"""
宏观经济: 利率、CPI、GDP、PMI 等宏观背景
"""
from data.price import _detect_market
from data.utils import retry_call, safe_float


def get_macro(symbol: str) -> dict:
    """获取当前宏观经济背景数据"""
    market = _detect_market(symbol)
    result = {"source": "AKShare / FRED"}

    # 美国宏观 (FRED)
    try:
        from config import FRED_API_KEY
        if FRED_API_KEY:
            from fredapi import Fred
            fred = Fred(api_key=FRED_API_KEY)
            result["us"] = {
                "source": "FRED",
                "fed_funds_rate": _safe_get(fred, "FEDFUNDS"),
                "cpi_yoy": _safe_get(fred, "CPIAUCSL"),
                "unemployment": _safe_get(fred, "UNRATE"),
                "gdp": _safe_get(fred, "GDP"),
                "ten_year_yield": _safe_get(fred, "DGS10"),
                "sp500": _safe_get(fred, "SP500"),
            }
    except ImportError:
        pass
    except Exception:
        pass

    # 中国宏观 (AKShare)
    if market == "a":
        try:
            import akshare as ak

            try:
                df_pmi = retry_call(lambda: ak.macro_china_pmi())
                if not df_pmi.empty:
                    latest_pmi = _latest_row(df_pmi, "月份")
                    result["cn_pmi"] = {
                        "source": "AKShare macro_china_pmi",
                        "month": str(latest_pmi.get("月份", "")),
                        "manufacturing_pmi": safe_float(latest_pmi.get("制造业-指数")),
                        "non_manufacturing_pmi": safe_float(latest_pmi.get("非制造业-指数")),
                    }
            except Exception:
                pass

            try:
                df_cpi = retry_call(lambda: ak.macro_china_cpi_monthly())
                if not df_cpi.empty:
                    latest_cpi = df_cpi.iloc[-1]
                    result["cn_cpi_latest"] = {
                        "source": "AKShare macro_china_cpi_monthly",
                        "item": str(latest_cpi.get("商品", "")),
                        "date": str(latest_cpi.get("日期", "")),
                        "value": safe_float(latest_cpi.get("今值")),
                        "forecast": safe_float(latest_cpi.get("预测值")),
                        "previous": safe_float(latest_cpi.get("前值")),
                    }
            except Exception:
                pass

            try:
                df_m2 = retry_call(lambda: ak.macro_china_money_supply())
                if not df_m2.empty:
                    latest_m2 = _latest_row(df_m2, "月份")
                    result["cn_money_supply_latest"] = {
                        "source": "AKShare macro_china_money_supply",
                        "month": str(latest_m2.get("月份", "")),
                        "m2_yoy": safe_float(latest_m2.get("货币和准货币(M2)-同比增长")),
                        "m1_yoy": safe_float(latest_m2.get("货币(M1)-同比增长")),
                        "m0_yoy": safe_float(latest_m2.get("流通中的现金(M0)-同比增长")),
                    }
            except Exception:
                pass

            try:
                df_shibor = retry_call(
                    lambda: ak.rate_interbank(market="上海银行间同业拆放利率", symbol="Shibor")
                )
                if not df_shibor.empty:
                    latest_shibor = df_shibor.iloc[-1]
                    result["cn_shibor_on"] = {
                        "source": "AKShare rate_interbank",
                        "date": str(latest_shibor.iloc[0]) if len(latest_shibor) > 0 else "",
                        "values": {str(k): safe_float(v) for k, v in latest_shibor.items()},
                    }
            except Exception:
                pass

        except ImportError:
            pass
        except Exception:
            pass

    return result


def _latest_row(df, sort_col: str):
    if sort_col in df.columns:
        return df.sort_values(sort_col).iloc[-1]
    return df.iloc[-1]


def _safe_get(fred, series_id: str) -> float | None:
    """安全从 FRED 获取最新值"""
    try:
        s = fred.get_series(series_id)
        if len(s) > 0:
            return round(float(s.dropna().iloc[-1]), 2)
    except Exception:
        pass
    return None
