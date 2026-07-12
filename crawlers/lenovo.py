"""Lenovo campus crawler for the public gateway API."""
import logging

import requests

from .base import BaseCrawler

logger = logging.getLogger(__name__)


class LenovoCrawler(BaseCrawler):
    API = "https://talent.lenovo.com.cn/gateway/jobBase/list"
    PAGE_SIZE = 50
    MAX_PAGES = 20
    JD_RAW_LIMIT = 500

    def fetch(self) -> list[dict]:
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://talent.lenovo.com.cn/position",
            "portal-type": "PC",
            "content-type": "application/json;charset=UTF-8",
        }
        jobs, seen = [], set()
        for page in range(1, self.MAX_PAGES + 1):
            try:
                resp = requests.get(
                    self.API,
                    params={"pageNum": page, "pageSize": self.PAGE_SIZE},
                    headers=headers,
                    timeout=30,
                )
                result = resp.json().get("result") or {}
            except Exception as exc:  # noqa: BLE001
                logger.warning("[%s] Lenovo API page %d failed: %s", self.company_name, page, exc)
                break

            rows = result.get("rows") or []
            if not rows:
                break
            for item in rows:
                jid = str(item.get("id") or "")
                title = item.get("jobName") or ""
                if not title or jid in seen:
                    continue
                seen.add(jid)
                city = str(item.get("workPlace") or "")[:40]
                jd_raw = str(item.get("cont") or item.get("jobDesc") or "")[: self.JD_RAW_LIMIT]
                jobs.append(
                    self._make_job(
                        title=title,
                        city=city,
                        jd_url=f"https://talent.lenovo.com.cn/position/detail?id={jid}",
                        jd_raw=jd_raw,
                    )
                )
            if len(jobs) >= int(result.get("total") or 0):
                break

        logger.info("[%s] Lenovo caught %d jobs", self.company_name, len(jobs))
        return jobs
