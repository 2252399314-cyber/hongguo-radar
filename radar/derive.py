"""由快照计算派生数据。除 derive_all 外都是纯函数。"""

from __future__ import annotations

import shutil
from datetime import date, timedelta
from typing import Any, Dict, List, Tuple

RANK_KEYS = ("hot", "real", "ai", "comic")
TYPE_KEYS = ("real", "ai", "comic")  # 判定类型时分类榜优先，综合榜不算类型
METRICS = ("hot", "fav", "like")
HISTORY_FIELDS = ("title", "tags", "eps", "first_visible", "rating_cnt", "review_cnt", "score")


def rank_days(snapshots: List[Dict[str, Any]], key: str) -> List[Tuple[str, List[Dict[str, Any]]]]:
    """按 rank_date 去重后的榜单日序列：同一个 rank_date 只保留最早那份快照。"""
    days: Dict[str, List[Dict[str, Any]]] = {}
    for snap in snapshots:
        rank = (snap.get("ranks") or {}).get(key)
        if rank and rank.get("rank_date") and rank["rank_date"] not in days:
            days[rank["rank_date"]] = rank["items"]
    return sorted(days.items())


def rank_changes(snapshots: List[Dict[str, Any]], key: str) -> Dict[str, Any]:
    days = rank_days(snapshots, key)
    if not days:
        return {"rank_date": None, "prev_rank_date": None, "items": [], "dropped": []}
    latest_date, latest = days[-1]
    has_prev = len(days) >= 2
    prev_items = days[-2][1] if has_prev else []
    prev = {it["id"]: it["rank"] for it in prev_items}
    prev_titles = {it["id"]: it.get("title", "") for it in prev_items}

    earlier = set()
    best: Dict[str, int] = {}
    for _, items in days[:-1]:
        for it in items:
            earlier.add(it["id"])
            best[it["id"]] = min(best.get(it["id"], it["rank"]), it["rank"])
    day_sets = [{it["id"] for it in items} for _, items in days]

    out = []
    for it in latest:
        sid = it["id"]
        streak = 0
        for ids in reversed(day_sets):
            if sid not in ids:
                break
            streak += 1
        if not has_prev or sid in prev:
            badge = None
        else:
            badge = "back" if sid in earlier else "new"
        out.append(
            {
                "id": sid,
                "rank": it["rank"],
                "title": it.get("title", ""),
                "status_tags": it.get("status_tags", []),
                "delta": prev[sid] - it["rank"] if sid in prev else None,
                "badge": badge,
                "streak": streak,
                "best_rank": min(best.get(sid, it["rank"]), it["rank"]),
            }
        )
    latest_ids = {it["id"] for it in latest}
    dropped = sorted(
        ({"id": sid, "last_rank": r, "title": prev_titles[sid]} for sid, r in prev.items() if sid not in latest_ids),
        key=lambda x: x["last_rank"],
    )
    return {
        "rank_date": latest_date,
        "prev_rank_date": days[-2][0] if has_prev else None,
        "items": out,
        "dropped": dropped,
    }


def series_type(snap: Dict[str, Any], sid: str) -> str:
    for key in TYPE_KEYS:
        rank = (snap.get("ranks") or {}).get(key) or {}
        if any(it["id"] == sid for it in rank.get("items", [])):
            return key
    return "unknown"


def _days_between(later: str, earlier: str) -> int:
    return (date.fromisoformat(later) - date.fromisoformat(earlier)).days


def growth(snapshots: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not snapshots:
        return {"date": None, "prev_date": None, "gap": None, "week_date": None, "items": []}
    cur = snapshots[-1]
    prev = snapshots[-2] if len(snapshots) >= 2 else None
    gap = _days_between(cur["date"], prev["date"]) if prev else None
    week_date = (date.fromisoformat(cur["date"]) - timedelta(days=7)).isoformat()
    week = next((s for s in snapshots if s["date"] == week_date), None)

    items = []
    for sid, s in cur["series"].items():
        if s is None:
            continue
        item = {
            "id": sid,
            "title": s.get("title", ""),
            "tags": s.get("tags") or [],
            "type": series_type(cur, sid),
            "watch": "watch" in (s.get("sources") or []),
            "hot": s.get("hot"),
            "fav": s.get("fav"),
            "like": s.get("like"),
            "score": s.get("score"),
            "gap": gap,
            "d_hot": None,
            "d_fav": None,
            "d_like": None,
            "r_hot": None,
            "d7_hot": None,
            "d7_fav": None,
        }
        p = prev["series"].get(sid) if prev else None
        if p:
            for m in METRICS:
                if s.get(m) is not None and p.get(m) is not None:
                    item["d_" + m] = round((s[m] - p[m]) / gap)
            if item["d_hot"] is not None and p.get("hot"):
                item["r_hot"] = round(item["d_hot"] / p["hot"], 4)
        w = week["series"].get(sid) if week else None
        if w:
            for m in ("hot", "fav"):
                if s.get(m) is not None and w.get(m) is not None:
                    item["d7_" + m] = s[m] - w[m]
        items.append(item)
    items.sort(key=lambda x: (x["d_hot"] is None, -(x["d_hot"] or 0)))
    return {
        "date": cur["date"],
        "prev_date": prev["date"] if prev else None,
        "gap": gap,
        "week_date": week_date if week else None,
        "items": items,
    }


def series_histories(snapshots: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    hist: Dict[str, Dict[str, Any]] = {}
    for snap in snapshots:
        positions = {
            key: {it["id"]: it["rank"] for it in rank.get("items", [])}
            for key, rank in (snap.get("ranks") or {}).items()
        }
        for sid, s in snap["series"].items():
            if s is None:
                continue
            h = hist.setdefault(sid, {"id": sid, "points": []})
            for field in HISTORY_FIELDS:
                value = s.get(field)
                if value is not None or field not in h:
                    h[field] = value
            h["points"].append(
                {
                    "date": snap["date"],
                    "hot": s.get("hot"),
                    "fav": s.get("fav"),
                    "like": s.get("like"),
                    "ranks": {k: pos[sid] for k, pos in positions.items() if sid in pos},
                }
            )
    return hist


def status(snapshots: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not snapshots:
        return {"date": None, "snapshots": 0}
    cur = snapshots[-1]
    errors = cur.get("errors") or []
    return {
        "date": cur["date"],
        "fetched_at": cur.get("fetched_at"),
        "snapshots": len(snapshots),
        "rank_dates": {k: ((cur.get("ranks") or {}).get(k) or {}).get("rank_date") for k in RANK_KEYS},
        "tracked": len(cur["series"]),
        "missing": sum(1 for v in cur["series"].values() if v is None),
        "error_count": len(errors),
        "errors": errors[:20],
        "watchlist": cur.get("watchlist") or [],
    }


def derive_all(store) -> None:
    snapshots = store.load_snapshots()
    store.write_derived("ranks_latest.json", {key: rank_changes(snapshots, key) for key in RANK_KEYS})
    store.write_derived("growth_latest.json", growth(snapshots))
    # 先清空再重写，快照被删除或改名后不会留下没人引用的旧文件
    shutil.rmtree(store.derived_dir / "series", ignore_errors=True)
    for sid, history in series_histories(snapshots).items():
        store.write_derived(f"series/{sid}.json", history)
    store.write_derived("status.json", status(snapshots))
