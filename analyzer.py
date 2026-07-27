import concurrent.futures
from datetime import datetime, timedelta
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import requests
import time
import unicodedata

import db as db_module
import job_cohorts
import job_details
import job_filters

logger = logging.getLogger(__name__)

# 分析并发数（保守，适配 DeepSeek 限流；可用环境变量 ANALYZE_WORKERS 调）。
# 串行时分析吞吐 ~几百/次，远跟不上爬取量（~2000/天）；并发后吞吐翻数倍。
# call_deepseek_api 已对 429/5xx 指数退避重试，并发触发限流时自动退避。
_ANALYZE_WORKERS = max(1, int(os.environ.get("ANALYZE_WORKERS", "4")))
_JD_HYDRATE_WORKERS = max(1, int(os.environ.get("JD_HYDRATE_WORKERS", "2")))

ANALYSIS_VERSION = "match-v2.0"
SCREENING_VERSION = "target-tier-v2.0"

_SCORE_COMPONENT_LIMITS = {
    "core_direction": 25,
    "required_skills": 25,
    "project_evidence": 25,
    "engineering_stack": 15,
    "basic_criteria": 10,
}
_EVIDENCE_CAPS = {
    "direct": 100,
    "partial": 79,
    "adjacent": 64,
    "insufficient": 49,
}

_DEFAULT_ANALYSIS = {
    "match_score": 0,
    "advantages": [],
    "gaps": [],
    "summary": "分析失败，请检查API配置",
    "recommendation": "考虑",
}

_INCOMPLETE_JD_ANALYSIS = {
    "match_score": 0,
    "score_breakdown": {},
    "evidence": [],
    "evidence_level": "insufficient",
    "advantages": [],
    "gaps": ["JD 不完整，无法核对岗位核心要求"],
    "summary": "JD不完整，待补全后评分",
    "recommendation": "考虑",
    "analysis_status": "jd_incomplete",
}

_UNCONFIRMED_COHORT_ANALYSIS = {
    "match_score": 0,
    "score_breakdown": {},
    "evidence": [],
    "evidence_level": "insufficient",
    "advantages": [],
    "gaps": ["届别尚未由官方信息确认为 2027 届"],
    "summary": "届别待确认，不进行匹配评分",
    "recommendation": "未评估",
    "analysis_status": "cohort_unconfirmed",
}

_VALID_RECOMMENDATIONS = {"推荐", "考虑", "不推荐"}

_DEFAULT_MODEL = "deepseek-v4-flash"
_DEFAULT_ANALYSIS_MODEL = "deepseek-v4-pro"
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
_CLASSIFY_BATCH = 20

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

_SCREENING_TIERS = {"A", "B", "C"}
_DIRECT_CPP_TITLE_RE = re.compile(
    r"C\s*/\s*C\+\+|C\+\+|C语言|(?<![A-Za-z])C开发|"
    r"上位机|桌面端|PC客户端|客户端开发|"
    r"Windows(?:终端|系统).{0,8}(?:开发|软件)",
    re.I,
)
_ROBOT_VISION_TITLE_RE = re.compile(
    r"机器人视觉|机器视觉|视觉算法|点云|手眼标定|目标检测|"
    r"机械臂|机器人(?:软件|系统|算法)|SLAM|导航算法|运控|运动控制",
    re.I,
)
_TEST_TITLE_RE = re.compile(
    r"测试开发|测开|SDET|软件测试|自动化测试|算法测试|机器人测试|"
    r"智能测试|系统测试|研发测试|实验室测试|测试助理|测试\s*Infra|测试工程师",
    re.I,
)
_SOFTWARE_TITLE_RE = re.compile(
    r"软件(?:开发|研发|工程师|架构)|系统软件|平台软件|应用软件|"
    r"嵌入式(?:软件|开发|工程师)|客户端|服务端|后端|研发方向|计算机软件类",
    re.I,
)
_ASPIRATIONAL_TITLE_RE = re.compile(
    r"大模型|LLM|AIGC|智能体|Agent|RAG|具身|VLA|VLM|强化学习|"
    r"模仿学习|世界模型|多模态|AI(?:应用|算法|工程)|人工智能|"
    r"视觉|感知|机器人|机械臂|SLAM|控制|运动规划|仿真|"
    r"智能算法|图像算法|软件算法|AI\s*Infra",
    re.I,
)
_BROAD_TECHNICAL_TITLE_RE = re.compile(
    r"算法|软件|开发|研发|测试|嵌入式|系统|模型|AI|Python|Java|"
    r"前端|全栈|数据库|内核|编译|中间件|Infra|Linux|工程师|研究",
    re.I,
)
_OFF_TARGET_TECH_TITLE_RE = re.compile(
    r"Java|前端|Web|Android|iOS|Golang|Go语言|PHP|数据库|大数据|"
    r"数据分析|网络安全|信息安全|芯片|IC设计|FPGA|硬件|结构|电气|射频|天线",
    re.I,
)
_CPP_STACK_RE = re.compile(
    r"C\s*/\s*C\+\+|C\+\+|C语言|Qt|Linux|Ubuntu|Windows|多线程|"
    r"操作系统|客户端|桌面端",
    re.I,
)
_TEST_STACK_RE = re.compile(
    r"自动化|测试平台|测试框架|接口测试|性能测试|单元测试|集成测试|"
    r"测试工具|测试脚本|Python|C\+\+|代码|编程",
    re.I,
)
_ROBOT_VISION_EVIDENCE_RE = re.compile(
    r"ROS|SCARA|RealSense|深度相机|点云|手眼标定|YOLO|目标检测|"
    r"机械臂|机器人视觉|机器视觉|机器人|Gazebo|Isaac|运动规划|轨迹|抓取",
    re.I,
)


def _configured_title_keywords(profile: dict | None) -> tuple[str, ...]:
    if not profile:
        return ()
    words = []
    for role in profile.get("target_roles") or []:
        if isinstance(role, str):
            words.append(role)
        elif isinstance(role, dict):
            words.append(role.get("name", ""))
            words.extend(role.get("keywords") or [])
    return tuple(
        unicodedata.normalize("NFKC", str(word)).strip().casefold()
        for word in words
        if str(word).strip()
    )


def local_screening_tier(job: dict, profile: dict | None = None) -> str:
    """Return a conservative local A/B/C tier without calling an LLM.

    A means the title and available JD contain concrete evidence for this
    profile. B is a target or technical role that still needs a cheap review.
    C is a high-confidence non-target role.
    """
    title = unicodedata.normalize("NFKC", str(job.get("title") or "")).strip()
    body = unicodedata.normalize("NFKC", str(job.get("jd_raw") or "")).strip()
    if job_filters.is_job_record_noise({**job, "title": title}):
        return "C"
    normalized = title.casefold()
    excluded = tuple(
        unicodedata.normalize("NFKC", str(word)).strip().casefold()
        for word in (profile or {}).get("excluded_title_keywords", [])
        if str(word).strip()
    )
    if any(word in normalized for word in excluded):
        return "C"
    if any(word in normalized for word in _IRRELEVANT_TITLE_PATTERNS):
        return "C"

    combined = f"{title}\n{body[:6000]}"
    configured_match = any(
        word in normalized for word in _configured_title_keywords(profile)
    )
    if _DIRECT_CPP_TITLE_RE.search(title):
        return "A"
    if _ROBOT_VISION_TITLE_RE.search(title):
        return "A" if _ROBOT_VISION_EVIDENCE_RE.search(combined) else "B"
    if _TEST_TITLE_RE.search(title):
        return (
            "A"
            if _TEST_STACK_RE.search(combined)
            or (
                re.search(r"机器人|机械臂", title)
                and _ROBOT_VISION_EVIDENCE_RE.search(combined)
            )
            else "B"
        )
    if _OFF_TARGET_TECH_TITLE_RE.search(title):
        return "C"
    if (
        _ASPIRATIONAL_TITLE_RE.search(title)
        and _ROBOT_VISION_EVIDENCE_RE.search(combined)
    ):
        return "A"
    if _SOFTWARE_TITLE_RE.search(title):
        return "A" if _CPP_STACK_RE.search(combined) else "B"
    if _ASPIRATIONAL_TITLE_RE.search(title):
        if re.search(r"AI\s*Infra|AI应用|大模型应用|仿真平台|智能算法", title, re.I):
            if _CPP_STACK_RE.search(combined) or _TEST_STACK_RE.search(combined):
                return "A"
        return "B"
    if _BROAD_TECHNICAL_TITLE_RE.search(title):
        return "B"
    if configured_match:
        return "B"
    return "C"


def classify_job_tiers(
    jobs: list[dict],
    profile: dict,
    model: str = _DEFAULT_MODEL,
    max_tokens: int = _DEFAULT_MAX_TOKENS,
) -> list[str]:
    """Classify jobs as A (Pro), B (display only), or C (reject).

    Only ambiguous local-B jobs use Flash. Strong local matches and hard
    rejections avoid model cost entirely.
    """
    if not jobs:
        return []

    tiers = [local_screening_tier(job, profile) for job in jobs]
    ambiguous = [(index, jobs[index]) for index, tier in enumerate(tiers) if tier == "B"]
    if not ambiguous:
        return tiers

    chunks = [
        ambiguous[i:i + _CLASSIFY_BATCH]
        for i in range(0, len(ambiguous), _CLASSIFY_BATCH)
    ]
    with concurrent.futures.ThreadPoolExecutor(max_workers=_ANALYZE_WORKERS) as ex:
        batch_results = ex.map(
            lambda chunk: _classify_tier_batch(
                [job for _, job in chunk], profile, model, max_tokens
            ),
            chunks,
        )
        for chunk, result in zip(chunks, batch_results):
            for (index, _), tier in zip(chunk, result):
                tiers[index] = tier
    return tiers


def classify_relevant_titles(
    titles: list[str],
    profile: dict,
    model: str = _DEFAULT_MODEL,
    max_tokens: int = _DEFAULT_MAX_TOKENS,
) -> list[bool]:
    """Backward-compatible boolean wrapper around tiered screening."""
    jobs = [{"title": title, "jd_raw": ""} for title in titles]
    return [
        tier != "C"
        for tier in classify_job_tiers(jobs, profile, model, max_tokens)
    ]


def _classify_tier_batch(
    jobs: list[dict],
    profile: dict,
    model: str = _DEFAULT_MODEL,
    max_tokens: int = _DEFAULT_MAX_TOKENS,
) -> list[str]:
    """Use Flash only for one batch of ambiguous local-B jobs."""
    if not jobs:
        return []

    system_prompt = (
        "你是校招岗位的低成本分流器，不负责详细评分。候选人证据如下：\n"
        f"{_profile_context(profile)}\n\n"
        "将每个岗位分为一档：\n"
        "A：根据标题和JD摘要，核心要求已有直接项目证据，预计严格匹配分可达到60分，值得调用Pro。\n"
        "B：属于候选人目标或学习方向，但直接项目证据不足、JD信息不足或只能迁移，保留展示但不调用Pro。\n"
        "C：方向明显不符，包括纯Java/前端/硬件/结构/电气/产品/运营等非目标岗位。\n"
        "learning_targets和unverified_skills不能作为已掌握能力；仅有Python、Linux等通用词不能判A。\n"
        f"输出严格JSON数组，包含ID 1到{len(jobs)}，格式为"
        '{"id":1,"tier":"A"}。只输出JSON，不要解释。'
    )
    user_message = "\n".join(
        f"{index}. 标题：{job.get('title', '')}\n"
        f"JD摘要：{' '.join(str(job.get('jd_raw') or '').split())[:900]}"
        for index, job in enumerate(jobs, start=1)
    )
    fallback = [local_screening_tier(job, profile) for job in jobs]

    try:
        content = call_deepseek_api(system_prompt, user_message, model, max_tokens).strip()
        response_items = _parse_json_array(content)
        if not isinstance(response_items, list):
            raise ValueError("预筛响应不是数组")
        if response_items and all(isinstance(item, bool) for item in response_items):
            if len(response_items) != len(jobs):
                raise ValueError(f"旧式预筛响应长度 {len(response_items)} ≠ {len(jobs)}")
            return [
                _merge_screening_tier(job, "A" if flag else "C", profile)
                for job, flag in zip(jobs, response_items)
            ]

        tiers = list(fallback)
        seen_ids = set()
        for item in response_items:
            if not isinstance(item, dict):
                continue
            try:
                item_id = int(item.get("id"))
            except (TypeError, ValueError):
                continue
            if 1 <= item_id <= len(jobs):
                index = item_id - 1
                raw_tier = str(item.get("tier") or "").strip().upper()
                if raw_tier not in _SCREENING_TIERS and "relevant" in item:
                    raw_tier = "A" if bool(item.get("relevant")) else "C"
                if raw_tier in _SCREENING_TIERS:
                    tiers[index] = _merge_screening_tier(
                        jobs[index], raw_tier, profile
                    )
                seen_ids.add(item_id)
        if not seen_ids:
            raise ValueError("预筛响应没有有效岗位 ID")
        missing = len(jobs) - len(seen_ids)
        if missing:
            logger.warning("预筛响应遗漏 %d/%d 条，仅遗漏项使用本地B档兜底", missing, len(jobs))
        return tiers
    except Exception as e:
        logger.error("DeepSeek 分级预筛失败（保守保留为本地档位）: %s", e)
        return fallback


def _parse_json_array(content: str) -> list:
    content = re.sub(r"^```(?:json)?\s*", "", content.strip())
    content = re.sub(r"\s*```$", "", content).strip()
    start = content.find("[")
    if start == -1:
        raise ValueError("预筛响应中没有 JSON 数组")
    value, _ = json.JSONDecoder().raw_decode(content[start:])
    if not isinstance(value, list):
        raise ValueError("预筛响应不是数组")
    return value


def _keyword_relevance_fallback(title: str) -> bool:
    return local_screening_tier({"title": title, "jd_raw": ""}) != "C"


def _merge_model_and_keyword_relevance(title: str, model_flag: bool) -> bool:
    tier = _merge_screening_tier(
        {"title": title, "jd_raw": ""},
        "A" if model_flag else "C",
    )
    return tier != "C"


def _merge_screening_tier(
    job: dict, model_tier: str, profile: dict | None = None
) -> str:
    """Keep hard negatives and direct local evidence deterministic."""
    local_tier = local_screening_tier(job, profile)
    if local_tier == "C":
        return "C"
    if local_tier == "A":
        return "A"
    title = str(job.get("title") or "")
    if model_tier == "C" and (
        _SOFTWARE_TITLE_RE.search(title)
        or _TEST_TITLE_RE.search(title)
        or _ASPIRATIONAL_TITLE_RE.search(title)
    ):
        return "B"
    return model_tier if model_tier in _SCREENING_TIERS else "B"


def _stable_hash(value) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def jd_fingerprint(job: dict) -> str:
    return _stable_hash({
        "company": " ".join(str(job.get("company") or "").split()),
        "title": " ".join(str(job.get("title") or "").split()),
        "city": " ".join(str(job.get("city") or "").split()),
        "jd_raw": " ".join(str(job.get("jd_raw") or "").split()),
    })


def profile_fingerprint(profile: dict) -> str:
    return _stable_hash(profile)


def analysis_metadata(job: dict, profile: dict, model: str) -> dict:
    return {
        "analysis_version": ANALYSIS_VERSION,
        "jd_fingerprint": jd_fingerprint(job),
        "profile_fingerprint": profile_fingerprint(profile),
        "model": model,
    }


def needs_analysis(conn, job: dict, profile: dict, model: str) -> bool:
    metadata = analysis_metadata(job, profile, model)
    return not db_module.analysis_is_current(conn, job["id"], **metadata)


def _profile_context(profile: dict) -> str:
    matching = profile.get("matching") or {}
    if not matching:
        return (
            f"目标方向：{profile.get('direction', '')}\n"
            f"候选人自述技能：{', '.join(profile.get('skills', []))}\n"
            "注意：未给出项目证据或熟练度的技能只能视为部分证据。"
        )
    return json.dumps(
        {
            "primary_directions": matching.get("primary_directions", []),
            "secondary_directions": matching.get("secondary_directions", []),
            "project_evidence": matching.get("project_evidence", []),
            "supporting_skills": matching.get("supporting_skills", []),
            "learning_targets": matching.get("learning_targets", []),
            "unverified_skills": matching.get("unverified_skills", []),
            "degree": profile.get("degree", ""),
            "job_type": profile.get("job_type", ""),
        },
        ensure_ascii=False,
        indent=2,
    )


def _score_component_limits(profile: dict) -> dict[str, int]:
    configured = profile.get("score_component_limits") or {}
    if set(configured) != set(_SCORE_COMPONENT_LIMITS):
        return dict(_SCORE_COMPONENT_LIMITS)
    try:
        limits = {name: int(configured[name]) for name in _SCORE_COMPONENT_LIMITS}
    except (TypeError, ValueError):
        return dict(_SCORE_COMPONENT_LIMITS)
    if any(value < 0 for value in limits.values()) or sum(limits.values()) != 100:
        return dict(_SCORE_COMPONENT_LIMITS)
    return limits


def _as_string_list(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _normalize_evidence(value) -> list[dict]:
    if not isinstance(value, list):
        return []
    normalized = []
    for item in value:
        if not isinstance(item, dict):
            continue
        relation = str(item.get("relation") or "").strip().lower()
        requirement_type = str(item.get("requirement_type") or "").strip().lower()
        if relation not in {"direct", "adjacent", "missing"}:
            relation = "missing"
        if requirement_type not in {"core", "supporting", "basic"}:
            requirement_type = "supporting"
        normalized.append({
            "jd_requirement": str(item.get("jd_requirement") or "").strip(),
            "profile_evidence": str(item.get("profile_evidence") or "").strip(),
            "relation": relation,
            "requirement_type": requirement_type,
        })
    return normalized


def _parse_analysis_json(content: str) -> dict:
    try:
        result = json.loads(content)
    except json.JSONDecodeError:
        # Some Anthropic-compatible responses contain a literal newline or tab
        # inside a JSON string. Python's non-strict mode safely accepts those
        # control characters while still rejecting broken structure.
        result = json.loads(content, strict=False)
    if not isinstance(result, dict):
        raise ValueError("细分析响应不是 JSON 对象")
    return result


def _finalize_analysis(raw: dict, job: dict, profile: dict, model: str) -> dict:
    raw_breakdown = raw.get("score_breakdown")
    if not isinstance(raw_breakdown, dict):
        raise ValueError("细分析响应缺少 score_breakdown")

    limits = _score_component_limits(profile)
    breakdown = {}
    for name, maximum in limits.items():
        try:
            value = int(round(float(raw_breakdown.get(name, 0))))
        except (TypeError, ValueError):
            value = 0
        breakdown[name] = max(0, min(maximum, value))

    evidence_level = str(raw.get("evidence_level") or "insufficient").strip().lower()
    if evidence_level not in _EVIDENCE_CAPS:
        evidence_level = "insufficient"
    evidence = _normalize_evidence(raw.get("evidence"))
    missing_core = _as_string_list(raw.get("missing_core_requirements"))

    score = min(100, sum(breakdown.values()), _EVIDENCE_CAPS[evidence_level])
    direct_core_count = sum(
        item["relation"] == "direct" and item["requirement_type"] == "core"
        for item in evidence
    )
    if direct_core_count == 0:
        score = min(score, 64)
    if len(missing_core) == 1:
        score = min(score, 74)
    elif len(missing_core) >= 2:
        score = min(score, 64)
    if score >= 90 and direct_core_count < 2:
        score = 89

    advantages = _as_string_list(raw.get("advantages"))
    gaps = _as_string_list(raw.get("gaps"))
    for gap in missing_core:
        if gap not in gaps:
            gaps.append(gap)

    thresholds = profile.get("score_thresholds") or {}
    recommend_threshold = int(thresholds.get("recommend", 80))
    consider_threshold = int(thresholds.get("consider", 60))
    if score >= recommend_threshold:
        recommendation = "推荐"
    elif score >= consider_threshold:
        recommendation = "考虑"
    else:
        recommendation = "不推荐"

    return {
        "match_score": score,
        "score_breakdown": breakdown,
        "evidence": evidence,
        "evidence_level": evidence_level,
        "advantages": advantages,
        "gaps": gaps,
        "summary": str(raw.get("summary") or "").strip(),
        "recommendation": recommendation,
        "analysis_status": "complete",
        **analysis_metadata(job, profile, model),
    }


def analyze_job(
    job: dict,
    profile: dict,
    model: str = _DEFAULT_ANALYSIS_MODEL,
    max_tokens: int = _DEFAULT_MAX_TOKENS,
) -> dict:
    if not job_cohorts.is_confirmed_current(job):
        return {
            **_UNCONFIRMED_COHORT_ANALYSIS,
            **analysis_metadata(job, profile, model),
        }
    if job_details.is_jd_incomplete(job):
        return {**_INCOMPLETE_JD_ANALYSIS, **analysis_metadata(job, profile, model)}

    limits = _score_component_limits(profile)
    system_prompt = (
        "你是严格的校招岗位匹配审计员。不得根据公司业务、岗位名称或常识替候选人虚构经验。\n"
        "只有候选人配置中 project_evidence 的内容可作为直接项目证据；supporting_skills "
        "只能作为工程栈证据；learning_targets 和 unverified_skills 均不能作为已掌握能力。\n\n"
        f"候选人结构化配置：\n{_profile_context(profile)}\n\n"
        "请逐条对照 JD，按以下上限给出整数子分：\n"
        f"- core_direction 0-{limits['core_direction']}：岗位核心职责与主/次方向的一致性。\n"
        f"- required_skills 0-{limits['required_skills']}：JD 必备技能中有直接证据的覆盖度。\n"
        f"- project_evidence 0-{limits['project_evidence']}：真实项目证据的数量、深度和相似程度。\n"
        f"- engineering_stack 0-{limits['engineering_stack']}：语言、框架、工具和工程环境。\n"
        f"- basic_criteria 0-{limits['basic_criteria']}：学历、届别等基础条件；地点不计入技能分。\n\n"
        "证据规则：\n"
        "1. relation 只能为 direct、adjacent、missing；requirement_type 只能为 core、supporting、basic。\n"
        "2. C++、Python、Qt、Linux 等通用工具重叠不能代替算法、业务或项目经验。\n"
        "3. 仅有工具重叠或邻接经验时 evidence_level 必须为 adjacent，不能写 direct。\n"
        "4. 缺少三维重建、跟踪、CAM、计算几何、强化学习等 JD 核心能力时必须列入 missing_core_requirements。\n"
        "5. 不得使用“精通”“完全匹配”等超出候选人配置证据的表述。\n"
        "6. evidence_level：direct=核心要求大多有直接项目证据；partial=有部分直接证据；"
        "adjacent=主要依赖可迁移经验；insufficient=证据不足。\n\n"
        "输出必须精炼：evidence 最多6条，advantages 最多4条，gaps 最多4条；"
        "每个数组元素不超过50个汉字，summary 不超过80个汉字。\n"
        "仅输出 JSON，不输出 markdown。不要输出总分和推荐结论，它们由程序计算。"
        "所有字符串必须位于同一行，字符串内部的双引号必须转义，字段之间必须保留逗号。\n"
        'JSON格式：{"score_breakdown":{"core_direction":0,"required_skills":0,'
        '"project_evidence":0,"engineering_stack":0,"basic_criteria":0},'
        '"evidence_level":"partial","evidence":[{"jd_requirement":"核心要求",'
        '"profile_evidence":"候选人证据或未提供","relation":"direct",'
        '"requirement_type":"core"}],"missing_core_requirements":["缺失的核心要求"],'
        '"advantages":["有证据的优势"],"gaps":["其他差距"],"summary":"一句话审慎结论"}'
    )

    user_message = (
        f"公司：{job['company']}\n"
        f"岗位：{job['title']}\n"
        f"城市：{job.get('city', '')}\n"
        f"岗位描述：{job.get('jd_raw', '')[:6000]}"
    )

    try:
        content = call_deepseek_api(system_prompt, user_message, model, max_tokens).strip()

        # 去除可能的 markdown 代码块包裹（兼容 ```json 和 ``` 两种形式）
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
        content = content.strip()

        try:
            result = _parse_analysis_json(content)
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(
                "JSON解析失败 [%s %s]: %s | 原始内容: %.200s",
                job["company"], job["title"], e, content,
            )
            return dict(_DEFAULT_ANALYSIS)

        try:
            return _finalize_analysis(result, job, profile, model)
        except (TypeError, ValueError) as e:
            logger.warning("评分响应校验失败 [%s %s]: %s", job["company"], job["title"], e)
            return dict(_DEFAULT_ANALYSIS)

    except Exception as e:
        logger.error("DeepSeek API 分析失败 [%s %s]: %s", job["company"], job["title"], e)
        return dict(_DEFAULT_ANALYSIS)


def analysis_screening_tier(job: dict) -> str:
    """Resolve the persisted tier after considering a newly hydrated JD."""
    persisted = str(job.get("screening_tier") or "").strip().upper()
    local = local_screening_tier(job)
    if persisted == "C":
        return "C"
    if persisted == "A" or local == "A":
        return "A"
    return "B"


def _analysis_priority(job: dict) -> tuple[int, int]:
    """Rank capped Pro candidates by concrete local evidence."""
    title = str(job.get("title") or "")
    body = str(job.get("jd_raw") or "")
    combined = f"{title}\n{body}"
    evidence_hits = sum(
        bool(pattern.search(combined))
        for pattern in (_CPP_STACK_RE, _TEST_STACK_RE, _ROBOT_VISION_EVIDENCE_RE)
    )
    direct_title = sum(
        bool(pattern.search(title))
        for pattern in (_DIRECT_CPP_TITLE_RE, _ROBOT_VISION_TITLE_RE, _TEST_TITLE_RE)
    )
    return direct_title, evidence_hits


def _can_hydrate_to_tier_a(job: dict) -> bool:
    """Return whether a sparse B row could become A after fetching its JD."""
    if not job_cohorts.is_confirmed_current(job):
        return False
    incomplete = job_details.is_jd_incomplete(job)
    durable_unavailable = str(job.get("jd_status") or "") in {
        "official_unavailable",
        "official_sparse",
        "list_only",
    }
    retry_cooldown = False
    if str(job.get("jd_status") or "") == "fetch_failed":
        try:
            checked_at = datetime.fromisoformat(str(job.get("jd_checked_at") or ""))
            retry_days = max(1, int(os.environ.get("JD_RETRY_DAYS", "7")))
            retry_cooldown = datetime.now() - checked_at < timedelta(days=retry_days)
        except (TypeError, ValueError):
            retry_cooldown = False
    if analysis_screening_tier(job) == "A":
        if incomplete and (durable_unavailable or retry_cooldown):
            return False
        return True
    if not incomplete:
        return False
    if durable_unavailable or retry_cooldown:
        return False
    title = str(job.get("title") or "")
    return any(
        pattern.search(title)
        for pattern in (
            _DIRECT_CPP_TITLE_RE,
            _ROBOT_VISION_TITLE_RE,
            _TEST_TITLE_RE,
            _SOFTWARE_TITLE_RE,
        )
    )


def needs_detailed_analysis(conn, job: dict, profile: dict, model: str) -> bool:
    """Return whether a job should enter the JD hydration/Pro queue."""
    return (
        needs_analysis(conn, job, profile, model)
        and job_cohorts.is_confirmed_current(job)
        and job_filters.is_formal_campus_job(job)
        and not job_filters.is_direction_out_job(job)
        and _can_hydrate_to_tier_a(job)
    )


def batch_analyze(
    jobs: list[dict],
    profile: dict,
    conn,
    model: str = _DEFAULT_ANALYSIS_MODEL,
    max_tokens: int = _DEFAULT_MAX_TOKENS,
    hydrate: bool = True,
    max_jobs: int | None = None,
    max_jobs_per_day: int | None = None,
) -> list[dict]:
    pending = [j for j in jobs if needs_analysis(conn, j, profile, model)]
    if not pending:
        return []

    prefiltered = [
        job for job in pending
        if job_cohorts.is_confirmed_current(job)
        and job_filters.is_formal_campus_job(job)
        and not job_filters.is_direction_out_job(job)
    ]
    excluded_before_hydration = len(pending) - len(prefiltered)
    if excluded_before_hydration:
        logger.warning(
            "预筛识别到 %d 个非确认27届、实习/提前批/社招或方向外岗位，"
            "不补 JD、不调用 Pro",
            excluded_before_hydration,
        )
    initial_pro_candidates = [
        job for job in prefiltered
        if analysis_screening_tier(job) == "A"
    ]
    upgrade_candidates = [
        job for job in prefiltered
        if analysis_screening_tier(job) == "B"
        and _can_hydrate_to_tier_a(job)
    ]
    pro_candidates = initial_pro_candidates + upgrade_candidates
    skipped_tier_b = len(prefiltered) - len(initial_pro_candidates)
    if skipped_tier_b:
        logger.info(
            "分级预筛保留 %d 个 B 档岗位展示；其中 %d 个强标题稀疏 JD 允许先补全复核",
            skipped_tier_b,
            len(upgrade_candidates),
        )
    if not pro_candidates:
        return []

    complete = []
    hydration_candidates = [
        job for job in pro_candidates if job_details.is_jd_incomplete(job)
    ]
    if hydration_candidates and hydrate:
        logger.info("细分析前补抓 %d 个不完整 JD", len(hydration_candidates))
        with concurrent.futures.ThreadPoolExecutor(max_workers=_JD_HYDRATE_WORKERS) as ex:
            futures = {ex.submit(job_details.fetch_full_job_description, job): job for job in hydration_candidates}
            for future in concurrent.futures.as_completed(futures):
                job = futures[future]
                try:
                    detail = future.result()
                except Exception as e:  # noqa: BLE001
                    logger.warning("岗位详情补抓异常 [%s %s]: %s", job["company"], job["title"], e)
                    detail = ""
                if detail:
                    db_module.update_job_jd(
                        conn,
                        job["id"],
                        detail,
                        jd_url=job.get("jd_url"),
                        link_kind=job.get("link_kind"),
                    )
                    job["jd_raw"] = detail

        complete = [
            job for job in pro_candidates if not job_details.is_jd_incomplete(job)
        ]
    elif hydration_candidates:
        complete = [
            job for job in pro_candidates if not job_details.is_jd_incomplete(job)
        ]
    else:
        complete = pro_candidates

    jd_incomplete_count = sum(
        job_details.is_jd_incomplete(job) for job in pro_candidates
    )
    if jd_incomplete_count:
        logger.warning("跳过 %d 个仍缺少完整 JD 的岗位，不调用 Pro", jd_incomplete_count)

    eligible = [
        job for job in complete
        if job_filters.is_formal_campus_job(job)
        and not job_filters.is_direction_out_job(job)
    ]
    excluded_after_hydration = len(complete) - len(eligible)
    if excluded_after_hydration:
        logger.warning(
            "JD 补全后识别到 %d 个实习/提前批/社招或方向外岗位，不调用 Pro",
            excluded_after_hydration,
        )
    complete = [
        job for job in eligible if analysis_screening_tier(job) == "A"
    ]

    if not complete:
        return []

    complete.sort(key=_analysis_priority, reverse=True)
    run_limit = max_jobs if max_jobs and max_jobs > 0 else None
    if max_jobs_per_day and max_jobs_per_day > 0:
        analyzed_today = conn.execute(
            """SELECT COUNT(*) FROM job_analysis
               WHERE model = ? AND date(analyzed_at) = date('now', 'localtime')""",
            (model,),
        ).fetchone()[0]
        daily_remaining = max(0, max_jobs_per_day - analyzed_today)
        run_limit = daily_remaining if run_limit is None else min(run_limit, daily_remaining)
    if run_limit is not None and len(complete) > run_limit:
        logger.warning(
            "Pro 硬限制生效：候选 %d 个，本次仅分析前 %d 个，其余留待后续确认",
            len(complete), run_limit,
        )
        complete = complete[:run_limit]
    if not complete:
        logger.warning("今日 Pro 分析额度已用完，本次不调用模型")
        return []
    logger.warning(
        "Pro 调用预算：本次 %d 个岗位，单条输出上限 %d Token，"
        "输出上限合计 %d Token（不含输入）",
        len(complete), max_tokens, len(complete) * max_tokens,
    )

    # analyze_job 是纯 DeepSeek API 调用（不碰 conn）→ 可并发；DB 写回放主线程串行（SQLite 安全）。
    results = []
    failed = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=_ANALYZE_WORKERS) as ex:
        fut_to_job = {ex.submit(analyze_job, j, profile, model, max_tokens): j for j in complete}
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
            if analysis.get("analysis_status") != "complete":
                failed += 1
                continue
            db_module.save_analysis(conn, job["id"], analysis)  # 主线程，SQLite 安全
            results.append({"job_id": job["id"], "analysis": analysis})

    logger.info("细分析完成：成功 %d / 失败(下次重试) %d（并发 %d worker）",
                len(results), failed, _ANALYZE_WORKERS)
    return results
