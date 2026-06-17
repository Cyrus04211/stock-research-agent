"""
非量化叙事数据新鲜度 — 仅保留近 N 天内的消息/研报/公告
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any

# 非量化叙事数据最大时效（天）
NARRATIVE_MAX_AGE_DAYS = 7


def narrative_cutoff_date(max_age_days: int = NARRATIVE_MAX_AGE_DAYS) -> date:
    return (datetime.now() - timedelta(days=max_age_days)).date()


def parse_item_date(value: Any) -> date | None:
    """解析多种日期格式为 date"""
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()

    text = str(value).strip()
    if not text or text.lower() in ("nan", "none", "nat"):
        return None

    # 2026-06-15 / 2026-06-15 12:00:00
    m = re.match(r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})", text)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass

    # 2026年06月15日
    m = re.match(r"(\d{4})年(\d{1,2})月(\d{1,2})日", text)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(text[:19], fmt).date()
        except ValueError:
            continue

    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")[:19]).date()
    except ValueError:
        return None


def is_fresh(value: Any, max_age_days: int = NARRATIVE_MAX_AGE_DAYS) -> bool:
    item_date = parse_item_date(value)
    if item_date is None:
        return False
    return item_date >= narrative_cutoff_date(max_age_days)


def filter_items_by_freshness(
    items: list[dict],
    date_keys: tuple[str, ...],
    max_age_days: int = NARRATIVE_MAX_AGE_DAYS,
) -> tuple[list[dict], dict]:
    """按日期字段过滤列表，返回 (新鲜条目, 统计信息)"""
    fresh = []
    stale = 0
    unknown = 0
    for item in items:
        if not isinstance(item, dict):
            unknown += 1
            continue
        item_date = None
        for key in date_keys:
            if key in item and item[key]:
                item_date = parse_item_date(item[key])
                if item_date:
                    break
        if item_date is None:
            unknown += 1
            continue
        if item_date >= narrative_cutoff_date(max_age_days):
            fresh.append(item)
        else:
            stale += 1

    meta = {
        "max_age_days": max_age_days,
        "cutoff_date": str(narrative_cutoff_date(max_age_days)),
        "fresh_count": len(fresh),
        "stale_dropped": stale,
        "unknown_date_dropped": unknown,
    }
    return fresh, meta


def freshness_meta(
    fresh_count: int,
    stale_dropped: int = 0,
    unknown_dropped: int = 0,
    max_age_days: int = NARRATIVE_MAX_AGE_DAYS,
) -> dict:
    return {
        "policy": f"仅保留近{max_age_days}日内非量化叙事数据",
        "max_age_days": max_age_days,
        "cutoff_date": str(narrative_cutoff_date(max_age_days)),
        "fresh_count": fresh_count,
        "stale_dropped": stale_dropped,
        "unknown_date_dropped": unknown_dropped,
    }
