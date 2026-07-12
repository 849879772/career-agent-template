import concurrent.futures
import json
import logging
import os
from pathlib import Path
import re
import requests
import time

import db as db_module

logger = logging.getLogger(__name__)

# 分析并发数（保守，适配 DeepSeek 限流；可用环境变量 ANALYZE_WORKERS 调）。
# 串行时分析吞吐 ~几百/次，远跟不上爬取量（~2000/天）；并发后吞吐翻数倍。
# call_deepseek_api 已对 429/5xx 指数退避重试，并发触发限流时自动退避。
_ANALYZE_WORKERS = max(1, int(os.environ.get("ANALYZE_WORKERS", "4")))

_DEFAULT_ANALYSIS = {
    "match_score": 0,
    "advantages": [],
    "gaps": [],
    "summary": "分析失败，请检查API配置",
    "recommendation": "考虑",
}

_DEFAULT_MODEL = "deepseek-v4-flash"
_DEFAULT_MAX_TOKENS = 1000
_ANTHROPIC_VERSION = "2023-06-01"
_DEEPSEEK_TOKEN_KEY = "DEEPSEEK_API_KEY"
_DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/anthropic").rstrip("/")
_DEEPSEEK_MESSAGES_URL = f"{_DEEPSEEK_BASE_URL}/v1/messages"


class LLMError(RuntimeError):
    pass


def _load_env_file() -> None:
    """Load project .env once, without requiring python-dotenv."""
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ[key] = value


def _deepseek_headers(token: str) -> dict:
    return {
        "anthropic-version": _ANTHROPIC_VERSION,
        "content-type": "application/json",
        "accept": "text/event-stream",
        "x-api-key": token,
    }


def _extract_text_from_json(data: dict) -> str:
    if isinstance(data, dict) and data.get("type") == "error":
        raise LLMError(json.dumps(data.get("error", data), ensure_ascii=False))
    blocks = data.get("content", []) if isinstance(data, dict) else []
    parts = [
        block.get("text", "")
        for block in blocks
        if isinstance(block, dict) and block.get("type") == "text"
    ]
    return "".join(parts).strip()


def _iter_sse_payloads(text_body: str):
    data_lines: list[str] = []
    for raw_line in text_body.splitlines():
        line = raw_line.rstrip("\r")
        if not line:
            if data_lines:
                yield "\n".join(data_lines).strip()
                data_lines = []
            continue
        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
    if data_lines:
        yield "\n".join(data_lines).strip()


def _read_deepseek_response(response) -> str:
    text_body = response.content.decode("utf-8", "replace")
    if "data:" in text_body:
        parts: list[str] = []
        err = ""
        saw_thinking = False
        for payload in _iter_sse_payloads(text_body):
            if not payload or payload == "[DONE]":
                continue
            try:
                event = json.loads(payload)
            except json.JSONDecodeError:
                continue
            event_type = event.get("type")
            if event_type == "error":
                err = json.dumps(event.get("error", event), ensure_ascii=False)
                continue
            if event_type == "message" and event.get("content"):
                parts.append(_extract_text_from_json(event))
                continue
            if event_type == "content_block_delta":
                delta = event.get("delta", {}) or {}
                if delta.get("type") == "text_delta":
                    parts.append(delta.get("text", ""))
                elif "text" in delta:
                    parts.append(str(delta.get("text") or ""))
                elif delta.get("type") == "input_json_delta":
                    parts.append(delta.get("partial_json", ""))
                elif delta.get("type") == "thinking_delta":
                    saw_thinking = True
                continue
            if event_type == "content_block_start":
                block = event.get("content_block", {}) or {}
                if block.get("type") == "text" and block.get("text"):
                    parts.append(str(block.get("text")))
        if err:
            raise LLMError(f"DeepSeek 流式返回错误: {err}")
        text = "".join(parts).strip()
        if text:
            return text
        if saw_thinking:
            raise LLMError("DeepSeek 只返回了 thinking 片段，未返回正文；请调大 max_tokens")

    try:
        return _extract_text_from_json(json.loads(text_body))
    except json.JSONDecodeError as e:
        raise LLMError(f"DeepSeek 响应无法解析: {text_body[:300]}") from e


def call_deepseek_api(
    system_prompt: str,
    user_message: str,
    model: str = _DEFAULT_MODEL,
    max_tokens: int = _DEFAULT_MAX_TOKENS,
    retries: int = 3,
) -> str:
    _load_env_file()
    token = os.environ.get(_DEEPSEEK_TOKEN_KEY, "").strip()
    if not token:
        raise LLMError("未找到 DEEPSEEK_API_KEY，请在系统环境变量或项目 .env 中配置")

    headers = _deepseek_headers(token)
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_message}],
        # 岗位筛选和评分只需要短 JSON。关闭思考模式可减少 token，
        # 也避免 reasoning 占满 max_tokens 后没有最终正文。
        "thinking": {"type": "disabled"},
        "stream": True,
    }
    for attempt in range(1, retries + 1):
        response = requests.post(
            _DEEPSEEK_MESSAGES_URL,
            headers=headers,
            json=payload,
            timeout=(15, 180),
            allow_redirects=False,
            stream=True,
        )
        if response.status_code in (429, 500, 502, 503, 504) and attempt < retries:
            wait = min(60, 2 ** attempt)
            logger.warning("API 返回 %d，%d 秒后重试（第 %d/%d 次）", response.status_code, wait, attempt, retries)
            time.sleep(wait)
            continue
        if response.status_code != 200:
            raise LLMError(f"DeepSeek API 返回 {response.status_code}: {response.text[:300]}")
        return _read_deepseek_response(response)


def call_claude_api(*args, **kwargs) -> str:
    """Backward-compatible name; the implementation now calls DeepSeek."""
    return call_deepseek_api(*args, **kwargs)


# 单次粗筛的标题条数上限：DeepSeek 的 reasoning token 会挤占输出空间，
# 小批量能显著降低 JSON 截断和长度不匹配概率。
_CLASSIFY_BATCH = 40

_RELEVANT_TITLE_PATTERNS = (
    "机器人", "视觉", "机器视觉", "感知", "slam", "点云", "图像", "算法", "cv", "计算机视觉",
    "具身", "强化学习", "世界模型", "仿真", "触觉", "灵巧手", "物理引擎",
    "vla", "vlm", "模仿学习", "端到端", "具身智能", "embodied",
    "机械臂", "控制", "运控", "运动控制", "运动规划", "自动化", "导航", "定位", "规控",
    "软件", "软件开发", "软件工程师", "后端", "客户端", "服务端", "开发", "研发", "c++", "c/c++",
    "python", "java",
    "前端", "全栈", "数据库", "内核", "编译", "架构师", "中间件",
    "ai", "人工智能", "大模型", "llm", "多模态", "模型", "训练", "推理",
    "智能体", "agent", "agentic", "rag", "function calling", "tool use",
    "robotics", "system engineer", "software engineer", "qa", "qe",
    "infra", "高性能计算", "信息安全", "网络工程师", "嵌入式", "系统", "linux",
    "测试", "软件测试", "测试开发", "测开", "开发测试", "sdet", "质量",
)

_IRRELEVANT_TITLE_PATTERNS = (
    "销售经理", "销售工程师", "销售专员", "销售代表", "客服", "法务", "财务", "会计", "hr", "人力", "行政", "物流",
    "运营", "电商", "品牌", "市场", "商务", "采购", "产品经理", "设计师",
    "主播", "编辑", "文案", "管培", "证券", "投资", "审计",
)


def _profile_directions(profile: dict) -> list[str]:
    directions = profile.get("directions") or []
    if not directions and profile.get("direction"):
        directions = [profile["direction"]]
    return [str(item).strip() for item in directions if str(item).strip()]


def _profile_target_roles(profile: dict) -> list[dict]:
    roles = profile.get("target_roles") or []
    normalized = []
    for role in roles:
        if isinstance(role, str):
            normalized.append({"name": role, "keywords": [role]})
            continue
        if isinstance(role, dict) and role.get("name"):
            normalized.append({
                "name": str(role["name"]),
                "keywords": [str(word) for word in role.get("keywords", []) if str(word).strip()],
            })
    return normalized


def _profile_relevant_keywords(profile: dict | None) -> tuple[str, ...]:
    if not profile:
        return ()
    words = list(profile.get("skills") or [])
    for role in _profile_target_roles(profile):
        words.extend(role["keywords"])
    return tuple(str(word).lower().strip() for word in words if str(word).strip())


def _profile_excluded_keywords(profile: dict | None) -> tuple[str, ...]:
    if not profile:
        return ()
    return tuple(
        str(word).lower().strip()
        for word in profile.get("excluded_title_keywords", [])
        if str(word).strip()
    )


def _target_roles_prompt(profile: dict) -> str:
    roles = _profile_target_roles(profile)
    if not roles:
        return "\n".join(f"  - {direction}" for direction in _profile_directions(profile))
    return "\n".join(
        f"  - {role['name']}：{', '.join(role['keywords'])}"
        for role in roles
    )


def _scoring_prompt(profile: dict) -> str:
    weights = profile.get("scoring_weights") or {
        "role_relevance": 35,
        "skill_match": 30,
        "responsibility_match": 20,
        "education_fit": 10,
        "location_preference": 5,
    }
    labels = {
        "role_relevance": "目标岗位相关度",
        "skill_match": "技术栈匹配度",
        "responsibility_match": "岗位职责匹配度",
        "education_fit": "学历与经验要求匹配度",
        "location_preference": "工作地点偏好",
    }
    return "\n".join(
        f"  - {labels.get(key, key)}：{value} 分"
        for key, value in weights.items()
    )


def _recommendation_for_score(score: int, profile: dict) -> str:
    thresholds = profile.get("score_thresholds") or {}
    recommend = int(thresholds.get("recommend", 80))
    consider = int(thresholds.get("consider", 60))
    if score >= recommend:
        return "推荐"
    if score >= consider:
        return "考虑"
    return "不推荐"


def classify_relevant_titles(
    titles: list[str],
    profile: dict,
    model: str = _DEFAULT_MODEL,
    max_tokens: int = _DEFAULT_MAX_TOKENS,
) -> list[bool]:
    """批量送岗位标题让 DeepSeek 粗筛是否值得详细分析。

    按 _CLASSIFY_BATCH 条/批分块多次调用（接入全部公司后标题可达数千，
    单次调用会撑爆请求体/响应 token），拼接各批 flags。每批失败时使用本地关键词兜底。

    Returns: 与 titles 等长的 bool 列表
    """
    if not titles:
        return []
    chunks = [titles[i:i + _CLASSIFY_BATCH] for i in range(0, len(titles), _CLASSIFY_BATCH)]
    if len(chunks) == 1:
        return _classify_batch(chunks[0], profile, model, max_tokens)
    # 多批并发（粗筛纯 API、不碰 DB）；executor.map 保持顺序拼接，flags 仍与 titles 对齐
    flags: list[bool] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=_ANALYZE_WORKERS) as ex:
        for batch_flags in ex.map(lambda ch: _classify_batch(ch, profile, model, max_tokens), chunks):
            flags.extend(batch_flags)
    return flags


def _classify_batch(
    titles: list[str],
    profile: dict,
    model: str = _DEFAULT_MODEL,
    max_tokens: int = _DEFAULT_MAX_TOKENS,
) -> list[bool]:
    """粗筛单批标题（≤ _CLASSIFY_BATCH 条）。出错时用本地关键词兜底，避免全量放行。"""
    if not titles:
        return []

    directions = " / ".join(_profile_directions(profile))
    roles_prompt = _target_roles_prompt(profile)
    excluded = ", ".join(profile.get("excluded_title_keywords", []))
    system_prompt = (
        "你是一个职业方向粗筛助手。候选人背景：\n"
        f"方向：{directions}\n"
        f"技能：{', '.join(profile.get('skills', [])[:20])}\n"
        f"求职类型：{profile.get('job_type', '校招')}\n\n"
        "候选人目标岗位（任一类相关即视为 true）：\n"
        f"{roles_prompt}\n\n"
        "下面是一批岗位标题。对每条判断：是否值得详细分析？\n"
        "判断标准：\n"
        "  - 与候选人上面任一目标类别有合理交集 → true\n"
        f"  - 命中排除关键词（{excluded}）或明显不相关 → false\n\n"
        f"输出严格的 JSON 数组，长度必须等于 {len(titles)}，每项为 true 或 false。\n"
        '例如：[true, false, true, false]\n'
        "不要输出任何其他文字、解释或 markdown 包裹。"
    )
    user_message = "\n".join(f"{i}. {t}" for i, t in enumerate(titles))

    try:
        content = call_deepseek_api(system_prompt, user_message, model, max_tokens).strip()
        flags = json.loads(_extract_json_array_text(content))
        if not isinstance(flags, list) or len(flags) != len(titles):
            raise ValueError(f"预筛响应长度 {len(flags) if isinstance(flags, list) else '非数组'} ≠ {len(titles)}")
        return [_merge_model_and_keyword_relevance(title, bool(flag), profile) for title, flag in zip(titles, flags)]
    except Exception as e:
        logger.error("DeepSeek 相关性预筛失败（使用本地关键词兜底）: %s", e)
        return [_keyword_relevance_fallback(title, profile) for title in titles]


def _extract_json_array_text(content: str) -> str:
    content = re.sub(r"^```(?:json)?\s*", "", content.strip())
    content = re.sub(r"\s*```$", "", content).strip()
    start = content.find("[")
    end = content.rfind("]")
    if start != -1 and end != -1 and end > start:
        return content[start:end + 1]
    return content


def _keyword_relevance_fallback(title: str, profile: dict | None = None) -> bool:
    normalized = (title or "").lower()
    excluded = _IRRELEVANT_TITLE_PATTERNS + _profile_excluded_keywords(profile)
    if any(word in normalized for word in excluded):
        return False
    relevant = _RELEVANT_TITLE_PATTERNS + _profile_relevant_keywords(profile)
    return any(word in normalized for word in relevant)


def _merge_model_and_keyword_relevance(
    title: str,
    model_flag: bool,
    profile: dict | None = None,
) -> bool:
    normalized = (title or "").lower()
    excluded = _IRRELEVANT_TITLE_PATTERNS + _profile_excluded_keywords(profile)
    if any(word in normalized for word in excluded):
        return False
    relevant = _RELEVANT_TITLE_PATTERNS + _profile_relevant_keywords(profile)
    return model_flag or any(word in normalized for word in relevant)


def analyze_job(
    job: dict,
    profile: dict,
    model: str = _DEFAULT_MODEL,
    max_tokens: int = _DEFAULT_MAX_TOKENS,
) -> dict:
    directions = " / ".join(_profile_directions(profile))
    roles_prompt = _target_roles_prompt(profile)
    scoring_prompt = _scoring_prompt(profile)
    cities = ", ".join(profile.get("preferred_cities", [])) or "不限"
    thresholds = profile.get("score_thresholds") or {"recommend": 80, "consider": 60}
    system_prompt = (
        "你是一个职业顾问。以下是候选人背景：\n"
        f"技能：{', '.join(profile.get('skills', []))}\n"
        f"方向：{directions}\n"
        f"学历：{profile.get('degree', '')}\n"
        f"求职类型：{profile.get('job_type', '校招')}\n"
        f"意向城市：{cities}\n\n"
        "候选人可投目标岗位（任一类匹配即可，不必全部对上）：\n"
        f"{roles_prompt}\n\n"
        "match_score 必须严格按以下权重逐项评分并求和（满分 100）：\n"
        f"{scoring_prompt}\n"
        f"推荐阈值：score >= {thresholds.get('recommend', 80)} 为推荐，"
        f"score >= {thresholds.get('consider', 60)} 为考虑，否则不推荐。\n"
        "请分析以下岗位与候选人的匹配度，仅输出JSON，不输出任何其他内容。\n"
        'JSON格式：{"match_score": 85, "advantages": ["优势1"], '
        '"gaps": ["缺失技能"], "summary": "一句话摘要", "recommendation": "推荐"}\n'
        "recommendation 只能是：推荐、考虑、不推荐 三选一。"
    )

    user_message = (
        f"公司：{job['company']}\n"
        f"岗位：{job['title']}\n"
        f"城市：{job.get('city', '')}\n"
        f"岗位描述：{job.get('jd_raw', '')[:2000]}"
    )

    try:
        content = call_deepseek_api(system_prompt, user_message, model, max_tokens).strip()

        # 去除可能的 markdown 代码块包裹（兼容 ```json 和 ``` 两种形式）
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
        content = content.strip()

        try:
            result = json.loads(content)
        except json.JSONDecodeError as e:
            logger.warning(
                "JSON解析失败 [%s %s]: %s | 原始内容: %.200s",
                job["company"], job["title"], e, content,
            )
            return dict(_DEFAULT_ANALYSIS)

        result.setdefault("match_score", 0)
        result["match_score"] = max(0, min(100, int(result["match_score"])))
        result.setdefault("advantages", [])
        result.setdefault("gaps", [])
        result.setdefault("summary", "")
        result["recommendation"] = _recommendation_for_score(result["match_score"], profile)

        return result

    except Exception as e:
        logger.error("DeepSeek API 分析失败 [%s %s]: %s", job["company"], job["title"], e)
        return dict(_DEFAULT_ANALYSIS)


def batch_analyze(
    jobs: list[dict],
    profile: dict,
    conn,
    model: str = _DEFAULT_MODEL,
    max_tokens: int = _DEFAULT_MAX_TOKENS,
) -> list[dict]:
    # 主线程预过滤已分析的（DB 读，避免重复调 API）
    pending = [j for j in jobs if not db_module.has_analysis(conn, j["id"])]
    if not pending:
        return []

    # analyze_job 是纯 DeepSeek API 调用（不碰 conn）→ 可并发；DB 写回放主线程串行（SQLite 安全）。
    results = []
    failed = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=_ANALYZE_WORKERS) as ex:
        fut_to_job = {ex.submit(analyze_job, j, profile, model, max_tokens): j for j in pending}
        for fut in concurrent.futures.as_completed(fut_to_job):
            job = fut_to_job[fut]
            try:
                analysis = fut.result()
            except Exception as e:  # noqa: BLE001
                logger.error("分析异常 [%s] %s: %s（下次重试）", job["company"], job["title"], e)
                failed += 1
                continue
            # 失败兜底分析不写库 → 下次 has_analysis 仍 False → 自动重试
            if analysis.get("summary") == _DEFAULT_ANALYSIS["summary"]:
                failed += 1
                continue
            db_module.save_analysis(conn, job["id"], analysis)  # 主线程，SQLite 安全
            results.append({"job_id": job["id"], "analysis": analysis})

    logger.info("细分析完成：成功 %d / 失败(下次重试) %d（并发 %d worker）",
                len(results), failed, _ANALYZE_WORKERS)
    return results
