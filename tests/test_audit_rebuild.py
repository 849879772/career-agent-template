import json

import yaml

import analyzer
import db
from profile_config import load_profile
from scripts import audit_rebuild


def test_audit_accepts_score_reduced_below_component_sum(tmp_path):
    db_path = tmp_path / "rebuild.db"
    applications_path = tmp_path / "applications.json"
    applications_path.write_text("[]", encoding="utf-8")
    conn = db.init_db(db_path)
    job = {
        "company": "测试公司",
        "title": "C++软件开发工程师",
        "city": "深圳",
        "job_type": "校招",
        "jd_url": "https://example.com/campus/job/1",
        "jd_raw": (
            "岗位职责\n负责 C++ 服务开发、性能优化和自动化测试。\n"
            "任职要求\n熟悉 Linux、数据结构、多线程和网络编程，具有相关项目经验。"
        ),
        "published_at": "",
        "source": "测试公司",
    }
    _, job_id = db.upsert_job(conn, job)
    stored = dict(conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone())
    config = yaml.safe_load((audit_rebuild.ROOT / "config.yaml").read_text(encoding="utf-8"))
    profile = load_profile(audit_rebuild.ROOT / "profile.yaml")
    model = config["deepseek"]["analysis_model"]
    db.save_analysis(conn, job_id, {
        "match_score": 74,
        "score_breakdown": {
            "core_direction": 20,
            "required_skills": 20,
            "project_evidence": 20,
            "engineering_stack": 15,
            "basic_criteria": 10,
        },
        "evidence": [{
            "jd_requirement": "C++软件开发",
            "profile_evidence": "C++项目",
            "relation": "direct",
            "requirement_type": "core",
        }],
        "evidence_level": "direct",
        "advantages": ["C++项目匹配"],
        "gaps": ["仍有一项核心要求待确认"],
        "summary": "方向匹配，但受核心缺口规则封顶。",
        "recommendation": "考虑",
        "analysis_status": "complete",
        **analyzer.analysis_metadata(stored, profile, model),
    })
    conn.close()

    result = audit_rebuild.audit(db_path, applications_path)
    assert result["passed"]
    assert result["blocking_checks"]["score_rule_errors"] == 0
    assert result["counts"]["applications"] == 0


def test_count_applications_rejects_invalid_json_shape(tmp_path):
    path = tmp_path / "applications.json"
    path.write_text(json.dumps({"not": "a list"}), encoding="utf-8")
    assert audit_rebuild._count_applications(path) == -1


def test_audit_preserves_valid_manual_application_records(tmp_path):
    db_path = tmp_path / "rebuild.db"
    applications_path = tmp_path / "applications.json"
    applications_path.write_text(
        json.dumps([{
            "id": 1,
            "job_id": None,
            "company": "手填公司",
            "title": "手填岗位",
        }], ensure_ascii=False),
        encoding="utf-8",
    )
    conn = db.init_db(db_path)
    conn.close()

    result = audit_rebuild.audit(db_path, applications_path)

    assert result["passed"]
    assert result["counts"]["applications"] == 1
    assert result["blocking_checks"]["applications_file_invalid"] == 0
    assert result["blocking_checks"]["dangling_application_job_ids"] == 0
