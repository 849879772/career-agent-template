"""北森 ATS（*.zhiye.com）通用校招爬虫基类。

师兄清单里 ~106 家用北森，URL 形如 https://<subdomain>.zhiye.com/...
现代北森校招 UI 在 `/campus/jobs`，岗位标题渲染在 DOM 里（styled-components）：
    <div class="...STListItemContent...">
      <div class="...STTitleSection...">
        <div class="...STJobTitle...">【代码】岗位标题</div>
优先调用北森 2022 门户 API 获取岗位列表和真实详情页链接；API 不可用时回退 DOM 渲染。

子类无需覆盖——careers_url 给任意北森页，基类按子域名拼 /campus/jobs 抓取。
注：少数老租户只有旧版 /Portal/Apply/Index（DOM 不同），本基类抓不到会返回空（优雅降级）。
"""
import logging
import re
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from .base import BaseCrawler
from .render import render_page

logger = logging.getLogger(__name__)


class BeisenRecruitCrawler(BaseCrawler):
    EXTRA_WAIT_MS = 6000
    SCROLL_TIMES = 8
    JD_RAW_LIMIT = 300
    PAGE_SIZE = 100
    # 北森列表页的栏目标题也带 STJobTitle 类，需剔除，避免写成假岗位
    _SKIP_TITLES = {"热招职位", "热门职位", "推荐职位", "热招岗位", "在招职位", "全部职位"}

    def _list_url(self) -> str:
        host = urlparse(self.careers_url).netloc
        return f"https://{host}/campus/jobs"

    def _origin(self) -> str:
        p = urlparse(self._list_url())
        return f"{p.scheme}://{p.netloc}"

    def _api_url(self) -> str:
        return f"{self._origin()}/api/Jobad/GetJobAdPageList"

    def _detail_url(self, job_ad_id: str) -> str:
        return f"{self._origin()}/campus/detail?jobAdId={job_ad_id}"

    def _api_payload(self, page_index: int) -> dict:
        return {
            "PageIndex": page_index,
            "PageSize": self.PAGE_SIZE,
            "Category": ["2"],
            "KeyWords": "",
            "SpecialType": 0,
            "PortalId": "",
            "DisplayFields": [
                "Category", "Kind", "LocId", "PostDate", "WorkWeChatQrCode",
            ],
        }

    def _fetch_api_jobs(self) -> list[dict]:
        session = requests.Session()
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json;charset=UTF-8",
            "Origin": self._origin(),
            "Referer": self._list_url(),
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
            ),
        }

        jobs: list[dict] = []
        seen = set()
        total = None
        page_index = 0
        while True:
            resp = session.post(
                self._api_url(),
                json=self._api_payload(page_index),
                headers=headers,
                timeout=25,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("Code") != 200:
                raise RuntimeError(data.get("Message") or "北森 API 返回非 200")

            rows = data.get("Data") or []
            if not isinstance(rows, list) or not rows:
                break
            total = data.get("Total") or data.get("Count") or total

            for row in rows:
                title = (row.get("JobAdName") or "").strip()
                job_id = str(row.get("Id") or "").strip()
                if not title or not job_id or job_id in seen:
                    continue
                seen.add(job_id)
                locs = row.get("LocNames") or []
                city = "、".join(str(x) for x in locs if x)[:80]
                jd_raw = "\n".join(
                    part for part in [
                        row.get("Duty") or "",
                        row.get("Require") or "",
                    ] if part
                )[: self.JD_RAW_LIMIT]
                jobs.append(self._make_job(
                    title=title,
                    city=city,
                    jd_url=self._detail_url(job_id),
                    jd_raw=jd_raw,
                ))

            page_index += 1
            if total is not None and len(jobs) >= int(total):
                break
            if len(rows) < self.PAGE_SIZE:
                break
            if page_index > 50:
                break

        return jobs

    def fetch(self) -> list[dict]:
        list_url = self._list_url()
        try:
            api_jobs = self._fetch_api_jobs()
            if api_jobs:
                logger.info("[%s] 北森 API 抓到 %d 个岗位", self.company_name, len(api_jobs))
                return api_jobs
        except Exception as e:
            logger.warning("[%s] 北森 API 抓取失败，回退渲染：%s", self.company_name, e)

        html = render_page(list_url, wait_for=None, timeout_ms=45000,
                           extra_wait_ms=self.EXTRA_WAIT_MS, scroll_times=self.SCROLL_TIMES)
        if not html:
            logger.warning("[%s] 北森 渲染失败", self.company_name)
            return []

        soup = BeautifulSoup(html, "html.parser")
        title_els = soup.find_all(
            lambda t: t.has_attr("class") and any("STJobTitle" in c for c in t["class"])
        )
        jobs = []
        seen = set()
        for el in title_els:
            title = el.get_text(" ", strip=True)
            if not title or len(title) < 2:
                continue
            if title in self._SKIP_TITLES:
                continue
            # 提取【代码】作唯一标识；无则用标题哈希兜底
            m = re.match(r"^[【\[]([^】\]]+)[】\]]", title)
            key = m.group(1) if m else str(abs(hash(title)) % (10 ** 8))
            if key in seen:
                continue
            seen.add(key)
            jd_url = f"{list_url}#{key}"
            # 城市：在所属列表项容器里找含 City/Location/地点 的标签
            container = el.find_parent(
                lambda t: t.has_attr("class") and any("STListItem" in c for c in t["class"])
            )
            city = ""
            if container:
                city_el = container.find(
                    lambda t: t.has_attr("class")
                    and any(("City" in c or "Location" in c or "Address" in c) for c in t["class"])
                )
                if city_el:
                    city = city_el.get_text(" ", strip=True)[:40]
            jobs.append(self._make_job(title=title, city=city, jd_url=jd_url))

        logger.info("[%s] 北森 抓到 %d 个岗位", self.company_name, len(jobs))
        return jobs
