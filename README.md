# hongguo-radar

每天自动采集红果短剧官网 4 个热度榜（综合 / 真人 / AI / 漫剧）的前 100 名，
以及每部被追踪剧的热度、收藏、点赞，算出名次变化和增速，发布成看板。

- 看板：https://2252399314-cyber.github.io/hongguo-radar/
- 观察列表：编辑 `watchlist.txt`，每行一个剧名或红果链接，下一次采集生效。
- 数据：`data/snapshots/` 是每天的原始快照，`data/derived/` 是由快照算出的结果。

## 本地运行

    python3 -m unittest discover -s tests -t . -v   # 测试
    python3 -m radar run                            # 采集今天的数据并计算
    python3 -m radar build-site                     # 生成 _site/
    python3 -m http.server 8765 --directory _site   # 本地预览

`run` 的参数：`--force` 覆盖当天已有的快照；`--allow-stale` 官方榜单没更新也照常写快照；`--date YYYY-MM-DD` 指定日期。

## 数据说明

热度是红果按观看和互动综合算出的分数，不是播放量。收藏一般取整到千，点赞一般取整到万。
