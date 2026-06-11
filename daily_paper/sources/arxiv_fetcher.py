"""ArXiv 数据源"""
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import arxiv

from daily_paper.normalizer import IMPACT_FACTOR_TABLE, finalize_paper, get_impact_factor
from daily_paper.classify import extract_paper_keywords, extract_official_keywords
from daily_paper.sources._citation_batch import batch_get_citation_counts  # noqa: F401

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
#  流水线子函数
# ═══════════════════════════════════════════════════════════

def _build_arxiv_query(arxiv_config: Dict) -> Tuple[str, datetime, Optional[datetime], Dict]:
    """从配置构建 ArXiv 搜索查询、日期范围和搜索对象"""
    arxiv_categories = arxiv_config.get("categories", [])
    days_back = arxiv_config.get("days_back", 60)
    configured_start = arxiv_config.get("start_date", "")
    configured_end = arxiv_config.get("end_date", "")
    max_results = arxiv_config.get("max_results", 1000)

    # 构建分类查询
    if arxiv_categories:
        cat_query = " OR ".join([f"cat:{cat}" for cat in arxiv_categories])
    else:
        cat_query = ""
    fluid_kw = "CFD OR fluid dynamics OR turbulence OR aerodynamics OR multiphase flow OR computational fluid dynamics"
    kw_query = f"({fluid_kw})"

    # 构建日期过滤
    date_query = ""
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(configured_start or "")):
        end_value = (
            configured_end
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(configured_end or ""))
            else datetime.now(timezone.utc).strftime("%Y-%m-%d")
        )
        start_token = str(configured_start).replace("-", "") + "0000"
        end_token = str(end_value).replace("-", "") + "2359"
        date_query = f"submittedDate:[{start_token} TO {end_token}]"

    if cat_query:
        query = f"({cat_query}) AND {kw_query}"
    else:
        query = kw_query
    if date_query:
        query = f"({query}) AND {date_query}"

    # 计算时间范围
    start_date = (
        datetime.strptime(configured_start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(configured_start or ""))
        else datetime.now(timezone.utc) - timedelta(days=days_back)
    )
    end_date = (
        datetime.strptime(configured_end, "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(days=1)
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(configured_end or ""))
        else None
    )

    search = arxiv.Search(
        query=query,
        max_results=max_results,
        sort_by=arxiv.SortCriterion.SubmittedDate,
        sort_order=arxiv.SortOrder.Descending,
    )

    logger.info(f"ArXiv查询条件: {query}")
    logger.info(f"开始抓取：近{days_back}天，最多{max_results}篇，分类：{arxiv_categories}")
    return start_date, end_date, search, max_results


def _arxiv_result_to_paper(result, config: Dict) -> Dict:
    """将 ArXiv search result 转换为论文字典"""
    published = result.published
    if published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)

    paper = {
        "id": result.entry_id.split("/")[-1],
        "title": result.title,
        "authors": ", ".join([author.name for author in result.authors]),
        "abstract": result.summary.replace("\n", " ").strip(),
        "published": published.strftime("%Y-%m-%d"),
        "paper_url": result.entry_id,
        "arxiv_id": result.entry_id.split("/")[-1],
        "arxiv_url": result.entry_id,
        "pdf_url": result.pdf_url,
        "categories": result.categories,
        "venue": "",
        "conference": "",
        "publication_types": ["Preprint"],
        "publication_type": "preprint",
        "is_preprint": True,
        "doi": "",
        "external_ids": {"ArXiv": result.entry_id.split("/")[-1]},
        "code_link": "",
        "tags": [],
        "source": "arxiv",
        "official_keywords": extract_official_keywords(result),
        "custom_keywords": [],
        "keywords": [],
    }

    # venue 匹配（从 comment 字段）
    if result.comment:
        venues = config.get("venues", {})
        all_venues = venues.get("conferences", []) + venues.get("journals", [])
        for venue in all_venues:
            if venue.lower() in result.comment.lower():
                paper["conference"] = venue
                break

    # 分类 + 关键词
    paper = finalize_paper(paper, config)
    paper["custom_keywords"] = extract_paper_keywords(paper, config)
    paper["keywords"] = list(set(paper["official_keywords"] + paper["custom_keywords"]))
    paper["impact_factor"] = get_impact_factor(paper, IMPACT_FACTOR_TABLE)
    return paper


def _filter_and_collect_arxiv(client, search, start_date: datetime, end_date: Optional[datetime], config: Dict) -> Tuple[List[Dict], List[Dict]]:
    """遍历 ArXiv 搜索结果，过滤日期并收集论文"""
    papers_high_if = []
    papers_other = []
    for result in client.results(search):
        published = result.published
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        if published < start_date or (end_date and published > end_date):
            continue

        paper = _arxiv_result_to_paper(result, config)
        # 按影响因子分组
        if paper["tags"]:
            if paper["impact_factor"] and paper["impact_factor"] >= 3.0:
                papers_high_if.append(paper)
            else:
                papers_other.append(paper)
    return papers_high_if, papers_other


def _apply_citations_and_sort(papers_high_if: List[Dict], papers_other: List[Dict], max_results: int, ss_api_key: str) -> List[Dict]:
    """批量获取引用数，并按影响因子优先排序"""
    all_collected = papers_high_if + papers_other
    if all_collected:
        logger.info(f"批量获取 {len(all_collected)} 篇 ArXiv 论文的引用数...")
        citation_map = batch_get_citation_counts(all_collected, ss_api_key=ss_api_key)
        for p in all_collected:
            p["citation_count"] = citation_map.get(p["id"], None)

    selected = papers_high_if[:max_results]
    if len(selected) < max_results:
        selected += papers_other[:max_results - len(selected)]
    logger.info(f"抓取完成：高影响因子{len(papers_high_if)}篇，其他{len(papers_other)}篇，实际返回{len(selected)}篇")
    return selected


# ═══════════════════════════════════════════════════════════
#  主入口
# ═══════════════════════════════════════════════════════════

def fetch_arxiv_papers(config: Dict, ss_api_key: str = "", arxiv_client=None) -> List[Dict]:
    """从 ArXiv 抓取论文（编排流水线）"""
    arxiv_source_config = config.get("sources", {}).get("arxiv", {})
    if not arxiv_source_config.get("enabled", False):
        logger.warning("ArXiv数据源已禁用！")
        return []

    if arxiv_client is None:
        arxiv_client = arxiv.Client()

    start_date, end_date, search, max_results = _build_arxiv_query(arxiv_source_config)
    papers_high_if, papers_other = _filter_and_collect_arxiv(
        arxiv_client, search, start_date, end_date, config
    )
    return _apply_citations_and_sort(papers_high_if, papers_other, max_results, ss_api_key)
