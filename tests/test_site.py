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
