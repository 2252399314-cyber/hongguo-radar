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
