"""腾讯校招爬虫 —— 自建站 join.qq.com，走公开 JSON API。

join.qq.com 是腾讯「校园招聘」门户，当前同一列表会混有应届正式与实习项目；
社招在另一门户。其搜索 API 公开免鉴权：
    POST https://join.qq.com/api/v1/position/searchPosition
    body: {"keyword":"", "pageIndex":N, "pageSize":50, "recruitType":"40003",
           "bgIds":[], "productIds":[], "categoryIds":[], "workLocations":[], "timestamp":""}
    resp: data.positionList[]（positionTitle=职位名, workCities=地点, bgs=事业群,
          postId=唯一标识）+ data.count=总数。
招聘项目标签用于排除日常/应届实习；只有正式校招项目才返回岗位。
"""
import logging

import requests

from .base import BaseCrawler

logger = logging.getLogger(__name__)


class TencentCrawler(BaseCrawler):
    API = "https://join.qq.com/api/v1/position/searchPosition"
    PAGE_SIZE = 50
    MAX_PAGES = 15
    JD_RAW_LIMIT = 300
    RECRUIT_TYPE = "40003"  # 校园招聘门户

    def fetch(self) -> list[dict]:
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Content-Type": "application/json",
            "Referer": "https://join.qq.com/post.html",
        }
        jobs, seen = [], set()
        for page in range(1, self.MAX_PAGES + 1):
            body = {
                "keyword": "", "pageIndex": page, "pageSize": self.PAGE_SIZE,
                "recruitType": self.RECRUIT_TYPE, "bgIds": [], "productIds": [],
                "categoryIds": [], "workLocations": [], "timestamp": "",
            }
            try:
                resp = requests.post(self.API, json=body, headers=headers, timeout=30)
                data = resp.json().get("data") or {}
            except Exception as e:  # noqa: BLE001
                logger.warning("[%s] 腾讯 API 第%d页失败: %s", self.company_name, page, e)
                break
            plist = data.get("positionList") or []
            if not plist:
                break
            for x in plist:
                pid = str(x.get("postId") or x.get("id") or "")
                if not pid or pid in seen:
                    continue
                seen.add(pid)
                title = (x.get("positionTitle") or "").strip()
                if not title or len(title) < 2:
                    continue
                city = " ".join((x.get("workCities") or "").split())[:40]
                project = (x.get("recruitLabelName") or x.get("projectName") or "校招").strip()
                if "实习" in project:
                    continue
                jd_raw = f"{x.get('bgs', '')} {project}".strip()[:self.JD_RAW_LIMIT]
                jd_url = f"https://join.qq.com/post_detail.html?postId={pid}"
                jobs.append(self._make_job(
                    title=title, city=city, job_type=project, jd_url=jd_url, jd_raw=jd_raw,
                ))
            if len(jobs) >= (data.get("count") or 0):
                break

        logger.info("[%s] 腾讯 抓到 %d 个岗位", self.company_name, len(jobs))
        return jobs
