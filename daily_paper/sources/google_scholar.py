"""Google Scholar source.

Scholar snippets are discovery metadata only. They must not be treated as
reliable abstracts unless another trusted source enriches the record later.
"""

import hashlib
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from urllib.parse import quote_plus

from daily_paper.normalizer import IMPACT_FACTOR_TABLE, finalize_paper, get_impact_factor
from daily_paper.queries import flatten_queries
from daily_paper.sources.browser import evaluate_in_chrome
from daily_paper.text import normalize_title

logger = logging.getLogger(__name__)


def _looks_like_scholar_snippet(text: str) -> bool:
    """Google Scholar search snippets are fragments, not reliable abstracts."""
    text = (text or "").strip()
    if not text:
        return False
    return (
        len(text) < 220
        or text[:1].islower()
        or "..." in text
        or re.search(r"\s{2,}", text) is not None
        or not text.endswith((".", "!", "?"))
    )


def _clean_scholar_venue(value: str) -> str:
    """Remove year and snippet artifacts from Google Scholar venue strings."""
    venue = re.sub(r"\b(19|20)\d{2}\b", "", value or "").strip(" ,;-")
    venue = venue.replace("…", "")
    venue = re.sub(r"\.{2,}", "", venue).strip(" ,;-")
    if re.search(r"arXiv\s*(preprint)?", venue, re.IGNORECASE):
        return ""
    return venue


def _build_browser_paper(item: Dict, title_norm: str, year_from: int, config: Dict) -> Dict:
    journal_year = item.get("journalYear", "")
    year_match = re.search(r"(19|20)\d{2}", journal_year)
    venue = _clean_scholar_venue(journal_year)
    snippet = item.get("snippet", "")
    paper = {
        "id": f"gs-{item.get('dataCid') or hashlib.md5(title_norm.encode()).hexdigest()[:12]}",
        "title": item.get("title", ""),
        "authors": item.get("authors", ""),
        "abstract": "",
        "abstract_status": "unreliable_google_scholar_snippet",
        "scholar_snippet": snippet,
        "published": year_match.group(0) if year_match else str(year_from),
        "paper_url": item.get("href", "") or item.get("fullTextUrl", ""),
        "arxiv_id": "",
        "arxiv_url": "",
        "pdf_url": item.get("fullTextUrl", ""),
        "preprint_pdf_url": "",
        "categories": [],
        "venue": venue,
        "conference": venue,
        "publication_types": [],
        "publication_type": "",
        "doi": "",
        "external_ids": {"GoogleScholarCID": item.get("dataCid", "")},
        "semantic_scholar_id": "",
        "code_link": "",
        "tags": [],
        "keywords": [],
        "citation_count": int(item.get("citedBy") or 0),
        "impact_factor": get_impact_factor({"conference": venue}, IMPACT_FACTOR_TABLE),
        "source": "google_scholar",
    }
    return finalize_paper(paper, config)


def _fetch_google_scholar_with_browser(
    config: Dict,
    queries: List[str],
    gs_config: Dict,
) -> Optional[List[Dict]]:
    max_per_query = min(int(gs_config.get("max_results_per_query", 10)), 20)
    max_pages = max(1, int(gs_config.get("max_pages_per_query", 1)))
    stop_after_empty_pages = max(1, int(gs_config.get("stop_after_empty_pages", 1)))
    year_from = int(gs_config.get("year_from", (datetime.now(timezone.utc) - timedelta(days=365)).year))
    all_papers = []
    seen_titles = set()

    script = """
async () => {
  for (let i = 0; i < 30; i++) {
    if (document.querySelector('#gs_res_ccl') || document.querySelector('#gs_captcha_ccl')) break;
    await new Promise(r => setTimeout(r, 500));
  }
  if (document.querySelector('#gs_captcha_ccl') || document.body.innerText.includes('unusual traffic')) {
    return { error: 'captcha', message: 'Google Scholar requires CAPTCHA verification.' };
  }
  const items = document.querySelectorAll('#gs_res_ccl .gs_r.gs_or.gs_scl');
  const results = Array.from(items).map((item, i) => {
    const titleEl = item.querySelector('.gs_rt a');
    const meta = item.querySelector('.gs_a')?.textContent || '';
    const parts = meta.split(' - ');
    const citedByEl = item.querySelector('.gs_fl a[href*="cites"]');
    const versionsEl = item.querySelector('.gs_fl a[href*="cluster"]');
    return {
      n: i + 1,
      title: titleEl?.textContent?.trim() || item.querySelector('.gs_rt')?.textContent?.trim() || '',
      href: titleEl?.href || '',
      authors: parts[0]?.trim() || '',
      journalYear: parts[1]?.trim() || '',
      citedBy: citedByEl?.textContent?.match(/\\d+/)?.[0] || '0',
      dataCid: item.getAttribute('data-cid') || '',
      fullTextUrl: (item.querySelector('.gs_ggs a') || item.querySelector('.gs_or_ggsm a'))?.href || '',
      snippet: item.querySelector('.gs_rs')?.textContent?.trim() || '',
      versions: versionsEl?.textContent?.match(/\\d+/)?.[0] || ''
    };
  });
  return { resultCount: results.length, results };
}
"""

    for query in queries:
        logger.info("Google Scholar browser search: %s", query)
        query_count = 0
        empty_pages = 0

        for page in range(max_pages):
            url = (
                "https://scholar.google.com/scholar"
                f"?q={quote_plus(query)}&hl=en&num={max_per_query}&as_ylo={year_from}"
                f"&start={page * max_per_query}"
            )
            data = evaluate_in_chrome(url, script, "Google Scholar", config, gs_config)
            if data is None:
                return None
            if data.get("error") == "captcha":
                logger.warning("Google Scholar CAPTCHA required in Chrome; skipping browser backend.")
                return None

            results = data.get("results", [])[:max_per_query]
            if not results:
                break

            page_new = 0
            for item in results:
                title_norm = normalize_title(item.get("title", ""))
                if not title_norm or title_norm in seen_titles:
                    continue
                seen_titles.add(title_norm)
                all_papers.append(_build_browser_paper(item, title_norm, year_from, config))
                query_count += 1
                page_new += 1

            logger.info(
                "  -> Google Scholar page %s/%s: new %s, total %s",
                page + 1,
                max_pages,
                page_new,
                len(all_papers),
            )
            empty_pages = empty_pages + 1 if page_new == 0 else 0
            if empty_pages >= stop_after_empty_pages or len(results) < max_per_query:
                break
            time.sleep(2)

        logger.info("  -> Google Scholar query added %s, total %s", query_count, len(all_papers))
        time.sleep(2)

    return all_papers


def fetch_google_scholar_papers(config: Dict, ss_api_key: str = "", arxiv_client=None) -> List[Dict]:
    """Fetch Google Scholar records with browser first, then scholarly fallback."""
    gs_config = config.get("sources", {}).get("google_scholar", {})
    if not gs_config.get("enabled", False):
        logger.info("Google Scholar source disabled")
        return []

    queries = flatten_queries(gs_config.get("queries", []))
    max_per_query = int(gs_config.get("max_results_per_query", 10))
    max_pages = max(1, int(gs_config.get("max_pages_per_query", 1)))
    max_total_per_query = max_per_query * max_pages
    year_from = int(gs_config.get("year_from", (datetime.now(timezone.utc) - timedelta(days=365)).year))

    browser_papers = _fetch_google_scholar_with_browser(config, queries, gs_config)
    if browser_papers is not None:
        logger.info("Google Scholar browser backend returned %s papers", len(browser_papers))
        return browser_papers

    try:
        from scholarly import scholarly as gs_module
    except ImportError:
        logger.warning("scholarly is not installed; skipping Google Scholar fallback.")
        return []

    all_papers = []
    seen_titles = set()

    for query in queries:
        logger.info("Google Scholar fallback search: %s", query)
        try:
            search_results = gs_module.search_pubs(query, year_low=year_from)
            count = 0
            inspected = 0
            page_new = 0
            for result in search_results:
                if count >= max_total_per_query:
                    break

                inspected += 1
                bib = result.get("bib", {})
                title = bib.get("title", "")
                if not title:
                    continue
                title_norm = normalize_title(title)
                if title_norm in seen_titles:
                    if inspected % max_per_query == 0 and page_new == 0:
                        break
                    continue
                seen_titles.add(title_norm)

                authors_raw = bib.get("author", [])
                if isinstance(authors_raw, str):
                    authors_str = authors_raw
                else:
                    authors_str = ", ".join(str(a) for a in authors_raw)

                venue = _clean_scholar_venue(bib.get("venue", "") or bib.get("journal", "") or "")
                pub_year = str(bib.get("pub_year", "")) if bib.get("pub_year") else ""
                abstract = bib.get("abstract", "") or ""
                abstract_status = "ok"
                scholar_snippet = ""
                if _looks_like_scholar_snippet(abstract):
                    scholar_snippet = abstract
                    abstract = ""
                    abstract_status = "unreliable_google_scholar_snippet"

                paper = {
                    "id": f"gs-{hashlib.md5(title_norm.encode()).hexdigest()[:12]}",
                    "title": title,
                    "authors": authors_str,
                    "abstract": abstract,
                    "abstract_status": abstract_status,
                    "scholar_snippet": scholar_snippet,
                    "published": pub_year or "unknown",
                    "paper_url": result.get("pub_url", "") or result.get("eprint_url", "") or "",
                    "arxiv_id": "",
                    "arxiv_url": "",
                    "pdf_url": result.get("eprint_url", "") or "",
                    "preprint_pdf_url": "",
                    "categories": [],
                    "venue": venue,
                    "conference": venue,
                    "publication_types": [],
                    "publication_type": "",
                    "doi": "",
                    "external_ids": {},
                    "semantic_scholar_id": "",
                    "code_link": "",
                    "tags": [],
                    "keywords": [],
                    "citation_count": result.get("num_citations"),
                    "impact_factor": get_impact_factor({"conference": venue}, IMPACT_FACTOR_TABLE),
                    "source": "google_scholar",
                }

                all_papers.append(finalize_paper(paper, config))
                count += 1
                page_new += 1
                if inspected % max_per_query == 0:
                    page_new = 0

            logger.info("  -> Google Scholar fallback added %s papers", count)
            time.sleep(3)

        except Exception as e:
            logger.warning("Google Scholar query failed (%s): %s", query, e)
            continue

    logger.info("Google Scholar returned %s papers", len(all_papers))
    return all_papers
