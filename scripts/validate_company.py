"""渲染验证候选公司：**是校招 + 能抓到** 才放行。只读，绝不写 config。

用真实爬虫（CRAWLER_MAP）渲染候选页，给出裁决：
  - OK         ：抓到 ≥1 岗 + 通过校招校验 → 可入库
  - SUSPECT-社招：抓到岗位但疑似社招（标题社招词比例高 / URL 非 campus 路径）→ 人工复核
  - EMPTY      ：0 岗（疑老版 DOM / WAF / 死链）→ 不入库

用法：
    python scripts/validate_company.py 名称 URL crawler              # 单条
    python scripts/validate_company.py --from data/candidates.json   # 批量
    python scripts/validate_company.py --from data/candidates.json --limit 10 --offset 0   # 分批（每家 ~30-60s）

产出：
    打印逐家裁决；写 data/validation_report.json；OK 项汇成 data/approved.yaml（可文本追加进 config.yaml）
"""
import io
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent.parent))

from crawlers import CRAWLER_MAP  # noqa: E402

ROOT = Path(__file__).parent.parent
REPORT_PATH = ROOT / "data" / "validation_report.json"
APPROVED_PATH = ROOT / "data" / "approved.yaml"

# 社招信号词（标题命中比例高 → 疑社招）。大小写不敏感。
SOCIAL_WORDS = [
    "资深", "高级", "专家", "经验", "年以上", "社招", "社会招聘", "总监", "主管", "负责人",
    "lead", "senior", "staff", "principal", "expert", "director", "manager",
]


def _is_campus_url(crawler: str, url: str) -> bool:
    """URL 路径层面的校招校验（防社招/投递页混入）。"""
    u = url.lower()
    p = urlparse(u)
    if crawler == "moka":
        return "/campus_apply/" in u or "/campus-recruitment/" in u or "campus" in u
    if crawler == "beisen":
        return "/campus/" in p.path or re.match(r"^/\d+/jobs/?$", p.path) is not None
    if crawler == "feishu":
        return "feishu" in p.netloc or "mioffice" in p.netloc  # 路径 token 各租户不同，仅排除明显社招
    return True


def _social_ratio(titles: list[str]) -> float:
    if not titles:
        return 0.0
    low = [t.lower() for t in titles]
    hit = sum(1 for t in low if any(w.lower() in t for w in SOCIAL_WORDS))
    return hit / len(low)


def validate_one(entry: dict) -> dict:
    name, url, crawler = entry["name"], entry["careers_url"], entry["crawler"]
    res = {"name": name, "careers_url": url, "crawler": crawler,
           "count": 0, "samples": [], "social_ratio": 0.0, "campus_url": _is_campus_url(crawler, url)}
    cls = CRAWLER_MAP.get(crawler)
    if cls is None:
        res["verdict"] = "ERROR"
        res["reason"] = f"未知 crawler: {crawler}"
        return res
    try:
        jobs = cls(name, url).fetch() or []
    except Exception as e:  # noqa: BLE001
        res["verdict"] = "EMPTY"
        res["reason"] = f"fetch 异常: {type(e).__name__}: {e}"
        return res

    titles = [j.get("title", "") for j in jobs]
    res["count"] = len(jobs)
    res["samples"] = [{"title": j.get("title", ""), "city": j.get("city", "")} for j in jobs[:8]]
    res["social_ratio"] = round(_social_ratio(titles), 2)

    if not jobs:
        res["verdict"] = "EMPTY"
        res["reason"] = "0 岗（疑老版 DOM / WAF / 死链）"
    elif res["social_ratio"] > 0.5 or not res["campus_url"]:
        res["verdict"] = "SUSPECT-社招"
        res["reason"] = f"社招词比例 {res['social_ratio']} / campus_url={res['campus_url']}"
    else:
        res["verdict"] = "OK"
        res["reason"] = ""
    return res


def _load_candidates(argv) -> list[dict]:
    if "--from" in argv:
        src = Path(argv[argv.index("--from") + 1])
        items = json.loads(src.read_text(encoding="utf-8"))
    else:
        # 单条：名称 URL crawler
        pos = [a for a in argv if not a.startswith("--")]
        if len(pos) < 3:
            print("用法：validate_company.py 名称 URL crawler  |  --from candidates.json"); sys.exit(1)
        items = [{"name": pos[0], "careers_url": pos[1], "crawler": pos[2]}]
    # 分批
    if "--offset" in argv:
        items = items[int(argv[argv.index("--offset") + 1]):]
    if "--limit" in argv:
        items = items[:int(argv[argv.index("--limit") + 1])]
    return items


def _save(results: list[dict]) -> list[dict]:
    """合并历史报告并落盘（report + approved.yaml）。返回合并后全量。"""
    prev = []
    if REPORT_PATH.exists():
        try:
            prev = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            prev = []
    by_name = {r["name"]: r for r in prev}
    for r in results:
        by_name[r["name"]] = r
    merged = list(by_name.values())
    REPORT_PATH.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")

    ok = [r for r in merged if r["verdict"] == "OK"]
    lines = ["# validate_company.py 验证通过（OK）的公司——可文本追加进 config.yaml\n"]
    for r in ok:
        lines.append(f"  - name: {r['name']}\n    careers_url: {r['careers_url']}\n    crawler: {r['crawler']}\n")
    APPROVED_PATH.write_text("".join(lines), encoding="utf-8")
    return merged


def main():
    argv = sys.argv[1:]
    items = _load_candidates(argv)
    print(f"待验证 {len(items)} 家（每家 Playwright 渲染 ~30-60s）\n")

    results = []
    for i, e in enumerate(items, 1):
        r = validate_one(e)
        mark = {"OK": "✅", "SUSPECT-社招": "⚠️", "EMPTY": "⛔", "ERROR": "❓"}.get(r["verdict"], "?")
        print(f"{mark} [{i}/{len(items)}] {r['name']:<16} {r['verdict']:<12} {r['count']}岗  {r['reason']}", flush=True)
        for s in r["samples"][:3]:
            print(f"      · {s['title']}  |  {s['city']}", flush=True)
        results.append(r)
        _save(results)  # 逐家 checkpoint，后台中途崩溃不丢进度

    merged = _save(results)
    ok = [r for r in merged if r["verdict"] == "OK"]

    n = len(results)
    cnt = lambda v: sum(1 for r in results if r["verdict"] == v)  # noqa: E731
    print(f"\n本次 {n} 家：OK {cnt('OK')} / SUSPECT {cnt('SUSPECT-社招')} / EMPTY {cnt('EMPTY')} / ERROR {cnt('ERROR')}")
    print(f"累计 OK {len(ok)} 家 → {APPROVED_PATH}（复核后文本追加进 config.yaml）")
    print(f"完整报告 → {REPORT_PATH}")


if __name__ == "__main__":
    main()
