"""飞书招聘（Lark Recruitment）通用爬虫基类。

小米 / 字节 / 蔚来等都用飞书招聘 SaaS，前端 DOM 完全一致：
    <a href="/campus/position/<ID>/detail">
      <div class="positionItem">
        <div class="positionItem-title">
          <span class="positionItem-title-text">标题</span>
        </div>
        <div class="positionItem-subTitle">
          <span>城市</span> | <span>校招/实习</span> | <span>类别</span> ...
        </div>
      </div>
    </a>
分页是 client-side（`.atsx-pagination-next` 按钮，URL 不变）。

子类只需覆盖类属性（LIST_URL / HOST / MAX_PAGES …），无需重写抓取逻辑。
"""
import logging
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from .base import BaseCrawler

logger = logging.getLogger(__name__)

_BLOCKED_RESOURCE_TYPES = {"image", "media", "font"}
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


class FeishuRecruitCrawler(BaseCrawler):
    """飞书招聘站点的通用 Playwright 翻页爬虫。

    子类覆盖：
        LIST_URL        岗位列表页 URL
        HOST            拼接相对 href 用的站点根（无尾斜杠）
        MAX_PAGES       最多翻几页
        GOTO_WAIT_UNTIL goto 的 wait_until 策略（networkidle / domcontentloaded）
        GOTO_TIMEOUT_MS goto 超时
        JD_RAW_LIMIT    jd_raw 截断长度
    """

    LIST_URL = ""
    HOST = ""
    MAX_PAGES = 10
    GOTO_WAIT_UNTIL = "networkidle"
    GOTO_TIMEOUT_MS = 60000
    JD_RAW_LIMIT = 500

    def fetch(self) -> list[dict]:
        try:
            from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
        except ImportError:
            logger.error("[%s] 未安装 playwright", self.company_name)
            return []

        all_jobs: list[dict] = []
        seen_urls: set[str] = set()

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
                )
                context = browser.new_context(
                    user_agent=_USER_AGENT,
                    viewport={"width": 1366, "height": 768},
                    locale="zh-CN",
                )
                page = context.new_page()
                page.route(
                    "**/*",
                    lambda r: r.abort()
                    if r.request.resource_type in _BLOCKED_RESOURCE_TYPES
                    else r.continue_(),
                )

                try:
                    page.goto(self.LIST_URL, wait_until=self.GOTO_WAIT_UNTIL,
                              timeout=self.GOTO_TIMEOUT_MS)
                    page.wait_for_selector(".positionItem-title-text", timeout=30000)
                except PWTimeout as e:
                    logger.warning("[%s] 加载列表超时: %s", self.company_name, e)

                for page_num in range(1, self.MAX_PAGES + 1):
                    page.wait_for_timeout(1500)
                    soup = BeautifulSoup(page.content(), "html.parser")
                    anchors = [
                        a for a in soup.find_all("a", href=True)
                        if "/position/" in a["href"] and "/detail" in a["href"]
                    ]
                    page_jobs = self._parse_anchors(anchors)

                    new_count = 0
                    for job in page_jobs:
                        if job["jd_url"] in seen_urls:
                            continue
                        seen_urls.add(job["jd_url"])
                        all_jobs.append(job)
                        new_count += 1

                    logger.info("[%s] 第 %d 页解析 %d 个岗位（新增 %d）",
                                self.company_name, page_num, len(page_jobs), new_count)
                    if new_count == 0 and page_num > 1:
                        break

                    next_btn = page.locator(".atsx-pagination-next").first
                    try:
                        cls = next_btn.get_attribute("class") or ""
                        if "disabled" in cls:
                            logger.info("[%s] 已到末页", self.company_name)
                            break
                        next_btn.click()
                    except Exception as e:
                        logger.warning("[%s] 翻页失败: %s", self.company_name, e)
                        break

                context.close()
                browser.close()
        except Exception as e:
            logger.error("[%s] 爬取异常: %s", self.company_name, e)

        logger.info("[%s] 共抓到 %d 个岗位", self.company_name, len(all_jobs))
        return all_jobs

    def _parse_anchors(self, anchors) -> list[dict]:
        jobs = []
        for a in anchors:
            title_el = a.select_one(".positionItem-title-text")
            title = title_el.get_text(strip=True) if title_el else ""
            if not title or len(title) < 2:
                continue

            city = ""
            sub = a.select_one(".positionItem-subTitle")
            if sub:
                first_span = sub.find("span")
                if first_span:
                    city = first_span.get_text(strip=True)

            href = a["href"]
            if not href.startswith("http"):
                href = self.HOST + href

            jd_raw = a.get_text(separator=" ", strip=True)[: self.JD_RAW_LIMIT]

            jobs.append(
                self._make_job(title=title, city=city, jd_url=href, jd_raw=jd_raw)
            )
        return jobs


class GenericFeishuCrawler(FeishuRecruitCrawler):
    """通用飞书招聘爬虫：从 careers_url 自动推导 LIST_URL/HOST，服务任意飞书租户。

    各租户路径 token 不同（campus / campusrecruitment / ponycampus / 398875 …），
    但 DOM（.positionItem-title-text）和详情锚点（/<token>/position/<id>/detail）一致，
    故基类只认 "/position/" + "/detail" 即可通用。

    config 用法：crawler: feishu + careers_url（岗位列表页或申请页都行，自动去 /application）。
    """

    def __init__(self, company_name: str, careers_url: str):
        super().__init__(company_name, careers_url)
        p = urlparse(careers_url)
        self.HOST = f"{p.scheme}://{p.netloc}"
        path = careers_url.split("?")[0].split("#")[0].rstrip("/")
        path = re.sub(r"/application$", "", path)  # 申请页 → 列表页
        self.LIST_URL = path
        self.GOTO_WAIT_UNTIL = "domcontentloaded"
