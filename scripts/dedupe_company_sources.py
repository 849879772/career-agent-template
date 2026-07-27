"""Merge duplicate configured recruitment sources and their stored company names.

Only entries with the same crawler and the same normalized official entry URL
are merged. This deliberately avoids fuzzy name matching across subsidiaries.
"""

from __future__ import annotations

import argparse
import csv
import re
import shutil
import sqlite3
from datetime import datetime
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.yaml"
DB_PATH = ROOT / "data" / "jobs.db"
REPORT_PATH = ROOT / "outputs" / "company_source_deduplication.csv"
DISPLAY_NAMES = {"oppo": "OPPO", "shein": "SHEIN", "tcl": "TCL"}
NAME_ALIASES = {
    "大华": "大华股份",
    "海康sb公司": "海康威视",
    "图森牛客内推": "图森智途",
    "锐捷": "锐捷网络",
    "零跑": "零跑汽车",
    "创达": "中科创达",
    "Momenta-M Star": "Momenta",
    "影石Insta360": "影石",
    "搜狐畅游-下周一官宣": "搜狐畅游",
    "文远知行WeRid": "文远知行",
    "恩智浦Qq!": "恩智浦",
    "匠芯创科技(hr邮箱)": "匠芯创科技",
    "因诺科技(hr邮箱)": "因诺科技",
    "思格新能源nk": "思格新能源",
    "成都精灵云nk": "成都精灵云",
    "曦华科技nk": "曦华科技",
    "阿里云（侧开-北上深杭-8.5发布9.1结束）尽早投": "阿里云",
    "柠檬微趣（初级测试工程师-北京-8.1发布-10-14k）五天内投": "柠檬微趣",
    "阿里平头哥（侧开-上海-8.8）15天内投": "阿里平头哥",
    "陶天集团（侧开-上海-8.4发布）五天内投": "淘天",
    "旷世科技-极感科技（图像算法工程师（人像感知方向）北京/成都-8.4发布）五天内投，不抱希望试试看": "旷视科技",
    "航天飞鹏-央企": "航天飞鹏",
}

# These entries are either covered by a broader official source or are
# referral/internship-only pages that cannot serve as a complete company feed.
REDUNDANT_SOURCE_NAMES = {
    "海康sb公司",
    "Momenta-M Star",
    "影石Insta360",
    "恩智浦Qq!",
}
EXCLUDED_SOURCE_NAMES = {
    "理想内推",
    "去哪儿旅行内推",
    "云创智行实习",
    "实习僧autowise.ai",
}


def source_key(company: dict) -> tuple[str, str]:
    url = urlsplit(company["careers_url"])
    normalized_url = urlunsplit((
        url.scheme.lower(), url.netloc.lower(), url.path.rstrip("/").lower(), "", ""
    ))
    # Moka exposes the same project through both campus_apply and
    # campus-recruitment routes. The tenant/project pair is the real source.
    if company["crawler"] == "moka":
        match = re.search(r"/(?:campus_apply|campus-recruitment)/([^/]+)/([^/]+)$", url.path, re.I)
        if match:
            normalized_url = f"moka-project:{match.group(1).lower()}/{match.group(2).lower()}"
    return company["crawler"], normalized_url


def build_plan(companies: list[dict]) -> tuple[list[dict], list[dict]]:
    canonical_by_source: dict[tuple[str, str], str] = {}
    kept: list[dict] = []
    aliases: list[dict] = []
    for company in companies:
        company = dict(company)
        original_name = company["name"]
        company["name"] = NAME_ALIASES.get(
            original_name,
            DISPLAY_NAMES.get(original_name.casefold(), original_name),
        )
        if original_name != company["name"]:
            aliases.append({
                "alias": original_name,
                "canonical": company["name"],
                "crawler": company["crawler"],
                "careers_url": company["careers_url"],
            })
        if original_name in EXCLUDED_SOURCE_NAMES:
            aliases.append({
                "alias": original_name,
                "canonical": "",
                "crawler": company["crawler"],
                "careers_url": company["careers_url"],
            })
            continue
        if original_name in REDUNDANT_SOURCE_NAMES:
            continue
        key = source_key(company)
        canonical = canonical_by_source.get(key)
        if canonical is None:
            canonical_by_source[key] = company["name"]
            kept.append(company)
            continue
        aliases.append({
            "alias": original_name,
            "canonical": canonical,
            "crawler": company["crawler"],
            "careers_url": company["careers_url"],
        })
    unique_aliases = {
        (row["alias"], row["canonical"], row["crawler"], row["careers_url"]): row
        for row in aliases
    }
    return kept, list(unique_aliases.values())


def apply_aliases(aliases: list[dict]) -> int:
    conn = sqlite3.connect(DB_PATH)
    changed = 0
    try:
        for row in aliases:
            if not row["canonical"] or row["alias"] == row["canonical"]:
                continue
            changed += conn.execute(
                "UPDATE jobs SET company = ? WHERE company = ?", (row["canonical"], row["alias"])
            ).rowcount
            conn.execute(
                "DELETE FROM job_screening_cache WHERE company = ?",
                (row["alias"],),
            )
        # Legacy rows can outlive their removed config alias. Normalize the
        # few case-only display names even when the alias no longer appears.
        for folded, canonical in DISPLAY_NAMES.items():
            changed += conn.execute(
                "UPDATE jobs SET company = ? WHERE lower(company) = ? AND company <> ?",
                (canonical, folded, canonical),
            ).rowcount
            conn.execute(
                "DELETE FROM job_screening_cache WHERE lower(company) = ? AND company <> ?",
                (folded, canonical),
            )
        conn.commit()
    finally:
        conn.close()
    return changed


def main() -> None:
    parser = argparse.ArgumentParser(description="Deduplicate identical company recruitment sources")
    parser.add_argument("--apply", action="store_true", help="rewrite config.yaml and data/jobs.db")
    args = parser.parse_args()

    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    companies = config.get("companies", [])
    kept, aliases = build_plan(companies)

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with REPORT_PATH.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=["alias", "canonical", "crawler", "careers_url"])
        writer.writeheader()
        writer.writerows(aliases)

    print(f"configured={len(companies)} kept={len(kept)} duplicate_entries={len(aliases)}")
    print(f"report={REPORT_PATH}")
    if not args.apply:
        return

    backup = DB_PATH.with_name(
        f"{DB_PATH.name}.bak_before_company_alias_cleanup_"
        f"{datetime.now():%Y%m%d_%H%M%S}"
    )
    shutil.copy2(DB_PATH, backup)
    config["companies"] = kept
    CONFIG_PATH.write_text(
        yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    changed = apply_aliases(aliases)
    print(f"database_backup={backup}")
    print(f"database_rows_renamed={changed}")


if __name__ == "__main__":
    main()
