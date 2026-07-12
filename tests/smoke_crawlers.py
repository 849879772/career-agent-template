"""手动冒烟脚本（不被 pytest 收集，文件名以 smoke_ 开头）。

用法：
    python tests/smoke_crawlers.py            # 全部跑
    python tests/smoke_crawlers.py unitree    # 只跑指定爬虫
    python tests/smoke_crawlers.py dji huawei

会真实访问目标网站，每家耗时 30-60 秒，总共可能 3-5 分钟。
首次使用前确保已运行：
    pip install -r requirements.txt
    playwright install chromium
"""

import io
import logging
import sys
from pathlib import Path

# Windows PowerShell 默认 GBK，强制 UTF-8 输出避免 CJK 兼容字符崩溃
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")

from crawlers.bytedance import ByteDanceCrawler  # noqa: E402
from crawlers.dji import DJICrawler  # noqa: E402
from crawlers.huawei import HuaweiCrawler  # noqa: E402
from crawlers.unitree import UnitreeCrawler  # noqa: E402
from crawlers.xiaomi import XiaomiCrawler  # noqa: E402
from crawlers.moka import MokaRecruitCrawler  # noqa: E402
from crawlers.beisen import BeisenRecruitCrawler  # noqa: E402

CRAWLERS = {
    "unitree": (UnitreeCrawler, "宇树科技", "https://www.unitree.com/careers/"),
    "dji": (DJICrawler, "大疆", "https://we.dji.com/zh-CN/campus"),
    "bytedance": (ByteDanceCrawler, "字节跳动", "https://jobs.bytedance.com/campus"),
    "huawei": (
        HuaweiCrawler,
        "华为",
        "https://career.huawei.com/reccampportal/portal5/campus-recruitment.html",
    ),
    "xiaomi": (XiaomiCrawler, "小米", "https://xiaomi.jobs.f.mioffice.cn/"),
    # 平台级爬虫（各拿一家真站冒烟）
    "moka": (MokaRecruitCrawler, "速腾聚创",
             "https://app.mokahr.com/campus-recruitment/robosense/69887"),
    "beisen": (BeisenRecruitCrawler, "浙江大华", "https://dahua1.zhiye.com/campus/jobs"),
}


def run_one(key: str):
    cls, name, url = CRAWLERS[key]
    print(f"\n{'='*60}\n  [{key}] {name}  -->  {url}\n{'='*60}")
    jobs = cls(name, url).fetch()
    print(f"\n抓到岗位数：{len(jobs)}")
    for i, j in enumerate(jobs[:5], 1):
        print(f"  {i}. {j['title']}  |  {j['city']}  |  {j['jd_url'][:80]}")
    if len(jobs) > 5:
        print(f"  ... 还有 {len(jobs) - 5} 个")
    return len(jobs)


def main():
    targets = sys.argv[1:] or list(CRAWLERS.keys())
    unknown = [t for t in targets if t not in CRAWLERS]
    if unknown:
        print(f"未知爬虫：{unknown}。可选：{list(CRAWLERS.keys())}")
        sys.exit(2)

    summary = {}
    for key in targets:
        try:
            summary[key] = run_one(key)
        except Exception as e:
            summary[key] = f"异常: {e}"

    print(f"\n\n{'='*60}\n  汇总\n{'='*60}")
    for k, v in summary.items():
        print(f"  {k:10s}  {v}")


if __name__ == "__main__":
    main()
