"""Web of Science / SCI 数据源。

本源面向两种本地使用方式：
1. 有 Clarivate API key 时，优先走 Web of Science API。
2. 没有 API key 但已连接学校图书馆网络/VPN 时，走本地 Edge/Chrome CDP 浏览器路径。

GitHub Actions 默认跳过该源，避免 hosted runner 因缺少机构网络或登录态而拖慢抓取。
"""

import hashlib
import json
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import requests
from dateutil import parser as date_parser

from daily_paper.dates import in_date_window, validate_date
from daily_paper.http import USER_AGENT
from daily_paper.normalizer import IMPACT_FACTOR_TABLE, finalize_paper, get_impact_factor
from daily_paper.queries import flatten_queries
from daily_paper.sources.browser import evaluate_in_chrome
from daily_paper.text import normalize_doi, normalize_title

logger = logging.getLogger(__name__)


def _enabled_env(name: str) -> bool:
    return os.environ.get(name, "").lower() in {"1", "true", "yes", "on"}


def _skip_in_ci(wos_config: dict) -> bool:
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return False
    if _enabled_env("ENABLE_WOS") or _enabled_env("ENABLE_LOCAL_LIBRARY_SOURCES"):
        return False
    return bool(wos_config.get("local_only", True))


def _api_key(wos_config: dict) -> str:
    return (
        wos_config.get("api_key")
        or os.environ.get("WOS_API_KEY")
        or os.environ.get("WEB_OF_SCIENCE_API_KEY")
        or os.environ.get("CLARIVATE_API_KEY")
        or ""
    ).strip()


def _date_window(wos_config: dict) -> tuple[str, str]:
    days_back = int(wos_config.get("days_back", 30))
    from_date = validate_date(wos_config.get("start_date", "")) or (
        datetime.now(timezone.utc) - timedelta(days=days_back)
    ).strftime("%Y-%m-%d")
    until_date = validate_date(wos_config.get("end_date", ""))
    return from_date, until_date


def _parse_publication_date(text: str) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if not text:
        return ""
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return text
    if re.fullmatch(r"(19|20)\d{2}", text):
        return text
    try:
        parsed = date_parser.parse(text, fuzzy=True, default=datetime(1900, 1, 1))
        if parsed.year >= 1900:
            return parsed.strftime("%Y-%m-%d")
    except (ValueError, OverflowError):
        pass
    year_match = re.search(r"(19|20)\d{2}", text)
    return year_match.group(0) if year_match else ""


def _first_text(*values) -> str:
    for value in values:
        if value is None:
            continue
        if isinstance(value, list):
            value = "; ".join(str(v) for v in value if v)
        if isinstance(value, dict):
            value = value.get("value") or value.get("name") or value.get("title") or ""
        text = re.sub(r"\s+", " ", str(value)).strip()
        if text:
            return text
    return ""


def _as_list(value) -> list:
    if not value:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _records_from_api(data: dict) -> list[dict]:
    if isinstance(data, list):
        return data
    for key in ("hits", "records", "documents", "results"):
        value = data.get(key)
        if isinstance(value, list):
            return value
    nested_records = (
        data.get("Data", {})
        .get("Records", {})
        .get("records", {})
        .get("REC")
    )
    if isinstance(nested_records, list):
        return nested_records
    if isinstance(nested_records, dict):
        return [nested_records]
    return []


def _names_to_authors(value) -> str:
    authors = []
    for author in _as_list(value):
        if isinstance(author, dict):
            name = author.get("displayName") or author.get("full_name") or author.get("name") or author.get("wos_standard")
        else:
            name = author
        name = re.sub(r"\s+", " ", str(name or "")).strip()
        if name:
            authors.append(name)
    return ", ".join(authors)


def _doi_from_item(item: dict) -> str:
    identifiers = item.get("identifiers") or {}
    if isinstance(identifiers, list):
        for identifier in identifiers:
            if str(identifier.get("type", "")).lower() == "doi":
                return normalize_doi(identifier.get("value", ""))
    return normalize_doi(
        item.get("doi")
        or item.get("DOI")
        or identifiers.get("doi")
        or identifiers.get("DOI")
        or ""
    )


def _paper_from_item(item: dict, config: dict) -> dict | None:
    source_info = item.get("source") or {}
    if not isinstance(source_info, dict):
        source_info = {}
    title = _first_text(
        item.get("title"),
        item.get("Title"),
        item.get("sourceTitle"),
        item.get("static_data", {}).get("summary", {}).get("titles", {}).get("title"),
    )
    title_norm = normalize_title(title)
    if not title_norm:
        return None

    doi = _doi_from_item(item)
    uid = _first_text(item.get("uid"), item.get("UT"), item.get("id"))
    authors = _names_to_authors(
        item.get("authors")
        or item.get("names")
        or item.get("static_data", {}).get("summary", {}).get("names", {}).get("name")
    )
    venue = _first_text(
        item.get("sourceTitle"),
        item.get("journal"),
        item.get("venue"),
        source_info.get("sourceTitle"),
        source_info.get("title"),
    )
    published = _parse_publication_date(
        item.get("publishedDate")
        or item.get("publicationDate")
        or item.get("date")
        or item.get("year")
        or source_info.get("publishedDate")
        or source_info.get("year")
    ) or "unknown"
    citation_count = item.get("timesCited") or item.get("timesCitedCount")
    citations = item.get("citations") or {}
    if citation_count is None and isinstance(citations, dict):
        citation_count = citations.get("timesCited") or citations.get("count")
    try:
        citation_count = int(citation_count) if citation_count is not None else None
    except (TypeError, ValueError):
        citation_count = None

    keywords = []
    for keyword in _as_list(item.get("keywords") or item.get("authorKeywords")):
        if isinstance(keyword, dict):
            keyword = keyword.get("value") or keyword.get("keyword")
        keyword = str(keyword or "").strip()
        if keyword:
            keywords.append(keyword)

    paper_url = _first_text(
        item.get("url"),
        item.get("recordLink"),
        item.get("links", {}).get("record") if isinstance(item.get("links"), dict) else "",
    )
    if not paper_url and uid:
        paper_url = f"https://www.webofscience.com/wos/woscc/full-record/{uid}"

    paper = {
        "id": doi or uid or f"wos-{hashlib.md5(title_norm.encode()).hexdigest()[:12]}",
        "title": title,
        "authors": authors,
        "abstract": _first_text(item.get("abstract"), item.get("summary")),
        "abstract_status": "ok" if item.get("abstract") else "",
        "published": published,
        "paper_url": paper_url,
        "arxiv_id": "",
        "arxiv_url": "",
        "pdf_url": "",
        "preprint_pdf_url": "",
        "categories": ["SCI", "Web of Science"],
        "venue": venue,
        "conference": venue,
        "publication_types": ["journal-article"] if venue else [],
        "publication_type": "",
        "doi": doi,
        "external_ids": {"WebOfScience": uid} if uid else {},
        "semantic_scholar_id": "",
        "code_link": "",
        "tags": [],
        "official_keywords": keywords,
        "keywords": keywords,
        "citation_count": citation_count,
        "impact_factor": get_impact_factor({"conference": venue}, IMPACT_FACTOR_TABLE),
        "source": "webofscience",
        "date_source": "webofscience",
        "date_status": "reliable" if re.fullmatch(r"\d{4}-\d{2}-\d{2}", published) else "approximate",
    }
    return finalize_paper(paper, config)


def _fetch_webofscience_api(config: dict, queries: list[str], wos_config: dict) -> list[dict] | None:
    key = _api_key(wos_config)
    if not key:
        return None

    api_url = wos_config.get("api_url", "https://api.clarivate.com/apis/wos-starter/v1/documents")
    query_param = wos_config.get("query_param", "q")
    max_per_query = min(int(wos_config.get("max_results_per_query", 20)), 50)
    from_date, until_date = _date_window(wos_config)
    headers = {
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
        "X-ApiKey": key,
    }
    all_papers = []
    seen = set()

    for query in queries:
        logger.info(f"Web of Science API 搜索: {query}")
        params = {
            query_param: query,
            wos_config.get("limit_param", "limit"): max_per_query,
        }
        if wos_config.get("from_date_param"):
            params[wos_config["from_date_param"]] = from_date
        if until_date and wos_config.get("until_date_param"):
            params[wos_config["until_date_param"]] = until_date

        data = None
        for attempt in range(3):
            try:
                response = requests.get(api_url, params=params, headers=headers, timeout=int(wos_config.get("timeout", 30)))
                if response.status_code == 200:
                    data = response.json()
                    break
                if response.status_code == 429:
                    time.sleep(5 * (attempt + 1))
                    continue
                logger.warning("Web of Science API 返回 %s: %s", response.status_code, response.text[:160])
                break
            except requests.RequestException as exc:
                logger.warning("Web of Science API 请求失败: %s", exc)
                if attempt == 2:
                    break
                time.sleep(2)
        if not data:
            continue

        query_count = 0
        for item in _records_from_api(data):
            paper = _paper_from_item(item, config)
            if not paper or not in_date_window(paper.get("published", ""), from_date, until_date):
                continue
            key = paper.get("doi") or paper.get("external_ids", {}).get("WebOfScience") or normalize_title(paper.get("title", ""))
            if not key or key in seen:
                continue
            seen.add(key)
            all_papers.append(paper)
            query_count += 1
        logger.info(f"  → Web of Science API 获取 {query_count} 篇，累计 {len(all_papers)} 篇")
        time.sleep(float(wos_config.get("delay", 1.0)))

    return all_papers


def _browser_search_url(query: str, wos_config: dict, from_date: str, until_date: str) -> str:
    template = wos_config.get("search_url_template")
    if template:
        return template.format(
            query=query,
            query_plus=urlencode({"q": query})[2:],
            from_date=from_date,
            until_date=until_date,
            year=from_date[:4] if from_date else "",
        )
    return "https://www.webofscience.com/wos/woscc/basic-search"


def _browser_script(query: str) -> str:
    query_json = json.dumps(query)
    return f"""
async () => {{
  const query = {query_json};
  const wait = ms => new Promise(r => setTimeout(r, ms));
  const visible = el => !!(el && el.offsetParent !== null);
  const hasResults = () => document.querySelector('[data-ta=\"summary-record\"], .summary-record, .search-results-item, app-record, .record-card');

  if (!hasResults()) {{
    const inputs = Array.from(document.querySelectorAll('textarea, input[type=\"text\"], input[type=\"search\"], [contenteditable=\"true\"]'));
    const input = inputs.find(visible);
    if (input) {{
      input.focus();
      if (input.isContentEditable) {{
        input.textContent = query;
      }} else {{
        input.value = query;
      }}
      input.dispatchEvent(new InputEvent('input', {{ bubbles: true, inputType: 'insertText', data: query }}));
      input.dispatchEvent(new Event('change', {{ bubbles: true }}));
      await wait(300);
      const buttons = Array.from(document.querySelectorAll('button, a, [role=\"button\"]'));
      const searchButton = buttons.find(el => /search|检索|搜索/i.test(el.textContent || el.getAttribute('aria-label') || ''));
      if (searchButton) searchButton.click();
    }}
  }}

  for (let i = 0; i < 60; i++) {{
    const text = document.body ? document.body.innerText : '';
    if (hasResults()) break;
    if (/captcha|verify|access denied|sign in|institutional login/i.test(text)) {{
      return {{ error: 'blocked', message: text.slice(0, 300) }};
    }}
    await wait(500);
  }}

  const items = Array.from(document.querySelectorAll('[data-ta=\"summary-record\"], .summary-record, .search-results-item, app-record, .record-card'));
  const results = items.map(item => {{
    const text = item.innerText || '';
    const titleEl = item.querySelector('[data-ta=\"summary-record-title\"] a, a[data-ta=\"summary-record-title\"], h3 a, h2 a, a[href*=\"full-record\"], a[href*=\"wos\"]');
    const doiMatch = text.match(/10\\.\\d{{4,9}}\\/[-._;()/:A-Z0-9]+/i);
    const citedMatch = text.match(/(?:Times Cited|被引频次|Citations?)\\s*:?\\s*(\\d+)/i);
    const yearMatch = text.match(/(19|20)\\d{{2}}/);
    const sourceEl = item.querySelector('[data-ta*=\"source\"], .source-title, .journal-title, [class*=\"source\"], [class*=\"journal\"]');
    const authorEl = item.querySelector('[data-ta*=\"author\"], .authors, [class*=\"author\"]');
    return {{
      title: titleEl?.textContent?.trim() || '',
      href: titleEl?.href || '',
      authors: authorEl?.textContent?.trim() || '',
      journal: sourceEl?.textContent?.trim() || '',
      date: yearMatch ? yearMatch[0] : '',
      doi: doiMatch ? doiMatch[0].replace(/[.,;]+$/, '') : '',
      citedBy: citedMatch ? citedMatch[1] : '',
      uid: item.getAttribute('data-record-id') || item.getAttribute('data-id') || ''
    }};
  }});
  return {{ resultCount: results.length, results }};
}}
"""


def _fetch_webofscience_browser(config: dict, queries: list[str], wos_config: dict) -> list[dict] | None:
    if not wos_config.get("use_browser", True):
        return None

    max_per_query = min(int(wos_config.get("max_results_per_query", 20)), 50)
    from_date, until_date = _date_window(wos_config)
    all_papers = []
    seen = set()

    for query in queries:
        logger.info(f"Web of Science 浏览器搜索: {query}")
        url = _browser_search_url(query, wos_config, from_date, until_date)
        data = evaluate_in_chrome(url, _browser_script(query), "Web of Science", config, wos_config)
        if data is None:
            logger.warning("Web of Science 浏览器后端不可用；保留已抓取的部分结果。")
            return all_papers or None
        if data.get("error"):
            logger.warning("Web of Science 浏览器路径受阻: %s", data.get("message", data.get("error")))
            return all_papers or None

        query_count = 0
        for item in data.get("results", [])[:max_per_query]:
            paper = _paper_from_item({
                "title": item.get("title", ""),
                "authors": item.get("authors", ""),
                "sourceTitle": item.get("journal", ""),
                "publishedDate": item.get("date", ""),
                "doi": item.get("doi", ""),
                "url": item.get("href", ""),
                "uid": item.get("uid", ""),
                "timesCited": item.get("citedBy") or None,
            }, config)
            if not paper or not in_date_window(paper.get("published", ""), from_date, until_date):
                continue
            key = paper.get("doi") or paper.get("external_ids", {}).get("WebOfScience") or normalize_title(paper.get("title", ""))
            if not key or key in seen:
                continue
            seen.add(key)
            all_papers.append(paper)
            query_count += 1
        logger.info(f"  → Web of Science 浏览器获取 {query_count} 篇，累计 {len(all_papers)} 篇")
        time.sleep(float(wos_config.get("delay", 1.5)))

    return all_papers


def fetch_webofscience_papers(config: dict, ss_api_key: str = "", arxiv_client=None) -> list[dict]:
    wos_config = config.get("sources", {}).get("webofscience", {})
    if not wos_config.get("enabled", False):
        logger.info("Web of Science 数据源已禁用")
        return []
    if _skip_in_ci(wos_config):
        logger.info("Web of Science/SCI 是本地机构网络源，GitHub Actions 默认跳过")
        return []

    queries = flatten_queries(wos_config.get("queries", []))
    if not queries:
        logger.info("Web of Science 未配置查询词")
        return []

    api_papers = _fetch_webofscience_api(config, queries, wos_config)
    if api_papers is not None:
        logger.info(f"Web of Science API 返回 {len(api_papers)} 篇论文")
        return api_papers

    browser_papers = _fetch_webofscience_browser(config, queries, wos_config)
    if browser_papers is not None:
        logger.info(f"Web of Science 浏览器后端返回 {len(browser_papers)} 篇论文")
        return browser_papers

    logger.warning(
        "Web of Science 抓取失败。请确保：\n"
        "  1. 已设置 WOS_API_KEY / WEB_OF_SCIENCE_API_KEY，或\n"
        "  2. 本地 Edge/Chrome 以 --remote-debugging-port=9222 运行并已通过学校图书馆网络登录 Web of Science"
    )
    return []
