from scripts.qq_docs_27_autumn_monitor import compare_with_config, parse_rows


def test_parse_rows_keeps_links_and_marks_mixed_records():
    payload = [{
        "f_company": {"k30": "公司名称"},
        "f_type": {"k30": "招聘类型", "k9": {"k3": [
            {"k1": "formal", "k2": "27届秋招"},
            {"k1": "intern", "k2": "27届暑期实习"},
        ]}},
        "f_link": {"k30": "投递链接"},
        "row": {"k1": {
            "f_company": {"k1": [{"k2": "DJI大疆"}]},
            "f_type": {"k9": ["formal", "intern"]},
            "f_link": {"k8": [{"k3": "https://example.com/jobs"}]},
        }},
    }]

    rows = parse_rows(payload)

    assert rows == [{
        "source_name": "DJI大疆",
        "canonical_name": "大疆",
        "tags": ["27届秋招", "27届暑期实习"],
        "links": ["https://example.com/jobs"],
        "source_status": "mixed_or_excluded",
        "excluded_tags": ["27届暑期实习"],
    }]


def test_compare_with_config_uses_campaign_aliases():
    rows = [{"source_name": "DJI大疆", "canonical_name": "大疆"}]
    result = compare_with_config(rows, [{"name": "大疆"}])
    assert result[0]["in_config"] is True
