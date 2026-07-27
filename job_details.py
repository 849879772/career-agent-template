"""On-demand job-detail hydration for sparse crawler records."""

from __future__ import annotations

import logging
import re
import time
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

import requests
import yaml
from bs4 import BeautifulSoup

from crawlers.hotjob import fetch_hotjob_position_detail
from crawlers.render import render_page

logger = logging.getLogger(__name__)

_DETAIL_SIGNAL_RE = re.compile(
    r"职位描述|岗位描述|职位职责|岗位职责|工作职责|任职要求|岗位要求|"
    r"任职资格|招聘要求|加分项|responsibilities|requirements|qualifications",
    re.I,
)
_PUBLISHED_ONLY_RE = re.compile(r"发布于\s*20\d{2}[-/.]\d{1,2}[-/.]\d{1,2}")
_EMPTY_DETAIL_SHELL_RE = re.compile(
    r"^(?:岗位职责|职位描述|岗位描述|职位职责)\s*"
    r"(?:岗位要求|任职要求|任职资格|招聘要求)\s*"
    r"(?:工作地点|部门意向|申请|分享|收藏)(?:\s|$)",
    re.I,
)
_START_MARKERS = (
    "职位描述", "岗位描述", "职位职责", "岗位职责", "工作职责", "工作内容",
    "职位介绍", "Job Description", "Responsibilities",
)
_END_MARKERS = (
    "职位信息", "公司信息", "公司介绍", "企业介绍", "相关推荐", "相似职位",
    "申请职位", "投递职位", "Apply Now",
)


def is_jd_incomplete(job: dict) -> bool:
    """Return True when stored text is only a list-card summary or is blank."""
    text = " ".join(str(job.get("jd_raw") or "").split())
    if not text:
        return True
    title = " ".join(str(job.get("title") or "").split())
    remainder = text.replace(title, "", 1).strip(" -|:：") if title else text
    remainder = _PUBLISHED_ONLY_RE.sub("", remainder).strip(" -|:：")
    if _EMPTY_DETAIL_SHELL_RE.search(remainder):
        return True
    has_detail_signal = bool(_DETAIL_SIGNAL_RE.search(text))
    if has_detail_signal and len(remainder) >= 50:
        return False
    return len(text) <= 300 or len(remainder) < 80


def _clean_api_text(value: object) -> str:
    if not value:
        return ""
    soup = BeautifulSoup(str(value), "html.parser")
    return "\n".join(
        line.strip() for line in soup.get_text("\n").splitlines() if line.strip()
    )


def fetch_feishu_job_description_status(url: str) -> tuple[str, str]:
    """Return Feishu JD text and a durable verification status."""
    parsed = urlparse(url)
    match = re.search(r"/position/(\d+)/detail", parsed.path)
    if not match:
        return "", "not_applicable"
    api_url = f"{parsed.scheme}://{parsed.netloc}/api/v1/job/posts/{match.group(1)}"
    try:
        response = requests.get(
            api_url,
            params={"portal_type": 6, "with_recommend": "false"},
            headers={"User-Agent": "Mozilla/5.0", "Referer": url},
            timeout=20,
        )
        response.raise_for_status()
        detail = (((response.json().get("data") or {}).get("job_post_detail")) or {})
        description = _clean_api_text(detail.get("description"))
        requirement = _clean_api_text(detail.get("requirement"))
        parts = []
        if description:
            parts.extend(["岗位职责", description])
        if requirement:
            parts.extend(["任职要求", requirement])
        detail_text = "\n".join(parts)[:12000]
        if detail_text:
            return detail_text, "complete"
        if detail:
            return "", "official_unavailable"
        return "", "fetch_failed"
    except Exception as exc:  # noqa: BLE001
        logger.debug("飞书岗位详情 API 获取失败 %s: %s", url, exc)
        return "", "fetch_failed"


def _fetch_feishu_job_description(url: str) -> str:
    detail, _status = fetch_feishu_job_description_status(url)
    return detail


_HUAWEI_API_ROOT = (
    "https://apigw-dgg-b0.huawei.com/api/apig/channelhw/"
    "recruitmentPosition/pub/"
)
_HUAWEI_API_HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Referer": "https://career.huawei.com/",
    "User-Agent": "Mozilla/5.0",
    "X-HW-ID": "app_000000035886",
    "X-Jalor-TenantAlias": "hcm",
    "X-Language": "zh_CN",
}


def fetch_huawei_job_description_status(url: str) -> tuple[str, str]:
    """Fetch Huawei's detailed position-intention responsibilities."""
    parsed = urlparse(url)
    if parsed.netloc.casefold() != "career.huawei.com":
        return "", "not_applicable"
    match = re.search(r"[?&]advertisementId=(\d+)", url, re.I)
    if not match:
        return "", "fetch_failed"
    try:
        detail_response = requests.post(
            f"{_HUAWEI_API_ROOT}getRecruitmentPositionDetail"
            "?X-HW-ID=app_000000035886",
            json={"advertisementId": match.group(1)},
            headers=_HUAWEI_API_HEADERS,
            timeout=30,
        )
        detail_response.raise_for_status()
        position = detail_response.json().get("data") or {}
        job_id = position.get("jobId")
        if not job_id:
            return "", "official_unavailable"

        intention_response = requests.post(
            f"{_HUAWEI_API_ROOT}getPositionIntentionList"
            "?X-HW-ID=app_000000035886",
            json={"jobId": job_id},
            headers=_HUAWEI_API_HEADERS,
            timeout=30,
        )
        intention_response.raise_for_status()
        intentions = intention_response.json().get("data") or []

        parts = []
        seen = set()
        for item in intentions:
            name = _clean_api_text(item.get("positionIntention"))
            duty = _clean_api_text(item.get("jobResponsibilities"))
            requirement = _clean_api_text(item.get("jobDemand"))
            signature = (name, duty, requirement)
            if signature in seen or not (duty or requirement):
                continue
            seen.add(signature)
            if name:
                parts.extend(["岗位方向", name])
            if duty:
                parts.extend(["岗位职责", duty])
            if requirement:
                parts.extend(["任职要求", requirement])

        if not parts:
            duty = _clean_api_text(position.get("mainBusiness"))
            requirement = _clean_api_text(position.get("jobRequire"))
            if duty and "详见岗位意向" not in duty:
                parts.extend(["岗位职责", duty])
            if requirement and "详见岗位意向" not in requirement:
                parts.extend(["任职要求", requirement])
        detail = "\n".join(parts)[:12000]
        return (detail, "complete") if detail else ("", "official_unavailable")
    except Exception as exc:  # noqa: BLE001
        logger.debug("华为岗位详情 API 获取失败 %s: %s", url, exc)
        return "", "fetch_failed"


def fetch_beisen_job_description_status(url: str) -> tuple[str, str]:
    """Fetch the detail payload exposed by modern Beisen campus portals."""
    parsed = urlparse(url)
    if not parsed.netloc.casefold().endswith(".zhiye.com"):
        return "", "not_applicable"
    match = re.search(r"[?&]jobAdId=([^&#]+)", url, re.I)
    if not match:
        return "", "fetch_failed"
    category_match = re.match(r"^/(\d+)/detail", parsed.path)
    category = category_match.group(1) if category_match else "2"
    try:
        response = requests.get(
            f"{parsed.scheme}://{parsed.netloc}/api/JobAd/GetJobAdInfo",
            params={
                "jobAdId": match.group(1),
                "category": category,
                "displayFields": (
                    '["jobAdName","Duty","Require","Category","Kind",'
                    '"LocId","PostDate"]'
                ),
            },
            headers={"User-Agent": "Mozilla/5.0", "Referer": url},
            timeout=25,
        )
        response.raise_for_status()
        payload = response.json()
        data = payload.get("Data") or {}
        duty = _clean_api_text(data.get("Duty"))
        requirement = _clean_api_text(data.get("Require"))
        parts = []
        if duty:
            parts.extend(["岗位职责", duty])
        if requirement:
            parts.extend(["任职要求", requirement])
        detail = "\n".join(parts)[:12000]
        if not detail:
            return "", "official_unavailable" if data else "fetch_failed"
        status = (
            "official_sparse"
            if is_jd_incomplete({"title": data.get("JobAdName", ""), "jd_raw": detail})
            else "complete"
        )
        return detail, status
    except Exception as exc:  # noqa: BLE001
        logger.debug("北森岗位详情 API 获取失败 %s: %s", url, exc)
        return "", "fetch_failed"


@lru_cache(maxsize=1)
def _configured_careers_urls() -> dict[str, str]:
    path = Path(__file__).with_name("config.yaml")
    try:
        config = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001
        return {}
    return {
        str(item.get("name") or ""): str(item.get("careers_url") or "")
        for item in config.get("companies") or []
    }


def extract_configured_page_jd(html: str, title: str) -> str:
    """Extract one job's full JD from an official campaign/listing page."""
    soup = BeautifulSoup(html or "", "html.parser")
    normalized_title = " ".join((title or "").split())

    # Many 51job campaign pages keep the complete JD in JavaScript objects.
    pattern = re.compile(
        r"name\s*:\s*'((?:\\.|[^'])*)'\s*,\s*"
        r"value\s*:\s*'((?:\\.|[^'])*)'",
        re.S,
    )
    for script in soup.find_all("script"):
        raw = script.string or script.get_text()
        for raw_name, raw_value in pattern.findall(raw or ""):
            name = raw_name.replace("\\'", "'").strip()
            if " ".join(name.split()) != normalized_title:
                continue
            value = raw_value.replace("\\'", "'").replace("\\n", "\n")
            detail = _clean_api_text(value)
            if _DETAIL_SIGNAL_RE.search(detail):
                return detail[:12000]

    candidates = []
    for text_node in soup.find_all(string=True):
        if text_node.parent and text_node.parent.name in {"script", "style"}:
            continue
        if " ".join(str(text_node).split()) != normalized_title:
            continue
        parent = text_node.parent
        for _ in range(6):
            if parent is None:
                break
            text = "\n".join(
                line.strip()
                for line in parent.get_text("\n").splitlines()
                if line.strip()
            )
            if _DETAIL_SIGNAL_RE.search(text) and len(text) >= 100:
                candidates.append(text)
            parent = parent.parent
    if not candidates:
        return ""
    return min(candidates, key=len)[:12000]


def fetch_configured_page_job_description(job: dict) -> str:
    """Try the company's configured official page for list-only/blocked details."""
    careers_url = _configured_careers_urls().get(str(job.get("company") or ""), "")
    if not careers_url.startswith(("http://", "https://")):
        return ""
    try:
        response = requests.get(
            careers_url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=30,
            verify=False,
        )
        response.raise_for_status()
        response.encoding = response.apparent_encoding or response.encoding
        return extract_configured_page_jd(
            response.text,
            str(job.get("title") or ""),
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("配置招聘页 JD 获取失败 %s: %s", careers_url, exc)
        return ""


def fetch_tencent_job_description_status(url: str) -> tuple[str, str]:
    """Fetch regular and Qingyun-topic JD fields from Tencent's detail API."""
    parsed = urlparse(url)
    if parsed.netloc.casefold() != "join.qq.com":
        return "", "not_applicable"
    match = re.search(r"(?:[?&]postId=)(\d+)", url, re.I)
    if not match:
        return "", "fetch_failed"
    for attempt in range(3):
        try:
            response = requests.get(
                "https://join.qq.com/api/v1/jobDetails/getJobDetailsByPostId",
                params={"timestamp": int(time.time() * 1000), "postId": match.group(1)},
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Referer": "https://join.qq.com/post.html",
                },
                timeout=20,
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("status") == 404 or "下架" in str(payload.get("message") or ""):
                return "", "job_offline"
            data = payload.get("data") or {}
            duties = _clean_api_text(
                data.get("desc")
                or data.get("topicDetail")
                or data.get("introduction")
            )
            requirements = _clean_api_text(
                data.get("request")
                or data.get("topicRequirement")
            )
            parts = []
            if duties:
                parts.extend(["岗位职责", duties])
            if requirements:
                parts.extend(["任职要求", requirements])
            detail = "\n".join(parts)[:12000]
            if detail:
                return detail, "complete"
            return (
                "",
                "official_unavailable"
                if payload.get("code") == 0
                else "fetch_failed",
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "腾讯岗位详情 API 获取失败 %s（%d/3）: %s",
                url,
                attempt + 1,
                exc,
            )
            if attempt < 2:
                time.sleep(attempt + 1)
    return "", "fetch_failed"


def extract_rendered_jd(html: str, title: str = "") -> str:
    """Extract the responsibility/requirement section from a rendered detail page."""
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    lines = [" ".join(line.split()) for line in soup.get_text("\n").splitlines()]
    lines = [line for line in lines if line]

    deduped = []
    for line in lines:
        if not deduped or line != deduped[-1]:
            deduped.append(line)
    lines = deduped

    start = next(
        (index for index, line in enumerate(lines)
         if any(line.casefold() == marker.casefold() for marker in _START_MARKERS)),
        None,
    )
    if start is None:
        start = next(
            (index for index, line in enumerate(lines)
             if any(marker.casefold() in line.casefold() for marker in _START_MARKERS)),
            None,
        )
    if start is None:
        return ""

    end = len(lines)
    for index in range(start + 1, len(lines)):
        if any(lines[index].casefold() == marker.casefold() for marker in _END_MARKERS):
            end = index
            break

    detail_lines = lines[start:end]
    # Some SPA pages keep both desktop and mobile detail components in the DOM.
    # The heading is shared while the complete content block appears twice.
    if len(detail_lines) >= 5:
        heading, content = detail_lines[0], detail_lines[1:]
        if len(content) % 2 == 0:
            midpoint = len(content) // 2
            if content[:midpoint] == content[midpoint:]:
                detail_lines = [heading, *content[:midpoint]]

    detail = "\n".join(detail_lines).strip()
    if title and detail == title:
        return ""
    return detail[:12000]


def fetch_full_job_description(job: dict) -> str:
    """Render one exact job URL and return a richer JD, or an empty string."""
    # New database rows always carry an evidence-based cohort status. Keep
    # backwards compatibility for standalone parser tests and legacy callers
    # that have no cohort fields yet.
    if "cohort_status" in job:
        import job_cohorts

        if not job_cohorts.is_confirmed_current(job):
            return ""
    if not is_jd_incomplete(job):
        return str(job.get("jd_raw") or "")
    if urlparse(str(job.get("jd_url") or "")).netloc.casefold().endswith("hotjob.cn"):
        detail, detail_url = fetch_hotjob_position_detail(str(job.get("jd_url") or ""))
        if detail_url:
            job["jd_url"] = detail_url
            job["link_kind"] = "detail"
        if detail:
            return detail
    url = str(job.get("jd_url") or "")
    host = urlparse(url).netloc.casefold()
    if host == "career.huawei.com":
        detail, _status = fetch_huawei_job_description_status(url)
        return detail
    if host.endswith(".zhiye.com"):
        detail, _status = fetch_beisen_job_description_status(url)
        if detail:
            return detail
    if host in {"jobs.51job.com", "xyz.51job.com", "xym.51job.com"}:
        detail = fetch_configured_page_job_description(job)
        if detail:
            return detail
    if job.get("link_kind") == "list":
        return fetch_configured_page_job_description(job)
    if not url.startswith(("http://", "https://")):
        return ""
    feishu_detail = _fetch_feishu_job_description(url)
    if feishu_detail:
        return feishu_detail
    if urlparse(url).netloc.casefold() == "join.qq.com":
        detail, _status = fetch_tencent_job_description_status(url)
        return detail

    extra_wait_ms = 5000 if "mokahr.com" in host else 1500
    html = render_page(url, timeout_ms=45000, extra_wait_ms=extra_wait_ms)
    detail = extract_rendered_jd(html or "", str(job.get("title") or ""))
    hydrated = {**job, "jd_raw": detail}
    if (
        not _DETAIL_SIGNAL_RE.search(detail)
        or is_jd_incomplete(hydrated)
    ):
        logger.warning("岗位详情自动补全失败或内容仍过短: %s", url)
        return ""
    return detail
