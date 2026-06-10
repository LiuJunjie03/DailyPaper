"""Crossref 数据源 — 通过关键词搜索发现正式发表论文"""
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List

from daily_paper.dates import in_date_window, validate_date
from daily_paper.http import request_json
from daily_paper.queries import flatten_queries

logger = logging.getLogger(__name__)


def _date_from_crossref_parts(value) -> str:
    """从 CrossRef date-parts 提取日期（published-online > published-print > created）"""
    for field in ("published-online", "published-print", "created"):
        parts = (value or {}).get(field, {}).get("date-parts") or []
        if not parts or not parts[0]:
            continue
        dp = parts[0]
        y = dp[0] if len(dp) > 0 else None
        m = dp[1] if len(dp) > 1 else None
        d = dp[2] if len(dp) > 2 else None
        if not y or not m:
            continue
        if not d:
            d = 1
        return f"{y:04d}-{m:02d}-{d:02d}"
    return ""


def _clean_abstract(text: str) -> str:
    """清理 Crossref 返回的 JATS XML 摘要"""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def fetch_crossref_papers(fetcher) -> List[Dict]:
    """从 Crossref 搜索正式发表论文"""
    config = fetcher.config.get("sources", {}).get("crossref", {})
    if not config.get("enabled", False):
        logger.info("Crossref 数据源已禁用")
        return []

    # 解析查询列表
    queries = flatten_queries(config)

    max_per_query = config.get("max_results_per_query", 20)
    days_back = config.get("days_back", 180)
    from_date = validate_date(config.get("start_date", "")) or (
        datetime.now(timezone.utc) - timedelta(days=days_back)
    ).strftime("%Y-%m-%d")
    until_date = validate_date(config.get("end_date", ""))

    all_papers = []
    seen_dois = set()

    for query in queries:
        logger.info(f"Crossref 搜索: {query}")
        date_filter = f"from-pub-date:{from_date}"
        if until_date:
            date_filter += f",until-pub-date:{until_date}"
        params = {
            "query": query,
            "filter": date_filter,
            "rows": max_per_query,
        }

        data = request_json("https://api.crossref.org/works", params=params)
        if not data:
            logger.warning(f"Crossref 查询无响应: {query}")
            continue

        items = (data.get("message") or {}).get("items") or []
        query_count = 0

        for item in items:
            doi = (item.get("DOI") or "").strip().lower()
            if not doi:
                continue
            if doi in seen_dois:
                continue
            seen_dois.add(doi)

            # 标题
            title_list = item.get("title") or []
            title = " ".join(title_list).strip()
            if not title:
                continue

            # 作者
            author_list = item.get("author") or []
            authors = ", ".join(
                f"{a.get('given', '')} {a.get('family', '')}".strip()
                for a in author_list
            )

            # 摘要（Crossref 中部分论文有 JATS 格式摘要）
            abstract = _clean_abstract(item.get("abstract", ""))

            # 发表日期
            published = _date_from_crossref_parts(item)
            if not in_date_window(published, from_date, until_date):
                continue

            # 期刊/会议名
            container = item.get("container-title") or []
            venue = container[0].strip() if container else ""

            # 引用数
            citation_count = item.get("is-referenced-by-count")

            # 论文类型 —— 过滤非论文条目
            item_type = item.get("type", "")
            _SKIP_TYPES = {
                "editorial", "correction", "withdrawn",
                "book-review", "dissertation", "reference-entry",
            }
            if item_type in _SKIP_TYPES:
                continue
            if any(title.lower().startswith(p) for p in ("withdrawn", "correction:", "editorial board")):
                continue

            paper = {
                "id": doi,
                "title": title,
                "authors": authors,
                "abstract": abstract,
                "published": published,
                "paper_url": f"https://doi.org/{doi}",
                "arxiv_id": "",
                "arxiv_url": "",
                "pdf_url": "",
                "preprint_pdf_url": "",
                "categories": [],
                "venue": venue,
                "conference": venue,
                "publication_types": [item_type] if item_type else [],
                "publication_type": "",
                "doi": doi,
                "external_ids": {},
                "semantic_scholar_id": "",
                "code_link": "",
                "tags": [],
                "keywords": [],
                "citation_count": citation_count,
                "impact_factor": fetcher.get_impact_factor({"conference": venue}),
                "source": "crossref",
            }

            paper = fetcher._finalize_paper(paper)
            all_papers.append(paper)
            query_count += 1

        logger.info(f"  → 获取 {query_count} 篇，累计 {len(all_papers)} 篇")
        time.sleep(1)  # 礼貌延迟

    logger.info(f"Crossref 共获取 {len(all_papers)} 篇去重论文")
    return all_papers
