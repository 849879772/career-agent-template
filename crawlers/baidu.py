"""百度校招爬虫 —— 自建站 talent.baidu.com，走公开 JSON API。

talent.baidu.com/jobs/list 校园招聘站，职位列表 API 公开免鉴权：
    POST https://talent.baidu.com/httservice/getPostListNew   （表单编码，非 JSON）
    body: recruitType=校招 & pageSize=100 & curPage=N & keyWord=
          （recruitType 的合法值就是中文"校招"，"校园招聘"/"college" 等都会被拒）
    resp: data.list[]（name=职位名, workPlace=地点, postId=唯一标识,
          workContent=JD）+ data.pages/total。
"""
import logging
import time

import requests

from .base import BaseCrawler

logger = logging.getLogger(__name__)


class BaiduCrawler(BaseCrawler):
    API = "https://talent.baidu.com/httservice/getPostListNew"
    DETAIL = "https://talent.baidu.com/jobs/detail/"
    PAGE_SIZE = 20  # 服务端上限 20（30+ 会报 Illegal argument）
    MAX_PAGES = 30
    JD_RAW_LIMIT = 300
    RECRUIT_TYPE = "校招"  # 合法值是中文"校招"

    def fetch(self) -> list[dict]:
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": "https://talent.baidu.com/jobs/list",
            "Origin": "https://talent.baidu.com",
        }
        jobs, seen = [], set()
        for page in range(1, self.MAX_PAGES + 1):
            data = {"recruitType": self.RECRUIT_TYPE, "pageSize": self.PAGE_SIZE,
                    "curPage": page, "keyWord": ""}
            result = None
            for attempt in range(3):
                try:
                    resp = requests.post(self.API, data=data, headers=headers, timeout=30)
                    body = resp.json()
                    if body.get("status") != "ok":
                        logger.warning("[%s] 百度 API 返回非 ok: %s", self.company_name, body.get("message"))
                        return jobs
                    result = body.get("data") or {}
                    break
                except Exception as e:  # noqa: BLE001
                    logger.warning("[%s] 百度 API 第%d页第%d次失败: %s",
                                   self.company_name, page, attempt + 1, e)
                    time.sleep(1.5 * (attempt + 1))
            if result is None:
                break
            plist = result.get("list") or []
            if not plist:
                break
            for x in plist:
                pid = str(x.get("postId") or x.get("jobId") or "")
                if not pid or pid in seen:
                    continue
                seen.add(pid)
                title = (x.get("name") or "").strip()
                if not title or len(title) < 2:
                    continue
                city = (x.get("workPlace") or "").replace(",", "、")[:40]
                jd_raw = (x.get("workContent") or x.get("serviceCondition") or "")[:self.JD_RAW_LIMIT]
                jobs.append(self._make_job(title=title, city=city,
                                           jd_url=f"{self.DETAIL}{pid}", jd_raw=jd_raw))
            if page >= (result.get("pages") or 0):
                break
            time.sleep(0.3)

        logger.info("[%s] 百度 抓到 %d 个岗位", self.company_name, len(jobs))
        return jobs
