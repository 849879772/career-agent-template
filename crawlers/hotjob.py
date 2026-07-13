"""hotjob.cn（北森 wecruit 系）通用校招爬虫基类。

师兄清单里 ~20 家用 hotjob，URL 形如 https://<sub>.hotjob.cn/SU<id>/pb/account.html。
hotjob 站点把社招/校招分页：
    /pb/social.html  社会招聘  ←  不要（社招陷阱：CSV 里的 /pb/account 常默认跳这里）
    /pb/school.html  校园招聘  ←  要
故本基类**强制走 /pb/school.html**，从 careers_url 解析 host + SU<id> 拼出校招列表页。
校招列表项 DOM：
    <div class="list-row-item">
      <div class="list-cell pos-name"><span class="list-cell-span">岗位标题</span></div>
      <div class="list-cell pos-cate"><span>职位类别</span></div>
      ...（工作地点 / 招聘人数 / 更新日期）
岗位非稳定 <a>，靠 JS 跳转，用标题哈希作唯一 jd_url（同北森做法）。

注：部分公司 hotjob 只有社招、校招在自建站（如 TCL → campus.tcl.com），
其 /pb/school.html 抓不到岗位会返回空（优雅降级，归 Phase 3 手工）。
"""
import logging
import re
import time
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from .base import BaseCrawler
from .render import render_page

logger = logging.getLogger(__name__)


class HotjobRecruitCrawler(BaseCrawler):
    EXTRA_WAIT_MS = 6000
    SCROLL_TIMES = 6
    JD_RAW_LIMIT = 300
    _SKIP_TITLES = {"职位名称", "岗位名称"}  # 表头行

    def _base(self) -> str:
        p = urlparse(self.careers_url)
        m = re.search(r"/(SU[0-9a-fA-F]+)", p.path)
        return f"https://{p.netloc}/{m.group(1) if m else ''}"

    def _suite_key(self) -> str:
        m = re.search(r"/(SU[0-9a-fA-F]+)", urlparse(self.careers_url).path)
        return m.group(1) if m else ""

    def _list_url(self) -> str:  # 桌面校招页
        return f"{self._base()}/pb/school.html"

    def _mc_url(self) -> str:  # 移动校招页（部分租户只有 /mc/，桌面 /pb/ 为 404）
        return f"{self._base()}/mc/position/campus"

    def _foxconn_url(self) -> str:
        p = urlparse(self.careers_url)
        if "foxconn.hotjob.cn" not in p.netloc:
            return ""
        return "https://foxconn.hotjob.cn/wt/Foxconn/web/index/CompFoxconnPagerecruit_School"

    @staticmethod
    def _cell_text(row, *suffixes: str) -> str:
        """取 row 里 class 形如 list-cell pos-<suffix> 的单元格内层 span 文本（避开"热招"等 badge）。"""
        for suf in suffixes:
            cell = row.find(
                lambda t: t.has_attr("class")
                and "list-cell" in t["class"]
                and any(f"pos-{suf}" in c for c in t["class"])
            )
            if cell:
                span = cell.find("span", class_="list-cell-span")
                return (span or cell).get_text(" ", strip=True)
        return ""

    def _parse_pb(self, html: str, list_url: str) -> list[dict]:
        """桌面 /pb/school.html：表格 list-row-item，pos-name/pos-locate 单元格。"""
        soup = BeautifulSoup(html, "html.parser")
        rows = soup.find_all(
            lambda t: t.has_attr("class") and any("list-row-item" in c for c in t["class"])
        )
        jobs, seen = [], set()
        for row in rows:
            title = self._cell_text(row, "name")
            if not title or len(title) < 2 or title in self._SKIP_TITLES:
                continue
            key = str(abs(hash(title)) % (10 ** 8))
            if key in seen:
                continue
            seen.add(key)
            city = self._cell_text(row, "locate", "area", "location", "city", "addr")
            jobs.append(self._make_job(
                title=title, city=city[:40], jd_url=f"{list_url}#{key}", link_kind="list"
            ))
        return jobs

    def _parse_pb_cards(self, html: str, list_url: str) -> list[dict]:
        """新版 /pb/school.html：卡片 list-card-item1，标题 pos-title-item。"""
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.find_all(
            lambda t: t.has_attr("class") and any("list-card-item" in c for c in t["class"])
        )
        jobs, seen = [], set()
        for card in cards:
            title_el = card.find(
                lambda t: t.has_attr("class") and any("pos-title-item" in c for c in t["class"])
            )
            if not title_el:
                continue
            title = title_el.get_text(" ", strip=True)
            if not title or len(title) < 2 or title in self._SKIP_TITLES:
                continue
            key = str(abs(hash(title)) % (10 ** 8))
            if key in seen:
                continue
            seen.add(key)
            text = card.get_text(" ", strip=True)
            city = ""
            for part in [p.strip() for p in re.split(r"[|｜]", text) if p.strip()]:
                if re.search(r"(市|省|区|县|州|盟|香港|澳门|台湾)", part) and "更新日期" not in part:
                    city = part
                    break
            jobs.append(self._make_job(title=title, city=city[:40], jd_url=f"{list_url}#{key}",
                                       jd_raw=text[: self.JD_RAW_LIMIT], link_kind="list"))
        return jobs

    def _fetch_new_pb_api(self) -> list[dict]:
        """新版 hotjob PB 站点的公开列表 API，可翻页抓全量岗位。"""
        suite_key = self._suite_key()
        if not suite_key:
            return []
        base = self._base()
        api = f"{base.replace('/' + suite_key, '')}/wecruit/positionInfo/listPosition/{suite_key}"
        list_url = self._list_url()
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": list_url,
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        }
        jobs, seen = [], set()
        page = 1
        total_page = 1
        while page <= total_page and page <= 30:
            params = {"iSaJAx": "isAjax", "request_locale": "zh_CN", "t": str(int(time.time() * 1000))}
            form = {"isFrompb": "true", "recruitType": "1", "pageSize": "50", "currentPage": str(page)}
            try:
                resp = requests.post(api, params=params, data=form, headers=headers, timeout=20)
                resp.raise_for_status()
                payload = resp.json()
            except Exception as e:  # noqa: BLE001
                logger.debug("[%s] hotjob API 失败 page=%s: %s", self.company_name, page, e)
                return jobs
            page_form = ((payload.get("data") or {}).get("pageForm") or {})
            total_page = int(page_form.get("totalPage") or total_page or 1)
            for item in page_form.get("pageData") or []:
                title = (item.get("postName") or "").strip()
                post_id = item.get("postId") or item.get("externalKey") or title
                if not title or post_id in seen:
                    continue
                seen.add(post_id)
                city = item.get("workPlaceStr") or ""
                jd_url = f"{list_url}#{post_id}"
                jd_raw = " | ".join(
                    str(v) for v in [
                        item.get("postTypeName"),
                        item.get("company"),
                        item.get("department"),
                        item.get("projectName"),
                        item.get("educationStr"),
                    ] if v
                )
                jobs.append(self._make_job(
                    title=title,
                    city=city[:40],
                    jd_url=jd_url,
                    jd_raw=jd_raw[: self.JD_RAW_LIMIT],
                    published_at=(item.get("publishDate") or "")[:10],
                    link_kind="list",
                ))
            if not page_form.get("pageData"):
                break
            page += 1
        return jobs

    def _parse_mc(self, html: str, list_url: str) -> list[dict]:
        """移动 /mc/position/campus：div.listItem，标题 span.listItemRtTitCon。"""
        soup = BeautifulSoup(html, "html.parser")
        items = soup.find_all(
            lambda t: t.has_attr("class") and any("listItem" in c for c in t["class"])
        )
        jobs, seen = [], set()
        for it in items:
            tit_el = it.find("span", class_=lambda c: c and "listItemRtTitCon" in c)
            if not tit_el:
                continue
            title = tit_el.get_text(" ", strip=True)
            if not title or len(title) < 2:
                continue
            key = str(abs(hash(title)) % (10 ** 8))
            if key in seen:
                continue
            seen.add(key)
            m = re.search(r"([一-龥]{2,}[市省](?:、[一-龥]{2,}[市省])*)", it.get_text(" ", strip=True))
            jobs.append(self._make_job(title=title, city=(m.group(1) if m else "")[:40],
                                       jd_url=f"{list_url}#{key}", link_kind="list"))
        return jobs

    def _parse_foxconn(self, html: str, list_url: str) -> list[dict]:
        """富士康 Dayee 模板；当前无岗位时页面/API 显示“暂无数据内容”。"""
        soup = BeautifulSoup(html, "html.parser")
        if "暂无数据" in soup.get_text(" ", strip=True):
            return []
        jobs, seen = [], set()
        for row in soup.select("tbody tr"):
            cells = [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]
            cells = [c for c in cells if c]
            if len(cells) < 2:
                continue
            title = cells[0]
            if title in self._SKIP_TITLES or len(title) < 2:
                continue
            key = str(abs(hash("|".join(cells))) % (10 ** 8))
            if key in seen:
                continue
            seen.add(key)
            city = cells[3] if len(cells) > 3 else ""
            jobs.append(self._make_job(title=title, city=city[:40], jd_url=f"{list_url}#{key}",
                                       jd_raw=" | ".join(cells)[: self.JD_RAW_LIMIT], link_kind="list"))
        return jobs

    def fetch(self) -> list[dict]:
        foxconn_url = self._foxconn_url()
        if foxconn_url:
            html = render_page(foxconn_url, wait_for=None, timeout_ms=45000,
                               extra_wait_ms=self.EXTRA_WAIT_MS, scroll_times=self.SCROLL_TIMES)
            if html:
                jobs = self._parse_foxconn(html, foxconn_url)
                logger.info("[%s] foxconn hotjob 抓到 %d 个岗位", self.company_name, len(jobs))
                return jobs

        api_jobs = self._fetch_new_pb_api()
        if api_jobs:
            logger.info("[%s] hotjob API 抓到 %d 个岗位", self.company_name, len(api_jobs))
            return api_jobs

        # 先桌面 /pb/school.html；为空再退移动 /mc/position/campus（部分租户桌面 404）
        for url, parse in ((self._list_url(), self._parse_pb), (self._mc_url(), self._parse_mc)):
            html = render_page(url, wait_for=None, timeout_ms=45000,
                               extra_wait_ms=self.EXTRA_WAIT_MS, scroll_times=self.SCROLL_TIMES)
            if not html:
                continue
            jobs = parse(html, url)
            if not jobs and "/pb/school.html" in url:
                jobs = self._parse_pb_cards(html, url)
            if jobs:
                logger.info("[%s] hotjob 抓到 %d 个岗位 (%s)", self.company_name, len(jobs),
                            "mc" if "/mc/" in url else "pb")
                return jobs
        logger.info("[%s] hotjob 抓到 0 个岗位", self.company_name)
        return []
