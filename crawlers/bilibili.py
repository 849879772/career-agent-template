"""bilibili 校招爬虫 —— 自建站 jobs.bilibili.com。

其职位列表 API(/api/campus/position/positionList)带客户端反爬 token(ajSessionId)，
裸 requests 被挡(-101)。但用 Playwright 渲染真实页面时，页面自身 JS 会带上 token，
DOM 正常填充，故走「渲染 + 解析 DOM + 点击翻页」绕过反爬。
列表 DOM：
    <h4 class="item-title"><span class="text">职位标题</span></h4>
职位非稳定 <a>(JS 跳转)，用标题哈希作唯一 jd_url(同 hotjob/北森做法)。
"""
import logging
import re

from bs4 import BeautifulSoup

from .base import BaseCrawler

logger = logging.getLogger(__name__)

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
_CITY_RE = re.compile(r"[一-龥]{2,}(?:市|省)")


class BilibiliCrawler(BaseCrawler):
    LIST_URL = "https://jobs.bilibili.com/campus/positions"
    MAX_PAGES = 30
    JD_RAW_LIMIT = 200

    def fetch(self) -> list[dict]:
        try:
            from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
        except ImportError:
            logger.error("[%s] 未安装 playwright", self.company_name)
            return []

        jobs, seen = [], set()
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=["--disable-blink-features=AutomationControlled", "--no-sandbox",
                          "--disable-dev-shm-usage"],
                )
                ctx = browser.new_context(user_agent=_UA, viewport={"width": 1366, "height": 768},
                                          locale="zh-CN")
                page = ctx.new_page()
                try:
                    page.goto(self.LIST_URL, wait_until="networkidle", timeout=45000)
                except PWTimeout:
                    logger.warning("[%s] goto 超时，仍尝试解析", self.company_name)
                try:
                    page.wait_for_selector(".item-title", timeout=30000)
                except PWTimeout:
                    logger.info("[%s] 未出现职位列表（淡季空？）", self.company_name)

                for _ in range(self.MAX_PAGES):
                    page.wait_for_timeout(1000)
                    new = self._parse(page.content(), jobs, seen)
                    if new == 0:
                        break
                    # 翻页：找「下一页」按钮，禁用/缺失则停
                    nxt = page.locator(
                        ".btn-next, .el-pagination .btn-next, "
                        "[class*='pagination'] [class*='next']"
                    ).first
                    try:
                        if nxt.count() == 0:
                            break
                        cls = (nxt.get_attribute("class") or "") + str(nxt.get_attribute("disabled"))
                        if "disabled" in cls or nxt.get_attribute("aria-disabled") == "true":
                            break
                        nxt.click(timeout=5000)
                    except Exception:
                        break

                ctx.close()
                browser.close()
        except Exception as e:  # noqa: BLE001
            logger.error("[%s] bilibili 爬取异常: %s", self.company_name, e)

        logger.info("[%s] bilibili 抓到 %d 个岗位", self.company_name, len(jobs))
        return jobs

    def _parse(self, html: str, jobs: list, seen: set) -> int:
        soup = BeautifulSoup(html, "html.parser")
        new = 0
        for h in soup.select(".item-title"):
            span = h.select_one(".text") or h
            title = span.get_text(" ", strip=True)
            if not title or len(title) < 2:
                continue
            key = str(abs(hash(title)) % (10 ** 8))
            if key in seen:
                continue
            seen.add(key)
            # 城市：从所在卡片容器文本里抽
            card = h.find_parent(lambda t: t.has_attr("class") and any(
                "item" in c and "title" not in c for c in t["class"]))
            ctext = card.get_text(" ", strip=True) if card else ""
            m = _CITY_RE.findall(ctext)
            city = "、".join(dict.fromkeys(m))[:40]
            jobs.append(self._make_job(title=title, city=city,
                                       jd_url=f"{self.LIST_URL}#{key}"))
            new += 1
        return new
