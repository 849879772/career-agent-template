"""把验证通过的公司（data/approved.yaml）**文本追加**进 config.yaml，保留全部注释。

不同于初版 import 的 yaml.dump 整体重写（会抹注释），这里只在文件尾部追加文本块。

用法：
    python scripts/promote.py                       # 干跑，预览将追加的公司
    python scripts/promote.py --write               # 真正追加进 config.yaml
    python scripts/promote.py --from data/approved.yaml --section "Phase 1 批量接入" --write
"""
import io
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml

ROOT = Path(__file__).parent.parent
CONFIG_PATH = ROOT / "config.yaml"
DEFAULT_SRC = ROOT / "data" / "approved.yaml"


def main():
    argv = sys.argv[1:]
    write = "--write" in argv
    src = Path(argv[argv.index("--from") + 1]) if "--from" in argv else DEFAULT_SRC
    section = argv[argv.index("--section") + 1] if "--section" in argv else "师兄清单批量接入"

    entries = yaml.safe_load(src.read_text(encoding="utf-8")) or []
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    existing = {c["name"] for c in config["companies"]}

    new = [e for e in entries if e["name"] not in existing]
    skipped = [e for e in entries if e["name"] in existing]

    print(f"approved {len(entries)} 家 → 新增 {len(new)} / 已存在跳过 {len(skipped)}\n")
    for e in new:
        print(f"  + {e['name']:<16} [{e['crawler']}] {e['careers_url'][:60]}")
    if not new:
        print("（无新增）"); return

    block = [f"  # ── {section} ────────────────────────────────"]
    for e in new:
        block.append(f"  - name: {e['name']}")
        block.append(f"    careers_url: {e['careers_url']}")
        block.append(f"    crawler: {e['crawler']}")

    if not write:
        print("\n（干跑，未写入。加 --write 真正文本追加进 config.yaml）"); return

    # companies: 不一定是文件最后一节（后面还有 claude: 等），故插到 companies 列表末尾，
    # 即 companies: 之后第一个顶格（col-0 非空）行之前，且跳过其前的空行。
    lines = CONFIG_PATH.read_text(encoding="utf-8").split("\n")
    ci = next(i for i, ln in enumerate(lines) if ln.rstrip() == "companies:")
    boundary = next((i for i in range(ci + 1, len(lines)) if lines[i].strip() and not lines[i][0].isspace()), len(lines))
    insert_at = boundary
    while insert_at - 1 > ci and lines[insert_at - 1].strip() == "":
        insert_at -= 1
    new_lines = lines[:insert_at] + block + lines[insert_at:]
    CONFIG_PATH.write_text("\n".join(new_lines), encoding="utf-8")
    # 校验追加后仍可解析、注释未丢
    after = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    print(f"\n✅ 已文本追加 {len(new)} 家 → config.yaml（公司总数 {len(after['companies'])}）")


if __name__ == "__main__":
    main()
