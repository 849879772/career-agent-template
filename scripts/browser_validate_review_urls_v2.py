from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright


ROOT = Path("outputs/crawler_effective_urls")
INPUT = ROOT / "auto_validation_results.json"
JSON_OUT = ROOT / "browser_validation_results_v2.json"
CSV_OUT = ROOT / "browser_validation_results_v2.csv"

NEED_REVIEW = "\u9700\u4eba\u5de5\u786e\u8ba4"
SUSPECT = "\u7591\u4f3c\u9519\u8bef"

CAMPUS_RE = re.compile(
    r"校园招聘|校招|应届|毕业生|2026届|2027届|campus|graduate|university|student",
    re.I,
)
JOB_RE = re.compile(
    r"职位|岗位|在招|全部职位|招聘职位|职位列表|投递|申请|position|job|opening|apply",
    re.I,
)
DETAIL_RE = re.compile(
    r"工作职责|岗位职责|职位描述|任职资格|职位要求|立即投递|申请职位|apply now",
    re.I,
)
RISK_RE = re.compile(r"社会招聘|社招|实习生招聘|实习岗位|internship|experienced", re.I)
BLOCK_RE = re.compile(
    r"请先登录|登录后查看|注册后查看|查询投递记录|身份认证|访问受限|无权限|Forbidden|Access Denied|参数错误",
    re.I,
)
EMPTY_RE = re.compile(r"暂无职位|暂无岗位|没有相关职位|职位已下线|0\s*个职位|共\s*0\s*个", re.I)


def load_targets() -> list[dict]:
    rows = json.loads(INPUT.read_text(encoding="utf-8"))
    targets = [r for r in rows if r.get("auto_verdict") in {NEED_REVIEW, SUSPECT}]
    seen = set()
    out = []
    for row in targets:
        key = (row.get("company"), row.get("crawler"), row.get("config_url"), row.get("effective_url"))
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def normalize_url(url: str) -> str:
    return (url or "").strip()


def probe(page, kind: str, url: str) -> dict:
    result = {
        "kind": kind,
        "url": url,
        "ok": False,
        "status": "",
        "final_url": "",
        "title": "",
        "body_len": 0,
        "link_count": 0,
        "campus_signal": False,
        "job_signal": False,
        "detail_signal": False,
        "risk_signal": False,
        "block_signal": False,
        "empty_signal": False,
        "sample_text": "",
        "error": "",
    }
    if not url.startswith(("http://", "https://")):
        result["error"] = "非 HTTP URL"
        return result

    try:
        resp = page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2500)
        # Trigger lazy-loaded lists on portals such as Moka, Beisen, and Feishu.
        for _ in range(2):
            page.mouse.wheel(0, 1600)
            page.wait_for_timeout(600)
        status = resp.status if resp else ""
        title = page.title()
        body = page.locator("body").inner_text(timeout=8000)
        links = page.locator("a").count()
        combined = f"{url}\n{page.url}\n{title}\n{body}"
        result.update(
            ok=not (isinstance(status, int) and status >= 400),
            status=status,
            final_url=page.url,
            title=title[:160],
            body_len=len(body),
            link_count=links,
            campus_signal=bool(CAMPUS_RE.search(combined)),
            job_signal=bool(JOB_RE.search(combined)),
            detail_signal=bool(DETAIL_RE.search(combined)),
            risk_signal=bool(RISK_RE.search(combined)),
            block_signal=bool(BLOCK_RE.search(combined)),
            empty_signal=bool(EMPTY_RE.search(combined)),
            sample_text=re.sub(r"\s+", " ", body)[:260],
        )
    except PlaywrightError as exc:
        result["error"] = str(exc).splitlines()[0][:240]
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"{type(exc).__name__}: {exc}"[:240]
    return result


def classify(row: dict, probes: list[dict]) -> tuple[str, str, str]:
    ok_probes = [p for p in probes if p.get("ok")]
    if not ok_probes:
        errors = "; ".join(p.get("error") or f"HTTP {p.get('status')}" for p in probes)
        return "失败-浏览器无法打开", "检查网络/反爬/链接是否失效", errors[:300]

    best = max(ok_probes, key=lambda p: (
        p.get("campus_signal", False) + p.get("job_signal", False) + p.get("detail_signal", False),
        p.get("body_len", 0),
    ))
    if best.get("block_signal") and not (
        best.get("campus_signal") and (best.get("job_signal") or best.get("detail_signal"))
    ):
        return "失败-登录验证码或权限限制", "需要人工浏览器登录/验证码后再测", best.get("sample_text", "")
    if best.get("empty_signal"):
        return "可打开-空列表或岗位下线", "秋招未开或岗位已下线；crawler 不应报错", best.get("sample_text", "")
    if best.get("campus_signal") and (best.get("job_signal") or best.get("detail_signal")):
        if best.get("risk_signal"):
            return "通过-有校招岗位信号但含实习/社招入口", "保留 crawler，但确认过滤规则", best.get("sample_text", "")
        return "通过-校招岗位页可用", "无需人工继续确认", best.get("sample_text", "")
    if best.get("job_signal") or best.get("detail_signal"):
        return "可打开-有岗位信号但校招不明确", "人工确认是否校招入口", best.get("sample_text", "")
    return "可打开-招聘信号不足", "人工确认入口是否正确", best.get("sample_text", "")


def main() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    rows = load_targets()
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, proxy={"server": "http://127.0.0.1:7897"})
        context = browser.new_context(
            viewport={"width": 1440, "height": 1000},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
            ),
            locale="zh-CN",
        )
        page = context.new_page()
        for idx, row in enumerate(rows, start=1):
            urls = [("配置入口", normalize_url(row.get("config_url", "")))]
            effective = normalize_url(row.get("effective_url", ""))
            if effective and effective != urls[0][1]:
                urls.append(("实际访问", effective))
            probes = [probe(page, kind, url) for kind, url in urls if url]
            verdict, action, reason = classify(row, probes)
            results.append({
                **row,
                "browser_verdict_v2": verdict,
                "recommended_action": action,
                "browser_reason": reason,
                "probes": probes,
            })
            print(f"{idx}/{len(rows)} {row.get('company')} {verdict}", flush=True)
        context.close()
        browser.close()

    JSON_OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    fields = [
        "company", "crawler", "auto_verdict", "confidence", "access_type",
        "browser_verdict_v2", "recommended_action", "browser_reason",
        "config_url", "effective_url", "probe_summary",
    ]
    with CSV_OUT.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in results:
            summary = []
            for p in row.get("probes", []):
                summary.append(
                    " | ".join([
                        str(p.get("kind", "")),
                        str(p.get("url", "")),
                        "OK" if p.get("ok") else "FAIL",
                        str(p.get("status", "")),
                        str(p.get("title", "")),
                        str(p.get("final_url", "")),
                        str(p.get("error", "")),
                    ])
                )
            writer.writerow({
                **{field: row.get(field, "") for field in fields},
                "probe_summary": "\n".join(summary),
            })
    print(JSON_OUT.resolve())
    print(CSV_OUT.resolve())


if __name__ == "__main__":
    sys.exit(main())
