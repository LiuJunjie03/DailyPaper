"""OpenAlex source: keyword search over the open scholarly graph."""

import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from daily_paper.dates import validate_date
from daily_paper.http import request_json
from daily_paper.normalizer import IMPACT_FACTOR_TABLE, finalize_paper, get_impact_factor
from daily_paper.queries import flatten_queries

logger = logging.getLogger(__name__)


def _openalex_abstract(inverted_index: Optional[Dict]) -> str:
    """Rebuild OpenAlex abstract text from an inverted index."""
    if not inverted_index:
        return ""
    words = []
    for word, positions in inverted_index.items():
        for pos in positions:
            words.append((pos, word))
    return " ".join(word for _, word in sorted(words))


def fetch_openalex_papers(config: Dict, ss_api_key: str = "", arxiv_client=None) -> List[Dict]:
    """Search OpenAlex by query, paging until a page adds no new records."""
    source_config = config.get("sources", {}).get("openalex", {})
    if not source_config.get("enabled", False):
        logger.info("OpenAlex source disabled")
        return []

    queries = flatten_queries(source_config)
    max_per_query = int(source_config.get("max_results_per_query", 20))
    max_pages = max(1, int(source_config.get("max_pages_per_query", 1)))
    stop_after_empty_pages = max(1, int(source_config.get("stop_after_empty_pages", 1)))
    days_back = source_config.get("days_back", 180)
    mailto = source_config.get("mailto", "")
    from_date = validate_date(source_config.get("start_date", "")) or (
        datetime.now(timezone.utc) - timedelta(days=days_back)
    ).strftime("%Y-%m-%d")
    until_date = validate_date(source_config.get("end_date", ""))

    all_papers = []
    seen_ids = set()

    for query in queries:
        logger.info("OpenAlex search: %s", query)
        date_filter = f"from_publication_date:{from_date}"
        if until_date:
            date_filter += f",to_publication_date:{until_date}"

        query_count = 0
        empty_pages = 0
        for page in range(1, max_pages + 1):
            params = {
                "search": query,
                "per_page": max_per_query,
                "page": page,
                "mailto": mailto,
                "filter": date_filter,
                "sort": "cited_by_count:desc",
            }
            data = request_json("https://api.openalex.org/works", params=params)
            if not data:
                logger.warning("OpenAlex query failed: %s page=%s", query, page)
                break

            results = data.get("results") or []
            if not results:
                break

            page_new = 0
            for item in results:
                raw_doi = (item.get("doi") or "").replace("https://doi.org/", "")
                openalex_id = (item.get("id") or "").rsplit("/", 1)[-1] if item.get("id") else ""
                dedup_id = raw_doi or openalex_id
                if not dedup_id or dedup_id in seen_ids:
                    continue
                seen_ids.add(dedup_id)

                title = (item.get("title") or "").strip()
                if not title:
                    continue

                authorships = item.get("authorships") or []
                authors = ", ".join(
                    (a.get("author") or {}).get("display_name", "")
                    for a in authorships
                    if (a.get("author") or {}).get("display_name")
                )
                primary_location = item.get("primary_location") or {}
                source_info = primary_location.get("source") or {}
                venue = source_info.get("display_name") or ""
                oa = item.get("open_access") or {}
                pdf_url = oa.get("oa_url") or ""
                work_type = item.get("type") or ""
                arxiv_id = ""
                if raw_doi and "arxiv" in raw_doi.lower():
                    match = re.search(r"arxiv\.(\d{4}\.\d{4,5})", raw_doi, re.IGNORECASE)
                    if match:
                        arxiv_id = match.group(1)

                paper = {
                    "id": raw_doi or f"oa-{openalex_id}",
                    "title": title,
                    "authors": authors,
                    "abstract": _openalex_abstract(item.get("abstract_inverted_index")),
                    "published": item.get("publication_date") or "",
                    "paper_url": f"https://doi.org/{raw_doi}" if raw_doi else (item.get("doi") or ""),
                    "arxiv_id": arxiv_id,
                    "arxiv_url": f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else "",
                    "pdf_url": pdf_url,
                    "preprint_pdf_url": f"https://arxiv.org/pdf/{arxiv_id}" if arxiv_id else "",
                    "categories": [],
                    "venue": venue,
                    "conference": venue,
                    "publication_types": [work_type] if work_type else [],
                    "publication_type": "",
                    "doi": raw_doi,
                    "external_ids": {"OpenAlex": openalex_id} if openalex_id else {},
                    "semantic_scholar_id": "",
                    "code_link": "",
                    "tags": [],
                    "keywords": [],
                    "citation_count": item.get("cited_by_count"),
                    "impact_factor": get_impact_factor({"conference": venue}, IMPACT_FACTOR_TABLE),
                    "source": "openalex",
                }

                all_papers.append(finalize_paper(paper, config))
                query_count += 1
                page_new += 1

            logger.info(
                "  -> OpenAlex page %s/%s: new %s, total %s",
                page,
                max_pages,
                page_new,
                len(all_papers),
            )
            empty_pages = empty_pages + 1 if page_new == 0 else 0
            if empty_pages >= stop_after_empty_pages or len(results) < max_per_query:
                break
            time.sleep(1)

        logger.info("  -> OpenAlex query added %s, total %s", query_count, len(all_papers))
        time.sleep(1)

    logger.info("OpenAlex returned %s deduplicated papers", len(all_papers))
    return all_papers
