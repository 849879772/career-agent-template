"""bilibili 校招爬虫 —— 自建站 jobs.bilibili.com。

其职位列表 API(/api/campus/position/positionList)带客户端反爬 token(ajSessionId)，
裸 requests 被挡(-101)。但用 Playwright 渲染真实页面时，页面自身 JS 会带上 token，
DOM 正常填充，故走「渲染 + 解析 DOM + 点击翻页」绕过反爬。
列表 DOM：
    <h4 class="item-title"><span class="text">职位标题</span></h4>
页面卡片没有 href，但列表 API 返回稳定职位 ID 和完整 JD，详情路由为
`/campus/positions/<id>`。爬虫优先消费页面自身携带令牌请求到的 API 响应，
DOM 解析仅作为接口结构变化时的降级方案。
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
        api_jobs, api_seen = [], set()
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

                def capture_position_api(response):
                    if "/api/campus/position/positionList" not in response.url:
                        return
                    try:
                        self._parse_api_payload(response.json(), api_jobs, api_seen)
                    except Exception as exc:  # noqa: BLE001
                        logger.debug("[%s] bilibili API 响应解析失败: %s", self.company_name, exc)

                page.on("response", capture_position_api)
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

        result = api_jobs or jobs
        logger.info(
            "[%s] bilibili 抓到 %d 个岗位（%s）",
            self.company_name,
            len(result),
            "官方 API" if api_jobs else "DOM 降级",
        )
        return result

    def _parse_api_payload(self, payload: dict, jobs: list, seen: set) -> int:
        data = payload.get("data") or {}
        rows = data.get("list") or []
        added = 0
        for row in rows:
            position_id = str(row.get("id") or "").strip()
            title = str(row.get("positionName") or row.get("name") or "").strip()
            if not position_id or not title or position_id in seen:
                continue
            seen.add(position_id)
            city = str(row.get("workCity") or row.get("workLocation") or "").strip()
            description = str(
                row.get("positionDescription")
                or row.get("positionDescriptions")
                or ""
            ).strip()
            published_at = str(row.get("pushTime") or row.get("ctime") or "").split(" ", 1)[0]
            jobs.append(self._make_job(
                title=title,
                city=city,
                job_type="校招 正式",
                jd_url=f"{self.LIST_URL}/{position_id}",
                jd_raw=description,
                published_at=published_at,
                link_kind="detail",
            ))
            added += 1
        return added

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
                                       jd_url=f"{self.LIST_URL}#{key}", link_kind="list"))
            new += 1
        return new
