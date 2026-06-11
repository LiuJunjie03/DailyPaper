"""OpenAlex 数据源 — 通过关键词搜索发现论文"""
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from daily_paper.dates import validate_date
from daily_paper.http import request_json
from daily_paper.normalizer import IMPACT_FACTOR_TABLE, finalize_paper, get_impact_factor
from daily_paper.queries import flatten_queries

logger = logging.getLogger(__name__)


def _openalex_abstract(inverted_index: Optional[Dict]) -> str:
    """从 OpenAlex 的 inverted index 重建摘要文本"""
    if not inverted_index:
        return ""
    words = []
    for word, positions in inverted_index.items():
        for pos in positions:
            words.append((pos, word))
    return " ".join(word for _, word in sorted(words))


def fetch_openalex_papers(config: Dict, ss_api_key: str = "", arxiv_client=None) -> List[Dict]:
    """从 OpenAlex 搜索论文"""
    source_config = config.get("sources", {}).get("openalex", {})
    if not source_config.get("enabled", False):
        logger.info("OpenAlex 数据源已禁用")
        return []

    # 解析查询列表
    queries = flatten_queries(source_config)

    max_per_query = source_config.get("max_results_per_query", 20)
    days_back = source_config.get("days_back", 180)
    mailto = source_config.get("mailto", "")
    from_date = validate_date(source_config.get("start_date", "")) or (
        datetime.now(timezone.utc) - timedelta(days=days_back)
    ).strftime("%Y-%m-%d")
    until_date = validate_date(source_config.get("end_date", ""))

    all_papers = []
    seen_ids = set()

    for query in queries:
        logger.info(f"OpenAlex 搜索: {query}")
        date_filter = f"from_publication_date:{from_date}"
        if until_date:
            date_filter += f",to_publication_date:{until_date}"
        params = {
            "search": query,
            "per_page": max_per_query,
            "mailto": mailto,
            "filter": date_filter,
            "sort": "cited_by_count:desc",
        }

        data = request_json("https://api.openalex.org/works", params=params)
        if not data:
            logger.warning(f"OpenAlex 查询无响应: {query}")
            continue

        results = data.get("results") or []
        query_count = 0

        for item in results:
            # 去重 ID（优先 DOI，其次 OpenAlex ID）
            raw_doi = (item.get("doi") or "").replace("https://doi.org/", "")
            openalex_id = (item.get("id") or "").rsplit("/", 1)[-1] if item.get("id") else ""
            dedup_id = raw_doi or openalex_id
            if not dedup_id:
                continue
            if dedup_id in seen_ids:
                continue
            seen_ids.add(dedup_id)

            # 标题
            title = (item.get("title") or "").strip()
            if not title:
                continue

            # 作者
            authorships = item.get("authorships") or []
            authors = ", ".join(
                (a.get("author") or {}).get("display_name", "")
                for a in authorships
                if (a.get("author") or {}).get("display_name")
            )

            # 摘要（从 inverted index 重建）
            abstract = _openalex_abstract(item.get("abstract_inverted_index"))

            # 发表日期
            published = item.get("publication_date") or ""

            # 期刊/来源
            primary_location = item.get("primary_location") or {}
            source_info = primary_location.get("source") or {}
            venue = source_info.get("display_name") or ""

            # 引用数
            citation_count = item.get("cited_by_count")

            # 开放获取 PDF
            oa = item.get("open_access") or {}
            pdf_url = oa.get("oa_url") or ""

            # 论文类型
            work_type = item.get("type") or ""

            # ArXiv ID（从 DOI 或定位信息推断）
            arxiv_id = ""
            if raw_doi and "arxiv" in raw_doi.lower():
                # 某些 ArXiv 论文的 DOI 格式为 10.48550/arXiv.xxxx.xxxxx
                match = re.search(r"arxiv\.(\d{4}\.\d{4,5})", raw_doi, re.IGNORECASE)
                if match:
                    arxiv_id = match.group(1)
            arxiv_url = f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else ""
            preprint_pdf_url = f"https://arxiv.org/pdf/{arxiv_id}" if arxiv_id else ""

            paper = {
                "id": raw_doi or f"oa-{openalex_id}",
                "title": title,
                "authors": authors,
                "abstract": abstract,
                "published": published,
                "paper_url": f"https://doi.org/{raw_doi}" if raw_doi else (item.get("doi") or ""),
                "arxiv_id": arxiv_id,
                "arxiv_url": arxiv_url,
                "pdf_url": pdf_url,
                "preprint_pdf_url": preprint_pdf_url,
                "categories": [],
                "venue": venue,
                "conference": venue,
                "publication_types": [work_type] if work_type else [],
                "publication_type": "",
                "doi": raw_doi,
                "external_ids": {"OpenAlex": openalex_id} if openalex_id else {},
                "semantic_scholar_id": "",
                "code_link": "",
                "tags": [],
                "keywords": [],
                "citation_count": citation_count,
                "impact_factor": get_impact_factor({"conference": venue}, IMPACT_FACTOR_TABLE),
                "source": "openalex",
            }

            paper = finalize_paper(paper, config)
            all_papers.append(paper)
            query_count += 1

        logger.info(f"  → 获取 {query_count} 篇，累计 {len(all_papers)} 篇")
        time.sleep(1)  # 礼貌延迟

    logger.info(f"OpenAlex 共获取 {len(all_papers)} 篇去重论文")
    return all_papers
