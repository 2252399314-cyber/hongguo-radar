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
