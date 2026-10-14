# hongguo-radar 设计文档

日期：2026-10-13
范围：红果短剧/漫剧榜单追踪器的第一版，只做两档功能：①每日榜单快照与排名变化；②增速榜与观察列表。另外配一个看板。

## 1. 目标与非目标

**目标**
- 每天自动采集红果官网 4 个官方热度榜的前 100 名，以及每部被追踪剧的精确指标。
- 算出名次变化、新上榜、掉榜、回榜、连续在榜天数、历史最高名次。
- 算出每部剧的热度、收藏、点赞日增量和 7 日增量，并据此给出飙升榜。
- 支持用户自定义观察列表，追踪不在榜上的剧。
- 用一个公开静态看板展示以上结果。

**非目标（本版不做）**
- 消息推送（飞书/微信）、新剧雷达、题材统计、原著匹配。
- 播放量、完播率、收入分账、投流消耗。红果没有公开这些数据。
- 历史数据回填：只能从首次采集那天开始积累。
- 小时级更新：官方榜单本身就是按天更新的。

## 2. 数据源（2026-10-13 实测）

| 用途 | URL | UA 要求 | 数据位置 |
|---|---|---|---|
| 官方榜单 | `https://hongguoduanju.com/rank/{hot-drama,hot-real-drama,hot-ai-drama,hot-comic-drama}?page=1..5` | **必须用爬虫 UA**（Baiduspider）；普通 UA 下 `content` 为空 | HTML 内嵌的 `_ROUTER_DATA` → `loaderData["rank_<key>/page"]`，取其中的 `.content.rankList[]`、`.content.pagination`、`.updatedText` |
| 单剧详情 | `https://hongguoduanju.com/detail?series_id=<id>` | 普通浏览器 UA 即可 | `loaderData.detail_page.seriesSocialInfo`（`hot_score_data.score`、`series_like_count`、`series_favorite_count`、`rating_count`、`reviews.total_count`）和 `loaderData.detail_page.seriesDetail`（`series_name`、`episode_cnt`、`first_visible_time`、`tags`、`series_episode_info.series_status`） |
| 剧名搜索 | `https://hongguoduanju.com/search/<urlencoded 剧名>` | 普通 UA | `loaderData["search_(keyword)/page"].searchList[]`，其中 `doc_type==23` 的条目：`name` 是剧名，`keyword` 是 series_id |

几点说明：
- `_ROUTER_DATA` 的解析方式：找到 `_ROUTER_DATA = ` 之后，用 `json.JSONDecoder().raw_decode` 读出 JSON。后面紧跟着的 JS 代码不要一起读。
- 榜单条目字段：`seriesId`、`rank`、`title`、`heatText`（如「7783万热度」）、`scoreText`（如「评分9.0」，可能为 null）、`favoriteText`、`likeText`、`tags[]`、`statusTags[]`（如「新剧」「爆剧」）。
- `updatedText` 形如「10月13日已更新 · 基于红果内观看/互动等综合热度排序」。**2026-10-14 实测：这行字只是按当天日期显示，并不代表数据已经刷新。** 当天 09:11 页面已经写着「10月14日已更新」，但 4 个榜的名次和 302 部剧的热度都和前一天 11:28 抓到的完全相同（收藏、点赞、评论数则是实时变化的）。所以它只作为 `label_date` 记录，不用来判断是否刷新。
- 精度：详情页的热度是精确整数。收藏一般取整到千，点赞一般取整到万。
- 网络：本机经代理访问正常。GitHub Actions 机房 IP 能否访问需在上线时验证（见第 9 节）。

## 3. 架构

采用方案 A：Python 采集与计算（只用标准库，兼容 Python ≥3.9），每日 JSON 快照，加一个静态看板。

```
GitHub Actions（每天北京时间 10:30、12:00、14:00、17:00、21:00 各检查一次）
  └─ python -m radar run
       ├─ collect：抓榜单 → 确定追踪集合 → 抓详情 → 解析观察列表
       │     └─ 写 data/snapshots/YYYY-MM-DD.json（原始快照，只追加不修改）
       └─ derive：读全部快照 → 写 data/derived/*.json
  └─ git commit data/ → push
  └─ python -m radar build-site → _site/ → 部署到 GitHub Pages（同一个工作流里完成）
```

仓库为公开仓库 `hongguo-radar`，GitHub 账号 `2252399314-cyber`。看板地址：`https://2252399314-cyber.github.io/hongguo-radar/`。

### 目录结构

```
radar/                 Python 包
  http.py              请求：重试、退避、超时、限速
  parse.py             解析 _ROUTER_DATA 和榜单、详情、搜索三种页面（纯函数）
  collect.py           采集流程，产出一份快照字典
  derive.py            由快照计算榜单变化、增速和单剧历史（纯函数）
  watchlist.py         读取并解析 watchlist.txt
  store.py             快照与派生结果的读写
  site.py              build-site：生成 _site/
  __main__.py          命令行入口：run / collect / derive / build-site，支持 --force、--allow-stale、--date
tests/
  fixtures/            真实页面样本（4 个榜单首页、1 个详情页、1 个搜索结果页）
  test_parse.py
  test_derive.py
  test_watchlist.py
site/                  看板：index.html、app.js、style.css
data/
  snapshots/           原始快照
  derived/             派生结果
watchlist.txt
.github/workflows/daily.yml
.github/workflows/pages.yml
```

注：观察列表用 `watchlist.txt`，不用 YAML，这样不需要引入第三方 YAML 库。格式是每行一条，写剧名或红果链接，`#` 开头为注释。

## 4. 采集

1. **抓榜单**：4 个榜各抓 5 页，共 20 个请求，用 Baiduspider UA。榜单 key 分别记为 `hot`、`real`、`ai`、`comic`。
2. **校验榜单**：每个榜至少 80 条，且能解析出榜单日期。任何一个榜不满足条件，本次运行判定失败，不写快照，进程以非零状态退出。
3. **检查是否已刷新**（2026-10-14 修订）：
   - 和最近一份更早的快照比较 4 个榜的名次序列。4 个榜都完全相同，说明官方今天还没刷新：不写快照，进程以 0 退出并输出提示，交给下一次定时运行。400 个位置碰巧全部相同几乎不可能。
   - 刷新了的话，每个榜的 `rank_date` 记为今天。页面上解析出的日期另存为 `label_date`，只作记录。
   - 手动加 `--allow-stale` 时，即使没刷新也写快照，`rank_date` 沿用上一份快照的值，这样按 `rank_date` 去重的计算不会重复计入在榜天数。定时任务不使用这个参数。
4. **确定追踪集合**，取以下三类的并集：
   - 今天出现在任意榜上的剧
   - 观察列表中已解析出编号的剧
   - 最近 14 天的快照里上过任意榜、但今天不在榜上的剧
5. **抓详情**：追踪集合里的每部剧抓一次详情页。最多 3 个并发，全局限速为相邻两次请求的发起间隔不少于 0.5 秒。400 部剧大约需要 3–4 分钟。
6. **校验详情**：失败比例超过 10% 时，本次运行判定失败，不写快照。比例不超过 10% 时照常写快照，失败的剧在快照里记为 `null`，并写入 `errors`。
7. **解析观察列表**：
   - 链接形式：从链接里匹配 `series_id=(\d+)` 或 `/player/(\d+)`，提取出编号。
   - 剧名形式：调用搜索，在 `doc_type==23` 的结果里找剧名完全相同的条目。恰好一个则解析成功；没有则记为 `not_found`；多于一个则记为 `ambiguous`。
   - 解析结果缓存到 `data/watchlist_resolved.json`。这个文件由采集步骤维护，不放在 `derived/` 里。已经解析成功的剧名不再重复搜索。

**幂等**：当天的快照文件已存在时直接跳过。加 `--force` 才会覆盖重抓。

### 快照格式 `data/snapshots/YYYY-MM-DD.json`

```json
{
  "date": "2026-10-14",
  "fetched_at": "2026-10-14T04:03:11Z",
  "ranks": {
    "hot":   {"rank_date": "2026-10-14", "items": [{"id": "769...", "rank": 1, "status_tags": ["新剧"]}]},
    "real":  {"rank_date": "2026-10-14", "items": []},
    "ai":    {"rank_date": "2026-10-14", "items": []},
    "comic": {"rank_date": "2026-10-14", "items": []}
  },
  "series": {
    "769...": {
      "title": "首辅娇娘", "tags": ["爱情"], "eps": 80, "first_visible": 1790000000,
      "status": 1, "hot": 67340000, "fav": 1357000, "like": 2623000,
      "rating_cnt": 4820, "review_cnt": 1256, "score": 9.4,
      "sources": ["rank:hot", "rank:real", "watch"]
    },
    "768...": null
  },
  "watchlist": [{"entry": "乖野之下，爱意疯长", "status": "ok", "id": "7677823149873843224"}],
  "errors": [{"stage": "detail", "id": "768...", "message": "HTTP 500 x3"}]
}
```

- `score` 取自榜单的 `scoreText`。不在榜上的剧，或者榜单没给评分的剧，记为 `null`。
- `sources` 记录这部剧为什么会被追踪。

## 5. 计算（derive）

`derive` 每次读取全部快照，按日期排序后重新计算所有派生结果。快照数量在数百份的量级时，全量重算的耗时可以接受，也最不容易出错。

**「上一份快照」的定义**：日期早于今天的、最近的一份快照。两份快照间隔 `gap` 天（正常为 1）。增速计算都按快照日期来。

**榜单计算按 `rank_date` 去重**：对每个榜，把所有快照里的这个榜按 `rank_date` 去重，同一个 `rank_date` 只保留最早的那份，得到一串「榜单日」。5.1 里所说的「上一份」「之前」「连续」都是在榜单日序列上计算的，不是在快照日期上计算。这样，用 `--allow-stale` 写出的、榜单没更新的快照，不会被重复计入在榜天数。

### 5.1 榜单变化 `data/derived/ranks_latest.json`

对每个榜（`hot`、`real`、`ai`、`comic`）、最新榜单日在榜的每部剧，计算：
- `rank`：今天的名次。
- `delta`：上一个榜单日的名次减去最新的名次，正数表示上升。上一个榜单日不在榜时为 `null`。
- `badge`：
  - `new`：在之前所有榜单日里都没上过这个榜。
  - `back`：上一个榜单日不在榜，但更早时上过。
  - 其余情况为 `null`。
- `streak`：截至最新榜单日，连续在榜的榜单日数。
- `best_rank`：历史最高名次。
- `dropped[]`：上一个榜单日在榜、最新榜单日不在榜的剧，附上它们上一次的名次。

### 5.2 增速 `data/derived/growth_latest.json`

对追踪集合里今天和上一份快照都有数据（都不为 `null`）的剧，计算：
- `d_hot`、`d_fav`、`d_like`：今天减上一份，再除以 `gap`，即日均增量。增量可以为负，不截断。
- `r_hot`：`d_hot` 除以上一份快照的热度。上一份热度为 0 时，`r_hot` 记为 `null`。
- `d7_hot`、`d7_fav`：今天减「7 天前那份快照」。需要正好 7 天前的快照存在，否则为 `null`。
- `gap`：大于 1 时，看板旁边标注「间隔 N 天」。
- `type`：取这部剧今天所在的分类榜，优先级为 `real`、`ai`、`comic`（一部剧同时在 `hot` 和某个分类榜时，以分类榜为准）。只出现在 `hot` 榜或只在观察列表里时，记为 `unknown`。

### 5.3 单剧历史 `data/derived/series/<id>.json`

每部出现过的剧一个文件：

```json
{"id": "...", "title": "...", "tags": [], "eps": 0, "first_visible": 0,
 "points": [{"date": "2026-10-14", "hot": 0, "fav": 0, "like": 0, "ranks": {"hot": 3, "real": 1}}]}
```

### 5.4 状态 `data/derived/status.json`

包含：最近一份快照的日期、4 个榜的榜单日期、追踪的剧数、本次的错误摘要、观察列表的解析结果。

## 6. 看板

单页静态网页，源码是 `site/index.html`、`app.js`、`style.css` 三个文件。

`python -m radar build-site` 负责生成 `_site/`（这个目录不提交到 git）：把 `site/*` 复制到 `_site/`，把 `data/derived/` 复制到 `_site/data/derived/`。页面用相对路径 `data/derived/...` 读取数据。Pages 发布和本地预览都使用这同一个 `_site/` 目录，路径保持一致。

- **顶部状态栏**：数据日期、各榜的榜单日期、运行状态（成功，或者部分失败及原因）、追踪剧数。
- **标签页「官方榜」**（默认打开）：下分综合、真人、AI、漫剧四个子页。
  - 表格列：名次、名次变化（↑↓、NEW、回榜）、剧名（带新剧/爆剧标记）、热度、热度日增、收藏（及日增）、评分、连续在榜天数、标签。
  - 顶部有搜索框。表格末尾附「今日掉榜」列表。
- **标签页「飙升榜」**：默认前 50 名。可切换排序（热度日增、收藏日增、热度增长率），可按类型筛选（全部、真人、AI、漫剧、未知）。
- **标签页「观察列表」**：每部剧显示当前指标和最近 7 天的迷你趋势线（手写 SVG）。没解析成功的条目也列出，并写明原因。
- **剧集详情面板**：点任何剧名弹出，内容包括：
  - 热度、收藏、点赞的历史折线（Chart.js，从 CDN 加载）
  - 各榜名次折线，纵轴倒置
  - 基本信息：集数、上线日期、标签、评分人数、评论数
  - 跳转红果的链接：`https://hongguoduanju.com/detail?series_id=<id>`
- 颜色深浅跟随系统，适配手机宽度。表格放在可横向滚动的容器里，页面本身不出现横向滚动。

## 7. 容错与提醒

- **请求**：超时 20 秒；失败重试 3 次，退避间隔为 2、4、8 秒；遇到 429 或 5xx 时额外等待（有 Retry-After 就按它来，最多 45 秒）。
- **失败判定**：见第 4 节的第 2、3、6 步。判定失败时进程以非零状态退出，不写快照、不提交。
- **提醒**：GitHub 会在定时任务失败时给仓库所有者发邮件；看板状态栏也会显示最近一次运行的状态。
- **工作流 `daily.yml`**：
  - 触发：定时在北京时间 10:30、12:00、14:00、17:00、21:00 各跑一次，另外支持手动触发。官方每天刷新一次，时间不固定：没刷新的那几次什么都不写，刷新后的第一次写入快照，之后的运行因为快照已存在而跳过。
  - `collect` 只有真的提交了新数据时才输出 `changed=true`，`deploy` 只在这种情况下运行。
  - 包含两个 job：
    1. `collect`：运行测试 → `python -m radar run` → 有变更时提交 `data/` 并推送。
    2. `deploy`：依赖 `collect`，检出最新的 main，运行 `build-site`，然后用 `upload-pages-artifact` 和 `deploy-pages` 发布。
  - 发布必须放在同一个工作流里完成。原因：用 `GITHUB_TOKEN` 推送的提交不会触发其他工作流的 `on: push`。
- **工作流 `pages.yml`**：只在人工推送到 main 时触发（比如改代码、改观察列表），负责重新发布看板。
- **并发控制**：两个工作流共用一个 `concurrency` 组，同一时间只跑一个实例。

## 8. 测试

- `test_parse.py`：用真实页面样本，校验以下内容：
  - 榜单条数、首条剧名、榜单日期的解析
  - 详情页的热度、收藏、点赞
  - 搜索结果的剧名和编号
- `test_derive.py`：用人造的多日快照，覆盖以下场景：
  - 名次升降
  - NEW、回榜、掉榜
  - 连续在榜天数、历史最高名次
  - 漏采日的日均换算（`gap` = 2）
  - 负增长
  - 7 日增量的有和无
  - 详情为 `null` 时跳过
  - 类型判定
- `test_watchlist.py`：覆盖以下场景：
  - 注释行和空行
  - 链接提取编号
  - 剧名唯一匹配、找不到、重名
- 测试框架用标准库 `unittest`，CI 里不需要额外安装依赖。
- 另外测试：榜单日期解析（含跨年）、按 `rank_date` 去重（一份带 `--allow-stale` 写出的快照不重复计入在榜天数）。
- **看板验证**：运行 `build-site` 后，在 `_site/` 目录下起 `python -m http.server`，用真实采集到的数据打开页面，截图检查桌面宽度和手机宽度下的显示。

## 9. 上线验证

1. 本机跑一次 `python -m radar run`，生成首份真实快照，确认数据正确。
2. 创建公开仓库并推送代码，开启 Pages（来源选 GitHub Actions）。
3. 手动触发一次 `daily.yml`，确认 Actions 的 IP 能抓到红果数据。如果被拦，回到设计层面重新选部署位置，比如改用自有服务器，再继续。
4. 打开看板地址，确认页面正常。
5. 第二天确认定时任务自动运行，并且增量数据第一次出现。
