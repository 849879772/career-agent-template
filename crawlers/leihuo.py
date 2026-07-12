import logging
import math

import requests

from .base import BaseCrawler

logger = logging.getLogger(__name__)


class LeihuoCrawler(BaseCrawler):
    """NetEase Leihuo campus jobs from xiaozhao.leihuo.netease.com."""

    API = "https://xiaozhao.leihuo.netease.com/api/apply/job/list/show"
    PAGE_SIZE = 50
    MAX_PAGES = 5
    JD_RAW_LIMIT = 1000

    def _project_id(self) -> int:
        url = self.careers_url.lower()
        if "intern" in url:
            return 73
        return 72

    def fetch(self) -> list[dict]:
        project_id = self._project_id()
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": self.careers_url,
            "Accept": "application/json, text/plain, */*",
        }
        jobs, seen = [], set()
        page, total_pages = 1, 1
        while page <= min(total_pages, self.MAX_PAGES):
            params = {
                "job_name": "",
                "page_size": self.PAGE_SIZE,
                "page_number": page,
                "project_id": project_id,
            }
            try:
                resp = requests.get(self.API, params=params, headers=headers, timeout=20)
                resp.raise_for_status()
                data = (resp.json().get("data") or {})
            except Exception as e:  # noqa: BLE001
                logger.warning("[%s] Leihuo position api failed page=%s: %s", self.company_name, page, e)
                break

            items = data.get("apply_job_list") or []
            total = int(data.get("count_number") or len(items))
            total_pages = max(1, math.ceil(total / self.PAGE_SIZE))
            for item in items:
                title = (item.get("job_name") or item.get("name") or "").strip()
                job_id = item.get("id") or title
                if not title or job_id in seen:
                    continue
                seen.add(job_id)
                jd_raw = "\n".join(
                    x for x in [
                        item.get("job_category_name") or "",
                        item.get("job_description") or "",
                        item.get("job_requirement") or "",
                    ] if x
                )
                jobs.append(self._make_job(
                    title=title,
                    city=(item.get("work_place_name") or item.get("work_place") or "")[:80],
                    jd_url=f"https://leihuo.163.com/campus/#/job/{job_id}",
                    jd_raw=jd_raw[: self.JD_RAW_LIMIT],
                ))
            if not items:
                break
            page += 1
        logger.info("[%s] Leihuo fetched %d jobs", self.company_name, len(jobs))
        return jobs
