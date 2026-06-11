#!/usr/bin/env python3
"""Repair year-only and default publication dates in monthly data files."""

import argparse
import json
import re
import time
from pathlib import Path
from typing import Dict, Iterable, Optional
from urllib.parse import quote

import requests

from daily_paper.enrich import request_json as _enrich_request_json, title_matches

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
USER_AGENT = "DailyPaperBot/1.0"
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
YEAR_RE = re.compile(r"^\d{4}$")


def is_complete_publication_date(value: str) -> bool:
    return bool(DATE_RE.fullmatch(str(value or "")))


def is_placeholder_publication_date(value: str, month: str = "") -> bool:
    value = str(value or "")
    if YEAR_RE.fullmatch(value):
        return True
    if not DATE_RE.fullmatch(value):
        return value.lower() in {"", "unknown", "none"}
    return value.endswith("-01-01") and (not month or value[:7] == month)


# 复用 daily_paper.enrich 的 request_json
request_json = _enrich_request_json


def date_from_crossref_parts(value: Dict) -> str:
    parts = (value or {}).get("date-parts") or []
    if not parts or not parts[0] or len(parts[0]) < 3:
        return ""
    year, month, day = parts[0][:3]
    return f"{year:04d}-{month:02d}-{day:02d}"


def fetch_crossref_date(paper: Dict) -> Optional[Dict]:
    items = []
    doi = (paper.get("doi") or "").strip()
    if doi:
        data = request_json(f"https://api.crossref.org/works/{quote(doi, safe='')}")
        if data:
            items.append((data.get("message") or {}, "crossref_doi"))

    data = request_json(
        "https://api.crossref.org/works",
        params={"query.title": paper.get("title", ""), "rows": 5},
    )
    if data:
        items.extend((item, "crossref_title") for item in ((data.get("message") or {}).get("items") or []))

    for item, source in items:
        title = " ".join(item.get("title") or [])
        if title and not title_matches(paper.get("title", ""), title):
            continue
        for field in ("published-online", "published-print", "published", "created"):
            date = date_from_crossref_parts(item.get(field) or {})
            if date:
                return {
                    "published": date,
                    "publication_date_source": source,
                    "doi": item.get("DOI") or doi,
                }
    return None


def fetch_openalex_date(paper: Dict) -> Optional[Dict]:
    data = request_json(
        "https://api.openalex.org/works",
        params={"search": paper.get("title", ""), "per-page": 5, "mailto": "research@example.com"},
    )
    for item in (data or {}).get("results", []):
        if not title_matches(paper.get("title", ""), item.get("title", "")):
            continue
        date = item.get("publication_date") or ""
        if is_complete_publication_date(date):
            doi = (item.get("doi") or "").replace("https://doi.org/", "")
            return {
                "published": date,
                "publication_date_source": "openalex",
                "doi": doi or paper.get("doi", ""),
                "openalex_id": item.get("id", ""),
            }
    return None


def fetch_arxiv_date(paper: Dict) -> Optional[Dict]:
    arxiv_id = (paper.get("arxiv_id") or paper.get("id") or "").split("v")[0]
    if not arxiv_id or not re.match(r"^\d{4}\.\d{4,5}$", arxiv_id):
        return None
    try:
        response = requests.get(
            "https://export.arxiv.org/api/query",
            params={"id_list": arxiv_id},
            timeout=15,
            headers={"User-Agent": USER_AGENT},
        )
        if response.status_code != 200:
            return None
        match = re.search(r"<published>(\d{4}-\d{2}-\d{2})T", response.text)
        if match:
            return {"published": match.group(1), "publication_date_source": "arxiv"}
    except requests.RequestException:
        return None
    return None


def repair_paper_date(paper: Dict) -> Optional[Dict]:
    fetchers = (fetch_arxiv_date, fetch_crossref_date, fetch_openalex_date)
    for fetcher in fetchers:
        result = fetcher(paper)
        if result and is_complete_publication_date(result.get("published", "")):
            return result
        time.sleep(0.2)
    return None


def iter_month_files(data_dir: Path, months: Iterable[str]) -> Iterable[Path]:
    if months:
        for month in months:
            yield data_dir / f"{month}.json"
        return
    yield from sorted(data_dir.glob("????-??.json"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default=str(DATA_DIR))
    parser.add_argument("--month", action="append", default=[])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    total_checked = total_updated = 0
    for path in iter_month_files(Path(args.data_dir), args.month):
        if not path.exists():
            continue
        month = path.stem
        papers = json.loads(path.read_text(encoding="utf-8"))
        changed = 0
        for paper in papers:
            if not is_placeholder_publication_date(paper.get("published", ""), month):
                continue
            total_checked += 1
            result = repair_paper_date(paper)
            if not result:
                continue
            old = paper.get("published", "")
            paper.update({k: v for k, v in result.items() if v})
            if paper.get("published") != old or result.get("publication_date_source"):
                changed += 1
                total_updated += 1
                print(f"{path.name}: {old} -> {paper.get('published')} {paper.get('title')}")
        if changed and not args.dry_run:
            path.write_text(json.dumps(papers, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({"checked": total_checked, "updated": total_updated, "dry_run": args.dry_run}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
