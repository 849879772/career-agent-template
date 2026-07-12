"""一次性 DOM 调研脚本：渲染目标 URL，打印 a / h1-h4 / 常见列表容器，
   用于确定爬虫的真实 selector。

   python tests/inspect_dom.py <url>
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from crawlers.render import render_page
from bs4 import BeautifulSoup


def main():
    if len(sys.argv) < 2:
        print("Usage: python tests/inspect_dom.py <url> [wait_selector] [extra_wait_ms]")
        sys.exit(2)
    url = sys.argv[1]
    wait = sys.argv[2] if len(sys.argv) > 2 else None
    extra = int(sys.argv[3]) if len(sys.argv) > 3 else 4000
    print(f"渲染: {url}  wait={wait!r}  extra={extra}ms")
    html = render_page(url, wait_for=wait, extra_wait_ms=extra, timeout_ms=45000)
    if not html:
        print("渲染失败"); sys.exit(1)
    print(f"HTML 大小: {len(html)} bytes")
    soup = BeautifulSoup(html, "html.parser")

    print("\n--- title ---")
    print(soup.title.get_text(strip=True) if soup.title else "(无 title)")

    print("\n--- 标题元素样本 (h1-h4 前 15 个) ---")
    for tag in ["h1", "h2", "h3", "h4"]:
        for el in soup.find_all(tag)[:5]:
            txt = el.get_text(strip=True)[:80]
            if txt:
                print(f"  <{tag}> {txt}")

    print("\n--- 链接 (前 30 个非空 anchor) ---")
    cnt = 0
    seen = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href in seen or href.startswith("#") or href.startswith("javascript"):
            continue
        seen.add(href)
        txt = a.get_text(strip=True)[:40]
        print(f"  {href[:90]:90}  text={txt!r}")
        cnt += 1
        if cnt >= 30: break

    print("\n--- 常见列表容器 class 计数 ---")
    classes = {}
    for el in soup.find_all(class_=True):
        for c in el.get("class", []):
            if any(kw in c.lower() for kw in ("job", "position", "career", "list", "item", "card", "recruit")):
                classes[c] = classes.get(c, 0) + 1
    for c, n in sorted(classes.items(), key=lambda x: -x[1])[:20]:
        print(f"  .{c}  x{n}")


if __name__ == "__main__":
    main()
