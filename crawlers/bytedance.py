from .feishu import FeishuRecruitCrawler


class ByteDanceCrawler(FeishuRecruitCrawler):
    """字节跳动校招（飞书招聘 jobs.bytedance.com）。

    DOM 与翻页逻辑见 FeishuRecruitCrawler，这里只配站点参数。
    每页 10 个岗位、总页数很多（首页底部显示 78 页），抓前 5 页 50 个足够。
    """

    LIST_URL = "https://jobs.bytedance.com/campus/position"
    HOST = "https://jobs.bytedance.com"
    MAX_PAGES = 5
    GOTO_WAIT_UNTIL = "domcontentloaded"
    GOTO_TIMEOUT_MS = 45000
    JD_RAW_LIMIT = 1000
