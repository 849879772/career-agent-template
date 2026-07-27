from scripts.dedupe_company_sources import build_plan


def test_build_plan_normalizes_aliases_but_keeps_distinct_sources():
    companies = [
        {
            "name": "大华股份",
            "careers_url": "https://dahua1.zhiye.com/campus/jobs",
            "crawler": "beisen",
        },
        {
            "name": "大华",
            "careers_url": "https://dahua.zhiye.com/campus/jobs",
            "crawler": "beisen",
        },
    ]

    kept, aliases = build_plan(companies)

    assert [row["name"] for row in kept] == ["大华股份", "大华股份"]
    assert aliases[0]["alias"] == "大华"
    assert aliases[0]["canonical"] == "大华股份"


def test_build_plan_removes_redundant_and_internship_only_sources():
    companies = [
        {
            "name": "海康威视",
            "careers_url": "https://campushr.hikvision.com/",
            "crawler": "hikvision",
        },
        {
            "name": "海康sb公司",
            "careers_url": "https://campushr.hikvision.com/school",
            "crawler": "hikvision",
        },
        {
            "name": "云创智行实习",
            "careers_url": "https://www.yczx.tech/join/campus",
            "crawler": "render",
        },
    ]

    kept, aliases = build_plan(companies)

    assert [row["name"] for row in kept] == ["海康威视"]
    assert {row["alias"] for row in aliases} == {"海康sb公司", "云创智行实习"}
