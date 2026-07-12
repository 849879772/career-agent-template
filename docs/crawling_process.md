# 秋招岗位抓取流程

本文档记录当前项目的标准抓取与接入流程。后续如果发现更稳、更省成本或更自动化的方案，应同步更新本文档。

执行公司接入、校招链接验证、失败项处理、抓取状态维护等任务时，应使用本地 Codex skill：`recruitment-crawler-integration`。该 skill 负责提供标准步骤、辅助脚本和检查清单；本文档是项目级流程说明，二者需保持一致。

## 1. 公司来源与清洗

公司来源包括 `公司清单总览.xlsx`、历史投递记录、手动新增名单和用户临时指定公司。

处理前先清洗：

- 合并已由 `config.yaml` 覆盖的别名或集团子公司。
- 删除非公司行，例如面试状态、个人备注、组合提醒、纯实习记录。
- 子公司是否由集团入口覆盖要谨慎判断；不能只因为名称相似就合并。
- 处理结果必须同步到 `outputs/company_integration_status.md`。

## 2. 招聘入口发现

优先查找官方校招入口：

- Moka：`campus_apply` / `campus-recruitment`
- 北森 Beisen：`*.zhiye.com/campus/jobs`
- 飞书招聘：`*.jobs.feishu.cn`
- Hotjob：`wecruit.hotjob.cn`
- 51job / 智联官方校招专题
- 公司官网“校园招聘 / 加入我们 / 招贤纳士”页面

以下入口不能直接作为 crawler：

- 个人中心、投递记录、登录页、成功页、问卷/表单
- 微信公众号-only、学校公告、BOSS/猎聘/牛客/WonderCV/应届生网摘要
- 社招页、实习页、岗位分类页、产品介绍页、招聘流程页

## 3. Firecrawl 辅助层

Firecrawl 不只是“查看页面”，可以参与抓取，但在本项目中定位为加速器和长尾通用抓取候选。

推荐用途：

- `search`：找候选官方入口，但中文校招搜索可能噪声较高。
- `scrape`：对已知 URL 转 Markdown/JSON，快速判断页面是否有真实岗位。
- `map`：在官方域名内发现 `campus`、`jobs`、`join`、`school`、`xyzp` 等路径。
- `interact`：少量需要点击“查看职位”、翻页、筛选的动态页面。

不推荐常规使用：

- 大范围 `crawl`，容易抓出大量无关页面并消耗积分。
- `agent`，适合复杂研究，但常规公司批量接入成本高、可审计性弱。

可按需使用 Firecrawl 或浏览器工具检查候选招聘入口，但这些结果只用于发现链接。
项目内的 `scripts/validate_company.py` 仍是正式接入前的验收入口。

注意：Firecrawl 输出只能作为候选判断，不能绕过项目验证流程。

## 4. 项目 crawler 验收

所有候选 URL 必须通过项目脚本验证：

```powershell
$env:HTTP_PROXY="http://127.0.0.1:7897"; $env:HTTPS_PROXY="http://127.0.0.1:7897"
$env:PYTHONIOENCODING="utf-8"
python scripts/validate_company.py 公司名 URL crawler
```

判定标准：

- `OK` 且样例是具体岗位标题，才允许接入。
- `validate_company.py` 的 `OK` 不是自动放行；如果样例是人物故事、文章标题、职位类别、岗位方向集合或包含实习岗，必须拒绝或继续找真实岗位页。
- 静态官网页如果样例是栏目词或页面结构词，如“研发中心”“研发实力”“研发平台”“职能类型”“招聘类型”“职位类型”“所属部门”，应改进过滤或标为不可直接接入，不能当岗位。
- 静态官网页如果样例是产品/服务栏目词，如“开发套件和开发板”“参考设计”“设计服务”，应改进过滤或标为不可直接接入，不能当岗位。
- 静态官网页如果样例含明显社招级别词，如“高级工程师”“资深”“专家”“主管”“经理”“总监”，默认不作为正式校招岗位接入，除非页面明确标注该岗位属于校园招聘。
- `SUSPECT-社招`、`EMPTY`、岗位分类、职责句、产品文案、社招/实习混入，都不允许直接接入。
- 不能只看岗位标题过滤实习：还要检查招聘项目/岗位类型标签和岗位摘要。例如腾讯的“日常实习”“应届实习”可能与正式岗共用同一个岗位标题，必须在入库前过滤。
- 只有可定位到单个岗位的 URL 才能标记为岗位详情；列表页、标题哈希锚点、分类页和无法解析详情的链接只能标记为“招聘列表”，报告中不得显示为“去投递”。
- 如果 Firecrawl 能抓到岗位，但本项目 crawler 抓不到，应先判断是否需要新增或改进 crawler。

## 5. crawler 选择

- `moka`：Moka 校招页面。
- `beisen`：北森 `campus/jobs`。除 `*.zhiye.com` 外，也可接入企业自定义北森域名（如 `hr.example.com/campus/jobs`），前提是 `validate_company.py` 返回具体校招岗位。
- `feishu`：飞书招聘页面或短链。
- `hotjob`：Hotjob 校招页。
- `render`：JS 渲染页面、51job/智联专题、自建动态页。
- `static_html`：官网静态岗位列表页。
- 可新增 `firecrawl` crawler：适合长尾官网页、结构混乱但 Firecrawl Markdown 干净的页面。

新增 `firecrawl` crawler 时仍需做过滤：

- 过滤实习、社招、岗位分类、职责句、产品/导航文案。
- 输出统一 job dict。
- 最终仍由测试和样例人工复核把关。

## 6. 写入配置与状态文档

只有通过验证后才写 `config.yaml`：

```yaml
- name: 公司名
  careers_url: https://example.com/campus/jobs
  crawler: render
```

同时更新 `outputs/company_integration_status.md`：

- 成功接入：`Newly added +1`，`Not connected -1`。
- 已有配置覆盖：`Already covered +1`，`Not connected -1`。
- 有链接但不能用：`Has URL +1`，`Not connected -1`。
- 纯噪声行：删除待处理行并记录 cleanup note。

失败原因要具体，例如：

- returned 0 jobs
- social jobs only
- internships only
- third-party page only
- announcement/PDF only
- product/category text, not jobs
- wrong company
- requires narrower parser

## 7. 最终测试

每批接入后至少运行：

```powershell
python -c "import yaml; d=yaml.safe_load(open('config.yaml',encoding='utf-8')); print(len(d['companies']))"
python -m pytest tests/test_crawlers.py tests/test_job_filters.py
```

如果修改了通用 crawler 的过滤规则，应复验至少一个已知成功页面，避免误伤。

如果修改了链接解析规则，还要检查：

- 真正详情链接打开后标题与抓取岗位一致；
- 无法解析的链接在报告中显示“招聘列表”，而不是“去投递”；
- 历史数据库中的实习/社招遗留行会被清理，投递记录本身不删除。

## 8. 当前推荐架构

最稳妥的长期流程是：

1. 普通搜索 / Firecrawl search 找候选入口。
2. Firecrawl scrape 快速看页面和抽岗位候选。
3. 用项目 crawler 和 `validate_company.py` 做最终验收。
4. 通过后写 `config.yaml`。
5. 失败或覆盖结果写入 `outputs/company_integration_status.md`。
6. `python main.py` 正式抓取、过滤、入库、AI 分析和生成报告。

一句话：Firecrawl 负责加速发现和解析长尾页面，项目 crawler 负责稳定生产抓取，状态文档负责全过程可追踪。
