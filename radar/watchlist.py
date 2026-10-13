"""观察列表：读 watchlist.txt，把剧名或链接解析成剧集编号。"""

from __future__ import annotations

import re
from typing import Callable, Dict, List, Optional

from radar.http import FetchError
from radar.parse import ParseError

ID_PATTERNS = (
    re.compile(r"series_id=(\d{6,})"),
    re.compile(r"/player/(\d{6,})"),
    re.compile(r"^(\d{15,})$"),
)


def parse_entries(text: str) -> List[str]:
    entries: List[str] = []
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and line not in entries:
            entries.append(line)
    return entries


def extract_id(entry: str) -> Optional[str]:
    for pattern in ID_PATTERNS:
        match = pattern.search(entry)
        if match:
            return match.group(1)
    return None


def resolve(
    entries: List[str],
    search: Callable[[str], List[Dict[str, str]]],
    cache: Dict[str, Dict],
) -> List[Dict]:
    """逐条解析观察列表。剧名解析成功后会写入 cache（原地修改），以后不再搜索。"""
    results: List[Dict] = []
    for entry in entries:
        sid = extract_id(entry)
        if sid:
            results.append({"entry": entry, "status": "ok", "id": sid})
            continue
        cached = cache.get(entry)
        if cached and cached.get("status") == "ok":
            results.append(dict(cached))
            continue
        try:
            hits = search(entry)
        except (FetchError, ParseError) as exc:
            results.append({"entry": entry, "status": "error", "message": str(exc)[:200]})
            continue
        ids: List[str] = []
        for hit in hits:
            if hit["title"] == entry and hit["id"] not in ids:
                ids.append(hit["id"])
        if len(ids) == 1:
            result = {"entry": entry, "status": "ok", "id": ids[0]}
            cache[entry] = dict(result)
        elif not ids:
            result = {"entry": entry, "status": "not_found"}
        else:
            result = {"entry": entry, "status": "ambiguous", "candidates": ids}
        results.append(result)
    return results
