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
