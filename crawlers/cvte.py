"""CVTE campus crawler for the Next.js campus API."""
import logging

import requests

from .base import BaseCrawler

logger = logging.getLogger(__name__)


class CVTECrawler(BaseCrawler):
    PROJECTS_API = "https://campus.cvte.com/api/project"
    POSITIONS_API = "https://campus.cvte.com/api/position"
    JD_RAW_LIMIT = 500

    def fetch(self) -> list[dict]:
        headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://campus.cvte.com/position"}
        try:
            projects_resp = requests.get(self.PROJECTS_API, headers=headers, timeout=30)
            projects = projects_resp.json().get("projects") or []
        except Exception as exc:  # noqa: BLE001
            logger.warning("[%s] CVTE projects API failed: %s", self.company_name, exc)
            projects = []

        project_ids = [p.get("id") for p in projects if p.get("id")]
        if not project_ids:
            logger.info("[%s] CVTE no active project positions", self.company_name)
            return []

        params = {"projectIds": ",".join(project_ids)}
        try:
            resp = requests.get(self.POSITIONS_API, params=params, headers=headers, timeout=30)
            rows = resp.json().get("projectPositions") or []
        except Exception as exc:  # noqa: BLE001
            logger.warning("[%s] CVTE positions API failed: %s", self.company_name, exc)
            return []

        jobs, seen = [], set()
        for item in rows:
            jid = str(item.get("id") or "")
            title = item.get("name") or item.get("positionName") or ""
            if not title or jid in seen:
                continue
            seen.add(jid)
            city = "、".join(a.get("cityName", "") for a in item.get("areaViews", []) if a)[:40]
            jd_raw = "\n".join(
                x for x in [item.get("duty") or "", item.get("requirement") or ""] if x
            )[: self.JD_RAW_LIMIT]
            jobs.append(
                self._make_job(
                    title=title,
                    city=city,
                    jd_url=f"https://campus.cvte.com/position/{jid}",
                    jd_raw=jd_raw,
                )
            )

        logger.info("[%s] CVTE caught %d jobs", self.company_name, len(jobs))
        return jobs
