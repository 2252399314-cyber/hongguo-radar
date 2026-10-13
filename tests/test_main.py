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
