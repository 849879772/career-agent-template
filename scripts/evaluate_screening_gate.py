"""Evaluate the local A/B/C gate against saved detailed-analysis results."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import analyzer


def evaluate(db_path: Path, positive_score: int = 60) -> dict:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = [
            dict(row)
            for row in conn.execute(
                """SELECT job.*, analysis.match_score
                   FROM jobs AS job
                   INNER JOIN job_analysis AS analysis ON analysis.job_id = job.id"""
            )
        ]
    finally:
        conn.close()

    positives = [row for row in rows if row["match_score"] >= positive_score]
    tiers = {
        tier: sum(analyzer.local_screening_tier(row) == tier for row in rows)
        for tier in "ABC"
    }
    positive_tiers = {
        tier: sum(analyzer.local_screening_tier(row) == tier for row in positives)
        for tier in "ABC"
    }
    a_total = tiers["A"]
    a_positive = positive_tiers["A"]
    return {
        "database": str(db_path),
        "analyzed": len(rows),
        "positive_score": positive_score,
        "positive": len(positives),
        "tiers": tiers,
        "positive_tiers": positive_tiers,
        "a_precision": round(a_positive / a_total, 4) if a_total else 0,
        "a_recall": round(a_positive / len(positives), 4) if positives else 0,
        "retained_ab_recall": round(
            (positive_tiers["A"] + positive_tiers["B"]) / len(positives), 4
        ) if positives else 0,
        "estimated_pro_reduction": round(1 - a_total / len(rows), 4) if rows else 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--positive-score", type=int, default=60)
    args = parser.parse_args()
    print(json.dumps(
        evaluate(args.db.resolve(), args.positive_score),
        ensure_ascii=False,
        indent=2,
    ))


if __name__ == "__main__":
    main()
