"""CNKI (中国知网) 数据源"""
import hashlib
import json
import logging
import os
import re
import time
from typing import Dict, List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from daily_paper.normalizer import IMPACT_FACTOR_TABLE, finalize_paper, get_impact_factor
from daily_paper.queries import flatten_queries
from daily_paper.sources.browser import evaluate_in_chrome
from daily_paper.sources.cnki_detail import enrich_cnki_paper
from daily_paper.text import normalize_title

logger = logging.getLogger(__name__)


DEFAULT_KNS_BASE_URL = "https://kns.cnki.net"


def _cnki_url(cnki_config: Dict, key: str, default_path: str) -> str:
    # 优先使用环境变量（CNKI_HOME_URL / CNKI_KNS_BASE_URL）
    env_key = f"CNKI_{key.upper()}"
    env_val = os.environ.get(env_key, "").strip()
    if env_val:
        return env_val
    configured = cnki_config.get(key)
    if configured:
        return configured
    base_url = (
        os.environ.get("CNKI_KNS_BASE_URL", "").strip()
        or cnki_config.get("kns_base_url")
        or DEFAULT_KNS_BASE_URL
    )
    return urljoin(base_url.rstrip("/") + "/", default_path.lstrip("/"))


def _absolute_cnki_url(cnki_config: Dict, href: str) -> str:
    href = href or ""
    if href.startswith(("http://", "https://")):
        return href
    base_url = cnki_config.get("detail_base_url") or cnki_config.get("kns_base_url") or DEFAULT_KNS_BASE_URL
    return urljoin(base_url.rstrip("/") + "/", href.lstrip("/"))


def _cnki_query_specs(cnki_config: Dict) -> List[Dict[str, str]]:
    """Normalize simple legacy queries and structured advanced-search queries."""
    raw_queries = cnki_config.get("advanced_queries") or flatten_queries(cnki_config.get("queries", []))
    specs = []
    for item in raw_queries:
        if isinstance(item, str):
            query = item.strip()
            journal = ""
        elif isinstance(item, dict):
            query = str(item.get("topic") or item.get("query") or "").strip()
            journal = str(item.get("journal") or item.get("venue") or "").strip()
        else:
            continue
        if query:
            specs.append({"query": query, "journal": journal})
    return specs


def _cnki_advanced_browser_script(query: str, journal: str, max_per_query: int, max_pages: int) -> str:
    """Return a DOM-only extractor for the current KNS8 advanced-search UI.

    CNKI renders the result table client side.  The script therefore fills the
    visible advanced-search inputs, reads each displayed result page, and clicks
    only the visible next-page control.  It deliberately returns an explicit
    partial flag instead of guessing that page one is the entire result set.
    """
    return f"""
async () => {{
  const query = {json.dumps(query, ensure_ascii=False)};
  const journal = {json.dumps(journal, ensure_ascii=False)};
  const maxResults = {int(max_per_query)};
  const maxPages = {int(max_pages)};
  const clean = value => (value || '').replace(/\\s+/g, ' ').trim();
  const waitFor = async (predicate, attempts = 60) => {{
    for (let attempt = 0; attempt < attempts; attempt += 1) {{
      if (predicate()) return true;
      await new Promise(resolve => setTimeout(resolve, 500));
    }}
    return false;
  }};
  const captchaVisible = () => {{
    const captcha = document.querySelector('#tcaptcha_transform_dy');
    return Boolean(captcha && captcha.getBoundingClientRect().top >= 0);
  }};
  if (captchaVisible()) return {{ error: 'captcha' }};

  const hasResultRows = () => Boolean(document.querySelector('.result-table-list tbody tr'));
  if (!hasResultRows()) {{
    const ready = await waitFor(() => document.querySelector('.gradeSearch') || captchaVisible());
    if (!ready) return {{ error: 'search_form_timeout' }};
    if (captchaVisible()) return {{ error: 'captcha' }};
    const inputs = Array.from(document.querySelectorAll('.gradeSearch input[type="text"]'));
    const searchButton = document.querySelector('.gradeSearch button');
    if (inputs.length < 1 || !searchButton) return {{ error: 'advanced_form_missing' }};
    inputs[0].value = query;
    inputs[0].dispatchEvent(new Event('input', {{ bubbles: true }}));
    // The current KNS8 advanced form places the exact-source field third.
    if (journal && inputs.length >= 3) {{
      inputs[2].value = journal;
      inputs[2].dispatchEvent(new Event('input', {{ bubbles: true }}));
    }}
    searchButton.click();
    const gotResults = await waitFor(() => hasResultRows() || captchaVisible());
    if (!gotResults) return {{ error: 'results_timeout' }};
    if (captchaVisible()) return {{ error: 'captcha' }};
  }};

  const papers = [];
  const seen = new Set();
  let total = '0';
  let page = '';
  let pagesRead = 0;
  let partial = false;
  while (pagesRead < maxPages && papers.length < maxResults) {{
    const rows = Array.from(document.querySelectorAll('.result-table-list tbody tr'));
    const checkboxes = Array.from(document.querySelectorAll('.result-table-list tbody input.cbItem'));
    total = clean(document.querySelector('.pagerTitleCell')?.innerText || total).match(/([\\d,]+)/)?.[1] || total;
    page = clean(document.querySelector('.countPageMark')?.innerText || page);
    rows.forEach((row, index) => {{
      const titleLink = row.querySelector('td.name a.fz14') || row.querySelector('td.name a');
      const title = clean(titleLink?.innerText);
      if (!title || seen.has(title) || papers.length >= maxResults) return;
      seen.add(title);
      const authors = Array.from(row.querySelectorAll('td.author a.KnowledgeNetLink'))
        .map(node => clean(node.innerText)).filter(Boolean);
      papers.push({{
        n: papers.length + 1,
        title,
        href: titleLink?.href || '',
        exportId: checkboxes[index]?.value || '',
        authors: authors.length ? authors.join('; ') : clean(row.querySelector('td.author')?.innerText),
        journal: clean(row.querySelector('td.source a')?.innerText || row.querySelector('td.source')?.innerText),
        date: clean(row.querySelector('td.date')?.innerText),
        database: clean(row.querySelector('td.data')?.innerText),
        citations: clean(row.querySelector('td.quote')?.innerText),
        downloads: clean(row.querySelector('td.download')?.innerText),
      }});
    }});
    pagesRead += 1;
    if (papers.length >= maxResults) {{ partial = true; break; }}
    const beforePage = page;
    const next = document.querySelector('.pages-next:not(.disabled), a.pages-next') ||
      Array.from(document.querySelectorAll('.pager a, .pages a')).find(
        node => ['>>', '下一页'].includes(clean(node.innerText))
      );
    if (!next) break;
    next.click();
    const advanced = await waitFor(
      () => clean(document.querySelector('.countPageMark')?.innerText) !== beforePage || captchaVisible()
    );
    if (!advanced || captchaVisible()) {{ partial = true; break; }}
  }}
  if (pagesRead >= maxPages) partial = true;
  return {{ query, journal, total, page, pagesRead, partial, results: papers }};
}}
"""


def _fetch_cnki_with_browser(config: Dict, queries: List[str], cnki_config: Dict) -> Optional[List[Dict]]:
    max_per_query = int(cnki_config.get("max_results_per_query", 20))
    max_pages = int(cnki_config.get("max_pages_per_query", 5))
    all_papers = []
    seen_titles = set()

    for spec in _cnki_query_specs(cnki_config):
        query, journal = spec["query"], spec["journal"]
        script = _cnki_advanced_browser_script(query, journal, max_per_query, max_pages)
        logger.info("CNKI advanced browser search: %s | source: %s", query, journal or "all")
        search_page_url = _cnki_url(cnki_config, "search_page_url", "/kns8s/AdvSearch")
        data = evaluate_in_chrome(search_page_url, script, "CNKI", config, cnki_config)
        if data is None:
            return None
        if data.get("error") == "captcha":
            logger.warning("CNKI CAPTCHA required in Chrome; skipping browser backend.")
            return None
        if data.get("partial"):
            logger.warning(
                "CNKI query is partial after %s page(s): %s", data.get("pagesRead", 0), query
            )

        for item in data.get("results", [])[:max_per_query]:
            title = item.get("title", "")
            title_norm = normalize_title(title)
            if not title_norm or title_norm in seen_titles:
                continue
            seen_titles.add(title_norm)
            citation_match = re.search(r"\d+", str(item.get("citations", "")))
            venue = item.get("journal", "")
            paper = {
                "id": f"cnki-{hashlib.md5(title_norm.encode()).hexdigest()[:12]}",
                "title": title,
                "authors": item.get("authors", ""),
                "abstract": "",
                "published": item.get("date") or "unknown",
                "paper_url": _absolute_cnki_url(cnki_config, item.get("href", "")),
                "arxiv_id": "",
                "arxiv_url": "",
                "pdf_url": "",
                "preprint_pdf_url": "",
                "categories": [item.get("database", "")] if item.get("database") else [],
                "venue": venue,
                "conference": venue,
                "publication_types": [],
                "publication_type": "",
                "doi": "",
                "external_ids": {"CNKIExportId": item.get("exportId", "")},
                "semantic_scholar_id": "",
                "code_link": "",
                "tags": [],
                "keywords": [],
                "citation_count": int(citation_match.group(0)) if citation_match else 0,
                "impact_factor": get_impact_factor({"conference": venue}, IMPACT_FACTOR_TABLE),
                "source": "cnki",
            }
            if cnki_config.get("enrich_details", True):
                paper = enrich_cnki_paper(config, paper, cnki_config)
            all_papers.append(finalize_paper(paper, config))
        time.sleep(2)

    return all_papers

def fetch_cnki_papers(config: Dict, ss_api_key: str = "", arxiv_client=None) -> List[Dict]:
    """从 CNKI 知网抓取中文学术论文"""
    cnki_config = config.get("sources", {}).get("cnki", {})
    if not cnki_config.get("enabled", False):
        logger.info("CNKI 数据源已禁用")
        return []
    if os.environ.get("GITHUB_ACTIONS") == "true" and os.environ.get("ENABLE_CNKI", "").lower() != "true":
        logger.info(
            "CNKI skipped on GitHub Actions: CNKI requires an authenticated institution/VPN "
            "browser session or a reachable proxy. Set ENABLE_CNKI=true only on a runner "
            "with that access."
        )
        return []

    queries = flatten_queries(cnki_config.get("queries", []))
    max_per_query = cnki_config.get("max_results_per_query", 20)

    browser_papers = _fetch_cnki_with_browser(config, queries, cnki_config)
    if browser_papers is not None:
        logger.info(f"CNKI browser backend returned {len(browser_papers)} papers")
        return browser_papers

    all_papers = []
    seen_titles = set()

    # 创建持久会话
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    })

    # 先访问主页获取 cookies
    try:
        session.get(_cnki_url(cnki_config, "home_url", "/"), timeout=15)
        time.sleep(1)
    except Exception as e:
        logger.warning(f"CNKI 主页访问失败: {e}")

    for query in queries:
        logger.info(f"CNKI 搜索: {query}")
        try:
            # 第一步：发起搜索请求，获取搜索结果页
            search_url = _cnki_url(cnki_config, "default_result_url", "/kns8s/defaultresult/index")
            params = {
                "classid": "WD0",
                "korder": "SU",
                "kw": query,
                "crossDbcodes": "CJFQ",
            }
            resp = session.get(search_url, params=params, timeout=30)
            if resp.status_code != 200:
                logger.warning(f"CNKI 搜索返回 {resp.status_code}")
                continue

            # 第二步：POST 请求获取结果数据（CNKI 的 AJAX 加载方式）
            time.sleep(1)
            grid_url = _cnki_url(cnki_config, "grid_url", "/kns8s/brief/grid")
            form_data = {
                "action": "",
                "NaviCode": "*",
                "ua": "1.21",
                "PageName": "ASP.brief_result_aspx",
                "DbPrefix": "CJFQ",
                "DbCatalog": "中国学术期刊网络出版总库",
                "ConfigFile": "CJFQINDEX.xml",
                "db_opt": "CJFQ",
                "txt_1_sel": "SU",
                "txt_1_value1": query,
                "his": "0",
                "parentdb": "CJFQ",
                " CurPage": "1",
                "RecordsCntPerPage": str(max_per_query),
            }
            grid_resp = session.post(grid_url, data=form_data, timeout=30)
            if grid_resp.status_code != 200:
                logger.warning(f"CNKI 结果页返回 {grid_resp.status_code}")
                continue

            # 解析 HTML 结果
            soup = BeautifulSoup(grid_resp.text, "lxml")

            # CNKI 结果在 table.result-table-list 或 div.docs-shell 中
            items = soup.select("table.result-table-list tbody tr")
            if not items:
                items = soup.select("table.result-table-list tr")
            if not items:
                # 尝试从静态搜索页解析
                soup_main = BeautifulSoup(resp.text, "lxml")
                items = soup_main.select("table.result-table-list tbody tr")
                if not items:
                    items = soup_main.select("table.result-table-list tr")

            if not items:
                logger.info(f"  → CNKI 未找到结果（可能需要 JavaScript 渲染）: {query}")
                continue

            for item in items[:max_per_query]:
                try:
                    # 标题
                    title_elem = item.select_one("td.name a.fz14") or item.select_one("td.name a")
                    if not title_elem:
                        continue
                    title = title_elem.get_text(strip=True)
                    title_norm = normalize_title(title)
                    if title_norm in seen_titles:
                        continue
                    seen_titles.add(title_norm)

                    # 链接
                    href = title_elem.get("href", "")
                    paper_url = _absolute_cnki_url(cnki_config, href)

                    # 作者
                    author_elem = item.select_one("td.author") or item.select_one("td.author a")
                    authors = author_elem.get_text(strip=True) if author_elem else ""

                    # 期刊/来源
                    journal_elem = item.select_one("td.source a") or item.select_one("td.source")
                    venue = journal_elem.get_text(strip=True) if journal_elem else ""

                    # 发表日期
                    date_elem = item.select_one("td.date")
                    pub_date = date_elem.get_text(strip=True) if date_elem else ""

                    # 引用次数
                    cite_elem = item.select_one("td.quote")
                    citations = 0
                    if cite_elem:
                        try:
                            citations = int(cite_elem.get_text(strip=True) or "0")
                        except ValueError:
                            pass

                    paper = {
                        "id": f"cnki-{hashlib.md5(title_norm.encode()).hexdigest()[:12]}",
                        "title": title,
                        "authors": authors,
                        "abstract": "",
                        "published": pub_date or "unknown",
                        "paper_url": paper_url,
                        "arxiv_id": "",
                        "arxiv_url": "",
                        "pdf_url": "",
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
                        "citation_count": citations,
                        "impact_factor": get_impact_factor({"conference": venue}, IMPACT_FACTOR_TABLE),
                        "source": "cnki",
                    }

                    if cnki_config.get("enrich_details", True):
                        paper = enrich_cnki_paper(config, paper, cnki_config, session=session)
                    paper = finalize_paper(paper, config)
                    all_papers.append(paper)

                except Exception as e:
                    logger.warning(f"CNKI 解析单条结果失败: {e}")
                    continue

            logger.info(f"  → CNKI 获取 {len([p for p in all_papers if p.get('source') == 'cnki'])} 篇")
            time.sleep(2)

        except Exception as e:
            logger.warning(f"CNKI 查询失败 ({query}): {e}")
            continue

    logger.info(f"CNKI 共获取 {len(all_papers)} 篇论文")
    return all_papers
