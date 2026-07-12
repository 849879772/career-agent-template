import logging
from typing import Optional

logger = logging.getLogger(__name__)

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# 标准 stealth 注入：隐藏 navigator.webdriver 标志
_STEALTH_INIT_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en'] });
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
"""

# 阻挡的资源类型（图片/字体能提速但保留 stylesheet：
# Playwright 的 wait_for_selector 需要 CSS 计算元素可见性，否则会误判超时）
_BLOCKED_RESOURCE_TYPES = {"image", "media", "font"}


def render_page(
    url: str,
    wait_for: Optional[str] = None,
    timeout_ms: int = 30000,
    extra_wait_ms: int = 0,
    scroll_times: int = 0,
) -> Optional[str]:
    """渲染 SPA 页面并返回完整 HTML。失败时返回 None。

    Args:
        url: 目标 URL
        wait_for: CSS selector，等到该元素出现再返回；为 None 时等 networkidle
        timeout_ms: 总超时（毫秒）
        extra_wait_ms: selector 命中后额外等待的毫秒数（让懒加载完成）
        scroll_times: 额外滚动到底的次数（触发列表懒加载/分页加载）
    """
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        logger.error(
            "未安装 playwright。请运行：pip install -r requirements.txt && "
            "playwright install chromium"
        )
        return None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                ],
            )
            context = browser.new_context(
                user_agent=_USER_AGENT,
                viewport={"width": 1366, "height": 768},
                locale="zh-CN",
                ignore_https_errors=True,
            )
            context.add_init_script(_STEALTH_INIT_SCRIPT)

            page = context.new_page()
            page.route(
                "**/*",
                lambda route: route.abort()
                if route.request.resource_type in _BLOCKED_RESOURCE_TYPES
                else route.continue_(),
            )

            try:
                try:
                    page.goto(url, wait_until="networkidle", timeout=timeout_ms)
                except PWTimeout:
                    logger.warning("[render] goto networkidle 超时 %s（仍尝试解析当前页面）", url)
                if wait_for:
                    try:
                        page.wait_for_selector(wait_for, timeout=timeout_ms, state="attached")
                    except PWTimeout:
                        logger.warning("[render] selector %s 未在 %dms 内出现", wait_for, timeout_ms)
                if extra_wait_ms > 0:
                    page.wait_for_timeout(extra_wait_ms)
                # 滚动到底加载懒加载列表（Moka/北森 等无限滚动列表）
                for _ in range(scroll_times):
                    try:
                        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        page.wait_for_timeout(1200)
                    except Exception:
                        break
                return page.content()
            finally:
                context.close()
                browser.close()
    except Exception as e:
        logger.error("[render] 渲染异常 %s: %s", url, e)
        return None
