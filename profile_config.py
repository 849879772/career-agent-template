from pathlib import Path

import yaml


REQUIRED_FIELDS = (
    "degree",
    "job_type",
    "directions",
    "skills",
    "target_roles",
    "score_component_limits",
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

    limits = profile["score_component_limits"]
    expected_components = {
        "core_direction",
        "required_skills",
        "project_evidence",
        "engineering_stack",
        "basic_criteria",
    }
    if (
        not isinstance(limits, dict)
        or set(limits) != expected_components
        or sum(limits.values()) != 100
    ):
        raise ValueError(
            "profile.yaml 的 score_component_limits 必须包含五个评分项且合计 100"
        )

    thresholds = profile["score_thresholds"]
    recommend = int(thresholds.get("recommend", 80))
    consider = int(thresholds.get("consider", 60))
    if not 0 <= consider <= recommend <= 100:
        raise ValueError("评分阈值必须满足 0 <= consider <= recommend <= 100")

    directions = [
        str(item).strip() for item in profile.get("directions", [])
        if str(item).strip()
    ]
    profile["direction"] = " / ".join(directions)
    if not profile.get("matching"):
        profile["matching"] = {
            "primary_directions": directions,
            "secondary_directions": profile.get("secondary_directions", []),
            "project_evidence": profile.get("project_evidence", []),
            "supporting_skills": profile.get("skills", []),
            "learning_targets": profile.get("learning_targets", []),
            "unverified_skills": profile.get("unverified_skills", []),
        }

    return profile
