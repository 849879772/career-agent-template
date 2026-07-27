import json
import logging
from datetime import datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .feishu import FeishuRecruitCrawler

logger = logging.getLogger(__name__)


class ByteDanceCrawler(FeishuRecruitCrawler):
    """字节跳动校招：通过官网岗位 API 按总数完整分页。"""

    LIST_URL = "https://jobs.bytedance.com/campus/position"
    HOST = "https://jobs.bytedance.com"
    GOTO_TIMEOUT_MS = 45000
    JD_RAW_LIMIT = 12000
    API_PAGE_SIZE = 100

    def fetch(self) -> list[dict]:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.error("[%s] 未安装 playwright", self.company_name)
            return []

        self.pagination_complete = False
        self.pagination_termination_reason = "not_started"
        self.total_count = 0
        jobs_by_id: dict[str, dict] = {}

        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    headless=True,
                    args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
                )
                context = browser.new_context(locale="zh-CN")
                page = context.new_page()
                captured: dict = {}

                def capture_search(response):
                    if (
                        "/api/v1/search/job/posts" in response.url
                        and response.status == 200
                        and not captured
                    ):
                        captured.update(
                            url=response.url,
                            headers=response.request.headers,
                            payload=response.request.post_data_json,
                        )

                page.on("response", capture_search)
                page.goto(
                    self.LIST_URL,
                    wait_until="networkidle",
                    timeout=self.GOTO_TIMEOUT_MS,
                )
                page.wait_for_timeout(500)
                if not captured:
                    raise RuntimeError("未捕获到字节岗位搜索 API")

                csrf = captured["headers"].get("x-csrf-token", "")
                base_payload = dict(captured["payload"])
                for offset in range(0, 1_000_000, self.API_PAGE_SIZE):
                    payload = dict(base_payload)
                    payload.update(limit=self.API_PAGE_SIZE, offset=offset)
                    api_url = self._api_page_url(
                        captured["url"], offset, self.API_PAGE_SIZE
                    )
                    result = None
                    for attempt in range(3):
                        result = page.evaluate(
                            """async ({url, payload, csrf}) => {
                                const response = await fetch(url, {
                                    method: "POST",
                                    headers: {
                                        "content-type": "application/json",
                                        "x-csrf-token": csrf,
                                        "portal-channel": "campus",
                                        "portal-platform": "pc",
                                        "website-path": "campus"
                                    },
                                    body: JSON.stringify(payload),
                                    credentials: "include"
                                });
                                return {
                                    status: response.status,
                                    text: await response.text()
                                };
                            }""",
                            {"url": api_url, "payload": payload, "csrf": csrf},
                        )
                        if result["status"] == 200 and result["text"]:
                            break
                        page.wait_for_timeout(1000 * (attempt + 1))
                    if not result or result["status"] != 200 or not result["text"]:
                        raise RuntimeError(
                            f"岗位 API 分页失败 offset={offset}, "
                            f"status={result and result['status']}"
                        )

                    body = json.loads(result["text"])
                    if body.get("code") != 0:
                        raise RuntimeError(
                            f"岗位 API 返回错误 offset={offset}: {body.get('message')}"
                        )
                    data = body.get("data") or {}
                    items = data.get("job_post_list") or []
                    self.total_count = int(data.get("count") or self.total_count)
                    for item in items:
                        job_id = str(item.get("id") or "")
                        if job_id:
                            jobs_by_id[job_id] = self._parse_api_job(item)
                    logger.info(
                        "[%s] API offset=%d 返回 %d 条，累计 %d/%d",
                        self.company_name,
                        offset,
                        len(items),
                        len(jobs_by_id),
                        self.total_count,
                    )
                    if offset + len(items) >= self.total_count:
                        self.pagination_complete = len(jobs_by_id) == self.total_count
                        self.pagination_termination_reason = (
                            "api_total_reached"
                            if self.pagination_complete
                            else "api_count_mismatch"
                        )
                        break
                    if not items:
                        self.pagination_termination_reason = "api_empty_before_total"
                        break

                context.close()
                browser.close()
        except Exception as exc:
            logger.error("[%s] 字节岗位 API 抓取异常: %s", self.company_name, exc)

        if not self.pagination_complete:
            logger.error(
                "[%s] API 抓取未完整结束：%s，获得 %d/%d",
                self.company_name,
                self.pagination_termination_reason,
                len(jobs_by_id),
                self.total_count,
            )
        return list(jobs_by_id.values())

    @staticmethod
    def _api_page_url(url: str, offset: int, limit: int) -> str:
        parts = urlsplit(url)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        query.update(offset=str(offset), limit=str(limit))
        return urlunsplit(
            (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
        )

    def _parse_api_job(self, item: dict) -> dict:
        job_id = str(item.get("id") or "")
        city_list = item.get("city_list") or []
        cities = [
            str(city.get("name") or city.get("i18n_name") or "").strip()
            for city in city_list
            if isinstance(city, dict)
        ]
        if not cities and isinstance(item.get("city_info"), dict):
            cities = [
                str(
                    item["city_info"].get("name")
                    or item["city_info"].get("i18n_name")
                    or ""
                ).strip()
            ]

        recruit_type = item.get("recruit_type") or {}
        subject = item.get("job_subject") or {}
        subject_name = subject.get("name") if isinstance(subject, dict) else ""
        if isinstance(subject_name, dict):
            subject_name = (
                subject_name.get("zh_cn")
                or subject_name.get("i18n")
                or subject_name.get("en_us")
                or ""
            )
        job_type = " ".join(
            value
            for value in [
                str(recruit_type.get("name") or "").strip()
                if isinstance(recruit_type, dict)
                else "",
                str(subject_name or "").strip(),
            ]
            if value
        ) or "校招"

        description = str(item.get("description") or "").strip()
        requirement = str(item.get("requirement") or "").strip()
        jd_raw = "\n".join(
            value
            for value in [
                "职位描述" if description else "",
                description,
                "任职要求" if requirement else "",
                requirement,
            ]
            if value
        )
        published_at = ""
        publish_time = item.get("publish_time")
        if isinstance(publish_time, (int, float)) and publish_time:
            published_at = datetime.fromtimestamp(publish_time / 1000).date().isoformat()

        return self._make_job(
            title=str(item.get("title") or "").strip(),
            city=" / ".join(dict.fromkeys(filter(None, cities)))[:120],
            job_type=job_type,
            jd_url=f"{self.HOST}/campus/position/{job_id}/detail",
            jd_raw=jd_raw[: self.JD_RAW_LIMIT],
            published_at=published_at,
            link_kind="detail",
        )
