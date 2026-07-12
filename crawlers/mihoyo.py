import logging
import math

import requests

from .base import BaseCrawler

logger = logging.getLogger(__name__)


class MihoyoCrawler(BaseCrawler):
    """米哈游校招：ats.openout.mihoyo.com 公开岗位列表接口。"""

    API = "https://ats.openout.mihoyo.com/ats-portal/v1/job/list"
    PAGE_SIZE = 100
    MAX_PAGES = 5
    JD_RAW_LIMIT = 300

    def fetch(self) -> list[dict]:
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://jobs.mihoyo.com/#/campus",
            "Content-Type": "application/json",
            "Release-Tag": "v26.7.2-260706",
            "Accept-Language": "zh-CN",
        }
        jobs, seen = [], set()
        page, total_pages = 1, 1
        while page <= min(total_pages, self.MAX_PAGES):
            payload = {
                "pageNo": page,
                "pageSize": self.PAGE_SIZE,
                "channelDetailIds": [1],
                "hireType": 1,
            }
            try:
                resp = requests.post(self.API, json=payload, headers=headers, timeout=20)
                resp.raise_for_status()
                data = resp.json().get("data") or {}
            except Exception as e:  # noqa: BLE001
                logger.warning("[%s] 米哈游岗位接口失败 page=%s: %s", self.company_name, page, e)
                break
            items = data.get("list") or []
            total = int(data.get("total") or len(items))
            total_pages = max(1, math.ceil(total / self.PAGE_SIZE))
            for item in items:
                job_id = item.get("id") or item.get("title")
                title = (item.get("title") or "").strip()
                if not title or job_id in seen:
                    continue
                seen.add(job_id)
                cities = [x.get("addressDetail") for x in item.get("addressDetailList") or [] if x.get("addressDetail")]
                jd_raw = " | ".join(
                    str(x) for x in [item.get("competencyType"), item.get("jobNature"),
                                     item.get("projectName"), item.get("jobSummary")] if x
                )
                jobs.append(self._make_job(
                    title=title,
                    city=" / ".join(cities)[:80],
                    jd_url=f"https://jobs.mihoyo.com/#/campus/position/{job_id}",
                    jd_raw=jd_raw[: self.JD_RAW_LIMIT],
                ))
            if not items:
                break
            page += 1
        logger.info("[%s] 米哈游抓到 %d 个岗位", self.company_name, len(jobs))
        return jobs
