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
import time
from concurrent.futures import ThreadPoolExecutor

import requests
from bs4 import BeautifulSoup

from .base import BaseCrawler

logger = logging.getLogger(__name__)


class TencentCrawler(BaseCrawler):
    API = "https://join.qq.com/api/v1/position/searchPosition"
    DETAIL_API = "https://join.qq.com/api/v1/jobDetails/getJobDetailsByPostId"
    PAGE_SIZE = 50
    MAX_PAGES = 15
    DETAIL_WORKERS = 8
    JD_RAW_LIMIT = 12000
    RECRUIT_TYPE = "40003"  # 校园招聘门户

    @staticmethod
    def _clean_detail(value: object) -> str:
        if not value:
            return ""
        soup = BeautifulSoup(str(value), "html.parser")
        return "\n".join(
            line.strip() for line in soup.get_text("\n").splitlines() if line.strip()
        )

    def _fetch_detail(self, post_id: str, headers: dict) -> str | None:
        try:
            resp = requests.get(
                self.DETAIL_API,
                params={"timestamp": int(time.time() * 1000), "postId": post_id},
                headers=headers,
                timeout=20,
            )
            payload = resp.json()
            if payload.get("status") == 404 or "下架" in str(payload.get("message") or ""):
                return None
            data = payload.get("data") or {}
            duties = self._clean_detail(
                data.get("desc")
                or data.get("topicDetail")
                or data.get("introduction")
            )
            requirements = self._clean_detail(
                data.get("request")
                or data.get("topicRequirement")
            )
            parts = []
            if duties:
                parts.extend(["岗位职责", duties])
            if requirements:
                parts.extend(["任职要求", requirements])
            return "\n".join(parts)[: self.JD_RAW_LIMIT]
        except Exception as exc:  # noqa: BLE001
            logger.warning("[%s] 腾讯岗位 %s 详情获取失败: %s", self.company_name, post_id, exc)
            return ""

    def fetch(self) -> list[dict]:
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Content-Type": "application/json",
            "Referer": "https://join.qq.com/post.html",
        }
        rows, seen = [], set()
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
                rows.append((pid, title, city, project, str(x.get("bgs") or "").strip()))
            if page * self.PAGE_SIZE >= (data.get("count") or 0):
                break

        detail_headers = {
            "User-Agent": headers["User-Agent"],
            "Referer": "https://join.qq.com/post.html",
        }
        with ThreadPoolExecutor(max_workers=self.DETAIL_WORKERS) as executor:
            details = dict(zip(
                (row[0] for row in rows),
                executor.map(lambda row: self._fetch_detail(row[0], detail_headers), rows),
            ))

        jobs = []
        for pid, title, city, project, business_group in rows:
            detail = details.get(pid)
            if detail is None:
                logger.info("[%s] 跳过官网已下架岗位 %s", self.company_name, pid)
                continue
            jd_raw = detail or f"{business_group} {project}".strip()
            jobs.append(self._make_job(
                title=title,
                city=city,
                job_type=project,
                jd_url=f"https://join.qq.com/post_detail.html?postId={pid}",
                jd_raw=jd_raw,
            ))

        logger.info("[%s] 腾讯 抓到 %d 个岗位", self.company_name, len(jobs))
        return jobs
