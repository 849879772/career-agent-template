"""Read the public Tencent Docs smart sheet before the daily campus crawl.

The document exposes its initial smart-sheet state through the public
``dop-api/opendoc`` JSONP endpoint.  This module intentionally reads only the
shared sheet; it never sends edits to Tencent Docs.
"""

from __future__ import annotations

import base64
import html
import json
import re
import zlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


SOURCE_URL = "https://docs.qq.com/smartsheet/DY3pHYkNvb0ZRSHdi?tab=BB08J2&viewId=vUQPXH"
TARGET_TAG = "27届秋招"
EXCLUDED_TAGS = {"27届秋招提前批", "27届暑期实习", "日常实习", "可转正实习"}

# Names in the shared sheet are often campaign names rather than the canonical
# company names used by config.yaml.
ALIASES = {
    "DJI大疆": "大疆",
    "科大讯飞-飞凡计划": "科大讯飞",
    "京东-TET管理培训生": "京东",
    "百度-校招&管培生": "百度",
    "思特威-岗位陆续上新": "思特威",
    "MiniMax Top Talent 计划": "MiniMax",
    "远景能源-看备注，主要C9": "远景科技",
    "学而思-陆续上新": "学而思",
}


def _text(cell: dict[str, Any]) -> str:
    value = cell.get("k1") or []
    if not isinstance(value, list):
        return ""
    return "".join(str(part.get("k2") or "") for part in value if isinstance(part, dict)).strip()


def _walk(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _parse_jsonp(text: str) -> dict[str, Any]:
    prefix = "clientVarsCallback("
    content = text.strip()
    if not content.startswith(prefix) or not content.endswith(")"):
        raise ValueError("腾讯文档返回内容不是预期的 JSONP")
    return json.loads(content[len(prefix):-1])


def _load_sheet_payload(session: requests.Session) -> Any:
    page = session.get(SOURCE_URL, timeout=30)
    page.raise_for_status()
    match = re.search(r'<link rel="preload" as="script" href="([^"]*opendoc[^"]+)', page.text)
    if not match:
        raise ValueError("未找到腾讯文档公开数据入口")

    endpoint = html.unescape(match.group(1))
    if endpoint.startswith("//"):
        endpoint = "https:" + endpoint
    response = session.get(endpoint, headers={"Referer": SOURCE_URL}, timeout=30)
    response.raise_for_status()
    client_vars = _parse_jsonp(response.text)["clientVars"]
    compressed = client_vars["collab_client_vars"]["initialAttributedText"]["text"][0]["smartsheet"]
    # Tencent Docs may omit base64 padding and occasionally uses URL-safe
    # alphabet characters in the compressed sheet payload.
    padded = compressed + "=" * (-len(compressed) % 4)
    return json.loads(zlib.decompress(base64.urlsafe_b64decode(padded)))


def parse_rows(payload: Any) -> list[dict[str, Any]]:
    """Return all rows carrying the exact 27届秋招 label and their real URLs."""
    fields: dict[str, str] = {}
    options: dict[str, str] = {}
    needed = {"公司名称", "招聘类型", "投递链接"}
    for item in _walk(payload):
        for field_id, definition in item.items():
            if not isinstance(definition, dict) or definition.get("k30") not in needed:
                continue
            fields[definition["k30"]] = field_id
            for option in ((definition.get("k9") or {}).get("k3") or []):
                if isinstance(option, dict):
                    options[str(option.get("k1") or "")] = str(option.get("k2") or "")

    if set(fields) != needed:
        raise ValueError("腾讯文档字段结构已变化")

    rows: dict[str, dict[str, Any]] = {}
    for item in _walk(payload):
        cells = item.get("k1") if isinstance(item, dict) else None
        if not isinstance(cells, dict) or fields["公司名称"] not in cells or fields["招聘类型"] not in cells:
            continue
        name = _text(cells[fields["公司名称"]])
        tags = [options.get(str(tag), str(tag)) for tag in cells[fields["招聘类型"]].get("k9", [])]
        if not name or TARGET_TAG not in tags:
            continue
        links = [
            str(link.get("k3") or "")
            for link in cells.get(fields["投递链接"], {}).get("k8", [])
            if isinstance(link, dict) and link.get("k3")
        ]
        row = {"source_name": name, "canonical_name": ALIASES.get(name, name), "tags": tags, "links": links}
        rows[name] = row

    for row in rows.values():
        excluded = set(row["tags"]) & EXCLUDED_TAGS
        # This status is informational only. A secondary internship or early
        # batch tag must not suppress a company carrying the 27-autumn tag.
        row["source_status"] = "strict_formal" if not excluded else "mixed_or_excluded"
        row["excluded_tags"] = sorted(excluded)
    return sorted(rows.values(), key=lambda row: row["source_name"])


def compare_with_config(rows: list[dict[str, Any]], companies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    configured = {str(company.get("name") or "").casefold() for company in companies}
    for row in rows:
        row["in_config"] = row["canonical_name"].casefold() in configured
    return rows


def run(companies: list[dict[str, Any]]) -> dict[str, Any]:
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})
    rows = compare_with_config(parse_rows(_load_sheet_payload(session)), companies)
    return {
        "source_url": SOURCE_URL,
        "checked_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "rows": rows,
        "covered": sum(row["in_config"] for row in rows),
        "needs_integration": sum(not row["in_config"] for row in rows),
    }


def write_report(result: dict[str, Any], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    import yaml

    root = Path(__file__).resolve().parents[1]
    config = yaml.safe_load((root / "config.yaml").read_text(encoding="utf-8"))
    result = run(config["companies"])
    output = root / "outputs" / "qq_docs_27_autumn_monitor.json"
    write_report(result, output)
    print(f"腾讯文档 27届秋招：{len(result['rows'])} 条，已覆盖 {result['covered']}，待接入 {result['needs_integration']}")
    print(output)
