from scripts.audit_active_job_links import _merge


def test_browser_verified_request_failure_is_access_blocked():
    row = {
        "id": 1,
        "company": "华润集团",
        "title": "CIM工程师",
        "jd_url": "https://runjob.crc.com.cn/",
        "link_kind": "list",
        "last_seen_at": "2026-07-25",
    }
    fetched = {
        "status": "",
        "final_url": "",
        "page_title": "",
        "http_verdict": "request_failed",
        "error": "legacy TLS",
    }

    assert _merge(row, fetched)["verdict"] == "access_blocked"
