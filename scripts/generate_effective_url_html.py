import html
import json
from pathlib import Path


ROOT = Path("outputs/crawler_effective_urls")
JSON_PATH = ROOT / "effective_crawler_urls.json"
AUTO_PATH = ROOT / "auto_validation_results.json"
BROWSER_PATH = ROOT / "browser_validation_results.json"
HTML_PATH = ROOT / "公司真实抓取地址核对表.html"


def esc(value) -> str:
    return html.escape(str(value or ""), quote=True)


def linkify(value) -> str:
    text = str(value or "")
    parts = []
    last = 0
    for match in re_url.finditer(text):
        if match.start() > last:
            parts.append(esc(text[last:match.start()]))
        url = match.group(0).rstrip(";,")
        suffix = match.group(0)[len(url):]
        parts.append(f'<a href="{esc(url)}" target="_blank">{esc(url)}</a>{esc(suffix)}')
        last = match.end()
    if last < len(text):
        parts.append(esc(text[last:]))
    return "".join(parts)


re_url = __import__("re").compile(r"https?://[^\s;]+")


def main() -> None:
    raw_rows = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    auto_rows = json.loads(AUTO_PATH.read_text(encoding="utf-8")) if AUTO_PATH.exists() else []
    browser_rows = json.loads(BROWSER_PATH.read_text(encoding="utf-8")) if BROWSER_PATH.exists() else []
    auto_by_key = {
        (
            str(row.get("crawler", "")).strip().lower(),
            str(row.get("config_url", "")).strip().rstrip("/").lower(),
            str(row.get("effective_url", "")).strip().rstrip("/").lower(),
        ): row
        for row in auto_rows
    }
    browser_by_key = {
        (
            str(row.get("crawler", "")).strip().lower(),
            str(row.get("config_url", "")).strip().rstrip("/").lower(),
            str(row.get("effective_url", "")).strip().rstrip("/").lower(),
        ): row
        for row in browser_rows
    }
    rows = []
    seen = set()
    for row in raw_rows:
        key = (
            str(row.get("crawler", "")).strip().lower(),
            str(row.get("config_url", "")).strip().rstrip("/").lower(),
            str(row.get("effective_url", "")).strip().rstrip("/").lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        rows.append(row)

    body_rows = []
    for idx, row in enumerate(rows, start=1):
        key = (
            str(row.get("crawler", "")).strip().lower(),
            str(row.get("config_url", "")).strip().rstrip("/").lower(),
            str(row.get("effective_url", "")).strip().rstrip("/").lower(),
        )
        auto = auto_by_key.get(key, {})
        browser_result = browser_by_key.get(key, {})
        review_class = "needs-review" if row["needs_review"] == "是" else ""
        auto_verdict = auto.get("auto_verdict", "未验证")
        auto_class = {
            "自动通过": "auto-pass",
            "需人工确认": "auto-manual",
            "疑似错误": "auto-error",
        }.get(auto_verdict, "auto-unknown")
        counts = "/".join(
            str(auto.get(k, ""))
            for k in ("raw_count", "formal_count", "dropped_count")
            if str(auto.get(k, "")) != ""
        )
        browser_verdict = browser_result.get("browser_verdict", "未测试")
        browser_class = {
            "浏览器可打开且有招聘信号": "browser-pass",
            "可打开但信号不足": "browser-warn",
            "浏览器打开失败": "browser-fail",
        }.get(browser_verdict, "browser-unknown")
        probe_notes = []
        for probe in browser_result.get("probes", []):
            status = "OK" if probe.get("ok") else "FAIL"
            details = probe.get("title") or probe.get("error") or probe.get("final_url") or ""
            probe_notes.append(f"{probe.get('kind', '')}: {status} {details}")
        browser_note = "；".join(probe_notes)
        body_rows.append(
            f"""
            <tr class="{review_class} {auto_class} {browser_class}">
              <td class="num">{idx}</td>
              <td class="company">{esc(row['company'])}</td>
              <td>{esc(row['crawler'])}</td>
              <td><a href="{esc(row['config_url'])}" target="_blank">{esc(row['config_url'])}</a></td>
              <td class="effective-links">{linkify(row['effective_url'])}</td>
              <td>{esc(row['access_type'])}</td>
              <td>{esc(row['rule'])}</td>
              <td class="center">{esc(row['needs_review'])}</td>
              <td class="auto-verdict">{esc(auto_verdict)}</td>
              <td class="counts">{esc(counts)}</td>
              <td>{esc(auto.get('auto_reason', ''))}</td>
              <td class="browser-verdict">{esc(browser_verdict)}</td>
              <td>{esc(browser_note)}</td>
              <td class="verify">
                <label><input type="radio" name="verify_{idx}" value="是"> 是</label>
                <label><input type="radio" name="verify_{idx}" value="否"> 否</label>
              </td>
              <td><input class="correct-url" data-row="{idx}" type="url" placeholder="验证失败时填正确校招地址"></td>
              <td><textarea class="manual-note" data-row="{idx}" placeholder="你的核对备注"></textarea></td>
              <td>{esc(row['note'])}</td>
            </tr>
            """
        )

    html_doc = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>公司真实抓取地址核对表</title>
  <style>
    :root {{
      --header: #1f4e79;
      --line: #d7e2ea;
      --band: #eef8fb;
      --review: #fff0e8;
      --text: #162033;
    }}
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif;
      color: var(--text);
      background: #f6f8fb;
    }}
    header {{
      position: sticky;
      top: 0;
      z-index: 3;
      background: #ffffff;
      border-bottom: 1px solid var(--line);
      padding: 14px 20px;
      display: flex;
      gap: 18px;
      align-items: center;
      justify-content: space-between;
    }}
    h1 {{
      margin: 0;
      font-size: 18px;
      font-weight: 700;
    }}
    .toolbar {{
      display: flex;
      gap: 10px;
      align-items: center;
      flex-wrap: wrap;
    }}
    .toolbar input {{
      width: 260px;
      padding: 7px 10px;
      border: 1px solid #b8c7d3;
      border-radius: 4px;
      font-size: 14px;
    }}
    .toolbar label {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-size: 14px;
      white-space: nowrap;
    }}
    main {{
      padding: 14px 20px 28px;
    }}
    table {{
      width: 100%;
      border-collapse: separate;
      border-spacing: 0;
      background: #fff;
      box-shadow: 0 1px 3px rgba(15, 23, 42, .08);
    }}
    th {{
      position: sticky;
      top: 59px;
      z-index: 2;
      background: var(--header);
      color: #fff;
      font-weight: 700;
      font-size: 13px;
      text-align: left;
      padding: 9px 10px;
      border-right: 1px solid rgba(255,255,255,.18);
      white-space: nowrap;
    }}
    td {{
      vertical-align: top;
      padding: 8px 10px;
      border-bottom: 1px solid var(--line);
      font-size: 13px;
      line-height: 1.35;
      max-width: 420px;
      word-break: break-all;
    }}
    tbody tr:nth-child(odd) td {{
      background: var(--band);
    }}
    tbody tr.needs-review td {{
      background: var(--review);
    }}
    .auto-verdict {{
      min-width: 92px;
      text-align: center;
      font-weight: 700;
      white-space: nowrap;
    }}
    tr.auto-pass .auto-verdict {{
      color: #166534;
    }}
    tr.auto-manual .auto-verdict {{
      color: #92400e;
    }}
    tr.auto-error .auto-verdict {{
      color: #991b1b;
    }}
    .browser-verdict {{
      min-width: 128px;
      text-align: center;
      font-weight: 700;
      white-space: nowrap;
    }}
    tr.browser-pass .browser-verdict {{
      color: #166534;
    }}
    tr.browser-warn .browser-verdict {{
      color: #92400e;
    }}
    tr.browser-fail .browser-verdict {{
      color: #991b1b;
    }}
    .counts {{
      min-width: 92px;
      text-align: center;
      color: #475569;
      white-space: nowrap;
    }}
    tbody tr.last-clicked td {{
      background: #fff7c2 !important;
      box-shadow: inset 0 2px 0 #d97706, inset 0 -2px 0 #d97706;
    }}
    .last-badge {{
      display: inline-block;
      margin-left: 8px;
      padding: 2px 6px;
      border-radius: 4px;
      background: #d97706;
      color: #fff;
      font-size: 12px;
      font-weight: 700;
      white-space: nowrap;
    }}
    a {{
      color: #075985;
      text-decoration: none;
    }}
    a:hover {{
      text-decoration: underline;
    }}
    .num {{
      text-align: right;
      width: 52px;
      color: #475569;
    }}
    .company {{
      min-width: 130px;
      font-weight: 600;
    }}
    .center {{
      text-align: center;
      min-width: 72px;
      font-weight: 700;
    }}
    .verify {{
      min-width: 110px;
      white-space: nowrap;
    }}
    .verify label {{
      display: inline-flex;
      align-items: center;
      gap: 4px;
      margin-right: 10px;
      cursor: pointer;
    }}
    .verify input {{
      accent-color: #166534;
    }}
    .correct-url {{
      width: 260px;
      box-sizing: border-box;
      padding: 6px 8px;
      border: 1px solid #b8c7d3;
      border-radius: 4px;
      font-size: 13px;
      background: #fff;
    }}
    .manual-note {{
      width: 240px;
      min-height: 34px;
      box-sizing: border-box;
      padding: 6px 8px;
      border: 1px solid #b8c7d3;
      border-radius: 4px;
      font-size: 13px;
      line-height: 1.35;
      resize: vertical;
      background: #fff;
      font-family: inherit;
    }}
    .hidden {{
      display: none;
    }}
  </style>
</head>
<body>
  <header>
    <h1>公司真实抓取地址核对表</h1>
    <div class="toolbar">
      <input id="search" type="search" placeholder="搜索公司 / crawler / 地址">
      <label><input id="reviewOnly" type="checkbox"> 只看重点核对</label>
      <label><input id="autoRiskOnly" type="checkbox"> 只看需人工/疑似</label>
      <label><input id="browserFailOnly" type="checkbox"> 只看浏览器失败</label>
      <span id="count"></span>
    </div>
  </header>
  <main>
    <table>
      <thead>
        <tr>
          <th>序号</th>
          <th>公司</th>
          <th>crawler</th>
          <th>配置入口</th>
          <th>实际访问地址/API</th>
          <th>访问类型</th>
          <th>推导规则</th>
          <th>需重点核对</th>
          <th>自动结论</th>
          <th>实抓数量<br>原始/正式/过滤</th>
          <th>自动原因</th>
          <th>浏览器验证</th>
          <th>浏览器详情</th>
          <th>验证结果</th>
          <th>正确地址（你填写）</th>
          <th>手动备注（你填写）</th>
          <th>备注</th>
        </tr>
      </thead>
      <tbody>
        {''.join(body_rows)}
      </tbody>
    </table>
  </main>
  <script>
    const storageKey = "crawler-effective-url-review-v1";
    const lastClickedKey = "crawler-effective-url-last-clicked-row-v1";
    const saved = JSON.parse(localStorage.getItem(storageKey) || "{{}}");

    function save() {{
      const data = {{}};
      document.querySelectorAll("tbody tr").forEach((tr, index) => {{
        const row = index + 1;
        const checked = tr.querySelector(`input[name="verify_${{row}}"]:checked`);
        const url = tr.querySelector(".correct-url").value;
        const manualNote = tr.querySelector(".manual-note").value;
        if (checked || url || manualNote) data[row] = {{ verify: checked?.value || "", url, manualNote }};
      }});
      localStorage.setItem(storageKey, JSON.stringify(data));
    }}

    Object.entries(saved).forEach(([row, data]) => {{
      if (data.verify) {{
        const radio = document.querySelector(`input[name="verify_${{row}}"][value="${{data.verify}}"]`);
        if (radio) radio.checked = true;
      }}
      const input = document.querySelector(`.correct-url[data-row="${{row}}"]`);
      if (input && data.url) input.value = data.url;
      const note = document.querySelector(`.manual-note[data-row="${{row}}"]`);
      if (note && data.manualNote) note.value = data.manualNote;
    }});

    document.addEventListener("change", save);
    document.addEventListener("input", event => {{
      if (event.target.classList.contains("correct-url") || event.target.classList.contains("manual-note")) save();
      applyFilter();
    }});

    function markLastClicked(rowNumber) {{
      document.querySelectorAll("tbody tr").forEach(tr => {{
        tr.classList.remove("last-clicked");
        tr.querySelectorAll(".last-badge").forEach(badge => badge.remove());
      }});

      const tr = document.querySelector(`tbody tr:nth-child(${{rowNumber}})`);
      if (!tr) return;
      tr.classList.add("last-clicked");
      const companyCell = tr.querySelector(".company");
      const badge = document.createElement("span");
      badge.className = "last-badge";
      badge.textContent = "上次点击";
      companyCell.appendChild(badge);
    }}

    const lastClicked = localStorage.getItem(lastClickedKey);
    if (lastClicked) markLastClicked(lastClicked);

    document.querySelectorAll(".effective-links a").forEach(link => {{
      link.addEventListener("click", () => {{
        const rowNumber = link.closest("tr").rowIndex;
        localStorage.setItem(lastClickedKey, String(rowNumber));
        markLastClicked(rowNumber);
      }});
    }});

    const search = document.getElementById("search");
    const reviewOnly = document.getElementById("reviewOnly");
    const autoRiskOnly = document.getElementById("autoRiskOnly");
    const browserFailOnly = document.getElementById("browserFailOnly");
    const count = document.getElementById("count");

    function applyFilter() {{
      const q = search.value.trim().toLowerCase();
      let visible = 0;
      document.querySelectorAll("tbody tr").forEach(tr => {{
        const hit = !q || tr.innerText.toLowerCase().includes(q);
        const reviewHit = !reviewOnly.checked || tr.classList.contains("needs-review");
        const autoRiskHit = !autoRiskOnly.checked || tr.classList.contains("auto-manual") || tr.classList.contains("auto-error");
        const browserFailHit = !browserFailOnly.checked || tr.classList.contains("browser-fail");
        const show = hit && reviewHit && autoRiskHit && browserFailHit;
        tr.classList.toggle("hidden", !show);
        if (show) visible++;
      }});
      count.textContent = `显示 ${{visible}} / {len(rows)} 行（已从 {len(raw_rows)} 行去重）`;
    }}

    search.addEventListener("input", applyFilter);
    reviewOnly.addEventListener("change", applyFilter);
    autoRiskOnly.addEventListener("change", applyFilter);
    browserFailOnly.addEventListener("change", applyFilter);
    applyFilter();
  </script>
</body>
</html>
"""

    HTML_PATH.write_text(html_doc, encoding="utf-8")
    print(HTML_PATH.resolve())


if __name__ == "__main__":
    main()
