# Career Agent：AI 校招情报系统

每天自动抓取数百家企业的校招岗位，过滤实习和社招，使用 DeepSeek 按个人技术栈分析匹配度，生成静态 HTML 报告，并可选推送到飞书。

本仓库是可直接复用的 GitHub Template。公司名单、爬虫和校招过滤规则已经配置好；每位使用者只需要填写自己的 `profile.yaml`、提供 DeepSeek API Key，再启用 GitHub Actions。

## 主要功能

- 多平台企业招聘爬虫，支持飞书、Moka、北森及企业专用招聘站。
- 正式校招过滤：实习和社招在入库前排除，往届岗位单独展示。
- 两阶段 AI 分析：先粗筛岗位标题，再对相关岗位计算匹配度。
- 增量运行：已有岗位复用分析结果，只分析新增岗位，节省 Token。
- 静态报告：岗位排行、今日新增、公司排行、往届校招和投递看板。
- GitHub Actions 定时运行，报告发布到 `gh-pages` 分支。
- 可接入 Cloudflare Pages 和飞书机器人。

## 使用前准备

- 一个 GitHub 账号。
- 一个可用的 DeepSeek API Key。
- 可选：飞书群自定义机器人 Webhook。
- 可选：Cloudflare 账号，用于部署公开报告页面。

## 一、从模板创建自己的仓库

1. 点击仓库右上角 **Use this template → Create a new repository**。
2. 填写自己的仓库名，例如 `my-career-agent`。
3. 建议选择 **Private**，岗位库和投递记录会保存在仓库中。
4. 点击 **Create repository**。

模板内的 `data/jobs.db` 是空数据库，`data/applications.json` 也是空列表，不包含模板作者的岗位或投递数据。

## 二、填写个人画像和评分标准

编辑仓库根目录的 `profile.yaml`。最常修改的是以下字段：

```yaml
degree: 研究生
job_type: 校招
target_cohort: 2027

skills: [C++, Python, Linux, ROS, PyTorch]

target_roles:
  - name: C++ 软件开发
    keywords: [C++, C/C++, 软件开发, 系统软件, 后端]
  - name: 大模型与智能体
    keywords: [大模型, LLM, RAG, Agent, Agentic]

preferred_cities: [北京, 上海, 深圳, 杭州]

scoring_weights:
  role_relevance: 35
  skill_match: 30
  responsibility_match: 20
  education_fit: 10
  location_preference: 5

score_thresholds:
  recommend: 80
  consider: 60
```

规则说明：

- `target_roles` 同时控制标题粗筛和详细分析，增加新方向时在这里添加。
- `excluded_title_keywords` 命中的岗位会优先排除。
- `scoring_weights` 必须合计为 `100`，否则程序会在启动时明确报错。
- `score_thresholds` 决定“推荐、考虑、不推荐”的分界线。
- `preferred_cities` 留空表示地点不限。

公司和抓取入口位于 `config.yaml`。默认配置可以直接使用；需要增删企业时再修改 `companies` 列表。

## 三、配置 GitHub Secrets

进入自己的仓库：**Settings → Secrets and variables → Actions**。

在 **Secrets** 中添加：

| 名称 | 是否必填 | 内容 |
|---|---:|---|
| `DEEPSEEK_API_KEY` | 是 | 自己的 DeepSeek API Key |
| `FEISHU_WEBHOOK` | 否 | 飞书自定义机器人的 Webhook URL |

不要把真实 Key 写入 `profile.yaml`、`config.yaml` 或 `.env.example`。

### 飞书机器人配置

1. 在飞书群中打开 **设置 → 群机器人 → 添加机器人 → 自定义机器人**。
2. 创建机器人并复制 Webhook。
3. 将完整 Webhook 保存为 GitHub Secret `FEISHU_WEBHOOK`。
4. 未配置时，流水线会正常运行，只是不发送飞书消息。

## 四、启用并首次运行 GitHub Actions

1. 打开仓库的 **Actions** 页面。
2. 如果 GitHub 提示工作流尚未启用，点击 **I understand my workflows, go ahead and enable them**。
3. 左侧选择 **Daily Recruitment Report**。
4. 点击 **Run workflow → Run workflow**。

首次运行需要安装浏览器并分析初始岗位，可能持续几十分钟到数小时。后续运行会复用岗位筛选和匹配结果，Token 消耗通常只来自新增岗位。

成功后可以看到：

- `main` 分支新增 `chore: update jobs.db ...` 提交。
- 自动创建 `gh-pages` 分支，其中包含 `index.html`。
- 配置了飞书时，群里会收到精简岗位报告。

工作流默认每天 UTC 22:00 触发，即北京时间次日 06:00。GitHub 可能延迟调度，实际完成时间取决于企业数量和网站响应。

## 五、部署 Cloudflare Pages

GitHub Actions 会把最新静态报告放到 `gh-pages` 分支。首次 Actions 成功后再配置 Cloudflare：

1. 登录 Cloudflare 控制台。
2. 进入 **Workers & Pages → Create application → Pages → Connect to Git**。
3. 授权 GitHub，并选择自己的 Career Agent 仓库。
4. Production branch 选择 `gh-pages`。
5. Framework preset 选择 `None`。
6. Build command 留空。
7. Build output directory 填 `.`。
8. 保存并部署。

部署完成后会得到类似地址：

```text
https://my-career-agent.pages.dev
```

回到 GitHub 仓库的 **Settings → Secrets and variables → Actions → Variables**，新增变量：

| 名称 | 值 |
|---|---|
| `REPORT_BASE_URL` | `https://my-career-agent.pages.dev` |

再次运行一次 Daily Recruitment Report。此后飞书中的“完整报告”会跳转到自己的 Cloudflare 页面。

如果暂时不部署 Cloudflare，系统会自动使用 GitHub Pages 地址：

```text
https://<GitHub用户名>.github.io/<仓库名>/index.html
```

## 六、本地运行

需要 Python 3.10 或更高版本。

```bash
git clone https://github.com/<你的用户名>/<你的仓库名>.git
cd <你的仓库名>
pip install -r requirements.txt
playwright install chromium
```

复制环境变量示例：

```powershell
Copy-Item .env.example .env
```

在 `.env` 中填写：

```dotenv
DEEPSEEK_API_KEY=你的API_Key
FEISHU_WEBHOOK=
REPORT_BASE_URL=
```

运行完整流程：

```bash
python main.py
```

只查看已有数据，不抓取、不调用 DeepSeek：

```bash
python view_all.py
```

启动本地投递管理页面：

```bash
python webapp.py
```

## 数据和费用说明

- `data/jobs.db` 保存岗位、分析结果和增量缓存，由 GitHub Actions 自动提交。
- `data/applications.json` 保存个人投递进度。
- 不要从不同设备同时修改 `jobs.db`，SQLite 二进制文件无法像文本一样合并。
- 不要强制推送 `main`，否则可能覆盖云端自动更新的数据库。
- 公开仓库会公开岗位分析和投递信息，个人部署建议使用私有仓库。
- DeepSeek 费用取决于新增岗位数；重复岗位不会重复进行详细分析。

## 修改公司名单

公司配置位于 `config.yaml`：

```yaml
companies:
  - name: 示例公司
    careers_url: https://example.com/campus
    crawler: render
```

新增企业前建议先执行：

```bash
python scripts/validate_company.py 示例公司 https://example.com/campus render
```

只有真实返回正式校招岗位的入口才应加入主配置。详细流程见 `docs/crawling_process.md`。

## 常见问题

### Actions 成功但没有收到飞书

检查 `FEISHU_WEBHOOK` 是否存在、机器人是否仍在群内，并在 Actions 日志中搜索“飞书推送”。飞书单条消息有大小限制，系统只展示部分高匹配岗位，完整列表在 HTML 报告中。

### Cloudflare 页面没有更新

确认最新 Actions 的 `Deploy report to gh-pages` 步骤成功，并确认 Cloudflare 的生产分支是 `gh-pages`，输出目录为 `.`。

### 第一次运行消耗时间很长

首次运行要抓取全部企业并分析初始岗位。后续运行会跳过已分析岗位，通常明显更快且更省 Token。

### 某些企业抓取不到岗位

招聘站可能存在地域限制、登录校验或 WAF。单家公司失败不会中断整个流程，也不会把该公司的岗位误判为全部下架。

## 测试

```bash
python -m pytest
python tests/smoke_crawlers.py unitree
```

第一条运行离线单元测试；第二条访问真实招聘网站，只建议在调试爬虫时运行。

## 项目结构

```text
crawlers/                 企业和招聘平台爬虫
data/jobs.db              岗位、分析结果和增量状态
data/applications.json    投递记录
profile.yaml              个人画像、目标岗位和评分规则
config.yaml               公司名单与模型参数
analyzer.py               DeepSeek 粗筛和匹配分析
main.py                   完整流水线入口
reporter.py               HTML 报告生成
notifier.py               飞书通知
.github/workflows/        定时抓取与报告部署
```

## 安全提示

- `.env` 已加入 `.gitignore`，不要手动强制提交。
- GitHub Secrets 不会出现在仓库文件中。
- 分享问题日志前，先检查其中是否含 Webhook、API Key 或个人投递信息。

## License

MIT
