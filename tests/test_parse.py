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
