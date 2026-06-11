"""Semantic Scholar 数据源"""
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import requests

from daily_paper.dates import validate_date
from daily_paper.normalizer import IMPACT_FACTOR_TABLE, finalize_paper, get_impact_factor
from daily_paper.queries import flatten_queries
from daily_paper.text import normalize_doi
from daily_paper.sources._citation_batch import batch_get_citation_counts  # noqa: F401

logger = logging.getLogger(__name__)


def get_citation_count(title, authors=None, year=None):
    """通过 Semantic Scholar API 获取引用次数（单篇查询，保留兼容）"""
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
                paper = data["data"][0]
                return paper.get("citationCount", 0)
    except Exception as e:
        logger.warning(f"Semantic Scholar API 查询失败: {e}")
    return None


# ═══════════════════════════════════════════════════════════
#  流水线子函数
# ═══════════════════════════════════════════════════════════

def _build_ss_request_params(ss_config: Dict) -> Tuple[datetime, Optional[datetime], str, List[str], int]:
    """从配置构建 Semantic Scholar 搜索参数"""
    queries = flatten_queries(ss_config)
    max_per_query = ss_config.get("max_results_per_query", 100)
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
    return start_date, end_date, year_filter, queries, max_per_query


def _ss_request_with_retry(url: str, params: Dict, api_key: str = "") -> Optional[requests.Response]:
    """带重试和 429 处理的 SS API 请求"""
    headers = {}
    if api_key:
        headers["x-api-key"] = api_key
    for attempt in range(3):
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=30)
            if resp.status_code == 429:
                wait_seconds = 30 + attempt * 10
                logger.warning(f"Semantic Scholar API 限速，等待{wait_seconds}秒...")
                time.sleep(wait_seconds)
                continue
            return resp
        except requests.RequestException as e:
            wait_seconds = 5 * (attempt + 1)
            logger.warning(f"Semantic Scholar 网络请求失败，{wait_seconds}秒后重试: {e}")
            time.sleep(wait_seconds)
    return None


def _ss_item_to_paper(item: Dict, config: Dict, start_date: datetime, end_date: Optional[datetime]) -> Optional[Dict]:
    """将 Semantic Scholar 搜索结果条目转换为论文字典（含日期过滤）"""
    ext_ids = item.get("externalIds") or {}
    paper_id = ext_ids.get("DOI") or ext_ids.get("ArXiv") or item.get("paperId", "")

    # 日期过滤
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

    abstract = item.get("abstract") or ""
    title = item.get("title") or ""
    if not title:
        return None

    arxiv_id = ext_ids.get("ArXiv")
    doi = ext_ids.get("DOI") or ""
    arxiv_url = f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else ""
    preprint_pdf_url = f"https://arxiv.org/pdf/{arxiv_id}" if arxiv_id else ""
    oa_pdf = item.get("openAccessPdf") or {}
    pdf_url = oa_pdf["url"] if oa_pdf and oa_pdf.get("url") else ""

    authors_list = item.get("authors", [])
    authors_str = ", ".join(a.get("name", "") for a in authors_list if a.get("name"))
    journal = item.get("journal") or {}
    venue = (
        item.get("venue")
        or (item.get("publicationVenue") or {}).get("name")
        or journal.get("name")
        or ""
    )
    # 清洗截断省略号
    venue = re.sub(r"[…\.]{2,}", "", venue).strip(" ,;-")
    # "arXiv preprint arXiv:xxxx" 不是期刊名，清空
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
        "authors": authors_str,
        "abstract": abstract,
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


# ═══════════════════════════════════════════════════════════
#  主入口
# ═══════════════════════════════════════════════════════════

def fetch_semantic_scholar_papers(config: Dict, ss_api_key: str = "", arxiv_client=None) -> List[Dict]:
    """用 Semantic Scholar 语义搜索替代关键词匹配（编排流水线）"""
    ss_config = config.get("sources", {}).get("semantic_scholar", {})
    if not ss_config.get("enabled", False):
        logger.info("Semantic Scholar 数据源已禁用")
        return []

    start_date, end_date, year_filter, queries, max_per_query = _build_ss_request_params(ss_config)

    all_papers = []
    seen_ids = set()

    FIELDS = (
        "paperId,url,title,abstract,authors,year,citationCount,"
        "venue,publicationVenue,publicationDate,publicationTypes,"
        "externalIds,openAccessPdf,fieldsOfStudy,journal"
    )

    for query in queries:
        logger.info(f"Semantic Scholar 搜索: {query}")
        params = {
            "query": query,
            "fields": FIELDS,
            "limit": max_per_query,
            "year": year_filter,
        }

        try:
            resp = _ss_request_with_retry(
                "https://api.semanticscholar.org/graph/v1/paper/search",
                params,
                api_key=ss_api_key,
            )
            if resp is None or resp.status_code != 200:
                logger.warning(
                    f"Semantic Scholar API 请求失败{'，状态码 ' + str(resp.status_code) if resp else ''}"
                )
                continue

            results = resp.json().get("data", [])
            for item in results:
                ext_ids = item.get("externalIds") or {}
                paper_id = ext_ids.get("DOI") or ext_ids.get("ArXiv") or item.get("paperId", "")
                if paper_id in seen_ids:
                    continue
                seen_ids.add(paper_id)

                paper = _ss_item_to_paper(item, config, start_date, end_date)
                if paper:
                    all_papers.append(paper)

            logger.info(f"  → 获取 {len(results)} 篇，累计 {len(all_papers)} 篇")
            time.sleep(3)

        except Exception as e:
            logger.warning(f"Semantic Scholar 查询失败 ({query}): {e}")
            continue

    logger.info(f"Semantic Scholar 共获取 {len(all_papers)} 篇去重论文")
    return all_papers
