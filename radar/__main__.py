"""命令行入口：python -m radar {run,collect,derive,build-site}"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

from radar.collect import CollectError, NotUpdated, collect
from radar.derive import derive_all
from radar.http import Fetcher
from radar.site import build_site
from radar.store import Store
from radar.watchlist import parse_entries

BEIJING = timezone(timedelta(hours=8))


REFRESH_HOUR = 9  # 官方每天上午 10 点左右刷新（2026-10-14 实测 09:54–09:59），9 点前抓到的还是前一天的批次


def batch_date(now: datetime) -> date:
    """这一刻能抓到的是哪一天的官方批次。GitHub 定时任务常常晚几个小时，凌晨补跑的要记到前一天。"""
    local = now.astimezone(BEIJING)
    return local.date() - timedelta(days=1) if local.hour < REFRESH_HOUR else local.date()


def cmd_collect(store: Store, args: argparse.Namespace) -> int:
    today = date.fromisoformat(args.date) if args.date else batch_date(datetime.now(BEIJING))
    if store.has_snapshot(today.isoformat()) and not args.force:
        print(f"{today} 的快照已存在，跳过（加 --force 可重抓）")
        return 0
    cache = store.load_watch_cache()
    try:
        snap = collect(
            Fetcher(),
            today,
            parse_entries(store.watchlist_text()),
            cache,
            store.load_snapshots(),
            allow_stale=args.allow_stale,
        )
    except NotUpdated as exc:
        print(f"官方榜单还没更新，本次不写快照：{exc}")
        return 0
    except CollectError as exc:
        print(f"采集失败：{exc}", file=sys.stderr)
        return 1
    store.write_snapshot(snap)
    store.save_watch_cache(cache)
    missing = sum(1 for v in snap["series"].values() if v is None)
    ranks = "，".join(f"{k} {len(r['items'])} 条（{r['rank_date']}）" for k, r in snap["ranks"].items())
    print(f"已写入 {today} 快照：{ranks}；追踪 {len(snap['series'])} 部，缺失 {missing}，错误 {len(snap['errors'])}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="radar", description="红果官方热度榜追踪")
    parser.add_argument("command", choices=["run", "collect", "derive", "build-site"])
    parser.add_argument("--root", default=".", help="仓库根目录，默认当前目录")
    parser.add_argument("--date", help="按指定批次日期采集（YYYY-MM-DD），默认按当前北京时间推算")
    parser.add_argument("--force", action="store_true", help="覆盖当天已有的快照")
    parser.add_argument("--allow-stale", action="store_true", help="官方榜单没更新也照常写快照")
    args = parser.parse_args(argv)
    store = Store(Path(args.root))

    if args.command == "build-site":
        print(f"已生成 {build_site(store.root)}")
        return 0
    if args.command == "derive":
        derive_all(store)
        print("派生数据已更新")
        return 0
    code = cmd_collect(store, args)
    if args.command == "run" and code == 0:
        derive_all(store)
        print("派生数据已更新")
    return code


if __name__ == "__main__":
    sys.exit(main())
