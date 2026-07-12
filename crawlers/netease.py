import logging
import math
from urllib.parse import parse_qs, urlparse

import requests

from .base import BaseCrawler

logger = logging.getLogger(__name__)


class NetEaseCrawler(BaseCrawler):
    """NetEase campus jobs from campus.163.com project position pages."""

    API = "https://campus.163.com/api/campuspc/position/getJobList"
    PAGE_SIZE = 50
    MAX_PAGES = 5
    JD_RAW_LIMIT = 1000

    def _project_id(self) -> str:
        parsed = urlparse(self.careers_url)
        params = parse_qs(parsed.query)
        if params.get("id"):
            return params["id"][0]
        return "69"

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
                "pageSize": self.PAGE_SIZE,
                "currentPage": page,
                "projectId": project_id,
            }
            try:
                resp = requests.get(self.API, params=params, headers=headers, timeout=20)
                resp.raise_for_status()
                data = (resp.json().get("data") or {})
            except Exception as e:  # noqa: BLE001
                logger.warning("[%s] NetEase position api failed page=%s: %s", self.company_name, page, e)
                break

            items = data.get("list") or []
            total = int(data.get("total") or len(items))
            total_pages = max(1, math.ceil(total / self.PAGE_SIZE))
            for item in items:
                title = (item.get("positionName") or "").strip()
                job_id = item.get("id") or title
                if not title or job_id in seen:
                    continue
                seen.add(job_id)
                jd_raw = "\n".join(
                    x for x in [
                        item.get("positionTypeName") or "",
                        item.get("firstBuName") or "",
                        item.get("positionDescription") or "",
                        item.get("positionRequirement") or "",
                    ] if x
                )
                jobs.append(self._make_job(
                    title=title,
                    city=(item.get("workPlaceName") or "")[:80],
                    jd_url=f"https://campus.163.com/app/job/detail/{job_id}?projectId={project_id}",
                    jd_raw=jd_raw[: self.JD_RAW_LIMIT],
                ))
            if not items:
                break
            page += 1
        logger.info("[%s] NetEase fetched %d jobs", self.company_name, len(jobs))
        return jobs
