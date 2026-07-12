import logging
import random
from typing import Optional

import requests

logger = logging.getLogger(__name__)

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]


class BaseCrawler:
    def __init__(self, company_name: str, careers_url: str):
        self.company_name = company_name
        self.careers_url = careers_url

    def fetch(self) -> list[dict]:
        raise NotImplementedError

    def _get(self, url: str, **kwargs) -> Optional[requests.Response]:
        headers = dict(kwargs.pop("headers", {}))
        headers.setdefault("User-Agent", random.choice(_USER_AGENTS))
        headers.setdefault("Accept-Language", "zh-CN,zh;q=0.9,en;q=0.8")
        try:
            resp = requests.get(url, headers=headers, timeout=15, **kwargs)
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            logger.error("[%s] 请求失败 %s: %s", self.company_name, url, e)
            return None

    def _make_job(
        self,
        title: str,
        city: str = "",
        job_type: str = "校招",
        jd_url: str = "",
        jd_raw: str = "",
        published_at: str = "",
        link_kind: str = "detail",
    ) -> dict:
        return {
            "company": self.company_name,
            "title": title,
            "city": city,
            "job_type": job_type,
            "jd_url": jd_url or self.careers_url,
            "jd_raw": jd_raw,
            "published_at": published_at,
            "link_kind": link_kind,
            "source": self.company_name,
        }
