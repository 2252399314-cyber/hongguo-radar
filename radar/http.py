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
