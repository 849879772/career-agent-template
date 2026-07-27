from crawlers.pdd import PDDCrawler


class FakeResponse:
    def __init__(self, result):
        self._result = result

    def raise_for_status(self):
        return None

    def json(self):
        return {"success": True, "result": self._result}


def test_pdd_crawler_uses_official_detail_api_and_direct_job_url(monkeypatch):
    calls = []

    def fake_post(_self, url, json, timeout):
        calls.append((url, json, timeout))
        if url.endswith("/list"):
            return FakeResponse({
                "list": [{
                    "id": "job-1",
                    "name": "AI Infra研发工程师【2027届云弧计划】",
                    "workLocationName": "上海",
                    "graduationYear": "2027",
                    "recruitTypeName": "云弧计划",
                    "releaseTime": 1778210700000,
                    "jobDuty": "负责大模型训练基础设施研发。",
                }],
                "total": "1",
            })
        return FakeResponse({
            "id": "job-1",
            "workLocationName": "上海",
            "graduationYear": "2027",
            "recruitTypeName": "云弧计划",
            "releaseTime": 1778210700000,
            "jobDuty": "负责大模型训练与推理基础设施研发。",
            "serveRequirement": "熟悉 C++、Python、PyTorch 和分布式系统。",
            "bonus": "有高性能计算项目经验优先。",
            "shareUrl": (
                "https://careers.pddglobalhr.com/campus/grad/detail?"
                "positionId=job-1"
            ),
        })

    monkeypatch.setattr("requests.Session.post", fake_post)
    jobs = PDDCrawler(
        "拼多多", "https://careers.pddglobalhr.com/campus/grad"
    ).fetch()

    assert len(jobs) == 1
    assert jobs[0]["link_kind"] == "detail"
    assert "positionId=job-1" in jobs[0]["jd_url"]
    assert "岗位职责" in jobs[0]["jd_raw"]
    assert "任职要求" in jobs[0]["jd_raw"]
    assert "加分项" in jobs[0]["jd_raw"]
    assert "2027届" in jobs[0]["job_type"]
    assert calls[0][0].endswith("/list")
    assert calls[1][0].endswith("/detail")
