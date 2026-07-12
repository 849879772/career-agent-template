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
import re

from bs4 import BeautifulSoup

from .base import BaseCrawler
from .render import render_page

logger = logging.getLogger(__name__)


class MokaRecruitCrawler(BaseCrawler):
    EXTRA_WAIT_MS = 6000
    SCROLL_TIMES = 8
    JD_RAW_LIMIT = 300

    def _jobs_url(self) -> str:
        # 去掉已有 hash/query，统一追加 #/jobs
        base = self.careers_url.split("#")[0].split("?")[0]
        return base + "#/jobs"

    def fetch(self) -> list[dict]:
        url = self._jobs_url()
        html = render_page(url, wait_for=None, timeout_ms=45000,
                           extra_wait_ms=self.EXTRA_WAIT_MS, scroll_times=self.SCROLL_TIMES)
        if not html:
            logger.warning("[%s] Moka 渲染失败", self.company_name)
            return []

        soup = BeautifulSoup(html, "html.parser")
        base = self.careers_url.split("#")[0].split("?")[0]
        jobs = []
        seen = set()
        for a in soup.find_all("a", href=True):
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

        logger.info("[%s] Moka 抓到 %d 个岗位", self.company_name, len(jobs))
        return jobs
