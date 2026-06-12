"""Crossref source: keyword search for formally published papers."""

import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List

from daily_paper.dates import in_date_window, validate_date
from daily_paper.http import request_json
from daily_paper.normalizer import IMPACT_FACTOR_TABLE, finalize_paper, get_impact_factor
from daily_paper.queries import flatten_queries

logger = logging.getLogger(__name__)


def _date_from_crossref_parts(value) -> str:
    """Extract date from Crossref date-parts, preferring online then print then created."""
    for field in ("published-online", "published-print", "created"):
        parts = (value or {}).get(field, {}).get("date-parts") or []
        if not parts or not parts[0]:
            continue
        dp = parts[0]
        y = dp[0] if len(dp) > 0 else None
        m = dp[1] if len(dp) > 1 else None
        d = dp[2] if len(dp) > 2 else None
        if not y or not m:
            continue
        if not d:
            d = 1
        return f"{y:04d}-{m:02d}-{d:02d}"
    return ""


def _clean_abstract(text: str) -> str:
    """Clean Crossref JATS/XML abstracts."""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def fetch_crossref_papers(config: Dict, ss_api_key: str = "", arxiv_client=None) -> List[Dict]:
    """Search Crossref by query, paging until no new deduplicated records appear."""
    source_config = config.get("sources", {}).get("crossref", {})
    if not source_config.get("enabled", False):
        logger.info("Crossref source disabled")
        return []

    queries = flatten_queries(source_config)
    max_per_query = int(source_config.get("max_results_per_query", 20))
    max_pages = max(1, int(source_config.get("max_pages_per_query", 1)))
    stop_after_empty_pages = max(1, int(source_config.get("stop_after_empty_pages", 1)))
    days_back = source_config.get("days_back", 180)
    from_date = validate_date(source_config.get("start_date", "")) or (
        datetime.now(timezone.utc) - timedelta(days=days_back)
    ).strftime("%Y-%m-%d")
    until_date = validate_date(source_config.get("end_date", ""))

    all_papers = []
    seen_dois = set()

    for query in queries:
        logger.info("Crossref search: %s", query)
        date_filter = f"from-pub-date:{from_date}"
        if until_date:
            date_filter += f",until-pub-date:{until_date}"

        query_count = 0
        empty_pages = 0
        for page in range(max_pages):
            params = {
                "query": query,
                "filter": date_filter,
                "rows": max_per_query,
                "offset": page * max_per_query,
            }
            data = request_json("https://api.crossref.org/works", params=params)
            if not data:
                logger.warning("Crossref query failed: %s page=%s", query, page + 1)
                break

            items = (data.get("message") or {}).get("items") or []
            if not items:
                break

            page_new = 0
            for item in items:
                doi = (item.get("DOI") or "").strip().lower()
                if not doi or doi in seen_dois:
                    continue
                seen_dois.add(doi)

                title = " ".join(item.get("title") or []).strip()
                if not title:
                    continue

                authors = ", ".join(
                    f"{a.get('given', '')} {a.get('family', '')}".strip()
                    for a in item.get("author") or []
                )
                published = _date_from_crossref_parts(item)
                if not in_date_window(published, from_date, until_date):
                    continue

                item_type = item.get("type", "")
                skip_types = {
                    "editorial", "correction", "withdrawn",
                    "book-review", "dissertation", "reference-entry",
                }
                if item_type in skip_types:
                    continue
                if any(title.lower().startswith(p) for p in ("withdrawn", "correction:", "editorial board")):
                    continue

                container = item.get("container-title") or []
                venue = container[0].strip() if container else ""
                paper = {
                    "id": doi,
                    "title": title,
                    "authors": authors,
                    "abstract": _clean_abstract(item.get("abstract", "")),
                    "published": published,
                    "paper_url": f"https://doi.org/{doi}",
                    "arxiv_id": "",
                    "arxiv_url": "",
                    "pdf_url": "",
                    "preprint_pdf_url": "",
                    "categories": [],
                    "venue": venue,
                    "conference": venue,
                    "publication_types": [item_type] if item_type else [],
                    "publication_type": "",
                    "doi": doi,
                    "external_ids": {},
                    "semantic_scholar_id": "",
                    "code_link": "",
                    "tags": [],
                    "keywords": [],
                    "citation_count": item.get("is-referenced-by-count"),
                    "impact_factor": get_impact_factor({"conference": venue}, IMPACT_FACTOR_TABLE),
                    "source": "crossref",
                }
                all_papers.append(finalize_paper(paper, config))
                query_count += 1
                page_new += 1

            logger.info(
                "  -> Crossref page %s/%s: new %s, total %s",
                page + 1,
                max_pages,
                page_new,
                len(all_papers),
            )
            empty_pages = empty_pages + 1 if page_new == 0 else 0
            if empty_pages >= stop_after_empty_pages or len(items) < max_per_query:
                break
            time.sleep(1)

        logger.info("  -> Crossref query added %s, total %s", query_count, len(all_papers))
        time.sleep(1)

    logger.info("Crossref returned %s deduplicated papers", len(all_papers))
    return all_papers
