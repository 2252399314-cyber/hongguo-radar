# hongguo-radar 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 每天自动采集红果官网 4 个热度榜和被追踪剧的指标，算出名次变化与增速，并发布到一个 GitHub Pages 静态看板。

**Architecture:** 采集与计算是一个只依赖 Python 标准库的包 `radar/`，分成请求、解析、观察列表、存储、采集、计算、建站几个模块。每天的原始快照存为 `data/snapshots/YYYY-MM-DD.json`，计算结果写到 `data/derived/`。看板是纯静态页面（`site/`），由 `build-site` 和数据一起组装成 `_site/` 后发布。GitHub Actions 负责定时运行、提交数据、部署 Pages。

**Tech Stack:** Python ≥3.9（只用标准库；本机是 3.9.6，CI 用 3.12），unittest，原生 HTML/CSS/JS，Chart.js 4.4.1（jsDelivr CDN），GitHub Actions + Pages。

**设计文档：** `docs/superpowers/specs/2026-10-13-hongguo-radar-design.md`

**相对设计文档的细化**（都是为了实现而补的细节，不改变设计）：
1. 快照里榜单条目多存了 `title`，这样掉榜列表和详情缺失的剧也有名字可显示。
2. 首个榜单日没有可对比的前一天，所以 `badge` 一律为 `null`，不会把 100 部剧全标成 NEW。
3. 增速条目带上 `tags` 和 `watch` 字段，看板直接用。
4. 看板支持 `#s=<编号>` 地址直接打开某部剧的详情，方便分享，也方便截图验证。

## 文件结构

```
.gitignore
README.md
watchlist.txt
radar/__init__.py
radar/http.py          Fetcher：全局限速、重试、退避；两个 UA 常量
radar/parse.py         router_data / parse_rank_page / parse_detail_page / parse_search_page / parse_rank_date
radar/watchlist.py     parse_entries / extract_id / resolve
radar/store.py         Store：快照、派生结果、观察列表缓存的读写
radar/collect.py       collect()：一次完整采集，返回快照字典
radar/derive.py        rank_changes / growth / series_histories / status / derive_all
radar/site.py          build_site()：生成 _site/
radar/__main__.py      命令行：run / collect / derive / build-site
site/index.html, site/style.css, site/app.js
tests/__init__.py
tests/helpers.py       生成假页面的工具、FakeFetcher
tests/fixtures/        rank_comic_p1.html、detail.html、search.html（规划时已从线上抓取并精简，放在工作区，Task 3 提交）
tests/test_http.py, test_parse.py, test_watchlist.py, test_store.py, test_collect.py, test_derive.py, test_site.py, test_main.py
.github/workflows/daily.yml, .github/workflows/pages.yml
```

所有命令都在仓库根目录 `/Users/sjt/hongguo-radar` 下执行。运行测试的统一命令：

```bash
python3 -m unittest discover -s tests -t . -v
```

---

### Task 1: 项目骨架

**Files:**
- Create: `.gitignore`, `README.md`, `watchlist.txt`, `radar/__init__.py`, `tests/__init__.py`

- [ ] **Step 1: 写入骨架文件**

`.gitignore`：
```
_site/
_shots/
__pycache__/
*.pyc
*.tmp
.DS_Store
```

`radar/__init__.py`：
```python
"""hongguo-radar：红果官方热度榜追踪。"""
```

`tests/__init__.py`：内容为空。

`watchlist.txt`：
```
# 观察列表：每行一个剧名（必须和红果上的剧名完全一致）或红果链接，# 开头为注释。
# 修改后从下一次每日采集开始生效。
乖野之下，爱意疯长
乖野之下，爱意疯长第二季
```

`README.md`：
```markdown
# hongguo-radar

每天自动采集红果短剧官网 4 个热度榜（综合 / 真人 / AI / 漫剧）的前 100 名，
以及每部被追踪剧的热度、收藏、点赞，算出名次变化和增速，发布成看板。

- 看板：https://2252399314-cyber.github.io/hongguo-radar/
- 观察列表：编辑 `watchlist.txt`，每行一个剧名或红果链接，下一次采集生效。
- 数据：`data/snapshots/` 是每天的原始快照，`data/derived/` 是由快照算出的结果。

## 本地运行

    python3 -m unittest discover -s tests -t . -v   # 测试
    python3 -m radar run                            # 采集今天的数据并计算
    python3 -m radar build-site                     # 生成 _site/
    python3 -m http.server 8765 --directory _site   # 本地预览

`run` 的参数：`--force` 覆盖当天已有的快照；`--allow-stale` 官方榜单没更新也照常写快照；`--date YYYY-MM-DD` 指定日期。

## 数据说明

热度是红果按观看和互动综合算出的分数，不是播放量。收藏一般取整到千，点赞一般取整到万。
```

- [ ] **Step 2: 确认测试框架能跑（此时 0 个测试）**

Run: `python3 -m unittest discover -s tests -t . -v`
Expected: `Ran 0 tests` 和 `OK`

- [ ] **Step 3: Commit**

```bash
git add .gitignore README.md watchlist.txt radar/__init__.py tests/__init__.py
git commit -m "chore: project skeleton" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: HTTP 请求（限速、重试、退避）

**Files:**
- Create: `radar/http.py`
- Test: `tests/test_http.py`

- [ ] **Step 1: 写失败的测试**

`tests/test_http.py`：
```python
import unittest
import urllib.error

from radar.http import FetchError, Fetcher


class ScriptedFetcher(Fetcher):
    """用预设响应代替真实网络，用假时钟记录睡眠。"""

    def __init__(self, responses, **kwargs):
        self.now = 0.0
        self.slept = []
        self.calls = []
        self.responses = list(responses)
        super().__init__(sleep=self._fake_sleep, clock=lambda: self.now, **kwargs)

    def _fake_sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds

    def _open(self, url, ua):
        self.calls.append((url, ua))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class FetcherTest(unittest.TestCase):
    def test_returns_body_on_200(self):
        f = ScriptedFetcher([(200, {}, "好".encode("utf-8"))])
        self.assertEqual(f.get("https://x/a", ua="UA"), "好")
        self.assertEqual(f.calls, [("https://x/a", "UA")])

    def test_retries_5xx_then_succeeds(self):
        f = ScriptedFetcher([(500, {}, b""), (200, {}, b"ok")])
        self.assertEqual(f.get("https://x/a"), "ok")
        self.assertEqual(f.slept, [2])

    def test_retry_after_adds_wait(self):
        f = ScriptedFetcher([(429, {"Retry-After": "5"}, b""), (200, {}, b"ok")])
        self.assertEqual(f.get("https://x/a"), "ok")
        self.assertEqual(f.slept, [7])

    def test_retry_after_is_capped(self):
        f = ScriptedFetcher([(503, {"retry-after": "999"}, b""), (200, {}, b"ok")])
        f.get("https://x/a")
        self.assertEqual(f.slept, [2 + 45])

    def test_gives_up_after_three_retries(self):
        f = ScriptedFetcher([(503, {}, b"")] * 4)
        with self.assertRaises(FetchError) as ctx:
            f.get("https://x/a")
        self.assertIn("HTTP 503", str(ctx.exception))
        self.assertEqual(len(f.calls), 4)
        self.assertEqual(f.slept, [2, 4, 8])

    def test_no_retry_on_404(self):
        f = ScriptedFetcher([(404, {}, b"")])
        with self.assertRaises(FetchError):
            f.get("https://x/a")
        self.assertEqual(len(f.calls), 1)

    def test_network_error_is_retried(self):
        f = ScriptedFetcher([urllib.error.URLError("boom"), (200, {}, b"ok")])
        self.assertEqual(f.get("https://x/a"), "ok")

    def test_throttle_spaces_requests(self):
        f = ScriptedFetcher([(200, {}, b"1"), (200, {}, b"2")], min_interval=0.5)
        f.get("https://x/a")
        f.get("https://x/b")
        self.assertEqual(f.slept, [0.5])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行，确认失败**

Run: `python3 -m unittest tests.test_http -v`
Expected: 报 `ModuleNotFoundError: No module named 'radar.http'`

- [ ] **Step 3: 实现**

`radar/http.py`：
```python
"""带全局限速、重试和退避的 HTTP GET（只用标准库）。"""

from __future__ import annotations

import threading
import time
import urllib.error
import urllib.request
from typing import Callable, Dict, Tuple

BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
# 红果的榜单页只对搜索引擎爬虫直接输出榜单数据。
SPIDER_UA = "Mozilla/5.0 (compatible; Baiduspider/2.0; +http://www.baidu.com/search/spider.html)"


class FetchError(Exception):
    """请求最终失败：重试用尽，或遇到不值得重试的状态码。"""


class Fetcher:
    def __init__(
        self,
        min_interval: float = 0.5,
        timeout: float = 20,
        backoff: Tuple[float, ...] = (2, 4, 8),
        max_retry_after: float = 45,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.min_interval = min_interval
        self.timeout = timeout
        self.backoff = backoff
        self.max_retry_after = max_retry_after
        self._sleep = sleep
        self._clock = clock
        self._lock = threading.Lock()
        self._next_at = 0.0

    def get(self, url: str, ua: str = BROWSER_UA) -> str:
        last = "no attempt"
        for attempt in range(len(self.backoff) + 1):
            self._throttle()
            extra = 0.0
            try:
                status, headers, body = self._open(url, ua)
            except OSError as exc:  # URLError、超时、连接重置都是 OSError
                last = f"{type(exc).__name__}: {exc}"
            else:
                if status == 200:
                    return body.decode("utf-8", errors="replace")
                last = f"HTTP {status}"
                if status == 429 or status >= 500:
                    extra = self._retry_after(headers)
                else:
                    raise FetchError(f"{url}: {last}")
            if attempt < len(self.backoff):
                self._sleep(self.backoff[attempt] + extra)
        raise FetchError(f"{url}: {last}")

    def _throttle(self) -> None:
        """全局限速：相邻两次请求的发起间隔不少于 min_interval（多线程共用）。"""
        with self._lock:
            now = self._clock()
            wait = self._next_at - now
            if wait > 0:
                self._sleep(wait)
                now = self._clock()
            self._next_at = now + self.min_interval

    def _retry_after(self, headers: Dict[str, str]) -> float:
        for key, value in headers.items():
            if key.lower() == "retry-after":
                try:
                    return min(float(value), self.max_retry_after)
                except ValueError:
                    return 0.0
        return 0.0

    def _open(self, url: str, ua: str) -> Tuple[int, Dict[str, str], bytes]:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": ua,
                "Accept": "text/html,application/json,*/*",
                "Accept-Language": "zh-CN,zh;q=0.9",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as resp:
                return resp.status, dict(resp.headers.items()), resp.read()
        except urllib.error.HTTPError as exc:
            headers = dict(exc.headers.items()) if exc.headers else {}
            return exc.code, headers, b""
```

- [ ] **Step 4: 运行，确认通过**

Run: `python3 -m unittest tests.test_http -v`
Expected: 8 个测试全部 `ok`

- [ ] **Step 5: Commit**

```bash
git add radar/http.py tests/test_http.py
git commit -m "feat: rate-limited fetcher with retry and backoff" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: 页面解析

**Files:**
- Create: `radar/parse.py`
- Test: `tests/test_parse.py`
- 样本：`tests/fixtures/rank_comic_p1.html`、`detail.html`、`search.html`（规划时已从线上页面精简得到，放在工作区里，本任务一并提交）

样本里的关键值（测试用）：
- `rank_comic_p1.html`：`updatedText` 为「10月13日已更新 · …」，`totalPages` 为 5。共 3 条：第 1 名 `7691228619774905368`「聚宝仙盆之杂灵根才是真BOSS第十三季」（评分 9.0，标签玄幻/逆袭/修真）；第 2 名 `7692463987333532697`；第 5 名 `7694116863835376664`（`scoreText` 为 null，`statusTags` 为 ["新剧"]）。
- `detail.html`：「乖野之下，爱意疯长」，111 集，`first_visible_time` "1787995680"，热度 43345060，收藏 "1811000"，点赞 "2600000"，评分人数 "4820"，评论 "1256"。注意有些数字是字符串。
- `search.html`：3 条 `doc_type` 23 的结果，前两条是两季《乖野之下》。

- [ ] **Step 1: 写失败的测试**

`tests/test_parse.py`：
```python
import unittest
from datetime import date
from pathlib import Path

from radar.parse import (
    ParseError,
    parse_detail_page,
    parse_rank_date,
    parse_rank_page,
    parse_search_page,
    router_data,
)

FIXTURES = Path(__file__).parent / "fixtures"
TODAY = date(2026, 10, 13)


def load(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def wrap(json_text):
    return "<script>_ROUTER_DATA = " + json_text + ";\nfunction runWindowFn(){}</script>"


class RouterDataTest(unittest.TestCase):
    def test_missing_marker_raises(self):
        with self.assertRaises(ParseError):
            router_data("<html></html>")

    def test_reads_json_followed_by_js(self):
        self.assertIn("detail_page", router_data(load("detail.html"))["loaderData"])

    def test_missing_loader_data_raises(self):
        with self.assertRaises(ParseError):
            router_data(wrap('{"foo": 1}'))


class RankDateTest(unittest.TestCase):
    def test_same_year(self):
        self.assertEqual(parse_rank_date("10月13日已更新 · 基于红果内观看", TODAY), "2026-10-13")

    def test_cross_year(self):
        self.assertEqual(parse_rank_date("12月31日已更新", date(2027, 1, 1)), "2026-12-31")

    def test_missing(self):
        self.assertIsNone(parse_rank_date("已更新", TODAY))


class RankPageTest(unittest.TestCase):
    def setUp(self):
        self.page = parse_rank_page(load("rank_comic_p1.html"), TODAY)

    def test_date_and_pages(self):
        self.assertEqual(self.page["rank_date"], "2026-10-13")
        self.assertEqual(self.page["total_pages"], 5)

    def test_first_item(self):
        self.assertEqual(len(self.page["items"]), 3)
        self.assertEqual(
            self.page["items"][0],
            {
                "id": "7691228619774905368",
                "rank": 1,
                "title": "聚宝仙盆之杂灵根才是真BOSS第十三季",
                "tags": ["玄幻", "逆袭", "修真"],
                "status_tags": [],
                "score": 9.0,
            },
        )

    def test_null_score_and_status_tags(self):
        item = self.page["items"][2]
        self.assertEqual(item["rank"], 5)
        self.assertIsNone(item["score"])
        self.assertEqual(item["status_tags"], ["新剧"])

    def test_empty_content_gives_no_items(self):
        html = wrap('{"loaderData":{"rank_hot-drama/page":{"updatedText":"10月13日已更新","content":{}}}}')
        page = parse_rank_page(html, TODAY)
        self.assertEqual(page["items"], [])
        self.assertIsNone(page["total_pages"])


class DetailPageTest(unittest.TestCase):
    def test_fields(self):
        self.assertEqual(
            parse_detail_page(load("detail.html")),
            {
                "title": "乖野之下，爱意疯长",
                "tags": ["恋爱", "都市", "豪门"],
                "eps": 111,
                "first_visible": 1787995680,
                "status": 1,
                "hot": 43345060,
                "fav": 1811000,
                "like": 2600000,
                "rating_cnt": 4820,
                "review_cnt": 1256,
            },
        )

    def test_missing_detail_raises(self):
        with self.assertRaises(ParseError):
            parse_detail_page(wrap('{"loaderData":{"detail_page":{}}}'))


class SearchPageTest(unittest.TestCase):
    def test_results(self):
        results = parse_search_page(load("search.html"))
        self.assertEqual(len(results), 3)
        self.assertEqual(
            results[:2],
            [
                {"title": "乖野之下，爱意疯长", "id": "7677823149873843224"},
                {"title": "乖野之下，爱意疯长第二季", "id": "7692068202615933977"},
            ],
        )

    def test_skips_other_doc_types(self):
        html = wrap(
            '{"loaderData":{"search_(keyword)/page":{"searchList":'
            '[{"doc_type":1,"name":"某演员","keyword":"123"}]}}}'
        )
        self.assertEqual(parse_search_page(html), [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行，确认失败**

Run: `python3 -m unittest tests.test_parse -v`
Expected: 报 `ModuleNotFoundError: No module named 'radar.parse'`

- [ ] **Step 3: 实现**

`radar/parse.py`：
```python
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
```

- [ ] **Step 4: 运行，确认通过**

Run: `python3 -m unittest tests.test_parse -v`
Expected: 14 个测试全部 `ok`

- [ ] **Step 5: Commit**

```bash
git add radar/parse.py tests/test_parse.py tests/fixtures
git commit -m "feat: parse rank, detail and search pages" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: 观察列表

**Files:**
- Create: `radar/watchlist.py`
- Test: `tests/test_watchlist.py`

- [ ] **Step 1: 写失败的测试**

`tests/test_watchlist.py`：
```python
import unittest

from radar.http import FetchError
from radar.watchlist import extract_id, parse_entries, resolve


class ParseEntriesTest(unittest.TestCase):
    def test_skips_comments_blank_and_duplicates(self):
        text = "# 注释\n\n  剧A  \n剧A\nhttps://hongguoduanju.com/player/7692068202615933977\n"
        self.assertEqual(
            parse_entries(text),
            ["剧A", "https://hongguoduanju.com/player/7692068202615933977"],
        )


class ExtractIdTest(unittest.TestCase):
    def test_detail_link(self):
        self.assertEqual(
            extract_id("https://hongguoduanju.com/detail?series_id=7677823149873843224"),
            "7677823149873843224",
        )

    def test_player_link(self):
        self.assertEqual(
            extract_id("https://hongguoduanju.com/player/7692068202615933977?from=x"),
            "7692068202615933977",
        )

    def test_bare_id(self):
        self.assertEqual(extract_id("7677823149873843224"), "7677823149873843224")

    def test_title_has_no_id(self):
        self.assertIsNone(extract_id("乖野之下，爱意疯长"))


class ResolveTest(unittest.TestCase):
    def test_link_needs_no_search(self):
        def search(_):
            raise AssertionError("不应该搜索")

        result = resolve(["https://hongguoduanju.com/player/900000000000000001"], search, {})
        self.assertEqual(result, [{"entry": "https://hongguoduanju.com/player/900000000000000001", "status": "ok", "id": "900000000000000001"}])

    def test_unique_exact_match_is_cached(self):
        cache = {}
        hits = [{"title": "剧A", "id": "1"}, {"title": "剧A第二季", "id": "2"}]
        result = resolve(["剧A"], lambda q: hits, cache)
        self.assertEqual(result, [{"entry": "剧A", "status": "ok", "id": "1"}])
        self.assertEqual(cache["剧A"], {"entry": "剧A", "status": "ok", "id": "1"})

    def test_cache_hit_skips_search(self):
        def search(_):
            raise AssertionError("不应该搜索")

        cache = {"剧A": {"entry": "剧A", "status": "ok", "id": "1"}}
        self.assertEqual(resolve(["剧A"], search, cache), [{"entry": "剧A", "status": "ok", "id": "1"}])

    def test_not_found(self):
        result = resolve(["剧B"], lambda q: [{"title": "剧B第二季", "id": "2"}], {})
        self.assertEqual(result, [{"entry": "剧B", "status": "not_found"}])

    def test_ambiguous(self):
        hits = [{"title": "剧C", "id": "3"}, {"title": "剧C", "id": "4"}]
        cache = {}
        result = resolve(["剧C"], lambda q: hits, cache)
        self.assertEqual(result, [{"entry": "剧C", "status": "ambiguous", "candidates": ["3", "4"]}])
        self.assertEqual(cache, {})

    def test_search_error_is_reported_not_raised(self):
        def search(_):
            raise FetchError("https://x: HTTP 500")

        result = resolve(["剧D"], search, {})
        self.assertEqual(result[0]["status"], "error")
        self.assertIn("HTTP 500", result[0]["message"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行，确认失败**

Run: `python3 -m unittest tests.test_watchlist -v`
Expected: 报 `ModuleNotFoundError: No module named 'radar.watchlist'`

- [ ] **Step 3: 实现**

`radar/watchlist.py`：
```python
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
```

- [ ] **Step 4: 运行，确认通过**

Run: `python3 -m unittest tests.test_watchlist -v`
Expected: 11 个测试全部 `ok`

- [ ] **Step 5: Commit**

```bash
git add radar/watchlist.py tests/test_watchlist.py
git commit -m "feat: watchlist parsing and name resolution" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: 存储

**Files:**
- Create: `radar/store.py`
- Test: `tests/test_store.py`

- [ ] **Step 1: 写失败的测试**

`tests/test_store.py`：
```python
import tempfile
import unittest
from pathlib import Path

from radar.store import Store


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_snapshot_roundtrip_sorted(self):
        self.assertFalse(self.store.has_snapshot("2026-10-14"))
        self.store.write_snapshot({"date": "2026-10-14", "series": {"1": {"title": "剧"}}})
        self.store.write_snapshot({"date": "2026-10-13", "series": {}})
        self.assertTrue(self.store.has_snapshot("2026-10-14"))
        self.assertEqual([s["date"] for s in self.store.load_snapshots()], ["2026-10-13", "2026-10-14"])
        text = self.store.snapshot_path("2026-10-14").read_text(encoding="utf-8")
        self.assertIn("剧", text)  # ensure_ascii=False

    def test_load_snapshots_when_empty(self):
        self.assertEqual(self.store.load_snapshots(), [])

    def test_write_derived_is_compact_and_nested(self):
        self.store.write_derived("series/123.json", {"a": [1, 2]})
        path = Path(self.tmp.name) / "data" / "derived" / "series" / "123.json"
        self.assertEqual(path.read_text(encoding="utf-8").strip(), '{"a":[1,2]}')

    def test_watchlist_text_missing_is_empty(self):
        self.assertEqual(self.store.watchlist_text(), "")
        (Path(self.tmp.name) / "watchlist.txt").write_text("剧A\n", encoding="utf-8")
        self.assertEqual(self.store.watchlist_text(), "剧A\n")

    def test_watch_cache_roundtrip(self):
        self.assertEqual(self.store.load_watch_cache(), {})
        self.store.save_watch_cache({"剧A": {"status": "ok", "id": "1"}})
        self.assertEqual(self.store.load_watch_cache(), {"剧A": {"status": "ok", "id": "1"}})


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行，确认失败**

Run: `python3 -m unittest tests.test_store -v`
Expected: 报 `ModuleNotFoundError: No module named 'radar.store'`

- [ ] **Step 3: 实现**

`radar/store.py`：
```python
"""数据目录读写。JSON 一律 UTF-8；写入先写临时文件再替换，避免写一半。"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List


def write_json(path: Path, obj: Any, compact: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        if compact:
            json.dump(obj, fh, ensure_ascii=False, separators=(",", ":"))
        else:
            json.dump(obj, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    os.replace(tmp, path)


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


class Store:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.snapshots_dir = self.root / "data" / "snapshots"
        self.derived_dir = self.root / "data" / "derived"
        self.watch_cache_path = self.root / "data" / "watchlist_resolved.json"
        self.watchlist_path = self.root / "watchlist.txt"

    def snapshot_path(self, day: str) -> Path:
        return self.snapshots_dir / f"{day}.json"

    def has_snapshot(self, day: str) -> bool:
        return self.snapshot_path(day).exists()

    def write_snapshot(self, snap: Dict[str, Any]) -> None:
        write_json(self.snapshot_path(snap["date"]), snap)

    def load_snapshots(self) -> List[Dict[str, Any]]:
        return [read_json(p) for p in sorted(self.snapshots_dir.glob("*.json"))]

    def write_derived(self, rel: str, obj: Any) -> None:
        write_json(self.derived_dir / rel, obj, compact=True)

    def watchlist_text(self) -> str:
        if not self.watchlist_path.exists():
            return ""
        return self.watchlist_path.read_text(encoding="utf-8")

    def load_watch_cache(self) -> Dict[str, Any]:
        return read_json(self.watch_cache_path, {})

    def save_watch_cache(self, cache: Dict[str, Any]) -> None:
        write_json(self.watch_cache_path, cache)
```

- [ ] **Step 4: 运行，确认通过**

Run: `python3 -m unittest tests.test_store -v`
Expected: 5 个测试全部 `ok`

- [ ] **Step 5: Commit**

```bash
git add radar/store.py tests/test_store.py
git commit -m "feat: snapshot and derived data store" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: 采集

**Files:**
- Create: `radar/collect.py`, `tests/helpers.py`
- Test: `tests/test_collect.py`

- [ ] **Step 1: 写测试工具**

`tests/helpers.py`：
```python
"""测试用：生成和红果页面结构一致的假页面，以及按 URL 返回页面的 FakeFetcher。"""

import json

from radar.http import FetchError


def page(loader_data):
    body = json.dumps({"loaderData": loader_data, "errors": None}, ensure_ascii=False)
    return "<html><body><script>_ROUTER_DATA = " + body + ";\nfunction runWindowFn(){}</script></body></html>"


def rank_html(slug, updated_text, items, total_pages):
    """items: [(编号, 名次), ...]"""
    rank_list = [
        {
            "id": sid,
            "seriesId": sid,
            "rank": rank,
            "title": "剧" + sid,
            "scoreText": "评分8.5",
            "statusTags": [],
            "tags": ["都市"],
        }
        for sid, rank in items
    ]
    return page(
        {
            "rank_layout": None,
            "rank_" + slug + "/page": {
                "updatedText": updated_text,
                "content": {"rankList": rank_list, "pagination": {"totalPages": total_pages}},
            },
        }
    )


def detail_html(sid, hot=1000, fav=100, like=10):
    return page(
        {
            "detail_page": {
                "seriesDetail": {
                    "series_id": sid,
                    "series_name": "剧" + sid,
                    "episode_cnt": 80,
                    "first_visible_time": "1780000000",
                    "tags": ["都市"],
                    "series_episode_info": {"series_status": 1},
                },
                "seriesSocialInfo": {
                    "hot_score_data": {"score": hot},
                    "series_favorite_count": str(fav),
                    "series_like_count": str(like),
                    "rating_count": "5",
                    "reviews": {"total_count": "2"},
                },
            }
        }
    )


def search_html(results):
    """results: [(剧名, 编号), ...]"""
    return page(
        {
            "search_(keyword)/page": {
                "searchList": [
                    {"doc_type": 23, "name": title, "keyword": sid, "video_data": {"series_id": sid}}
                    for title, sid in results
                ]
            }
        }
    )


class FakeFetcher:
    def __init__(self, pages):
        self.pages = dict(pages)
        self.calls = []

    def get(self, url, ua=None):
        self.calls.append((url, ua))
        if url not in self.pages:
            raise FetchError(url + ": HTTP 404")
        return self.pages[url]
```

- [ ] **Step 2: 写失败的测试**

`tests/test_collect.py`：
```python
import unittest
from datetime import date

from radar import collect as C
from radar.http import SPIDER_UA
from tests.helpers import FakeFetcher, detail_html, rank_html, search_html

TODAY = date(2026, 10, 14)
DEFAULT_RANKS = {
    "hot": [("1", 1), ("2", 2), ("3", 3)],
    "real": [("1", 1), ("4", 2), ("5", 3)],
    "ai": [("2", 1), ("6", 2), ("7", 3)],
    "comic": [("8", 1), ("9", 2), ("10", 3)],
}


def build_pages(updated_text="10月14日已更新", ranks=None, details=(), extra=None):
    """每个榜拆成两页；为所有在榜的剧和 details 里的剧生成详情页。"""
    ranks = ranks or DEFAULT_RANKS
    pages = {}
    for key, items in ranks.items():
        slug = C.RANK_SLUGS[key]
        pages[C.rank_url(slug, 1)] = rank_html(slug, updated_text, items[:2], 2)
        pages[C.rank_url(slug, 2)] = rank_html(slug, updated_text, items[2:], 2)
    ids = {sid for items in ranks.values() for sid, _ in items} | set(details)
    for sid in ids:
        pages[C.detail_url(sid)] = detail_html(sid)
    pages.update(extra or {})
    return pages


def run(pages, watch_entries=(), watch_cache=None, history=(), fetcher=None, **kwargs):
    fetcher = fetcher or FakeFetcher(pages)
    return C.collect(
        fetcher,
        TODAY,
        list(watch_entries),
        {} if watch_cache is None else watch_cache,
        list(history),
        now="2026-10-14T04:00:00Z",
        min_rank_items=3,
        **kwargs,
    )


class CollectTest(unittest.TestCase):
    def test_happy_path(self):
        snap = run(build_pages())
        self.assertEqual(snap["date"], "2026-10-14")
        self.assertEqual(snap["fetched_at"], "2026-10-14T04:00:00Z")
        self.assertEqual(set(snap["ranks"]), {"hot", "real", "ai", "comic"})
        self.assertEqual(snap["ranks"]["hot"]["rank_date"], "2026-10-14")
        self.assertEqual(
            snap["ranks"]["hot"]["items"],
            [
                {"id": "1", "rank": 1, "title": "剧1", "status_tags": []},
                {"id": "2", "rank": 2, "title": "剧2", "status_tags": []},
                {"id": "3", "rank": 3, "title": "剧3", "status_tags": []},
            ],
        )
        self.assertEqual(len(snap["series"]), 10)
        one = snap["series"]["1"]
        self.assertEqual(one["sources"], ["rank:hot", "rank:real"])
        self.assertEqual(one["score"], 8.5)
        self.assertEqual((one["hot"], one["fav"], one["like"]), (1000, 100, 10))
        self.assertEqual(snap["errors"], [])
        self.assertEqual(snap["watchlist"], [])

    def test_rank_pages_use_spider_ua(self):
        fetcher = FakeFetcher(build_pages())
        run(None, fetcher=fetcher)
        for url, ua in fetcher.calls:
            if "/rank/" in url:
                self.assertEqual(ua, SPIDER_UA)
            else:
                self.assertNotEqual(ua, SPIDER_UA)

    def test_not_updated_raises(self):
        with self.assertRaises(C.NotUpdated):
            run(build_pages(updated_text="10月13日已更新"))

    def test_allow_stale_still_writes(self):
        snap = run(build_pages(updated_text="10月13日已更新"), allow_stale=True)
        self.assertEqual(snap["ranks"]["hot"]["rank_date"], "2026-10-13")
        self.assertEqual(len(snap["series"]), 10)

    def test_too_few_items_raises(self):
        with self.assertRaises(C.CollectError):
            run(build_pages(ranks={"hot": [("1", 1), ("2", 2)]}))

    def test_watchlist_and_recently_dropped_are_tracked(self):
        pages = build_pages(
            details=("800", "900000", "77"),
            extra={C.search_url("剧X"): search_html([("剧X", "800"), ("剧X外传", "801")])},
        )
        history = [
            {"date": "2026-09-01", "ranks": {"hot": {"rank_date": "2026-09-01", "items": [{"id": "66", "rank": 1}]}}, "series": {}},
            {"date": "2026-10-10", "ranks": {"hot": {"rank_date": "2026-10-10", "items": [{"id": "77", "rank": 5}]}}, "series": {}},
        ]
        # 链接里的编号至少 6 位才会被识别（见 watchlist.ID_PATTERNS）
        snap = run(pages, watch_entries=["剧X", "https://hongguoduanju.com/player/900000"], history=history)
        self.assertEqual(snap["series"]["800"]["sources"], ["watch"])
        self.assertEqual(snap["series"]["900000"]["sources"], ["watch"])
        self.assertEqual(snap["series"]["77"]["sources"], ["recent"])
        self.assertNotIn("66", snap["series"])
        self.assertEqual(
            snap["watchlist"],
            [
                {"entry": "剧X", "status": "ok", "id": "800"},
                {"entry": "https://hongguoduanju.com/player/900000", "status": "ok", "id": "900000"},
            ],
        )

    def test_detail_failures_within_limit(self):
        pages = build_pages()
        del pages[C.detail_url("10")]
        snap = run(pages)
        self.assertIsNone(snap["series"]["10"])
        self.assertEqual(len(snap["errors"]), 1)
        self.assertEqual(snap["errors"][0]["stage"], "detail")
        self.assertEqual(snap["errors"][0]["id"], "10")

    def test_detail_failures_over_limit_raise(self):
        pages = build_pages()
        del pages[C.detail_url("9")]
        del pages[C.detail_url("10")]
        with self.assertRaises(C.CollectError):
            run(pages)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: 运行，确认失败**

Run: `python3 -m unittest tests.test_collect -v`
Expected: 报 `ImportError`（`radar.collect` 不存在）

- [ ] **Step 4: 实现**

`radar/collect.py`：
```python
"""每日采集：榜单 → 观察列表 → 追踪集合 → 详情，产出一份快照字典。"""

from __future__ import annotations

import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from radar.http import SPIDER_UA, FetchError
from radar.parse import ParseError, parse_detail_page, parse_rank_page, parse_search_page
from radar.watchlist import resolve

BASE = "https://hongguoduanju.com"
RANK_SLUGS = {"hot": "hot-drama", "real": "hot-real-drama", "ai": "hot-ai-drama", "comic": "hot-comic-drama"}
MAX_RANK_PAGES = 5
MIN_RANK_ITEMS = 80
MAX_DETAIL_FAIL_RATIO = 0.10
LOOKBACK_DAYS = 14


class CollectError(Exception):
    """数据不可信，本次不写快照。"""


class NotUpdated(Exception):
    """官方榜单还没更新到今天。"""


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
        if rank["rank_date"] is None or len(rank["items"]) < min_rank_items:
            raise CollectError(f"{key} 榜异常: {len(rank['items'])} 条, 榜单日期 {rank['rank_date']}")
        ranks[key] = {
            "rank_date": rank["rank_date"],
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

    stale = [k for k, r in ranks.items() if r["rank_date"] != today.isoformat()]
    if stale and not allow_stale:
        detail = ", ".join(f"{k}={ranks[k]['rank_date']}" for k in stale)
        raise NotUpdated(f"榜单尚未更新到 {today.isoformat()}: {detail}")

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
    def fetch_detail(sid: str):
        try:
            return sid, parse_detail_page(fetcher.get(detail_url(sid))), None
        except (FetchError, ParseError) as exc:
            return sid, None, str(exc)[:300]

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
```

- [ ] **Step 5: 运行，确认通过**

Run: `python3 -m unittest tests.test_collect -v`
Expected: 8 个测试全部 `ok`

- [ ] **Step 6: 跑全部测试**

Run: `python3 -m unittest discover -s tests -t . -v`
Expected: 全部 `ok`

- [ ] **Step 7: Commit**

```bash
git add radar/collect.py tests/helpers.py tests/test_collect.py
git commit -m "feat: daily collection of ranks, watchlist and details" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: 计算（榜单变化、增速、单剧历史、状态）

**Files:**
- Create: `radar/derive.py`
- Test: `tests/test_derive.py`

- [ ] **Step 1: 写失败的测试**

`tests/test_derive.py`：
```python
import tempfile
import unittest
from pathlib import Path

from radar.derive import derive_all, growth, rank_changes, series_histories, status
from radar.store import Store, read_json


def snap(day, ranks=None, series=None, rank_date=None, errors=None):
    """ranks: {榜: [编号, ...]}，名次即列表顺序；series: {编号: (热度, 收藏, 点赞) 或 None}"""
    return {
        "date": day,
        "fetched_at": day + "T04:00:00Z",
        "ranks": {
            key: {
                "rank_date": rank_date or day,
                "items": [
                    {"id": sid, "rank": i + 1, "title": "剧" + sid, "status_tags": []}
                    for i, sid in enumerate(ids)
                ],
            }
            for key, ids in (ranks or {}).items()
        },
        "series": {
            sid: None
            if value is None
            else {
                "title": "剧" + sid,
                "tags": ["都市"],
                "eps": 10,
                "first_visible": 1,
                "hot": value[0],
                "fav": value[1],
                "like": value[2],
                "rating_cnt": 1,
                "review_cnt": 1,
                "score": None,
                "sources": [],
            }
            for sid, value in (series or {}).items()
        },
        "watchlist": [],
        "errors": errors or [],
    }


class RankChangesTest(unittest.TestCase):
    def test_first_day_has_no_badges(self):
        result = rank_changes([snap("2026-10-01", {"hot": ["a", "b"]})], "hot")
        self.assertEqual(result["rank_date"], "2026-10-01")
        self.assertIsNone(result["prev_rank_date"])
        self.assertEqual(result["dropped"], [])
        first = result["items"][0]
        self.assertEqual(
            first,
            {"id": "a", "rank": 1, "title": "剧a", "status_tags": [], "delta": None, "badge": None, "streak": 1, "best_rank": 1},
        )

    def test_moves_new_and_dropped(self):
        result = rank_changes(
            [snap("2026-10-01", {"hot": ["a", "b", "c"]}), snap("2026-10-02", {"hot": ["b", "a", "d"]})],
            "hot",
        )
        items = {it["id"]: it for it in result["items"]}
        self.assertEqual(items["b"]["delta"], 1)
        self.assertEqual(items["b"]["streak"], 2)
        self.assertEqual(items["b"]["best_rank"], 1)
        self.assertEqual(items["a"]["delta"], -1)
        self.assertEqual(items["d"]["badge"], "new")
        self.assertIsNone(items["d"]["delta"])
        self.assertEqual(result["dropped"], [{"id": "c", "last_rank": 3, "title": "剧c"}])
        self.assertEqual(result["prev_rank_date"], "2026-10-01")

    def test_back_on_list(self):
        result = rank_changes(
            [
                snap("2026-10-01", {"hot": ["a", "b"]}),
                snap("2026-10-02", {"hot": ["b"]}),
                snap("2026-10-03", {"hot": ["a", "b"]}),
            ],
            "hot",
        )
        items = {it["id"]: it for it in result["items"]}
        self.assertEqual(items["a"]["badge"], "back")
        self.assertEqual(items["a"]["streak"], 1)
        self.assertEqual(items["a"]["best_rank"], 1)
        self.assertEqual(items["b"]["streak"], 3)
        self.assertEqual(items["b"]["delta"], -1)

    def test_stale_snapshot_not_double_counted(self):
        result = rank_changes(
            [
                snap("2026-10-01", {"hot": ["a"]}),
                snap("2026-10-02", {"hot": ["a"]}, rank_date="2026-10-01"),
                snap("2026-10-03", {"hot": ["a"]}),
            ],
            "hot",
        )
        self.assertEqual(result["items"][0]["streak"], 2)
        self.assertEqual(result["prev_rank_date"], "2026-10-01")

    def test_missing_rank_key(self):
        self.assertEqual(
            rank_changes([snap("2026-10-01", {"hot": ["a"]})], "comic"),
            {"rank_date": None, "prev_rank_date": None, "items": [], "dropped": []},
        )


class GrowthTest(unittest.TestCase):
    def test_daily_deltas(self):
        result = growth(
            [snap("2026-10-01", series={"x": (1000, 100, 10)}), snap("2026-10-02", series={"x": (1500, 130, 10)})]
        )
        item = result["items"][0]
        self.assertEqual((result["date"], result["prev_date"], result["gap"]), ("2026-10-02", "2026-10-01", 1))
        self.assertEqual((item["d_hot"], item["d_fav"], item["d_like"]), (500, 30, 0))
        self.assertEqual(item["r_hot"], 0.5)
        self.assertIsNone(item["d7_hot"])
        self.assertEqual(item["tags"], ["都市"])
        self.assertFalse(item["watch"])

    def test_gap_is_averaged(self):
        result = growth(
            [snap("2026-10-01", series={"x": (1000, 100, 10)}), snap("2026-10-03", series={"x": (1600, 100, 10)})]
        )
        item = result["items"][0]
        self.assertEqual(item["gap"], 2)
        self.assertEqual(item["d_hot"], 300)
        self.assertEqual(item["r_hot"], 0.3)

    def test_negative_growth_kept(self):
        result = growth(
            [snap("2026-10-01", series={"x": (1000, 100, 10)}), snap("2026-10-02", series={"x": (900, 100, 10)})]
        )
        self.assertEqual(result["items"][0]["d_hot"], -100)
        self.assertEqual(result["items"][0]["r_hot"], -0.1)

    def test_null_series_skipped(self):
        result = growth(
            [snap("2026-10-01", series={"y": None}), snap("2026-10-02", series={"y": (10, 1, 1), "z": None})]
        )
        self.assertEqual([it["id"] for it in result["items"]], ["y"])
        self.assertIsNone(result["items"][0]["d_hot"])

    def test_seven_day_delta(self):
        result = growth(
            [
                snap("2026-10-01", series={"x": (1000, 100, 1)}),
                snap("2026-10-07", series={"x": (1600, 160, 1)}),
                snap("2026-10-08", series={"x": (1700, 170, 1)}),
            ]
        )
        item = result["items"][0]
        self.assertEqual(result["week_date"], "2026-10-01")
        self.assertEqual((item["d_hot"], item["d7_hot"], item["d7_fav"]), (100, 700, 70))

    def test_type_and_watch(self):
        s = snap("2026-10-01", {"hot": ["a"], "real": ["a"], "comic": ["b"]}, {"a": (1, 1, 1), "b": (1, 1, 1), "c": (1, 1, 1)})
        s["series"]["c"]["sources"] = ["watch"]
        items = {it["id"]: it for it in growth([s])["items"]}
        self.assertEqual((items["a"]["type"], items["b"]["type"], items["c"]["type"]), ("real", "comic", "unknown"))
        self.assertTrue(items["c"]["watch"])

    def test_sorted_by_hot_delta_none_last(self):
        result = growth(
            [
                snap("2026-10-01", series={"p": (100, 1, 1), "q": (100, 1, 1)}),
                snap("2026-10-02", series={"p": (150, 1, 1), "q": (300, 1, 1), "n": (5, 1, 1)}),
            ]
        )
        self.assertEqual([it["id"] for it in result["items"]], ["q", "p", "n"])

    def test_empty(self):
        self.assertEqual(growth([])["items"], [])


class HistoryAndStatusTest(unittest.TestCase):
    def test_series_histories(self):
        hist = series_histories(
            [
                snap("2026-10-01", {"hot": ["a"]}, {"a": (100, 10, 1)}),
                snap("2026-10-02", {}, {"a": (200, 20, 2), "b": None}),
            ]
        )
        self.assertEqual(list(hist), ["a"])
        self.assertEqual(hist["a"]["title"], "剧a")
        self.assertEqual(
            hist["a"]["points"],
            [
                {"date": "2026-10-01", "hot": 100, "fav": 10, "like": 1, "ranks": {"hot": 1}},
                {"date": "2026-10-02", "hot": 200, "fav": 20, "like": 2, "ranks": {}},
            ],
        )

    def test_status(self):
        s = snap(
            "2026-10-02",
            {"hot": ["a"]},
            {"a": (1, 1, 1), "b": None},
            errors=[{"stage": "detail", "id": "b", "message": "x"}, {"stage": "detail", "id": "c", "message": "y"}],
        )
        result = status([snap("2026-10-01"), s])
        self.assertEqual(result["date"], "2026-10-02")
        self.assertEqual(result["snapshots"], 2)
        self.assertEqual(result["tracked"], 2)
        self.assertEqual(result["missing"], 1)
        self.assertEqual(result["error_count"], 2)
        self.assertEqual(result["rank_dates"], {"hot": "2026-10-02", "real": None, "ai": None, "comic": None})

    def test_derive_all_writes_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp))
            store.write_snapshot(snap("2026-10-01", {"hot": ["a"]}, {"a": (100, 10, 1)}))
            store.write_snapshot(snap("2026-10-02", {"hot": ["a"]}, {"a": (150, 12, 1)}))
            derive_all(store)
            derived = Path(tmp) / "data" / "derived"
            self.assertEqual(read_json(derived / "ranks_latest.json")["hot"]["rank_date"], "2026-10-02")
            self.assertEqual(read_json(derived / "growth_latest.json")["items"][0]["d_hot"], 50)
            self.assertEqual(read_json(derived / "status.json")["date"], "2026-10-02")
            self.assertEqual(len(read_json(derived / "series" / "a.json")["points"]), 2)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行，确认失败**

Run: `python3 -m unittest tests.test_derive -v`
Expected: 报 `ModuleNotFoundError: No module named 'radar.derive'`

- [ ] **Step 3: 实现**

`radar/derive.py`：
```python
"""由快照计算派生数据。除 derive_all 外都是纯函数。"""

from __future__ import annotations

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
    for sid, history in series_histories(snapshots).items():
        store.write_derived(f"series/{sid}.json", history)
    store.write_derived("status.json", status(snapshots))
```

- [ ] **Step 4: 运行，确认通过**

Run: `python3 -m unittest tests.test_derive -v`
Expected: 16 个测试全部 `ok`

- [ ] **Step 5: Commit**

```bash
git add radar/derive.py tests/test_derive.py
git commit -m "feat: derive rank changes, growth, histories and status" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: 建站与命令行入口

**Files:**
- Create: `radar/site.py`, `radar/__main__.py`
- Test: `tests/test_site.py`, `tests/test_main.py`

- [ ] **Step 1: 写失败的测试**

`tests/test_site.py`：
```python
import tempfile
import unittest
from pathlib import Path

from radar.site import build_site


class BuildSiteTest(unittest.TestCase):
    def test_copies_site_and_derived(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "site").mkdir()
            (root / "site" / "index.html").write_text("<html></html>", encoding="utf-8")
            (root / "data" / "derived").mkdir(parents=True)
            (root / "data" / "derived" / "status.json").write_text("{}", encoding="utf-8")
            (root / "_site").mkdir()
            (root / "_site" / "stale.txt").write_text("old", encoding="utf-8")

            out = build_site(root)

            self.assertEqual(out, root / "_site")
            self.assertTrue((out / "index.html").exists())
            self.assertTrue((out / "data" / "derived" / "status.json").exists())
            self.assertFalse((out / "stale.txt").exists())


if __name__ == "__main__":
    unittest.main()
```

`tests/test_main.py`：
```python
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from radar import __main__ as cli
from radar.collect import CollectError, NotUpdated
from radar.store import Store

SNAP = {
    "date": "2026-10-14",
    "fetched_at": "2026-10-14T04:00:00Z",
    "ranks": {"hot": {"rank_date": "2026-10-14", "items": [{"id": "1", "rank": 1, "title": "剧1", "status_tags": []}]}},
    "series": {
        "1": {
            "title": "剧1", "tags": [], "eps": 1, "first_visible": 1, "hot": 1, "fav": 1, "like": 1,
            "rating_cnt": 1, "review_cnt": 1, "score": None, "sources": ["rank:hot"],
        }
    },
    "watchlist": [],
    "errors": [],
}


class MainTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.args = ["--root", str(self.root), "--date", "2026-10-14"]

    def tearDown(self):
        self.tmp.cleanup()

    def test_run_writes_snapshot_and_derived(self):
        with mock.patch.object(cli, "collect", return_value=dict(SNAP)) as fake, mock.patch.object(cli, "Fetcher"):
            self.assertEqual(cli.main(["run"] + self.args), 0)
        fake.assert_called_once()
        self.assertTrue(Store(self.root).has_snapshot("2026-10-14"))
        self.assertTrue((self.root / "data" / "derived" / "status.json").exists())

    def test_existing_snapshot_is_skipped(self):
        Store(self.root).write_snapshot(dict(SNAP))
        with mock.patch.object(cli, "collect") as fake, mock.patch.object(cli, "Fetcher"):
            self.assertEqual(cli.main(["collect"] + self.args), 0)
        fake.assert_not_called()

    def test_force_overwrites(self):
        Store(self.root).write_snapshot(dict(SNAP))
        with mock.patch.object(cli, "collect", return_value=dict(SNAP)) as fake, mock.patch.object(cli, "Fetcher"):
            self.assertEqual(cli.main(["collect", "--force"] + self.args), 0)
        fake.assert_called_once()

    def test_not_updated_exits_zero_without_snapshot(self):
        with mock.patch.object(cli, "collect", side_effect=NotUpdated("x")), mock.patch.object(cli, "Fetcher"):
            self.assertEqual(cli.main(["collect"] + self.args), 0)
        self.assertFalse(Store(self.root).has_snapshot("2026-10-14"))

    def test_collect_error_exits_one(self):
        with mock.patch.object(cli, "collect", side_effect=CollectError("x")), mock.patch.object(cli, "Fetcher"):
            self.assertEqual(cli.main(["run"] + self.args), 1)
        self.assertFalse(Store(self.root).has_snapshot("2026-10-14"))

    def test_allow_stale_is_passed(self):
        with mock.patch.object(cli, "collect", return_value=dict(SNAP)) as fake, mock.patch.object(cli, "Fetcher"):
            cli.main(["collect", "--allow-stale"] + self.args)
        self.assertTrue(fake.call_args.kwargs["allow_stale"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行，确认失败**

Run: `python3 -m unittest tests.test_site tests.test_main -v`
Expected: 报 `ModuleNotFoundError`（`radar.site` 和 `radar.__main__` 不存在）

- [ ] **Step 3: 实现**

`radar/site.py`：
```python
"""生成 _site/：页面源码 + 派生数据。Pages 发布和本地预览共用这个目录。"""

from __future__ import annotations

import shutil
from pathlib import Path


def build_site(root: Path) -> Path:
    root = Path(root)
    out = root / "_site"
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(root / "site", out)
    derived = root / "data" / "derived"
    if derived.exists():
        shutil.copytree(derived, out / "data" / "derived")
    return out
```

`radar/__main__.py`：
```python
"""命令行入口：python -m radar {run,collect,derive,build-site}"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

from radar.collect import CollectError, NotUpdated, collect
from radar.derive import derive_all
from radar.http import Fetcher
from radar.site import build_site
from radar.store import Store
from radar.watchlist import parse_entries

BEIJING = timezone(timedelta(hours=8))


def beijing_today() -> date:
    return datetime.now(BEIJING).date()


def cmd_collect(store: Store, args: argparse.Namespace) -> int:
    today = date.fromisoformat(args.date) if args.date else beijing_today()
    if store.has_snapshot(today.isoformat()) and not args.force:
        print(f"{today} 的快照已存在，跳过（加 --force 可重抓）")
        return 0
    cache = store.load_watch_cache()
    try:
        snap = collect(
            Fetcher(),
            today,
            parse_entries(store.watchlist_text()),
            cache,
            store.load_snapshots(),
            allow_stale=args.allow_stale,
        )
    except NotUpdated as exc:
        print(f"官方榜单还没更新，本次不写快照：{exc}")
        return 0
    except CollectError as exc:
        print(f"采集失败：{exc}", file=sys.stderr)
        return 1
    store.write_snapshot(snap)
    store.save_watch_cache(cache)
    missing = sum(1 for v in snap["series"].values() if v is None)
    ranks = "，".join(f"{k} {len(r['items'])} 条（{r['rank_date']}）" for k, r in snap["ranks"].items())
    print(f"已写入 {today} 快照：{ranks}；追踪 {len(snap['series'])} 部，缺失 {missing}，错误 {len(snap['errors'])}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="radar", description="红果官方热度榜追踪")
    parser.add_argument("command", choices=["run", "collect", "derive", "build-site"])
    parser.add_argument("--root", default=".", help="仓库根目录，默认当前目录")
    parser.add_argument("--date", help="按指定日期采集（YYYY-MM-DD，北京时间），默认今天")
    parser.add_argument("--force", action="store_true", help="覆盖当天已有的快照")
    parser.add_argument("--allow-stale", action="store_true", help="官方榜单没更新也照常写快照")
    args = parser.parse_args(argv)
    store = Store(Path(args.root))

    if args.command == "build-site":
        print(f"已生成 {build_site(store.root)}")
        return 0
    if args.command == "derive":
        derive_all(store)
        print("派生数据已更新")
        return 0
    code = cmd_collect(store, args)
    if args.command == "run" and code == 0:
        derive_all(store)
        print("派生数据已更新")
    return code


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: 运行，确认通过**

Run: `python3 -m unittest tests.test_site tests.test_main -v`
Expected: 7 个测试全部 `ok`

- [ ] **Step 5: 跑全部测试**

Run: `python3 -m unittest discover -s tests -t . -v`
Expected: 全部 `ok`

- [ ] **Step 6: Commit**

```bash
git add radar/site.py radar/__main__.py tests/test_site.py tests/test_main.py
git commit -m "feat: build-site and command line entry" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: 看板页面

**Files:**
- Create: `site/index.html`, `site/style.css`, `site/app.js`

页面只读 `data/derived/` 下的 JSON，没有构建步骤。看板的视觉验证放在 Task 10，用真实数据来看。

- [ ] **Step 1: 写 `site/index.html`**

```html
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>红果榜单雷达</title>
<link rel="stylesheet" href="style.css">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js" defer></script>
<script src="app.js" defer></script>
</head>
<body>
<header class="top">
  <h1>红果榜单雷达</h1>
  <div id="status" class="status">加载中…</div>
</header>
<nav class="tabs" id="tabs">
  <button data-tab="rank" class="active">官方榜</button>
  <button data-tab="surge">飙升榜</button>
  <button data-tab="watch">观察列表</button>
</nav>
<main>
  <section id="view-rank">
    <div class="toolbar">
      <div class="seg" id="rank-keys">
        <button data-key="hot" class="active">综合</button>
        <button data-key="real">真人</button>
        <button data-key="ai">AI</button>
        <button data-key="comic">漫剧</button>
      </div>
      <input id="rank-q" type="search" placeholder="搜索剧名">
    </div>
    <div class="table-wrap"><table id="rank-table"></table></div>
    <h3 class="sub">今日掉榜</h3>
    <div id="dropped" class="dropped"></div>
  </section>
  <section id="view-surge" hidden>
    <div class="toolbar">
      <div class="seg" id="surge-sort">
        <button data-sort="d_hot" class="active">热度日增</button>
        <button data-sort="d_fav">收藏日增</button>
        <button data-sort="r_hot">热度增长率</button>
      </div>
      <div class="seg" id="surge-type">
        <button data-type="all" class="active">全部</button>
        <button data-type="real">真人</button>
        <button data-type="ai">AI</button>
        <button data-type="comic">漫剧</button>
        <button data-type="unknown">未知</button>
      </div>
    </div>
    <p id="surge-note" class="note"></p>
    <div class="table-wrap"><table id="surge-table"></table></div>
  </section>
  <section id="view-watch" hidden>
    <p class="note">在仓库的 watchlist.txt 里每行写一个剧名或红果链接，下一次采集生效。</p>
    <div class="table-wrap"><table id="watch-table"></table></div>
  </section>
</main>
<dialog id="detail">
  <div class="detail-head">
    <h2 id="d-title"></h2>
    <button id="d-close" aria-label="关闭">✕</button>
  </div>
  <div id="d-info" class="d-info"></div>
  <div class="chart-box"><canvas id="d-metrics"></canvas></div>
  <div class="chart-box"><canvas id="d-ranks"></canvas></div>
  <a id="d-link" target="_blank" rel="noopener">去红果看 →</a>
</dialog>
</body>
</html>
```

- [ ] **Step 2: 写 `site/style.css`**

```css
:root {
  --bg: #f7f7f8; --panel: #ffffff; --fg: #1d1d1f; --muted: #6b6b73; --line: #e4e4e8;
  --accent: #d6336c; --up: #d6336c; --down: #2b8a3e; --warn: #b26a00; --bad: #c92a2a;
  --c1: #d6336c; --c2: #1c7ed6; --c3: #f08c00; --c4: #2b8a3e;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #111114; --panel: #1b1b20; --fg: #ececf1; --muted: #9a9aa5; --line: #2c2c34;
    --accent: #f06595; --up: #f06595; --down: #51cf66; --warn: #fcc419; --bad: #ff6b6b;
    --c1: #f06595; --c2: #4dabf7; --c3: #ffa94d; --c4: #51cf66;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--fg);
  font: 14px/1.5 -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", sans-serif;
}
.top { padding: 16px 16px 8px; }
h1 { font-size: 20px; margin: 0 0 6px; }
.status { display: flex; flex-wrap: wrap; gap: 6px 14px; color: var(--muted); font-size: 13px; }
.status b { color: var(--fg); }
.warn { color: var(--warn); }
.bad { color: var(--bad); font-weight: 600; }
.tabs {
  display: flex; gap: 4px; padding: 0 16px; border-bottom: 1px solid var(--line);
  position: sticky; top: 0; background: var(--bg); z-index: 2;
}
.tabs button {
  border: 0; background: none; color: var(--muted); padding: 10px 12px; font-size: 15px;
  cursor: pointer; border-bottom: 2px solid transparent;
}
.tabs button.active { color: var(--fg); border-bottom-color: var(--accent); font-weight: 600; }
main { padding: 12px 16px 40px; max-width: 1200px; }
.toolbar { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 10px; }
.seg { display: inline-flex; border: 1px solid var(--line); border-radius: 8px; overflow: hidden; }
.seg button {
  border: 0; background: var(--panel); color: var(--fg); padding: 6px 12px; cursor: pointer; font-size: 13px;
}
.seg button + button { border-left: 1px solid var(--line); }
.seg button.active { background: var(--accent); color: #fff; }
input[type=search] {
  flex: 1; min-width: 140px; max-width: 260px; padding: 6px 10px; border: 1px solid var(--line);
  border-radius: 8px; background: var(--panel); color: var(--fg); font-size: 13px;
}
.table-wrap { overflow-x: auto; background: var(--panel); border: 1px solid var(--line); border-radius: 10px; }
table { border-collapse: collapse; width: 100%; min-width: 760px; }
th, td { padding: 8px 10px; border-bottom: 1px solid var(--line); text-align: left; white-space: nowrap; }
th { font-size: 12px; color: var(--muted); font-weight: 500; }
td.num { text-align: right; font-variant-numeric: tabular-nums; }
td.title { white-space: normal; min-width: 180px; }
td.tags { color: var(--muted); font-size: 12px; }
td small { font-size: 12px; }
.up { color: var(--up); }
.down { color: var(--down); }
.flat { color: var(--muted); }
.link {
  border: 0; background: none; padding: 0; color: var(--fg); font: inherit; text-align: left; cursor: pointer;
}
.link:hover { color: var(--accent); text-decoration: underline; }
.tag {
  display: inline-block; margin-left: 6px; padding: 0 6px; border-radius: 4px; font-size: 11px;
  background: var(--line); color: var(--muted);
}
.tag.hot { background: color-mix(in srgb, var(--accent) 15%, transparent); color: var(--accent); }
.badge { padding: 1px 6px; border-radius: 4px; font-size: 11px; font-weight: 600; color: #fff; }
.badge.new { background: var(--accent); }
.badge.back { background: var(--c2); }
.sub { font-size: 14px; margin: 18px 0 8px; color: var(--muted); }
.dropped { display: flex; flex-wrap: wrap; gap: 8px; color: var(--muted); font-size: 13px; }
.chip { background: var(--panel); border: 1px solid var(--line); border-radius: 999px; padding: 3px 10px; }
.note { color: var(--muted); font-size: 13px; margin: 0 0 10px; }
.sparkline { width: 80px; height: 24px; color: var(--c1); display: block; }
dialog {
  width: min(900px, calc(100vw - 32px)); max-height: calc(100vh - 32px); border: 1px solid var(--line);
  border-radius: 12px; background: var(--panel); color: var(--fg); padding: 16px;
}
dialog::backdrop { background: rgb(0 0 0 / 0.45); }
.detail-head { display: flex; justify-content: space-between; align-items: start; gap: 12px; }
.detail-head h2 { font-size: 18px; margin: 0; }
#d-close { border: 0; background: none; color: var(--muted); font-size: 18px; cursor: pointer; }
.d-info { display: flex; flex-wrap: wrap; gap: 6px 14px; color: var(--muted); font-size: 13px; margin: 8px 0 12px; }
.chart-box { position: relative; height: 240px; margin-bottom: 12px; }
#d-link { color: var(--accent); }
@media (max-width: 600px) {
  .top { padding: 12px 16px 6px; }
  h1 { font-size: 18px; }
  .tabs button { padding: 10px 8px; }
}
```

- [ ] **Step 3: 写 `site/app.js`**

```js
"use strict";

const DATA = "data/derived/";
const RANK_NAMES = { hot: "综合", real: "真人", ai: "AI", comic: "漫剧" };
const TYPE_NAMES = { real: "真人", ai: "AI", comic: "漫剧", unknown: "未知" };
const WATCH_ERR = {
  not_found: "红果上没找到同名剧，请检查剧名或改用链接",
  ambiguous: "有多部同名剧，请改用链接",
  error: "搜索失败，下次采集会重试",
};
const state = { tab: "rank", rankKey: "hot", q: "", sort: "d_hot", type: "all" };
let status = null;
let ranks = null;
let growth = null;
let growthById = new Map();
const seriesCache = new Map();
let charts = [];

async function getJSON(path) {
  const res = await fetch(DATA + path, { cache: "no-cache" });
  if (!res.ok) throw new Error(`${path} HTTP ${res.status}`);
  return res.json();
}

function el(tag, attrs, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") node.className = v;
    else if (k === "onclick") node.addEventListener("click", v);
    else node.setAttribute(k, v);
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined || c === false) continue;
    node.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return node;
}

function fmtNum(n) {
  if (n === null || n === undefined) return "—";
  const a = Math.abs(n);
  if (a >= 1e8) return (n / 1e8).toFixed(2).replace(/\.?0+$/, "") + "亿";
  if (a >= 1e4) return (n / 1e4).toFixed(1).replace(/\.0$/, "") + "万";
  return String(Math.round(n));
}

function fmtDelta(n) {
  if (n === null || n === undefined) return "—";
  if (n === 0) return "0";
  return (n > 0 ? "+" : "−") + fmtNum(Math.abs(n));
}

function fmtPct(r) {
  if (r === null || r === undefined) return "—";
  return (r > 0 ? "+" : "") + (r * 100).toFixed(1) + "%";
}

function deltaClass(n) {
  return n > 0 ? "up" : n < 0 ? "down" : "";
}

function beijingToday() {
  return new Date(Date.now() + 8 * 3600e3).toISOString().slice(0, 10);
}

function daysBetween(a, b) {
  return Math.round((Date.parse(a) - Date.parse(b)) / 86400e3);
}

function titleButton(id, title) {
  return el("button", { class: "link", onclick: () => openDetail(id) }, title || id);
}

function header(names) {
  return el("thead", {}, el("tr", {}, names.map((h) => el("th", {}, h))));
}

function renderStatus() {
  const box = document.getElementById("status");
  box.textContent = "";
  if (!status || !status.date) {
    box.append("还没有数据");
    return;
  }
  const rankDates = Object.entries(status.rank_dates)
    .map(([k, d]) => `${RANK_NAMES[k]} ${d ? d.slice(5) : "—"}`)
    .join(" · ");
  box.append(
    el("span", {}, "数据日期 ", el("b", {}, status.date)),
    el("span", {}, "官方榜 " + rankDates),
    el("span", {}, `追踪 ${status.tracked} 部`),
  );
  if (status.missing) box.append(el("span", { class: "warn" }, `${status.missing} 部详情缺失`));
  if (status.error_count) {
    const tip = status.errors.map((e) => e.message).join("\n");
    box.append(el("span", { class: "warn", title: tip }, `${status.error_count} 个错误`));
  }
  const lag = daysBetween(beijingToday(), status.date);
  if (lag > 1) box.append(el("span", { class: "bad" }, `数据已 ${lag} 天未更新`));
}

function changeCell(it) {
  if (it.badge === "new") return el("span", { class: "badge new" }, "NEW");
  if (it.badge === "back") return el("span", { class: "badge back" }, "回榜");
  if (it.delta === null || it.delta === undefined) return "—";
  if (it.delta === 0) return el("span", { class: "flat" }, "–");
  return el("span", { class: deltaClass(it.delta) }, (it.delta > 0 ? "↑" : "↓") + Math.abs(it.delta));
}

function renderRank() {
  const r = ranks[state.rankKey];
  const table = document.getElementById("rank-table");
  table.textContent = "";
  table.append(header(["名次", "变化", "剧名", "热度", "热度日增", "收藏（日增）", "评分", "在榜", "标签"]));
  const q = state.q.trim();
  const body = el("tbody");
  for (const it of r.items) {
    const g = growthById.get(it.id) || {};
    const title = g.title || it.title;
    if (q && !title.includes(q)) continue;
    body.append(
      el(
        "tr",
        {},
        el("td", { class: "num" }, it.rank),
        el("td", {}, changeCell(it)),
        el("td", { class: "title" }, titleButton(it.id, title), it.status_tags.map((t) => el("span", { class: "tag hot" }, t))),
        el("td", { class: "num" }, fmtNum(g.hot)),
        el("td", { class: "num " + deltaClass(g.d_hot) }, fmtDelta(g.d_hot)),
        el("td", { class: "num" }, fmtNum(g.fav), " ", el("small", { class: deltaClass(g.d_fav) }, fmtDelta(g.d_fav))),
        el("td", { class: "num" }, g.score ?? "—"),
        el("td", { class: "num" }, it.streak + " 天"),
        el("td", { class: "tags" }, (g.tags || []).slice(0, 3).join(" / ")),
      ),
    );
  }
  table.append(body);

  const dropped = document.getElementById("dropped");
  dropped.textContent = "";
  if (!r.prev_rank_date) dropped.append("第一天的数据，暂无对比");
  else if (!r.dropped.length) dropped.append("无");
  for (const d of r.dropped) {
    dropped.append(el("span", { class: "chip" }, titleButton(d.id, d.title), ` 原第 ${d.last_rank} 名`));
  }
}

function renderSurge() {
  const key = state.sort;
  const note = document.getElementById("surge-note");
  if (!growth.prev_date) {
    note.textContent = "增速需要至少两天的数据，明天开始显示。";
  } else {
    note.textContent =
      `对比 ${growth.prev_date} → ${growth.date}` + (growth.gap > 1 ? `（间隔 ${growth.gap} 天，已换算成日均）` : "");
  }
  const rows = growth.items
    .filter((g) => g[key] !== null && g[key] !== undefined && (state.type === "all" || g.type === state.type))
    .sort((a, b) => b[key] - a[key])
    .slice(0, 50);
  const table = document.getElementById("surge-table");
  table.textContent = "";
  table.append(header(["#", "剧名", "类型", "热度", "热度日增", "增长率", "收藏日增", "7 日热度增量"]));
  const body = el("tbody");
  rows.forEach((g, i) => {
    body.append(
      el(
        "tr",
        {},
        el("td", { class: "num" }, i + 1),
        el("td", { class: "title" }, titleButton(g.id, g.title), g.watch ? el("span", { class: "tag" }, "观察") : null),
        el("td", {}, TYPE_NAMES[g.type] || g.type),
        el("td", { class: "num" }, fmtNum(g.hot)),
        el("td", { class: "num " + deltaClass(g.d_hot) }, fmtDelta(g.d_hot)),
        el("td", { class: "num " + deltaClass(g.r_hot) }, fmtPct(g.r_hot)),
        el("td", { class: "num " + deltaClass(g.d_fav) }, fmtDelta(g.d_fav)),
        el("td", { class: "num " + deltaClass(g.d7_hot) }, fmtDelta(g.d7_hot)),
      ),
    );
  });
  table.append(body);
}

function sparkline(values) {
  const v = values.filter((x) => x !== null && x !== undefined);
  if (v.length < 2) return document.createTextNode("数据不足");
  const NS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", "0 0 80 24");
  svg.setAttribute("class", "sparkline");
  const min = Math.min(...v);
  const span = Math.max(...v) - min || 1;
  const points = v.map((x, i) => `${(i / (v.length - 1)) * 78 + 1},${23 - ((x - min) / span) * 22}`).join(" ");
  const line = document.createElementNS(NS, "polyline");
  line.setAttribute("points", points);
  line.setAttribute("fill", "none");
  line.setAttribute("stroke", "currentColor");
  line.setAttribute("stroke-width", "1.5");
  svg.append(line);
  return svg;
}

function loadSeries(id) {
  if (!seriesCache.has(id)) {
    seriesCache.set(
      id,
      getJSON(`series/${id}.json`).catch((e) => {
        seriesCache.delete(id);
        throw e;
      }),
    );
  }
  return seriesCache.get(id);
}

function renderWatch() {
  const table = document.getElementById("watch-table");
  table.textContent = "";
  const entries = status.watchlist || [];
  if (!entries.length) {
    table.append(el("tbody", {}, el("tr", {}, el("td", {}, "观察列表为空"))));
    return;
  }
  table.append(header(["条目", "剧名", "热度", "热度日增", "收藏", "收藏日增", "近 7 天热度"]));
  const body = el("tbody");
  table.append(body);
  for (const w of entries) {
    if (w.status !== "ok") {
      const why = WATCH_ERR[w.status] + (w.candidates ? "：" + w.candidates.join("、") : "");
      body.append(el("tr", {}, el("td", {}, w.entry), el("td", { class: "warn", colspan: "6" }, why)));
      continue;
    }
    const g = growthById.get(w.id) || {};
    const spark = el("td", { class: "spark" });
    body.append(
      el(
        "tr",
        {},
        el("td", {}, w.entry),
        el("td", { class: "title" }, titleButton(w.id, g.title || w.id)),
        el("td", { class: "num" }, fmtNum(g.hot)),
        el("td", { class: "num " + deltaClass(g.d_hot) }, fmtDelta(g.d_hot)),
        el("td", { class: "num" }, fmtNum(g.fav)),
        el("td", { class: "num " + deltaClass(g.d_fav) }, fmtDelta(g.d_fav)),
        spark,
      ),
    );
    loadSeries(w.id)
      .then((s) => spark.append(sparkline(s.points.slice(-7).map((p) => p.hot))))
      .catch(() => spark.append("—"));
  }
}

function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

async function openDetail(id) {
  const dlg = document.getElementById("detail");
  const info = document.getElementById("d-info");
  document.getElementById("d-title").textContent = (growthById.get(id) || {}).title || id;
  document.getElementById("d-link").href = `https://hongguoduanju.com/detail?series_id=${encodeURIComponent(id)}`;
  info.textContent = "加载中…";
  charts.forEach((c) => c.destroy());
  charts = [];
  history.replaceState(null, "", "#s=" + encodeURIComponent(id));
  if (!dlg.open) dlg.showModal();

  let s;
  try {
    s = await loadSeries(id);
  } catch (e) {
    info.textContent = "历史数据加载失败";
    return;
  }
  document.getElementById("d-title").textContent = s.title || id;
  const firstDay = s.first_visible ? new Date(s.first_visible * 1000 + 8 * 3600e3).toISOString().slice(0, 10) : "—";
  info.textContent = "";
  info.append(
    ...[
      `${s.eps ?? "—"} 集`,
      `上线 ${firstDay}`,
      `评分 ${s.score ?? "—"}`,
      `${fmtNum(s.rating_cnt)} 人评分`,
      `${fmtNum(s.review_cnt)} 条评论`,
      (s.tags || []).join(" / "),
    ].map((t) => el("span", {}, t)),
  );
  if (!window.Chart) {
    info.append(el("span", { class: "warn" }, "图表库加载失败"));
    return;
  }
  const labels = s.points.map((p) => p.date.slice(5));
  const fg = cssVar("--muted");
  const grid = cssVar("--line");
  const base = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: "index", intersect: false },
    plugins: { legend: { labels: { color: fg } } },
  };
  const axisX = { ticks: { color: fg }, grid: { color: grid } };
  charts.push(
    new Chart(document.getElementById("d-metrics"), {
      type: "line",
      data: {
        labels,
        datasets: [
          { label: "热度", data: s.points.map((p) => p.hot), yAxisID: "y", borderColor: cssVar("--c1"), tension: 0.2 },
          { label: "收藏", data: s.points.map((p) => p.fav), yAxisID: "y1", borderColor: cssVar("--c2"), tension: 0.2 },
          { label: "点赞", data: s.points.map((p) => p.like), yAxisID: "y1", borderColor: cssVar("--c3"), tension: 0.2 },
        ],
      },
      options: {
        ...base,
        scales: {
          x: axisX,
          y: { position: "left", ticks: { color: fg, callback: (v) => fmtNum(v) }, grid: { color: grid } },
          y1: { position: "right", ticks: { color: fg, callback: (v) => fmtNum(v) }, grid: { drawOnChartArea: false } },
        },
      },
    }),
  );
  const keys = Object.keys(RANK_NAMES).filter((k) => s.points.some((p) => p.ranks[k] !== undefined));
  charts.push(
    new Chart(document.getElementById("d-ranks"), {
      type: "line",
      data: {
        labels,
        datasets: keys.map((k, i) => ({
          label: RANK_NAMES[k] + "榜名次",
          data: s.points.map((p) => p.ranks[k] ?? null),
          borderColor: cssVar(`--c${i + 1}`),
          spanGaps: false,
          tension: 0.2,
        })),
      },
      options: {
        ...base,
        scales: { x: axisX, y: { reverse: true, min: 1, ticks: { color: fg, precision: 0 }, grid: { color: grid } } },
      },
    }),
  );
}

function setActive(container, attr, value) {
  for (const b of container.querySelectorAll("button")) b.classList.toggle("active", b.dataset[attr] === value);
}

function showTab(tab) {
  state.tab = tab;
  setActive(document.getElementById("tabs"), "tab", tab);
  for (const t of ["rank", "surge", "watch"]) document.getElementById("view-" + t).hidden = t !== tab;
  if (tab === "rank") renderRank();
  else if (tab === "surge") renderSurge();
  else renderWatch();
}

function onSeg(id, attr, apply) {
  document.getElementById(id).addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    apply(b.dataset[attr]);
    setActive(e.currentTarget, attr, b.dataset[attr]);
  });
}

function wire() {
  onSeg("tabs", "tab", showTab);
  onSeg("rank-keys", "key", (v) => {
    state.rankKey = v;
    renderRank();
  });
  onSeg("surge-sort", "sort", (v) => {
    state.sort = v;
    renderSurge();
  });
  onSeg("surge-type", "type", (v) => {
    state.type = v;
    renderSurge();
  });
  document.getElementById("rank-q").addEventListener("input", (e) => {
    state.q = e.target.value;
    renderRank();
  });
  const dlg = document.getElementById("detail");
  document.getElementById("d-close").addEventListener("click", () => dlg.close());
  dlg.addEventListener("click", (e) => {
    if (e.target === dlg) dlg.close();
  });
  dlg.addEventListener("close", () => history.replaceState(null, "", location.pathname + location.search));
}

async function init() {
  wire();
  try {
    [status, ranks, growth] = await Promise.all([
      getJSON("status.json"),
      getJSON("ranks_latest.json"),
      getJSON("growth_latest.json"),
    ]);
  } catch (e) {
    document.getElementById("status").textContent = "数据加载失败：" + e.message;
    return;
  }
  growthById = new Map(growth.items.map((g) => [g.id, g]));
  renderStatus();
  showTab("rank");
  const m = location.hash.match(/^#s=(\d+)$/);
  if (m) openDetail(m[1]);
}

init();
```

- [ ] **Step 4: 语法检查**

Run: `node --check site/app.js && echo OK`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add site/
git commit -m "feat: static dashboard" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: 本机实跑和看板验证

这一步连真实的红果官网（本机通过环境变量里的代理 `127.0.0.1:7897` 出网，urllib 会自动使用），大约需要 4 分钟。

- [ ] **Step 1: 跑一次真实采集**

Run: `python3 -m radar run`
Expected：最后两行类似
```
已写入 2026-10-1X 快照：hot 100 条（2026-10-1X），real 100 条（…），ai 100 条（…），comic 100 条（…）；追踪 3xx 部，缺失 0，错误 0
派生数据已更新
```
如果输出是「官方榜单还没更新」，说明官方当天还没更新（一般上午 10 点多更新），改用 `python3 -m radar run --allow-stale`。

- [ ] **Step 2: 抽查快照内容**

Run:
```bash
python3 - <<'EOF'
import json, glob
p = sorted(glob.glob("data/snapshots/*.json"))[-1]
s = json.load(open(p, encoding="utf-8"))
print(p)
for k, r in s["ranks"].items():
    print(k, r["rank_date"], len(r["items"]), r["items"][0]["title"])
ok = [v for v in s["series"].values() if v]
print("tracked", len(s["series"]), "ok", len(ok), "errors", len(s["errors"]))
top = max(ok, key=lambda v: v["hot"] or 0)
print("最高热度:", top["title"], top["hot"], top["fav"], top["like"])
print("watchlist:", s["watchlist"])
EOF
```
Expected：4 个榜都约 100 条，追踪的剧几乎全部 ok，观察列表里两季《乖野之下》都是 `status: ok`。把输出和 https://hongguoduanju.com/rank/hot-drama 页面上的榜首对一下，名字应该一致。

- [ ] **Step 3: 生成站点并在本地起服务**

Run: `python3 -m radar build-site`
然后用后台方式运行：`python3 -m http.server 8765 --directory _site`

- [ ] **Step 4: 截图检查桌面版和手机版**

```bash
mkdir -p _shots
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
SID=$(python3 -c "import json;print(json.load(open('_site/data/derived/ranks_latest.json',encoding='utf-8'))['hot']['items'][0]['id'])")
"$CHROME" --headless=new --disable-gpu --hide-scrollbars --virtual-time-budget=8000 --window-size=1280,1600 --screenshot="$PWD/_shots/desktop.png" http://localhost:8765/
"$CHROME" --headless=new --disable-gpu --hide-scrollbars --virtual-time-budget=8000 --window-size=390,1400 --screenshot="$PWD/_shots/mobile.png" http://localhost:8765/
"$CHROME" --headless=new --disable-gpu --hide-scrollbars --virtual-time-budget=8000 --window-size=1280,1100 --screenshot="$PWD/_shots/detail.png" "http://localhost:8765/#s=$SID"
```
（`_shots/` 已经在 `.gitignore` 里。）用 Read 工具打开这三张图检查：
- 状态栏有数据日期和 4 个榜的日期。
- 综合榜表格有 100 行，名次、热度、收藏、标签都有值。因为是第一天，「变化」列是「—」，「今日掉榜」显示「第一天的数据，暂无对比」。
- 手机宽度下页面本身没有横向滚动，表格在自己的容器里横向滚动。
- 详情面板显示了标题、基本信息和图表。只有 1 个数据点时，折线图只有一个点，这是正常的。

如果有问题，修 `site/` 里对应的文件，重新运行 `build-site` 并截图，直到没问题为止。最后停掉 http.server。

- [ ] **Step 5: 提交第一份真实数据**

```bash
git add data/
git commit -m "data: first snapshot" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
（如果 Step 4 改了 `site/`，先单独提交：`git add site/ && git commit -m "fix: dashboard layout" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"`）

---

### Task 11: GitHub Actions 工作流

**Files:**
- Create: `.github/workflows/daily.yml`, `.github/workflows/pages.yml`

- [ ] **Step 1: 写 `.github/workflows/daily.yml`**

```yaml
name: daily

on:
  schedule:
    - cron: '0 4 * * *'   # 北京时间 12:00
    - cron: '0 7 * * *'   # 北京时间 15:00，兜底，允许官方榜单未更新
  workflow_dispatch:
    inputs:
      allow_stale:
        description: '官方榜单没更新也写快照'
        type: boolean
        default: false
      force:
        description: '覆盖当天已有的快照'
        type: boolean
        default: false

permissions:
  contents: write
  pages: write
  id-token: write

concurrency:
  group: radar
  cancel-in-progress: false

jobs:
  collect:
    runs-on: ubuntu-latest
    timeout-minutes: 25
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Test
        run: python -m unittest discover -s tests -t . -v
      - name: Collect and derive
        run: |
          ARGS=""
          if [ "${{ github.event.schedule }}" = "0 7 * * *" ] || [ "${{ inputs.allow_stale }}" = "true" ]; then
            ARGS="$ARGS --allow-stale"
          fi
          if [ "${{ inputs.force }}" = "true" ]; then
            ARGS="$ARGS --force"
          fi
          python -m radar run $ARGS
      - name: Commit data
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add data/
          if git diff --cached --quiet; then
            echo "数据没有变化"
            exit 0
          fi
          git commit -m "data: $(TZ=Asia/Shanghai date +%F)"
          git pull --rebase origin main
          git push origin HEAD:main

  deploy:
    needs: collect
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - uses: actions/checkout@v4
        with:
          ref: main
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Build site
        run: python -m radar build-site
      - uses: actions/configure-pages@v5
      - uses: actions/upload-pages-artifact@v3
        with:
          path: _site
      - id: deployment
        uses: actions/deploy-pages@v4
```

- [ ] **Step 2: 写 `.github/workflows/pages.yml`**

用 `GITHUB_TOKEN` 推送的数据提交不会触发这个工作流，所以它只在人工推送（改代码、改观察列表）时运行。

```yaml
name: pages

on:
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: radar
  cancel-in-progress: false

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Test
        run: python -m unittest discover -s tests -t . -v
      - name: Build site
        run: python -m radar build-site
      - uses: actions/configure-pages@v5
      - uses: actions/upload-pages-artifact@v3
        with:
          path: _site
      - id: deployment
        uses: actions/deploy-pages@v4
```

- [ ] **Step 3: 检查 YAML 语法**

Run: `ruby -ryaml -e 'ARGV.each { |f| YAML.load_file(f); puts "ok #{f}" }' .github/workflows/daily.yml .github/workflows/pages.yml`
Expected: 两行 `ok ...`（macOS 自带 ruby）

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/
git commit -m "ci: daily collection and pages deployment" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 12: 上线

按设计创建**公开**仓库 `2252399314-cyber/hongguo-radar`。

- [ ] **Step 1: 创建仓库并推送**

```bash
gh repo create 2252399314-cyber/hongguo-radar --public --description "红果短剧官方热度榜每日追踪" --source=. --remote=origin --push
```
推送会触发一次 `pages` 工作流。这时 Pages 还没开启，那次运行可能失败，可以忽略，下一步会重跑。

- [ ] **Step 2: 开启 Pages（来源选 GitHub Actions）**

```bash
gh api -X POST repos/2252399314-cyber/hongguo-radar/pages -f build_type=workflow
```
Expected：返回 JSON，其中 `"build_type": "workflow"`。如果报 409（已经存在），改用 `gh api -X PUT repos/2252399314-cyber/hongguo-radar/pages -f build_type=workflow`。

- [ ] **Step 3: 在 Actions 上实测抓取**

这一步验证 GitHub 机房的 IP 能不能抓到红果。用 `force=true` 在云端重抓当天数据：

```bash
gh workflow run daily.yml -R 2252399314-cyber/hongguo-radar -f force=true
python3 -c "import time; time.sleep(8)"   # 等新的运行出现在列表里
RUN=$(gh run list -R 2252399314-cyber/hongguo-radar --workflow daily.yml --limit 1 --json databaseId --jq '.[0].databaseId')
gh run watch "$RUN" -R 2252399314-cyber/hongguo-radar --exit-status
gh run view "$RUN" -R 2252399314-cyber/hongguo-radar --log | grep -E "已写入|采集失败|官方榜单还没更新"
```
Expected：`collect` 和 `deploy` 两个 job 都成功，日志里有「已写入 … hot 100 条 …」。
- 如果日志是「官方榜单还没更新」：重跑一次，加上 `-f allow_stale=true -f force=true`。
- 如果是「采集失败」并且是 403、超时或榜单 0 条：说明 Actions 的 IP 被红果拦截了。**停下来**，把日志告诉用户，回到设计层面重新选部署位置（比如改用自有服务器），不要自己想办法绕过。

- [ ] **Step 4: 检查线上看板**

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://2252399314-cyber.github.io/hongguo-radar/
curl -s https://2252399314-cyber.github.io/hongguo-radar/data/derived/status.json | python3 -m json.tool | head -20
```
Expected：第一行是 `200`，`status.json` 里的 `date` 是今天。再按 Task 10 Step 4 的方法，把地址换成线上地址截一张桌面版的图看一下。

- [ ] **Step 5: 拉回云端的数据提交**

```bash
git pull --rebase origin main
```

---

### Task 13: 第二天的验证（人工检查清单）

第二天北京时间 12:30 之后：
- [ ] `gh run list -R 2252399314-cyber/hongguo-radar --workflow daily.yml --limit 3`：12:00 那次（`schedule`）成功。
- [ ] 打开看板：官方榜的「变化」列出现 ↑↓ 或 NEW，「今日掉榜」有内容，飙升榜显示「对比 昨天 → 今天」并且有数据。
- [ ] 15:00 那次运行日志显示「快照已存在，跳过」。
