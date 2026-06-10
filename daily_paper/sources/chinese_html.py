"""Generic HTML search support for Chinese literature portals."""

import hashlib
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional
from urllib.parse import quote_plus, urljoin

import requests
from bs4 import BeautifulSoup

from daily_paper.text import normalize_title, clean_text
from daily_paper.dates import parse_date as complete_date, in_date_window
from daily_paper.queries import flatten_queries
from daily_paper.sources.browser import evaluate_in_chrome


logger = logging.getLogger(__name__)


def request_html(url: str, params: Optional[Dict] = None, timeout: int = 25) -> Optional[str]:
    try:
        response = requests.get(
            url,
            params=params,
            timeout=timeout,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            },
        )
        if response.status_code == 200:
            response.encoding = response.apparent_encoding or response.encoding
            return response.text
        logger.info("Chinese source request returned %s: %s", response.status_code, url)
    except requests.RequestException as exc:
        logger.info("Chinese source request failed: %s (%s)", url, exc)
    return None


def rendered_html(url: str, params: Dict, fetcher, config: Dict, source_label: str) -> Optional[str]:
    if not config.get("use_browser", False):
        return None
    if os.environ.get("GITHUB_ACTIONS") == "true":
        return None
    if config.get("_browser_unavailable"):
        return None
    full_url = requests.Request("GET", url, params=params).prepare().url
    script = r"""
async () => {
  for (let i = 0; i < 30; i++) {
    const text = document.body ? document.body.innerText : '';
    if (document.querySelector('.result-item, .list-item, .doc-item, li, tr') && text.length > 200) break;
    await new Promise(r => setTimeout(r, 500));
  }
  return { html: document.documentElement.outerHTML };
}
"""
    data = evaluate_in_chrome(full_url, script, source_label, fetcher.config, config)
    if data is None:
        config["_browser_unavailable"] = True
        return None
    return data.get("html") or ""


def search_url_and_params(config: Dict, query: str, default_url: str) -> tuple[str, Dict]:
    template = config.get("search_url_template")
    if template:
        return template.format(query=quote_plus(query), raw_query=query), {}
    url = config.get("search_url") or default_url
    query_param = config.get("query_param", "q")
    return url, {query_param: query}


def select_first_text(container, selectors: Iterable[str]) -> str:
    for selector in selectors:
        found = container.select_one(selector)
        if found:
            text = clean_text(found.get_text(" "))
            if text:
                return text
    return ""


def select_link(container, selectors: Iterable[str]):
    for selector in selectors:
        for link in container.select(selector):
            text = clean_text(link.get_text(" "))
            href = link.get("href", "")
            if text and href:
                return link
    return None


def meta_content(soup: BeautifulSoup, *names: str) -> str:
    for name in names:
        tag = soup.find("meta", attrs={"name": name}) or soup.find("meta", attrs={"property": name})
        value = clean_text(tag.get("content", "") if tag else "")
        if value:
            return value
    return ""


def parse_detail_page(url: str) -> Dict:
    html = request_html(url)
    if not html:
        return {}
    soup = BeautifulSoup(html, "lxml")
    authors = [
        clean_text(tag.get("content", ""))
        for tag in soup.find_all("meta", attrs={"name": "citation_author"})
        if clean_text(tag.get("content", ""))
    ]
    keywords = meta_content(soup, "citation_keywords", "keywords")
    abstract = meta_content(soup, "citation_abstract", "dc.description", "description")
    return {
        "title": meta_content(soup, "citation_title", "dc.title") or clean_text(soup.title.get_text(" ") if soup.title else ""),
        "authors": "; ".join(authors),
        "abstract": abstract,
        "published": complete_date(meta_content(soup, "citation_publication_date", "dc.date")),
        "venue": meta_content(soup, "citation_journal_title", "citation_conference_title"),
        "doi": meta_content(soup, "citation_doi", "dc.identifier"),
        "keywords": [kw.strip() for kw in re.split(r"[;,；，]", keywords) if kw.strip()],
        "pdf_url": meta_content(soup, "citation_pdf_url"),
    }


def parse_search_results(html: str, base_url: str, config: Dict) -> List[Dict]:
    soup = BeautifulSoup(html or "", "lxml")
    result_selectors = config.get("result_selectors") or [
        ".result-list .item",
        ".result-item",
        ".list-item",
        ".doc-list .doc-item",
        "li",
        "tr",
    ]
    title_selectors = config.get("title_selectors") or [
        "a[title]",
        ".title a",
        ".name a",
        "h3 a",
        "h4 a",
        "a",
    ]
    author_selectors = config.get("author_selectors") or [".author", ".authors", "[class*=author]"]
    venue_selectors = config.get("venue_selectors") or [".source", ".journal", ".periodical", "[class*=source]"]
    date_selectors = config.get("date_selectors") or [".date", ".year", "[class*=date]", "[class*=year]"]
    snippet_selectors = config.get("snippet_selectors") or [".abstract", ".summary", ".snippet", "[class*=abstract]", "[class*=summary]"]

    records = []
    seen_links = set()
    for container in soup.select(",".join(result_selectors)):
        link = select_link(container, title_selectors)
        if not link:
            continue
        title = clean_text(link.get("title") or link.get_text(" "))
        href = urljoin(base_url, link.get("href", ""))
        if not title or len(title) < 4 or href in seen_links:
            continue
        seen_links.add(href)
        container_text = clean_text(container.get_text(" "))
        if title not in container_text:
            continue
        snippet = select_first_text(container, snippet_selectors)
        records.append({
            "title": title,
            "paper_url": href,
            "authors": select_first_text(container, author_selectors),
            "venue": select_first_text(container, venue_selectors),
            "published": complete_date(select_first_text(container, date_selectors) or container_text),
            "source_snippet": snippet,
        })
    return records


def build_paper(fetcher, source_key: str, source_label: str, prefix: str, record: Dict, config: Dict) -> Optional[Dict]:
    title = record.get("title", "")
    title_norm = normalize_title(title)
    if not title_norm:
        return None

    detail = {}
    if config.get("enrich_details", True) and record.get("paper_url"):
        detail = parse_detail_page(record["paper_url"])
        time.sleep(float(config.get("detail_delay", 0.2)))

    abstract = clean_text(detail.get("abstract") or "")
    source_snippet = clean_text(record.get("source_snippet") or "")
    abstract_status = "enriched" if abstract else ("search_snippet_only" if source_snippet else "")

    authors = detail.get("authors") or record.get("authors") or ""
    venue = detail.get("venue") or record.get("venue") or ""
    published = detail.get("published") or record.get("published") or "unknown"
    doi = detail.get("doi") or ""

    paper = {
        "id": f"{prefix}-{hashlib.md5(title_norm.encode()).hexdigest()[:12]}",
        "title": detail.get("title") or title,
        "authors": authors,
        "abstract": abstract,
        "abstract_status": abstract_status,
        "abstract_source": source_key if abstract else "",
        "source_snippet": source_snippet,
        "published": published,
        "paper_url": record.get("paper_url", ""),
        "arxiv_id": "",
        "arxiv_url": "",
        "pdf_url": detail.get("pdf_url") or "",
        "preprint_pdf_url": "",
        "categories": [source_label],
        "venue": venue,
        "conference": venue,
        "publication_types": ["journal-article"],
        "publication_type": "",
        "doi": doi,
        "external_ids": {},
        "semantic_scholar_id": "",
        "code_link": "",
        "tags": [],
        "keywords": detail.get("keywords") or [],
        "citation_count": None,
        "impact_factor": fetcher.get_impact_factor({"conference": venue}),
        "source": source_key,
    }
    return fetcher._finalize_paper(paper)


def fetch_chinese_html_source(fetcher, source_key: str, source_label: str, default_url: str, prefix: str) -> List[Dict]:
    config = fetcher.config.get("sources", {}).get(source_key, {})
    if not config.get("enabled", False):
        logger.info("%s 数据源已禁用", source_label)
        return []

    queries = flatten_queries(config)
    max_per_query = int(config.get("max_results_per_query", 10))
    days_back = int(config.get("days_back", 180))
    from_date = config.get("start_date") or (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%d")
    until_date = config.get("end_date", "")
    delay = float(config.get("delay", 1.0))

    papers = []
    seen_titles = set()
    for query in queries:
        logger.info("%s 搜索: %s", source_label, query)
        url, params = search_url_and_params(config, query, default_url)
        html = request_html(url, params=params)
        if not html:
            continue
        records = parse_search_results(html, url, config)[:max_per_query]
        if not records:
            dynamic_html = rendered_html(url, params, fetcher, config, source_label)
            if dynamic_html:
                records = parse_search_results(dynamic_html, url, config)[:max_per_query]
        query_count = 0
        for record in records:
            title_norm = normalize_title(record.get("title", ""))
            if not title_norm or title_norm in seen_titles:
                continue
            if not in_date_window(record.get("published", ""), from_date, until_date):
                continue
            paper = build_paper(fetcher, source_key, source_label, prefix, record, config)
            if not paper:
                continue
            seen_titles.add(title_norm)
            papers.append(paper)
            query_count += 1
        logger.info("  -> %s 获取 %s 篇，累计 %s 篇", source_label, query_count, len(papers))
        time.sleep(delay)

    logger.info("%s 共获取 %s 篇论文", source_label, len(papers))
    return papers
