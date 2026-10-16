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


def previous_snapshot(day, rank_date=None, ranks=None):
    """和 build_pages 默认榜单内容完全相同的一份历史快照。"""
    ranks = ranks or DEFAULT_RANKS
    return {
        "date": day,
        "ranks": {
            key: {"rank_date": rank_date or day, "items": [{"id": sid, "rank": rank} for sid, rank in items]}
            for key, items in ranks.items()
        },
        "series": {},
    }


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

    def test_label_date_is_kept_but_not_trusted(self):
        # 页面上的「X月X日已更新」只是按当天日期显示的文字，记录下来但不用来判断是否刷新
        snap = run(build_pages(updated_text="10月13日已更新"))
        self.assertEqual(snap["ranks"]["hot"]["label_date"], "2026-10-13")
        self.assertEqual(snap["ranks"]["hot"]["rank_date"], "2026-10-14")

    def test_same_ranks_as_previous_snapshot_raises(self):
        with self.assertRaises(C.NotUpdated):
            run(build_pages(), history=[previous_snapshot("2026-10-13")])

    def test_allow_stale_reuses_previous_rank_date(self):
        snap = run(build_pages(), history=[previous_snapshot("2026-10-13", rank_date="2026-10-12")], allow_stale=True)
        self.assertEqual(snap["ranks"]["hot"]["rank_date"], "2026-10-12")
        self.assertEqual(len(snap["series"]), 10)

    def test_changed_ranks_are_fresh(self):
        prev = previous_snapshot("2026-10-13")
        prev["ranks"]["comic"]["items"].reverse()
        snap = run(build_pages(), history=[prev])
        self.assertEqual(snap["ranks"]["comic"]["rank_date"], "2026-10-14")

    def test_unchanged_hot_means_not_refreshed(self):
        # 2026-10-15 的真实情况：AI 榜名次有零星变动，但热度一个没变，官方其实还没刷新
        prev = previous_snapshot("2026-10-13")
        prev["ranks"]["ai"]["items"].reverse()
        prev["series"] = {sid: {"hot": 1000} for sid in ["1", "2", "3"]}
        with self.assertRaises(C.NotUpdated):
            run(build_pages(), history=[prev])

    def test_changed_hot_means_refreshed_even_if_ranks_same(self):
        prev = previous_snapshot("2026-10-13")
        prev["series"] = {sid: {"hot": 900} for sid in ["1", "2", "3"]}
        snap = run(build_pages(), history=[prev])
        self.assertEqual(snap["ranks"]["hot"]["rank_date"], "2026-10-14")

    def test_probe_details_are_not_fetched_twice(self):
        fetcher = FakeFetcher(build_pages())
        prev = previous_snapshot("2026-10-13")
        prev["series"] = {sid: {"hot": 900} for sid in ["1", "2", "3"]}
        run(None, fetcher=fetcher, history=[prev])
        urls = [u for u, _ in fetcher.calls]
        self.assertEqual(len(urls), len(set(urls)))

    def test_compares_with_latest_earlier_snapshot_only(self):
        # 更早的快照和今天一样不算数，只和最近一份比
        older = previous_snapshot("2026-10-12")
        latest = previous_snapshot("2026-10-13")
        latest["ranks"]["hot"]["items"].reverse()
        snap = run(build_pages(), history=[older, latest])
        self.assertEqual(snap["ranks"]["hot"]["rank_date"], "2026-10-14")

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
