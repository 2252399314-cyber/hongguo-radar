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
