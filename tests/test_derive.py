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
