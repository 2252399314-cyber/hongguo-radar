"""测试用：生成和红果页面结构一致的假页面，以及按 URL 返回页面的 FakeFetcher。"""

import json

from radar.http import FetchError


def page(loader_data):
    body = json.dumps({"loaderData": loader_data, "errors": None}, ensure_ascii=False)
    return "<html><body><script>_ROUTER_DATA = " + body + ";\nfunction runWindowFn(){}</script></body></html>"


def rank_html(slug, updated_text, items, total_pages):
    """items: [(编号, 名次), ...]"""
    rank_list = [
        {
            "id": sid,
            "seriesId": sid,
            "rank": rank,
            "title": "剧" + sid,
            "scoreText": "评分8.5",
            "statusTags": [],
            "tags": ["都市"],
        }
        for sid, rank in items
    ]
    return page(
        {
            "rank_layout": None,
            "rank_" + slug + "/page": {
                "updatedText": updated_text,
                "content": {"rankList": rank_list, "pagination": {"totalPages": total_pages}},
            },
        }
    )


def detail_html(sid, hot=1000, fav=100, like=10):
    return page(
        {
            "detail_page": {
                "seriesDetail": {
                    "series_id": sid,
                    "series_name": "剧" + sid,
                    "episode_cnt": 80,
                    "first_visible_time": "1780000000",
                    "tags": ["都市"],
                    "series_episode_info": {"series_status": 1},
                },
                "seriesSocialInfo": {
                    "hot_score_data": {"score": hot},
                    "series_favorite_count": str(fav),
                    "series_like_count": str(like),
                    "rating_count": "5",
                    "reviews": {"total_count": "2"},
                },
            }
        }
    )


def search_html(results):
    """results: [(剧名, 编号), ...]"""
    return page(
        {
            "search_(keyword)/page": {
                "searchList": [
                    {"doc_type": 23, "name": title, "keyword": sid, "video_data": {"series_id": sid}}
                    for title, sid in results
                ]
            }
        }
    )


class FakeFetcher:
    def __init__(self, pages):
        self.pages = dict(pages)
        self.calls = []

    def get(self, url, ua=None):
        self.calls.append((url, ua))
        if url not in self.pages:
            raise FetchError(url + ": HTTP 404")
        return self.pages[url]
