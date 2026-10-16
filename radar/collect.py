"""每日采集：榜单 → 观察列表 → 追踪集合 → 详情，产出一份快照字典。"""

from __future__ import annotations

import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from radar.http import SPIDER_UA, FetchError
from radar.parse import ParseError, parse_detail_page, parse_rank_page, parse_search_page
from radar.watchlist import resolve

BASE = "https://hongguoduanju.com"
RANK_SLUGS = {"hot": "hot-drama", "real": "hot-real-drama", "ai": "hot-ai-drama", "comic": "hot-comic-drama"}
MAX_RANK_PAGES = 5
MIN_RANK_ITEMS = 80
MAX_DETAIL_FAIL_RATIO = 0.10
LOOKBACK_DAYS = 14
PROBE_SIZE = 5  # 判断是否刷新时比较综合榜前几名的热度
MIN_PROBE = 3  # 至少要有这么多部可比，否则退回比较名次


class CollectError(Exception):
    """数据不可信，本次不写快照。"""


class NotUpdated(Exception):
    """官方榜单内容和上一份快照完全相同，说明今天还没刷新。"""


def rank_url(slug: str, page: int) -> str:
    return f"{BASE}/rank/{slug}" if page == 1 else f"{BASE}/rank/{slug}?page={page}"


def detail_url(sid: str) -> str:
    return f"{BASE}/detail?series_id={sid}"


def search_url(query: str) -> str:
    return f"{BASE}/search/{urllib.parse.quote(query)}"


def fetch_rank(fetcher, slug: str, today: date) -> Dict[str, Any]:
    items: List[Dict[str, Any]] = []
    rank_date: Optional[str] = None
    for page in range(1, MAX_RANK_PAGES + 1):
        parsed = parse_rank_page(fetcher.get(rank_url(slug, page), ua=SPIDER_UA), today)
        rank_date = rank_date or parsed["rank_date"]
        items.extend(parsed["items"])
        total = parsed["total_pages"]
        if total is None or page >= total:
            break
    seen, unique = set(), []
    for item in sorted(items, key=lambda x: x["rank"]):
        if item["id"] not in seen:
            seen.add(item["id"])
            unique.append(item)
    return {"rank_date": rank_date, "items": unique}


def previous_snapshot(history: List[Dict[str, Any]], today: date) -> Optional[Dict[str, Any]]:
    earlier = [s for s in history if s["date"] < today.isoformat()]
    return max(earlier, key=lambda s: s["date"]) if earlier else None


def is_stale(ranks: Dict[str, Dict[str, Any]], previous: Dict[str, Any], fetch_detail) -> bool:
    """官方今天还没刷新吗？

    热度是官方每天批量算一次的，最可靠：抓综合榜前几名的精确热度，和上一份快照比，全都没变就是没刷新。
    名次不可靠：没刷新时也可能有零星变动（2026-10-15 就是这样）。上一份快照里可比的剧太少时，才退回比较名次。
    """
    old_series = previous.get("series") or {}
    compared = []
    for item in ranks["hot"]["items"][:PROBE_SIZE]:
        old = old_series.get(item["id"])
        if not old or old.get("hot") is None:
            continue
        _, detail, _ = fetch_detail(item["id"])
        if detail and detail.get("hot") is not None:
            compared.append(detail["hot"] == old["hot"])
    if len(compared) >= MIN_PROBE:
        return all(compared)
    return same_ranks(ranks, previous)


def same_ranks(ranks: Dict[str, Dict[str, Any]], previous: Dict[str, Any]) -> bool:
    """4 个榜的名次序列都和上一份快照一样。"""
    for key, rank in ranks.items():
        old = (previous.get("ranks") or {}).get(key)
        if not old or [it["id"] for it in old["items"]] != [it["id"] for it in rank["items"]]:
            return False
    return True


def recent_rank_ids(history: List[Dict[str, Any]], today: date) -> List[str]:
    """最近 LOOKBACK_DAYS 天（不含今天）的快照里上过任意榜的剧。"""
    start = (today - timedelta(days=LOOKBACK_DAYS)).isoformat()
    end = today.isoformat()
    ids: List[str] = []
    for snap in history:
        if not (start <= snap["date"] < end):
            continue
        for rank in (snap.get("ranks") or {}).values():
            for item in rank.get("items", []):
                if item["id"] not in ids:
                    ids.append(item["id"])
    return ids


def collect(
    fetcher,
    today: date,
    watch_entries: List[str],
    watch_cache: Dict[str, Dict],
    history: List[Dict[str, Any]],
    *,
    allow_stale: bool = False,
    now: Optional[str] = None,
    min_rank_items: int = MIN_RANK_ITEMS,
    max_fail_ratio: float = MAX_DETAIL_FAIL_RATIO,
    workers: int = 3,
) -> Dict[str, Any]:
    # 1. 榜单
    ranks: Dict[str, Dict[str, Any]] = {}
    rank_info: Dict[str, Dict[str, Any]] = {}
    for key, slug in RANK_SLUGS.items():
        try:
            rank = fetch_rank(fetcher, slug, today)
        except (FetchError, ParseError) as exc:
            raise CollectError(f"{key} 榜抓取失败: {exc}") from exc
        if len(rank["items"]) < min_rank_items:
            raise CollectError(f"{key} 榜异常: 只有 {len(rank['items'])} 条")
        ranks[key] = {
            "rank_date": today.isoformat(),
            # 页面上「X月X日已更新」解析出的日期。它只是按当天日期显示的文字，仅作记录
            "label_date": rank["rank_date"],
            "items": [
                {"id": it["id"], "rank": it["rank"], "title": it["title"], "status_tags": it["status_tags"]}
                for it in rank["items"]
            ],
        }
        for it in rank["items"]:
            info = rank_info.setdefault(it["id"], {"score": None, "sources": []})
            if info["score"] is None:
                info["score"] = it["score"]
            info["sources"].append(f"rank:{key}")

    # 详情带缓存：判断是否刷新时抓过的剧，后面不再重复抓
    detail_cache: Dict[str, Tuple[Optional[Dict[str, Any]], Optional[str]]] = {}

    def fetch_detail(sid: str):
        if sid not in detail_cache:
            try:
                detail_cache[sid] = (parse_detail_page(fetcher.get(detail_url(sid))), None)
            except (FetchError, ParseError) as exc:
                detail_cache[sid] = (None, str(exc)[:300])
        detail, error = detail_cache[sid]
        return sid, (dict(detail) if detail else None), error

    previous = previous_snapshot(history, today)
    if previous and is_stale(ranks, previous, fetch_detail):
        if not allow_stale:
            raise NotUpdated(f"官方数据和 {previous['date']} 的快照相同，今天还没刷新")
        # 强制写入时沿用上一份的榜单日，计算时按 rank_date 去重，不会重复计入在榜天数
        for key, rank in ranks.items():
            rank["rank_date"] = previous["ranks"][key]["rank_date"]

    # 2. 观察列表
    watch = resolve(watch_entries, lambda q: parse_search_page(fetcher.get(search_url(q))), watch_cache)

    # 3. 追踪集合：在榜 + 观察列表 + 最近掉榜
    sources: Dict[str, List[str]] = {sid: list(info["sources"]) for sid, info in rank_info.items()}
    for w in watch:
        if w["status"] == "ok":
            sources.setdefault(w["id"], []).append("watch")
    for sid in recent_rank_ids(history, today):
        if sid not in sources:
            sources[sid] = ["recent"]
    tracked = list(sources)

    # 4. 详情
    series: Dict[str, Optional[Dict[str, Any]]] = {}
    errors: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for sid, detail, error in pool.map(fetch_detail, tracked):
            if detail is None:
                series[sid] = None
                errors.append({"stage": "detail", "id": sid, "message": error})
            else:
                detail["score"] = rank_info.get(sid, {}).get("score")
                detail["sources"] = sources[sid]
                series[sid] = detail
    for w in watch:
        if w["status"] == "error":
            errors.append({"stage": "watchlist", "id": None, "message": f"{w['entry']}: {w.get('message', '')}"})

    failed = sum(1 for v in series.values() if v is None)
    if tracked and failed / len(tracked) > max_fail_ratio:
        raise CollectError(f"详情失败 {failed}/{len(tracked)}，超过 {max_fail_ratio:.0%}")

    return {
        "date": today.isoformat(),
        "fetched_at": now or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ranks": ranks,
        "series": series,
        "watchlist": watch,
        "errors": errors,
    }
