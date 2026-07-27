"""Pinduoduo campus crawler backed by the site's public JSON APIs."""

from __future__ import annotations

import logging
import time
from datetime import datetime

import requests

from .base import BaseCrawler

logger = logging.getLogger(__name__)

_API_ROOT = "https://careers.pddglobalhr.com/api/careers/api/recruit/position"
_LIST_API = f"{_API_ROOT}/list"
_DETAIL_API = f"{_API_ROOT}/detail"
_DETAIL_PAGE = "https://careers.pddglobalhr.com/campus/grad/detail?positionId={position_id}"
_HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json;charset=UTF-8",
    "Referer": "https://careers.pddglobalhr.com/campus/grad",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
    ),
}


class PDDCrawler(BaseCrawler):
    PAGE_SIZE = 100
    MAX_PAGES = 20

    def _post_result(self, session: requests.Session, url: str, body: dict):
        for attempt in range(1, self.REQUEST_ATTEMPTS + 1):
            try:
                response = session.post(url, json=body, timeout=25)
                response.raise_for_status()
                payload = response.json()
                if payload.get("success"):
                    return payload.get("result")
                raise RuntimeError(payload.get("errorMsg") or "official API returned success=false")
            except (requests.RequestException, ValueError, RuntimeError) as exc:
                if attempt == self.REQUEST_ATTEMPTS:
                    logger.warning("[%s] 拼多多接口请求失败 %s: %s", self.company_name, url, exc)
                    return None
                time.sleep(0.5 * attempt)
        return None

    @staticmethod
    def _published_at(value) -> str:
        try:
            timestamp = int(value)
            if timestamp > 10_000_000_000:
                timestamp //= 1000
            return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")
        except (TypeError, ValueError, OSError):
            return ""

    @staticmethod
    def _jd_text(detail: dict, fallback: dict) -> str:
        duty = str(detail.get("jobDuty") or fallback.get("jobDuty") or "").strip()
        requirement = str(detail.get("serveRequirement") or "").strip()
        bonus = str(detail.get("bonus") or "").strip()
        parts = []
        if duty:
            parts.extend(["岗位职责", duty])
        if requirement:
            parts.extend(["任职要求", requirement])
        if bonus:
            parts.extend(["加分项", bonus])
        return "\n".join(parts)[:12000]

    def fetch(self) -> list[dict]:
        session = requests.Session()
        session.headers.update(_HEADERS)
        rows = []
        total = None

        for page in range(1, self.MAX_PAGES + 1):
            result = self._post_result(
                session,
                _LIST_API,
                {"page": page, "pageSize": self.PAGE_SIZE, "t": None},
            )
            if not isinstance(result, dict):
                break
            page_rows = result.get("list") or []
            rows.extend(row for row in page_rows if isinstance(row, dict))
            try:
                total = int(result.get("total") or 0)
            except (TypeError, ValueError):
                total = None
            if not page_rows or (total is not None and len(rows) >= total):
                break

        jobs = []
        seen_ids = set()
        for row in rows:
            position_id = str(row.get("id") or "").strip()
            title = str(row.get("name") or "").strip()
            if not position_id or not title or position_id in seen_ids:
                continue
            seen_ids.add(position_id)

            detail = self._post_result(
                session,
                _DETAIL_API,
                {"id": position_id, "t": None},
            )
            detail = detail if isinstance(detail, dict) else {}
            year = str(detail.get("graduationYear") or row.get("graduationYear") or "").strip()
            recruit_type = str(
                detail.get("recruitTypeName") or row.get("recruitTypeName") or ""
            ).strip()
            job_type = " ".join(
                part for part in ("校招", "正式", f"{year}届" if year else "", recruit_type)
                if part
            )
            detail_url = str(detail.get("shareUrl") or "").strip() or _DETAIL_PAGE.format(
                position_id=position_id
            )
            jobs.append(self._make_job(
                title=title,
                city=str(
                    detail.get("workLocationName") or row.get("workLocationName")
                    or row.get("workLocation") or ""
                ).strip(),
                job_type=job_type,
                jd_url=detail_url,
                jd_raw=self._jd_text(detail, row),
                published_at=self._published_at(
                    detail.get("releaseTime") or row.get("releaseTime")
                ),
                link_kind="detail",
            ))

        logger.info("[%s] 拼多多官方 API 抓到 %d 个岗位", self.company_name, len(jobs))
        return jobs
