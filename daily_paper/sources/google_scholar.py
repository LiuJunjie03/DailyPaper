"""Google Scholar 数据源"""
import requests
import time
import re
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from urllib.parse import quote_plus

from daily_paper.text import normalize_title
from daily_paper.sources.browser import evaluate_in_chrome

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


def _fetch_google_scholar_with_browser(fetcher, queries: List[str], gs_config: Dict) -> Optional[List[Dict]]:
    max_per_query = min(int(gs_config.get("max_results_per_query", 10)), 20)
    year_from = gs_config.get("year_from", (datetime.now(timezone.utc) - timedelta(days=365)).year)
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
        url = (
            "https://scholar.google.com/scholar"
            f"?q={quote_plus(query)}&hl=en&num={max_per_query}&as_ylo={year_from}"
        )
        logger.info(f"Google Scholar browser search: {query}")
        data = evaluate_in_chrome(url, script, "Google Scholar", fetcher.config, gs_config)
        if data is None:
            return None
        if data.get("error") == "captcha":
            logger.warning("Google Scholar CAPTCHA required in Chrome; skipping browser backend.")
            return None

        for item in data.get("results", [])[:max_per_query]:
            title = item.get("title", "")
            title_norm = normalize_title(title)
            if not title_norm or title_norm in seen_titles:
                continue
            seen_titles.add(title_norm)
            journal_year = item.get("journalYear", "")
            year_match = re.search(r"(19|20)\d{2}", journal_year)
            venue = re.sub(r"\b(19|20)\d{2}\b", "", journal_year).strip(" ,;-")
            snippet = item.get("snippet", "")
            paper = {
                "id": f"gs-{item.get('dataCid') or hashlib.md5(title_norm.encode()).hexdigest()[:12]}",
                "title": title,
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
                "impact_factor": fetcher.get_impact_factor({"conference": venue}),
                "source": "google_scholar",
            }
            all_papers.append(fetcher._finalize_paper(paper))
        time.sleep(2)

    return all_papers

def fetch_google_scholar_papers(fetcher) -> List[Dict]:
    """从 Google Scholar 抓取论文（使用 scholarly 库）"""
    gs_config = fetcher.config.get("sources", {}).get("google_scholar", {})
    if not gs_config.get("enabled", False):
        logger.info("Google Scholar 数据源已禁用")
        return []

    # 支持 dict 格式的 queries（和 Semantic Scholar 一致）
    queries = fetcher._flatten_queries(gs_config.get("queries", []))

    max_per_query = gs_config.get("max_results_per_query", 10)
    year_from = gs_config.get("year_from",
        (datetime.now(timezone.utc) - timedelta(days=365)).year)

    browser_papers = _fetch_google_scholar_with_browser(fetcher, queries, gs_config)
    if browser_papers is not None:
        logger.info(f"Google Scholar browser backend returned {len(browser_papers)} papers")
        return browser_papers

    try:
        from scholarly import scholarly as gs_module
    except ImportError:
        logger.warning("scholarly 库未安装，跳过 Google Scholar 数据源。请运行: pip install scholarly")
        return []

    all_papers = []
    seen_titles = set()

    for query in queries:
        logger.info(f"Google Scholar 搜索: {query}")
        try:
            search_results = gs_module.search_pubs(query, year_low=year_from)
            count = 0
            for result in search_results:
                if count >= max_per_query:
                    break

                bib = result.get("bib", {})
                title = bib.get("title", "")
                if not title:
                    continue
                title_norm = normalize_title(title)
                if title_norm in seen_titles:
                    continue
                seen_titles.add(title_norm)

                authors_raw = bib.get("author", [])
                if isinstance(authors_raw, str):
                    authors_str = authors_raw
                else:
                    authors_str = ", ".join(str(a) for a in authors_raw)

                venue = bib.get("venue", "") or bib.get("journal", "") or ""
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
                    "impact_factor": fetcher.get_impact_factor({"conference": venue}),
                    "source": "google_scholar",
                }

                paper = fetcher._finalize_paper(paper)
                all_papers.append(paper)
                count += 1

            logger.info(f"  → Google Scholar 获取 {count} 篇")
            time.sleep(3)  # 避免触发反爬

        except Exception as e:
            logger.warning(f"Google Scholar 查询失败 ({query}): {e}")
            continue

    logger.info(f"Google Scholar 共获取 {len(all_papers)} 篇论文")
    return all_papers
