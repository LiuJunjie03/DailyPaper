#!/usr/bin/env python3
"""Report abstract enrichment status for Google Scholar records."""

import json
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"


def main() -> int:
    status_counts = Counter()
    source_counts = Counter()
    remaining = []

    for path in sorted(DATA_DIR.glob("????-??.json")):
        papers = json.loads(path.read_text(encoding="utf-8"))
        for paper in papers:
            if paper.get("source") != "google_scholar":
                continue
            status = paper.get("abstract_status") or "unknown"
            status_counts[status] += 1
            if paper.get("abstract_source"):
                source_counts[paper["abstract_source"]] += 1
            if status == "unreliable_google_scholar_snippet":
                remaining.append({
                    "month_file": path.name,
                    "title": paper.get("title", ""),
                    "paper_url": paper.get("paper_url", ""),
                    "venue": paper.get("venue", ""),
                    "published": paper.get("published", ""),
                })

    report = {
        "status_counts": dict(status_counts),
        "abstract_source_counts": dict(source_counts),
        "remaining_count": len(remaining),
        "remaining": remaining,
    }
    sys.stdout.buffer.write(json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8") + b"\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
