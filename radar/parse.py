"""解析红果官网页面内嵌的 _ROUTER_DATA。全是纯函数，便于用样本测试。"""

from __future__ import annotations

import json
import re
from datetime import date
from typing import Any, Dict, List, Optional

MARKER = "_ROUTER_DATA = "


class ParseError(Exception):
    """页面结构不符合预期（多半是红果改版了）。"""


def router_data(html: str) -> Dict[str, Any]:
    start = html.find(MARKER)
    if start < 0:
        raise ParseError("找不到 _ROUTER_DATA")
    try:
        # raw_decode 只读出 JSON 本身，后面紧跟的 JS 代码不受影响。
        obj, _ = json.JSONDecoder().raw_decode(html, start + len(MARKER))
    except ValueError as exc:
        raise ParseError(f"_ROUTER_DATA 不是合法 JSON: {exc}") from exc
    if not isinstance(obj, dict) or not isinstance(obj.get("loaderData"), dict):
        raise ParseError("_ROUTER_DATA 缺少 loaderData")
    return obj


def _page(data: Dict[str, Any], prefix: str) -> Dict[str, Any]:
    for key, value in data["loaderData"].items():
        if key.startswith(prefix) and key.endswith("/page") and isinstance(value, dict):
            return value
    raise ParseError(f"loaderData 里没有 {prefix}*/page")


def to_int(value: Any) -> Optional[int]:
    """红果有的数字是字符串（如 "1811000"），统一转成 int；转不了返回 None。"""
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def parse_rank_date(text: str, today: date) -> Optional[str]:
    """「10月13日已更新」→ ISO 日期。年份取今天的年份，月份比今天大说明跨年了。"""
    match = re.search(r"(\d{1,2})月(\d{1,2})日", text or "")
    if not match:
        return None
    month, day = int(match.group(1)), int(match.group(2))
    year = today.year - 1 if month > today.month else today.year
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def parse_score(text: Any) -> Optional[float]:
    match = re.search(r"\d+(?:\.\d+)?", text or "")
    return float(match.group(0)) if match else None


def parse_rank_page(html: str, today: date) -> Dict[str, Any]:
    page = _page(router_data(html), "rank_")
    content = page.get("content") or {}
    items: List[Dict[str, Any]] = []
    for raw in content.get("rankList") or []:
        sid = str(raw.get("seriesId") or raw.get("id") or "")
        rank = to_int(raw.get("rank"))
        if not sid or rank is None:
            raise ParseError(f"榜单条目缺少编号或名次: {raw!r:.200}")
        items.append(
            {
                "id": sid,
                "rank": rank,
                "title": raw.get("title") or "",
                "tags": list(raw.get("tags") or []),
                "status_tags": list(raw.get("statusTags") or []),
                "score": parse_score(raw.get("scoreText")),
            }
        )
    pagination = content.get("pagination") or {}
    return {
        "rank_date": parse_rank_date(page.get("updatedText") or "", today),
        "total_pages": to_int(pagination.get("totalPages")),
        "items": items,
    }


def parse_detail_page(html: str) -> Dict[str, Any]:
    page = router_data(html)["loaderData"].get("detail_page")
    if not isinstance(page, dict):
        raise ParseError("loaderData 里没有 detail_page")
    detail = page.get("seriesDetail") or {}
    social = page.get("seriesSocialInfo") or {}
    title = detail.get("series_name")
    if not title:
        raise ParseError("详情页缺少 series_name")
    return {
        "title": title,
        "tags": list(detail.get("tags") or []),
        "eps": to_int(detail.get("episode_cnt")),
        "first_visible": to_int(detail.get("first_visible_time")),
        "status": to_int((detail.get("series_episode_info") or {}).get("series_status")),
        "hot": to_int((social.get("hot_score_data") or {}).get("score")),
        "fav": to_int(social.get("series_favorite_count")),
        "like": to_int(social.get("series_like_count")),
        "rating_cnt": to_int(social.get("rating_count")),
        "review_cnt": to_int((social.get("reviews") or {}).get("total_count")),
    }


def parse_search_page(html: str) -> List[Dict[str, str]]:
    page = _page(router_data(html), "search_")
    results: List[Dict[str, str]] = []
    for raw in page.get("searchList") or []:
        if raw.get("doc_type") != 23:  # 23 是短剧，其余是演员、角色等
            continue
        video = raw.get("video_data") if isinstance(raw.get("video_data"), dict) else {}
        sid = str(video.get("series_id") or raw.get("keyword") or "")
        if sid and raw.get("name"):
            results.append({"title": raw["name"], "id": sid})
    return results
