# 秋招岗位抓取流程

## 0. 腾讯文档 27 届秋招前置监控

每天执行 `python main.py` 时，先只读检查腾讯文档“秋招内推汇总”表。当前正式秋招表的工作表 ID 为 `t0gmEC`；`BB08J2` 是实习汇总表，不能作为正式秋招监控源。脚本 `scripts/qq_docs_27_autumn_monitor.py` 读取公开的智能表格数据，提取带有精确 `27届秋招` 标签的公司名称、标签和真实投递链接，并写入 `outputs/qq_docs_27_autumn_monitor.json`。

- 腾讯文档公开接口每次只返回 60 行。监控脚本会继续读取后续窗口并合并去重，避免秋招条目位于后续页时被遗漏。若结果突然从多家公司降为 0，必须先在网页核对当前工作表名称和 URL 中的 `tab`，不能直接把 0 当作“今天没有秋招公司”。
- 名称先通过别名表归一化，再与 `config.yaml` 比对；已覆盖公司会等待主 crawler 的实际抓取结果。
- 腾讯文档常在公司名后追加“下周官宣”“陆续上新”“未官宣”等活动备注，必须先映射为稳定公司名。若稳定公司名已在配置中但旧入口返回 0，应升级原入口而不是再新增一个同名配置；柠檬微趣即由失效官网静态页升级为当前 Moka 项目。
- 不在配置中的公司进入受控自动接入：先由腾讯链接识别已有平台 crawler（Moka、北森、飞书、Hotjob 或通用渲染器），再真实抓取并依次执行正式校招、具体岗位和目标方向过滤。只有返回至少一个正式且方向相关的具体岗位时，才自动追加到 `config.yaml` 并加入同轮主流程；返回 0 岗位、实习/社招混入、方向外岗位、未知平台或异常时，不写配置，而是更新 `outputs/company_integration_status.md` 的“腾讯文档自动接入状态”。
- 已经人工确认过期、只含导航或无法作为招聘入口的来源必须进入自动接入阻断名单，不能因为腾讯文档再次出现就回流到生产配置。阻断应同时记录 URL 与原因，并由测试保证不会调用 crawler。
- 同时携带 `27届暑期实习`、`日常实习`、`可转正实习` 或 `27届秋招提前批` 标签的来源会标记为 `mixed_or_excluded`，但只要同时有精确 `27届秋招` 标签，仍必须进入公司核验与抓取。是否为正式校招应在岗位级别通过标题、项目标签和岗位正文判断，不能仅因公司层标签混合而跳过整家公司。
- 该来源不可访问时记录警告但不阻断固定公司抓取，避免单一外部表格影响每日任务。

本文档记录当前项目的标准抓取与接入流程。后续如果发现更稳、更省成本或更自动化的方案，应同步更新本文档。

执行公司接入、校招链接验证、失败项处理、抓取状态维护等任务时，应使用本地 Codex skill：`recruitment-crawler-integration`。该 skill 负责提供标准步骤、辅助脚本和检查清单；本文档是项目级流程说明，二者需保持一致。

## 1. 公司来源与清洗

公司来源包括 `公司清单总览.xlsx`、历史投递记录、手动新增名单和用户临时指定公司。

处理前先清洗：

- 合并已由 `config.yaml` 覆盖的别名或集团子公司。
- 对同名多入口不能只比较公司名或 URL。必须分别实跑并比较岗位稳定 ID 集合：完全重合时保留当前、可稳定返回岗位的入口；各自存在独有岗位时按不同招聘项目保留。配置去重后还要检查数据库中是否存在由旧入口留下的重复岗位。
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

自建站首页只有“查看在招职位”时，必须继续跟到真实列表并检查分页和详情。例如埃科光电岗位实际位于 `/front.home.index/schoolList`，首页本身不能作为岗位抓取结果。SPA 菜单打开新招聘项目时，应同时查看菜单目标 URL 和岗位列表网络请求；网易互娱当前 27 届项目由此确认是 `projectId=102`，不能沿用旧页面路径或 crawler 默认项目。

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

已创建辅助脚本：

```powershell
python C:\Users\周帅康\.codex\skills\recruitment-crawler-integration\scripts\recruitment_candidate_probe.py companies.txt --out data/candidates_probe.json
python C:\Users\周帅康\.codex\skills\recruitment-crawler-integration\scripts\firecrawl_scrape_jobs.py "https://example.com/campus" --out data/firecrawl_probe.json
```

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
- 不能只看岗位标题过滤实习：还要检查招聘项目、岗位类型、页面头部元数据、URL、当前实习周期要求及中英文正文。例如腾讯的“日常实习”“应届实习”可能与正式岗共用标题，京东会通过 `type=internship` 区分同名岗位，阿里会写“实习生专项招聘”，东风页面会只在元数据写“实习生”，这些都必须在入库前过滤。
- 列表卡片文字不能视为完整 JD。职责与要求缺失、正文为空或仅含“标题 + 发布时间”时标记为不完整；进入匹配分析前必须渲染具体岗位详情页补全并回写。补全失败时不得用空壳 JD 调用模型。
- 数据库刷新不得用较短的列表摘要覆盖已经补全的详情正文。Moka 等列表型 crawler 可以继续用摘要发现岗位，但详情内容应按需补全；批量补全优先覆盖首次出现或用户实际关注的岗位，避免每天全量渲染数千个详情页。
- “能连续实习三个月”“实习薪酬津贴”“转正机会”属于岗位本身是实习的强信号；“有实习经历/项目经验者优先”只是正式校招的加分项，不能误删。使用 `scripts/audit_formal_campus_content.py` 查看逐岗位判定及保留项。
- 提前批不进入数据库。标题、招聘类型、正文或 URL 明确出现“提前批”“提前招聘”“提前选拔”“预招聘”时直接过滤；青云、TOP Talent、Super Sparks 等专项人才计划若页面标注正式且没有上述提前批或实习信号，应继续保留。
- 不要把公司配置名当成岗位属性。普通校园招聘入口必须使用正式公司名，例如亿联网络的通用校园页不能命名为“亿联网络提前批”；只指向 internship 专区的来源不得保留在生产配置。
- 只有可定位到单个岗位的 URL 才能标记为岗位详情；列表页、标题哈希锚点、分类页和无法解析详情的链接只能标记为“招聘列表”，报告中不得显示为“去投递”。
- `link_kind: list` 的公司必须让按钮打开可访问的官方招聘列表，不能继续保留已知会 404、断开连接或跳错站点的伪详情 URL。多个岗位共用列表页时，在 URL fragment 中加入稳定的 `job-ref` 标识以避免 SQLite 唯一键把岗位合并；该标识不改变浏览器实际打开的列表页面。
- HTTP 200 只证明 SPA 外壳可达，不证明岗位仍存在。对于京东等详情内容来自 API 的站点，必须同时用岗位详情 API 校验 ID；API 未返回 `publishId` 和岗位标题时，应判为下线或错误页面。
- 官网已迁移到新校招门户且当前返回 0 岗位时，应以新官网为准并记录“当前未开放”，不能为了保留旧岗位继续使用过期专题。清理旧行前必须先真实浏览新入口，并确认旧详情已经失效；同程旅行的 2019 专题即按此规则迁移。
- 通用 crawler 不得把 YouTube、LinkedIn、微博、视频站或通用求职搜索结果当成企业岗位详情；这些外链即使锚文本含“工程师”也必须丢弃，验收脚本将其作为阻断项。
- 如果 Firecrawl 能抓到岗位，但本项目 crawler 抓不到，应先判断是否需要新增或改进 crawler。
- 通用网络层对临时连接失败采用有限重试：Requests 最多请求 3 次，Playwright 页面导航最多尝试 2 次。重试后仍返回 0 岗位的公司不得计入“成功公司”，也不得据此判断历史岗位下线。
- “今日下线”只比较昨天仍被看到、今天该公司又成功返回岗位但未再次出现的记录。更早的历史批次不能反复计入今日下线；连续多日抓取失败的公司只保留在活跃窗口和健康审计中，不生成伪下线通知。
- 累计主页和飞书“全部追踪”只读取最近 3 天活跃窗口，不再展示数据库中的永久历史全集。SQLite 仍保留历史记录；三天缓冲用于容忍单次抓取失败，避免站点偶发故障让整家公司立即消失。

### 4.1 届别证据闸门

届别判断必须发生在 JD 详情补全、Flash 粗筛和 V4-Pro 匹配评分之前。系统只把有官方证据确认的 2027 届岗位视为当前目标岗位。

1. 证据优先级依次为：岗位标题、官方 API 的招聘类型/项目字段、公司校招入口正文、岗位正文。发布时间中的年份不是届别证据。
2. 每条岗位持久化 `cohort`、`cohort_status`、`cohort_source`、`cohort_evidence` 和 `cohort_checked_at`，以便审计“为什么被判为 27 届”。
3. 公司校招入口明确写“2027 届校园招聘”时，可作为同一入口内未标年份岗位的公司级证据；仅因为同公司某一个岗位写了“27 届”，不能自动推断其他岗位也是 27 届。
4. 同时出现多个招聘届别时标记为 `conflict`，不能选择较新的年份；官网无明确年份时标记为 `unknown`。
5. 确认 27 届进入“27届校招”；确认 2026 届及更早进入“往届校招岗位”；未知或冲突进入“届别待确认”。三类互斥。
6. 往届和待确认岗位不补抓 JD、不执行 Flash 分级、不调用 V4-Pro，也不进入飞书推荐；只维护岗位链接和上下线状态。
7. 可运行 `python scripts/backfill_job_cohorts.py --all` 重新检查官方入口并回写证据，使用 `python scripts/audit_cohort_pipeline.py` 验收三类数量和违规评分。

8. 英文岗位标题中的 `campus-2026`、`2027 Campus Recruitment`、`new grad 2027` 也可作为届别证据，但只识别完整四位年份，避免把发布日期中的月份或日期误判为届别。
9. 每家公司先检查 `campaign_url`（未配置时使用 `careers_url`）的官方校招活动页。普通 HTTP 看不到活动标题时使用 Playwright 渲染；腾讯文档提供的官方链接可在当次运行中作为活动页候选，但腾讯文档标签本身不构成届别证据。
10. 实际岗位列表存在“2027 校招/2027 秋招”项目时，岗位必须保存所属项目到 `campaign_text`；该项目中的非实习岗位确认成 2027 届，明确标注实习、提前批或社招的岗位仍优先排除。项目制页面不得把 2027 届扩散到 TOP Talent 等未标年份的其他项目。
11. 岗位列表没有届别项目时，如果统一校招首页明确只有一个正式校招年份，则所有当前非实习校招岗位继承该年份。页面可以同时存在其他年份的实习项目，但多个正式校招年份仍视为冲突，不进行公司级继承。
12. 前两层均无届别结论时，腾讯文档中明确带“27届秋招”的公司可作为受约束兜底：仅确认已通过正式校招过滤、没有明确往届证据、且不属于其他未标届别项目的岗位。证据必须随当次腾讯文档读取写入内存，保存来源名称、原文和链接；来源撤下后不得继续使用旧缓存。
13. 岗位发布时间不参与届别推断。2026 年发布可能仍是 2026 届春招、补录或 2027 届实习，不能仅凭日期确认 2027 届。
14. 公司级检查结果写入 `outputs/company_campaign_evidence.json`，记录活动页、提取方式、证据原文、适用范围和检查时间。员工故事中的“历届校招生”、发布日期和结果数量不得作为招聘届别。
15. 岗位 JD 明确给出毕业时间区间时，以区间结束年份作为届别，例如“2026 年 10 月 1 日至 2027 年 9 月 30 日期间毕业”确认成 2027 届；普通发布日期和不含“毕业”语义的日期区间仍不参与判断。

### 4.2 仅 27 届 JD 详情补全

只有 `cohort=2027` 且 `cohort_status=confirmed` 的岗位进入 JD 完整度检查。生产数据必须优先保存招聘平台详情 API 中的完整字段，而不是列表摘要。常见组合包括 `description + requirement`、`Duty + Require`、`jobDuty + jobRequirement`；写入 `jd_raw` 时保留“职位描述 / 任职要求”等标题，单条正文上限为 12000 字符。

1. 平台 crawler 在发现岗位后直接请求详情 API；飞书详情页优先使用公开 `api/v1/job/posts/{id}` 接口。
   Hotjob 列表接口返回的 `postId` 必须继续请求
   `/wecruit/positionInfo/listPositionDetail/SU...`，读取 `workContent` 与
   `serviceCondition`，并把链接改为可打开的 `pb/posDetail.html?postId=...`。
   详情接口明确返回“招聘已关闭/岗位已下架”时，该岗位不得继续入库。
2. API 无详情时才用 Playwright 打开具体岗位页补全，列表 URL 不做无意义渲染。
3. 确认 27 届岗位若只有标题、地点、发布时间或短列表摘要，标记为 JD 不完整，不调用 Pro。非 27 届岗位使用 `not_required`，不进入待补全队列。
4. 详情补全成功后立即回写，避免长任务中断时丢失进度；后续运行不得用更短的列表摘要覆盖完整正文。
5. 腾讯青云等官方 API 本身不提供职责/要求的岗位保留为待补全，不伪造 JD，也不生成匹配分。
6. 51job 专题必须核对页面语义与数据脚本。例如数字绿土 `si.html/js/sz.js`
   是社会招聘，正式校招应使用 `san.html/js/xz.js`，并只接受投递 URL 中
   `type=CAMPUSRECRUITMENT` 的记录；实习和管理招聘类型在 crawler 内直接丢弃。
7. 列表链接不等于 JD 必然不完整。若官方校招页的数据脚本已经包含完整职责与要求，可以保存完整 JD，但 `link_kind` 仍必须为 `list`，报告按钮只能标为“招聘列表”。

### 4.3 仅 27 届增量分析与评分验收

- 只有确认 27 届岗位进入方向筛选。方向筛选采用 A/B/C 闸门：A 为有直接证据、允许进入 Pro；B 为方向相关但证据不足，只入库展示；C 为明确方向外，不入库。宽泛词“开发、研发、系统、模型、AI、算法”不能单独把岗位升为 A。
- 本地规则先处理明确 A/C，只有模糊 B 档调用 Flash。Flash 输入“标题 + 精简 JD + 结构化候选人证据”，只能把证据充分的岗位升为 A；`learning_targets` 和 `unverified_skills` 不得当作已掌握能力。
- V4-Pro 只分析“确认 27 届 + A 档 + JD 完整 + 尚未按当前配置分析”的岗位。每次和每日数量上限默认均为 `0`（不限），让少量真实新增岗位在同一轮完成；需要控制费用时可将 `max_pro_jobs_per_run` 或 `max_pro_jobs_per_day` 配为正整数。日志会在调用前打印岗位数与最大输出预算。`ALLOW_FULL_PRO_ANALYSIS=1` 可临时忽略配置上限。若个别响应因 1200 Token 截断而无法解析，只重试失败岗位并临时提高该次输出上限，禁止重跑已成功项。
- 分析是否复用由 `analysis_version + JD 指纹 + 用户画像指纹 + 模型` 共同决定；任一项变化才重新分析。
- 匹配分由核心方向、必备技能、项目证据、工程栈和基础条件五项组成，并受证据等级、核心证据数量和核心缺口封顶。模型不能直接决定最终总分。
- 修改筛选规则后必须先离线回放，不调用 API：

  ```powershell
  python scripts/evaluate_screening_gate.py --db data/jobs_rebuild_v2_20260722.db
  ```

  以历史 `match_score >= 60` 为正样本，A 档召回率应至少为 95%，A+B 保留召回率必须为 100%；未达到前不能恢复全量 Pro。
- 全量重建必须先写临时 SQLite，再运行 `scripts/audit_rebuild.py` 检查正式校招过滤、方向过滤、JD 完整性、分析元数据、分项上限和投递记录；阻断项清零后才能替换正式库。
- 数据清理只合并“公司、标题、城市、完整 JD 文本”全部一致的岗位，并迁移最新分析和投递关联。标题与城市相同但 JD 不同的岗位可能属于不同业务线，必须保留。
- 中断后使用 `scripts/resume_rebuild_analysis.py --skip-hydration` 续跑，仅处理尚未完成的完整 JD。

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
- 全量复核使用 `python scripts/audit_job_links.py`：它会对每家公司每种链接类型抽取一个真实 URL，记录可访问、列表页、登录跳转和请求失败的结果到 `outputs/job_link_audit.csv`。详情链接跳到登录、总览或社会招聘时，必须修复 crawler/配置或降级为非详情链接。
- 当前活跃岗位逐条复核使用 `python scripts/audit_active_job_links.py --active-days 3`。该脚本对活跃窗口内每条 URL 分类，按 SPA 网络地址去重请求，并对京东详情 ID 做 API 语义校验，输出 `outputs/active_job_link_audit.{md,csv,json}`。`access_blocked` 不等于失效，应按公司和路由模板用浏览器抽样；`request_failed` 必须用浏览器确认后记录结论。
- 对浏览器可正常打开、但 Requests 因旧 TLS、WAF 或长连接超时失败的已知官网，应归类为 `access_blocked`，不能写成 `request_failed` 或直接删除。华润 `runjob.crc.com.cn` 与拓邦 `campus.topband.com.cn` 属于此类。
- 对官网内容有效、但服务端 TLS 长期不稳定且没有可靠官方 API 的极少数站点，可以增加公司专用的只读文本回退。回退源必须读取同一官方 URL，岗位链接仍指向官网；解析结果必须同时包含明确岗位名、工作职责和任职要求，并通过真实抓取测试后才能进入生产配置。不得把搜索结果摘要或第三方转载直接作为岗位数据。
- 分页实现复核使用 `python scripts/audit_crawler_pagination.py`。它会对全部 `config.yaml` 条目记录 crawler 的翻页策略、每页数量、硬上限和风险提示到 `outputs/crawler_pagination_audit.csv`。API 返回总数/`hasMore` 的 crawler 必须翻到末页；UI 翻页 crawler 必须以“下一页禁用”或重复内容为停止条件，不能以“先抓几页够用”为理由截断。
- API crawler 必须在结束时校验“累计条数 == 官方 total”或已明确收到 `hasMore=false`。字节跳动官方 API 当前总量为 5,691；任一页失败或总量不一致时整家公司本轮结果作废，禁止把部分页写入数据库。

## 8. 全量接入健康审计

每次大批量接入后，以及校招季开始时，运行只读审计：

```powershell
$env:HTTP_PROXY="http://127.0.0.1:7897"; $env:HTTPS_PROXY="http://127.0.0.1:7897"
python scripts/audit_company_integrations.py --workers 8
```

它不会调用 AI、不会写入 SQLite；会逐家公司检查配置入口、生产 crawler 的真实返回、实习/社招过滤结果、27 届/往届分布和一条详情链接，输出 `outputs/company_integration_audit.csv` 与 JSON。重点处理：

- `EMPTY`、`CRAWLER_ERROR`、`FILTERED_ALL`：入口或解析规则失效，必须修复后再运行正式抓取。
- `PREVIOUS_ONLY_REVIEW`：不能直接判定失败，可能只是今年未开招；但若官网已有 27 届岗位，说明当前入口过期或抓错页面，必须重新发现并验证入口。
- `LIST_ONLY`、`DETAIL_REACHABILITY_REVIEW`：岗位可见但直达详情不可用，报告中不得作为“去投递”详情链接展示。

审计结束后，把结论同步到 `outputs/company_integration_status.md`，保留需要复核的公司和原因。

## 9. 当前推荐架构

最稳妥的长期流程是：

1. 普通搜索 / Firecrawl search 找候选入口。
2. Firecrawl scrape 快速看页面和抽岗位候选。
3. 用项目 crawler 和 `validate_company.py` 做最终验收。
4. 通过后写 `config.yaml`。
5. 失败或覆盖结果写入 `outputs/company_integration_status.md`。
6. `python main.py` 正式抓取、过滤、入库、AI 分析和生成报告。
7. 校招季或链接规则变更后运行 `scripts/audit_active_job_links.py`，清理 404、空壳详情、产品/论坛误项，并浏览器复核限流站点。

一句话：Firecrawl 负责加速发现和解析长尾页面，项目 crawler 负责稳定生产抓取，状态文档负责全过程可追踪。
