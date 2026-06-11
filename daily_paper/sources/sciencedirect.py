"""ScienceDirect (Elsevier) 数据源 — 通过浏览器抓取搜索结果

依赖学校图书馆网络 / VPN 访问 ScienceDirect。
使用 Chromium DevTools Protocol 自动化抓取（Edge/Chrome 均可）。
仅支持浏览器路径，无静态 HTTP fallback（ScienceDirect 全 JS 渲染）。
"""

import hashlib
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from dateutil import parser as date_parser

from daily_paper.dates import in_date_window, validate_date
from daily_paper.normalizer import IMPACT_FACTOR_TABLE, finalize_paper, get_impact_factor
from daily_paper.queries import flatten_queries
from daily_paper.sources.browser import evaluate_in_chrome
from daily_paper.text import normalize_title

logger = logging.getLogger(__name__)


def _enabled_env(name: str) -> bool:
    return os.environ.get(name, "").lower() in {"1", "true", "yes", "on"}


def _date_window(sd_config: dict) -> tuple[str, str]:
    days_back = int(sd_config.get("days_back", 30))
    from_date = validate_date(sd_config.get("start_date", "")) or (
        datetime.now(timezone.utc) - timedelta(days=days_back)
    ).strftime("%Y-%m-%d")
    until_date = validate_date(sd_config.get("end_date", ""))
    return from_date, until_date


def _parse_publication_date(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return ""
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


def _search_url(query: str, sd_config: dict, from_date: str, until_date: str) -> str:
    template = sd_config.get("search_url_template")
    if template:
        return template.format(
            query=query,
            query_plus=urlencode({"q": query})[2:],
            from_date=from_date,
            until_date=until_date,
            year=from_date[:4] if from_date else "",
        )
    params = {"qs": query}
    if from_date and (not until_date or from_date[:4] == until_date[:4]):
        params["date"] = from_date[:4]
    return "https://www.sciencedirect.com/search?" + urlencode(params)


def _skip_in_ci(sd_config: dict) -> bool:
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return False
    if _enabled_env("ENABLE_SCIENCEDIRECT") or _enabled_env("ENABLE_LOCAL_LIBRARY_SOURCES"):
        return False
    return bool(sd_config.get("local_only", True))


def _fetch_sciencedirect_with_browser(config: dict, queries: list[str], sd_config: dict) -> list[dict] | None:
    """通过 Edge/Chrome 浏览器抓取 ScienceDirect 搜索结果"""
    max_per_query = min(int(sd_config.get("max_results_per_query", 20)), 50)
    from_date, until_date = _date_window(sd_config)
    all_papers = []
    seen_titles = set()

    # — JS 脚本：等待搜索结果加载 → 提取每篇文章的元数据 —
    script = r"""
async () => {
  for (let i = 0; i < 30; i++) {
    if (document.querySelector('#srp-results') || document.querySelector('.result-list')
        || document.body.innerText.includes('Search results')) break;
    await new Promise(r => setTimeout(r, 500));
  }
  if (document.querySelector('#captcha') || document.body.innerText.includes('captcha')) {
    return { error: 'captcha', message: 'ScienceDirect requires CAPTCHA verification.' };
  }
  const items = document.querySelectorAll('#srp-results li.result-list-item, '
    + '#srp-results .result-item, .search-result-wrapper .result-item');
  const results = Array.from(items).map(item => {
    const titleEl = item.querySelector('.result-item-title a, h2.title-link a, .result-list-title a');
    const authorsEl = item.querySelector('.result-item-authors, .author-group, .authors');
    const journalEl = item.querySelector('.result-item-journal, .journal, .publication-title');
    const dateEl = item.querySelector('.result-item-date, .cover-date, .srp-date, .publication-date');
    const doiEl = item.querySelector('.result-item-doi, .doi, a[href*="doi.org"]');
    const abstractEl = item.querySelector('.result-item-abstract, .abstract, .snippet');
    const pdfEl = item.querySelector('.pdf-download a, .result-item-pdf-link a, a[href*="pdf"]');
    const doiHref = doiEl?.href || titleEl?.href || '';
    const doiMatch = doiHref.match(/(?:doi\.org\/|\/)(10\.\d{4,}\/[^\s?#]+)/i);
    const dateText = dateEl?.textContent?.trim() || '';
    return {
      title: titleEl?.textContent?.trim() || '',
      href: titleEl?.href || '',
      authors: authorsEl?.textContent?.trim() || '',
      journal: journalEl?.textContent?.trim() || '',
      date: dateText,
      doi: doiMatch ? doiMatch[1].replace(/[.]+$/, '') : '',
      abstract: abstractEl?.textContent?.trim() || '',
      pdfUrl: pdfEl?.href || ''
    };
  });
  return { resultCount: results.length, results };
}
"""

    for query in queries:
        url = _search_url(query, sd_config, from_date, until_date)
        logger.info(f"ScienceDirect 浏览器搜索: {query}")
        data = evaluate_in_chrome(url, script, "ScienceDirect", config, sd_config)
        if data is None:
            logger.warning("ScienceDirect 浏览器后端不可用；保留已抓取的部分结果。")
            return all_papers or None
        if data.get("error") == "captcha":
            logger.warning("ScienceDirect CAPTCHA 验证；保留已抓取的部分结果。")
            return all_papers or None

        for item in data.get("results", [])[:max_per_query]:
            title = item.get("title", "")
            title_norm = normalize_title(title)
            if not title_norm or title_norm in seen_titles:
                continue
            seen_titles.add(title_norm)

            authors = item.get("authors", "")
            journal = item.get("journal", "") or ""
            doi = item.get("doi", "")
            published = _parse_publication_date(item.get("date", "")) or "unknown"
            if not in_date_window(published, from_date, until_date):
                continue
            abstract = item.get("abstract", "") or ""
            pdf_url = item.get("pdfUrl", "") or ""
            paper_url = item.get("href", "") or (
                f"https://doi.org/{doi}" if doi else ""
            )
            venue = re.sub(r"\s+", " ", journal).strip()

            paper = {
                "id": doi or f"sd-{hashlib.md5(title_norm.encode()).hexdigest()[:12]}",
                "title": title,
                "authors": authors,
                "abstract": abstract,
                "abstract_status": "ok" if abstract else "",
                "published": published,
                "paper_url": paper_url,
                "arxiv_id": "",
                "arxiv_url": "",
                "pdf_url": pdf_url,
                "preprint_pdf_url": "",
                "categories": [],
                "venue": venue,
                "conference": venue,
                "publication_types": ["journal-article"] if venue else [],
                "publication_type": "",
                "doi": doi,
                "external_ids": {},
                "semantic_scholar_id": "",
                "code_link": "",
                "tags": [],
                "keywords": [],
                "citation_count": None,
                "impact_factor": get_impact_factor({"conference": venue}, IMPACT_FACTOR_TABLE),
                "source": "sciencedirect",
                "date_source": "sciencedirect",
                "date_status": "reliable" if re.fullmatch(r"\d{4}-\d{2}-\d{2}", published) else "approximate",
            }
            all_papers.append(finalize_paper(paper, config))

        logger.info(f"  → ScienceDirect 获取 {len(data.get('results', []))} 篇，累计 {len(all_papers)} 篇")
        time.sleep(2)

    logger.info(f"ScienceDirect 共获取 {len(all_papers)} 篇论文")
    return all_papers


def fetch_sciencedirect_papers(config: dict, ss_api_key: str = "", arxiv_client=None) -> list[dict]:
    """从 ScienceDirect 抓取论文（仅浏览器路径）

    需要：
    - 学校图书馆网络或 VPN 可访问 ScienceDirect
    - 本地运行 Edge/Chrome（remote-debugging-port=9222）
    """
    sd_config = config.get("sources", {}).get("sciencedirect", {})
    if not sd_config.get("enabled", False):
        logger.info("ScienceDirect 数据源已禁用")
        return []
    if _skip_in_ci(sd_config):
        logger.info("ScienceDirect 是本地机构网络源，GitHub Actions 默认跳过")
        return []

    queries = flatten_queries(sd_config.get("queries", []))
    if not queries:
        logger.info("ScienceDirect 未配置查询词")
        return []

    browser_papers = _fetch_sciencedirect_with_browser(config, queries, sd_config)
    if browser_papers is not None:
        logger.info(f"ScienceDirect 浏览器后端返回 {len(browser_papers)} 篇论文")
        return browser_papers

    logger.warning(
        "ScienceDirect 浏览器抓取失败。请确保：\n"
        "  1. Edge/Chrome 以 --remote-debugging-port=9222 运行\n"
        "  2. 学校网络可访问 sciencedirect.com\n"
        "  3. 未触发 CAPTCHA"
    )
    return []
