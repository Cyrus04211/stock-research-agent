"""
研报数据: 券商研报评级、盈利预测（A股）+ 分析师评级（美股）
叙事类研报仅保留近7日；一致预期 EPS 仍基于近7日研报计算。
"""
import pandas as pd
from data.price import _detect_market, _to_yf_ticker
from data.freshness import NARRATIVE_MAX_AGE_DAYS, is_fresh, freshness_meta
from data.utils import retry_call
import yfinance as yf


def get_research(symbol: str) -> dict:
    """获取研报/分析师评级数据，自动判断市场"""
    market = _detect_market(symbol)
    if market == "a":
        return _get_a_share_research(symbol)
    return _get_us_research(symbol)


def _get_a_share_research(symbol: str) -> dict:
    """A 股研报数据: 评级、盈利预测"""
    try:
        import akshare as ak
        df = retry_call(lambda: ak.stock_research_report_em(symbol=symbol))
        if df.empty:
            return {"source": "东方财富研报中心", "count": 0, "note": "暂无研报数据"}

        result = {
            "source": "东方财富研报中心",
            "total_reports": len(df),
            "recent_reports": [],
            "rating_summary": {},
            "rating_summary_7d": {},
            "earnings_forecast": {},
            "freshness": freshness_meta(0),
        }

        if "日期" in df.columns:
            df_sorted = df.sort_values("日期", ascending=False)
        else:
            df_sorted = df

        # 叙事类：仅近7日研报
        df_fresh = df_sorted[df_sorted["日期"].apply(lambda d: is_fresh(d, NARRATIVE_MAX_AGE_DAYS))]
        stale_count = len(df_sorted) - len(df_fresh)

        # 量化一致预期：最近30篇研报（不受7日限制）
        forecast_df = df_sorted.head(30)

        if "东财评级" in df.columns and not df_fresh.empty:
            rating_counts = df_fresh["东财评级"].value_counts().to_dict()
            result["rating_summary_7d"] = {str(k): int(v) for k, v in rating_counts.items()}

        # 全历史评级仅作背景统计，prompt 中标注不可用于叙事
        if "东财评级" in df.columns:
            rating_counts_all = df["东财评级"].value_counts().to_dict()
            result["rating_summary"] = {
                str(k): int(v) for k, v in rating_counts_all.items()
            }
            result["rating_summary_note"] = "全历史统计，叙事分析禁止使用，请用 rating_summary_7d"

        for _, row in df_fresh.head(20).iterrows():
            report = {
                "title": str(row.get("报告名称", "")),
                "institution": str(row.get("机构", "")),
                "rating": str(row.get("东财评级", "")),
                "date": str(row.get("日期", "")),
            }
            eps_cols = [c for c in df.columns if "盈利预测-收益" in str(c)]
            for col in eps_cols:
                year = col.split("-")[0].strip()
                eps_val = row.get(col)
                pe_val = row.get(col.replace("收益", "市盈率"))
                if eps_val and str(eps_val) != "nan":
                    report[f"EPS_{year}"] = str(eps_val)
                    if pe_val and str(pe_val) != "nan":
                        report[f"PE_{year}"] = str(pe_val)
            result["recent_reports"].append(report)

        eps_cols = [c for c in df.columns if "盈利预测-收益" in str(c)]
        for eps_col in eps_cols:
            year_label = eps_col.split("-")[0].strip()
            eps_vals = pd.to_numeric(forecast_df[eps_col], errors="coerce").dropna()
            if len(eps_vals) > 0:
                result["earnings_forecast"][f"EPS_{year_label}"] = round(float(eps_vals.mean()), 4)
                result["earnings_forecast"][f"EPS_{year_label}_min"] = round(float(eps_vals.min()), 4)
                result["earnings_forecast"][f"EPS_{year_label}_max"] = round(float(eps_vals.max()), 4)
                result["earnings_forecast"][f"EPS_{year_label}_analysts"] = len(eps_vals)

                pe_col = eps_col.replace("收益", "市盈率")
                if pe_col in forecast_df.columns:
                    pe_vals = pd.to_numeric(forecast_df[pe_col], errors="coerce").dropna()
                    if len(pe_vals) > 0:
                        result["earnings_forecast"][f"PE_{year_label}"] = round(float(pe_vals.mean()), 2)

        result["earnings_forecast"]["_note"] = (
            f"量化一致预期基于最近30篇研报均值；"
            f"叙事引用研报仅可使用近{NARRATIVE_MAX_AGE_DAYS}日条目"
        )
        result["freshness"] = freshness_meta(
            fresh_count=len(result["recent_reports"]),
            stale_dropped=stale_count,
        )
        if not result["recent_reports"]:
            result["note"] = (
                f"近{NARRATIVE_MAX_AGE_DAYS}日内无新研报；"
                "叙事分析不得引用更早研报标题，应写「近一周无新研报」"
            )

        return result
    except Exception as e:
        return {"source": "东方财富研报中心", "error": str(e)}


def _get_us_research(symbol: str) -> dict:
    """美股分析师评级数据"""
    ticker_str = _to_yf_ticker(symbol)
    result = {
        "source": "Yahoo Finance + Finnhub",
        "analyst_ratings": {},
        "recommendations_trend": [],
        "freshness": freshness_meta(0),
    }

    try:
        t = yf.Ticker(ticker_str)
        info = t.info or {}

        result["analyst_ratings"] = {
            "target_mean": info.get("targetMeanPrice"),
            "target_high": info.get("targetHighPrice"),
            "target_low": info.get("targetLowPrice"),
            "recommendation_mean": info.get("recommendationMean"),
            "recommendation_key": info.get("recommendationKey"),
            "number_of_analysts": info.get("numberOfAnalystOpinions"),
        }

        recs = t.recommendations
        if recs is not None and not recs.empty:
            if "period" in recs.columns:
                recs = recs.rename(columns={"period": "date"})
            for _, row in recs.tail(6).iterrows():
                entry = {
                    "date": str(row.get("date", row.name)),
                    "strong_buy": int(row.get("strongBuy", 0)),
                    "buy": int(row.get("buy", 0)),
                    "hold": int(row.get("hold", 0)),
                    "sell": int(row.get("sell", 0)),
                    "strong_sell": int(row.get("strongSell", 0)),
                }
                if is_fresh(entry["date"], NARRATIVE_MAX_AGE_DAYS):
                    result["recommendations_trend"].append(entry)
    except Exception as e:
        result["error"] = str(e)

    try:
        import requests
        from config import FINNHUB_API_KEY
        if FINNHUB_API_KEY:
            r = requests.get(
                "https://finnhub.io/api/v1/stock/recommendation",
                params={"symbol": symbol, "token": FINNHUB_API_KEY},
                timeout=10,
            )
            if r.status_code == 200:
                finnhub_data = r.json()
                if finnhub_data:
                    result["recommendations_trend_finnhub"] = [
                        x for x in finnhub_data[:6]
                        if is_fresh(x.get("period", ""), NARRATIVE_MAX_AGE_DAYS)
                    ]
    except Exception:
        pass

    result["freshness"] = freshness_meta(len(result.get("recommendations_trend", [])))
    return result
