import logging

from .base import BaseCrawler

logger = logging.getLogger(__name__)


class HuaweiCrawler(BaseCrawler):
    """华为校招 (career.huawei.com)。

    数据来源：列表页加载时浏览器会调用内部 API
        POST https://apigw-dgg-b0.huawei.com/api/apig/channelhw/recruitmentPosition/pub/getJobPage
    返回 JSON 包含 jobName / mainBusiness / jobRequire / workArea 等字段。

    详情页 URL 的 ID 用 `advertisementId` 字段（不是 `advertisementsIntegrationId`——
    后者是内部聚合 ID，前者才是公网 URL 用的）。

    本爬虫用 Playwright 加载页面 + 翻页（API 需浏览器签名，无法纯 requests 重放），
    通过 page.on('response', ...) 拦截 API 响应直接抽取数据，跳过 DOM 解析。

    详情页 URL: https://career.huawei.com/cn/job-details?advertisementId=<ID>
    """

    LIST_URL = (
        "https://career.huawei.com/cn/campus-recruitment-job-list"
        "?recruitmentType=FRESH_GRADUATE"
    )
    DETAIL_URL_TEMPLATE = "https://career.huawei.com/cn/job-details?advertisementId={ad_id}"
    API_PATH_FRAGMENT = "/recruitmentPosition/pub/getJobPage"
    MAX_PAGES = 10

    def fetch(self) -> list[dict]:
        try:
            from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
        except ImportError:
            logger.error("[华为] 未安装 playwright")
            return []

        # 累积每页 API 响应里的 result 数组
        captured_pages: list[list[dict]] = []

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
                )
                context = browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                    ),
                    viewport={"width": 1366, "height": 768},
                    locale="zh-CN",
                )
                page = context.new_page()
                page.route(
                    "**/*",
                    lambda r: r.abort()
                    if r.request.resource_type in {"image", "media", "font"}
                    else r.continue_(),
                )

                def on_response(resp):
                    if self.API_PATH_FRAGMENT in resp.url and resp.status == 200:
                        try:
                            body = resp.json()
                            result = body.get("data", {}).get("result", []) or []
                            captured_pages.append(result)
                        except Exception as e:
                            logger.warning("[华为] API 解析失败: %s", e)

                page.on("response", on_response)

                try:
                    page.goto(self.LIST_URL, wait_until="networkidle", timeout=60000)
                    page.wait_for_selector(".job-item", timeout=30000, state="attached")
                except PWTimeout as e:
                    logger.warning("[华为] 加载超时: %s", e)

                for page_num in range(1, self.MAX_PAGES + 1):
                    page.wait_for_timeout(1500)
                    if len(captured_pages) < page_num:
                        logger.info("[华为] 第 %d 页 API 未捕获，停止翻页", page_num)
                        break
                    logger.info(
                        "[华为] 第 %d 页 API 捕获 %d 个岗位",
                        page_num, len(captured_pages[page_num - 1]),
                    )

                    pagers = page.locator(".pager-item-pager-pc").all()
                    if page_num - 1 >= len(pagers):
                        break
                    try:
                        pagers[page_num - 1].click()
                    except Exception as e:
                        logger.warning("[华为] 翻页失败: %s", e)
                        break

                context.close()
                browser.close()
        except Exception as e:
            logger.error("[华为] 爬取异常: %s", e)

        # 把所有页 API 数据转成 job 字典，按 advertisementId 去重
        all_jobs = []
        seen_ids = set()
        for page_results in captured_pages:
            for item in page_results:
                ad_id = item.get("advertisementId")  # 用公网 URL 字段，不是 advertisementsIntegrationId
                title = (item.get("jobName") or "").strip()
                if not ad_id or not title or ad_id in seen_ids:
                    continue
                seen_ids.add(ad_id)

                city = (item.get("workArea") or item.get("jobArea")
                        or item.get("countryName") or "").strip()
                main = item.get("mainBusiness") or ""
                require = item.get("jobRequire") or ""
                jd_raw = (f"{main}\n{require}").strip()[:1500]

                all_jobs.append(
                    self._make_job(
                        title=title,
                        city=city,
                        jd_url=self.DETAIL_URL_TEMPLATE.format(ad_id=ad_id),
                        jd_raw=jd_raw,
                        published_at=item.get("releaseDate") or "",
                    )
                )

        logger.info("[华为] 共抓到 %d 个岗位", len(all_jobs))
        return all_jobs
