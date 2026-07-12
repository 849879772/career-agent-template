"""通用渲染爬虫 —— 服务「自建 SPA 校招站」(无公开 API 或 API 带反爬)。

很多公司校招站是自建 SPA，职位列表 API 常带客户端反爬 token(如 bilibili 的
ajSessionId)，裸 requests 抓不到。用 Playwright 渲染真实页面时页面自身 JS 会带上
token、DOM 正常填充，故走「渲染 + 自动选主选择器 + 翻页」绕过。

**自动选主选择器**(避免"抓所有关键词元素"的脏数据)：渲染后统计每个 tag.class
里"像职位名"的直接文本数，职位列表组件会重复出现 N 次(N 远大于筛选/导航噪声)，
取得分最高、且文本足够干净的那个 class 作为唯一选择器，只解析它。

config 用法：crawler: render + careers_url(职位列表页 URL)。无需子类。
若某站结构特殊选不出干净选择器(主选择器命中数 < 阈值)，优雅返空、归人工。
"""
import logging
import re
from collections import defaultdict
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .base import BaseCrawler

logger = logging.getLogger(__name__)

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
_CITY_RE = re.compile(r"[\u4e00-\u9fa5]{2,}(?:市|省|区|县)?")
_JOB_KW = re.compile(
    r"工程师|研发|开发|算法|架构|设计师|实习生|管培|培训生|专员|主管|"
    r"产品经理|运营|测试|分析师|顾问|储备|工艺|科学家|研究员|策划|助理|应届|博士后|"
    r"trainee|engineer|developer|intern|graduate|analyst",
    re.I,
)
# 明显非职位的噪声(筛选/导航/页脚/说明文案)
_NOISE = re.compile(
    r"筛选|清除|职位类别|工作地点|大职能|仅查看|热门|须知|查看|更多|登录|注册|"
    r"计划是|面向|推出|全球|高校|在校生|清空|展开|收起|首页|关于|联系|"
    r"招聘流程|投递方式|个人中心|加入我们|了解更多|立即申请|点击|"
    r"校招流程|校招岗位|校招FAQ|FAQ|招聘公告|招聘简章|招聘动态|校招行程|快捷通道|"
    r"应届生招聘|实习生招聘|博士生招聘|进入校招|实习机会|"
    r"产品类|技术类|职能类|运营市场类|研发美术类|运营美术类|岗位类别|"
    r"子类别|业务开发与支持|系统开发管理|系统运维管理|网络规划与投资计划|项目计划管理|网络运营管理|"
    r"开发板|评估板|参考设计|所有开发板|开发工具|测试服务|"
    r"研发中心|开发团队|业务架构|工程中心|工厂中心|需求部门|"
    r"职位描述|岗位职责|任职要求|工作内容|招聘对象|招收对象|毕业时间|"
    r"年及以上|三年及以上|五年及以上|经验者优先|全流程测试能力|大学|"
    r"产品中心|解决方案|了解更多|产品研发|开发成本|协同研发|硬件基础|开箱即用|"
    r"高性能CAE|几何内核|约束求解|数字化仿真|数字化制造|数字化设计|产品开发|"
    r"行业应用|应用验证|信创生态|自主可控|功能成熟|高效替代|合作咨询|人事招聘|"
    r"测试机|通用数字测试机|复杂SoC测试机|DDIC测试机|CIS测试机|半导体测试机|"
    r"摄像头模组测试|测试系统软件开发服务",
    re.I,
)
_BAD_TITLE_RE = re.compile(r"^\d+[、.，,]|[。；;]$|^20(1\d|2[0-4])-\d{2}-\d{2}|类\s*\|\s*")
_CONTEXT_NOISE = re.compile(
    r"社会招聘|工作经验|三年及以上|五年及以上|博士后工作站|招聘公告|双选会|宣讲会|基层就业|学院就业|薪资范围|发布时间|"
    r"产品中心|解决方案|了解更多|产品研发|几何内核|约束求解|数字化仿真|数字化制造|信创生态|合作咨询|"
    r"测试机|通用数字测试机|复杂SoC测试机|DDIC测试机|CIS测试机|半导体测试机|摄像头模组测试|"
    r"序号|单位名称|单位所在地|招聘人数|应聘方式|海报|双选会|招聘会",
    re.I,
)


class GenericRenderCrawler(BaseCrawler):
    MAX_PAGES = 25
    JD_RAW_LIMIT = 200
    MIN_LEN, MAX_LEN = 4, 30
    MIN_HITS = 3  # 主选择器至少命中这么多职位才认为有效

    def _list_url(self) -> str:
        return self.careers_url

    def _clean_title(self, text: str) -> str:
        text = re.sub(r"\s+", " ", text or "").strip()
        text = re.sub(r"\s*(立即投递|申请职位|投递简历)\s*$", "", text).strip()
        if "个岗位" in text or text.endswith("类"):
            return ""
        if not (self.MIN_LEN <= len(text) <= self.MAX_LEN):
            return ""
        if _BAD_TITLE_RE.search(text) or _NOISE.search(text) or not _JOB_KW.search(text):
            return ""
        return text

    def fetch(self) -> list[dict]:
        try:
            from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
        except ImportError:
            logger.error("[%s] 未安装 playwright", self.company_name)
            return []

        jobs, seen = [], set()
        selector_sig = None
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=["--disable-blink-features=AutomationControlled", "--no-sandbox",
                          "--disable-dev-shm-usage"],
                )
                ctx = browser.new_context(user_agent=_UA, viewport={"width": 1366, "height": 768},
                                          locale="zh-CN", ignore_https_errors=True)
                page = ctx.new_page()
                try:
                    page.goto(self._list_url(), wait_until="networkidle", timeout=45000)
                except PWTimeout:
                    logger.warning("[%s] goto 超时，仍尝试解析", self.company_name)
                page.wait_for_timeout(2500)

                self._click_campus_entry(page)
                # 第一页：先定主选择器
                selector_sig = self._pick_selector(page.content())
                # 兜底：很多 SPA 先显示项目/类别卡，需点「校招/职位/全部职位」才露列表
                if not selector_sig:
                    for kw in ("校园招聘", "校招", "应届", "查看职位", "全部职位",
                               "职位列表", "社会招聘", "职位查询", "立即查看"):
                        try:
                            loc = page.get_by_text(re.compile(kw)).first
                            if loc.count() == 0:
                                continue
                            loc.click(timeout=3000)
                            page.wait_for_timeout(2000)
                            selector_sig = self._pick_selector(page.content())
                            if selector_sig:
                                break
                        except Exception:
                            continue
                if not selector_sig:
                    line_jobs = self._parse_line_jobs(page.content())
                    if line_jobs:
                        ctx.close(); browser.close()
                        return line_jobs
                    logger.info("[%s] 未选出干净职位选择器（淡季空/结构特殊），返空", self.company_name)
                    ctx.close(); browser.close()
                    return []

                for _ in range(self.MAX_PAGES):
                    new = self._parse(page.content(), selector_sig, jobs, seen)
                    nxt = page.locator(
                        ".btn-next, .el-pagination .btn-next, .ant-pagination-next, "
                        "[class*='pagination'] [class*='next'], li[title='下一页'], a[aria-label='Next']"
                    ).first
                    try:
                        if nxt.count() == 0:
                            break
                        cls = (nxt.get_attribute("class") or "") + str(nxt.get_attribute("aria-disabled"))
                        if "disabled" in cls.lower():
                            break
                        nxt.click(timeout=4000)
                        page.wait_for_timeout(1200)
                    except Exception:
                        break

                if not jobs:
                    jobs.extend(self._parse_line_jobs(page.content()))

                ctx.close()
                browser.close()
        except Exception as e:  # noqa: BLE001
            logger.error("[%s] 渲染爬取异常: %s", self.company_name, e)

        logger.info("[%s] 通用渲染 抓到 %d 个岗位（选择器=%s）",
                    self.company_name, len(jobs), selector_sig)
        return jobs

    def _parse_line_jobs(self, html: str) -> list[dict]:
        """Fallback for simple static pages that list jobs as lines like `职位：软件工程师`."""
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text("\n", strip=True)
        jobs, seen = [], set()
        for match in re.finditer(r"(?:^|\n)\s*职位\s*[：:]\s*([^\n\r]{2,40})", text):
            title = self._clean_title(match.group(1))
            if not title or title in seen:
                continue
            seen.add(title)
            jobs.append(self._make_job(
                title=title, city="", jd_url=self._list_url(), link_kind="list",
            ))
        return jobs

    def _sig(self, el) -> str:
        cls = ".".join(el.get("class") or [])
        return f"{el.name}.{cls}" if cls else el.name

    def _direct_text(self, el) -> str:
        direct = "".join(t for t in el.find_all(string=True, recursive=False)).strip()
        return direct if direct else el.get_text(" ", strip=True)

    def _job_link(self, el) -> tuple[str, str]:
        """Return a real detail link near a title, otherwise the listing page."""
        nodes = [el]
        parent = el.parent
        for _ in range(3):
            if not parent:
                break
            nodes.append(parent)
            parent = parent.parent
        for node in nodes:
            anchors = [node] if getattr(node, "name", "") == "a" else node.find_all("a", href=True)
            for anchor in anchors:
                href = (anchor.get("href") or "").strip()
                if not href or href == "#" or href.lower().startswith("javascript:"):
                    continue
                resolved = urljoin(self._list_url(), href)
                if resolved == self._list_url() or re.search(r"#\d+$", resolved):
                    continue
                return resolved, "detail"
        return self._list_url(), "list"

    def _click_campus_entry(self, page) -> None:
        """Some sites default to social jobs even from a campus-looking URL."""
        for kw in ("校园招聘", "校招岗位", "校招职位", "应届生招聘", "校园职位"):
            try:
                loc = page.get_by_text(re.compile(kw)).first
                if loc.count() == 0:
                    continue
                loc.click(timeout=2500)
                page.wait_for_timeout(1800)
                return
            except Exception:
                continue

    def _pick_selector(self, html: str) -> str:
        """统计每个 tag.class 下的干净职位标题数，取最高者(≥MIN_HITS)。"""
        soup = BeautifulSoup(html, "html.parser")
        score = defaultdict(int)
        for el in soup.find_all(["a", "h2", "h3", "h4", "h5", "span", "div", "p", "li"]):
            if self._clean_title(self._direct_text(el)):
                score[self._sig(el)] += 1
        if not score:
            return ""
        best, n = max(score.items(), key=lambda kv: kv[1])
        return best if n >= self.MIN_HITS else ""

    def _parse(self, html: str, sig: str, jobs: list, seen: set) -> int:
        soup = BeautifulSoup(html, "html.parser")
        new = 0
        for el in soup.find_all(["a", "h2", "h3", "h4", "h5", "span", "div", "p", "li"]):
            if self._sig(el) != sig:
                continue
            title = self._clean_title(self._direct_text(el))
            if not title:
                continue
            key = str(abs(hash(title)) % (10 ** 8))
            if key in seen:
                continue
            seen.add(key)
            anc = el
            for _ in range(3):
                anc = anc.parent if anc and anc.parent else anc
            ctext = anc.get_text(" ", strip=True) if anc else ""
            if _CONTEXT_NOISE.search(ctext):
                continue
            m = _CITY_RE.findall(ctext)
            city = "、".join(dict.fromkeys(m))[:40]
            jd_url, link_kind = self._job_link(el)
            jobs.append(self._make_job(
                title=title, city=city, jd_url=jd_url, link_kind=link_kind,
            ))
            new += 1
        return new
