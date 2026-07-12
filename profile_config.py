from pathlib import Path

import yaml


REQUIRED_FIELDS = (
    "degree",
    "job_type",
    "directions",
    "skills",
    "target_roles",
    "scoring_weights",
    "score_thresholds",
)


def load_profile(path: str | Path = "profile.yaml") -> dict:
    profile_path = Path(path)
    if not profile_path.exists():
        raise ValueError(f"找不到用户画像配置: {profile_path}")

    profile = yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}
    missing = [field for field in REQUIRED_FIELDS if field not in profile]
    if missing:
        raise ValueError(f"profile.yaml 缺少字段: {', '.join(missing)}")

    weights = profile["scoring_weights"]
    if not isinstance(weights, dict) or sum(weights.values()) != 100:
        raise ValueError("profile.yaml 的 scoring_weights 必须是合计 100 的数字映射")

    thresholds = profile["score_thresholds"]
    recommend = int(thresholds.get("recommend", 80))
    consider = int(thresholds.get("consider", 60))
    if not 0 <= consider <= recommend <= 100:
        raise ValueError("评分阈值必须满足 0 <= consider <= recommend <= 100")

    return profile
