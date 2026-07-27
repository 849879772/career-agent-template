"""Moka ATS（app.mokahr.com）通用校招爬虫基类。

师兄清单里 ~92 家用 Moka，URL 形如：
    https://app.mokahr.com/campus-recruitment/<slug>/<id>
    https://app.mokahr.com/campus_apply/<slug>/<id>
真正的岗位列表在 hash 路由 `#/jobs` 下（客户端渲染），DOM 结构一致：
    <a href="#/job/<uuid>"> ... <div class="...title...">标题</div> ... </a>
每个岗位有唯一的 #/job/<uuid>，拼成 jd_url（保证 upsert 不塌缩）。

子类无需覆盖任何东西——careers_url 即 Moka 落地页，基类自动跳 #/jobs 抓取。
"""
import logging
import math
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from .base import BaseCrawler
from .render import render_page

logger = logging.getLogger(__name__)


class MokaRecruitCrawler(BaseCrawler):
    EXTRA_WAIT_MS = 6000
    SCROLL_TIMES = 8
    JD_RAW_LIMIT = 300
    PAGE_SIZE = 30
    MAX_PAGES = 30

    def _jobs_url(self, page: int = 1) -> str:
        """Preserve project filters while changing only the Moka page number."""
        parts = urlsplit(self.careers_url)
        fragment = parts.fragment
        if not fragment.lstrip("/").startswith("jobs"):
            fragment = "/jobs"
        route, _, query = fragment.partition("?")
        params = dict(parse_qsl(query, keep_blank_values=True))
        params["page"] = str(page)
        fragment = f"{route}?{urlencode(params)}"
        return urlunsplit(
            (parts.scheme, parts.netloc, parts.path, parts.query, fragment)
        )

    def _parse_page(self, html: str, seen: set[str]) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        base = self.careers_url.split("#")[0].split("?")[0]
        jobs = []
        list_container = soup.find(
            class_=lambda classes: classes and any(
                str(name).startswith("jobs-")
                for name in (
                    classes if isinstance(classes, list) else [classes]
                )
            )
        )
        anchors = (list_container or soup).find_all("a", href=True)
        for a in anchors:
            m = re.search(r"#/job/([0-9a-f\-]{8,})", a["href"], re.I)
            if not m:
                continue
            uuid = m.group(1)
            if uuid in seen:
                continue
            seen.add(uuid)
            # 标题：优先取 class 含 title 的元素；否则取锚点文本去掉"发布于…"
            title_el = a.find(lambda t: t.has_attr("class")
                              and any("title" in c.lower() for c in t["class"]))
            title = (title_el.get_text(strip=True) if title_el
                     else re.split(r"发布于", a.get_text(strip=True))[0]).strip()
            if not title or len(title) < 2:
                continue
            jd_url = f"{base}#/job/{uuid}"
            jd_raw = a.get_text(" ", strip=True)[: self.JD_RAW_LIMIT]
            jobs.append(self._make_job(title=title, jd_url=jd_url, jd_raw=jd_raw))
        return jobs

    @staticmethod
    def _result_count(html: str) -> int | None:
        text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
        match = re.search(r"(?<!\d)(\d{1,5})\s*结果", text)
        return int(match.group(1)) if match else None

    def fetch(self) -> list[dict]:
        jobs: list[dict] = []
        seen: set[str] = set()
        expected_total: int | None = None
        self.pagination_complete = True
        self.pagination_termination_reason = "all_pages"

        for page in range(1, self.MAX_PAGES + 1):
            url = self._jobs_url(page)
            html = render_page(
                url,
                wait_for=None,
                timeout_ms=45000,
                extra_wait_ms=self.EXTRA_WAIT_MS,
                scroll_times=self.SCROLL_TIMES,
            )
            if not html:
                logger.warning("[%s] Moka 第 %d 页渲染失败", self.company_name, page)
                self.pagination_complete = not jobs
                self.pagination_termination_reason = f"render_failed_page_{page}"
                return [] if jobs else jobs

            if expected_total is None:
                expected_total = self._result_count(html)
            page_jobs = self._parse_page(html, seen)
            if not page_jobs:
                if expected_total is not None and len(jobs) < expected_total:
                    self.pagination_complete = False
                    self.pagination_termination_reason = f"empty_page_{page}"
                break
            jobs.extend(page_jobs)

            if expected_total is not None and len(jobs) >= expected_total:
                break
            if expected_total is None and len(page_jobs) < self.PAGE_SIZE:
                break
            if expected_total is not None:
                expected_pages = math.ceil(expected_total / self.PAGE_SIZE)
                if page >= expected_pages:
                    break
        else:
            if expected_total is None or len(jobs) < expected_total:
                self.pagination_complete = False
                self.pagination_termination_reason = "max_pages"

        logger.info(
            "[%s] Moka 抓到 %d 个岗位（预期 %s）",
            self.company_name,
            len(jobs),
            expected_total if expected_total is not None else "未知",
        )
        return jobs
