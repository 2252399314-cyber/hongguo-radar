"""生成 _site/：页面源码 + 派生数据。Pages 发布和本地预览共用这个目录。"""

from __future__ import annotations

import shutil
from pathlib import Path


def build_site(root: Path) -> Path:
    root = Path(root)
    out = root / "_site"
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(root / "site", out)
    derived = root / "data" / "derived"
    if derived.exists():
        shutil.copytree(derived, out / "data" / "derived")
    return out
