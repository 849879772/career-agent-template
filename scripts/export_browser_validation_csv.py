import csv
import json
from pathlib import Path


ROOT = Path("outputs/crawler_effective_urls")
JSON_PATH = ROOT / "browser_validation_results.json"
CSV_PATH = ROOT / "browser_validation_results.csv"


def main() -> None:
    rows = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    fields = [
        "company",
        "crawler",
        "auto_verdict",
        "access_type",
        "browser_verdict",
        "config_url",
        "effective_url",
        "probe_summary",
    ]
    with CSV_PATH.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            probes = []
            for probe in row.get("probes", []):
                probes.append(
                    " | ".join(
                        [
                            probe.get("kind", ""),
                            probe.get("url", ""),
                            "OK" if probe.get("ok") else "FAIL",
                            probe.get("title", ""),
                            probe.get("final_url", ""),
                            probe.get("error", ""),
                        ]
                    )
                )
            writer.writerow({**{k: row.get(k, "") for k in fields}, "probe_summary": "\n".join(probes)})
    print(CSV_PATH.resolve())


if __name__ == "__main__":
    main()
