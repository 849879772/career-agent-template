# 公司招聘接入状态

## 2026-07-27 官方校招活动页届别复核

- 18:40 完成修改后的首次全量正式运行并写入 `data/jobs.db`：10,514 个活跃岗位中确认 2027 届 1,337 个，A 档 682 个、B 档 655 个；当日新增完成 416 条 V4-Pro 分析，库内 743 条分析均为 `complete`。仅同花顺“算法工程师（金融 AI Agent 平台）”因官方来源只有列表页、JD 为空而未调用 Pro；另有 67 个 JD 不完整岗位均为 B 档，不调用 Pro。报告已于 18:40 重新生成；本地未配置 `FEISHU_WEBHOOK`，因此本轮未推送飞书。
- 16:46 增加“腾讯文档27届秋招”受约束兜底并修复 Moka 项目参数、主列表边界和真实分页。腾讯文档31条记录、30家公司全部实抓成功，共抓2,883个原始岗位；排除463个实习/提前批/社招和413个方向外岗位后，2,007个目标岗位中确认2027届1,984个、往届12个、待确认10个、冲突1个。未使用岗位发布时间，未调用 DeepSeek，未写入正式数据库。
- 远景科技固定抓取官网 `2027届应届生` 项目 `100124183`，完整读取6页170/170个岗位；排除方向外岗位后148个目标岗位全部确认2027届，待确认从30降为0。解析器同时排除了右侧“最新职位”中不属于当前项目的侧栏链接。
- 腾讯文档兜底只在官方项目和活动首页均无届别结论时使用，明确2026届、实习、提前批和其他项目优先。原723个待确认减少至10个；剩余为 MiniMax 5、Momenta 4、影石1，均因同站存在已标届别项目，未把腾讯文档证据扩散到另一个未标项目。普渡机器人仍有1个岗位字段冲突。
- Moka 完整分页还补回了此前首屏遗漏：文远知行抓取137个、微步在线49个、思特威37个、远景科技170个；任何中途分页失败都会丢弃该公司的部分结果，避免误判完整抓取。

- 16:09 按“岗位列表 2027 项目优先、无项目时继承 2027 活动首页、所有明确实习继续排除”的新规则重新读取腾讯文档并实抓全部 30 家公司。31 条来源记录均已覆盖，30/30 家爬虫成功返回岗位。
- 本轮共抓到 2,620 个原始岗位；排除 412 个实习/提前批/社招和 387 个方向外岗位后，剩余 1,821 个目标方向岗位：确认 2027 届 1,087 个、确认往届 10 个、待确认 723 个、冲突 1 个。本轮仅规则核验，未写入正式数据库、未调用 DeepSeek。
- MiniMax 完整翻页抓到 82 个岗位；59 个明确非正式岗位被排除，23 个目标岗位中确认 2027 届 17 个、2025 届 1 个、待确认 5 个。5 个标题写 2027 但卡片用工类型明确为“实习”的算法岗位继续排除，符合“除开实习”的要求。
- 新规则解决或扩大确认范围的主要公司包括：大疆 121、OPPO 95、小鹏汽车 260、影石 151、汇川技术 114、百度 114、文远知行 24、合合信息 9、MiniMax 17、Momenta 8。仍待确认的 723 个集中在官网和岗位列表均未出现 2027 正式项目证据的公司，不能仅凭腾讯文档标签强行提升。
- 机器可读复核结果：`outputs/tencent_docs_cohort_recheck_after_rules_20260727.json`；公司活动页证据：`outputs/tencent_docs_campaign_evidence_after_rules_20260727.json`。

- 届别判断改为“公司活动页证据 + 岗位字段证据”两层：优先检查 `campaign_url`，未配置时检查 `careers_url`；静态请求无法取得活动标题时再用 Playwright 渲染。
- 公司活动页只要明确且仅有一个正式校招年份，就允许无项目年份的非实习岗位继承；其他年份若只属于实习不构成冲突。多个正式年份仍保持待确认，项目制页面只确认归属于对应年份项目的岗位。
- 腾讯文档 29 家公司已重新核验，共涉及 855 个目标方向岗位：确认 2027 届 438 个、确认往届 2 个、冲突 1 个、仍待确认 414 个。20 家至少有一个确认 2027 届目标岗位。
- 官方活动页已直接识别：大疆、百度、基恩士为 2027 活动；Momenta、搜狐畅游和 MiniMax 均识别到 2027 正式项目，同时存在的日常实习、暑期实习或 2028 实习不再把正式 2027 项目标成冲突。
- 京东官网 JD 使用“2026 年 10 月 1 日至 2027 年 9 月 30 日期间毕业”表达，新增毕业区间规则后 17 个相关岗位全部确认成 2027 届。日期、页脚版权年份、结果数量和员工故事不会被当作届别证据。
- 本轮只做确定性规则复核，没有调用 DeepSeek。证据明细见 `outputs/tencent_docs_campaign_evidence_20260727.json`。

更新时间：2026-07-27

## 2026-07-26 届别证据与分析闸门升级

- 抓取流程改为先检查官方岗位字段和公司校招入口，再决定届别；只有有官方证据确认的 27 届岗位会补全 JD、执行方向分级和 V4-Pro 匹配评分。
- 正式库 3,987 个岗位已迁移为：确认 27 届 627、确认往届 420、届别待确认 2,940。未知届别不会再混入 27 届主页，而是在独立导航中展示判断依据。
- 627 个确认 27 届岗位的 JD 全部完整；保留 327 条有效评分。已清除 1,616 条非确认 27 届历史评分，非 27 届违规评分、JD 不完整违规评分和非 27 届残留筛选分级均为 0。
- 入口复核按公司去重访问，不逐岗位补 JD。仅某个岗位写“27 届”不会推断同公司其他岗位的届别；入口无明确年份或同时出现多个年份时保持待确认。
- 数据库备份：`data/jobs.db.bak_before_cohort_gate_20260726_210555`。验收报告：`outputs/cohort_pipeline_audit_20260726.md`；机器可读结果：`outputs/cohort_pipeline_audit_20260726.json`。

更新日期：2026-07-26

## 2026-07-25 腾讯文档实时同步与 5 家后置复核

- 16:24 再次读取腾讯文档正式秋招表：当前 **30 条记录、29 家去重公司，配置覆盖 30/30，待接入 0**。新增别名将“柠檬微趣-下周官宣”稳定归一化为“柠檬微趣”。
- 柠檬微趣此前已有一条无法返回岗位的旧官网静态页，并非真正可用接入；现已删除旧入口，切换到官方 Moka 项目 `microfunhr/36717`。实跑原始 30 个岗位，经过实习/社招、方向和 A/B/C 闸门后入库 **8** 个，其中 5 个 JD 完整、4 个 A 档完成 Pro 分析。
- 网易互娱旧 `game.campus.163.com/position` 通用渲染配置返回 0。通过官网“应届生 → 网易互娱27届校园招聘”菜单和网络请求定位当前正式项目 `id=102`，改用 NetEase 官方 API 完整抓取 **56** 个岗位，最终入库 **17** 个 C++、游戏引擎、AI、Agent、测试等目标岗位，全部 JD 完整，11 个 A 档完成 Pro 分析。
- 埃科光电旧配置只停留在首页，未进入真实职位列表。新增专用 crawler，遍历 `/front.home.index/schoolList` 两页共 **14** 个岗位，并逐个读取详情页职责和要求。官网明确标注“招聘类型：校园招聘”的博士岗不再因标题含“高级”而被误判为社招；方向分级后最终入库 **7** 个岗位，全部 JD 完整，其中 5 个 A 档完成 Pro 分析、2 个 B 档保留展示。
- 基恩士实跑 2 个正式岗位，仅“校园大使”和销售；学而思实跑 17 个岗位，正式部分均为教师方向；搜狐畅游实跑 29 个岗位，9 个正式岗位均为策划、运营、营销、战略或普通数据分析。三家公司当前目标岗位为 0 属于正确过滤，不是漏抓。
- 方向过滤新增英文 Product Manager、游戏策划/设计/运营、纯美术制作、策划管培生、普通数据分析和技术型销售等明确非目标角色，避免游戏公司业务词把非技术岗位误放入库。
- 本轮定向处理共新增 **32** 个岗位；柠檬微趣、网易互娱和埃科光电当前合计 32 个入库岗位，其中 29 个 JD 完整、20 个 A 档已完成 Pro 分析。正式库现有 **3,821** 个岗位、3,737 个完整 JD、1,912 条分析，覆盖 274 家有目标岗位的公司。
- 修复了 B 档分析清理规则：持久化为 B、但因完整 JD 命中本地强证据而升级为 A 的岗位不会再被误清理；误删的 100 条有效分析已从本轮操作前备份恢复，无需重新消耗 Token。
- 最终验收通过：实习、提前批、社招、方向外、缺 JD 评分、完整 A 档漏分析与异常链接均为 0。测试 **225 passed**。报告见 `outputs/final_acceptance_20260725_qqdocs_sync2/rebuild_audit.md`，链接见 `outputs/active_job_link_audit_20260725_qqdocs_sync2.md`，质量清单见 `outputs/formal_quality_issues_20260725_qqdocs_sync2.md`。

更新日期：2026-07-25

## 2026-07-25 全量修复最终验收

- `config.yaml` 已从 471 条入口收敛为 **466 条入口、464 家公司**。大华、淘天、零跑、中科创达和锐捷的冗余入口已移除；旷视与图森各保留两个入口，因为实跑岗位 ID 集合证明它们对应不同招聘项目。
- 正式库现有 **3,789** 个岗位，覆盖 **271** 家有目标方向岗位的公司；**3,708** 条 JD 完整、**81** 条待补全。待补全项包括 33 条列表页、45 条详情正文抽取失败和 3 条官网明确不提供正文；45 条详情已再次逐页渲染重试，均仍受 WAF、动态接口或官网空正文限制。待补全项中明确 27 届岗位为 **0**，不完整 JD 均不会进入 Pro 分析。
- 已合并 **11** 组“同公司、同标题、同城市且完整 JD 完全一致”的岗位，迁移每组最新分析并保留投递数据。当前完全重复 JD、重复 URL、C 档入库、缺 JD 评分、完整 A 档漏分析均为 **0**；剩余 2 组同名同城岗位的 JD 明显不同，按真实独立岗位保留。
- 字节跳动已改用官方 API 按总数完整翻页：接口总量 5,691，正式校招 215，方向筛选后入库 188。腾讯青云改用详情字段并清理 23 个官方已下线岗位。
- 同程旅行已从 2019 旧入口切换到当前官方校招门户；官网目前为 0 个在招岗位，旧库 7 个失效岗位已清理。bilibili 的 8 个岗位已恢复真实详情路由；数字绿土的失效详情域名已改为可打开的官方 51job 校招列表，同时保留页面脚本中的完整 JD。
- 活跃岗位链接复核结果：**3,634** 条可达详情、**40** 条可达列表、**115** 条访问受限、请求失败 **0**。访问受限集中在奇瑞、中国兵器工业集团等 WAF/限流站点，已与坏链接分开记录。
- 正式校招内容复核确认实习、提前批、社招和方向外岗位均为 **0**；317 条仅提及“实习经历”的正式岗位和 183 条专项人才计划经规则复核后保留。
- 最终验收：`outputs/final_acceptance_20260725_fixed2/rebuild_audit.md`；链接明细：`outputs/active_job_link_audit_20260725_final_fixed2.md`；质量清单：`outputs/formal_quality_issues_20260725_final_fixed2.md`。测试结果为 **222 passed**。

更新日期：2026-07-25

## 2026-07-25 V2 重建库正式启用

- 已将通过验收的 `data/jobs_rebuild_v2_20260722.db` 写入正式 `data/jobs.db`；正式库现有 **5,686** 个岗位和 **3,379** 条完整匹配分析，`integrity_check` 为 `ok`。
- 迁移时把 `last_seen_at` 刷新到启用日期，但保留原始 `crawled_at`，避免整库被误判为“今日新增”；管理页面当前可展示 **4,193** 条活跃且非 C 档/非重复列表岗位。
- 原正式库备份为 `data/jobs.db.bak_before_rebuild_v2_promotion_20260725_003051`。
- `data/applications.json` 的 14 条投递记录全部保留：5 条按“公司 + 岗位名”安全映射到新岗位 ID，9 条在重建库中已无对应岗位，已解除 `job_id` 关联并继续作为手工投递卡片保存，避免错绑。
- 正式库复审继续通过：非正式校招、方向外岗位、异常外链、缺 JD 评分、分析元数据错误、评分规则错误和完整 A 档未分析均为 **0**。

更新日期：2026-07-25

## 2026-07-24 Hotjob JD 补全与 V2 重建验收完成

- 对 **68** 条“标题为 A 档但 JD 不完整”的优先岗位执行详情补全：Hotjob、飞书、北森和腾讯分别调用官方详情接口，普通详情页才回退渲染。
- Hotjob 已确认列表 fragment 是真实 `postId`，共享 crawler 现调用 `listPositionDetail` 获取 `workContent/serviceCondition`，并生成可直达 `posDetail.html` 的岗位链接。本轮由此补全 **61** 条；数字绿土另有 **2** 条从误接社招页校正为正式校招完整 JD。
- 腾讯 **1** 条已下架、创维 **2** 条招聘关闭、南京巨鲨 **1** 条已不在当前北森 API，均从临时重建库移除。其域创新 **1** 条仍在线，但官方飞书详情对象不含职责/要求，因此保留为 JD 待补全且禁止调用 Pro。
- 最终新增完成 **63** 条 V4-Pro 分析；其中 2 条首次响应被 1200 Token 输出上限截断，只对失败项以 1800 Token 重试成功。未重算此前已完成分析。
- 临时库现有 **5,686** 个岗位、**4,278** 条完整 JD、**1,408** 条待补全、**3,379** 条已分析，覆盖 **280** 家有岗位公司。验收确认非正式校招、方向外岗位、异常外链、缺 JD 评分、分析元数据错误、评分规则错误和“完整 A 档未分析”均为 **0**。
- 验收报告：`outputs/rebuild_v2_20260722/rebuild_audit.md`；正式 `data/jobs.db` 与现有投递记录尚未在本次补全过程中替换。

更新日期：2026-07-24

## 2026-07-22 匹配评分 V2 全量重建（已由 2026-07-24 续跑完成）

- 已从空白临时数据库完成 481 条生产来源抓取与方向粗筛，清洗后保留 **5,695** 个岗位，覆盖 **280** 家有目标方向岗位的公司；公司、岗位、城市组成的逻辑重复组为 **0**。
- 详情 API 与页面补全后，**4,215** 个岗位具有可评分的完整 JD，**1,480** 个列表摘要/来源空正文岗位保留为待补全且不调用 Pro。二次过滤清理 21 个实习/当前到岗实习岗位、19 个方向外岗位，并移除 AMD 导航项和影石短链重复项。
- 当时已有 **3,011** 个岗位通过 V4-Pro 证据化评分，DeepSeek 余额耗尽后中断；后续续跑和 JD 补全结果见上方 2026-07-24 记录。
- 飞书详情 URL 现在统一去除 `share_token`；静态和通用渲染 crawler 会拒绝 YouTube、LinkedIn、微博等非岗位外链。配置删除重复/无效的 `影石Insta360(未官宣)`、`实习僧AMD`、`实习僧momenta` 和 `实习僧小鹏` 来源。
- 临时验收报告：`outputs/rebuild_v2_20260722/rebuild_audit.md`。充值后续跑只分析剩余岗位，阻断项归零后再清空正式投递记录并替换数据库。

更新日期：2026-07-22

## 2026-07-22 实习与提前批全库详细筛查

- 筛查清理前数据库共有 **10,459** 个岗位，近三日活跃 **6,895** 个。逐岗位检查标题、招聘类型、URL、页面元数据、完整正文和实习周期要求后，活跃岗位中确认 **191 个实习岗**、**311 个提前批岗位**；全库历史分别为 **272** 和 **329** 个，二者无重叠。
- 实习漏项主要来自 OPPO“寻梦实习招聘”、蔚来/58/MiniMax 等页面头部的“实习”标签、阿里/淘天“实习生专项招聘”、东风“实习生”元数据、马上消费“实习薪酬津贴”，以及连续实习时长和英文 internship 要求。原规则只看标题和少数项目词，无法覆盖这些表达。
- 另有 **117** 个活跃岗位仅写“有实习经历/项目经验者优先”等加分项，已逐类复核并保留；**259** 个青云、TOP Talent、Super Sparks 等专项计划未标注实习或提前批，也继续保留。奇瑞“研发见习生”要求正常取得毕业证、学位证，按正式校招保留。
- 已备份 `data/jobs.db.bak_before_intern_early_cleanup_20260722_100120`，随后清理 **601** 个实习/提前批历史岗位及分析。清理后全库 **9,858** 个、近三日活跃入库记录 **6,393** 个；报告按详情优先规则隐藏 6 个重复列表项后展示 **6,387** 个，其中 27 届主页面 **4,763** 个、往届页面 **1,615** 个，另有 9 个分析/链接异常项隐藏。复查确认实习与提前批均为 **0**。
- `实习僧特斯拉` 只指向 Tesla internship 专区，已从生产配置移除；`亿联网络提前批` 实为普通校园招聘入口，已更名为 `亿联网络`，其 24 个正式岗位保留。
- 清理前逐岗位结果：`outputs/formal_campus_content_audit_20260722.{md,csv,json}`；清理后零残留复查：`outputs/formal_campus_content_audit_20260722_after_cleanup.{md,csv,json}`。后续抓取在入库前执行同一过滤，报告层再次兜底。

更新日期：2026-07-22

## 2026-07-22 云端结果下拉与质量检查

- 腾讯文档前置检查新发现并自动验证接入 `Dexmal 原力灵机`，官方飞书入口真实返回 16 个明确 27 届岗位；配置已同步到本地。
- 云端 7 月 21–22 日产生 106 条新数据库记录。质量复核拦截 10 条京东 `type=internship` 实习岗位、7 条方向外/导航项，以及 7 条仍使用旧美团详情路由的记录；其余有效增量按 URL 合并到本地并保留云端分析。
- 京东生产 crawler 已限定为 `present` 与 `talent` 正式校招轨道，实习判断新增 URL 兜底。通用渲染器新增“开发者区域”导航过滤，方向过滤新增校园大使、生态合作、商品开发、产品培训生、营销活动和游戏任务策划等明确非目标岗位。
- 云端仍保留本地已于 7 月 20 日移除的当当网 2022 过期专题，这是因为本地修复尚未推送，并非本次腾讯文档重新接入。本地继续排除该入口，自动接入增加已知过期来源阻断。

更新日期：2026-07-22

## 2026-07-20 当前活跃岗位链接全量审计

- 已逐条审计最近 3 天活跃的 **6,854** 个岗位链接，覆盖 **300** 家公司。结果为：5,401 条可直达岗位详情、1,244 条可打开官方招聘列表、207 条北森详情在批量请求中返回 429，但中国兵器工业集团与奇瑞的代表岗位均已在浏览器确认标题、职责和任职资格正常。
- 美团旧 crawler 使用已失效的筛选字段并生成错误详情路由，曾混入社招/实习且打开 404。现改为官网 `jobType=1` 正式校招接口与 `/web/position/detail?jobUnionId=...&highlightType=campus` 详情路由，实时返回 68 个正式校招岗位；数据库保留并迁移 63 个现有正式岗位，清理 1,603 个非正式或错误历史行。
- 京东官网接口已改为 0 起始分页，默认查询必须传空 `planIdList`。修复后实时返回 49 个正式项目岗位（应届生 16、TGT 人才 33）；14 个仍在招的历史岗位保留分析并迁移到当前 ID，55 个详情 API 已返回空岗位的旧行已清理。新出现岗位留待下一轮正式流程按方向筛选和增量分析。
- 华沿机器人（原大族机器人）已从 404 的 `hansrobot.com/join.html` 切换到当前校园招聘页，三页均已访问，当前有效岗位集中在第 1 页，共 6 个且含完整职责要求；第 2、3 页官网当前为空。
- 已清理德明利“主控研发”产品导航、昂瑞微“开发者论坛”、统信 UOS 开发者平台和统信社招误项。统信现返回 8 个校园详情页；昂瑞微现返回 14 个校园列表岗位。数字绿土的 7 个拒绝公开访问的详情地址统一回退到可打开的官方 51job 招聘列表。
- 当当网旧 2022 专题只误抓到发票补开入口，已从生产配置移除。拓邦股份和华润集团的官方列表无法被 Requests 稳定访问，但均已在真实浏览器中确认能打开岗位列表/搜索页，不作为坏链接清理。
- 累计报告已改为只展示最近 3 天活跃岗位，历史行继续保存在 SQLite 但不再永久出现在主页。重建后主页显示 6,848 个岗位，均已有分析；已确认旧美团 404、数字绿土失效详情域名、旧大族链接及上述导航误项在生成 HTML 中均为 0 次出现。
- 完整结果：`outputs/active_job_link_audit_20260720.md`；数据库清理前备份：`data/jobs.db.bak_before_verified_link_cleanup_20260720_172038`。

更新日期：2026-07-20

## 2026-07-17 腾讯文档与云端结果校准

- 今日腾讯文档识别出 20 家 `27届秋招` 公司，配置覆盖率为 20/20；按云端实际抓取结果校准后，17 家正常刷新、同花顺抓取不完整、基恩士云端返回 0、学而思因岗位均为教师方向而正确不入主岗位库。
- 同花顺本地实时复跑返回 29 个岗位，云端只刷新 1 个，确认通用渲染 crawler 在 CI 中存在完整性问题。
- 基恩士本地实时复跑返回 2 个 2027 校招岗位，云端本轮未刷新，需增加失败重试和后置告警。
- 今日云端新增 107 个岗位，但仅 48 个完成 AI 分析；北汽集团新增的 59 个岗位均未分析，暂不出现在“今日新增”页面，下次运行会自动重试。
- 详细校准结果见 `outputs/qq_docs_27_autumn_calibration_20260717.md`。

更新日期：2026-07-17

## 2026-07-16 腾讯文档与云端抓取差集复核

- 腾讯文档正式秋招工作表已从旧监控地址纠正为 `tab=t0gmEC`；旧 `BB08J2` 实际是“实习内推汇总”，会让前置监控错误返回 0 条。
- 今日“秋招内推汇总”解析出 19 家带精确 `27届秋招` 标签的公司，名称归一化后 19 家均已在 `config.yaml` 覆盖。新增别名：卓驭、思特威、文远知行的腾讯文档活动名称。
- 相比 2026-07-14 的 13 家，新增关注 OPPO、元戎启行、卓驭、文远知行、智元机器人、网易雷火。已删除元戎启行旧 Moka 项目 `6487` 的重复配置，保留当前项目 `145894`。
- 19 家真实在线审计共返回 1,608 条正式岗位；18 家原 crawler 可返回岗位。学而思 17 条均为教师方向，正确由方向粗筛阻止入主岗位库。
- 网易雷火是确认漏抓：旧 crawler 固定请求过期项目 `72`，返回 0；已切换到 27 届正式校招项目 `77`，并使用 API 提供的官方详情链接。修复后抓到 53 条明确 `2027届应届毕业生` 全职岗位。
- 以 07:28 云端数据库为基准，上午官网还出现同花顺 4 条、小鹏汽车 3 条、智元机器人 6 条和网易雷火至少 7 条高度相关未入库岗位；同花顺另有 9 条已命中相关粗筛缓存。它们应在部署修复后的下一轮主流程中增量入库和分析。

更新日期：2026-07-16

## 2026-07-13 腾讯文档 27 届秋招前置试运行

来源：`27届校招秋招实习内推合集` 的“秋招实习内推汇总”表。已从公开智能表格解析出公司名、招聘类型标签和真实投递链接，并新增每日运行前的只读核对脚本 `scripts/qq_docs_27_autumn_monitor.py`。

- 已覆盖并待主流程复核：科大讯飞、汇川技术、小鹏汽车、基恩士、大疆、京东、百度；远景能源由已有“远景科技 / EnvisionGroup”Moka 校招入口覆盖。
- 本次验证后新增并接入：微步在线（Moka，35 个岗位）、思特威（Moka，30 个岗位）、MiniMax（飞书，76 个岗位）、同花顺（官方校招页，19 个岗位）。
- 学而思：已于 2026-07-14 接入并完成真实抓取。官网有多条 `27秋招` 正式教师岗位；它们会进入抓取与岗位级过滤，但因均不属于当前技术方向而不写入主岗位库。
- MiniMax 来源同时带有 `27届暑期实习` 标签。已接入其官方飞书招聘页，但主流程仍会在入库前按岗位项目/标题过滤实习岗位；不能把来源标签本身当作正式岗证明。
- 复核修复：科大讯飞旧北森入口固定在默认分类 `campus/jobs`，实际返回 0 岗；腾讯文档来源指向“飞凡计划”分类 `/5/jobs`。已扩展通用北森 crawler 以保留并请求 URL 中的分类号，配置已切换为该入口。

更新日期：2026-07-13

## 2026-07-13 全量健康审计

已对 `config.yaml` 的 540 条配置完成只读复核（其中 521 个独立公司名称，存在历史别名/重复项），过程不调用 AI、不写入岗位数据库。详细结果见 `outputs/company_integration_audit.csv`（同目录 JSON 可供程序读取）。

- `HEALTHY`：66 家，能抓到正式岗位、明确有 27 届或满足详情抽样检查。
- `COHORT_UNKNOWN`：131 家，能抓到正式岗位但页面未明确届别，校招季应复查。
- `PREVIOUS_ONLY_REVIEW`：143 家，只抓到明确往届岗位；若官网已有 27 届，必须重新发现当前校招入口，汇川技术此前即属于这一类风险。
- `LIST_ONLY`：38 家，有岗位但没有可直达详情链接，报告不能把它们展示成“去投递”。
- `EMPTY`：141 家、`FILTERED_ALL`：19 家，分别表示 crawler 没有返回岗位或岗位均被实习/社招规则过滤，需重接、修复或移出有效抓取名单。
- `DETAIL_REACHABILITY_REVIEW`：2 家，样本详情链接无法确认可直接打开。

后续接入或修改入口后，必须复跑 `python scripts/audit_company_integrations.py --workers 8`，并更新本节和具体公司状态；不能再只因“配置存在”就标为接入成功。

## 2026-07-13 链接与分页复核

- OPPO 的 43 条历史岗位链接原为 `campus/post?id=<ID>`，会打开岗位总览；已改为官网真实详情路由 `campus/post/<ID>`，并完成数据库迁移。
- `outputs/job_link_audit.csv` 对 418 个公司/链接类型样本复核：296 条 HTTP 可达、110 条已识别为列表链接、5 条登录跳转、7 条请求异常。HTTP 可达仅表示路由可访问，不能替代页面语义复核。
- `outputs/crawler_pagination_audit.csv` 覆盖 540 条配置：46 条采用 API 总数/`hasMore` 翻页、354 条采用 UI 或启发式翻页、140 条为单响应/静态页。已移除字节跳动“只抓前 5 页”、宇树“只取前 50 条”、飞书默认 10 页和北森 50 页的截断；单响应/静态页仍需按官网结构逐站确认是否有隐藏分页。

## 2026-07-13 公司来源去重

按“同 crawler 且同一规范化官方入口”清理重复来源：`config.yaml` 从 540 条降为 483 条，移除大小写别名、实习/内推备注、简称和同一入口的重复公司项。数据库中对应岗位公司名已迁移，当前不存在大小写重复公司名；公司排行中的 OPPO、SHEIN、TCL 等只会各显示一行。

去重不使用模糊名称匹配，因此不同官方入口的子公司或独立招聘项目会保留，避免误合并。

## 汇总

- 来源 Excel 投递记录：1967 行。
- 归一化后的公司候选项：920 项。
- 已新增到 `config.yaml`：143 家。
- 已被当前配置覆盖：399 项。
- 未接入 / 需要继续查找或验证链接：70 项。
- 已找到链接但不能直接作为抓取入口：192 项。

## 已新增并接入

| 公司 | 爬虫 | 抓取入口 |
| 广立微 | `moka` | https://app.mokahr.com/campus-recruitment/semitronix/140043 |
| 数字绿土 | `greenvalley` | https://campus.51job.com/greenvalley/san.html（解析 `js/xz.js`，仅保留 `CAMPUSRECRUITMENT` 正式校招） |
| 航嘉集团 | `beisen` | https://hr.huntkey.com/campus/jobs |
| 诺瓦星云 | `beisen` | https://novastar.zhiye.com/campus/jobs |
| 知象光电 | `static_html` | https://hr.revopoint3d.com.cn/gwtd.html |
| 中国航信 | `static_html` | https://www.travelsky.cn/travelsky/rlzy/rczp/xyzp/A069009003001Gone1.html |
| --- | --- | --- |
| 盛科通信 | `beisen` | https://centec.zhiye.com/campus/jobs |
| 统信软件 | `static_html` | https://uniontech.com/m/Recruitment.html |
| 芯行纪 | `xtimes` | https://www.xtimes-da.com/index.php/Mobile?a=page&p=joinus_school |
| 深圳景旺电子 | `static_html` | https://www.kinwong.com/careers/ |
| 华虹集团 | `moka` | https://app.mokahr.com/campus-recruitment/huahong/78009#/ |
| 德明利 | `static_html` | https://www.twsc.com.cn/job/index.html |
| 大族机器人（现华沿机器人） | `huayan` | https://www.huayan-robotics.com/about-us/talent-recruitment?type=60 |
| 裕太微电子 | `static_html` | https://www.motor-comm.com/join/campus-recruitment |
| itc | `render` | https://hr.itc.vip/job/school.html |
| 依图 | `render` | https://www.yitutech.com/cn/join-us |
| 东莞新能源科技 | `hotjob` | https://wecruit.hotjob.cn/SU612e24992f9d247d0f41930e/pb/school.html |
| 中航国际-深南电路 | `beisen` | https://avicsz.zhiye.com/campus/jobs |
| 乐动机器人 | `beisen` | https://ldrobot.zhiye.com/campus/jobs |
| 北京全路通信信号研究设计院 | `beisen` | https://crscd.zhiye.com/campus/jobs |
| 半岛医疗 | `beisen` | https://peninsulalaser.zhiye.com/campus/jobs |
| 华睿科技 | `beisen` | https://irayple.zhiye.com/campus/jobs |
| 壁仞科技 | `moka` | https://app.mokahr.com/campus-recruitment/biren/44727 |
| 大族激光 | `moka` | https://app.mokahr.com/campus-recruitment/hanslaser/46383 |
| 广电运通 | `moka` | https://app.mokahr.com/campus-recruitment/grgbanking/39448 |
| 影石 | `feishu` | https://arashivision.jobs.feishu.cn/campus |
| 德赛西威 | `feishu` | https://yesv-desaysv.jobs.feishu.cn/campus |
| 成都鼎桥通信 | `beisen` | https://td-tech.zhiye.com/campus/jobs |
| 捷顺科技 | `beisen` | https://jieshun.zhiye.com/campus/jobs |
| 新兴产业投资 | `beisen` | https://dggmt.zhiye.com/campus/jobs |
| 江淮汽车 | `beisen` | https://jac.zhiye.com/campus/jobs |
| 江铃汽车 | `beisen` | https://jmc.zhiye.com/campus/jobs |
| 洲明科技 | `beisen` | https://unilumin.zhiye.com/campus/jobs |
| 浙江中控技术 | `moka` | https://app.mokahr.com/campus-recruitment/supcon/148189 |
| 元戎启行 | `moka` | https://app.mokahr.com/campus-recruitment/deeproute/145894 |
| 深圳康冠科技 | `beisen` | https://careerktc.zhiye.com/campus/jobs |
| 维谛技术 | `moka` | https://app.mokahr.com/campus-recruitment/vertiv/118713 |
| 绿盟科技 | `moka` | https://app.mokahr.com/campus_apply/nsfocus/29118 |
| 羚控科技 | `beisen` | https://lyncon.zhiye.com/campus/jobs |
| 诺瓦星云 | `beisen` | https://novastar.zhiye.com/campus/jobs |
| 豪鹏科技 | `hotjob` | https://wecruit.hotjob.cn/SU611e3a2c2f9d24229e05a18d/pb/school.html |
| 领益智造 | `hotjob` | https://wecruit.hotjob.cn/SU600fcd2b5d83dc11e4a581b3/pb/school.html |
| 鼎阳科技 | `beisen` | https://siglent.zhiye.com/campus/jobs |
| 中国电子 | `render` | https://campus.cec.com.cn/collection |
| 国家开发投资集团 | `render` | https://sdic1.iguopin.com/jobCampus |
| 希望森兰 | `render` | https://www.chinavvvf.com/list-28-1.html |
| 拓邦股份 | `render` | https://campus.topband.com.cn/company/tuobang/tuobang5011161#/positionList?wt=1&keyword= |
| 智微智能 | `render` | http://hr.jwipc.com:9007/hcm/portal.aspx |
| 深科技 | `render` | https://zhaopin.kaifa.cn/Campus/Positions |
| 砺算科技 | `render` | https://www.lisuantech.com/join-us/school.html |
| 豹趣科技 | `render` | https://www.cheetahfun.com/campus.html |
| 长城汽车 | `render` | https://zhaopin.gwm.cn/SU64eeb4ff1eb80519a80a074c/pb/school.html |
| UCloud优刻得 | `beisen` | https://ucloud.zhiye.com/campus/jobs |
| MPS芯源系统 | `render` | https://www.monolithicpower.cn/cn/about-mps/careers/cn-hire.html |
| 三一集团 | `beisen` | https://sany.zhiye.com/campus/jobs |
| 龙旗科技 | `beisen` | https://longcheerzp1.zhiye.com/campus/jobs |
| 中兴通讯 | `render` | https://job.zte.com.cn/cn/campus-recruitment/Recruitment_positions/freshstudent.html |
| 中元汇吉 | `beisen` | https://zybio.zhiye.com/campus/jobs |
| 中国中车 | `hotjob` | https://crrc.hotjob.cn/SU64d47c466202cc36e27a52d4/pb/school.html |
| 中国联通 | `render` | https://zglt.iguopin.com/job |
| 中国兵器工业集团 | `beisen` | https://norincogroupzhaopin.zhiye.com/campus/jobs |
| 中国网安三十所 | `moka` | https://app.mokahr.com/campus_apply/cetc30/36270 |
| 中科创达 | `feishu` | https://thundersoft.jobs.feishu.cn/campus |
| 云圣智能 | `beisen` | https://ikingtec.zhiye.com/campus/jobs |
| 比特大陆 | `render` | https://jobs.bitmain.com.cn/students |
| 埃科光电 | `render` | http://career.i-tek.cn/ |
| 零跑汽车 | `beisen` | https://leapmotor1.zhiye.com/campus/jobs |
| 数字绿土 | `greenvalley` | https://campus.51job.com/greenvalley/san.html |
| 芯动科技 | `beisen` | https://innosilicon.zhiye.com/campus/jobs |
| 海能达 | `render` | https://zpxz.hytera.com/ |
| 正运动技术 | `render` | https://www.zmotion.com.cn/hire.html |
| 同有科技 | `render` | https://www.toyou.com.cn/Tongyou/ShoolJoin/ |
| 佰维存储 | `beisen` | https://biwin1.zhiye.com/campus/jobs |
| 同程旅行 | `render` | https://promotion.elong.com/index/cn/campus/yjszp.html?type=zpgw |
| 易思维 | `beisen` | https://isv-tech.zhiye.com/campus/jobs |
| 昂瑞微 | `static_html` | https://www.onmicro.com.cn/xyzp/230.html |
| 泰凌微电子 | `render` | https://telink.m.zhiye.com/#/jobs?jc=2 |
| 华中数控 | `beisen` | https://hzncc.zhiye.com/campus/jobs |
| 华大集团 | `beisen` | https://genomics.zhiye.com/campus/jobs |
| 北方华创 | `render` | https://www.naura.com/join/index.html |
| B站 | `bilibili` | https://jobs.bilibili.com/campus/positions |
| 东方电气 | `render` | https://dec2026.iguopin.com/job |
| 中国汽研 | `render` | https://www.caeri.com.cn/zgqy/jrwm/rczp/xyzp/ |
| 中冶赛迪 | `render` | https://campus.51job.com/cisdi/job.html |
| 中科曙光 | `beisen` | https://sugon.zhiye.com/campus/jobs |
| 九州科技 | `render` | https://www.jiuzhoutech.com/cn/xyrsnews.asp |
| 人大金仓 | `moka` | https://app.mokahr.com/campus-recruitment/kingbase/47259 |
| 亿联网络 | `beisen` | https://yealink.zhiye.com/campus/jobs |
| 北汽集团 | `beisen` | https://baicgroup.zhiye.com/campus/jobs |
| 南芯科技 | `beisen` | https://nanxin.zhiye.com/campus/jobs |
| 卡尔动力 | `feishu` | https://kargobot.jobs.feishu.cn/267069 |
| 吉祥腾达 | `beisen` | https://tenda.zhiye.com/campus/jobs |
| 广汽集团 | `beisen` | https://gacrnd.zhiye.com/campus/jobs |
| 开立医疗 | `moka` | https://app.mokahr.com/campus-recruitment/sonoscape/94392 |
| 摩尔线程 | `beisen` | https://mthreads.zhiye.com/campus/jobs |
| 新易盛 | `beisen` | https://eoptolink.zhiye.com/campus/jobs |
| 晶晨半导体 | `beisen` | https://amlogicsh.zhiye.com/campus/jobs |
| 智洋创新 | `render` | https://webapp.zhaopin.com/2025/hd/zycxk0828ZL85636/post/index.html |
| 拼多多 | `render` | https://careers.pddglobalhr.com/campus/grad |
| 延锋 | `moka` | https://app.mokahr.com/m/campus-recruitment/yanfeng/45086 |
| 康尼机电 | `render` | https://campus.51job.com/kangni2000/about.html |
| 德州仪器 | `moka` | https://app.mokahr.com/su/vjlqkz |
| 思朗科技 | `feishu` | https://smartlogictech.jobs.feishu.cn/s/ike2Mj9x |
| 深开鸿 | `render` | https://www.kaihong.com/xyzp |
| 石头科技 | `beisen` | https://roborock.zhiye.com/campus/jobs |
| 联影医疗 | `beisen` | https://united-imaging.zhiye.com/campus/jobs |
| 芯原股份 | `render` | https://campus.51job.com/VeriSilicon2026 |
| 紫光同创 | `render` | https://www.pangomicro.com/join_school/ |
| 舜宇集团 | `moka` | https://app.mokahr.com/m/campus_apply/sunnyoptical/45602 |
| 米哈游 | `mihoyo` | https://jobs.mihoyo.com/ |
| 豪威集团 | `beisen` | https://ovt-omnivision.zhiye.com/campus/jobs |
| 长安汽车 | `beisen` | https://changan.zhiye.com/campus/jobs |
| 长江存储 | `beisen` | https://ymtc-campus.zhiye.com |
| 高新兴 | `beisen` | https://gosuncn.zhiye.com/campus/jobs |
| 顶点软件 | `hotjob` | https://wecruit.hotjob.cn/SU62d669e0bef57c0f7dbabacf/pb/school.html |
| 鼎桥通讯 | `beisen` | https://td-tech.zhiye.com/campus/jobs |
| 爱瑞无线 | `moka` | https://app.mokahr.com/su/chumxr |
| 珞石机器人 | `render` | https://app135149.eapps.dingtalkcloud.com/su/YMZMF |
| 电科莱斯 | `moka` | https://app.mokahr.com/campus_apply/cetcles/40889 |
| 星网锐捷 | `beisen` | https://starnet.zhiye.com/campus/jobs |
| 神驰机电 | `beisen` | https://senci.zhiye.com/campus/jobs |
| 信步科技 | `render` | https://www.seavo.com/career/campus/jobs |
| 南京巨鲨 | `beisen` | https://jusha.zhiye.com/campus/jobs |
| 先临三维 | `beisen` | https://shining3d.zhiye.com/campus/jobs |
| 万华化学 | `render` | https://www.whchem.com/column/164/ |
| 华大BGI | `beisen` | https://genomics.zhiye.com/campus/jobs |
| 华润集团 | `render` | https://runjob.crc.com.cn/ |
| 上海复旦微电子 | `render` | https://campus.51job.com/fmsh2026/p2.html |
| 中科曙光 | `beisen` | https://sugon.zhiye.com/campus/jobs |
| 恩智浦 | `render` | https://campus.51job.com/nxp/graduates.html |
| 数码视讯 | `render` | https://www.sumavision.com.cn/join-us |
| 旭创科技 | `render` | https://xyzp.51job.com/innolight/about.html |
| 普门科技 | `render` | https://www.lifotronic.com/job/campus.html |
| 正泰集团 | `render` | https://campus.chint.com |
| 步科股份 | `render` | https://www.kinco.cn/talent-recruitment |
| 海信集团 | `beisen` | https://jobs.hisense.com/campus/jobs |
| 云天励飞 | `beisen` | https://intellif.zhiye.com/campus/jobs |
| 三一集团 | `beisen` | https://sany.zhiye.com/campus/jobs |
| 上汽集团 | `render` | https://saic-recruit.saicmotor.com/ |
| 先导科技 | `beisen` | https://vital.zhiye.com/campus/jobs |
| 葡萄城 | `render` | https://www.grapecity.cn/about/joinus.htm |
| 酷睿程 | `render` | https://carizon.jobs.feishu.cn/421026 |
| 中国电科 | `render` | https://cetc.iguopin.com/job-campus |
| 广域铭岛 | `render` | https://www.sail-cloud.com/join-us |
| 爱学习 | `beisen` | https://aixuexi1.zhiye.com/campus/jobs |

## 已由现有配置覆盖的 Excel 公司

| Excel 公司 | 当前配置匹配 | Excel 岗位/备注 | 来源 |
| --- | --- | --- | --- |
| 平头哥 | 阿里平头哥（侧开-上海-8.8）15天内投 | 测开、芯片软件开发 | 戴-投递情况.xlsx / 戴仕强测评:156 |
| 广域铭岛 | 广域铭岛 | 智驾数据应用开发工程师（C++） | 戴-投递情况.xlsx / 戴仕强测评:380 |
| 庆铃 | 重庆庆铃 | 软件开发及运维技术岗位和智能网联方向岗（邮箱） | 戴-投递情况.xlsx / 戴仕强测评:243 |
| 康冠科技KTC | 康冠科技 / 深圳康冠科技 | 测开、嵌入式开发、linux驱动开发 | 戴-投递情况.xlsx / 戴仕强测评:66 |
| 当当网 | 当当网 | 技术类、网易邮箱投递的 | 戴-投递情况.xlsx / 戴仕强测评:59 |
| 影石Instal360 | 影石 | 嵌软/嵌入式算法 | 刘博简历投递记录.xlsx / Sheet3:10 |
| 惠州市德赛西威 | 德赛西威 / 惠州市德赛西威汽车 | 嵌软/应用软件/测开/算法 | 刘博简历投递记录.xlsx / Sheet3:65 |
| 成都天锐星通科技股份有限公司 | 天锐星通 | 测试方法研究工程师（校招，智联招聘） | wyp.xlsx / 吴亚鹏测评:3 |
| 招联 | 招联金融 | 后台开发 | 戴-投递情况.xlsx / 戴仕强测评:316 |
| 昂瑞微电子 | 昂瑞微 | 嵌入式软件工程师、邮箱投递 | 戴-投递情况.xlsx / 戴仕强测评:72 |
| 星纵物联5天内投 | 星纵物联 |  | wyp.xlsx / 师兄:271 |
| 江波龙电子 | 江波龙 | 测试 | 刘博简历投递记录.xlsx / Sheet2:216 |
| 海信集团/9.6发布岗位 | 海信集团 | 软开c++（设计模式）/软开（嵌）限投一个 | 刘博简历投递记录.xlsx / Sheet3:68 |
| 海康 | 海康威视 | SLAM算法工程师 | 刘博简历投递记录.xlsx / Sheet2:25 |
| 深圳云天励飞技术股份有限公司 | 云天励飞 | 算法工程师（邮件投递） | wyp.xlsx / 师兄:243 |
| 深圳元戎启行科技有限公司 | 元戎启行 | 测试开发工程师 | wyp.xlsx / 师兄:242 |
| 深圳鼎阳科技 | 鼎阳科技 | 软件测试开发、嵌入式开发 | 戴-投递情况.xlsx / 戴仕强测评:70 |
| 烟台睿创微纳 | 睿创微纳 | 只投了SDK开发（填表，没要简历），其他只有ic | 戴-投递情况.xlsx / 戴仕强测评:501 |
| 爱学习 | 爱学习 | 算法，绩点写的3.0和3.15 | 戴-投递情况.xlsx / 戴仕强测评:58 |
| 爱瑞无线科技 | 爱瑞无线 | C++、测试 | 戴-投递情况.xlsx / 戴仕强测评:104 |
| 电科莱斯、28所 | 电科莱斯 | 软开 | 戴-投递情况.xlsx / 戴仕强测评:299 |
| 福建星网锐捷通讯 | 星网锐捷 / 锐捷 | C++（邮箱投递） | 戴-投递情况.xlsx / 戴仕强测评:203 |
| 米哈游miHoYo | 米哈游 / miHoYo | 游戏测试开发 | 刘博简历投递记录.xlsx / Sheet3:9 |
| 恒生电子 | 恒生 | C++开发工程师 | 刘博简历投递记录.xlsx / Sheet1:55 |
| 杭州广立微电子 | 广立微 | C++开发、测试（杭州） | 戴-投递情况.xlsx / 戴仕强测评:157 |
| 柠檬微趣 | 柠檬微趣（初级测试工程师-北京-8.1发布-10-14k）五天内投 | 后台开发 | 戴-投递情况.xlsx / 戴仕强测评:134 |
| 比特大陆算能科技 | 比特大陆 | 算法 | 戴-投递情况.xlsx / 戴仕强测评:87 |
| 理想 | 理想内推 | 测开(了解嵌优先)/智驾软件研发 | 刘博简历投递记录.xlsx / Sheet3:40 |
| 用友汽车信息科技 | 用友 | 校招已开启，目前只有北京 | 戴-投递情况.xlsx / 戴仕强测评:419 |
| 紫光华智 | 紫光 | 软开，待投（还无职位） | 戴-投递情况.xlsx / 戴仕强测评:222 |
| 紫光国芯 | 紫光 | 测试 | 戴-投递情况.xlsx / 戴仕强测评:102 |
| 紫光展悦 | 紫光 | 目前只有社招 | 戴-投递情况.xlsx / 戴仕强测评:402 |
| 网易 | 网易云音乐 / 网易雷火 / 网易互娱 | 游戏测试开发 | 刘博简历投递记录.xlsx / Sheet2:66 |
| 腾讯子公司 | 腾讯 | 测开、后台开发 | 戴-投递情况.xlsx / 戴仕强测评:218 |
| 腾讯子公司腾讯云 | 腾讯 | 未招聘，只有腾讯但只有成都岗，之前投了 | 戴-投递情况.xlsx / 戴仕强测评:369 |
| 腾讯音乐 | 腾讯 | 软件开发-后台方向 | 刘博简历投递记录.xlsx / Sheet1:38 |
| 腾讯音乐尽早投 | 腾讯 | 侧开（挂了后面可投系统测试或者技术测试） | wyp.xlsx / 吴亚鹏测评:57 |
| 淘宝 | 淘天 / 阿里巴巴 | 研发工程师C/C++ | 刘博简历投递记录.xlsx / Sheet1:61 |
| 吉祥腾达科技 | covered by `吉祥腾达` (`beisen`) | https://tenda.zhiye.com/campus/jobs | 嵌入式软件工程师 |
| 博思软件 | covered by `博思` / `福建博思软件` (`moka`) | https://app.mokahr.com/campus-recruitment/bosssoft/68370 | python研发工程师 |
| 360集团 | 360集团 | 嵌入式 | 刘博简历投递记录.xlsx / Sheet2 |
| 58同城 | 58同城 | 测试工程师 | wyp.xlsx / 吴亚鹏测评 |
| ArcSoft虹软 | ArcSoft虹软 | 算法测试开发 | 刘博简历投递记录.xlsx / Sheet2 |
| bilibili | bilibili | 测试开发 | wyp.xlsx / 吴亚鹏测评 |
| CVTE | CVTE | 嵌入式软件开发工程师（Linux方向） | 刘博简历投递记录.xlsx / Sheet1 |
| FunPlus | FunPlus | 游戏测试 | 刘博简历投递记录.xlsx / Sheet2 |
| miHoYo | miHoYo | 游戏测试开发 | 刘博简历投递记录.xlsx / Sheet2 |
| Momenta | Momenta | 测试 | 刘博简历投递记录.xlsx / Sheet2 |
| mova | mova | 测试 | wyp.xlsx / 吴亚鹏测评 |
| NVIDIA | NVIDIA | Soc | 刘博简历投递记录.xlsx / Sheet2 |
| oppo | oppo | 多媒体应用开发 | 刘博简历投递记录.xlsx / Sheet1 |
| realme | realme | C++/测试 | 刘博简历投递记录.xlsx / Sheet2 |
| SHEIN | SHEIN | C++开发工程师 | 刘博简历投递记录.xlsx / 正式批 |
| TCL | TCL | 嵌入式开发 | 刘博简历投递记录.xlsx / Sheet2 |
| TP-Link联洲 | TP-Link联洲 | 系统测试(妥妥的学历厂卡双九) | 刘博简历投递记录.xlsx / Sheet2 |
| tplink | tplink | 软件工程师 | 刘博简历投递记录.xlsx / Sheet1 |
| vivo | vivo | 测试开发工程师 | 刘博简历投递记录.xlsx / 正式批 |
| 万兴科技nk | 万兴科技 | C++ | 刘博简历投递记录.xlsx / Sheet2 |
| 万得 | 万得 | C++开发工程师 | 刘博简历投递记录.xlsx / Sheet1 |
| 上海微电子 | 上海微电子 | 嵌入式-国企 | 刘博简历投递记录.xlsx / Sheet2 |
| 上海燧原科技 | 上海燧原科技 | 驱动开发 | 刘博简历投递记录.xlsx / Sheet2 |
| 东土科技 | 东土科技 | 软件开发-网络开发 | 刘博简历投递记录.xlsx / 正式批 |
| 东方财富 | 东方财富 | 软测 | 戴-投递情况.xlsx / 戴仕强测评 |
| 东莞新能德科技 | 东莞新能德 | 可靠性测试 /电子研发 /(国企版带嵌) | 刘博简历投递记录.xlsx / Sheet3 |
| 东软集团 | 东软集团 | 测试 | wyp.xlsx / 吴亚鹏测评 |
| 东风汽车 | 东风汽车 | 智能制造类-东本发动机 | 刘博简历投递记录.xlsx / Sheet2 |
| 中信科 | 中信科 | 测试 | wyp.xlsx / 吴亚鹏测评 |
| 中兴实习 | 中兴 | 软件测试 | 刘博简历投递记录.xlsx / Sheet2 |
| 中国一汽 | 中国一汽 | 测试 | 刘博简历投递记录.xlsx / Sheet2 |
| 中国平安 | 中国平安 | 测试工程师 | 戴-投递情况.xlsx / 戴仕强测评 |
| 中国电信天翼云 | 中国电信天翼云 | 后端开发 | 戴-投递情况.xlsx / 戴仕强测评 |
| 中国电子云 | 中国电子云 | 后端开发工程师 | 戴-投递情况.xlsx / 戴仕强测评 |
| 中国网安/30所 | 中国网安/30所 | 产品化测试工程师 | wyp.xlsx / 吴亚鹏测评 |
| 中国邮政 | 中国邮政 | 开发 | 刘博简历投递记录.xlsx / Sheet2 |
| 中国银行 | 中国银行 | 测试 | 刘博简历投递记录.xlsx / Sheet2 |
| 中控技术 | 中控 | C++工程师 | 刘博简历投递记录.xlsx / 正式批 |
| 中新赛克 | 中新赛克 | C语言工程师 | 刘博简历投递记录.xlsx / 正式批 |
| 中望软件 | 中望软件 | C++ | 刘博简历投递记录.xlsx / Sheet2 |
| 中汇会计师事务所 | 中汇会计师事务所 | 测试 | 刘博简历投递记录.xlsx / Sheet2 |
| 中海达实习 | 中海达 | 软开 | 刘博简历投递记录.xlsx / Sheet2 |
| 中电36所 | 中电36所 | 嵌入式软件 | 刘博简历投递记录.xlsx / Sheet2 |
| 中电52所 | 中电52所 | 嵌入式/c++ | 刘博简历投递记录.xlsx / Sheet2 |
| 中电十所 | 中电十所 | 嵌入式软件 | 刘博简历投递记录.xlsx / Sheet2 |
| 中科寒武纪 | 中科寒武纪 | 软侧开 | 戴-投递情况.xlsx / 戴仕强测评 |
| 中科曙光 | 中科曙光 | 测试开发 | wyp.xlsx / 吴亚鹏测评 |
| 中通 | 中通 | 测试 | 刘博简历投递记录.xlsx / Sheet2 |
| 中金所 | 中金所 | 测试 | wyp.xlsx / 吴亚鹏测评 |
| 丰疆智能 | 丰疆智能 | 嵌入式 | 刘博简历投递记录.xlsx / Sheet2 |
| 九十智能 | 九十智能 | 感知 | wyp.xlsx / 吴亚鹏测评 |
| 九号公司 | 九号公司 | 嵌入式开发 | 刘博简历投递记录.xlsx / Sheet2 |
| 九洲集团 | 九洲集团 | 软件开发工程师 | 刘博简历投递记录.xlsx / 正式批 |
| 九阳 | 九阳 | SLAM算法 | 刘博简历投递记录.xlsx / Sheet2 |
| 乾程科技 | 乾程科技 | 嵌入式 | 刘博简历投递记录.xlsx / Sheet2 |
| 云创智行实习 | 云创智行实习 | 激光SLAM算法 | 刘博简历投递记录.xlsx / Sheet2 |
| 云天励飞 | 云天励飞 | 测试开发工程师 | 刘博简历投递记录.xlsx / 正式批 |
| 云智研发 | 云智研发 | 系统测试 | wyp.xlsx / 吴亚鹏测评 |
| 云账房 | 云账房 | 测试 | wyp.xlsx / 吴亚鹏测评 |
| 云鲸智能 | 云鲸智能 | 机器人软件开发 | 刘博简历投递记录.xlsx / 正式批 |
| 亚信安全 | 亚信安全 | 侧开 | wyp.xlsx / 吴亚鹏测评 |
| 交控科技股份有限公司 | 交控科技 | 软件工程师 | 刘博简历投递记录.xlsx / 正式批 |
| 京东 | 京东实习 | 后端开发 | 刘博简历投递记录.xlsx / Sheet1 |
| 京东方 | 京东方 | 测试终端 | 刘博简历投递记录.xlsx / Sheet2 |
| 亿嘉和 | 亿嘉和 | 嵌入式软件/SLAM | 刘博简历投递记录.xlsx / Sheet2 |
| 亿联网络 | 亿联网络提前批 | C++开发工程师 | 刘博简历投递记录.xlsx / Sheet1 |
| 亿道集团 | 亿道集团 | 测试 | 刘博简历投递记录.xlsx / Sheet2 |
| 众合科技 | 众合科技 | C++开发工程师（线网产品中心,QT简历）、测试 | 戴-投递情况.xlsx / 戴仕强测评 |
| 优博讯科技 | 优博讯 | 软件开发工程师 | 刘博简历投递记录.xlsx / 正式批 |
| 优必选科技 | 优必选 | 测试开发工程师 | 刘博简历投递记录.xlsx / 正式批 |
| 优比选 | 优比选 | 软件侧开 | wyp.xlsx / 吴亚鹏测评 |
| 优特科技 | 优特科技 | 系统测试 | wyp.xlsx / 吴亚鹏测评 |
| 优艾智合 | 优艾智合 | 软测 | wyp.xlsx / 吴亚鹏测评 |
| 传音 | 传音 | 软件开发工程师 | 刘博简历投递记录.xlsx / 正式批 |
| 传音控股 | 传音控股 | 软件工程师（C/C++方向） | 刘博简历投递记录.xlsx / Sheet2 |
| 佑驾创新 | 佑驾创新 | SLAM/嵌测(非嵌)/测开(11.28国企带嵌)限3个 | 刘博简历投递记录.xlsx / Sheet3 |
| 作业帮 | 作业帮 | 侧开 | wyp.xlsx / 吴亚鹏测评 |
| 佰维存储 | 佰维存储 | 软件开发工程师 | 刘博简历投递记录.xlsx / 正式批 |
| 佳都科技 | 佳都科技 | 软测 | wyp.xlsx / 吴亚鹏测评 |
| 信也科技nk | 信也科技 | 测试 | 刘博简历投递记录.xlsx / Sheet2 |
| 元鼎 | 元鼎 | 测试 | wyp.xlsx / 吴亚鹏测评 |
| 兆易创新 | 兆易创新 | 嵌入式软件 | 刘博简历投递记录.xlsx / Sheet2 |
| 光电运通 | 光电运通 | 软件测试 | wyp.xlsx / 吴亚鹏测评 |
| 光迅科技 | 光迅科技 | 应用开发工程师 | 刘博简历投递记录.xlsx / 正式批 |
| 公牛集团 | 公牛 | 软开/限两个 | 刘博简历投递记录.xlsx / Sheet3 |
| 其域创新 | 其域创新 | 测试 | wyp.xlsx / 吴亚鹏测评 |
| 凌云光 | 凌云光 | 软件测试 | wyp.xlsx / 吴亚鹏测评 |
| 创维 | 创维 | 测试/软件--毁约？ | 刘博简历投递记录.xlsx / Sheet2 |
| 创达 | 创达 | 测试 | wyp.xlsx / 吴亚鹏测评 |
| 北京图森智途 | 北京图森智途 | 软件研发-Linux/仿真测试 | 刘博简历投递记录.xlsx / Sheet2 |
| 北京易控智驾 | 北京易控智驾 | 测试 | 刘博简历投递记录.xlsx / Sheet2 |
| 北森 | 北森 | 测试/应用运维 | 刘博简历投递记录.xlsx / Sheet2 |
| 匠芯创科技 | 匠芯创科技(hr邮箱) | 软件设计 | 刘博简历投递记录.xlsx / Sheet2 |
| 华为 | 华为 | 通用软件工程师 | 刘博简历投递记录.xlsx / 正式批 |
| 华勤技术 | 华勤 | 软件工程师 | 刘博简历投递记录.xlsx / 正式批 |
| 华曦达 | 华曦达 | 嵌入式软件工程师 | 刘博简历投递记录.xlsx / 正式批 |
| 华橙网络 | 华橙网络 | 软测 | wyp.xlsx / 吴亚鹏测评 |
| 华测 | 华测 | 嵌入式软件/多源融合算法 | 刘博简历投递记录.xlsx / Sheet2 |
| 华诺星空 | 华诺星空 | 嵌入式软件工程师 | 刘博简历投递记录.xlsx / 正式批 |
| 卓望 | 卓望公司 | 软测 | 戴-投递情况.xlsx / 戴仕强测评 |
| 卓越教育 | 卓越教育 | 测试 | wyp.xlsx / 吴亚鹏测评 |
| 卓驭科技 | 卓驭 | C++软件开发工程师 | 刘博简历投递记录.xlsx / Sheet1 |
| 南方卫星导航 | 南方卫星导航 | SLAM/嵌入式软件 | 刘博简历投递记录.xlsx / Sheet2 |
| 博世 | 博世 | 嵌入式测试/自动驾驶测试 | 刘博简历投递记录.xlsx / Sheet2 |
| 博思 | 博思 | 软件测试 | wyp.xlsx / 吴亚鹏测评 |
| 博睿康 | 博睿康 | 开发 | 刘博简历投递记录.xlsx / Sheet2 |
| 卡斯柯 | 卡斯柯 | 嵌入式 | 刘博简历投递记录.xlsx / Sheet2 |
| 去哪儿旅行内推 | 去哪儿旅行内推 | 测开 | 刘博简历投递记录.xlsx / Sheet2 |
| 叠纸游戏 | 叠纸游戏 | 服务端开发 | 戴-投递情况.xlsx / 戴仕强测评 |
| 合合信息 | 合合信息 | 后端开发 | 刘博简历投递记录.xlsx / Sheet1 |
| 吉利控股 | 吉利控股 | 软件工程师 | 刘博简历投递记录.xlsx / 正式批 |
| 吉比特 | 吉比特 | 游戏测试 | wyp.xlsx / 吴亚鹏测评 |
| 启源芯动力 | 启源芯动力 | 研发工程师-测试 | wyp.xlsx / 吴亚鹏测评 |
| 哈喽 | 哈喽 | 软测 | wyp.xlsx / 吴亚鹏测评 |
| 哔哩哔哩 | 哔哩哔哩（侧开-上海-8.1） | 软件开发-测试方向 | 刘博简历投递记录.xlsx / Sheet1 |
| 唯品会 | 唯品会 | 测试工程师 | wyp.xlsx / 吴亚鹏测评 |
| 因诺科技 | 因诺科技(hr邮箱) | 嵌入式 | 刘博简历投递记录.xlsx / Sheet2 |
| 图森智途 | 图森智途 | 软件研发-Linux | 刘博简历投递记录.xlsx / Sheet2 |
| 图森牛客内推 | 图森牛客内推 | 自动驾驶仿真测试 | 刘博简历投递记录.xlsx / Sheet2 |
| 地平线 | 地平线 | 智驾中间件开发 | 刘博简历投递记录.xlsx / Sheet1 |
| 均胜集团 | 均胜集团 | 嵌入式 | 刘博简历投递记录.xlsx / Sheet2 |
| 基恩士sb小日本 | 基恩士sb小日本 | 销售+技术 | 刘博简历投递记录.xlsx / Sheet2 |
| 塞力斯 | 塞力斯 | 科技公司-软硬件测试类 | wyp.xlsx / 吴亚鹏测评 |
| 大华股份 | 大华 | 测开 | 戴-投递情况.xlsx / 戴仕强测评 |
| 大普微电子 | 大普微电子 | 嵌入式软件 | 刘博简历投递记录.xlsx / Sheet2 |
| 大疆 | 大疆 | 嵌入式软件开发（实习） | 刘博简历投递记录.xlsx / Sheet1 |
| 奇安信科技 | 奇安信 | 后端开发工程师 | 刘博简历投递记录.xlsx / 正式批 |
| 奇瑞 | 奇瑞 | 软件 | 刘博简历投递记录.xlsx / Sheet2 |
| 奥比中光 | 奥比中光 | 软件开发工程师 | 刘博简历投递记录.xlsx / 正式批 |
| 威迈斯 | 威迈斯 | 软件工程师 | 刘博简历投递记录.xlsx / 正式批 |
| 字节跳动 | 字节跳动 | C++客户端开发工程师-用户中台 | 刘博简历投递记录.xlsx / Sheet1 |
| 宁德时代 | 宁德时代 | 建图与定位算法/嵌入式软件 | 刘博简历投递记录.xlsx / Sheet2 |
| 宇树科技 | 宇树科技 | 激光SLAM/解决方案(11.28国企带嵌) | 刘博简历投递记录.xlsx / Sheet3 |
| 安克创新 | 安克创新 | C++工程师 | 刘博简历投递记录.xlsx / 正式批 |
| 安恒信息 | 安恒信息 |  | 刘博简历投递记录.xlsx / 正式批 |
| 宏盛股份 | 宏盛股份 | 测试 | wyp.xlsx / 吴亚鹏测评 |
| 实习僧AMD | 实习僧AMD | 深度学习SLAM实习生 | 刘博简历投递记录.xlsx / Sheet2 |
| 实习僧autowise.ai | 实习僧autowise.ai | 自动驾驶算法实习生 | 刘博简历投递记录.xlsx / Sheet2 |
| 实习僧momenta | 实习僧momenta | 建图定位算法实习生 | 刘博简历投递记录.xlsx / Sheet2 |
| 实习僧小鹏 | 实习僧小鹏 | 自动驾驶-传感器标定算法实习生 | 刘博简历投递记录.xlsx / Sheet2 |
| 实习僧特斯拉 | 实习僧特斯拉 | 测试开发工程师 | 刘博简历投递记录.xlsx / Sheet2 |
| 实习僧速腾 | 实习僧速腾 | 嵌入式软件开发实习生 | 刘博简历投递记录.xlsx / Sheet2 |
| 容知日新 | 容知日新 | 软测 | wyp.xlsx / 吴亚鹏测评 |
| 富士康 | 富士康 | 嵌入式 | 刘博简历投递记录.xlsx / Sheet2 |
| 富途集团 | 富途集团 | 后台开发-双重邮挂 | 刘博简历投递记录.xlsx / Sheet2 |
| 小天才 | 小天才 | ai算法测试工程师 | wyp.xlsx / 吴亚鹏测评 |
| 小米 | 小米 | 软件开发工程师 | 刘博简历投递记录.xlsx / 正式批 |
| 小红书 | 小红书 | Java/C++/Golang开发（中间件方向rpc） | 刘博简历投递记录.xlsx / Sheet2 |
| 小赢科技 | 小赢科技 | 测试 | wyp.xlsx / 吴亚鹏测评 |
| 小马智行 | 小马智行 | 嵌入式开发/研发 | 刘博简历投递记录.xlsx / Sheet2 |
| 小鹏汽车 | 小鹏汽车 | c++自动驾驶开发、软测 | 戴-投递情况.xlsx / 戴仕强测评 |
| 平凯星辰 | 平凯星辰 | 侧开 | wyp.xlsx / 吴亚鹏测评 |
| 广东联通 | 广东联通 | 软件 | 刘博简历投递记录.xlsx / Sheet2 |
| 广和通 | 广和通 | 开发工程师 | 刘博简历投递记录.xlsx / 正式批 |
| 广州金升阳 | 广州金升阳 | 嵌入式 | 刘博简历投递记录.xlsx / Sheet2 |
| 广汽研究院 | 广汽研究院 | 智能网联类 | 刘博简历投递记录.xlsx / Sheet2 |
| 广汽集团-埃安 | 广汽集团-埃安 | 自动驾驶软件 | 刘博简历投递记录.xlsx / Sheet2 |
| 广电运通-姚孃 | 广电运通-姚孃 | 系统驱动 | 刘博简历投递记录.xlsx / Sheet2 |
| 广立微 | 广立微 | C++EDA（看不到进度） | 刘博简历投递记录.xlsx / Sheet2 |
| 广联达 | 广联达 | C++开发工程师 | 刘博简历投递记录.xlsx / 正式批 |
| 库玛科技 | 库玛科技 | 侧开 | wyp.xlsx / 吴亚鹏测评 |
| 度小满 | 度小满 | 没得重庆岗，只有上海北京 | 戴-投递情况.xlsx / 戴仕强测评 |
| 康冠科技 | 康冠科技 | 软件工程师 | 刘博简历投递记录.xlsx / 正式批 |
| 影石Insta360 | 影石Insta360 | 测试开发工程师 | wyp.xlsx / 师兄 |
| 得一微电子 | 得一微电子 | 测试 | wyp.xlsx / 吴亚鹏测评 |
| 得物 | 得物 | 测试 | 刘博简历投递记录.xlsx / Sheet2 |
| 快手 | 快手 | C++开发工程师 | 刘博简历投递记录.xlsx / Sheet1 |
| 思必驰 | 思必驰 | 测试 | wyp.xlsx / 吴亚鹏测评 |
| 思格新能源nk | 思格新能源nk | 嵌入式 | 刘博简历投递记录.xlsx / Sheet2 |
| 恒玄科技 | 恒玄科技 | 软件开发工程师 | 刘博简历投递记录.xlsx / 正式批 |
| 恒生 | 恒生 | 测试 | 刘博简历投递记录.xlsx / Sheet2 |
| 恩智浦Qq! | 恩智浦Qq! | MCU测试 | 刘博简历投递记录.xlsx / Sheet2 |
| 惠州市德赛西威汽车 | 惠州市德赛西威汽车 | 嵌入式 | 刘博简历投递记录.xlsx / Sheet2 |
| 成谷科技 | 成谷科技 | 测试开发 | 刘博简历投递记录.xlsx / Sheet2 |
| 成都新易盛通信 | 成都新易盛通信 | 嵌入式软件开发 | 刘博简历投递记录.xlsx / Sheet2 |
| 成都精灵云nk | 成都精灵云nk | C++ | 刘博简历投递记录.xlsx / Sheet2 |
| 拓竹科技 | 拓竹科技 | C++开发工程师 | 刘博简历投递记录.xlsx / Sheet1 |
| 招商银行招银网络科技 | 招商银行招银网络科技 | 侧开 | wyp.xlsx / 吴亚鹏测评 |
| 招联金融 | 招联金融 | 测试工程师 | 刘博简历投递记录.xlsx / 正式批 |
| 招银网络科技 | 招银网络科技 | 测试开发工程师 | 刘博简历投递记录.xlsx / 正式批 |
| 搜狐畅游 | 搜狐畅游 | 游戏软件开发、群表 | 戴-投递情况.xlsx / 戴仕强测评 |
| 携程 | 携程 | 侧开 | wyp.xlsx / 吴亚鹏测评 |
| 数字政通 | 数字政通 | 项目实施工程师、方案解决工程师 | 戴-投递情况.xlsx / 戴仕强测评 |
| 数字马力 | 数字马力 | 测开 | 刘博简历投递记录.xlsx / Sheet3 |
| 数禾科技 | 数禾科技 | 数据分析（风险策略方向） | 戴-投递情况.xlsx / 戴仕强测评 |
| 文远知行 | 文远知行 | 集成开发工程师 | 刘博简历投递记录.xlsx / Sheet1 |
| 斑马网络 | 斑马网络 | 官网只有社招 | 戴-投递情况.xlsx / 戴仕强测评 |
| 新凯来 | 新凯来 | 软件工程师 | 刘博简历投递记录.xlsx / 正式批 |
| 新华三 | 新华三 | C++开发工程师 | 刘博简历投递记录.xlsx / 正式批 |
| 新大陆 | 新大陆 | 软件测试 | wyp.xlsx / 吴亚鹏测评 |
| 施耐德 | 施耐德 | 嵌入式软件测试/测试工程师 | 刘博简历投递记录.xlsx / Sheet2 |
| 旷世科技-极感科技北京/成都-8.4发布）五天内投，不抱希望试试看 | 旷世科技-极感科技（图像算法工程师（人像感知方向）北京/成都-8.4发布）五天内投，不抱希望试试看 | 商汤科技（侧开-深圳-8.1发布9.29结束）尽早投 | wyp.xlsx / 师兄 |
| 旷视 | 旷视科技 | DSWF9Smb/自驾软件/工程开发 /21号宣讲 | 刘博简历投递记录.xlsx / Sheet3 |
| 昊一源 | 昊一源 | 软测 | wyp.xlsx / 吴亚鹏测评 |
| 明源云 | 明源云 | 测试 | wyp.xlsx / 吴亚鹏测评 |
| 明阳智慧能源 | 明阳智慧能源 | 软件 | 刘博简历投递记录.xlsx / Sheet2 |
| 易事特 | 易事特 | 测试 | wyp.xlsx / 吴亚鹏测评 |
| 星宸科技 | 星宸科技 | 嵌入式软件 | 刘博简历投递记录.xlsx / Sheet2 |
| 星猿哲科技 | 星猿哲科技 | 机器人开发 | 刘博简历投递记录.xlsx / Sheet2 |
| 星环科技 | 星环科技 | 分布式开发 | 刘博简历投递记录.xlsx / Sheet2 |
| 星纵物联 | 星纵物联 | 应用软件开发工程师 | 刘博简历投递记录.xlsx / Sheet1 |
| 星网锐捷 | 星网锐捷 | C++开发工程师 | 刘博简历投递记录.xlsx / 正式批 |
| 普渡机器人 | 普渡机器人 | C++工程师 | 刘博简历投递记录.xlsx / 正式批 |
| 智元机器人 | 智元机器人 | C++ 稚晖君 | 刘博简历投递记录.xlsx / Sheet2 |
| 智方 | 智方 | 侧开 | wyp.xlsx / 吴亚鹏测评 |
| 智驾科技MAXIEYE | 智驾科技MAXIEYE | 测试 | 刘博简历投递记录.xlsx / Sheet2 |
| 曦华科技nk | 曦华科技nk | 嵌入式(秋招终止hhh） | 刘博简历投递记录.xlsx / Sheet2 |
| 机加科技 | 机加科技 | 侧开 | wyp.xlsx / 吴亚鹏测评 |
| 杉川机器人 | 杉川机器人 | 算法/软测(国企带嵌) | 刘博简历投递记录.xlsx / Sheet3 |
| 杭州国芯 | 杭州国芯 | 嵌入式 | 刘博简历投递记录.xlsx / Sheet2 |
| 杭州行芯科技 | 杭州行芯科技 | 软件 | 刘博简历投递记录.xlsx / Sheet2 |
| 杰华特微电子股份有限公司 | 杰华特微电子 | 测试开发工程师 | wyp.xlsx / 师兄 |
| 极智嘉科技 | 极智嘉 | SLAM/机器人软件 | 刘博简历投递记录.xlsx / Sheet3 |
| 极米科技 | 极米科技 | 嵌入式 | 刘博简历投递记录.xlsx / Sheet2 |
| 极飞科技 | 极飞科技 | 应用软件工程师 | 刘博简历投递记录.xlsx / 正式批 |
| 柏楚电子 | 柏楚电子 | 嵌入式软件 | 刘博简历投递记录.xlsx / Sheet2 |
| 柠檬微趣五天内投 | 柠檬微趣（初级测试工程师-北京-8.1发布-10-14k）五天内投 | 阿里云（侧开-北上深杭-8.5发布9.1结束）尽早投 | wyp.xlsx / 师兄 |
| 格力 | 格力 | 电控软件设计 | 刘博简历投递记录.xlsx / Sheet2 |
| 森马股份 | 森马股份 | 系统分析 | 刘博简历投递记录.xlsx / Sheet2 |
| 欣旺达 | 欣旺达 | 应用软件/（国企带嵌） | 刘博简历投递记录.xlsx / Sheet3 |
| 正浩创新 | 正浩创新 | 软件测试工程师 | 刘博简历投递记录.xlsx / 正式批 |
| 比亚迪 | 比亚迪 | 开发-不固定 | 刘博简历投递记录.xlsx / Sheet2 |
| 水滴 | 水滴 | 测试 | wyp.xlsx / 吴亚鹏测评 |
| 汇川技术 | 汇川技术 | 系统软件工程师 | 刘博简历投递记录.xlsx / Sheet1 |
| 江波龙 | 江波龙 | 测开、测试 | 戴-投递情况.xlsx / 戴仕强测评 |
| 江苏芯云电子 | 江苏芯云电子 | 嵌入式软开(hr邮箱） | 刘博简历投递记录.xlsx / Sheet2 |
| 沐瞳科技 | 沐瞳科技 | C++服务端开发工程师 | 刘博简历投递记录.xlsx / Sheet1 |
| 波士顿科学 | 波士顿科学 | 嵌入式固件Firmware | 刘博简历投递记录.xlsx / Sheet2 |
| 泰凌微电子nk | 泰凌微电子 | 嵌入式开发 | 刘博简历投递记录.xlsx / Sheet2 |
| 浙江保融科技 | 浙江保融科技 | 软件 | 刘博简历投递记录.xlsx / Sheet2 |
| 浙江大华 | 浙江大华 | 嵌入式软件工程师 | 刘博简历投递记录.xlsx / 正式批 |
| 浩鲸科技 | 浩鲸科技 | C++开发工程师 | 刘博简历投递记录.xlsx / 正式批 |
| 海信集团 | 海信集团 | 软件工程师 | 刘博简历投递记录.xlsx / 正式批 |
| 海尔 | 海尔 | 嵌入式软件工程师 | 刘博简历投递记录.xlsx / Sheet1 |
| 海康sb公司 | 海康sb公司 | 软件开发-嵌/SLAM算法 | 刘博简历投递记录.xlsx / Sheet2 |
| 海康威视 | 海康威视 | 应用开发工程师 | 刘博简历投递记录.xlsx / 正式批 |
| 海德思 | 海德思 | 软测和算法 | wyp.xlsx / 吴亚鹏测评 |
| 海柔创新 | 海柔创新 | 嵌入式软件 | 刘博简历投递记录.xlsx / 正式批 |
| 海格通信 | 海格通信 | 应用开发工程师 | 刘博简历投递记录.xlsx / 正式批 |
| 淘天 | 淘天 | 测试开发 | 刘博简历投递记录.xlsx / Sheet2 |
| 深信服 | 深信服 | C++软件工程师 | 刘博简历投递记录.xlsx / 正式批 |
| 深圳依时货拉拉 | 深圳依时货拉拉 | 后端测试 | 刘博简历投递记录.xlsx / Sheet2 |
| 清微智能 | 清微智能 | 软件测试 | wyp.xlsx / 吴亚鹏测评 |
| 游卡 | 游卡 | 服务端开发工程师 | 刘博简历投递记录.xlsx / Sheet1 |
| 满帮集团 | 满帮集团 | 测开（测试简历） | 戴-投递情况.xlsx / 戴仕强测评 |
| 滴滴 | 滴滴 | 系统工程师（C++） | 刘博简历投递记录.xlsx / Sheet1 |
| 灵犀互娱 | 灵犀互娱 | 软件开发-游戏测试方向 | 刘博简历投递记录.xlsx / Sheet1 |
| 灵犀互娱尽早投 | 灵犀互娱（游戏侧开-广州-8.5发布）尽早投 | 侧开 | wyp.xlsx / 吴亚鹏测评 |
| 炬芯科技 | 炬芯科技 | 嵌入式 | 刘博简历投递记录.xlsx / Sheet2 |
| 点众科技 | 点众科技 | 测试 | wyp.xlsx / 吴亚鹏测评 |
| 烽火通信 | 烽火通信 | C++开发工程师 | 刘博简历投递记录.xlsx / 正式批 |
| 爱旭股份 | 爱旭股份 | IT | 刘博简历投递记录.xlsx / Sheet2 |
| 珠海全志科技 | 珠海全志科技 | 嵌入式软件 | 刘博简历投递记录.xlsx / Sheet2 |
| 理想内推 | 理想内推 | 软件研发 | 刘博简历投递记录.xlsx / Sheet2 |
| 瑞沃德 | 瑞沃德 | 软测 | wyp.xlsx / 吴亚鹏测评 |
| 用友 | 用友 | 软件测试 | wyp.xlsx / 吴亚鹏测评 |
| 电科金仓 | 电科金仓 | 测试工程师 | wyp.xlsx / 吴亚鹏测评 |
| 百度 | 百度 | 软件工程师 | 刘博简历投递记录.xlsx / Sheet1 |
| 盛趣游戏 | 盛趣游戏 | C++游戏 | 刘博简历投递记录.xlsx / Sheet2 |
| 睿创微纳 | 睿创微纳 | C++工程师 | 刘博简历投递记录.xlsx / 正式批 |
| 睿联技术 | 睿联技术 | 嵌入式 | 刘博简历投递记录.xlsx / Sheet2 |
| 神策 | 神策 | 侧开 | wyp.xlsx / 吴亚鹏测评 |
| 祥承科技 | 祥承科技 | 软件测试 | wyp.xlsx / 吴亚鹏测评 |
| 福建博思软件 | 福建博思软件 | 测试 | 刘博简历投递记录.xlsx / Sheet2 |
| 禾望电气 | 禾望电气 | 嵌入式软件 | 刘博简历投递记录.xlsx / Sheet2 |
| 禾赛 | 禾赛科技 | 算法工程师（多传感器融合） | 刘博简历投递记录.xlsx / Sheet2 |
| 科大讯飞 | 科大讯飞 | C++开发工程师/运维开发工程师 | 刘博简历投递记录.xlsx / Sheet1 |
| 米哈游 | 米哈游 | 后端开发 | 刘博简历投递记录.xlsx / Sheet1 |
| 紫光 | 紫光 | 嵌入式/测试 | 刘博简历投递记录.xlsx / Sheet2 |
| 纳睿雷达 | 纳睿雷达 | 雷达目标数据处理（hr邮箱） | 刘博简历投递记录.xlsx / Sheet2 |
| 纵目科技 | 纵目科技 |  | 刘博简历投递记录.xlsx / Sheet2 |
| 经纬恒润 | 经纬恒润 | C++开发工程师 | 刘博简历投递记录.xlsx / 正式批 |
| 绿联 | 绿联 | 测试 | wyp.xlsx / 吴亚鹏测评 |
| 网易云音乐 | 网易云音乐 | 侧开 | wyp.xlsx / 吴亚鹏测评 |
| 网易互娱 | 网易互娱 | 游戏测试工程师 | wyp.xlsx / 吴亚鹏测评 |
| 网易雷火 | 网易雷火 | 软件开发-游戏测试方向 | 刘博简历投递记录.xlsx / Sheet1 |
| 美团 | 美团 | 软件开发-测试方向 | 刘博简历投递记录.xlsx / Sheet1 |
| 美的 | 美的 | C++/嵌软/信息化工程师(HR推荐的岗位，KPI) | 刘博简历投递记录.xlsx / Sheet3 |
| 群核信息 | 群核信息 | 测试 | wyp.xlsx / 吴亚鹏测评 |
| 联友科技 | 联友科技 | 软件测试 | wyp.xlsx / 吴亚鹏测评 |
| 联发科技 | 联发科技 | 软件开发工程师（无线通信方向） | 刘博简历投递记录.xlsx / Sheet1 |
| 联影集团 | 联影 | 测试（已挂），又投了软开 | 戴-投递情况.xlsx / 戴仕强测评 |
| 联想 | 联想 | C++开发工程师 | 刘博简历投递记录.xlsx / Sheet1 |
| 腾讯 | 腾讯 | 软件开发-测试方向 | 刘博简历投递记录.xlsx / Sheet1 |
| 腾讯云智 | 腾讯云智 | 后端 | 刘博简历投递记录.xlsx / Sheet2 |
| 航天811所 | 航天811所 | 嵌入式软件开发 | 刘博简历投递记录.xlsx / Sheet2 |
| 航天恒星科技 | 航天恒星科技 | 软件测试 | wyp.xlsx / 吴亚鹏测评 |
| 航天飞鹏-央企 | 航天飞鹏-央企 | xxx | 刘博简历投递记录.xlsx / Sheet2 |
| 艾为电子 | 艾为电子 | 软件开发 | 刘博简历投递记录.xlsx / Sheet1 |
| 芯原微电子 | 芯原微电子 | 软件工程师 | 刘博简历投递记录.xlsx / 正式批 |
| 芯合电子 | 芯合电子 | 软开 | 刘博简历投递记录.xlsx / Sheet2 |
| 英威腾 | 英威腾 | 嵌入式/测试 | 刘博简历投递记录.xlsx / Sheet2 |
| 英飞源技术 | 英飞源 | 嵌入式（hr邮箱） | 刘博简历投递记录.xlsx / Sheet2 |
| 荣湃半导体 | 荣湃半导体 | 应用工程师 | 刘博简历投递记录.xlsx / Sheet2 |
| 荣耀 | 荣耀 | 通用软件开发工程师 | 刘博简历投递记录.xlsx / Sheet1 |
| 莉莉丝 | 莉莉丝 | 测试 | wyp.xlsx / 吴亚鹏测评 |
| 菜鸟 | 菜鸟 | 自动驾驶测开(少量hc) | 刘博简历投递记录.xlsx / Sheet2 |
| 蔚来实习 | 蔚来 | 自动驾驶语义建图SLAM方向实习生 | 刘博简历投递记录.xlsx / Sheet2 |
| 虎牙 | 虎牙 | 侧开 | wyp.xlsx / 吴亚鹏测评 |
| 虹软科技 | 虹软科技 | C++开发工程师 | 刘博简历投递记录.xlsx / Sheet1 |
| 虾皮信息 | 虾皮信息 | 测试工程师 | wyp.xlsx / 吴亚鹏测评 |
| 蚂蚁集团 | 蚂蚁集团 | 测开(熟悉理论)/限投一个 | 刘博简历投递记录.xlsx / Sheet3 |
| 行芯科技 | 行芯科技 | 软件研发工程师 | 刘博简历投递记录.xlsx / 正式批 |
| 西山居 | 西山居 | 游戏开发、游戏测开 | 戴-投递情况.xlsx / 戴仕强测评 |
| 视源股份 | 视源股份 | 软件测试 | wyp.xlsx / 吴亚鹏测评 |
| 记忆科技 | 记忆科技 | 软件开发工程师 | 刘博简历投递记录.xlsx / 正式批 |
| 贝壳 | 贝壳 | C++开发工程师 | 刘博简历投递记录.xlsx / 正式批 |
| 超聚变 | 超聚变 | 软开 | 刘博简历投递记录.xlsx / Sheet3 |
| 越疆机器人 | 越疆机器人 | 嵌入式软件开发（ROS方向） | 刘博简历投递记录.xlsx / 正式批 |
| 达美盛 | 达美盛 |  | 刘博简历投递记录.xlsx / Sheet2 |
| 迅雷 | 迅雷 | 服务器开发、公众号 | 戴-投递情况.xlsx / 戴仕强测评 |
| 迈普 | 迈普 | 嵌入式/测试 | 刘博简历投递记录.xlsx / Sheet2 |
| 迈瑞医疗 | 迈瑞医疗 | 软测 | wyp.xlsx / 吴亚鹏测评 |
| 迪普科技 | 迪普科技 | 软件开发工程师 | 刘博简历投递记录.xlsx / 正式批 |
| 追觅 | 追觅 | 侧开 | wyp.xlsx / 吴亚鹏测评 |
| 途游 | 途游 | 测试 | wyp.xlsx / 吴亚鹏测评 |
| 速腾聚创 | 速腾聚创 | 软件开发 | 刘博简历投递记录.xlsx / Sheet2 |
| 重庆庆铃 | 重庆庆铃 | 软开 | 刘博简历投递记录.xlsx / Sheet2 |
| 重庆长安汽车 | 重庆长安汽车 | SLAM | 刘博简历投递记录.xlsx / Sheet2 |
| 金证科技 | 金证科技 | C++ | 刘博简历投递记录.xlsx / Sheet2 |
| 银星智能 | 银星智能 |  | 刘博简历投递记录.xlsx / Sheet2 |
| 锐捷 | 锐捷 | C++软开/自动化测开/限投两个 | 刘博简历投递记录.xlsx / Sheet3 |
| 锐捷网络 | 锐捷网络 | 嵌入式软件工程师 | 刘博简历投递记录.xlsx / 正式批 |
| 锐明技术 | 锐明技术 | 软件开发工程师 | 刘博简历投递记录.xlsx / 正式批 |
| 长园深瑞继保 | 长园深瑞继保 | 系统软件工程师 | 刘博简历投递记录.xlsx / 正式批 |
| 长安 | 长安 | 软件测试 | wyp.xlsx / 吴亚鹏测评 |
| 长川科技 | 长川科技 | 软件开发工程师 | 刘博简历投递记录.xlsx / 正式批 |
| 阳光电源 | 阳光电源 | 软测 | wyp.xlsx / 吴亚鹏测评 |
| 阿维塔 | 阿维塔 | 软件/ 系统测试 (国企带嵌) | 刘博简历投递记录.xlsx / Sheet3 |
| 阿里云尽早投 | 阿里云（侧开-北上深杭-8.5发布9.1结束）尽早投 | 侧开 | wyp.xlsx / 吴亚鹏测评 |
| 阿里国际 | 阿里国际 | 侧开 | wyp.xlsx / 吴亚鹏测评 |
| 阿里巴巴 | 阿里巴巴 | 开发 | 刘博简历投递记录.xlsx / Sheet2 |
| 阿里平头哥15天内投 | 阿里平头哥（侧开-上海-8.8）15天内投 | 美团（测开-深圳-7.29发布）这两天就投 | wyp.xlsx / 师兄 |
| 陶天集团五天内投 | 陶天集团（侧开-上海-8.4发布）五天内投 | 灵犀互娱（游戏侧开-广州-8.5发布）尽早投 | wyp.xlsx / 师兄 |
| 零跑科技 | 零跑科技 | 嵌入式软件工程师 | 刘博简历投递记录.xlsx / 正式批 |
| 霸王茶姬 | 霸王茶姬 | 侧开 | wyp.xlsx / 吴亚鹏测评 |
| 韶音科技 | 韶音科技 | 嵌入式软件工程师 | 刘博简历投递记录.xlsx / Sheet1 |
| 顺丰 | 顺丰 | 测试开发 | 刘博简历投递记录.xlsx / Sheet2 |
| 顺捷 | 顺捷 | 测试 | wyp.xlsx / 吴亚鹏测评 |
| 顺网科技 | 顺网科技 | 软测 | wyp.xlsx / 吴亚鹏测评 |
| 领行科技 | 领行科技 | 测试 | wyp.xlsx / 吴亚鹏测评 |
| 飞猪 | 飞猪 | 开发 | 刘博简历投递记录.xlsx / Sheet2 |
| 飞羽科技 | 飞羽科技 | 游戏测试 | wyp.xlsx / 吴亚鹏测评 |
| 饿了么 | 饿了么 | 测试开发工程师 | 刘博简历投递记录.xlsx / Sheet1 |
| 高德地图 | 高德地图 | C++开发-导航规划 | 刘博简历投递记录.xlsx / Sheet2 |
| 麦科田 | 麦科田 | 软测 | wyp.xlsx / 吴亚鹏测评 |
| 麦米电气 | 麦米电气 | 软件测试 | wyp.xlsx / 吴亚鹏测评 |
| 鼎桥通信 | 鼎桥通信 | 软件开发工程师C/C++ | 刘博简历投递记录.xlsx / 正式批 |
| 鼎甲科技 | 鼎甲科技 |  | 刘博简历投递记录.xlsx / 正式批 |
| 龙旗科技nksb | 龙旗科技nksb | 影像工程师 | 刘博简历投递记录.xlsx / Sheet2 |
| 长鑫存储 | `beisen` | https://cxmt.zhiye.com/campus/jobs |
| 金智科技 | `render` | https://campus.51job.com/wiscom2026/about1.html |
| 马上消费金融 | `feishu` | https://weikezhijia.jobs.feishu.cn/s/iMRaH4GB |
| 飞鱼科技 | `moka` | https://app.mokahr.com/m/campus-recruitment/feiyu/142123?recommendCode=DSF2Kc4p&hash=%23%2Fjobs#/jobs |
| 金发科技 | `beisen` | https://kingfa.zhiye.com/campus/jobs |
| 金山办公 | `moka` | https://join.wps.cn/campus-recruitment/wps/41436#/jobs |
| 赛里斯 | `beisen` | https://sokon.zhiye.com/campus/jobs |
| 高途 | `moka` | https://app.mokahr.com/campus_apply/bjhl |
| 邦普电脑技术开发 | `render` | https://www.punp.com/xyzp/index.aspx |
| 远景科技 | `moka` | https://app.mokahr.com/m/campus_apply/envisiongroup/43123?recommendCode=DS1ayUbm&hash=%23%2Fjobs#/jobs |
| 超参数科技 | `render` | https://hr.chaocanshu.cn/campus_apply/chaocanshu/45562#/ |

## 未接入 / 需要继续查找或验证链接
| 公司 | Excel 岗位/备注 | 来源 |
| --- | --- | --- |
| 博仕康科技 | 后端c++（邮箱），图像分割（待投） | 戴-投递情况.xlsx / 戴仕强测评:337 |
| 国家电投-湛江核电 | 国聘已投 | 刘博简历投递记录.xlsx / Sheet3:167 |
| 国家金融科技认证 |  | 戴-投递情况.xlsx / 戴仕强测评:482 |
| 国有行 |  | 戴-投递情况.xlsx / 戴仕强测评:444 |
| 国汽智控 | 目前只有app的社招 | 戴-投递情况.xlsx / 戴仕强测评:497 |
| 大医集团 | 软件（邮箱） | 戴-投递情况.xlsx / 戴仕强测评:339 |
| 大唐高鸿智联科技 |  | 戴-投递情况.xlsx / 戴仕强测评:452 |
| 大陆汽车重庆研发 | 只在前程无忧上有社招，岗不对口 | 戴-投递情况.xlsx / 戴仕强测评:376 |
| 奥马冰箱 | 不行 | 戴-投递情况.xlsx / 戴仕强测评:49 |
| 富民银行 | 只有app的社招 | 戴-投递情况.xlsx / 戴仕强测评:405 |
| 广州铁科智控 | C++开发/测试/应届生网 | 刘博简历投递记录.xlsx / Sheet3:136 |
| 广新控股集团 | 管培生/公众号投/国企版(微+小写) | 刘博简历投递记录.xlsx / Sheet3:188 |
| 广晟控股集团 | 研发工程师/研发助理/（国企版带嵌） | 刘博简历投递记录.xlsx / Sheet3:182 |
| 德勤GDC | 公众号只有24校招，等 | 戴-投递情况.xlsx / 戴仕强测评:407 |
| 忽米网 | 目前只有app的社招 | 戴-投递情况.xlsx / 戴仕强测评:389 |
| 懂车帝 | 字节旗下，之前那个，无研发 | 戴-投递情况.xlsx / 戴仕强测评:368 |
| 成都民航空管科技 | C++开发（QT简历） | 戴-投递情况.xlsx / 戴仕强测评:228 |
| 撼地数智 | 只发布了社会招聘（python后端等） | 戴-投递情况.xlsx / 戴仕强测评:418 |
| 数字重庆大数据应用发展 |  | 戴-投递情况.xlsx / 戴仕强测评:484 |
| 数码电子 | C++软开、运维开发 | 戴-投递情况.xlsx / 戴仕强测评:195 |
| 日丰 | IT岗（应届生） | 戴-投递情况.xlsx / 戴仕强测评:305 |
| 智慧星空 | 软件开发 | 刘博简历投递记录.xlsx / 正式批:253 |
| 未尔科技 | C++开发（邮箱投递） | 戴-投递情况.xlsx / 戴仕强测评:174 |
| 核桃编程 | python老师（7k左右，太低） | 戴-投递情况.xlsx / 戴仕强测评:161 |
| 桑达无线 | 软件开发（C方向） | 刘博简历投递记录.xlsx / 正式批:175 |
| 桑达无线通讯 | 软测（强度低、邮箱） | 戴-投递情况.xlsx / 戴仕强测评:292 |
| 欧冶半导体 | 软件/测试 投递：career@oritek.com.cn | 刘博简历投递记录.xlsx / Sheet3:142 |
| 欧菲斯集团 | 暂无 | 戴-投递情况.xlsx / 戴仕强测评:412 |
| 武汉精密电子 | 软开 | 戴-投递情况.xlsx / 戴仕强测评:158 |
| 民生银行 | 金融科技（数据分析） | 戴-投递情况.xlsx / 戴仕强测评:149 |
| 汇明光电 | 算法 | 戴-投递情况.xlsx / 戴仕强测评:81 |
| 法睿兰达 | 软件开发/SLAM/嵌软/公众号投递 | 刘博简历投递记录.xlsx / Sheet3:131 |
| 派诺科技 | 嵌软/公众号投递 | 刘博简历投递记录.xlsx / Sheet3:115 |
| 海德斯通信 | 应用开发工程师 | 刘博简历投递记录.xlsx / 正式批:166 |
| 海悟集团 | IT类，网易邮箱发的 | 戴-投递情况.xlsx / 戴仕强测评:138 |
| 海量数据 | C++开发 | 戴-投递情况.xlsx / 戴仕强测评:327 |
| 海雀科技 | 初级嵌入式/邮箱投递zhaopin@haique-tech.com | 刘博简历投递记录.xlsx / Sheet3:128 |
| 润通 | IT岗（邮箱） | 戴-投递情况.xlsx / 戴仕强测评:293 |
| 深圳巴士集团 | 线下:技术管理岗,网申： | 刘博简历投递记录.xlsx / Sheet3:152 |
| 深圳谱程未来科技 | 软件 | 刘博简历投递记录.xlsx / Sheet3:126 |
| 湛江核电 | 生产助理专工/线下，网申 | 刘博简历投递记录.xlsx / Sheet3:150 |
| 特斯联 | 目前只有app的社招 | 戴-投递情况.xlsx / 戴仕强测评:388 |
| 特隆美储能 | 软件工程师 | 刘博简历投递记录.xlsx / 正式批:192 |
| 珠海市杰理科技股 | 软件、公众号 | 刘博简历投递记录.xlsx / Sheet3:179 |
| 瑞能科技 | C++开发、嵌入式开发 | 戴-投递情况.xlsx / 戴仕强测评:73 |
| 盛宝金融 | 目前只有社招 | 戴-投递情况.xlsx / 戴仕强测评:381 |
| 睿蓝汽车 | 暂无 | 戴-投递情况.xlsx / 戴仕强测评:496 |
| 福耀玻璃 | 产品开发（非IT） | 戴-投递情况.xlsx / 戴仕强测评:148 |
| 禾多 | 可视化软件开发 | 戴-投递情况.xlsx / 戴仕强测评:289 |
| 科力锐 | 技术支持工程师（只有市场部招聘，所以结束） | 戴-投递情况.xlsx / 戴仕强测评:309 |
| 科锐国际-科瑞国际校园招聘公众号 | 无对应岗位 | 戴-投递情况.xlsx / 戴仕强测评:10 |
| 秦川集团技术研究院 | 软件开发、网易邮箱投递 | 戴-投递情况.xlsx / 戴仕强测评:60 |
| 索贝 | 开发工程师（简历填写的简易，内容少没附件） | 戴-投递情况.xlsx / 戴仕强测评:198 |
| 绵阳高新科技城 | QT开发 | 戴-投递情况.xlsx / 戴仕强测评:276 |
| 联合光电 | 嵌入式 | 刘博简历投递记录.xlsx / Sheet2:208 |
| 联合微电子 | 嵌入式岗，寄 | 戴-投递情况.xlsx / 戴仕强测评:454 |
| 联合电子 | 软开 | 刘博简历投递记录.xlsx / Sheet3:175 |
| 联基集团 | 技术类、网易邮箱投递的 | 戴-投递情况.xlsx / 戴仕强测评:50 |
| 联通西部云计算中心 |  | 戴-投递情况.xlsx / 戴仕强测评:483 |
| 舜云 | 软开（QT简历，邮箱） | 戴-投递情况.xlsx / 戴仕强测评:284 |
| 航天云网科技 |  | 戴-投递情况.xlsx / 戴仕强测评:478 |
| 航天新通科技 |  | 戴-投递情况.xlsx / 戴仕强测评:473 |
| 航天智信 | 软件研发（C++） | 戴-投递情况.xlsx / 戴仕强测评:266 |
| 航天科工 | 软件开发 | 刘博简历投递记录.xlsx / 正式批:215 |
| 艾目易科技 | 软件工程师 | 刘博简历投递记录.xlsx / 正式批:206 |
| 芯上微装 | 应用开发工程师 | 刘博简历投递记录.xlsx / 正式批:174 |
| 西南证券 | 还没开始，去年10月开始 | 戴-投递情况.xlsx / 戴仕强测评:371 |
| 西部笔迹大数据研究院 | 算法工程师（算法简历） | 戴-投递情况.xlsx / 戴仕强测评:283 |
| 西部航空 |  | 戴-投递情况.xlsx / 戴仕强测评:447 |
| 觉晓教育 |  | 戴-投递情况.xlsx / 戴仕强测评:391 |




## 已找到链接但不能直接作为抓取入口
| 公司 | 原因 | URL | Excel 岗位/备注 |
| --- | --- | --- | --- |
| 思特奇 | 官方 Hotjob 候选入口使用 hotjob/render 爬虫均返回 0 岗 | https://wecruit.hotjob.cn/SU645b0d18bef57c0907e9fbc8/pb/school.html | C++开发、测试（公众号） |
| 华夏航空 | 官网/候选入口使用当前 render 爬虫返回 0 岗，未验证到可直接抓取的校招岗位列表 | https://www.chinaexpressair.com/ | 未开始 |
| 特发集团 | 官方智联校招候选入口使用当前 render 爬虫返回 0 岗 | https://sdg.zhaopin.com/ | 软件/软件助理/智联 |
| 科华数据 | 官方页面只返回分类/导航标签，不是真实校招岗位行 | https://www.kehua.com.cn/join | 软测 |
| 深圳市信维通信 | Hotjob 候选入口返回社招/经验岗，不是干净的校招岗位 | https://sc.hotjob.cn/wt/sunway/web/mobMobileWebsite/index/listFavorateN1?brandCode=1 | 嵌软管培生/应届生网 |
| 国家开发银行重庆分行 | 官方智联校招候选入口使用当前 render 爬虫返回 0 岗 | https://cdb2026.zhaopin.com/index.html |  |
| 叠拓信息技术 | 只找到旧活动页或第三方信息，未验证到当前可直接抓取的官方岗位列表入口 | https://campus.51job.com/tieto2020 | C++软开（无线通信方向，8-13k 不行）、填表报名 |
| 宝尊电商 | 官方前程无忧校招候选入口使用当前 render 爬虫返回 0 岗 | https://campus.51job.com/baozun2026/join.html | 测试（垃圾简历填写） |
| 湖南三湘银行 | 官方前程无忧校招候选入口使用当前 render 爬虫返回 0 岗 | https://campus.51job.com/csxbank2026/ | 科技类-管培生（不去） |
| 星宇车灯 | 官方飞书校招候选入口过滤分类标签后返回 0 岗；飞书专用爬虫在旧版 DOM 上超时 | https://g86y49ibp5.jobs.feishu.cn/xingyuxiaozhao | Linux软件开发工程师 |
| 华润电力 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://crc.wintalent.cn/wt/CRP/web/index/campusGuidePageN300 |  |
| 华阳多媒体 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://www.adayome.com/JobPosting_list.html | MCU软件工程师 |
| 精智达 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://campus.51job.com/jingzhida2025 | 软件/测开/嵌软/应届生网 |
| 同为股份 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://www.nowcoder.com/community/1245 | 软开（C++、邮箱投递） |
| 华润微电子重庆有限公司 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://www.crmicro.com/contact/ |  |
| 深圳能源集团 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://campus.51job.com/szny2026/job.html | 系统应用开发/智联 |
| 友塔游戏 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://www.yottagames.com.cn/campus | 开发、游戏开发、群表 |
| 吉芯科技 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | http://campus.51job.com/jxkj2025 |  |
| 埃克光电 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://career.i-tek.cn/front.home.index/schoolIndex | 软开、图像算法 |
| 江苏通信服务 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://campus.51job.com/ccsjs/index.html | 软开 |
| 国家能源集团 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://zhaopin.chnenergy.com.cn/recTypeSerch?kinds=1&schType=2 | 热控检修 |
| 华夏银行 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://hxb.hotjob.cn/ ; https://www.hxb.com.cn/jrhx/cpyc/xyzp/index.shtml | MT岗-信息科技专业：无法投递 |
| 南方电网 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://zhaopin.csg.cn/#/campusRecruitment | 信息通信业务 |
| 南网数字 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://zhaopin.csg.cn/#/campusRecruitment | 信息通讯（填表投递，水） |
| 广州地铁集团 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://gzmetro.zhiye.com/campus ; https://gzmtr.zhaopin.com/ | 自动化技术 |
| 芯恩 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://siencampus.hotjob.cn/ | 智能制造工程师 |
| 芯讯通 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://cn.simcom.com/xiaozhao.html | 软件测试（工资低：7-15w） |
| 小度 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://talent.baidu.com/jobs/trend | C++开发 |
| 猛玛 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://hollyland.zhiye.com/campus/jobs | Linux应用/MCU软件 |
| 虹科电子科技 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://job.hkaco.com/recruitment-2/ | 自动驾驶/汽车软开/解决方案（国企版简历） |
| 莱迪思 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://www.latticesemi.com/zh-CN/About/Jobs |  |
| 西安三星电子研究所 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://companyadc.51job.com/companyads/ads/37/36379/36378706/index.htm | 测开：前程无忧 |
| 联合汽车电子 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://campus.51job.com/uaes2026/mobile/uaes-about.html | 嵌入式软件开发（测试简历、应届生app） |
| 禾迈电力电子 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://app.mokahr.com/campus_apply/hoymiles/70377#/jobs | 嵌入式软件工程师 |
| 科远智慧科技 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://sciyon.zhiye.com/campus/jobs | C++工程师 |
| 积成电子 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://ieslab.zhaopin.com/ | C++工程师 |
| 润科通用 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | http://zhaopin.runketongyong.com | 软开 |
| 深圳巨烽 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://jingxinpharm.zhiye.com/jobs?KeyWords=%E6%B7%B1%E5%9C%B3%E5%B7%A8%E7%83%BD | 软件(公众号投递) |
| 火羽科技 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://campus.huoyugame.com/ | 服务端开发、运维 |
| 点点互动 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://career.centurygames.cn/campus ; https://centurygame.zhiye.com/ |  |
| 南京银行 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://job.njcb.com.cn/ | 技术部:未投递 |
| 招商银行海口分行 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://cmb-recruitment-mobile.paas.cmbchina.com/positionSchool | 信息技术类 |
| 浪潮 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://career.inspur.com/campus2026/campus.html | 软件 |
| 爱立信 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://www.moseeker.com/ericsson | 软件工程师/10.22号宣讲 |
| 法奥机器人 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://www.frtech.fr/JOIN | 应用软件工程师 |
| 深圳宏电 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://www.hongdian.com/ | 嵌软（硕士15-40w） |
| 星尘智能 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://astribot.com/ | 感知算法/嵌软 |
| 有为信息 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://www.yuweitek.com/ | C++开发工程师 |
| 毫末智行 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://haomo.jobs.feishu.cn/campus | 泊车C++开发/感知算法/限两个 |
| 同元软控 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://app.mokahr.com/campus-recruitment/tongyuan/45781#/ | C++、成绩单，已提交 |
| 数马电子 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://www.xhorse.com/ | C++开发工程师 |
| 天王星 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | shixiseng/nowcoder/university pages | C++开发、python大数据开发 |
| 天瑞星通 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | nowcoder/university pages | 测试应用工程师 |
| 未岚大陆 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://app.mokahr.com/campus-recruitment/weilandalu | C++工程师 |
| 库犸科技 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://mammotion.jobs.feishu.cn/campus_recruitment | 测试工程师 |
| 概伦电子 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://www.primarius-tech.com/training/job.html | C++开发工程师 |
| 杉岩数据 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://www.szsandstone.com/join-us | 存储开发工程师 |
| 永联科技 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://www.szwinline.com/Join_us.html | 嵌入式软件 |
| 海光信息 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://campus.51job.com/hygon2026/ | cpu软件开发工程师 |
| 歌尔股份 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://goertek.hotjob.cn/ | 应用软件开发工程师 |
| 法雷奥 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://valeo.gllue.com/portal/campusposition/list | 软件（视觉、自驾）/测试（应届生网） |
| 华芯巨数 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://app.mokahr.com/m/campus_apply/huaxinjushu/36809 | 软件开发 |
| 和利时 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://campus.hollysys.net | 工业算法、软件工程师 |
| 四方继保 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://sf-auto1.zhiye.com/campus/jobs | 嵌入式软件工程师 |
| 多益网络 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://xz.duoyi.com/v40/ | 服务端开发 |
| 收钱吧 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://shouqianba.zhiye.com/campus/jobs | 测开 |
| 拉普拉斯新能源科技 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://wecruit.hotjob.cn/SU64ec16d96202cc142aaa3ef3/mc/position/campus | 软件开发/公众号投递 |
| 招银科技 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://cmbnt.cmbchina.com | 测开（测开简历） |
| 国电南自51job | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://campus.51job.com/SAC/index1.html | 软件工程师 |
| 星宇股份 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://g86y49ibp5.jobs.feishu.cn/xingyuxiaozhao | 软件工程师（SOC方向） |
| 小熊博望 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://rqqmslsz9y.jobs.feishu.cn/referral/campus/m/position?token=MzsxNzIwNDIwNDQ3Mzg1OzY5NzQzMDY5MTc2NjEyNzk3NTc7MDsx | ios工程师 |
| 宇视科技 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://talent.uniview.com/#/campus/jobs | C++工程师 |
| 帆软 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://join.fanruan.com/campus | 后台开发工程师 |
| 安路科技 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://app.mokahr.com/m/campus-recruitment/anlogic/46366 | 软开，上传本科成绩单多半寄 |
| 三环集团 | personal center / delivery record / success page | https://hr.cctc.cc/success | 机器视觉、机械研发 |
| 中国核工业集团 | personal center / delivery record / success page | https://cnnc.zhiye.com/Portal/Resume/ResumeItem | 软件开发/(国企带嵌) |
| 华夏银行-华夏银行公众号、 | personal center / delivery record / success page | https://wecruit.hotjob.cn/SU645b0d18bef57c0907e9fbc8/pb/account.html#/myDeliver | 经办岗-信息科技专业，类似于助手？ |
| 庆铃汽车，长安汽车，长安福特，长安马自达，力帆汽车、长城，以及美国福特、韩国现代、日本五十铃 | third-party / WeChat / form / personal page | https://www.jobui.com/rank/company/view/chongqing/qiche/ |  |
| 美图 | personal center / delivery record / success page | https://campus.meitu.com/campus-recruitment/meitu/54138/#/candidateHome/applications | 视觉算法 |
| 速腾 | personal center / delivery record / success page | https://app.mokahr.com/campus-recruitment/robosense/69887#/candidateHome/applications |  |
| 阿丘科技 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://app.mokahr.com/campus_apply/aqrose/38322 ; https://app.mokahr.com/apply/aqrose/38321#/jobs | 视觉工程师 |
| 麦风科技 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://www.imyfone.cn/campus/ | C++开发工程师 |
| 长虹集团 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://group.changhong.com/jrzh_295/xyzp/ ; https://neo-net.com/list/?58_1.html= | 系统工程师 |
| 金山软件 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://campus.kingsoft.com | C++开发、测试 |
| 高斯宝电气 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://recruit.gospower.com/recruit/ | 软开(偏嵌)/测试 |
| 鹰角网络 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://app.mokahr.com/campus-recruitment/hypergryph/26326?locale=zh-CN | 服务器开发 |
| 隆鑫通用动力 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://www.loncinindustries.com/Group/Jobs.aspx?catid=7-74-102 | 软件研发类岗位 |
| 长龙铁路电子 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | http://sdg.zhaopin.com/ | 软件开发 |
| 高瓴联合 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | university/LinkedIn/third-party pages | 软件工程师 |
| 重庆诺源工业软件科技 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://neuetech.cn/index.php?a=index&c=Lists&m=home&tid=115 | 软开 |
| 重庆川仪自动化股份 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://www.cqcy.com/recruit/campus.html ; https://www.cqcy.com/content/details37_10331.html | 校园招聘 |
| 重庆声光电 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://campus.51job.com/cqsgd2018 | 校园招聘 |
| 重庆万国半导体科技 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | career.nankai.edu.cn / yingjiesheng | 暂无 |
| 重庆中科渝芯电子 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | eie.scu.edu.cn / jdjyw.jlu.edu.cn | 校园招聘 |
| 重庆华渝电气 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | bys.lnrc.com.cn aggregate | 校园招聘 |
| 重庆壹零空间 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://www.onespacechina.com/ | 等 |
| 达实智能 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://www.chn-das.com/CampusRecruitment/ | 嵌软 |
| 迈克生物 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://www.maccura.com/jiaru/ | C++开发、软测 |
| 道恩集团 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | university / yingjiesheng pages | 报名形式 |
| 象帝先计算技术 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://www.xdxct.com/jobs | 只有23 |
| 赛乐医疗 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | wondercv / yingjiesheng / shushuqiuzhi | C++开发工程师 |
| 谱瑞集成电路 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://campus.51job.com/parade/jobs.html | 暂无 |
| 辰卓科技 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://www.cztek.com/lists/42.html ; https://hire.dingtalk.com/referralWebsite | 应用软件工程师 |
| 重庆春之翼 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://wecruit.hotjob.cn/SU6311b6cf0dcad4076d054b89/pb/school.html | 目前只有app的社招 |
| 重庆浪潮 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | http://career.inspur.com/campus2026/ | 软件实施工程师 |
| 重庆渝欧跨境 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://www.yuoucn.com/about | app校招/运营管培 |
| 进出口银行重庆分行 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://www.eximbank.gov.cn/info/notice/recruit/202510/t20251029_70302.html | 校园招聘 |
| 重庆中航建设集团 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://et.airchina.com.cn/cn/about_us/recruitment/ground_crew_info/184849.shtml | 校园招聘 |
| 重庆农商行 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://cqrcb2026.zhaopin.com/jobs/index.html | 还找不到信息 |
| 重庆华龙网集团 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | cqnews / bendibao / boss | 暂无 |
| 重庆太极实业 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://sinopharm2026.iguopin.com/job | 校园招聘 |
| 重庆小微企业融资 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://www.cqxwdb.com/ | 暂无 |
| 重庆小米消费金融公司 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://www.mixiaojin.com/ | 暂时没有样 |
| 重庆梧桐车联科技 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | niuqizp / shushuqiuzhi / boss | 暂无 |
| 重庆海装风电工程 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://zckj2026xiaoyuan.zhaopin.com/ | 校园招聘 |
| 重庆航天信息 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | sasac / niuqizp | 校园招聘 |
| 重庆航天工业 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | casic / sasac | 暂无 |
| 重庆航天火箭电子技术 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://www.iguopin.com/company?id=10685326364181964 | 校园招聘 |
| 重庆航空 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://www.chongqingairlines.cn/contactus/ground_job.html | 暂无 |
| 重庆药羚 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | liepin / boss | 暂无 |
| 重庆通信产业 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://campus.51job.com/cqccs2024/route.html | 校园招聘 |
| 重庆金美通信 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://www.iguopin.com/company?id=10685374176732243 | 校园招聘 |
| 重庆钢铁股份 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://www.cqgtjt.com/category/hire | 暂无 |
| 重庆铁马工业集团 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://zhaopin.nhrdc.cn | 校园招聘 |
| 重庆集诚汽车电子 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | wondercv / upjianli | 暂无 |
| 重庆飞象工业互联网 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | liepin / school news | 暂无 |
| 重庆鼎汇信息技术 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | boss | 暂无 |
| 重汽轻型汽车有限公司 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://zhaopin.sinotruk.com:8009 | 校园招聘 |
| 中国重型汽车集团 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://zhaopin.sinotruk.com:8009 | 校园招聘 |
| 中国信息通信研究院西部分院 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://www.cqcaict.ac.cn/job/ | 暂无 |
| 中国农业发展银行重庆分行 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://adbc2026.zhaopin.com/ | 校园招聘 |
| 中国兵器装备集团 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://zhaopin.nhrdc.cn/ | 校园招聘 |
| 中国华能-广东公司 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://zhaopin.chng.com.cn | 生产技术岗 |
| 中国大唐集团 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://zhaopin.china-cdt.com/ | 自动化 |
| 中物院软件中心 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://www.caep-scns.ac.cn/career | 测开 |
| 中国通信-广东南方通信 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://iter.stongyw.cn/web/school/job/index.html | 软件开发 |
| 中通服软件 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | nowcoder / yingjiesheng / boss | 软件测试工程师 |
| 中铁建设集团（ | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | 微信公众号/公告 | 工程管理 |
| 乐橙网络 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://job.imou.com/ | C++服务端/软测 |
| 乐牛游戏 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://campus.leniu.com/ | 游戏服务端开发 |
| 伯维存储 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://www.biwin.com.cn/jobs | 助理C++/python开发 |
| 云从科技 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://app.mokahr.com/campus_apply/cloudwalk/3810 | C++开发 |
| 伊士通 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | nowcoder / shushuqiuzhi | 软开、测试 |
| 会凌电子 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | uestc / zhipin | c语言开发工程师 |
| 位图/位图信息 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | search candidates | C++/芯片软件研发 |
| 佛吉亚 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://jobs.51job.com/campus/caCGwGYQJnBzxSNFQ1Vjc.html | 软件助理工程师 |
| 佛山照明 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | fslhrc@163.com / third-party | 研发储干 |
| 保融科技 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | nowcoder / fingard.com | 软件开发Java/Python |
| 信维通信 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://sc.hotjob.cn/wt/sunway/web/mobMobileWebsite/index/listFavorateN1?brandCode=1 | 嵌软 |
| 商汤 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://hr.sensetime.com/SU60fa3bdabef57c1023fc1cbc/pb/school.html | 暂无 |
| 山石网科 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | official Hotjob candidate | 软件研发工程师 |
| 完美世界 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://jobs.games.wanmei.com/school.html | 测开 |
| 南瑞继保 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://nrec.zhiye.com/campus | 软件研发 |
| 国科微/国科微电子 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://www.gokemicro.com/CampusRecruitment/index.aspx | 软件/测试 |
| 峰岹科技 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://www.fortiortech.com/joinus.html | 软件开发工程师 |
| 信通院工业互联网创新中心 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | search candidates | 暂无 |
| 华力微电子 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://www.nowcoder.com/enterprise/6716 | 系统开发与运维 |
| 华宇信息 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | nowcoder / school pages | 软开、软测 |
| 傲基科技 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | aukeys / liepin / shixiseng | 嵌入式软件 |
| 光庭信息 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | school / yingjiesheng / shushuqiuzhi | Python开发 |
| 冰川网络 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | search candidates | C++开发、游戏测试 |
| 北京佰才邦技术股份 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | niuqizp / nowcoder / school | 自动化测试/终端软件 |
| 北京华品博睿网络 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | search candidates | 测试工程师 |
| 北京大学重庆大数据研究院 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | search candidates | 暂无 |
| 北京理工大学重庆创新中心 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | search candidates | 暂无 |
| 北京范式转移科技有限公司 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | official page / third-party | 分析师 |
| 北京风丘科技 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | email / third-party | C++开发 |
| 北太振寰 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | search candidates | QT软件类 |
| 北斗星通智联 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | old pages | 暂无 |
| 北方信息控制研究院 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | search candidates | 暂无 |
| shopee | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://app.mokahr.com/campus_apply/shopee/2962 | 测试 |
| tap4fun | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://tap4fun.com/join-us | 服务端/客户端开发 |
| VeSync | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://vesync.zhiye.com/campus/jobs | 嵌入式开发 |
| 一微半导体 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://www.amicro.com.cn/ | SLAM/嵌软 |
| 4399/4399游戏 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://hr.4399om.com/weixin/ ; https://web.4399.com/campus/ | C++游戏开发 |
| OBSBOT 寻影 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://www.obsbot.cn/about/careers | C++开发工程师 |
| 上汽通用五菱 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://zhaopin.sgmw.com.cn/ | 重庆岗 |
| 2024高瓴联合 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | third-party / portfolio references | 暂无 |
| 29所 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | yingjiesheng / eoffcn / gaoxiaojob | 不知道什么岗 |
| 三未信安 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://www.sansec.com.cn/position.html | C++开发工程师 |
| 三峡银行 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://gzw.cq.gov.cn/gqzp/202604/t20260410_15604567_wap.html | 还没开始 |
| 上汽红岩汽车 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://www.saicmotor.com/chinese/rlzy/rcxq/xyzp/index_xz2.shtml | 校园招聘 |
| 中国移动/中国移动设计院西南分院 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://job.10086.cn/ | 解决方案/研发岗 |
| 中国银联股份 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://join.unionpay.com/wt/unionpayhr/mobweb/v8/index | 校园招聘 |
| 中广核 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://cgn.hotjob.cn/ | 中国广核新能源/集团 |
| 中移物联网 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://job.10086.cn/touch/personal/campus/campus_job_list.html?cId=77 | 软件工程师 |
| 上海电驱动 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | third-party/school pages | 基础软件工程师 |
| 东莞立讯精密 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://luxshare.hotjob.cn/ | 研发岗 |
| 东风日产 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://www.dongfeng-nissan.com.cn/about/recruit/campus | 新型技术研发 |
| 信锐技术 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://hr.sundray.com.cn | C++开发 |
| 优特电力 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | university / yingjiesheng pages | v |
| 亚控科技 | 已验证该入口，当前爬虫不能返回干净、可入库的校招岗位，暂不作为抓取入口 | https://www.kingview.com/news_info.php?num=1002736 | 软件开发C++ |

## 已排除或需要注意

- 2026-07-26：修复云端抓取异常。银河通用飞书校招页当前明确显示 0 个岗位；通用飞书爬虫现将“空列表且无分页控件”识别为正常完成，不再误报翻页失败。芯行纪改用专用 `xtimes` 爬虫，在官网 HTTPS/TLS 不稳定时通过只读文本解析通道读取同一官方页面，实抓 3 个校招岗位，均包含工作职责和资格要求；用户侧链接仍保留芯行纪官网，并标记为招聘列表。
- 2026-07-19：复核云端明确网络失败项。豹趣科技和正运动技术使用原官方校招入口重新验证，分别真实返回 5、8 个岗位，确认是瞬时网络故障；通用 Requests 与 Playwright 导航层已加入有限重试。芯行纪官方校招页仍有有效岗位内容，但官网 TLS/连接不稳定且暂未找到可靠官方替代入口，保留配置并由重试与健康审计持续监控，失败时不参与岗位下线判断。
- 2026-07-14：京东已修复岗位详情链接。旧爬虫误将 API 路径作为浏览器地址并标记为招聘列表；现改用 `https://campus.jd.com/#/details?type=...&id=...`，已在浏览器验证可打开具体岗位详情页。已迁移 70 条历史京东链接，并重抓入库；远景能源对应配置名为“远景科技”，使用已验证的 Moka 校招入口，已重抓并刷新报告。
- 2026-07-14：学而思腾讯文档条目同时包含“27届秋招提前批”标签，但官网也有明确 `27秋招` 正式岗位；已接入。岗位级规则会继续过滤实习和社招，方向外的教师岗位则仅保留筛选缓存、不入主岗位库。
- 2026-07-14：腾讯文档当前 13 家带 `27届秋招` 标签的公司已全部重抓：1,035 条原始岗位，过滤 107 条实习/非正式岗位；新增 72 条技术方向相关岗位且全部完成分析。基恩士当前抓到 2 条正式岗位（销售/校园大使），按当前技术方向筛选后无入库岗位，但爬虫和公司配置均正常。
- 2026-07-13：汇川技术已去除重复别名“汇川”，并将历史岗位统一归属为“汇川技术”。旧北森入口 `inovance.zhiye.com` 已过期，改用当前官网 `https://recruit.inovance.com/#/campus/jobs` 的公开 API；真实抓到 83 条 27 届校招，均有可直达详情链接、职责和任职要求。59 条方向相关岗位已入库并完成分析，24 条方向外岗位仅保留筛选缓存，不入库。
- 2026-07-10：已将验证失败、只返回分类/导航、社招、旧活动页、第三方摘要、二维码/微信/邮箱投递等入口归入“已找到链接但不能直接作为抓取入口”。
- 2026-07-10：腾讯官方接口当前混有“应届实习”和“应届毕业生”；爬虫已按项目标签过滤实习，真实验证保留 98 个正式岗位并清理历史实习记录。
- 2026-07-10：通用渲染、静态页、Hotjob、Bilibili、京东等无法提供稳定岗位详情链接的历史记录已标记为“招聘列表”，报告不再误标“去投递”；后续抓取会优先提取卡片中的真实详情链接。
- 2026-07-10：已清理 Excel 投递记录中的非公司噪声行，如电话面、笔试、一梯队、综合面、群面等。
- 2026-07-09 至 2026-07-10：已按公司别名、集团覆盖关系和实际爬取结果，分别归入已接入、已覆盖、待验证或不可直接接入。具体公司状态以上方表格为准。
- 后续新增公司时，必须先通过 `scripts/validate_company.py` 返回真实校招岗位，再写入 `config.yaml`；状态变更同步更新本文档。

## 腾讯文档自动接入状态（自动维护）
<!-- TENCENT_DOCS_AUTO_ONBOARDING_START -->
| 公司 | 腾讯文档链接 | 识别爬虫 | 状态 | 原因 |
| --- | --- | --- | --- | --- |
| MDPI | https://mdpi.cn/career/recruit/ca-recruit/position?email=3341436634@qq.com | `render` | 待人工接入 | render 返回 0 个岗位 |
| 三环集团 | https://hr.cctc.cc/school?sourceCode=869573&isRecommendCode=true | `render` | 待人工接入 | render 返回 0 个岗位 |
| 友塔游戏 | https://www.yottagames.com.cn/zh/internal-recommendation?token=480b3cd4a66863e82cb4e2bc1fd60a45-999602-1093058550&sub=077 | `render` | 待人工接入 | render 返回 0 个岗位 |
| 吉比特-雷霆游戏 | https://hr.g-bits.com/web/index.html#/post-web/post-list/?referralCode=FH386S | `render` | 待人工接入 | render 返回 0 个岗位 |
| 帆软 | https://t6ixa9nyl6.jiandaoyun.com/f/65e1a1308ce7672fded0f0cf?ext=CDSXJ | `render` | 待人工接入 | render 返回 0 个岗位 |
| 网易互联网 | https://campus.163.com/bolehtml/home?projectId=103&type=99&boleId=e1dd4e319e73d68a&boleType=2&signature=133fad406699e30097ce17c376500d6c&isShare=1 | `render` | 待人工接入 | render 返回 0 个岗位 |
| 联合利华 | https://xym.51job.com/VueData/neitui/user/#/?ehireid=8833740&prd=xyznt&ruid=162491&referrer=o0cn56rchou82EDTyJc1LYCY0txw | `render` | 待人工接入 | render 返回 0 个岗位 |
| 龙湖集团华西地区 | https://点击后面图片投递内推 | `render` | 待人工接入 | render 返回 0 个岗位 |
<!-- TENCENT_DOCS_AUTO_ONBOARDING_END -->
