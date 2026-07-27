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
from urllib.parse import urlparse, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from .base import BaseCrawler

logger = logging.getLogger(__name__)

_BLOCKED_RESOURCE_TYPES = {"image", "media", "font"}
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_CAMPAIGN_LABEL_RE = re.compile(
    r"(?<!\d)(?:20\d{2}|[12]\d)\s*(?:届|年)?\s*"
    r"(?:春招|秋招|校招|校园招聘|校园招募|应届生招聘|毕业生招聘|"
    r"暑期实习|日常实习|实习生招聘)",
    re.I,
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
    # Stop on the disabled next button or repeated page content. This is a
    # circuit breaker only, not a normal collection limit.
    MAX_PAGES = 500
    GOTO_WAIT_UNTIL = "networkidle"
    GOTO_TIMEOUT_MS = 60000
    JD_RAW_LIMIT = 500

    @staticmethod
    def _next_button(page):
        locator = page.locator(".atsx-pagination-next")
        if locator.count() == 0:
            return None
        return locator.first

    def fetch(self) -> list[dict]:
        self.pagination_complete = False
        self.pagination_termination_reason = "not_started"
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
                    page.wait_for_selector(
                        ".positionItem-title-text, .listNoData-text",
                        timeout=30000,
                    )
                except PWTimeout as e:
                    logger.warning("[%s] 加载列表超时: %s", self.company_name, e)

                for page_num in range(1, self.MAX_PAGES + 1):
                    page.wait_for_timeout(1500)
                    page_jobs = self._parse_page_jobs(page)
                    new_jobs = [
                        job for job in page_jobs
                        if job["jd_url"] not in seen_urls
                    ]
                    if not new_jobs and page_num > 1:
                        # Client-side pagination can take longer than the
                        # nominal delay. Re-read before declaring a stall.
                        for _ in range(3):
                            page.wait_for_timeout(2500)
                            page_jobs = self._parse_page_jobs(page)
                            new_jobs = [
                                job for job in page_jobs
                                if job["jd_url"] not in seen_urls
                            ]
                            if new_jobs:
                                break

                    for job in new_jobs:
                        seen_urls.add(job["jd_url"])
                        all_jobs.append(job)
                    new_count = len(new_jobs)

                    logger.info("[%s] 第 %d 页解析 %d 个岗位（新增 %d）",
                                self.company_name, page_num, len(page_jobs), new_count)
                    next_btn = self._next_button(page)
                    if next_btn is None:
                        self.pagination_complete = True
                        self.pagination_termination_reason = (
                            "empty_result_no_pagination"
                            if not all_jobs
                            else "single_page_no_pagination"
                        )
                        logger.info("[%s] 页面无分页控件，已完成当前列表", self.company_name)
                        break

                    if new_count == 0 and page_num > 1:
                        cls = next_btn.get_attribute("class") or ""
                        if "disabled" in cls:
                            self.pagination_complete = True
                            self.pagination_termination_reason = "terminal_button_disabled"
                        else:
                            self.pagination_termination_reason = "page_stalled"
                            logger.error(
                                "[%s] 第 %d 页内容持续未刷新且下一页仍可用，本次结果不完整",
                                self.company_name,
                                page_num,
                            )
                        break

                    try:
                        cls = next_btn.get_attribute("class") or ""
                        if "disabled" in cls:
                            logger.info("[%s] 已到末页", self.company_name)
                            self.pagination_complete = True
                            self.pagination_termination_reason = "terminal_button_disabled"
                            break
                        next_btn.click()
                    except Exception as e:
                        self.pagination_termination_reason = "next_page_error"
                        logger.warning("[%s] 翻页失败: %s", self.company_name, e)
                        break
                else:
                    self.pagination_termination_reason = "safety_limit"
                    logger.error(
                        "[%s] 达到 %d 页安全上限，尚未确认末页；本次结果可能不完整",
                        self.company_name,
                        self.MAX_PAGES,
                    )

                context.close()
                browser.close()
        except Exception as e:
            logger.error("[%s] 爬取异常: %s", self.company_name, e)

        logger.info("[%s] 共抓到 %d 个岗位", self.company_name, len(all_jobs))
        return all_jobs

    def _parse_page_jobs(self, page) -> list[dict]:
        soup = BeautifulSoup(page.content(), "html.parser")
        anchors = [
            anchor for anchor in soup.find_all("a", href=True)
            if "/position/" in anchor["href"] and "/detail" in anchor["href"]
        ]
        return self._parse_anchors(anchors)

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
            parts = urlsplit(href)
            href = urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))

            jd_raw = a.get_text(separator=" ", strip=True)[: self.JD_RAW_LIMIT]
            campaign_text = " ".join(dict.fromkeys(
                match.group(0).strip()
                for match in _CAMPAIGN_LABEL_RE.finditer(jd_raw)
            ))

            jobs.append(
                self._make_job(
                    title=title,
                    city=city,
                    jd_url=href,
                    jd_raw=jd_raw,
                    campaign_text=campaign_text,
                )
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
