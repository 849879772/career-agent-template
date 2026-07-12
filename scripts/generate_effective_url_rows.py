import json
import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import yaml


PLACEHOLDER_CRAWLERS = {
    "zhiyuan", "galbot", "robotera", "fftai", "ubtech", "limx",
    "dahua", "megvii", "sensetime", "orbbec",
    "ponyai", "weride", "momenta", "horizon", "nio",
    "jaka", "dobot", "xpeng",
}


FIXED_CRAWLERS = {
    "dji": (
        "https://apply.careers.dji.com/campus-recruitment/dji/143359?locale=zh-CN#/jobs",
        "页面",
        "专用 crawler 固定打开 DJI Moka 校招 jobs 列表，并逐页点击分页",
    ),
    "xiaomi": ("https://xiaomi.jobs.f.mioffice.cn/campus", "页面", "专用飞书 crawler 固定列表页"),
    "bytedance": ("https://jobs.bytedance.com/campus/position", "页面", "专用飞书 crawler 固定列表页"),
    "huawei": (
        "https://career.huawei.com/cn/campus-recruitment-job-list?recruitmentType=FRESH_GRADUATE ; "
        "intercept API: /recruitmentPosition/pub/getJobPage",
        "页面+API",
        "Playwright 打开固定校招页并拦截岗位 API 响应",
    ),
    "tencent": ("https://join.qq.com/api/v1/position/searchPosition", "API", "固定 API，body recruitType=40003"),
    "meituan": ("https://zhaopin.meituan.com/api/official/job/getJobList", "API", "固定 API，body recruitmentType=CAMPUS_HIRING"),
    "baidu": ("https://talent.baidu.com/httservice/getPostListNew", "API", "固定 API，form recruitType=校招"),
    "kuaishou": ("https://campus.kuaishou.cn/recruit/campus/e/api/v1/open/positions/simple", "API", "固定 API，分页抓取 campus open positions"),
    "jd": (
        "https://campus.jd.com/api/wx/position/getProjectList ; "
        "https://campus.jd.com/api/wx/position/page?type=present|talent|internship",
        "API",
        "固定 API，先取项目再按 present/talent/internship 抓职位",
    ),
    "mihoyo": ("https://ats.openout.mihoyo.com/ats-portal/v1/job/list", "API", "固定 API，hireType=1/channelDetailIds=[1]"),
    "gbits": ("https://joinserver.g-bits.com:8666/humanResource/recruitmentExtranet/ExtrannetCampusPost/queryRecuitPost", "API", "固定 API，recruitsType=CAMPUS_RECRUITING"),
    "oppo": ("https://careers.oppo.com/openapi/position/pageNew", "API", "固定 API，OPPO university recruitment"),
    "sf": ("https://campus.sf-express.com/api/web/position/query", "API", "固定 API，campus.sf-express.com position query"),
    "boe": ("https://campus.boe.com/api/Jobad/GetJobAdPageList", "API", "固定 API，BOE campus jobs"),
    "byd": ("https://job.byd.com/portal/api/portal-api/position/queryList", "API", "固定 API，payload zpType=00252/searchType=1"),
    "cvte": ("https://campus.cvte.com/api/project ; https://campus.cvte.com/api/position", "API", "固定 API，先取项目再取岗位"),
    "hikvision": ("https://campushr.hikvision.com/api/search/crsPositionSearch/getPositionByQuery", "API", "固定 API，jobNature=应届生"),
    "bilibili": ("https://jobs.bilibili.com/campus/positions", "页面", "专用 Playwright 固定列表页并点击分页"),
    "lenovo": ("https://talent.lenovo.com.cn/gateway/jobBase/list", "API", "固定 API，Lenovo jobBase list"),
}


def strip_base(url: str) -> str:
    return url.split("#")[0].split("?")[0].rstrip("/")


def hotjob_effective_url(url: str) -> str:
    parsed = urlparse(url)
    if "foxconn.hotjob.cn" in parsed.netloc:
        return "https://foxconn.hotjob.cn/wt/Foxconn/web/index/CompFoxconnPagerecruit_School"
    match = re.search(r"/(SU[0-9a-fA-F]+)", parsed.path)
    if not match:
        return url
    suite = match.group(1)
    base = f"https://{parsed.netloc}/{suite}"
    api = f"https://{parsed.netloc}/wecruit/positionInfo/listPosition/{suite}"
    return f"{api} ; fallback: {base}/pb/school.html ; {base}/mc/position/campus"


def alibaba_effective_url(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc or "campus-talent.alibaba.com"
    if host in {"campus.alibaba.com", "talent.alibaba.com"}:
        host = "campus-talent.alibaba.com"
    origin = f"https://{host}"
    return f"{origin}/campus/position?batchId=100000540002 ; API: {origin}/position/search"


def infer(company: dict) -> dict:
    crawler = company.get("crawler", "")
    config_url = company.get("careers_url", "")

    note = ""
    if crawler == "unitree":
        effective_url, access_type, rule, needs_review = config_url, "页面", "专用 crawler 直接打开配置入口", "否"
    elif crawler == "render":
        effective_url, access_type, rule, needs_review = config_url, "页面", "通用渲染 crawler 直接打开配置入口", "否"
    elif crawler == "moka":
        effective_url, access_type, rule, needs_review = strip_base(config_url) + "#/jobs", "页面", "Moka 平台：去掉 query/hash 后追加 #/jobs", "否"
    elif crawler == "beisen":
        effective_url = f"https://{urlparse(config_url).netloc}/campus/jobs"
        access_type, rule, needs_review = "页面", "北森平台：按配置 host 强制拼 /campus/jobs", "否"
    elif crawler == "feishu":
        effective_url = re.sub(r"/application$", "", config_url.split("?")[0].split("#")[0].rstrip("/"))
        access_type, rule, needs_review = "页面", "飞书平台：去掉 query/hash，并去掉末尾 /application", "否"
    elif crawler == "hotjob":
        effective_url = hotjob_effective_url(config_url)
        access_type, rule, needs_review = "API/页面", "Hotjob：优先新 PB API，失败后 fallback 到 /pb/school.html 和 /mc/position/campus", "否"
    elif crawler == "alibaba":
        effective_url, access_type, rule, needs_review = alibaba_effective_url(config_url), "页面+API", "阿里系：按配置 host 推导 origin，先打开 position 页再请求 position/search", "是"
    elif crawler == "netease":
        project_id = parse_qs(urlparse(config_url).query).get("id", ["69"])[0]
        effective_url = f"https://campus.163.com/api/campuspc/position/getJobList?projectId={project_id}"
        access_type, rule, needs_review = "API", "网易：从配置入口 query id 推导 projectId 后请求固定 API", "是"
    elif crawler == "leihuo":
        project_id = 73 if "intern" in config_url.lower() else 72
        effective_url = f"https://xiaozhao.leihuo.netease.com/api/apply/job/list/show?project_id={project_id}"
        access_type, rule, needs_review = "API", "网易雷火：按 URL 是否含 intern 推导 project_id", "是"
    elif crawler in FIXED_CRAWLERS:
        effective_url, access_type, rule = FIXED_CRAWLERS[crawler]
        needs_review = "是"
    elif crawler in PLACEHOLDER_CRAWLERS:
        effective_url = "未真实访问职位页：PlaceholderCrawler.fetch 返回空列表"
        access_type, rule, needs_review = "无", "占位 crawler，当前没有真实接入抓取逻辑", "是"
        note = "需要接入真实列表页/API后再核对"
    else:
        effective_url, access_type, rule, needs_review = config_url, "未知", "未识别 crawler，按配置入口展示", "是"
        note = "需要人工确认 crawler 实现"

    if not note and needs_review == "是":
        note = "建议优先核对：实际抓取地址/API 与配置入口可能不完全一致"

    return {
        "company": company.get("name", ""),
        "crawler": crawler,
        "config_url": config_url,
        "effective_url": effective_url,
        "access_type": access_type,
        "rule": rule,
        "needs_review": needs_review,
        "note": note,
    }


def main() -> None:
    config = yaml.safe_load(Path("config.yaml").read_text(encoding="utf-8"))
    rows = [infer(company) for company in config.get("companies", [])]
    output_dir = Path("outputs/crawler_effective_urls")
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / "effective_crawler_urls.json"
    output.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output.resolve())
    print(len(rows))


if __name__ == "__main__":
    main()
