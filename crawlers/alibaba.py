import logging
import math
from urllib.parse import urlparse

import requests

from .base import BaseCrawler

logger = logging.getLogger(__name__)


class AlibabaCrawler(BaseCrawler):
    """阿里巴巴校园招聘：campus-talent.alibaba.com 公开岗位搜索接口。"""

    DEFAULT_HOST = "campus-talent.alibaba.com"
    DEFAULT_BATCH_ID = 100000540002
    PAGE_SIZE = 50
    MAX_PAGES = 20
    JD_RAW_LIMIT = 1000

    def _origin(self) -> str:
        host = urlparse(self.careers_url).netloc or self.DEFAULT_HOST
        if host in {"campus.alibaba.com", "talent.alibaba.com"}:
            host = self.DEFAULT_HOST
        return f"https://{host}"

    def _position_url(self, batch_id: int | None = None) -> str:
        url = f"{self._origin()}/campus/position"
        return f"{url}?batchId={batch_id}" if batch_id else url

    def _session(self) -> requests.Session:
        s = requests.Session()
        s.headers.update({
            "User-Agent": "Mozilla/5.0",
            "Referer": self._position_url(self.DEFAULT_BATCH_ID),
            "Content-Type": "application/json",
        })
        s.get(self._position_url(self.DEFAULT_BATCH_ID), timeout=20)
        return s

    def _batch_ids(self, s: requests.Session) -> list[int]:
        if self._origin().endswith(self.DEFAULT_HOST):
            return [self.DEFAULT_BATCH_ID]
        csrf = s.cookies.get("XSRF-TOKEN")
        if not csrf:
            return []
        try:
            resp = s.post(
                f"{self._origin()}/searchCondition/listBatch?_csrf={csrf}",
                json={"channel": "campus_group_official_site", "language": "zh"},
                timeout=20,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:  # noqa: BLE001
            logger.warning("[%s] 阿里系批次接口失败: %s", self.company_name, e)
            return []

        ids: list[int] = []

        def walk(obj):
            if isinstance(obj, dict):
                if obj.get("id") is not None and str(obj.get("id")).isdigit():
                    ids.append(int(obj["id"]))
                for v in obj.values():
                    walk(v)
            elif isinstance(obj, list):
                for item in obj:
                    walk(item)

        walk(data.get("content") or data)
        return list(dict.fromkeys(ids))

    def fetch(self) -> list[dict]:
        s = self._session()
        csrf = s.cookies.get("XSRF-TOKEN")
        if not csrf:
            logger.warning("[%s] 阿里巴巴未拿到 XSRF-TOKEN", self.company_name)
            return []

        jobs, seen = [], set()
        for batch_id in self._batch_ids(s):
            total_pages = 1
            page = 1
            while page <= min(total_pages, self.MAX_PAGES):
                payload = {
                    "batchId": batch_id,
                    "pageIndex": page,
                    "pageSize": self.PAGE_SIZE,
                    "channel": "campus_group_official_site",
                    "language": "zh",
                }
                try:
                    resp = s.post(f"{self._origin()}/position/search?_csrf={csrf}", json=payload, timeout=20)
                    resp.raise_for_status()
                    content = (resp.json().get("content") or {})
                except Exception as e:  # noqa: BLE001
                    logger.warning("[%s] 阿里系岗位接口失败 batch=%s page=%s: %s",
                                   self.company_name, batch_id, page, e)
                    break

                items = content.get("datas") or []
                total = content.get("totalCount") or content.get("total") or len(items)
                total_pages = max(1, math.ceil(int(total) / self.PAGE_SIZE)) if str(total).isdigit() else total_pages
                for item in items:
                    title = (item.get("name") or "").strip()
                    job_id = item.get("id") or title
                    if not title or job_id in seen:
                        continue
                    seen.add(job_id)
                    city = " / ".join(item.get("workLocations") or [])
                    jd_raw = "\n".join(
                        x for x in [item.get("description") or "", item.get("requirement") or ""] if x
                    )
                    jobs.append(self._make_job(
                        title=title,
                        city=city[:80],
                        jd_url=f"{self._origin()}/campus/position-detail?positionId={job_id}",
                        jd_raw=jd_raw[: self.JD_RAW_LIMIT],
                        published_at="",
                    ))
                if not items:
                    break
                page += 1
        logger.info("[%s] 阿里系抓到 %d 个岗位", self.company_name, len(jobs))
        return jobs
