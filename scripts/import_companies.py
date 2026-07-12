"""从师兄投递清单 CSV 生成**候选公司清单**（只产出 data/candidates.json，不写 config）。

覆盖三个有通用爬虫的平台：Moka / 飞书 / 北森。按方向白名单（phase*_targets.txt）严选——
每家都要 Playwright 渲染验证，全量上百家会拖垮流水线，故聚焦方向相关公司。

写 config 由 validate_company.py 验证后**文本追加**完成（保留注释），本脚本不再碰 config。

用法：
    python scripts/import_companies.py --csv path/to/companies.csv
    python scripts/import_companies.py --revive-beisen  # Phase 2：「假死」北森（登录/个人页），URL 归一化为 /campus/jobs
    python scripts/import_companies.py --out data/candidates.json   # 自定义输出路径
"""
import csv
import io
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml

ROOT = Path(__file__).parent.parent
CONFIG_PATH = ROOT / "config.yaml"
DEFAULT_OUT = ROOT / "data" / "candidates.json"
TARGETS_PATH = Path(__file__).parent / "phase1_targets.txt"
TARGETS_P2_PATH = Path(__file__).parent / "phase2_targets.txt"

# CSV「识别平台」→ 爬虫 key
PLATFORM_CRAWLER = {"Moka": "moka", "北森": "beisen", "飞书招聘": "feishu", "e成/hotjob": "hotjob"}
# Phase 2「假死」北森的死链标记
REVIVE_MARKS = {"登录/个人页"}


def clean_name(raw: str) -> str:
    """去掉公司名里的括号备注：韶音科技（拒绝996…）→ 韶音科技。"""
    return re.split(r"[（(]", raw, 1)[0].strip()


def beisen_campus_url(url: str) -> str:
    """把任意北森 URL 归一化为校招列表页 https://{netloc}/campus/jobs（爬虫本就这么推，这里同步存储）。"""
    netloc = urlparse(url).netloc
    return f"https://{netloc}/campus/jobs" if netloc else url


def load_existing() -> set:
    config = yaml.safe_load(open(CONFIG_PATH, encoding="utf-8"))
    return {c["name"] for c in config["companies"]}


def load_targets(path: Path) -> list[str]:
    """读取方向白名单（每行一个公司名，# 注释与空行忽略）。"""
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            out.append(line)
    return out


def _select_by_targets(rows, existing, targets, row_ok, crawler_of, url_of):
    """按白名单子串匹配 CSV；canonical 名取白名单条目，天然去重同公司多行。"""
    picked = {}  # target -> entry
    for tgt in targets:
        if tgt in existing or tgt in picked:
            continue
        for r in rows:
            if not row_ok(r):
                continue
            name = clean_name(r["公司名称"])
            url = (r["招聘链接"] or "").split("?")[0].strip()
            if url and (tgt in name or name in tgt):
                picked[tgt] = {"name": tgt, "careers_url": url_of(url, crawler_of(r)), "crawler": crawler_of(r)}
                break
        else:
            print(f"  （未在 CSV 中找到：{tgt}）")
    return list(picked.values())


def select_phase1(rows, existing):
    targets = load_targets(TARGETS_PATH)
    if not targets:
        print("⚠️ 未找到 phase1_targets.txt"); return []
    return _select_by_targets(
        rows, existing, targets,
        row_ok=lambda r: not r["死链标记"] and r["识别平台"] in PLATFORM_CRAWLER,
        crawler_of=lambda r: PLATFORM_CRAWLER[r["识别平台"]],
        url_of=lambda url, c: beisen_campus_url(url) if c == "beisen" else url,
    )


def select_revive_beisen(rows, existing):
    targets = load_targets(TARGETS_P2_PATH)
    if not targets:
        print("⚠️ 未找到 phase2_targets.txt"); return []
    return _select_by_targets(
        rows, existing, targets,
        row_ok=lambda r: r["识别平台"] == "北森" and r["死链标记"] in REVIVE_MARKS,
        crawler_of=lambda r: "beisen",
        url_of=lambda url, c: beisen_campus_url(url),
    )


# 清单里的噪声行（师兄的笔记/分组标题，非真实公司）。
_NOISE_NAMES = ("公司", "投递记录", "正式批", "备注", "实习", "暑期")


def _is_noise(name: str) -> bool:
    return (not name) or any(k in name for k in _NOISE_NAMES)


def select_all(rows, existing):
    """全部平台可接公司（Moka/北森/飞书），含北森「假死」(登录/个人页)恢复。

    不做方向筛选——用户要"全部都要"。北森 URL 一律归一化为 /campus/jobs。
    """
    picked = {}
    for r in rows:
        plat = r["识别平台"]
        if plat not in PLATFORM_CRAWLER:
            continue
        mark = r["死链标记"]
        # 接受：活链；或北森「假死」个人页（host 有效，可换 /campus/jobs 复活）
        if mark and not (plat == "北森" and mark in REVIVE_MARKS):
            continue
        name = clean_name(r["公司名称"])
        url = (r["招聘链接"] or "").split("?")[0].strip()
        if _is_noise(name) or not url or name in existing or name in picked:
            continue
        crawler = PLATFORM_CRAWLER[plat]
        careers = beisen_campus_url(url) if crawler == "beisen" else url
        picked[name] = {"name": name, "careers_url": careers, "crawler": crawler}
    return list(picked.values())


def main():
    argv = sys.argv[1:]
    if "--csv" not in argv:
        raise SystemExit("用法: python scripts/import_companies.py --csv path/to/companies.csv [--all|--revive-beisen]")
    csv_path = Path(argv[argv.index("--csv") + 1])
    revive = "--revive-beisen" in argv
    all_mode = "--all" in argv
    out = Path(argv[argv.index("--out") + 1]) if "--out" in argv else DEFAULT_OUT

    rows = list(csv.DictReader(open(csv_path, encoding="utf-8-sig")))
    existing = load_existing()
    if all_mode:
        entries = select_all(rows, existing)
    elif revive:
        entries = select_revive_beisen(rows, existing)
    else:
        entries = select_phase1(rows, existing)

    by = {}
    for e in entries:
        by[e["crawler"]] = by.get(e["crawler"], 0) + 1
    phase = "全部平台可接(--all)" if all_mode else ("Phase 2 假死北森恢复" if revive else "Phase 1 平台方向公司")
    dist = " / ".join(f"{k} {v}" for k, v in sorted(by.items()))
    print(f"[{phase}] 候选 {len(entries)} 家（{dist}）：\n")
    for e in entries:
        print(f"  - {e['name']:<16} [{e['crawler']:<6}] {e['careers_url'][:64]}")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✅ 已写候选 → {out}（下一步：python scripts/validate_company.py --from {out}）")


if __name__ == "__main__":
    main()
