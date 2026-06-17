"""
新闻与公告: 近期新闻、公司公告、行业快讯（叙事类仅保留近7日）
"""
from data.price import _detect_market, _to_yf_ticker
from data.freshness import (
    NARRATIVE_MAX_AGE_DAYS,
    filter_items_by_freshness,
    freshness_meta,
    is_fresh,
    parse_item_date,
)
from data.utils import retry_call
import yfinance as yf


def get_news(symbol: str) -> dict:
    """获取近期新闻和公告"""
    market = _detect_market(symbol)
    result = {
        "headlines": [],
        "announcements": [],
        "sentiment_hint": None,
        "freshness": freshness_meta(0),
    }

    raw_headlines = []
    raw_announcements = []

    # yfinance 新闻（全球）
    ticker_str = _to_yf_ticker(symbol)
    try:
        t = yf.Ticker(ticker_str)
        yf_news = t.news
        if yf_news:
            for item in yf_news:
                content = item.get("content", item)
                raw_headlines.append({
                    "title": content.get("title", ""),
                    "publisher": content.get("provider", {}).get("displayName", "") if isinstance(content.get("provider"), dict) else "",
                    "published": content.get("pubDate", "") or content.get("displayTime", ""),
                    "type": content.get("contentType", ""),
                    "summary": (content.get("summary", "") or "")[:200],
                    "url": content.get("canonicalUrl", {}).get("url", "") if isinstance(content.get("canonicalUrl"), dict) else "",
                    "source": "Yahoo Finance",
                })
    except Exception:
        pass

    # A 股补充
    if market == "a":
        try:
            import akshare as ak

            try:
                df_ann = retry_call(lambda: ak.stock_news_em(symbol=symbol))
                if not df_ann.empty:
                    for _, row in df_ann.iterrows():
                        raw_announcements.append({
                            "title": str(row.get("新闻标题", row.get("标题", ""))),
                            "date": str(row.get("发布时间", "")),
                            "source": str(row.get("文章来源", row.get("来源", "东方财富"))),
                            "url": str(row.get("新闻链接", row.get("链接", ""))),
                            "summary": str(row.get("新闻内容", ""))[:200],
                            "data_source": "东方财富 stock_news_em",
                        })
            except Exception as e:
                result["announcements_error"] = str(e)[:120]

            try:
                df_info = retry_call(lambda: ak.stock_info_global_em())
                if not df_info.empty:
                    raw_headlines.extend(_parse_global_briefs(df_info))
            except Exception:
                pass
        except Exception:
            pass

    # Finnhub 新闻情感补充（美股）
    try:
        import requests
        from config import FINNHUB_API_KEY
        if FINNHUB_API_KEY and market == "us":
            r = requests.get(
                "https://finnhub.io/api/v1/news-sentiment",
                params={"symbol": symbol, "token": FINNHUB_API_KEY},
                timeout=10,
            )
            if r.status_code == 200:
                data = r.json()
                if data.get("sentiment"):
                    result["sentiment_hint"] = {
                        "bullish_percent": round(data["sentiment"].get("bullishPercent", 0) * 100, 1),
                        "bearish_percent": round(data["sentiment"].get("bearishPercent", 0) * 100, 1),
                        "buzz_score": data.get("buzz", {}).get("buzz"),
                        "articles_in_last_week": data.get("buzz", {}).get("articlesInLastWeek"),
                        "source": "Finnhub",
                    }
                if data.get("companyNewsScore"):
                    result["company_news_score"] = data["companyNewsScore"]
    except Exception:
        pass

    headlines, h_meta = filter_items_by_freshness(
        raw_headlines, ("published", "date"), NARRATIVE_MAX_AGE_DAYS
    )
    announcements, a_meta = filter_items_by_freshness(
        raw_announcements, ("date", "published"), NARRATIVE_MAX_AGE_DAYS
    )

    result["headlines"] = headlines[:15]
    result["announcements"] = announcements[:15]
    result["freshness"] = freshness_meta(
        fresh_count=len(result["headlines"]) + len(result["announcements"]),
        stale_dropped=h_meta["stale_dropped"] + a_meta["stale_dropped"],
        unknown_dropped=h_meta["unknown_date_dropped"] + a_meta["unknown_date_dropped"],
    )
    if not result["headlines"] and not result["announcements"]:
        result["note"] = f"近{NARRATIVE_MAX_AGE_DAYS}日内无可用新闻/公告（早于 {h_meta['cutoff_date']} 的条目已丢弃）"

    return result


def _parse_global_briefs(df) -> list[dict]:
    """解析全球财经快讯，尽量提取日期"""
    items = []
    date_col = next((c for c in df.columns if "时间" in str(c) or "日期" in str(c)), None)
    text_col = next((c for c in df.columns if "内容" in str(c) or "标题" in str(c)), df.columns[0])

    for _, row in df.iterrows():
        text = str(row.get(text_col, row.iloc[0]))[:200]
        pub = str(row.get(date_col, "")) if date_col else ""
        if not pub:
            # 尝试从正文提取日期前缀
            d = parse_item_date(text[:20])
            pub = str(d) if d else ""
        items.append({
            "title": text[:150],
            "published": pub,
            "source": "东方财富全球快讯",
            "type": "global_brief",
        })
    return items
