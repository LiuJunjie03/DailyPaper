"""CNKI (中国知网) 数据源"""
import requests
import time
import re
import json
import hashlib
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from fetchers.browser import evaluate_in_chrome
from fetchers.cnki_detail import enrich_cnki_paper

logger = logging.getLogger(__name__)


DEFAULT_KNS_BASE_URL = "https://kns.cnki.net"

from daily_paper.text import normalize_title


def _cnki_url(cnki_config: Dict, key: str, default_path: str) -> str:
    # 优先使用环境变量（CNKI_HOME_URL / CNKI_KNS_BASE_URL）
    env_key = f"CNKI_{key.upper()}"
    env_val = os.environ.get(env_key, "").strip()
    if env_val:
        return env_val
    configured = cnki_config.get(key)
    if configured:
        return configured
    base_url = os.environ.get("CNKI_KNS_BASE_URL", "").strip() or cnki_config.get("kns_base_url") or DEFAULT_KNS_BASE_URL
    return urljoin(base_url.rstrip("/") + "/", default_path.lstrip("/"))


def _absolute_cnki_url(cnki_config: Dict, href: str) -> str:
    href = href or ""
    if href.startswith(("http://", "https://")):
        return href
    base_url = cnki_config.get("detail_base_url") or cnki_config.get("kns_base_url") or DEFAULT_KNS_BASE_URL
    return urljoin(base_url.rstrip("/") + "/", href.lstrip("/"))


def _fetch_cnki_with_browser(fetcher, queries: List[str], cnki_config: Dict) -> Optional[List[Dict]]:
    max_per_query = int(cnki_config.get("max_results_per_query", 20))
    all_papers = []
    seen_titles = set()

    for query in queries:
        script = f"""
async () => {{
  const query = {json.dumps(query, ensure_ascii=False)};
  await new Promise((resolve, reject) => {{
    let n = 0;
    const tick = () => {{
      if (document.title.includes('安全验证') || document.body.innerText.includes('向右滑动完成验证')) resolve();
      if (document.querySelector('input.search-input')) resolve();
      else if (++n > 30) reject(new Error('search input timeout'));
      else setTimeout(tick, 500);
    }};
    tick();
  }});
  if (document.title.includes('安全验证') || document.body.innerText.includes('向右滑动完成验证')) {{
    return {{ error: 'captcha', message: 'CNKI requires slider verification.' }};
  }}
  const captcha = document.querySelector('#tcaptcha_transform_dy');
  if (captcha && captcha.getBoundingClientRect().top >= 0) return {{ error: 'captcha' }};
  const input = document.querySelector('input.search-input');
  input.value = query;
  input.dispatchEvent(new Event('input', {{ bubbles: true }}));
  document.querySelector('input.search-btn')?.click();
  await new Promise((resolve, reject) => {{
    let n = 0;
    const tick = () => {{
      if (document.querySelector('.result-table-list tbody tr') || document.querySelector('.pagerTitleCell')) resolve();
      else if (++n > 40) reject(new Error('results timeout'));
      else setTimeout(tick, 500);
    }};
    tick();
  }});
  const captcha2 = document.querySelector('#tcaptcha_transform_dy');
  if (captcha2 && captcha2.getBoundingClientRect().top >= 0) return {{ error: 'captcha' }};
  const rows = document.querySelectorAll('.result-table-list tbody tr');
  const checkboxes = document.querySelectorAll('.result-table-list tbody input.cbItem');
  const results = Array.from(rows).slice(0, {max_per_query}).map((row, i) => {{
    const titleLink = row.querySelector('td.name a.fz14') || row.querySelector('td.name a');
    const authors = Array.from(row.querySelectorAll('td.author a.KnowledgeNetLink') || []).map(a => a.innerText?.trim()).filter(Boolean);
    const authorText = authors.length ? authors.join('; ') : (row.querySelector('td.author')?.innerText?.trim() || '');
    return {{
      n: i + 1,
      title: titleLink?.innerText?.trim() || '',
      href: titleLink?.href || '',
      exportId: checkboxes[i]?.value || '',
      authors: authorText,
      journal: row.querySelector('td.source a')?.innerText?.trim() || row.querySelector('td.source')?.innerText?.trim() || '',
      date: row.querySelector('td.date')?.innerText?.trim() || '',
      database: row.querySelector('td.data')?.innerText?.trim() || '',
      citations: row.querySelector('td.quote')?.innerText?.trim() || '0',
      downloads: row.querySelector('td.download')?.innerText?.trim() || ''
    }};
  }});
  return {{
    query,
    total: document.querySelector('.pagerTitleCell')?.innerText?.match(/([\\d,]+)/)?.[1] || '0',
    page: document.querySelector('.countPageMark')?.innerText || '1/1',
    results
  }};
}}
"""
        logger.info(f"CNKI browser search: {query}")
        search_page_url = _cnki_url(cnki_config, "search_page_url", "/kns8s/search")
        data = evaluate_in_chrome(search_page_url, script, "CNKI", fetcher.config, cnki_config)
        if data is None:
            return None
        if data.get("error") == "captcha":
            logger.warning("CNKI CAPTCHA required in Chrome; skipping browser backend.")
            return None

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
                "impact_factor": fetcher.get_impact_factor({"conference": venue}),
                "source": "cnki",
            }
            if cnki_config.get("enrich_details", True):
                paper = enrich_cnki_paper(fetcher, paper, cnki_config)
            all_papers.append(fetcher._finalize_paper(paper))
        time.sleep(2)

    return all_papers

def fetch_cnki_papers(fetcher) -> List[Dict]:
    """从 CNKI 知网抓取中文学术论文"""
    cnki_config = fetcher.config.get("sources", {}).get("cnki", {})
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

    queries = fetcher._flatten_queries(cnki_config.get("queries", []))
    max_per_query = cnki_config.get("max_results_per_query", 20)

    browser_papers = _fetch_cnki_with_browser(fetcher, queries, cnki_config)
    if browser_papers is not None:
        logger.info(f"CNKI browser backend returned {len(browser_papers)} papers")
        return browser_papers

    all_papers = []
    seen_titles = set()

    # 创建持久会话
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
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
                        "impact_factor": fetcher.get_impact_factor({"conference": venue}),
                        "source": "cnki",
                    }

                    if cnki_config.get("enrich_details", True):
                        paper = enrich_cnki_paper(fetcher, paper, cnki_config, session=session)
                    paper = fetcher._finalize_paper(paper)
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
