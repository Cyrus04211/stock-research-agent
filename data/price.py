"""
行情与估值数据: 历史K线、关键统计指标、PE/PB分位数
"""
import yfinance as yf
import pandas as pd
from typing import Optional


def _detect_market(symbol: str) -> str:
    """根据代码格式判断市场: us / a / hk"""
    if symbol.isdigit():
        if len(symbol) == 6:
            return "a"
        if len(symbol) <= 5:
            return "hk"
    return "us"


def _to_yf_ticker(symbol: str) -> str:
    """转换为 yfinance 接受的 ticker 格式"""
    market = _detect_market(symbol)
    if market == "a":
        # Shanghai: 6xxxxx -> .SS, Shenzhen: 0xxxxx/3xxxxx -> .SZ
        if symbol.startswith("6"):
            return f"{symbol}.SS"
        return f"{symbol}.SZ"
    if market == "hk":
        return f"{symbol.zfill(4)}.HK"
    return symbol


def get_price_data(symbol: str) -> dict:
    """
    获取行情数据：历史价格 + 关键统计
    返回结构化的 dict，直接喂给 LLM
    """
    ticker_str = _to_yf_ticker(symbol)
    market = _detect_market(symbol)

    try:
        t = yf.Ticker(ticker_str)
        info = t.info or {}
        hist_1y = t.history(period="1y")
        hist_5y = t.history(period="5y")

        # --- 近期价格表现 ---
        if not hist_1y.empty:
            close = hist_1y["Close"]
            current_price = round(float(close.iloc[-1]), 2)
            ytd_start = close[close.index >= f"{close.index[-1].year}-01-01"]
            ytd_change = (
                round(float((close.iloc[-1] / ytd_start.iloc[0] - 1) * 100), 1)
                if len(ytd_start) > 1 else None
            )
            ma_60 = round(float(close.rolling(60).mean().iloc[-1]), 2) if len(close) >= 60 else None
            ma_200 = round(float(close.rolling(200).mean().iloc[-1]), 2) if len(close) >= 200 else None
            high_52w = round(float(close.rolling(252).max().iloc[-1]), 2) if len(close) >= 252 else round(float(close.max()), 2)
            low_52w = round(float(close.rolling(252).min().iloc[-1]), 2) if len(close) >= 252 else round(float(close.min()), 2)
            vol_avg_3m = round(float(hist_1y["Volume"].tail(63).mean()), 0) if len(hist_1y) >= 63 else None
        else:
            current_price = info.get("currentPrice") or info.get("regularMarketPrice")
            ytd_change = None
            ma_60 = ma_200 = high_52w = low_52w = vol_avg_3m = None

        # --- PE 分位数近似 (用5年高低点估算) ---
        pe_current = info.get("trailingPE") or info.get("forwardPE")
        pe_5y_low = pe_5y_high = None
        if pe_current and not hist_5y.empty and len(hist_5y) >= 500:
            # 简单方法：用价格范围粗略估算 PE 分位
            close_5y = hist_5y["Close"]
            price_5y_low = round(float(close_5y.min()), 2)
            price_5y_high = round(float(close_5y.max()), 2)
            price_position = (current_price - price_5y_low) / (price_5y_high - price_5y_low) * 100
            price_position = round(price_position, 1)
        else:
            price_5y_low = price_5y_high = price_position = None

        return {
            "symbol": symbol,
            "market": market,
            "name": info.get("longName") or info.get("shortName") or symbol,
            "current_price": current_price,
            "currency": info.get("currency", "USD"),
            # 估值核心
            "pe_trailing": info.get("trailingPE"),
            "pe_forward": info.get("forwardPE"),
            "pb": info.get("priceToBook"),
            "ps": info.get("priceToSales"),
            "peg": info.get("pegRatio"),
            "dividend_yield": round(float(info["dividendYield"]) * 100, 2) if info.get("dividendYield") else None,
            # 市值
            "market_cap": info.get("marketCap"),
            "enterprise_value": info.get("enterpriseValue"),
            "ev_to_ebitda": info.get("enterpriseToEbitda"),
            # 价格区间
            "high_52w": high_52w,
            "low_52w": low_52w,
            "ma_60": ma_60,
            "ma_200": ma_200,
            "price_vs_ma60_pct": round(float((current_price / ma_60 - 1) * 100), 1) if current_price and ma_60 else None,
            "price_vs_ma200_pct": round(float((current_price / ma_200 - 1) * 100), 1) if current_price and ma_200 else None,
            "price_5y_low": price_5y_low,
            "price_5y_high": price_5y_high,
            "price_5y_position_pct": price_position,
            "ytd_change_pct": ytd_change,
            # 风险指标
            "beta": info.get("beta"),
            "short_ratio": info.get("shortRatio"),
            "short_pct": round(float(info["shortPercentOfFloat"]) * 100, 1) if info.get("shortPercentOfFloat") else None,
            # 成交量
            "avg_volume_3m": vol_avg_3m,
            # 成长性
            "revenue_growth_yoy": round(float(info["revenueGrowth"]) * 100, 1) if info.get("revenueGrowth") else None,
            "earnings_growth_yoy": round(float(info["earningsGrowth"]) * 100, 1) if info.get("earningsGrowth") else None,
        }
    except Exception as e:
        return {"symbol": symbol, "market": market, "error": str(e)}


def _parse_value_em_df(df: pd.DataFrame) -> dict:
    """解析东方财富 stock_value_em 返回的估值序列"""
    if df.empty:
        return {}

    latest = df.iloc[-1]
    pe_col = "PE(TTM)" if "PE(TTM)" in df.columns else "PE"
    pb_col = "市净率" if "市净率" in df.columns else "PB"
    ps_col = "市销率" if "市销率" in df.columns else "PS"
    price_col = "当日收盘价" if "当日收盘价" in df.columns else None

    result = {
        "source": "东方财富 stock_value_em",
        "data_date": str(latest.get("数据日期", "")),
        "current_price": _safe_price(latest.get(price_col)) if price_col else None,
        "change_pct": _safe_price(latest.get("当日涨跌幅")),
        "pe_current": _safe_price(latest.get(pe_col)),
        "pb_current": _safe_price(latest.get(pb_col)),
        "ps_current": _safe_price(latest.get(ps_col)),
        "market_cap": _safe_price(latest.get("总市值")),
    }

    if pe_col in df.columns and len(df) > 20:
        pe_series = pd.to_numeric(df[pe_col], errors="coerce").dropna()
        if len(pe_series) > 0:
            current_pe = float(pe_series.iloc[-1])
            result["pe_5y_min"] = round(float(pe_series.min()), 2)
            result["pe_5y_max"] = round(float(pe_series.max()), 2)
            result["pe_5y_median"] = round(float(pe_series.median()), 2)
            result["pe_percentile"] = round(float((pe_series < current_pe).mean() * 100), 1)

    if pb_col in df.columns and len(df) > 20:
        pb_series = pd.to_numeric(df[pb_col], errors="coerce").dropna()
        if len(pb_series) > 0:
            current_pb = float(pb_series.iloc[-1])
            result["pb_5y_min"] = round(float(pb_series.min()), 2)
            result["pb_5y_max"] = round(float(pb_series.max()), 2)
            result["pb_5y_median"] = round(float(pb_series.median()), 2)
            result["pb_percentile"] = round(float((pb_series < current_pb).mean() * 100), 1)

    return result


def _safe_price(val) -> float | None:
    try:
        f = float(val)
        if f != f:
            return None
        return round(f, 2)
    except (TypeError, ValueError):
        return None


# A 股补充: 用 AKShare 拿估值分位
def get_a_share_valuation(symbol: str) -> dict:
    """A 股专属: 从 AKShare 获取估值数据和 PE/PB 历史分位"""
    try:
        import akshare as ak
        from data.utils import retry_call

        df = retry_call(lambda: ak.stock_value_em(symbol=symbol))
        return _parse_value_em_df(df)
    except Exception as e:
        return {"error": str(e)}


def get_a_share_price(symbol: str) -> dict:
    """A 股专属: 历史行情数据（hist 失败时回退到 stock_value_em）"""
    try:
        import akshare as ak
        from data.utils import retry_call

        try:
            df = retry_call(lambda: ak.stock_zh_a_hist(symbol=symbol, period="daily", adjust="qfq"))
            if df.empty:
                raise ValueError("empty hist")

            df = df.sort_values("日期")
            latest = df.iloc[-1]
            close = pd.to_numeric(df["收盘"], errors="coerce")

            current_price = float(close.iloc[-1])
            ma_60 = round(float(close.tail(60).mean()), 2) if len(close) >= 60 else None
            ma_200 = round(float(close.tail(200).mean()), 2) if len(close) >= 200 else None
            high_252 = round(float(close.tail(252).max()), 2) if len(close) >= 252 else None
            low_252 = round(float(close.tail(252).min()), 2) if len(close) >= 252 else None

            ytd = df[df["日期"] >= f"{df.iloc[-1]['日期'][:4]}-01-01"]
            ytd_change = None
            if len(ytd) > 1:
                ytd_change = round(float((pd.to_numeric(ytd.iloc[-1]["收盘"], errors="coerce") /
                                          pd.to_numeric(ytd.iloc[0]["收盘"], errors="coerce") - 1) * 100), 1)

            df["年份"] = pd.to_datetime(df["日期"]).dt.year
            yearly = df.groupby("年份").agg(
                open_price=("开盘", "first"),
                close_price=("收盘", "last")
            )
            yearly["return"] = round((yearly["close_price"] / yearly["open_price"] - 1) * 100, 1)
            annual_returns = {str(k): v for k, v in yearly["return"].tail(5).items()}

            return {
                "source": "AKShare stock_zh_a_hist",
                "current_price": current_price,
                "涨跌幅": float(latest.get("涨跌幅", 0)) if "涨跌幅" in df.columns else None,
                "ma_60": ma_60,
                "ma_200": ma_200,
                "high_252d": high_252,
                "low_252d": low_252,
                "price_vs_ma60_pct": round((current_price / ma_60 - 1) * 100, 1) if current_price and ma_60 else None,
                "price_vs_ma200_pct": round((current_price / ma_200 - 1) * 100, 1) if current_price and ma_200 else None,
                "ytd_change_pct": ytd_change,
                "annual_returns": annual_returns,
                "volatility_1y": round(float(close.pct_change().tail(252).std() * (252 ** 0.5) * 100), 1) if len(close) >= 252 else None,
            }
        except Exception as hist_err:
            val_df = retry_call(lambda: ak.stock_value_em(symbol=symbol))
            val = _parse_value_em_df(val_df)
            if not val.get("current_price"):
                return {"error": f"hist: {hist_err}; value_em: no price"}
            return {
                "source": "东方财富 stock_value_em (hist 不可用时的回退)",
                "current_price": val["current_price"],
                "data_date": val.get("data_date"),
                "change_pct": val.get("change_pct"),
                "note": "均线/波动率因 K 线接口不可用而未计算",
            }
    except Exception as e:
        return {"error": str(e)}
