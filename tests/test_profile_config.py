from pathlib import Path

import pytest

from profile_config import load_profile


def test_default_profile_is_valid():
    profile = load_profile(Path(__file__).parent.parent / "profile.yaml")

    assert profile["target_roles"]
    assert sum(profile["scoring_weights"].values()) == 100


def test_rejects_invalid_weight_total(tmp_path):
    profile = tmp_path / "profile.yaml"
    profile.write_text(
        """
degree: 本科
job_type: 校招
directions: [软件开发]
skills: [C++]
target_roles: [C++开发]
scoring_weights: {role: 60, skill: 30}
score_thresholds: {recommend: 80, consider: 60}
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="合计 100"):
        load_profile(profile)
