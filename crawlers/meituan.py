"""美团校招爬虫 —— 自建站 zhaopin.meituan.com，走公开 JSON API。

campus.meituan.com 跳转到 zhaopin.meituan.com/web/campus（校园招聘官网）。
其职位列表 API 公开免鉴权：
    POST https://zhaopin.meituan.com/api/official/job/getJobList
    body: {"keyword":"", "recruitmentType":"CAMPUS_HIRING",
           "page":{"pageNo":N, "pageSize":100}}   # 翻页必须是嵌套 page 对象
    resp: data.list[]（name=职位名, cityList[].name=地点, jobUnionId=唯一标识,
          jobDuty/jobRequirement=JD）+ data.page.totalPage/totalCount。
校招约 2900 岗。实习岗由 reporter 按标题统一隐藏。
"""
import logging
import time

import requests

from .base import BaseCrawler

logger = logging.getLogger(__name__)


class MeituanCrawler(BaseCrawler):
    API = "https://zhaopin.meituan.com/api/official/job/getJobList"
    PAGE_SIZE = 100
    MAX_PAGES = 40  # 校招约 2900 岗 / 100 = 30 页，留余量
    JD_RAW_LIMIT = 300
    RECRUIT_TYPE = "CAMPUS_HIRING"

    def fetch(self) -> list[dict]:
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Content-Type": "application/json",
            "Referer": "https://zhaopin.meituan.com/web/campus",
            "Origin": "https://zhaopin.meituan.com",
        }
        jobs, seen = [], set()
        for page in range(1, self.MAX_PAGES + 1):
            body = {"keyword": "", "recruitmentType": self.RECRUIT_TYPE,
                    "page": {"pageNo": page, "pageSize": self.PAGE_SIZE}}
            data = None
            for attempt in range(3):  # 大站偶发限流/SSL 中断，轻量重试
                try:
                    resp = requests.post(self.API, json=body, headers=headers, timeout=30)
                    data = resp.json().get("data") or {}
                    break
                except Exception as e:  # noqa: BLE001
                    logger.warning("[%s] 美团 API 第%d页第%d次失败: %s",
                                   self.company_name, page, attempt + 1, e)
                    time.sleep(1.5 * (attempt + 1))
            if data is None:
                break  # 三次仍失败，止损返回已抓到的
            plist = data.get("list") or []
            if not plist:
                break
            for x in plist:
                jid = str(x.get("jobUnionId") or "")
                if not jid or jid in seen:
                    continue
                seen.add(jid)
                title = (x.get("name") or "").strip()
                if not title or len(title) < 2:
                    continue
                city = "、".join(c.get("name", "") for c in (x.get("cityList") or []) if c.get("name"))[:40]
                jd_raw = (x.get("jobDuty") or x.get("jobRequirement") or x.get("desc") or "")[:self.JD_RAW_LIMIT]
                jd_url = f"https://zhaopin.meituan.com/web/campus/position-detail?jobId={jid}"
                jobs.append(self._make_job(title=title, city=city, jd_url=jd_url, jd_raw=jd_raw))
            page_info = data.get("page") or {}
            if page >= (page_info.get("totalPage") or 0):
                break
            time.sleep(0.3)  # 页间小延时，降低限流概率

        logger.info("[%s] 美团 抓到 %d 个岗位", self.company_name, len(jobs))
        return jobs
