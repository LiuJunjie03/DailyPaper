"""Semantic Scholar source."""

import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import requests

from daily_paper.dates import validate_date
from daily_paper.normalizer import IMPACT_FACTOR_TABLE, finalize_paper, get_impact_factor
from daily_paper.queries import flatten_queries
from daily_paper.sources._citation_batch import batch_get_citation_counts  # noqa: F401
from daily_paper.text import normalize_doi

logger = logging.getLogger(__name__)


def get_citation_count(title, authors=None, year=None):
    """Fetch citation count for one title through Semantic Scholar."""
    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = {
        "query": title,
        "fields": "title,authors,year,citationCount",
        "limit": 1,
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("data"):
                return data["data"][0].get("citationCount", 0)
    except Exception as e:
        logger.warning("Semantic Scholar API query failed: %s", e)
    return None


def _build_ss_request_params(ss_config: Dict) -> Tuple[datetime, Optional[datetime], str, List[str], int, int, int]:
    """Build request controls for Semantic Scholar search."""
    queries = flatten_queries(ss_config)
    max_per_query = int(ss_config.get("max_results_per_query", 100))
    max_pages = max(1, int(ss_config.get("max_pages_per_query", 1)))
    stop_after_empty_pages = max(1, int(ss_config.get("stop_after_empty_pages", 1)))
    days_back = ss_config.get("days_back", 180)

    configured_start = validate_date(ss_config.get("start_date", ""))
    configured_end = validate_date(ss_config.get("end_date", ""))
    start_date = (
        datetime.strptime(configured_start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        if configured_start else datetime.now(timezone.utc) - timedelta(days=days_back)
    )
    end_date = (
        datetime.strptime(configured_end, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        if configured_end else None
    )
    year_from = start_date.year
    year_filter = f"{year_from}-{end_date.year}" if end_date else f"{year_from}-"
    return start_date, end_date, year_filter, queries, max_per_query, max_pages, stop_after_empty_pages


def _ss_request_with_retry(url: str, params: Dict, api_key: str = "") -> Optional[requests.Response]:
    """Semantic Scholar request with basic retry and 429 backoff."""
    headers = {}
    if api_key:
        headers["x-api-key"] = api_key
    for attempt in range(3):
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=30)
            if resp.status_code == 429:
                wait_seconds = 30 + attempt * 10
                logger.warning("Semantic Scholar API rate limited; waiting %ss", wait_seconds)
                time.sleep(wait_seconds)
                continue
            return resp
        except requests.RequestException as e:
            wait_seconds = 5 * (attempt + 1)
            logger.warning("Semantic Scholar request failed; retrying in %ss: %s", wait_seconds, e)
            time.sleep(wait_seconds)
    return None


def _ss_item_to_paper(item: Dict, config: Dict, start_date: datetime, end_date: Optional[datetime]) -> Optional[Dict]:
    """Convert one Semantic Scholar result into a normalized paper dict."""
    ext_ids = item.get("externalIds") or {}
    paper_id = ext_ids.get("DOI") or ext_ids.get("ArXiv") or item.get("paperId", "")

    pub_date = item.get("publicationDate")
    if pub_date:
        try:
            dt = datetime.strptime(pub_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            if dt < start_date or (end_date and dt > end_date):
                return None
            published = pub_date
        except ValueError:
            year = item.get("year")
            published = str(year) if year else "unknown"
    else:
        year = item.get("year")
        published = str(year) if year else "unknown"

    title = item.get("title") or ""
    if not title:
        return None

    arxiv_id = ext_ids.get("ArXiv")
    doi = ext_ids.get("DOI") or ""
    arxiv_url = f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else ""
    preprint_pdf_url = f"https://arxiv.org/pdf/{arxiv_id}" if arxiv_id else ""
    oa_pdf = item.get("openAccessPdf") or {}
    pdf_url = oa_pdf["url"] if oa_pdf and oa_pdf.get("url") else ""

    authors = ", ".join(a.get("name", "") for a in item.get("authors", []) if a.get("name"))
    journal = item.get("journal") or {}
    venue = (
        item.get("venue")
        or (item.get("publicationVenue") or {}).get("name")
        or journal.get("name")
        or ""
    )
    venue = re.sub(r"[….]{2,}", "", venue).strip(" ,;-")
    if venue and re.search(r"arXiv\s*(preprint)?", venue, re.IGNORECASE):
        venue = ""
    paper_url = (
        item.get("url")
        or (f"https://doi.org/{normalize_doi(doi)}" if doi else "")
        or arxiv_url
        or f"https://www.semanticscholar.org/paper/{item.get('paperId', '')}"
    )

    paper = {
        "id": paper_id,
        "title": title,
        "authors": authors,
        "abstract": item.get("abstract") or "",
        "published": published,
        "paper_url": paper_url,
        "arxiv_id": arxiv_id or "",
        "arxiv_url": arxiv_url,
        "pdf_url": pdf_url,
        "preprint_pdf_url": preprint_pdf_url,
        "categories": item.get("fieldsOfStudy") or [],
        "venue": venue,
        "conference": venue,
        "publication_types": item.get("publicationTypes") or [],
        "publication_type": "",
        "doi": doi,
        "external_ids": ext_ids,
        "semantic_scholar_id": item.get("paperId", ""),
        "code_link": "",
        "tags": [],
        "keywords": [],
        "citation_count": item.get("citationCount"),
        "impact_factor": get_impact_factor({"conference": venue}, IMPACT_FACTOR_TABLE),
        "source": "semantic_scholar",
    }
    return finalize_paper(paper, config)


def fetch_semantic_scholar_papers(config: Dict, ss_api_key: str = "", arxiv_client=None) -> List[Dict]:
    """Search Semantic Scholar by query, paging until no new deduplicated records appear."""
    ss_config = config.get("sources", {}).get("semantic_scholar", {})
    if not ss_config.get("enabled", False):
        logger.info("Semantic Scholar source disabled")
        return []

    start_date, end_date, year_filter, queries, max_per_query, max_pages, stop_after_empty_pages = (
        _build_ss_request_params(ss_config)
    )

    all_papers = []
    seen_ids = set()

    fields = (
        "paperId,url,title,abstract,authors,year,citationCount,"
        "venue,publicationVenue,publicationDate,publicationTypes,"
        "externalIds,openAccessPdf,fieldsOfStudy,journal"
    )

    for query in queries:
        logger.info("Semantic Scholar search: %s", query)
        query_count = 0
        empty_pages = 0

        for page in range(max_pages):
            params = {
                "query": query,
                "fields": fields,
                "limit": max_per_query,
                "offset": page * max_per_query,
                "year": year_filter,
            }
            try:
                resp = _ss_request_with_retry(
                    "https://api.semanticscholar.org/graph/v1/paper/search",
                    params,
                    api_key=ss_api_key,
                )
                if resp is None or resp.status_code != 200:
                    status = f", status {resp.status_code}" if resp else ""
                    logger.warning("Semantic Scholar API request failed%s", status)
                    break

                results = resp.json().get("data", [])
                if not results:
                    break

                page_new = 0
                for item in results:
                    ext_ids = item.get("externalIds") or {}
                    paper_id = ext_ids.get("DOI") or ext_ids.get("ArXiv") or item.get("paperId", "")
                    if paper_id in seen_ids:
                        continue

                    paper = _ss_item_to_paper(item, config, start_date, end_date)
                    if paper:
                        seen_ids.add(paper_id)
                        all_papers.append(paper)
                        query_count += 1
                        page_new += 1

                logger.info(
                    "  -> Semantic Scholar page %s/%s: new %s, total %s",
                    page + 1,
                    max_pages,
                    page_new,
                    len(all_papers),
                )
                empty_pages = empty_pages + 1 if page_new == 0 else 0
                if empty_pages >= stop_after_empty_pages or len(results) < max_per_query:
                    break
                time.sleep(3)

            except Exception as e:
                logger.warning("Semantic Scholar query failed (%s): %s", query, e)
                break

        logger.info("  -> Semantic Scholar query added %s, total %s", query_count, len(all_papers))
        time.sleep(3)

    logger.info("Semantic Scholar returned %s deduplicated papers", len(all_papers))
    return all_papers
